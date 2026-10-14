import io.opentelemetry.javaagent.bootstrap.CallDepth;
import io.opentelemetry.javaagent.bootstrap.InstrumentedTaskClasses;
import java.util.concurrent.atomic.AtomicReference;
import java8.util.function.Predicate;
import io.opentelemetry.instrumentation.api.annotation.support.async.AsyncOperationEndStrategies;
import io.opentelemetry.instrumentation.api.annotation.support.async.AsyncOperationEndStrategy;
import io.opentelemetry.javaagent.tooling.asyncannotationsupport.WeakRefAsyncOperationEndStrategies;
import io.opentelemetry.context.Context;
import io.opentelemetry.instrumentation.api.instrumenter.Instrumenter;

/** Exercises class-keyed caches after the Java 6 compatibility overlay. */
public final class ToolingClassCacheTest {
  static void check(boolean ok) { if (!ok) throw new AssertionError("class cache invariant"); }
  static void verifyTypeNames() throws Exception {
    Class<?> supplier = Class.forName("io.opentelemetry.javaagent.tooling.field.RuntimeFieldBasedImplementationSupplier");
    java.lang.reflect.Method name = supplier.getDeclaredMethod("getTypeName", Class.class);
    name.setAccessible(true);
    Class<?>[] types = {String.class, int.class, void.class, String[][].class, int[][][].class, java.util.Map.Entry.class};
    String[] expected = {"java.lang.String", "int", "void", "java.lang.String[][]", "int[][][]", "java.util.Map$Entry"};
    for (int i = 0; i < types.length; i++) check(expected[i].equals(name.invoke(null, types[i])));
  }
  static void verifyExtensions() throws Exception {
    java.lang.reflect.Method extract = io.opentelemetry.javaagent.tooling.ExtensionClassLoader.class
        .getDeclaredMethod("includeEmbeddedExtensionsIfFound", java.util.List.class, java.io.File.class);
    extract.setAccessible(true);
    for (boolean invalid : new boolean[] {false, true}) {
      java.io.File jar = java.io.File.createTempFile("extension-test", ".jar");
      try {
        java.util.jar.JarOutputStream out = new java.util.jar.JarOutputStream(new java.io.FileOutputStream(jar));
        try {
          out.putNextEntry(new java.util.jar.JarEntry(invalid ? "extensions/../escape.jar" : "extensions/valid.jar"));
          out.write(new byte[] {11, 22, 33}); out.closeEntry();
        } finally { out.close(); }
        java.util.List<java.net.URL> urls = new java.util.ArrayList<java.net.URL>();
        try {
          extract.invoke(null, urls, jar);
          check(!invalid && urls.size() == 1);
          java.io.InputStream in = urls.get(0).openStream();
          try { check(in.read() == 11 && in.read() == 22 && in.read() == 33 && in.read() == -1); }
          finally { in.close(); }
        } catch (java.lang.reflect.InvocationTargetException e) {
          check(invalid && e.getCause() instanceof IllegalStateException);
          check(urls.isEmpty());
        }
      } finally { check(jar.delete()); }
    }
  }
  static void verifyResources() throws Exception {
    final ClassLoader loader = new ClassLoader() {};
    final AtomicReference<Throwable> failure = new AtomicReference<Throwable>();
    final java.util.concurrent.CountDownLatch start = new java.util.concurrent.CountDownLatch(1);
    Thread[] workers = new Thread[8];
    for (int i = 0; i < workers.length; i++) {
      final int index = i;
      workers[i] = new Thread(new Runnable() {
        public void run() {
          try {
            start.await();
            for (int j = 0; j < 16; j++) {
              java.net.URL url = new java.net.URL("file:/resource-" + index + "-" + j);
              for (int repeat = 0; repeat < 2; repeat++) {
                io.opentelemetry.javaagent.bootstrap.HelperResources.register(loader, "test", java.util.Collections.singletonList(url));
              }
            }
          } catch (Throwable t) { failure.set(t); }
        }
      });
      workers[i].start();
    }
    start.countDown();
    for (Thread worker : workers) worker.join();
    if (failure.get() != null) throw new AssertionError(failure.get());
    java.util.List<java.net.URL> urls = io.opentelemetry.javaagent.bootstrap.HelperResources.loadAll(loader, "test");
    check(urls.size() == 128);
    try { urls.clear(); throw new AssertionError("mutable resource list"); }
    catch (UnsupportedOperationException expected) { }
    java.net.URL shared = new java.net.URL("file:/global-resource");
    io.opentelemetry.javaagent.bootstrap.HelperResources.registerForAllClassLoaders("global", java.util.Collections.singletonList(shared));
    check(shared.equals(io.opentelemetry.javaagent.bootstrap.HelperResources.loadOne(loader, "global")));
  }
  static void verifyRegistry(AsyncOperationEndStrategies registry) throws Exception {
    AsyncOperationEndStrategy strategy = new AsyncOperationEndStrategy() {
      public boolean supports(Class<?> type) { return type == ToolingClassCacheTest.class; }
      public <Q, R> Object end(Instrumenter<Q, R> instrumenter, Context context,
          Q request, Object value, Class<R> responseType) { throw new UnsupportedOperationException(); }
    };
    registry.registerStrategy(strategy);
    check(registry.resolveStrategy(ToolingClassCacheTest.class) == strategy);
    registry.unregisterStrategy(strategy);
    check(registry.resolveStrategy(ToolingClassCacheTest.class) == null);
    Class<?> completionStage = null;
    try { completionStage = Class.forName("java.util.concurrent.CompletionStage"); }
    catch (ClassNotFoundException expectedOnJava6) { }
    if (completionStage != null) check(registry.resolveStrategy(completionStage) != null);
  }
  public static void main(String[] args) throws Exception {
    boolean foundLoader = false;
    for (io.opentelemetry.javaagent.tooling.AgentExtension extension : java.util.ServiceLoader.load(io.opentelemetry.javaagent.tooling.AgentExtension.class)) {
      if (extension.getClass().getName().equals("io.opentelemetry.javaagent.tooling.instrumentation.InstrumentationLoader")) {
        check("instrumentation-loader".equals(extension.extensionName()));
        foundLoader = true;
      }
    }
    check(foundLoader);
    verifyTypeNames();
    verifyExtensions();
    verifyResources();
    verifyRegistry(AsyncOperationEndStrategies.instance());
    WeakRefAsyncOperationEndStrategies.initialize();
    verifyRegistry(AsyncOperationEndStrategies.instance());
    InstrumentedTaskClasses.setIgnoredTaskClassesPredicate(new Predicate<String>() {
      public boolean test(String name) { return name.equals(String.class.getName()); }
    });
    check(!InstrumentedTaskClasses.canInstrumentTaskClass(String.class));
    check(InstrumentedTaskClasses.canInstrumentTaskClass(ToolingClassCacheTest.class));
    final CallDepth depth = CallDepth.forClass(ToolingClassCacheTest.class);
    check(depth == CallDepth.forClass(ToolingClassCacheTest.class));
    check(depth != CallDepth.forClass(String.class));
    check(depth.getAndIncrement() == 0);
    check(depth.getAndIncrement() == 1);
    final AtomicReference<Throwable> failure = new AtomicReference<Throwable>();
    Thread worker = new Thread(new Runnable() {
      public void run() {
        try {
          CallDepth other = CallDepth.forClass(ToolingClassCacheTest.class);
          check(other != depth);
          check(other.getAndIncrement() == 0);
          check(other.decrementAndGet() == 0);
          check(InstrumentedTaskClasses.canInstrumentTaskClass(ToolingClassCacheTest.class));
        } catch (Throwable t) { failure.set(t); }
      }
    });
    worker.start(); worker.join();
    if (failure.get() != null) throw new AssertionError(failure.get());
    check(depth.decrementAndGet() == 1);
    check(depth.decrementAndGet() == 0);
    System.out.println("TOOLING_CLASS_CACHE_OK depth=ok threads=ok filtering=ok java=" + System.getProperty("java.version"));
  }
}
