/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.appenders;

import java.util.function.Supplier;
import opamp.proto.v1.Opamp.AgentToServer;
import opamp.proto.v1.Opamp.EffectiveConfig;

/**
 * This class is internal and is hence not for public use. Its APIs are unstable and can change at
 * any time.
 */
public final class EffectiveConfigAppender implements AgentToServerAppender {
  private final Supplier<EffectiveConfig> effectiveConfig;

  public static EffectiveConfigAppender create(Supplier<EffectiveConfig> effectiveConfig) {
    return new EffectiveConfigAppender(effectiveConfig);
  }

  private EffectiveConfigAppender(Supplier<EffectiveConfig> effectiveConfig) {
    this.effectiveConfig = effectiveConfig;
  }

  @Override
  public void appendTo(AgentToServer.Builder builder) {
    EffectiveConfig value = effectiveConfig.get();
    if (value != null) builder.setEffectiveConfig(value);
  }
}
