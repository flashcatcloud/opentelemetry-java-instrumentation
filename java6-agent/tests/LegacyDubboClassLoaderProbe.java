import java.io.File;
import java.lang.ref.WeakReference;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.net.URL;
import java.net.URLClassLoader;

/** Exercises injected legacy helpers and registry metadata in disposable application loaders. */
public final class LegacyDubboClassLoaderProbe {
  private static WeakReference<ClassLoader> exercise(String[] paths) throws Exception {
    URL[] urls = new URL[paths.length];
    for (int i = 0; i < paths.length; i++) urls[i] = new File(paths[i]).toURI().toURL();
    URLClassLoader loader = new URLClassLoader(urls, ClassLoader.getSystemClassLoader().getParent());
    Thread thread = Thread.currentThread();
    ClassLoader previous = thread.getContextClassLoader();
    try {
      thread.setContextClassLoader(loader);
      Class.forName("com.alibaba.dubbo.remoting.exchange.support.DefaultFuture", false, loader);
      Class<?> helper = Class.forName("io.opentelemetry.javaagent.tooling.DubboTelemetry", true, loader);
      if (helper.getClassLoader() != loader) throw new AssertionError("Legacy helper escaped application loader");
      Class<?> invocation = Class.forName("com.alibaba.dubbo.rpc.RpcInvocation", true, loader);
      Class<?> invoker = Class.forName("com.alibaba.dubbo.rpc.Invoker", true, loader);
      Object carrier = invocation.newInstance();
      Object proxy = Proxy.newProxyInstance(loader, new Class<?>[] {invoker}, new InvocationHandler() {
        public Object invoke(Object ignored, Method method, Object[] args) {
          if (method.getName().equals("getInterface")) return String.class;
          return null;
        }
      });
      invocation.getMethod("setInvoker", invoker).invoke(carrier, proxy);
      Class<?> registry = Class.forName("io.opentelemetry.javaagent.shaded.instrumentation.alibabadubbo.v2_5.internal.DubboRegistryUtil", true, loader);
      Object address = registry.getMethod("extractRegistryAddress", invocation).invoke(null, carrier);
      if (address != null) throw new AssertionError("Fabricated registry address");
    } finally {
      thread.setContextClassLoader(previous);
      try { URLClassLoader.class.getMethod("close").invoke(loader); }
      catch (NoSuchMethodException expectedOnJava6) { }
    }
    return new WeakReference<ClassLoader>(loader);
  }
  public static void main(String[] paths) throws Exception {
    for (int cycle = 0; cycle < 3; cycle++) {
      WeakReference<ClassLoader> reference = exercise(paths);
      for (int attempt = 0; attempt < 100 && reference.get() != null; attempt++) {
        System.gc(); System.runFinalization(); Thread.sleep(100);
      }
      if (reference.get() != null) throw new AssertionError("Legacy loader retained: " + cycle);
    }
    System.out.println("LEGACY_HELPER_UNLOAD_OK cycles=3");
  }
}
