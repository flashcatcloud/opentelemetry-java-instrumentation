/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation;

final class DegradationState {
  volatile DegradationConfig config = DegradationConfig.ENABLED;
}
