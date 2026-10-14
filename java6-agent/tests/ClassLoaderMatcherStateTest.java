import io.opentelemetry.javaagent.bootstrap.internal.InClassLoaderMatcher;
import java.util.concurrent.atomic.AtomicReference;

/** Verifies the compatibility overlay preserves nested and per-thread matcher state. */
public final class ClassLoaderMatcherStateTest {
  private static void check(boolean condition) {
    if (!condition) throw new AssertionError("matcher state invariant");
  }
  public static void main(String[] args) throws Exception {
    check(!InClassLoaderMatcher.get());
    boolean outer = InClassLoaderMatcher.getAndSet(true);
    check(!outer);
    boolean inner = InClassLoaderMatcher.getAndSet(true);
    check(inner);
    InClassLoaderMatcher.set(inner);
    check(InClassLoaderMatcher.get());
    final AtomicReference<Throwable> failure = new AtomicReference<Throwable>();
    Thread worker = new Thread(new Runnable() {
      public void run() {
        try {
          check(!InClassLoaderMatcher.get());
          check(!InClassLoaderMatcher.getAndSet(true));
          InClassLoaderMatcher.set(false);
          check(!InClassLoaderMatcher.get());
        } catch (Throwable t) { failure.set(t); }
      }
    });
    worker.start(); worker.join();
    if (failure.get() != null) throw new AssertionError(failure.get());
    check(InClassLoaderMatcher.get());
    InClassLoaderMatcher.set(outer);
    check(!InClassLoaderMatcher.get());
    System.out.println("MATCHER_STATE_OK nested=ok isolated=ok restored=ok java=" + System.getProperty("java.version"));
  }
}
