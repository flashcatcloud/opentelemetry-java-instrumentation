/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
import java.io.File;
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;

/** Runs the unchanged Redis fixture in disposable application classloaders. */
public final class ClassLoaderUnloadProbe {
  private static WeakReference<ClassLoader> runApplication(String[] paths) throws Exception {
    URL[] urls = new URL[paths.length];
    for (int i = 0; i < paths.length; i++) urls[i] = new File(paths[i]).toURI().toURL();
    URLClassLoader loader = new URLClassLoader(urls, ClassLoader.getSystemClassLoader().getParent());
    Thread thread = Thread.currentThread();
    ClassLoader previous = thread.getContextClassLoader();
    try {
      thread.setContextClassLoader(loader);
      Class<?> probe = Class.forName("RedisClientProbe", true, loader);
      if (probe.getClassLoader() != loader) throw new AssertionError("Fixture escaped child loader");
      probe.getMethod("main", String[].class).invoke(null, (Object) new String[0]);
    } finally {
      thread.setContextClassLoader(previous);
      // URLClassLoader.close was added in Java 7; the Java 6 run has no such API.
      try { URLClassLoader.class.getMethod("close").invoke(loader); }
      catch (NoSuchMethodException expectedOnJava6) { }
    }
    return new WeakReference<ClassLoader>(loader);
  }

  public static void main(String[] paths) throws Exception {
    for (int cycle = 0; cycle < 3; cycle++) {
      WeakReference<ClassLoader> reference = runApplication(paths);
      for (int attempt = 0; attempt < 100 && reference.get() != null; attempt++) {
        System.gc();
        System.runFinalization();
        Thread.sleep(100);
      }
      if (reference.get() != null) throw new AssertionError("Application classloader retained, cycle=" + cycle);
    }
    System.out.println("CLASSLOADER_UNLOAD_OK cycles=3");
  }
}
