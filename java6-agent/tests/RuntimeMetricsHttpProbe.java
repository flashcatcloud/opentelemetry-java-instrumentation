/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
/** Test lifecycle only; leave the HTTP fixture and its timeouts unchanged. */
public final class RuntimeMetricsHttpProbe {
  public static void main(String[] args) throws Exception {
    HttpClientProbe.main(args);
    // Allow periodic JMX collection before SDK and observer shutdown hooks race.
    Thread.sleep(10000);
  }
}
