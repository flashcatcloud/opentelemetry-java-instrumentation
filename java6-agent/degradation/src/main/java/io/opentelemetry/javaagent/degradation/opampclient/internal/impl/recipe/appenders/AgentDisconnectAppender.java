/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.appenders;

import opamp.proto.v1.Opamp.AgentDisconnect;
import opamp.proto.v1.Opamp.AgentToServer;

/**
 * This class is internal and is hence not for public use. Its APIs are unstable and can change at
 * any time.
 */
public final class AgentDisconnectAppender implements AgentToServerAppender {

  public static AgentDisconnectAppender create() {
    return new AgentDisconnectAppender();
  }

  private AgentDisconnectAppender() {}

  @Override
  public void appendTo(AgentToServer.Builder builder) {
    builder.setAgentDisconnect(AgentDisconnect.newBuilder().build());
  }
}
