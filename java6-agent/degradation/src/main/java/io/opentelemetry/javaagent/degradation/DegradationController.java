/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation;

import static java.util.Objects.requireNonNull;

import io.opentelemetry.sdk.common.internal.ScopeConfigurator;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.internal.SdkTracerProviderUtil;
import io.opentelemetry.sdk.trace.internal.TracerConfig;
import java.lang.reflect.Field;

/** Owned by the single OpAMP response worker; exporters only read the published state. */
final class DegradationController {
  private final DegradationState state;
  private final SdkTracerProvider provider;
  private final ScopeConfigurator<TracerConfig> original;
  private boolean stopped;

  DegradationController(DegradationState state, SdkTracerProvider provider) {
    this.state = state;
    this.provider = provider;
    this.original = originalConfigurator(provider);
  }

  void apply(DegradationConfig config) {
    if (stopped != config.stopped) {
      SdkTracerProviderUtil.setTracerConfigurator(
          provider,
          config.stopped
              ? TracerConfig.configuratorBuilder().setDefault(TracerConfig.disabled()).build()
              : original);
      stopped = config.stopped;
    }
    state.publish(config);
  }

  // The SDK exposes a setter but no getter. Read once, before any remote changes, so resume
  // preserves local scope rules instead of enabling every tracer unconditionally.
  @SuppressWarnings("unchecked")
  private static ScopeConfigurator<TracerConfig> originalConfigurator(SdkTracerProvider provider) {
    try {
      Field field = SdkTracerProvider.class.getDeclaredField("tracerConfigurator");
      field.setAccessible(true);
      return (ScopeConfigurator<TracerConfig>) requireNonNull(field.get(provider));
    } catch (NoSuchFieldException e) {
      throw new IllegalStateException("Unsupported SDK tracer configuration", e);
    } catch (IllegalAccessException e) {
      throw new IllegalStateException("Unsupported SDK tracer configuration", e);
    }
  }
}
