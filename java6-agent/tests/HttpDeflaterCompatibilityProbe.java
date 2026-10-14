/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.util.Arrays;
import java.util.zip.Deflater;
import java.util.zip.Inflater;

/** Exercises the optional private Okio SYNC_FLUSH API; no application tracing API calls. */
public class HttpDeflaterCompatibilityProbe {
  public static void main(String[] args) throws Exception {
    ClassLoader loader = (ClassLoader) Class.forName("io.opentelemetry.javaagent.bootstrap.AgentInitializer")
        .getMethod("getExtensionsClassLoader").invoke(null);
    String prefix = "io.opentelemetry.javaagent.transport.okio.";
    Class<?> bufferType = Class.forName(prefix + "Buffer", true, loader);
    Class<?> sinkType = Class.forName(prefix + "DeflaterSink", true, loader);
    Class<?> sinkApi = Class.forName(prefix + "Sink", true, loader);
    Deflater deflater = new Deflater();
    Inflater inflater = new Inflater();
    Object input = bufferType.newInstance();
    Object output = bufferType.newInstance();
    Object sink = sinkType.getConstructor(sinkApi, Deflater.class).newInstance(output, deflater);
    byte[] payload = "bounded-private-transport".getBytes("UTF-8");
    bufferType.getMethod("write", byte[].class).invoke(input, new Object[]{payload});
    sinkType.getMethod("write", bufferType, long.class).invoke(sink, input, Long.valueOf(payload.length));
    boolean java6 = "1.6".equals(System.getProperty("java.specification.version"));
    try {
      try {
        sinkType.getMethod("flush").invoke(sink);
        if (java6) throw new AssertionError("Java 6 falsely accepted SYNC_FLUSH");
        byte[] compressed = (byte[]) bufferType.getMethod("readByteArray").invoke(output);
        inflater.setInput(compressed);
        byte[] actual = new byte[payload.length];
        if (inflater.inflate(actual) != payload.length || !Arrays.equals(payload, actual)) {
          throw new AssertionError("SYNC_FLUSH corrupted output");
        }
      } catch (InvocationTargetException error) {
        if (!java6 || !(error.getCause() instanceof IOException)
            || error.getCause().getMessage().indexOf("unavailable") < 0) throw error;
      }
      System.out.println("HTTP_DEFLATER_COMPATIBILITY_OK java6=" + java6);
    } finally {
      deflater.end();
      inflater.end();
    }
  }
}
