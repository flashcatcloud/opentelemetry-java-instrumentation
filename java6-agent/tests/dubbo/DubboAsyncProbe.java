package example;

import com.alibaba.dubbo.common.URL;
import com.alibaba.dubbo.common.extension.ExtensionLoader;
import com.alibaba.dubbo.remoting.exchange.ResponseCallback;
import com.alibaba.dubbo.rpc.*;
import com.alibaba.dubbo.rpc.protocol.dubbo.FutureAdapter;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;

/** Ordinary Dubbo API fixture; the same bytecode is run with and without the agent. */
public class DubboAsyncProbe {
  static Invoker<QueryService> invoker;
  static Object call(String method, boolean fail, boolean async) throws Exception {
    RpcInvocation invocation = new RpcInvocation(method,
        "query".equals(method) ? new Class<?>[]{boolean.class} : new Class<?>[0],
        "query".equals(method) ? new Object[]{fail} : new Object[0]);
    invocation.setAttachment("async", String.valueOf(async));
    Result result = invoker.invoke(invocation);
    if (async) return RpcContext.getContext().getFuture();
    if (result.hasException()) throw new IllegalStateException(result.getException());
    if (!Integer.valueOf(42).equals(result.getValue())) throw new AssertionError(result);
    return result.getValue();
  }
  public static void main(String[] args) throws Exception {
    System.out.println("RUNTIME " + System.getProperty("java.runtime.version"));
    final String mode = args[0];
    Protocol protocol = ExtensionLoader.getExtensionLoader(Protocol.class).getExtension("dubbo");
    invoker = protocol.refer(QueryService.class, URL.valueOf("dubbo://java6-dubbo-b:20880/example.QueryService?client=netty&timeout="
        + "10000&slow.timeout=" + ("timeout".equals(mode) ? "200" : "10000") + "&serialization=hessian2"));
    if ("fast".equals(mode)) {
      final CountDownLatch all = new CountDownLatch(24);
      final Semaphore slots = new Semaphore(2);
      final AtomicReference<Throwable> failed = new AtomicReference<Throwable>();
      for (int i = 0; i < 24; i++) {
        slots.acquire();
        FutureAdapter<?> f = (FutureAdapter<?>) call("query", false, true);
        f.getFuture().setCallback(new ResponseCallback() {
          public void done(Object response) {
            try {
              // Do not block Dubbo's response threads waiting for another response
              // handled by the same pool. The uninstrumented library can deadlock.
              FutureAdapter<?> nested = (FutureAdapter<?>) call("query", false, true);
              nested.getFuture().setCallback(new ResponseCallback() {
                public void done(Object response) {
                  try {
                    Result result = (Result) response;
                    if (result.hasException() || !Integer.valueOf(42).equals(result.getValue()))
                      failed.set(new AssertionError("bad nested result"));
                  } finally { all.countDown(); slots.release(); }
                }
                public void caught(Throwable error) { failed.set(error); all.countDown(); slots.release(); }
              });
            } catch (Throwable e) { failed.set(e); all.countDown(); slots.release(); }
          }
          public void caught(Throwable error) { failed.set(error); all.countDown(); slots.release(); }
        });
      }
      call("query", false, false);
      if (!all.await(30, TimeUnit.SECONDS) || failed.get() != null) throw new AssertionError(failed.get());
      call("query", false, false);
      System.out.println("DUBBO_ASYNC_OK fast");
      Thread.sleep(1500);
      protocol.destroy();
      return;
    }
    final CountDownLatch callback = new CountDownLatch(1);
    final AtomicReference<Throwable> callbackError = new AtomicReference<Throwable>();
    long start = System.currentTimeMillis();
    FutureAdapter<?> future = (FutureAdapter<?>) call("error".equals(mode) ? "query" : "slow", true, true);
    long returned = System.currentTimeMillis();
    System.out.println("RETURNED " + returned);
    // This call on the same thread must be a new root, even while the first is pending.
    call("query", false, false);
    if ("cancel".equals(mode)) {
      if (future.cancel(true)) throw new AssertionError("agent changed FutureAdapter.cancel contract");
      future.getFuture().getClass().getMethod("cancel").invoke(future.getFuture());
      Thread.sleep(1600);
    }
    if ("late".equals(mode) || "throw".equals(mode)) future.get();
    if ("throw".equals(mode) || "callback".equals(mode) || "late".equals(mode) || "error".equals(mode) || "timeout".equals(mode)) {
      future.getFuture().setCallback(new ResponseCallback() {
        public void done(Object response) { run(); }
        public void caught(Throwable error) { run(); }
        private void run() {
          try { call("query", false, false); }
          catch (Throwable e) { callbackError.set(e); }
          finally { callback.countDown(); }
          if ("throw".equals(mode)) throw new IllegalStateException("expected-business-callback-error");
        }
      });
      if (!callback.await(15, TimeUnit.SECONDS)) throw new AssertionError("missing business callback");
      if (callbackError.get() != null) throw new AssertionError(callbackError.get());
    } else if ("get".equals(mode)) {
      if (!Integer.valueOf(42).equals(future.get())) throw new AssertionError("bad result");
    } else if ("ignored".equals(mode)) {
      // Completion must be observed even when the application never calls get/setCallback.
      Thread.sleep(2000);
      if (!future.isDone()) throw new AssertionError("pending future");
    }
    long finished = System.currentTimeMillis();
    call("query", false, false);
    if (!"error".equals(mode) && !"timeout".equals(mode) && finished-start < 1400)
      throw new AssertionError("slow service did not run");
    System.out.println("FINISHED " + finished + " DUBBO_ASYNC_OK " + mode);
    Thread.sleep(1500); // allow timeout provider to return and exporter to drain
    protocol.destroy();
  }
}
