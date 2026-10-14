/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package io.opentelemetry.javaagent.tooling;

import io.opentelemetry.javaagent.bootstrap.DubboBridge;
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.instrumentation.alibabadubbo.v2_5.DubboRequest;
import com.alibaba.dubbo.rpc.Invoker;
import com.alibaba.dubbo.rpc.Result;
import com.alibaba.dubbo.rpc.RpcContext;
import com.alibaba.dubbo.rpc.RpcInvocation;
import com.alibaba.dubbo.rpc.support.RpcUtils;
import com.alibaba.dubbo.remoting.exchange.Response;
import com.alibaba.dubbo.remoting.exchange.support.DefaultFuture;
import io.opentelemetry.instrumentation.api.instrumenter.*;


import io.opentelemetry.context.*;
import java.util.*;

/** Injected legacy lifecycle adapter; request and telemetry assembly are generated upstream code. */
public final class DubboTelemetry {
  public static final DubboTelemetry INSTANCE = new DubboTelemetry(io.opentelemetry.api.GlobalOpenTelemetry.get());
  private final Instrumenter<DubboRequest, Result> clientInstrumenter;
  private final Instrumenter<DubboRequest, Result> serverInstrumenter;
  private final ThreadLocal<Call> pending = new ThreadLocal<Call>();
  static final class Async {
    final Context context;
    final Context callbackContext;
    DubboRequest request;
    final Instrumenter<DubboRequest, Result> instrumenter;
    final java.util.concurrent.atomic.AtomicBoolean ended = new java.util.concurrent.atomic.AtomicBoolean();
    Async(Context parent, Context context, DubboRequest request, Instrumenter<DubboRequest, Result> instrumenter) {
      this.context = context; this.request = request; this.instrumenter = instrumenter;
      // Carry the completed span as callback parent, without its in-flight RPC suppression keys.
      this.callbackContext = parent.with(io.opentelemetry.api.trace.Span.fromContext(context));
    }
    void finish(Throwable error) {
      if (ended.compareAndSet(false, true)) {
        try { instrumenter.end(context, request, null, error); }
        finally { request = null; }
      }
    }
  }
  private final Set<String> headers;
  DubboTelemetry(OpenTelemetry telemetry) {
    headers = new HashSet<String>(telemetry.getPropagators().getTextMapPropagator().fields());
    headers.addAll(Arrays.asList("traceparent", "tracestate", "baggage"));
    io.opentelemetry.instrumentation.alibabadubbo.v2_5.DubboTelemetry official =
        io.opentelemetry.instrumentation.alibabadubbo.v2_5.DubboTelemetry.create(telemetry);
    clientInstrumenter = official.clientInstrumenter();
    serverInstrumenter = official.serverInstrumenter();
  }

  static final class Call {
    final Context context;
    DubboRequest request;
    final Instrumenter<DubboRequest, Result> instrumenter;
    final Scope scope;
    final Async async;
    final Call outer;
    boolean attached;
    final Map<String,String> attachments;
    final Map<String,String> previous;
    Call(Instrumenter<DubboRequest, Result> instrumenter, DubboRequest request, Context parent, Context context, Map<String,String> attachments,
        Map<String,String> previous, boolean asynchronous, Call outer) {
      this.async = asynchronous ? new Async(parent, context, request, instrumenter) : null;
      this.outer = outer;
      this.context = context; this.request = request; this.instrumenter = instrumenter;
      this.attachments = attachments; this.previous = previous;
      this.scope = context.makeCurrent();
    }
    void end(Object result, Throwable error) throws Exception {
      scope.close();
      try {
        if (error == null && result != null) {
          error = ((Result) result).getException();
        }
      } finally {
        try { restore(attachments, previous); }
        finally { instrumenter.end(context, request, (Result) result, error); }
      }
    }
  }
  private static void restore(Map<String,String> attachments, Map<String,String> previous) {
    if (previous == null) return;
    for (String key : previous.keySet()) {
      if (previous.get(key) != null) attachments.put(key, previous.get(key));
      else attachments.remove(key);
    }
  }
  @SuppressWarnings("unchecked")
  public Object enter(boolean server, Object invoker, Object invocation) throws Exception {
    if (!(invoker instanceof Invoker) || !(invocation instanceof RpcInvocation)) return null;
    Invoker<?> typedInvoker = (Invoker<?>) invoker;
    RpcInvocation typedInvocation = (RpcInvocation) invocation;
    com.alibaba.dubbo.common.URL url = typedInvoker.getUrl();
    if (!"dubbo".equals(url.getProtocol())) return null;
    boolean asynchronous = !server && RpcUtils.isAsync(url, typedInvocation);
    if (!server && RpcUtils.isOneway(url, typedInvocation)) return null;
    Map<String, String> attachments = typedInvocation.getAttachments();
    DubboRequest request = DubboRequest.legacy(typedInvoker, typedInvocation, RpcContext.getContext(), server);
    Instrumenter<DubboRequest, Result> instrumenter = server ? serverInstrumenter : clientInstrumenter;
    Context parent = Context.current();
    if (!instrumenter.shouldStart(parent, request)) return null;
    Map<String,String> previous = server ? null : new HashMap<String,String>();
    if (!server) for (String key : headers) {
      previous.put(key, attachments.get(key));
    }
    Context context = null;
    try {
      if (!server) for (String key : headers) attachments.remove(key);
      context = instrumenter.start(parent, request);
      Call call = new Call(instrumenter, request, parent, context, attachments, previous, asynchronous, pending.get());
      pending.set(call);
      return call;
    } catch (Exception e) {
      try { restore(attachments, previous); }
      finally { if (context != null) instrumenter.end(context, request, null, e); }
      throw e;
    }
  }
  public void exit(Object state, Object result, Throwable error) throws Exception {
    if (state == null) return;
    Call call = (Call) state;
    if (call.outer == null) pending.remove(); else pending.set(call.outer);
    if (call.async == null) { call.end(result, error); return; }
    call.scope.close();
    try { restore(call.attachments, call.previous); }
    finally {
      if (error != null || !call.attached) call.async.finish(error);
    }
  }
  public boolean isAsyncRequest() {
    Call call = pending.get();
    return call != null && call.async != null;
  }
  public void futureCreated(Object future, DubboBridge.FutureAccess access) throws Exception {
    Call call = pending.get();
    if (call == null || call.async == null) return;
    access.set(future, call.async);
    call.attached = true;
    // DefaultFuture publishes itself before its constructor returns. Re-read the
    // volatile response after mapping, so a very fast reply cannot lose completion.
    Object response = response(future);
    if (response != null) completed(future, response, false, access);
  }
  public void completed(Object future, Object response, boolean cancelled, DubboBridge.FutureAccess access) throws Exception {
    Async state = (Async) access.get(future);
    if (state == null || state.ended.get()) return;
    Throwable error = null;
    if (cancelled) error = new java.util.concurrent.CancellationException("Dubbo request cancelled");
    else {
      if (!(response instanceof Response)) return;
      Response reply = (Response) response;
      int status = reply.getStatus();
      if (status == Response.OK) {
        Object result = reply.getResult();
        if (result instanceof Result) error = ((Result) result).getException();
      } else {
        String message = reply.getErrorMessage();
        error = status == Response.CLIENT_TIMEOUT || status == Response.SERVER_TIMEOUT
            ? new java.util.concurrent.TimeoutException(message) : new java.io.IOException(message);
      }
    }
    state.finish(error);
  }
  // A private completion slot is the only unavailable public API on legacy DefaultFuture.
  // Cached in the injected application's loader, never the Agent or bootstrap loader.
  private static final java.lang.reflect.Field RESPONSE = responseField();
  private static java.lang.reflect.Field responseField() {
    try {
      java.lang.reflect.Field field = DefaultFuture.class.getDeclaredField("response");
      field.setAccessible(true);
      return field;
    } catch (Exception unavailable) { return null; }
  }
  private static Object response(Object future) throws Exception {
    return RESPONSE == null ? null : RESPONSE.get(future);
  }
  public Object callbackEnter(Object future, DubboBridge.FutureAccess access) throws Exception {
    Async state = (Async) access.get(future);
    if (state == null) return null;
    // If a reply raced constructor publication, finish before calling business code,
    // rather than waiting for doReceived's exit after that callback returns.
    if (!state.ended.get()) {
      Object result = response(future);
      if (result != null) completed(future, result, false, access);
    }
    return state.callbackContext.makeCurrent();
  }
  public void callbackExit(Object scope) { if (scope != null) ((Scope) scope).close(); }

}
