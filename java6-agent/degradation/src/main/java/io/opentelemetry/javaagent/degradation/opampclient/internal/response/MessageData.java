/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation.opampclient.internal.response;

import com.google.auto.value.AutoValue;
import io.opentelemetry.javaagent.degradation.opampclient.OpampClient;
import javax.annotation.Nullable;
import opamp.proto.v1.Opamp.AgentRemoteConfig;
import opamp.proto.v1.Opamp.CustomMessage;

/**
 * Data class provided in {@link OpampClient.Callbacks#onMessage(OpampClient, MessageData)} with
 * Server's provided status changes.
 */
@AutoValue
public abstract class MessageData {
  @Nullable
  public abstract AgentRemoteConfig getRemoteConfig();

  @Nullable
  public abstract CustomMessage getCustomMessage();

  public static Builder builder() {
    return new AutoValue_MessageData.Builder();
  }

  @AutoValue.Builder
  public abstract static class Builder {
    public abstract Builder setRemoteConfig(AgentRemoteConfig remoteConfig);

    public abstract Builder setCustomMessage(CustomMessage customMessage);

    public abstract MessageData build();
  }
}
