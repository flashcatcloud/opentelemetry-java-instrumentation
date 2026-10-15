/*
 * Licensed to Elasticsearch B.V. under one or more contributor
 * license agreements. See the NOTICE file distributed with
 * this work for additional information regarding copyright
 * ownership. Elasticsearch B.V. licenses this file to you under
 * the Apache License, Version 2.0 (the "License"); you may
 * not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
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
      new DegradationConfig(false, true, true, true, Duration.ofSeconds(30));
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
    return parse(bytes, ENABLED);
  }

  static DegradationConfig parse(byte[] bytes, DegradationConfig previous) throws IOException {
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
            && !key.equals("opamp_polling_interval")) {
          reader.skipValue();
          continue;
        }
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
      try {
        interval = Duration.parse("PT" + values.get("opamp_polling_interval"));
        // Bound scheduling to avoid zero/negative busy loops and nanosecond overflow.
        if (interval.isZero() || interval.isNegative()) throw new IllegalArgumentException();
        interval.toNanos();
      } catch (RuntimeException invalid) {
        interval = previous.interval;
      }
    }
    return new DegradationConfig(
        bool(values, "deactivate_all_instrumentations", false, previous.stopped),
        bool(values, "send_traces", true, previous.sendTraces),
        bool(values, "send_metrics", true, previous.sendMetrics),
        bool(values, "send_logs", true, previous.sendLogs),
        interval);
  }

  // EDOT CentralConfig.Configs restores defaults for omitted keys. ConfigOption.getBoolean
  // accepts case-insensitive strings; updateOrLog retains a property's old value on errors.
  private static boolean bool(
      Map<String, String> values, String key, boolean fallback, boolean previous) {
    String value = values.get(key);
    if (value == null) return fallback;
    if ("true".equalsIgnoreCase(value)) return true;
    if ("false".equalsIgnoreCase(value)) return false;
    java.util.logging.Logger.getLogger(DegradationConfig.class.getName())
        .warning("Invalid remote boolean: " + key);
    return previous;
  }
}
