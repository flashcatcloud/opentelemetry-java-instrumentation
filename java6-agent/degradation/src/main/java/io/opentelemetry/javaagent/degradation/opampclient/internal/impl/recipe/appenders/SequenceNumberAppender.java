/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.appenders;

import java.util.function.Supplier;
import opamp.proto.v1.Opamp.AgentToServer;

/**
 * This class is internal and is hence not for public use. Its APIs are unstable and can change at
 * any time.
 */
public final class SequenceNumberAppender implements AgentToServerAppender {
  private final Supplier<Long> sequenceNumber;

  public static SequenceNumberAppender create(Supplier<Long> sequenceNumber) {
    return new SequenceNumberAppender(sequenceNumber);
  }

  private SequenceNumberAppender(Supplier<Long> sequenceNumber) {
    this.sequenceNumber = sequenceNumber;
  }

  @Override
  public void appendTo(AgentToServer.Builder builder) {
    builder.setSequenceNum(sequenceNumber.get());
  }
}
