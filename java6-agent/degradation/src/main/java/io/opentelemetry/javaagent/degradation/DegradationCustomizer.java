/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation;

import com.google.auto.service.AutoService;
import io.opentelemetry.sdk.autoconfigure.spi.AutoConfigurationCustomizer;
import io.opentelemetry.sdk.autoconfigure.spi.AutoConfigurationCustomizerProvider;
import io.opentelemetry.sdk.autoconfigure.spi.ConfigProperties;

@AutoService(AutoConfigurationCustomizerProvider.class)
public final class DegradationCustomizer implements AutoConfigurationCustomizerProvider {
  @Override
  public int order() {
    return 0;
  }

  static final DegradationState STATE = new DegradationState();

  @Override
  public void customize(AutoConfigurationCustomizer customizer) {
    customizer.addSpanExporterCustomizer(
        (exporter, config) -> enabled(config) ? STATE.wrap(exporter) : exporter);
    customizer.addMetricExporterCustomizer(
        (exporter, config) -> enabled(config) ? STATE.wrap(exporter) : exporter);
    customizer.addLogRecordExporterCustomizer(
        (exporter, config) -> enabled(config) ? STATE.wrap(exporter) : exporter);
  }

  static boolean enabled(ConfigProperties config) {
    return EdotSettings.getEndpoint(config) != null;
  }
}
