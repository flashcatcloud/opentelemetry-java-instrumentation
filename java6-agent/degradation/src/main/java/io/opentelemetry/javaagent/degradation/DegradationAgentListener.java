/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation;

import com.google.auto.service.AutoService;
import io.opentelemetry.javaagent.extension.AgentListener;
import io.opentelemetry.sdk.autoconfigure.AutoConfiguredOpenTelemetrySdk;
import io.opentelemetry.sdk.autoconfigure.internal.AutoConfigureUtil;
import io.opentelemetry.sdk.autoconfigure.spi.ConfigProperties;
import java.io.IOException;
import java.util.logging.Logger;

@AutoService(AgentListener.class)
public final class DegradationAgentListener implements AgentListener {
  @Override
  public int order() {
    return 0;
  }

  private static final Logger logger = Logger.getLogger(DegradationAgentListener.class.getName());

  @Override
  public void afterAgent(AutoConfiguredOpenTelemetrySdk autoConfiguredSdk) {
    ConfigProperties config = AutoConfigureUtil.getConfig(autoConfiguredSdk);
    if (config == null || !DegradationCustomizer.enabled(config)) {
      return;
    }
    try {
      String endpoint = EdotSettings.getEndpoint(config);
      String service = EdotSettings.getServiceName(config);
      String environment = EdotSettings.getServiceEnvironment(config);
      DegradationController controller =
          new DegradationController(
              DegradationCustomizer.STATE,
              autoConfiguredSdk.getOpenTelemetrySdk().getSdkTracerProvider());
      OpampConnection connection =
          new OpampConnection(
              endpoint,
              EdotSettings.headers(config),
              config,
              service == null ? "unknown_service:java" : service,
              environment == null ? "" : environment,
              controller,
              DegradationCustomizer.STATE);
      Thread hook =
          new Thread(
              () -> {
                try {
                  connection.close();
                } catch (IOException e) {
                  logger.warning("Could not close OpAMP client");
                }
              },
              "otel-opamp-shutdown");
      try {
        Runtime.getRuntime().addShutdownHook(hook);
      } catch (IllegalStateException | SecurityException e) {
        connection.close();
        throw e;
      }
      logger.info("OpAMP runtime degradation enabled");
    } catch (IOException | RuntimeException e) {
      logger.warning("OpAMP runtime degradation could not start");
    }
  }
}
