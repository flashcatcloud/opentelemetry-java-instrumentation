/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
/** Deliberately has no OTel references, annotations, or tracing calls. */
public final class PlainApplication {
  public static void main(String[] args) throws Exception {
    // Reuse one executor thread to expose leaked scopes between independent calls.
    java.util.concurrent.ExecutorService worker = java.util.concurrent.Executors.newSingleThreadExecutor();
    try {
      for (int i = 0; i < 3; i++) {
        worker.submit(new Runnable() { public void run() { parent(); after(); } }).get();
      }
    } finally { worker.shutdown(); }
    for (String hidden : new String[] {"io.opentelemetry.sdk.trace.SdkTracerProvider", "net.bytebuddy.ByteBuddy"}) {
      try { Class.forName(hidden); throw new AssertionError("agent dependency leaked: " + hidden); }
      catch (ClassNotFoundException expected) {}
    }
    System.out.println("APPLICATION_OK");
  }
  static void parent() { child(); try { fail(); } catch (IllegalStateException expected) {} child(); }
  static int child() { return 42; }
  static void fail() { throw new IllegalStateException("expected-error"); }
  static void after() {}
}
