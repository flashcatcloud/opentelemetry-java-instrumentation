/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.appenders;

import java.util.function.Supplier;
import opamp.proto.v1.Opamp.AgentToServer;
import opamp.proto.v1.Opamp.CustomCapabilities;

/**
 * This class is internal and is hence not for public use. Its APIs are unstable and can change at
 * any time. TODO AgentToServer.getCustomMessage() support
 */
public final class CustomCapabilitiesAppender implements AgentToServerAppender {
  private final Supplier<CustomCapabilities> customCapabilities;

  public static CustomCapabilitiesAppender create(Supplier<CustomCapabilities> customCapabilities) {
    return new CustomCapabilitiesAppender(customCapabilities);
  }

  private CustomCapabilitiesAppender(Supplier<CustomCapabilities> customCapabilities) {
    this.customCapabilities = customCapabilities;
  }

  @Override
  public void appendTo(AgentToServer.Builder builder) {
    CustomCapabilities value = customCapabilities.get();
    if (value != null) builder.setCustomCapabilities(value);
  }
}
