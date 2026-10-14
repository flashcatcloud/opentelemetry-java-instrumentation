/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package io.opentelemetry.java6;

/** Java 6 equivalent of String.join for upstream endpoint rendering. */
public final class InstrumentationStrings {
  private InstrumentationStrings() {}
  public static String join(CharSequence delimiter, Iterable<? extends CharSequence> values) {
    if (delimiter == null || values == null) throw new NullPointerException();
    StringBuilder result = new StringBuilder();
    boolean first = true;
    for (CharSequence value : values) {
      if (!first) result.append(delimiter);
      result.append(value);
      first = false;
    }
    return result.toString();
  }
}
