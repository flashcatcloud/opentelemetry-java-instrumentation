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

The repaired candidate SHA-256 is `a332b4e154788d7930007de08b872178509d288de4df13d3fbba0495b8cf06d6`. The full build exited 0. ZIP comparison against the previous candidate found only `GzipSource.classdata` and provenance changed. On Oracle 6u45, Java 8 and Java 17, `HttpGzipExtraProbe` decoded valid XLEN 0/32767/32768/65535 payloads and rejected truncated XLEN with IOException. Results are under `build/e2e/official-http-gzip-fixed/gzip-*.json`; the repaired candidate also passed the 21 startup cases, six business-continuity runs, three blocked-write, three retry/recovery and three Deflater checks, all 12 network cases and all three gzip-response HTTP export cases. The mixed baseline and candidate passed again: four traces of 15 spans, with resolved parent IDs and no error spans. All new evidence carries the repaired hash and is stored separately from the prior candidate. The earlier candidate sustained run was stopped after its Java 6 run completed; its Java 8 interruption is not a functional pass and no result from it is counted for the repaired binary. The repaired-candidate long tests were stopped at the user’s request to prioritize delivery. Oracle 6u45 completed its 600-round transport run; Java 8/17 long runs and the extended business runs are not counted as passes.


## Repaired-candidate source rebuild and component regression

A fresh source-only build from Agent `f3a32b7a38` and merged SDK `3a96a956aee3b269e85bffbd046a7784ae4bc05a` completed with exit 0 using `JAVA6_HOME=/absolute/path/to/jdk1.6.0_45 sh java6-agent/build-all.sh /absolute/path/to/clean-sdk`. The build directory was populated by `git archive`, without copying prior build outputs. The rebuilt JAR has exactly the repaired SHA-256 above, with no added, removed or changed ZIP entries. Evidence: `build/e2e/official-http-gzip-fixed/clean-build.json` and `clean-build.log`.

The same repaired binary passed 12 Spring/executor/ForkJoin/modern Dubbo cases (`fixed-components/matrix.json`) and 21 JDBC/Jedis/MongoDB/gRPC/RabbitMQ/Lettuce cases (`broad-components/matrix.json`). Each record retains its exact command, exit code and candidate hash. Versions and JVM combinations are those in the recorded commands and fixture reports; this is not a claim that every modern library supports Java 6.

Native Oracle JDBC comparison on 10.98.1.245 passed baseline and Agent runs on Java 6, 8 and 17 (`oracle-native/*.json`). Agent runs produced three client spans, including the expected SQL error, with Oracle semantics and unchanged fixture bytecode. An earlier local SSH-tunnel attempt failed identically without the Agent and is retained separately under `oracle/`; it is not counted as a passing run or an Agent regression.

The repaired candidate subsequently passed all seven legacy/modern Dubbo scenarios (`legacy-final/matrix.json`): Dubbo 2.5.3 and 2.6.2 on Oracle 6u45, Dubbox 2.8.4 on Java 8, Dubbo 2.6.12 on Java 17, Java 6 Dubbox VirtualField fallback and stable RPC semantics, and upstream Dubbo 3.2.15 on Java 17. The full legacy scenarios include nine async modes and no-agent comparisons; fallback and stable-semantic scenarios use their explicitly recorded subsets.

Four DBCP/Hikari cases on Java 8/17 passed (`pools/matrix.json`). Six application-classloader runs passed, baseline and Agent on Java 6/8/17 (`classloader/matrix.json`): three disposable Redis application loaders were collected in each run and Agent runs emitted 18 spans. This does not establish cleanup for every asynchronous application object graph.

## RC4 delivery

The exact repaired JAR was published to repo host 8.141.104.18 at `/datafc/repo/hnnx/flashcat_agent/2.32.0-java6-rc4/flashcat-javaagent.jar` (21,078,036 bytes). Remote `sha256sum -c SHA256SUMS` passed for the JAR, Chinese usage instructions and `verification.json`. Published RC3 is unchanged. PR #3 was merged before publishing; it contains the repaired runtime sources.

The same JAR runs on independent test host 10.98.1.245 and forwards to Collector 10.98.1.111:4418. A seeded async request returned the unchanged business value 42. Rendered 9000 inspection of trace `ef421272a8224709ad906cdc5deeb39e` confirmed four services and 15 spans, successful HTTP/Dubbo/Oracle/Redis/MySQL/Kafka calls, including producer/consumer and both Dubbo paths. Evidence is recorded in `build/delivery/2.32.0-java6-rc4/verification.json`; the matching topic/container suffix is `a8352801`, distinguishing this run from RC3 traffic.

Long tests were explicitly stopped by the user; this release does not claim completed long-duration resource/performance acceptance. Full TLS/client-certificate options, customer-specific Dubbox binaries/enterprise bridges and all upstream components remain outside the verified support matrix. Oracle 6u45 gRPC TLS remains unsupported by the verified path. These limitations are included in the delivered usage instructions.
