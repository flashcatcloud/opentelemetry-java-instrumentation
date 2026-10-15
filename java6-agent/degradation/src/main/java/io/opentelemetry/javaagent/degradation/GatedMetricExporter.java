/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation;

import io.opentelemetry.sdk.common.CompletableResultCode;
import io.opentelemetry.sdk.common.export.MemoryMode;
import io.opentelemetry.sdk.metrics.Aggregation;
import io.opentelemetry.sdk.metrics.InstrumentType;
import io.opentelemetry.sdk.metrics.data.AggregationTemporality;
import io.opentelemetry.sdk.metrics.data.MetricData;
import io.opentelemetry.sdk.metrics.export.MetricExporter;
import java.util.Collection;

final class GatedMetricExporter implements MetricExporter {
  private final MetricExporter delegate;
  private final DegradationState state;

  GatedMetricExporter(MetricExporter delegate, DegradationState state) {
    this.delegate = delegate;
    this.state = state;
  }

  @Override
  public CompletableResultCode export(Collection<MetricData> data) {
    return state.config.sendMetrics ? delegate.export(data) : CompletableResultCode.ofSuccess();
  }

  @Override
  public CompletableResultCode flush() {
    return delegate.flush();
  }

  @Override
  public CompletableResultCode shutdown() {
    return delegate.shutdown();
  }

  @Override
  public AggregationTemporality getAggregationTemporality(InstrumentType type) {
    return delegate.getAggregationTemporality(type);
  }

  @Override
  public Aggregation getDefaultAggregation(InstrumentType type) {
    return delegate.getDefaultAggregation(type);
  }

  @Override
  public MemoryMode getMemoryMode() {
    return delegate.getMemoryMode();
  }

  @Override
  public void close() {
    shutdown().join(10, java.util.concurrent.TimeUnit.SECONDS);
  }
}
