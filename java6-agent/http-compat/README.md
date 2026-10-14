# Official HTTP sender compatibility overlay

The candidate now builds the SDK v1.66.0 `OkHttpHttpSender` and its provider,
response value type, dispatcher utility and retry interceptor from upstream source.
`sources.json` pins both original and prepared file hashes. `prepare-http-transport.py`
checks originals, applies patches without fuzz, and verifies every prepared file.
The handwritten sender source and its old build entry have been removed. The
packager rejects any stale handwritten sender classes.

The private runtime dependencies are source builds of OkHttp 3.12.13 and Okio 1.17.2.
Their published binaries require Java 7. The source build uses Oracle JDK 6 API
jars and Retrolambda, preserving upstream network protocol implementations.
Build with `JAVA6_HOME=/absolute/path/to/jdk1.6.0_45` when invoking
`build-official-candidate.sh /absolute/path/to/sdk-fork`.
Android and Conscrypt artifacts are compile-only and must not be packaged.

## Reasons for deviations

- Java 8 language/library usage is mapped to the existing Java 6 backports.
- Okio's two Java 7 `Path` overloads are excluded; no exporter call uses them.
  `Deflater.SYNC_FLUSH` is unavailable on Java 6 and fails explicitly if invoked.
  The SDK compressor and Okio response decompressor do not require this operation.
- The upstream Okio [b4fa875](https://github.com/square/okio/commit/b4fa875)
  gzip XLEN unsigned-length fix (CVE-2023-3635)
  is retained as an explicit patch; lengths 32768..65535 must not become negative.
- Android 10 platform detection is excluded from this server-JVM distribution.
- The upstream hostname ASCII guard from commit
  `f574ea2f5259d9040f264ddeb582fb1ce563f10c` is ported to Java source.
- A five-request admission limit bounds the old OkHttp dispatcher's unbounded
  waiting queue. Saturation is a telemetry export failure; it does not block callers.
- Retry sleep checks cancellation in 50 ms slices. Without this overlay, a long
  Retry-After delays timeout completion on the backported transport.
- Response decoding failures invoke the error callback. The unmodified source
  logs the IOException but can report a successful response with incomplete content.

The retry status policy, backoff calculation, HTTP handling, TLS validation,
request compression and response handling otherwise remain upstream implementations.
The patches expose every deviation for review; this is not an unchanged official binary.

## Evidence and release boundaries

`build/e2e/official-sender-reuse-v2/result.json` records the isolated prototype's
Java 6/8/17 tests, including gzip, invalid responses, TLS trust/hostname rejection,
retry cancellation, 500 submissions per JVM, exactly-once callbacks and cleanup.
These tests do not establish full Agent acceptance or long-running resource safety.
The Java 6 TLS test explicitly uses TLSv1; it does not establish TLS1.2 support.

OkHttp 3.12 is an old upstream line. Porting one known security fix is not a complete
security audit or a renewed upstream maintenance guarantee. Full candidate regression is recorded in [VALIDATION.md](VALIDATION.md).
Dependency review and sustained resource testing remain release gates.
Existing RC3 artifacts must not be overwritten by this candidate.
