/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation.opampclient.internal.request.delay;

import java.time.Duration;
import javax.annotation.concurrent.GuardedBy;

public final class ExponentialBackoffPeriodicDelay implements PeriodicDelay {
  private final Duration initialDelay;
  private final Object delayNanosLock = new Object();

  @GuardedBy("delayNanosLock")
  private long delayNanos;

  public ExponentialBackoffPeriodicDelay(Duration initialDelay) {
    this.initialDelay = initialDelay;
    delayNanos = initialDelay.toNanos();
  }

  @Override
  public Duration getNextDelay() {
    synchronized (delayNanosLock) {
      long previousValue = delayNanos;
      delayNanos = delayNanos > Long.MAX_VALUE / 2 ? Long.MAX_VALUE : delayNanos * 2;
      return Duration.ofNanos(previousValue);
    }
  }

  @Override
  public void reset() {
    synchronized (delayNanosLock) {
      delayNanos = initialDelay.toNanos();
    }
  }
}
