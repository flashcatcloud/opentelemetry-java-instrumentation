/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package io.opentelemetry.javaagent.degradation;

import io.opentelemetry.sdk.autoconfigure.spi.internal.DefaultConfigProperties;
import java.util.HashMap;
import java.util.Map;

/** EDOT CentralConfig connection/configuration contract regression, including Java 6 adapters. */
public final class ConfigCompatibilityTest {
  private static void check(boolean condition, String message) {
    if (!condition) throw new AssertionError(message);
  }

  private static DegradationConfig parse(String value, DegradationConfig previous)
      throws Exception {
    return DegradationConfig.parse(value.getBytes("UTF-8"), previous);
  }

  public static void main(String[] args) throws Exception {
    Map<String, String> settings = new HashMap<String, String>();
    check(
        EdotSettings.getEndpoint(DefaultConfigProperties.createFromMap(settings)) == null,
        "default off");
    settings.put("elastic.otel.opamp.endpoint", "http://ignored:123");
    check(
        EdotSettings.getEndpoint(DefaultConfigProperties.createFromMap(settings)) == null,
        "Elastic property must not enable this agent");
    settings.put("otel.javaagent.opamp.endpoint", "http://localhost:19000/prefix");
    check(
        "http://localhost:19000/prefix/v1/opamp"
            .equals(EdotSettings.getEndpoint(DefaultConfigProperties.createFromMap(settings))),
        "agent endpoint and prefix");
    settings.put("otel.javaagent.opamp.endpoint", "http://localhost:19000/v1/opamp");
    check(
        "http://localhost:19000/v1/opamp"
            .equals(EdotSettings.getEndpoint(DefaultConfigProperties.createFromMap(settings))),
        "suffix not duplicated");
    settings.put(
        "otel.resource.attributes", "deployment.environment=legacy,service.name=from-resource");
    check(
        "legacy"
            .equals(
                EdotSettings.getServiceEnvironment(
                    DefaultConfigProperties.createFromMap(settings))),
        "legacy environment");
    check(
        "from-resource"
            .equals(EdotSettings.getServiceName(DefaultConfigProperties.createFromMap(settings))),
        "resource service");
    settings.put("otel.service.name", "from-property");
    check(
        "from-property"
            .equals(EdotSettings.getServiceName(DefaultConfigProperties.createFromMap(settings))),
        "service precedence");
    settings.put(
        "otel.resource.attributes",
        "deployment.environment=legacy,deployment.environment.name=modern");
    check(
        "modern"
            .equals(
                EdotSettings.getServiceEnvironment(
                    DefaultConfigProperties.createFromMap(settings))),
        "modern environment precedence");
    settings.remove("otel.javaagent.opamp.endpoint");
    check(
        EdotSettings.getEndpoint(DefaultConfigProperties.createFromMap(settings)) == null,
        "no fallback to Elastic endpoint");
    settings.put("elastic.otel.opamp.headers", "Authorization=ignored");
    check(
        EdotSettings.headers(DefaultConfigProperties.createFromMap(settings)).isEmpty(),
        "no Elastic headers fallback");
    for (String key : new String[] {"certificate", "client.key", "client.certificate"}) {
      settings.put("elastic.otel.opamp." + key, "ignored");
      check(
          EdotSettings.setting(DefaultConfigProperties.createFromMap(settings), key) == null,
          "no Elastic TLS fallback");
      settings.put("otel.javaagent.opamp." + key, "configured");
      check(
          "configured"
              .equals(EdotSettings.setting(DefaultConfigProperties.createFromMap(settings), key)),
          "agent TLS setting");
    }

    DegradationConfig stopped =
        parse(
            "{\"deactivate_all_instrumentations\":\"TRUE\",\"send_traces\":\"false\",\"send_metrics\":false,\"send_logs\":false,\"opamp_polling_interval\":\"5s\"}",
            DegradationConfig.ENABLED);
    check(
        stopped.stopped && !stopped.sendTraces && !stopped.sendMetrics && !stopped.sendLogs,
        "stop config");
    DegradationConfig reset = parse("{}", stopped);
    check(
        !reset.stopped
            && reset.sendTraces
            && reset.sendMetrics
            && reset.sendLogs
            && reset.interval.getSeconds() == 30,
        "omitted keys restore EDOT defaults");
    DegradationConfig partial =
        parse("{\"send_traces\":\"garbage\",\"unknown\":{\"future\":true}}", stopped);
    check(
        !partial.sendTraces && partial.sendMetrics && !partial.stopped,
        "invalid value retained; unknown ignored; omitted reset");
    check(
        parse("{\"opamp_polling_interval\":\"1m\"}", stopped).interval.getSeconds() == 60,
        "EDOT duration units");
    check(
        parse("{\"opamp_polling_interval\":\"0s\"}", stopped).interval.getSeconds() == 5,
        "avoid zero-delay busy loop");
    for (String invalid : new String[] {"{", "{\"send_logs\":false,\"send_logs\":true}", "{} {}"}) {
      boolean rejected = false;
      try {
        parse(invalid, stopped);
      } catch (java.io.IOException expected) {
        rejected = true;
      } catch (RuntimeException expected) {
        rejected = true;
      }
      check(rejected, "invalid JSON rejected");
    }
    System.out.println(
        "PASS: agent namespace, service/environment, config defaults,"
            + " partial/reset/invalid/unknown configuration");
  }
}
