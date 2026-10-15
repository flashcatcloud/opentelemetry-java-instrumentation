/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package io.opentelemetry.javaagent.degradation;

import io.opentelemetry.sdk.logs.export.LogRecordExporter;
import io.opentelemetry.sdk.metrics.export.MetricExporter;
import io.opentelemetry.sdk.trace.export.SpanExporter;
import java.util.ArrayList;
import java.util.List;

final class DegradationState {
  volatile DegradationConfig config = DegradationConfig.ENABLED;
  private final List<BlockableSpanExporter> spans = new ArrayList<>();
  private final List<BlockableMetricExporter> metrics = new ArrayList<>();
  private final List<BlockableLogRecordExporter> logs = new ArrayList<>();

  synchronized SpanExporter wrap(SpanExporter delegate) {
    BlockableSpanExporter exporter = BlockableSpanExporter.createCustomInstance(delegate);
    exporter.setSendingSpans(config.sendTraces);
    spans.add(exporter);
    return exporter;
  }

  synchronized MetricExporter wrap(MetricExporter delegate) {
    BlockableMetricExporter exporter = BlockableMetricExporter.createCustomInstance(delegate);
    exporter.setSendingMetrics(config.sendMetrics);
    metrics.add(exporter);
    return exporter;
  }

  synchronized LogRecordExporter wrap(LogRecordExporter delegate) {
    BlockableLogRecordExporter exporter = BlockableLogRecordExporter.createCustomInstance(delegate);
    exporter.setSendingLogs(config.sendLogs);
    logs.add(exporter);
    return exporter;
  }

  synchronized void publish(DegradationConfig value) {
    for (BlockableSpanExporter exporter : spans) exporter.setSendingSpans(value.sendTraces);
    for (BlockableMetricExporter exporter : metrics) exporter.setSendingMetrics(value.sendMetrics);
    for (BlockableLogRecordExporter exporter : logs) exporter.setSendingLogs(value.sendLogs);
    config = value;
  }
}
