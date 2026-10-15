/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation;

import io.opentelemetry.sdk.common.CompletableResultCode;
import io.opentelemetry.sdk.logs.data.LogRecordData;
import io.opentelemetry.sdk.logs.export.LogRecordExporter;
import java.util.Collection;

final class GatedLogRecordExporter implements LogRecordExporter {
  private final LogRecordExporter delegate;
  private final DegradationState state;

  GatedLogRecordExporter(LogRecordExporter delegate, DegradationState state) {
    this.delegate = delegate;
    this.state = state;
  }

  @Override
  public CompletableResultCode export(Collection<LogRecordData> data) {
    return state.config.sendLogs ? delegate.export(data) : CompletableResultCode.ofSuccess();
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
