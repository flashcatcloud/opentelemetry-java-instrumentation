# Single-JAR delivery gates

The current official-module candidate is under active development. No final release is declared. Expanded scope and authorizations are recorded in [MIGRATION.md](MIGRATION.md).

## Required final architecture

One JAR uses official Agent loading, Muzzle, helper injection, instrumentation components, autoconfiguration and exporters on Java 6/8/17. Compatibility overlays retain upstream source hashes and reviewable patches. The necessary old Dubbo extension uses official module discovery. Its direct-Tracer span lifecycle has been replaced with upstream RPC Instrumenter, semantic extractors, metrics and exception handling; legacy class/attachment/Future adaptation remains. Complete the legacy version/JVM and RPC semantic-mode regression before declaring this migration accepted. Module discovery alone does not establish component implementation parity. Replaced prototype HTTP/JDBC/Redis advice, standalone AgentBuilder and starter have been removed; packaging rejects their stale class files.

## Handwritten-code justification

Every handwritten adaptation must identify the upstream implementation considered, the exact incompatibility, why a smaller reuse option is insufficient, and behavioral verification. Provisional architecture choices remain explicit review items. See [legacy Dubbo reuse audit](legacy-dubbo/REUSE.md); functional passes alone do not justify duplication.

## Runtime acceptance

- Freeze one final artifact and verify its checksum across all runs on real Oracle 6u45, Java 8 and Java 17.
- Verify HTTP server/client, JDBC MySQL and Oracle, Redis, legacy Dubbo 2.5/2.6 sync/async and modern Dubbo 2.7/representative 3.x.
- Expand official modules for Spring MVC, common HTTP clients, JDBC pools, Jedis/Lettuce, executors, Kafka, RabbitMQ, MongoDB, Elasticsearch and gRPC. Record real library-version × JVM results; unavailable JVM/library combinations remain explicit.
- Verify propagation, parent IDs, errors, concurrent isolation, callback completion, cancellation/rejection/restoration, route/DB/RPC semantics and sampling. Startup alone is insufficient.
- Verify default logging and isolation from application dependencies; invalid configuration and unsupported export modes must be diagnosed without changing business behavior.
- Verify OTLP timeout/retry/shutdown, TLS and authentication paths, and suppress exporter self-tracing. HTTP/protobuf and plaintext OTLP/gRPC have candidate-level evidence. The published rc1 remains HTTP/protobuf-only. The bb295 candidate additionally passed Java8/17 trusted TLS, untrusted/hostname-mismatch rejection, and three-JVM deadline/UNAVAILABLE tests. Java6 gRPC TLS, client-certificate/protocol-option coverage, retry parity and long-duration failure coverage remain release gates; these results do not establish full transport parity.
- Verify classloader lifecycle, retransformation/disabled instrumentation, application behavior without the Agent, and representative startup/runtime overhead.
- Deploy the frozen artifact into the authorized PoC on independent host 10.98.1.245, send to Collector on 10.98.1.111, maintain traffic, and inspect complete traces on the 9000 UI. Preserve unrelated services.

## Reproducibility and handoff

- Finish fresh-checkout dependency/bootstrap tooling resolution with pinned checksums and clean builds.
- Reconcile README/configuration docs and remove or retire obsolete prototype entry points and misleading reports.
- Package required licenses/notices and provenance/SBOM, final SHA-256, supported-version matrix, deployment/rollback instructions and compatibility limits.
- Review changes in both flashcatcloud forks, commit/push/create reviewable PRs within the approved scope; do not automatically merge.

## Current commands

See [README.md](README.md) for the official candidate build. Core acceptance scripts are `verify-official-loader.py`, `e2e/official-chain.py`, `e2e/official-jdbc.py`, `e2e/official-redis.py` and `e2e/http-errors.py`. The chain runner supports legacy/modern Dubbo, executor/ForkJoin and Spring variants. It creates uniquely named temporary containers and removes only those containers. Credentials are supplied via existing test configuration rather than embedded in reports.

Historical prototype results and old `build/dist` artifacts do not satisfy these gates. Exact completed checks and remaining work are recorded with artifact hashes in MIGRATION.md.

## Integrated acceptance and application safety (user requirement 2026-10-14)

The final acceptance must include a continuously running 2–4-service mixed trace, not only isolated component probes: HTTP/Spring, RPC including Dangdang Dubbox 2.8.4 and upstream Apache Dubbo, Kafka, Redis, Oracle and MySQL, across real Oracle Java 6u45, Java 8 and Java 17. Include synchronous and asynchronous calls with cross-process parent/link verification and visible service instances on 9000. Application fixtures must contain no telemetry API calls or manually propagated tracing headers.

Application safety is a release blocker: unsupported combinations must skip instrumentation rather than prevent startup or change business results. Validate no-agent comparisons, incompatible/missing libraries, advice failures, collector unavailability/timeouts/backpressure, cancellation/errors and context cleanup. Test results bound this claim; do not promise absolute absence of all runtime risk based on a finite matrix.

Implemented four-service fixture: Java 8 Spring HTTP entry → Oracle Java 6 Dubbox 2.8.4 provider (Redis/Oracle) → Java 8 HTTP/Kafka publisher → Java 17 Kafka consumer and upstream Dubbo 3.2.15 provider (MySQL). The Java 8 bridge also invokes the native Dubbo provider. `e2e/mixed-chain.py` passed a no-agent baseline and four instrumented sync/async/concurrent traces, each with 15 spans and verified parent IDs, on candidate `f914002a9f9a27b293c0cca2188a9123baec3c3028a366d4a5e04465d9c6b3cb`. Evidence: `build/e2e/mixed-chain-baseline.json` and `mixed-chain-live-validation.json`. Continuous traffic forwards to 10.98.1.111:4418 and is visible on 9000. That historical run used local application containers. RC2 `2c21c7f18c4c1d8d3f1f9b7eb2eb4f6ed84aa8decd58d163f349a4edc8d9df2c` subsequently passed the four-service chain on native x86 10.98.1.111 (`build/e2e/mixed-chain-2c21-native.json`), with a separate continuous run forwarding to Collector. This establishes remote application execution. The RC2 UI sample in `build/e2e/rc2-ui-verification.json` records a four-service, fifteen-span trace with HTTP, Dubbo, Oracle, Redis, MySQL and Kafka call types. One rendered trace does not establish completion of all application-safety gates or all UI views.

## RC2 resource-cancellation evidence

RC2 passed the native x86 accepted-but-never-read HTTP request test on Oracle6u45 and Java8/17. Java8 and Java17 each passed five additional iterations, preserving per-run commands, hashes and resource assertions in `build/e2e/blocked-write-2c21-native/`. Local amd64-emulation failures are retained separately and remain unexplained; native passes do not erase them. No runtime patch was made in this revalidation. A twenty-cycle same-JVM blocked-write lifecycle check subsequently passed on each of Java6/8/17 (`build/e2e/rc2-sender-soak-results/`), with zero sender threads after each shutdown. A subsequent single-sender backpressure test passed ten rounds of eighty requests on each JVM, with exactly one callback per request and no active, queued, pending or timer work after each round (`build/e2e/rc2-sender-backpressure-results/`). These are bounded transport probes; hours-long business soak, heap/resource bounds and overhead checks remain outstanding. The RC2 full native component regression was interrupted during severe host memory/I/O pressure; its recorded startup failures remain unresolved and are not counted as passes (`build/e2e/native-regression-2c21/`).

## Test placement restriction (user correction 2026-10-14)

Do not run test applications, load generators, component fixtures or regression jobs on the Doris host 10.98.1.111. Existing remote application runs are historical evidence, not a deployment pattern to repeat. Keep the Collector endpoint there; execute subsequent tests locally or on the user-selected independent test host 10.98.1.245, accessed directly from the local machine (not through the jump host). Confirm login and capacity before deployment. Stop this task's misplaced test applications and runners, preserving Doris, Collector and unrelated services. The stop attempt is not confirmation: verify actual container/process termination before reporting cleanup complete.

## RC3 independent-host mixed-chain verification

The delivered RC3 SHA-256 `e6bfaf529d73fb0bdbbea0df7fb80357660e901ec493885e911ce5cce322601d` passed the unchanged four-service mixed fixture on independent host 10.98.1.245, with real Oracle 6u45, Java 8 and Java 17. The no-agent baseline and four instrumented sync/async/concurrent requests passed; each instrumented trace had exactly 15 unique spans, all four services, correct parent IDs, Oracle/MySQL/Redis attributes, two Dubbo paths and Kafka producer/consumer spans, without error statuses. Evidence is in `build/e2e/rc3-mixed245/`. Runner: `python3 /opt/flashcat-java6-agent-test/run-mixed245.py`, exit 0. The prior missing Oracle and old test-driver failures were environment failures and were not counted as passes. Published RC3 bytes are unchanged. Rendered 9000 UI inspection also confirmed four services and 15 spans; see RC3-VALIDATION.md. Longer soak, overhead and broader component/option coverage remain outstanding.
