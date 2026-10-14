/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package io.opentelemetry.javaagent.bootstrap;

/** Minimal opaque state boundary for the official VirtualField mechanism. */
public final class DubboBridge {
  /** Future-owned state; this holder must never be retained by a global dispatcher. */
  public static final class FutureState {
    public final Object value;
    public FutureState(Object value) { this.value = value; }
  }
  /** Implemented by the typed, application-loader helper. Never retained globally. */
  public interface FutureAccess {
    Object get(Object future);
    void set(Object future, Object state);
  }
  private DubboBridge() {}
}
