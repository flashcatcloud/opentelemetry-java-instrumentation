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

import io.opentelemetry.sdk.autoconfigure.spi.ConfigProperties;
import java.util.Map;

/** EDOT CentralConfig connection settings; neutral keys remain optional aliases. */
final class EdotSettings {
  // package private for testing

  static String getEndpoint(ConfigProperties properties) {
    String endpoint = properties.getString("elastic.otel.opamp.endpoint");
    if (endpoint == null) endpoint = properties.getString("otel.javaagent.opamp.endpoint");
    if (endpoint == null || endpoint.isEmpty()) {
      return null;
    }
    if (!endpoint.endsWith("v1/opamp")) {
      if (endpoint.endsWith("/")) {
        endpoint += "v1/opamp";
      } else {
        endpoint += "/v1/opamp";
      }
    }
    return endpoint;
  }

  // package private for testing
  static String getServiceName(ConfigProperties properties) {
    String serviceName = properties.getString("otel.service.name");
    if (serviceName != null) {
      return serviceName;
    }
    Map<String, String> resourceMap = properties.getMap("otel.resource.attributes");
    serviceName = resourceMap.get("service.name");
    if (serviceName != null) {
      return serviceName;
    }
    return "unknown_service:java"; // Specified default
  }

  // package private for testing

  static String getServiceEnvironment(ConfigProperties properties) {
    Map<String, String> resourceMap = properties.getMap("otel.resource.attributes");
    String environment = resourceMap.get("deployment.environment.name");
    if (environment != null) {
      return environment;
    }
    return resourceMap.get("deployment.environment"); // backward compatible, can be null
  }

  static String setting(ConfigProperties config, String suffix) {
    String value = config.getString("elastic.otel.opamp." + suffix);
    return value != null ? value : config.getString("otel.javaagent.opamp." + suffix);
  }

  static Map<String, String> headers(ConfigProperties config) {
    return config.getMap(
        config.getString("elastic.otel.opamp.headers") != null
            ? "elastic.otel.opamp.headers"
            : "otel.javaagent.opamp.headers");
  }
}
