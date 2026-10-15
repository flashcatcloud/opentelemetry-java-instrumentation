/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package io.opentelemetry.javaagent.degradation;

import com.google.gson.stream.JsonReader;
import com.google.gson.stream.JsonToken;
import java.io.IOException;
import java.io.StringReader;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;

final class DegradationConfig {
  static final DegradationConfig ENABLED =
      new DegradationConfig(false, true, true, true, Duration.ofSeconds(5));
  final boolean stopped, sendTraces, sendMetrics, sendLogs;
  final Duration interval;

  DegradationConfig(
      boolean stopped, boolean traces, boolean metrics, boolean logs, Duration interval) {
    this.stopped = stopped;
    this.sendTraces = traces;
    this.sendMetrics = metrics;
    this.sendLogs = logs;
    this.interval = interval;
  }

  static DegradationConfig parse(byte[] bytes) throws IOException {
    JsonReader reader = new JsonReader(new StringReader(new String(bytes, "UTF-8")));
    reader.setLenient(false);
    Map<String, String> values = new HashMap<>();
    try {
      reader.beginObject();
      while (reader.hasNext()) {
        String key = reader.nextName();
        if (values.containsKey(key)) throw new IOException("Duplicate field");
        if (!key.equals("deactivate_all_instrumentations")
            && !key.equals("send_traces")
            && !key.equals("send_metrics")
            && !key.equals("send_logs")
            && !key.equals("opamp_polling_interval")) throw new IOException("Unknown field");
        JsonToken token = reader.peek();
        if (token == JsonToken.STRING) values.put(key, reader.nextString());
        else if (token == JsonToken.BOOLEAN && !key.equals("opamp_polling_interval"))
          values.put(key, Boolean.toString(reader.nextBoolean()));
        else throw new IOException("Invalid value");
      }
      reader.endObject();
      if (reader.peek() != JsonToken.END_DOCUMENT) throw new IOException("Trailing JSON");
    } finally {
      reader.close();
    }
    Duration interval = ENABLED.interval;
    if (values.containsKey("opamp_polling_interval")) {
      String value = values.get("opamp_polling_interval");
      if (!value.matches("[0-9]+s")) throw new IOException("Invalid interval");
      long seconds = Long.parseLong(value.substring(0, value.length() - 1));
      if (seconds < 1 || seconds > 3600) throw new IOException("Invalid interval");
      interval = Duration.ofSeconds(seconds);
    }
    return new DegradationConfig(
        bool(values, "deactivate_all_instrumentations"),
        bool(values, "send_traces"),
        bool(values, "send_metrics"),
        bool(values, "send_logs"),
        interval);
  }

  private static boolean bool(Map<String, String> values, String key) throws IOException {
    String value = values.get(key);
    if ("true".equals(value)) return true;
    if ("false".equals(value)) return false;
    throw new IOException("Missing or invalid boolean");
  }
}
