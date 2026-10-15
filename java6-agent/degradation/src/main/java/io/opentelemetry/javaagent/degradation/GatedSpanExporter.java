/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation;

import io.opentelemetry.sdk.common.CompletableResultCode;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.export.SpanExporter;
import java.util.Collection;

final class GatedSpanExporter implements SpanExporter {
  private final SpanExporter delegate;
  private final DegradationState state;

  GatedSpanExporter(SpanExporter delegate, DegradationState state) {
    this.delegate = delegate;
    this.state = state;
  }

  @Override
  public CompletableResultCode export(Collection<SpanData> data) {
    return state.config.sendTraces ? delegate.export(data) : CompletableResultCode.ofSuccess();
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
  public void close() {
    shutdown().join(10, java.util.concurrent.TimeUnit.SECONDS);
  }
}
