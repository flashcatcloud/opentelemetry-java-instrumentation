# RC3 validation for fork review

Tested delivery artifact SHA-256: `e6bfaf529d73fb0bdbbea0df7fb80357660e901ec493885e911ce5cce322601d` (20,560,558 bytes). This is a release candidate, not full upstream feature parity or final production acceptance. Generated binaries and raw captured traces are intentionally excluded from Git.

| Verification | Result | Runner / retained evidence under `java6-agent/build/` |
| --- | --- | --- |
| Legacy Dubbo 2.5.3/2.6.2 and Dubbox 2.8.4 on Oracle 6u45; Dubbox on 8; 2.6.12 and modern 3.2.15 on 17 | Passed synchronous, asynchronous, error, cancellation, timeout and propagation assertions | `e2e/official-chain.py`, `e2e/legacy-official-reuse/`, `e2e/native-legacy-reuse-rc3/` |
| Independent-host Spring/executor/ForkJoin/modern Dubbo matrix | 12 cases, exit 0, identical artifact | `e2e/official-chain.py`, `e2e/rc3-components/matrix.json` |
| Four unchanged business services on independent host, Oracle 6u45 / 8 / 17 | No-agent baseline passed; four sync/async/concurrent traces each had exactly 15 unique spans with correct parents | `e2e/mixed-chain.py`, `e2e/rc3-mixed245/` |
| HTTP, Dubbox, Apache Dubbo, Oracle, Redis, MySQL, Kafka in one chain | Passed assertions and rendered UI inspection | `e2e/rc3-mixed245/ui-verification.json`; trace `527b5fa81c0b48f2aa4d0cb5bd4b79f7` |
| OTLP/gRPC traces and positive JVM metrics on 6/8/17; trusted and untrusted TLS on 8/17 | Seven cases passed; rejection did not fall back to plaintext | `e2e/grpc-export-metrics.py`, `e2e/rc3-grpc-regression/matrix.json` |
| Actual Collector gRPC acceptance on 6/8/17 | Successful forwarding for both traces and metrics, no partial rejection | `e2e/rc3-grpc-forward/`; does not prove downstream metrics UI/storage |
| Accepted-but-blocked HTTP sender backpressure | Five repeated processes per JVM, each ten rounds of 80 requests; exactly one callback per request and no remaining active/queued/pending/timer work | `tests/SenderBlockedWriteProbe.java`, `e2e/rc3-backpressure-results/` |
| Legacy helper/registry disposable classloader | Passed on 6/8/17 | `tests/LegacyDubboClassLoaderProbe.java`, `e2e/legacy-official-reuse/unload-*.json` |

Test applications and databases run on the independent test host, not the Doris/Collector host. Continuous mixed traffic remains enabled. Raw runner commands and exit codes are retained in the above local reports; commands and prerequisites for reproducing fixtures are in README.md and the corresponding runner's `--help`.

Remaining gates include longer resource/overhead soak, broader frozen-artifact component coverage, complete upstream suites, client-certificate and retry-option parity. Oracle 6u45 gRPC TLS is not supported by the verified path. Dedicated helper GC tests do not establish absence of all application/classloader leaks. Earlier failed environmental runs are preserved separately and are not counted as passes.

## Source-only rebuild

`sh java6-agent/build-all.sh /absolute/path/to/clean/sdk` completed with exit 0 in a fresh directory with no generated output or dependency caches. Rebuilt SHA-256: `a6865944bf3bf635f0c56049677f97c5ecdd28ae2ac61e7c226b2bdbbd19bbde`. It is **not byte-identical** to delivered RC3. ZIP comparison found four changed entries: two provenance manifests, `LegacyDubboFutureAccess` debug line numbers, and its source location in generated Muzzle references (26 → 27). `javap -p -c -s -constants` showed unchanged FutureAccess instructions and only that Muzzle diagnostic line change in the module. The published RC3 was not replaced. Full comparison: `build/rc3-clean-build-comparison.json`.

Matching SDK source is flashcatcloud/opentelemetry-java commit `99d7919`, reviewed in https://github.com/flashcatcloud/opentelemetry-java/pull/1. Build the paired forks; unmodified upstream SDK binaries are not interchangeable with this compatibility variant.

The rebuilt artifact also passed `e2e/official-chain.py --legacy-dubbo 2.8.4 --dubbox-java6-api --async-modes get,callback,late,ignored,error,timeout,cancel,throw,fast --async-baseline` on real Oracle 6u45 on the independent host (exit 0), including synchronous propagation, all nine asynchronous modes and their no-agent comparisons. This targeted recheck is not a rerun of the entire RC3 matrix on the rebuilt digest.

## Bounded retry and recovery (2026-10-15)

`SenderRetryRecoveryProbe` passed on native Oracle 6u45, Java 8 and Java 17 using the unchanged RC3 SHA above. Each JVM reused one sender for 20 alternating 503-failure / 200-recovery rounds, eight requests per round. All 480 callbacks were exactly once, all recovery-round requests succeeded, aggregate attempts were bounded at 40 per round, and each round ended with zero active worker tasks, queued tasks, pending requests and timer tasks. Sender shutdown terminated its worker and timer pools. The sender used the upstream default retry policy and a three-second overall request deadline.

Compile with Oracle6 `javac -d probes SenderRetryRecoveryProbe.java`, then run with `-Xverify:all -Xmx192m -javaagent:<RC3.jar> -Dotel.instrumentation.common.default-enabled=false -Dotel.traces.exporter=none -Dotel.metrics.exporter=none -Dotel.logs.exporter=none -cp probes SenderRetryRecoveryProbe`. All three processes exited 0. Commands, runtime, artifact digest and full output are retained in `build/e2e/rc3-retry-recovery/retry-recovery-{6,8,17}.json`. `e2e/retry-recovery.py` provides a Docker-based entry point; the reported runs used native-host commands (Java17 in its container), not that wrapper.

The first probe failed because its mock HTTP endpoint terminated its accept loop on a cancelled client's EOF. That fixture was corrected to accept subsequent connections, and the failed report was retained separately. It is not counted as a sender pass. This is a direct transport test with bounded payloads, not an end-to-end application latency/heap soak or proof against every failure mode. Existing separate unchanged-business timeout tests passed on native Java6/8; local emulated runs failed to reach the mock endpoint before their deadline and are not counted as that scenario's passes.

## Full-Agent startup failure isolation

The unchanged RC3 passed 21 processes (seven cases on each of Oracle6u45, Java8 and Java17): no-agent baseline, normal Agent, malformed OTLP endpoint, unsupported protocol, unknown trace exporter, unknown sampler and explicitly disabled Agent. All processes exited 0 and completed the existing `PlainApplication` executor/exception/dependency-isolation fixture, with exactly one `APPLICATION_OK` marker. Maximum observed process duration was 6.19 seconds. Full commands and diagnostics: `build/e2e/rc3-startup-safety/matrix.json`. This verifies startup isolation for these configuration failures, not continuous traffic, all JVM startup errors or business latency parity.

## Short continuous business fault/recovery check

The unchanged RC3 passed all six runs: no-agent baseline and Agent-enabled execution on each of Oracle6u45, Java8 and Java17. Each run repeated the unchanged `HttpClientProbe` 60 times (180 business HTTP requests), preserving expected success, HTTP-error and connection-refusal behavior. Agent runs passed through Collector HTTP503 responses, delayed responses exceeding the configured 500ms export deadline, and successful HTTP200 recovery. All processes exited 0; every round completed within the explicit 5-second watchdog. Observed threads remained within the probe bound of a 32-thread range. This is approximately 30 seconds per run, not a long-duration soak, strict latency parity, heap-leak proof or complete downstream trace validation. Full commands, per-round timings/thread/heap samples, fault-phase observations, fixture source and driver are archived in `build/e2e/rc3-business-continuity/`.
