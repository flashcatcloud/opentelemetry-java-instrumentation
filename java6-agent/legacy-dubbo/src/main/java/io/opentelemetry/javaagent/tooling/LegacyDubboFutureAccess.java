/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package io.opentelemetry.javaagent.tooling;

import com.alibaba.dubbo.remoting.exchange.support.DefaultFuture;
import io.opentelemetry.instrumentation.api.util.VirtualField;
import io.opentelemetry.javaagent.bootstrap.DubboBridge;

/** Keeps future-owned state under the official field-injection/fallback lifecycle. */
public final class LegacyDubboFutureAccess implements DubboBridge.FutureAccess {
  private static final VirtualField<DefaultFuture, DubboBridge.FutureState> FUTURE_STATE =
      VirtualField.find(DefaultFuture.class, DubboBridge.FutureState.class);
  public static final LegacyDubboFutureAccess INSTANCE = new LegacyDubboFutureAccess();

  @Override
  public Object get(Object future) {
    DubboBridge.FutureState state = FUTURE_STATE.get((DefaultFuture) future);
    return state == null ? null : state.value;
  }

  @Override
  public void set(Object future, Object state) {
    // Keep completed context for callbacks registered after response completion.
    // DefaultFuture is not reused. Completion drops request metadata; only the
    // callback context remains. Do not add a reference back to the owning future.
    FUTURE_STATE.set((DefaultFuture) future,
        state == null ? null : new DubboBridge.FutureState(state));
  }

  private LegacyDubboFutureAccess() {}
}
