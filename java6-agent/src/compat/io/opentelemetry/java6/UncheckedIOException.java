/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package io.opentelemetry.java6;

import java.io.IOException;

/** Java6 equivalent for the JDK8 unchecked IO wrapper used by upstream marshalers. */
public final class UncheckedIOException extends RuntimeException {
  private static final long serialVersionUID = 1L;
  public UncheckedIOException(IOException cause) { super(require(cause)); }
  public UncheckedIOException(String message, IOException cause) { super(message, require(cause)); }
  private static IOException require(IOException cause) {
    if (cause == null) throw new NullPointerException("cause");
    return cause;
  }
  @Override public IOException getCause() { return (IOException) super.getCause(); }
}
