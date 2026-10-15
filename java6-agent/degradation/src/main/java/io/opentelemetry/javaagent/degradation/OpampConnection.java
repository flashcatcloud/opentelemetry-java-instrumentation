/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package io.opentelemetry.javaagent.degradation;

import com.google.protobuf.ByteString;
import io.opentelemetry.exporter.sender.okhttp.internal.OkHttpHttpSenderProvider;
import io.opentelemetry.sdk.common.export.*;
import java.io.Closeable;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.ByteBuffer;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;
import java.util.logging.Logger;
import javax.net.ssl.SSLContext;
import javax.net.ssl.X509TrustManager;
import opamp.proto.v1.Anyvalue.*;
import opamp.proto.v1.Opamp.*;

/** HTTP/protobuf remote-config subset of OpAMP, using the existing Java 6 SDK transport. */
final class OpampConnection implements Closeable {
  private static final Logger logger = Logger.getLogger(OpampConnection.class.getName());
  private final HttpSender sender;
  private final Thread worker;
  private final DegradationController controller;
  private final DegradationState state;
  private final ByteString uid;
  private final AgentDescription description;
  private volatile boolean closed;
  // Only the worker owns protocol state. Retain and send the ACK on every request, including
  // retries.
  private RemoteConfigStatus ack;
  private long sequence;

  OpampConnection(
      String endpoint,
      Map<String, String> headers,
      String service,
      String environment,
      DegradationController controller,
      DegradationState state) {
    this.controller = controller;
    this.state = state;
    UUID id = UUID.randomUUID();
    uid =
        ByteString.copyFrom(
            ByteBuffer.allocate(16)
                .putLong(id.getMostSignificantBits())
                .putLong(id.getLeastSignificantBits())
                .array());
    description =
        AgentDescription.newBuilder()
            .addIdentifyingAttributes(attribute("service.name", service))
            .addIdentifyingAttributes(attribute("deployment.environment.name", environment))
            .build();
    sender = new OkHttpHttpSenderProvider().createSender(new SenderConfig(endpoint, headers));
    worker = new Thread(this::run, "otel-opamp-java6");
    worker.setDaemon(true);
    try {
      worker.start();
    } catch (RuntimeException e) {
      sender.shutdown();
      throw e;
    }
  }

  private static KeyValue attribute(String key, String value) {
    return KeyValue.newBuilder()
        .setKey(key)
        .setValue(AnyValue.newBuilder().setStringValue(value))
        .build();
  }

  private void run() {
    boolean failed = false;
    while (!closed) {
      long delay = state.config.interval.toMillis();
      try {
        AgentToServer.Builder request =
            AgentToServer.newBuilder()
                .setInstanceUid(uid)
                .setSequenceNum(sequence++)
                .setCapabilities(0x1003)
                .setAgentDescription(description);
        if (ack != null) request.setRemoteConfigStatus(ack);
        ServerToAgent response = exchange(request.build().toByteArray());
        if (!response.getInstanceUid().equals(uid))
          throw new IOException("Unexpected instance identity");
        if (response.hasErrorResponse()) throw new IOException("Server rejected request");
        if (failed) logger.info("OpAMP connection restored");
        failed = false;
        if (response.hasRemoteConfig()) {
          AgentRemoteConfig remote = response.getRemoteConfig();
          // Resends of an already applied/rejected hash are idempotent. ACK remains queued.
          if (ack == null || !ack.getLastRemoteConfigHash().equals(remote.getConfigHash())) {
            RemoteConfigStatus.Builder status =
                RemoteConfigStatus.newBuilder().setLastRemoteConfigHash(remote.getConfigHash());
            try {
              if (remote.getConfigHash().isEmpty() || remote.getConfigHash().size() > 32)
                throw new IOException("Invalid hash");
              AgentConfigObject file = remote.getConfig().getConfigMapMap().get("elastic");
              if (file == null
                  || !file.getContentType().equals("application/json")
                  || file.getBody().size() > 65536) throw new IOException("Invalid config");
              controller.apply(DegradationConfig.parse(file.getBody().toByteArray()));
              status.setStatus(RemoteConfigStatuses.RemoteConfigStatuses_APPLIED);
            } catch (IOException | RuntimeException e) {
              status
                  .setStatus(RemoteConfigStatuses.RemoteConfigStatuses_FAILED)
                  .setErrorMessage("Invalid or unsupported degradation configuration");
              logger.warning("OpAMP degradation configuration rejected; previous state retained");
            }
            ack = status.build();
            delay = 0; // Immediately report the new configuration status.
          }
        }
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        break;
      } catch (IOException | RuntimeException e) {
        if (!failed && !closed)
          logger.warning("OpAMP connection unavailable; retaining last configuration");
        failed = true;
        delay = 5000;
      }
      try {
        if (!closed && delay > 0) Thread.sleep(delay);
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        break;
      }
    }
  }

  private ServerToAgent exchange(byte[] bytes) throws IOException, InterruptedException {
    CountDownLatch done = new CountDownLatch(1);
    AtomicReference<HttpResponse> response = new AtomicReference<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();
    sender.send(
        new MessageWriter() {
          public void writeMessage(OutputStream out) throws IOException {
            out.write(bytes);
          }

          public int getContentLength() {
            return bytes.length;
          }
        },
        value -> {
          response.set(value);
          done.countDown();
        },
        error -> {
          failure.set(error);
          done.countDown();
        });
    if (!done.await(15, TimeUnit.SECONDS)) {
      // Do not accumulate requests if a transport violates its 10-second deadline.
      closed = true;
      sender.shutdown();
      throw new IOException("Transport deadline exceeded");
    }
    HttpResponse value = response.get();
    if (failure.get() != null || value == null || value.getStatusCode() != 200)
      throw new IOException("OpAMP request failed");
    return ServerToAgent.parseFrom(value.getResponseBody());
  }

  @Override
  public void close() throws IOException {
    closed = true;
    worker.interrupt();
    sender.shutdown().join(5, TimeUnit.SECONDS);
    try {
      worker.join(5000);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
    }
  }

  private static final class SenderConfig implements HttpSenderConfig {
    private final URI endpoint;
    private final Map<String, List<String>> headers = new HashMap<>();

    SenderConfig(String endpoint, Map<String, String> headers) {
      this.endpoint = URI.create(endpoint);
      for (Map.Entry<String, String> entry : headers.entrySet())
        this.headers.put(entry.getKey(), Collections.singletonList(entry.getValue()));
    }

    public URI getEndpoint() {
      return endpoint;
    }

    public String getContentType() {
      return "application/x-protobuf";
    }

    public Compressor getCompressor() {
      return null;
    }

    public Duration getTimeout() {
      return Duration.ofSeconds(10);
    }

    public Duration getConnectTimeout() {
      return Duration.ofSeconds(10);
    }

    public Supplier<Map<String, List<String>>> getHeadersSupplier() {
      return () -> headers;
    }

    public ProxyOptions getProxyOptions() {
      return null;
    }

    public RetryPolicy getRetryPolicy() {
      return null;
    }

    public SSLContext getSslContext() {
      return null;
    }

    public X509TrustManager getTrustManager() {
      return null;
    }

    public ExecutorService getExecutorService() {
      return null;
    }

    public long getMaxResponseBodySize() {
      return 131072;
    }

    public List<String> getEnabledProtocols() {
      return null;
    }
  }
}
