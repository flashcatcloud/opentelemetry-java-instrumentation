/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package io.opentelemetry.javaagent.tooling;

import io.opentelemetry.exporter.internal.RetryUtil;
import io.opentelemetry.sdk.common.CompletableResultCode;
import io.opentelemetry.sdk.common.export.*;
import java8.util.function.Consumer;
import java.io.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.net.ssl.HttpsURLConnection;

/** Java 6 transport boundary. Configuration, batching and OTLP encoding belong to upstream. */
public final class Java6HttpSenderProvider implements HttpSenderProvider {
  public HttpSender createSender(HttpSenderConfig config) { return new Sender(config); }

  // Reused verbatim from SDK v1.66.0 RetryInterceptor. prepare-tooling.py checks
  // source identity; loading the whole OkHttp sender would require its newer JVM dependencies.
  static boolean isRetryableException(IOException e) {
    // Known retryable SocketTimeoutException messages: null, "connect timed out", "timeout"
    // Known retryable ConnectTimeout messages: "Failed to connect to
    // localhost/[0:0:0:0:0:0:0:1]:62611"
    // Known retryable UnknownHostException messages: "xxxxxx.com"
    // Known retryable SocketException: Socket closed
    if (e instanceof SocketTimeoutException) {
      return true;
    } else if (e instanceof ConnectException) {
      return true;
    } else if (e instanceof UnknownHostException) {
      return true;
    } else if (e instanceof SocketException) {
      return true;
    }
    return false;
  }

  private static final class Sender implements HttpSender {
    private final HttpSenderConfig config;
    private final ExecutorService worker;
    private final boolean ownsWorker;
    private final ScheduledThreadPoolExecutor timer;
    private final Set<Request> pending=Collections.synchronizedSet(new HashSet<Request>());
    private volatile boolean closed;
    Sender(HttpSenderConfig config) {
      this.config=config;
      if(config.getEndpoint().getUserInfo()!=null) throw new IllegalArgumentException("OTLP endpoint must not contain user information");
      Map<String,List<String>> initialHeaders=config.getHeadersSupplier().get();
      if(initialHeaders!=null) for(Map.Entry<String,List<String>> h:initialHeaders.entrySet()) for(String value:h.getValue()) validateHeader(h.getKey(),value);
      if(config.getEnabledProtocols()!=null) throw new IllegalArgumentException("Explicit TLS protocols are not yet supported by the Java 6 HTTP sender");
      ThreadFactory factory=new ThreadFactory() {
        public Thread newThread(Runnable r) { Thread t=new Thread(r,"otel-java6-http");t.setDaemon(true);return t; }
      };
      ownsWorker=config.getExecutorService()==null;
      worker=ownsWorker ? new ThreadPoolExecutor(1,2,30,TimeUnit.SECONDS,new ArrayBlockingQueue<Runnable>(64),factory) : config.getExecutorService();
      timer=new ScheduledThreadPoolExecutor(1,factory);
    }
    public void send(MessageWriter writer,Consumer<HttpResponse> response,Consumer<Throwable> error) {
      final byte[] payload;
      try {
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();
        OutputStream encoded=config.getCompressor()==null?bytes:config.getCompressor().compress(bytes);
        writer.writeMessage(encoded);encoded.close();payload=bytes.toByteArray();
      } catch(IOException e) {error.accept(e);return;}
      Request request=new Request(payload,response,error);
      if(closed) { error.accept(new IOException("OTLP sender closed"));return; }
      pending.add(request);
      try {
        request.deadlineTask=timer.schedule(new Runnable() { public void run() { request.fail(new SocketTimeoutException("OTLP request deadline exceeded")); } },config.getTimeout().toNanos(),TimeUnit.NANOSECONDS);
        worker.execute(request);
      } catch(RejectedExecutionException e) {request.fail(e);}
    }
    private static void validateHeader(String name,String value) {
      if(name==null || !name.matches("[!#$%&'*+.^_`|~0-9A-Za-z-]+") || value==null || value.indexOf('\r')>=0 || value.indexOf('\n')>=0)
        throw new IllegalArgumentException("Invalid OTLP header");
    }
    public CompletableResultCode shutdown() {
      closed=true;
      Request[] requests;
      synchronized(pending) {requests=pending.toArray(new Request[0]);}
      for(Request request:requests) request.fail(new IOException("OTLP sender shutdown"));
      timer.shutdownNow();
      if(ownsWorker) worker.shutdownNow();
      return CompletableResultCode.ofSuccess();
    }
    private final class Request implements Runnable {
      private final byte[] payload;
      private final Consumer<HttpResponse> response;
      private final Consumer<Throwable> error;
      private final AtomicBoolean done=new AtomicBoolean();
      private final long started=System.nanoTime();
      private volatile ScheduledFuture<?> deadlineTask;
      private volatile HttpURLConnection activeConnection;
      Request(byte[] payload,Consumer<HttpResponse> response,Consumer<Throwable> error) {this.payload=payload;this.response=response;this.error=error;}
      void fail(Throwable e) {
        if(done.compareAndSet(false,true)) {
          finish();
          if(worker instanceof ThreadPoolExecutor) ((ThreadPoolExecutor)worker).remove(this);
          try {error.accept(e);} finally {
            HttpURLConnection connection=activeConnection;
            if(connection!=null) connection.disconnect();
          }
        }
      }
      void finish() {pending.remove(this);ScheduledFuture<?> task=deadlineTask;if(task!=null){task.cancel(false);timer.purge();}}
      int remaining() throws SocketTimeoutException {
        long left=config.getTimeout().toNanos()-(System.nanoTime()-started);
        if(done.get() || left<=0) throw new SocketTimeoutException("OTLP request deadline exceeded");
        return (int)Math.max(1,Math.min(Integer.MAX_VALUE,TimeUnit.NANOSECONDS.toMillis(left)));
      }
      public void run() {
        io.opentelemetry.api.impl.InstrumentationUtil.suppressInstrumentation(new Runnable() {
          public void run() { runSuppressed(); }
        });
      }
      private void runSuppressed() {
        try {
          RetryPolicy policy=config.getRetryPolicy();
          int attempts=policy==null?1:policy.getMaxAttempts();
          long backoff=policy==null?0:policy.getInitialBackoff().toNanos();
          for(int attempt=0;attempt<attempts;attempt++) {
            remaining();
            HttpURLConnection connection=null;
            long delay=backoff;
            try {
              URL url=config.getEndpoint().toURL();
              Proxy proxy=Proxy.NO_PROXY;
              if(config.getProxyOptions()!=null) {
                List<Proxy> proxies=config.getProxyOptions().getProxySelector().select(config.getEndpoint());
                if(!proxies.isEmpty()) proxy=proxies.get(0);
              }
              connection=(HttpURLConnection)url.openConnection(proxy);
              activeConnection=connection;
              remaining();
              if(connection instanceof HttpsURLConnection && config.getSslContext()!=null)
                ((HttpsURLConnection)connection).setSSLSocketFactory(config.getSslContext().getSocketFactory());
              connection.setConnectTimeout((int)Math.max(1,Math.min(remaining(),config.getConnectTimeout().toMillis())));
              connection.setReadTimeout(remaining());connection.setInstanceFollowRedirects(false);
              connection.setRequestMethod("POST");connection.setDoOutput(true);
              connection.setRequestProperty("Content-Type",config.getContentType());
              if(config.getCompressor()!=null)connection.setRequestProperty("Content-Encoding",config.getCompressor().getEncoding());
              Map<String,List<String>> headers=config.getHeadersSupplier().get();
              if(headers!=null)for(Map.Entry<String,List<String>> h:headers.entrySet())for(String value:h.getValue()){validateHeader(h.getKey(),value);connection.addRequestProperty(h.getKey(),value);}
              connection.setFixedLengthStreamingMode(payload.length);
              OutputStream output=connection.getOutputStream();try {remaining();output.write(payload);}finally {output.close();}
              connection.setReadTimeout(remaining());
              final int code=connection.getResponseCode();
              final String message=connection.getResponseMessage();
              InputStream input=code>=400?connection.getErrorStream():connection.getInputStream();
              ByteArrayOutputStream body=new ByteArrayOutputStream();
              if(input!=null)try {byte[] buffer=new byte[4096];int count;while(true) {connection.setReadTimeout(remaining());count=input.read(buffer);if(count<0)break;body.write(buffer,0,count);if(body.size()>config.getMaxResponseBodySize())throw new IOException("OTLP response exceeds configured limit");}}finally {input.close();}
              final byte[] result=body.toByteArray();
              if(!RetryUtil.retryableHttpResponseCodes().contains(code) || attempt+1==attempts) {
                if(done.compareAndSet(false,true)) {finish();response.accept(new HttpResponse() {public int getStatusCode(){return code;} public String getStatusMessage(){return message;}public byte[] getResponseBody(){return result;}});}
                return;
              }
              delay=RetryUtil.retryAfterNanos(connection.getHeaderField("Retry-After")).orElse(delay);
            } catch(IOException e) {
              boolean retryable = policy != null && policy.getRetryExceptionPredicate() != null
                  ? policy.getRetryExceptionPredicate().test(e) : isRetryableException(e);
              if(attempt+1==attempts || !retryable) throw e;
            } finally {if(connection!=null)connection.disconnect();activeConnection=null;}
            long available=TimeUnit.MILLISECONDS.toNanos(remaining());
            TimeUnit.NANOSECONDS.sleep(Math.min(delay,available));
            if(policy!=null)backoff=Math.min(policy.getMaxBackoff().toNanos(),(long)(backoff*policy.getBackoffMultiplier()));
          }
        } catch(Exception e) {if(e instanceof InterruptedException)Thread.currentThread().interrupt();fail(e);}

      }
    }
  }
}
