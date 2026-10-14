# Official HTTP sender candidate validation

Candidate SHA-256: `803152b566e261179743f288870f1eba9a40edb75304393fc96760375757c34b`.
This is a new candidate, not the published RC3. PR #1 was already merged; these changes require a new PR targeting `v2.32.0`.

Build command (exit 0):

```sh
JAVA6_HOME=/absolute/path/to/jdk1.6.0_45 sh java6-agent/build-official-candidate.sh /absolute/path/to/opentelemetry-java
```

Source preparation regression: `python3 java6-agent/tests/HttpSourcePreparationTest.py` passed, including repeatability, altered original source rejection and corrupt archive rejection without replacing the previous prepared output. The HTTP dependency and sender linkage checks covered 253 and 24 classes respectively, with zero missing Java 6 JDK links.

Raw results are retained under `java6-agent/build/e2e/official-http-final/` (ignored build evidence). Each result records the tested candidate hash; command-bearing records retain actual invocations. Remote test host was 10.98.1.245, not the Doris host. Test drivers were run from `/opt/flashcat-java6-agent-test/official-http-final/`: `python3 deflater.py`, `python3 startup.py`, `python3 continuity.py`, `python3 blocked.py`, `python3 retry.py`, and `python3 mixed.py` (all exit 0).

| Evidence | Result and scope |
| --- | --- |
| startup/matrix.json | 21 passes: seven baseline/configuration/disabled cases on Java 6, 8, 17; application main completed |
| continuity/*.json | Six passes: baseline and Agent on each JVM, 180 business requests per run; Collector 503, stalled response, recovery; business status/exception behavior preserved |
| blocked-results/*.json | Three passes: four 16 MB writes to a non-reading receiver; deadline callbacks and executor termination |
| retry-results/*.json | Three passes: 20 rounds of eight submissions per JVM; alternating failures/recovery, exactly-once callbacks, bounded admission, drained dispatcher, restored permits and terminated executor |
| deflater-results/*.json | Three passes: actual relocated dependency explicitly rejects unsupported Java 6 SYNC_FLUSH; Java 8/17 flushed payload decompresses correctly |
| network-matrix.json | 12 passes: authenticated gzip HTTP, trusted TLS, rejected untrusted TLS, and gRPC traces plus JVM metrics on each JVM |
| mixed-chain-baseline.json / mixed-chain.json | Both pass; four sync/async/concurrent request traces, each 15 spans across four services; parent IDs resolve, no error spans |

The mixed chain covers Java 8 Spring/HTTP entry, Java 6 Dubbox 2.8.4 with Oracle and Redis, Java 8 HTTP bridge, and Java 17 Dubbo 3.2.15/MySQL/Kafka worker. The same candidate JAR is used throughout; test application code is unchanged between baseline and instrumented runs.

Remote runtimes: Oracle 6u45-b06, Bisheng 8u402-b06 and Temurin 17.0.20.1+1. Local network tests additionally use Temurin 8u504, Java 17.0.1 for HTTP/TLS and Temurin 17.0.20.1+1 for gRPC. Java 6 TLS explicitly tests TLSv1, not TLS 1.2. gRPC testing here is plaintext with authentication headers.

These finite tests are not proof of zero business impact under all failures, a sustained resource soak, full exporter-option coverage, or a complete dependency security audit. The mixed results are captured by the test receiver; they do not establish that this candidate was displayed in the 9000 UI. The customer-specific Dubbox binary and enterprise bridge are not included. Existing continuous RC3 traffic and published RC3 artifacts remain unchanged.

## Subsequent dependency finding

The candidate above is superseded for release purposes: Oracle 6u45 reproduced CVE-2023-3635 through its private Okio GzipSource. `HttpGzipExtraProbe` accepted XLEN 0 and 32767, then failed at 32768 with `IllegalArgumentException: byteCount < 0: -32768`. The upstream `b4fa875` unsigned-length fix is now included in the source overlay. The repaired binary requires new validation; the results above must not be attributed to it. PR #2 merged at 2026-10-14T17:32:58Z before this fix and does not include it.

The repaired candidate SHA-256 is `a332b4e154788d7930007de08b872178509d288de4df13d3fbba0495b8cf06d6`. The full build exited 0. ZIP comparison against the previous candidate found only `GzipSource.classdata` and provenance changed. On Oracle 6u45, Java 8 and Java 17, `HttpGzipExtraProbe` decoded valid XLEN 0/32767/32768/65535 payloads and rejected truncated XLEN with IOException. Results are under `build/e2e/official-http-gzip-fixed/gzip-*.json`; the repaired candidate also passed the 21 startup cases, six business-continuity runs, three blocked-write, three retry/recovery and three Deflater checks, all 12 network cases and all three gzip-response HTTP export cases. The mixed baseline and candidate passed again: four traces of 15 spans, with resolved parent IDs and no error spans. All new evidence carries the repaired hash and is stored separately from the prior candidate. Sustained testing of the earlier candidate is still in progress and is not counted as a pass for this repaired binary.
