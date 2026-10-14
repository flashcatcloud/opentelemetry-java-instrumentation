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
