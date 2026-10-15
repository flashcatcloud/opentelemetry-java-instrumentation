/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation;

import io.opentelemetry.javaagent.shaded.io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.javaagent.shaded.io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.javaagent.shaded.io.opentelemetry.api.trace.Tracer;
import java.net.HttpURLConnection;
import java.net.URL;

/** A separate business JVM used by the n9e-plus interoperability test. */
public final class InteropApplication {
  public static void main(String[] args) throws Exception {
    System.out.println(
        "JVM="
            + System.getProperty("java.version")
            + " PID="
            + java.lang.management.ManagementFactory.getRuntimeMXBean().getName());
    Tracer tracer = GlobalOpenTelemetry.getTracer("interop");
    LongCounter counter =
        GlobalOpenTelemetry.getMeter("interop").counterBuilder("interop.work").build();
    int iteration = 0;
    while (true) {
      io.opentelemetry.javaagent.shaded.io.opentelemetry.api.trace.Span span =
          tracer.spanBuilder("work").startSpan();
      boolean recording = span.isRecording();
      span.end();
      io.opentelemetry.javaagent.shaded.io.opentelemetry.api.trace.Span fresh =
          GlobalOpenTelemetry.getTracer("fresh-" + iteration++).spanBuilder("fresh").startSpan();
      boolean newRecording = fresh.isRecording();
      fresh.end();
      HttpURLConnection connection =
          (HttpURLConnection)
              new URL(args[0] + "?recording=" + recording + "&fresh=" + newRecording)
                  .openConnection();
      try {
        connection.getInputStream().close();
      } finally {
        connection.disconnect();
      }
      counter.add(1);
      GlobalOpenTelemetry.get()
          .getLogsBridge()
          .get("interop")
          .logRecordBuilder()
          .setBody("work")
          .emit();
      Thread.sleep(100);
    }
  }

  private InteropApplication() {}
}
