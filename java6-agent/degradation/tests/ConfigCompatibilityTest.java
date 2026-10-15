/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package io.opentelemetry.javaagent.degradation;

/** Exercises the strict JSON parser independently of server-generated configurations. */
public final class ConfigCompatibilityTest {
  public static void main(String[] args) throws Exception {
    String body =
        "\"deactivate_all_instrumentations\":true,\"send_traces\":\"false\","
            + "\"send_metrics\":false,\"send_logs\":false";
    DegradationConfig config = DegradationConfig.parse(("{" + body + "}").getBytes("UTF-8"));
    if (!config.stopped || config.sendTraces || config.sendMetrics || config.sendLogs) {
      throw new AssertionError("Boolean parsing");
    }
    String[] invalid = {
      "{}",
      "{" + body + ",\"send_logs\":false}",
      "{" + body + ",\"unknown\":true}",
      "{" + body + "} {}",
      "{" + body + ",\"opamp_polling_interval\":\"0s\"}",
      "{" + body + ",\"opamp_polling_interval\":\"3601s\"}",
      "{" + body + ",\"opamp_polling_interval\":5}",
      "{" + body.replace("true", "null") + "}",
      "{" + body.replace("true", "\"TRUE\"") + "}"
    };
    for (String value : invalid) {
      boolean rejected = false;
      try {
        DegradationConfig.parse(value.getBytes("UTF-8"));
      } catch (java.io.IOException expected) {
        rejected = true;
      } catch (RuntimeException expected) {
        rejected = true;
      }
      if (!rejected) throw new AssertionError("Accepted: " + value);
    }
    System.out.println(
        "PASS: strict configuration parser (valid + " + invalid.length + " invalid cases)");
  }
}
