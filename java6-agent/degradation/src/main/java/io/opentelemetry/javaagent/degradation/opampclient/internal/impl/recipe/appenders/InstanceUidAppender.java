/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.appenders;

import com.google.protobuf.ByteString;
import java.util.function.Supplier;
import opamp.proto.v1.Opamp.AgentToServer;

/**
 * This class is internal and is hence not for public use. Its APIs are unstable and can change at
 * any time.
 */
public final class InstanceUidAppender implements AgentToServerAppender {
  private final Supplier<byte[]> instanceUid;

  public static InstanceUidAppender create(Supplier<byte[]> instanceUid) {
    return new InstanceUidAppender(instanceUid);
  }

  private InstanceUidAppender(Supplier<byte[]> instanceUid) {
    this.instanceUid = instanceUid;
  }

  @Override
  public void appendTo(AgentToServer.Builder builder) {
    builder.setInstanceUid(ByteString.copyFrom(instanceUid.get()));
  }
}
