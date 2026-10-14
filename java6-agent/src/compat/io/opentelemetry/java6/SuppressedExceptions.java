/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package io.opentelemetry.java6;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

/** Preserve resource-cleanup failures on Java 7+ without breaking primary failures on Java 6. */
public final class SuppressedExceptions {
  private static final Method ADD_SUPPRESSED = findAddSuppressed();

  private static Method findAddSuppressed() {
    try {
      return Throwable.class.getMethod("addSuppressed", Throwable.class);
    } catch (NoSuchMethodException absentOnJava6) {
      return null;
    }
  }

  public static void addSuppressed(Throwable primary, Throwable secondary) {
    if (primary == null || secondary == null) throw new NullPointerException();
    if (primary == secondary) throw new IllegalArgumentException("Self-suppression not permitted");
    if (ADD_SUPPRESSED == null) return;
    try {
      ADD_SUPPRESSED.invoke(primary, secondary);
    } catch (IllegalAccessException error) {
      throw new IllegalStateException(error);
    } catch (InvocationTargetException error) {
      Throwable cause = error.getCause();
      if (cause instanceof RuntimeException) throw (RuntimeException) cause;
      if (cause instanceof Error) throw (Error) cause;
      throw new IllegalStateException(cause);
    }
  }

  private SuppressedExceptions() {}
}
