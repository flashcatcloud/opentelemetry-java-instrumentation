/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package io.opentelemetry.java6;

/** JDK7 Character.isSurrogate, expressed using the same UTF-16 code unit range. */
public final class Characters {
  public static boolean isSurrogate(char value) { return value >= '\uD800' && value <= '\uDFFF'; }
  private Characters() {}
}
