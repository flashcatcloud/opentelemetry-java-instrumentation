/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation.opampclient.internal.response;

import com.google.auto.value.AutoValue;
import opamp.proto.v1.Opamp.ServerToAgent;

@AutoValue
public abstract class Response {
  public abstract ServerToAgent getServerToAgent();

  public static Response create(ServerToAgent serverToAgent) {
    return new AutoValue_Response(serverToAgent);
  }
}
