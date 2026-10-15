/*
 * Licensed to Elasticsearch B.V. under one or more contributor
 * license agreements. See the NOTICE file distributed with
 * this work for additional information regarding copyright
 * ownership. Elasticsearch B.V. licenses this file to you under
 * the Apache License, Version 2.0 (the "License"); you may
 * not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
package io.opentelemetry.javaagent.degradation;

import io.opentelemetry.javaagent.degradation.opampclient.OpampClient;
import io.opentelemetry.javaagent.degradation.opampclient.OpampClientBuilder;
import io.opentelemetry.javaagent.degradation.opampclient.internal.connectivity.http.OkHttpSender;
import io.opentelemetry.javaagent.degradation.opampclient.internal.request.delay.PeriodicDelay;
import io.opentelemetry.javaagent.degradation.opampclient.internal.request.delay.RetryPeriodicDelay;
import io.opentelemetry.javaagent.degradation.opampclient.internal.request.service.HttpRequestService;
import io.opentelemetry.javaagent.degradation.opampclient.internal.response.MessageData;
import io.opentelemetry.sdk.autoconfigure.spi.ConfigProperties;
import java.io.Closeable;
import java.io.IOException;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import java.util.logging.Logger;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import opamp.proto.v1.Opamp.AgentConfigObject;
import opamp.proto.v1.Opamp.AgentRemoteConfig;
import opamp.proto.v1.Opamp.RemoteConfigStatus;
import opamp.proto.v1.Opamp.RemoteConfigStatuses;
import opamp.proto.v1.Opamp.ServerErrorResponse;

/** Java 6 port of EDOT OpampManager using its upstream OpAMP client state machine. */
final class OpampConnection implements Closeable {
  private final OpampClient client;
  private final OkHttpSender sender;

  OpampConnection(
      String endpoint,
      Map<String, String> headers,
      ConfigProperties settings,
      String service,
      String environment,
      DegradationController controller,
      DegradationState state) {
    MutablePeriodicDelay delay = new MutablePeriodicDelay(Duration.ofSeconds(30));
    OkHttpClient.Builder http = new OkHttpClient.Builder();
    OpampTlsConfigurer.configure(
        http,
        endpoint,
        EdotSettings.setting(settings, "certificate"),
        EdotSettings.setting(settings, "client.key"),
        EdotSettings.setting(settings, "client.certificate"));
    http.interceptors()
        .add(
            chain -> {
              Request.Builder request = chain.request().newBuilder();
              for (Map.Entry<String, String> entry : headers.entrySet())
                request.addHeader(entry.getKey(), entry.getValue());
              return chain.proceed(request.build());
            });
    sender = OkHttpSender.create(endpoint, http.build());
    OpampClientBuilder builder =
        OpampClient.builder().enableRemoteConfig().putIdentifyingAttribute("service.name", service);
    if (environment != null)
      builder.putIdentifyingAttribute("deployment.environment.name", environment);
    builder.setRequestService(
        HttpRequestService.create(
            sender, delay, RetryPeriodicDelay.create(Duration.ofSeconds(30))));
    client = builder.build(new Callbacks(controller, state, delay));
  }

  @Override
  public void close() throws IOException {
    try {
      client.close();
    } finally {
      sender.close();
    }
  }

  private static final class Callbacks implements OpampClient.Callbacks {
    private final Logger logger = Logger.getLogger(Callbacks.class.getName());
    private final DegradationController controller;
    private final DegradationState state;
    private final MutablePeriodicDelay pollingDelay;
    private boolean failed;

    Callbacks(
        DegradationController controller, DegradationState state, MutablePeriodicDelay delay) {
      this.controller = controller;
      this.state = state;
      this.pollingDelay = delay;
    }

    public void onMessage(OpampClient client, MessageData message) {
      AgentRemoteConfig remote = message.getRemoteConfig();
      if (remote == null) return;
      AgentConfigObject file = remote.getConfig().getConfigMapMap().get("otel");
      if (file == null) return; // EDOT ignores configurations outside its namespace.
      RemoteConfigStatus.Builder ack = RemoteConfigStatus.newBuilder();
      try {
        if (file.getBody().isEmpty() || file.getBody().size() > 65536)
          throw new IOException("Invalid configuration size");
        // EDOT accepts the JSON body independently of content_type metadata.
        DegradationConfig next =
            DegradationConfig.parse(file.getBody().toByteArray(), state.config);
        controller.apply(next);
        pollingDelay.setDelay(next.interval);
        ack.setStatus(RemoteConfigStatuses.RemoteConfigStatuses_APPLIED)
            .setLastRemoteConfigHash(remote.getConfigHash());
      } catch (IOException | RuntimeException invalid) {
        // Like EDOT, FAILED carries no applied hash. Never acknowledge an unapplied config.
        ack.setStatus(RemoteConfigStatuses.RemoteConfigStatuses_FAILED);
        logger.warning("OpAMP configuration rejected; previous configuration retained");
      }
      client.setRemoteConfigStatus(ack.build());
    }

    public void onConnect(OpampClient client) {
      if (failed) logger.info("OpAMP connection restored");
      failed = false;
    }

    public void onConnectFailed(OpampClient client, Throwable error) {
      if (!failed) logger.warning("OpAMP connection unavailable; previous configuration retained");
      failed = true;
    }

    public void onErrorResponse(OpampClient client, ServerErrorResponse error) {
      logger.warning("OpAMP server rejected request; previous configuration retained");
    }
  }

  private static final class MutablePeriodicDelay implements PeriodicDelay {
    private final AtomicReference<Duration> duration = new AtomicReference<>();

    MutablePeriodicDelay(Duration initial) {
      duration.set(initial);
    }

    public Duration getNextDelay() {
      return duration.get();
    }

    public void reset() {}

    void setDelay(Duration value) {
      duration.set(value);
    }
  }
}
