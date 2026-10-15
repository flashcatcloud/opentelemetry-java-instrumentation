# Java 6 runtime degradation and OpAMP

This module ports EDOT Java 1.13.0's connection configuration and exporter gates,
and reuses its OpenTelemetry Contrib 1.59.0 OpAMP client state machine. The
Java 6 source adaptations and upstream file hashes are documented in [REUSE.md](REUSE.md)
and `upstream.json`. It is packaged into the existing compatibility agent.

Use the existing EDOT connection property; no additional enable flag or probe token:

```properties
elastic.otel.opamp.endpoint=http://n9e.example:19000
otel.service.name=my-service
otel.resource.attributes=deployment.environment.name=prod
```

The endpoint helper appends `/v1/opamp`. Existing `otel.*` export settings stay
unchanged. The legacy resource key `deployment.environment` also works. Neither
an environment nor authentication headers are required. Without an endpoint,
no OpAMP worker starts. `otel.javaagent.opamp.endpoint` remains an optional fallback
alias; the original `elastic.otel.opamp.endpoint` takes precedence.

The merged n9e-plus probe route requires no Authorization header. Management
routes continue using existing administrator headers (`X-User-Token`,
`X-User-Name`, `X-Cluster`); these are never agent configuration. Existing control
requests remain `POST /api/n9e-plus/opamp/control`, for example:

```json
{"scope":"service","selector":"my-service","stop":true}
```

Use `stop:false` to remove that rule. `instance` uses the instance UID as selector;
`all` uses an empty selector. Matching rules combine with OR: clearing a global
rule does not clear a service or instance stop. Instances and ACK state remain
available through `/api/n9e-plus/opamp/instances`.

The server supplies the same `elastic` JSON namespace and five controls:

```json
{"deactivate_all_instrumentations":"true","send_traces":"false","send_metrics":"false","send_logs":"false","opamp_polling_interval":"5s"}
```

EDOT defaults apply to omitted fields: instrumentation enabled, all three exporters
enabled, polling every 30 seconds. Unknown fields are ignored; invalid string
booleans retain the previous value. Malformed JSON is rejected with FAILED and the
previous configuration retained. APPLIED carries the applied hash; FAILED does not.
The upstream client handles sequence numbers, changed-field compression,
ReportFullState, retry/backoff and ACK recovery.

Stop disables SDK span recording for cached and new tracers and gates trace,
metric and log exporters. Resume restores the original tracer configurator and
exporter flags in the same JVM. Injected bytecode remains; internal metric/log
collection and already in-flight exports can continue. This module implements
HTTP/protobuf remote configuration, not restart/package management or WebSocket.

## Build and verification

Run `java6-agent/build-official-candidate.sh /path/to/opentelemetry-java` with the
existing Java 6 SDK prerequisites. Packaging relocates the reused client's HTTP
references into the existing private transport, merges SPI registrations, and
includes EDOT LICENSE/NOTICE, dependency licenses, SBOM and source provenance.

Compile `tests/InteropApplication.java` with JDK 8 `javac -source 6 -target 6`,
the real Java 6 `rt.jar` as `-bootclasspath`, and the packaged agent as `-cp`.
Run each target Java executable with:

```sh
INTEROP_JAVA=/path/to/java \
INTEROP_AGENT=/path/to/official-loader-candidate.jar \
INTEROP_CLASSPATH=/path/to/test-classes \
python3 java6-agent/degradation/tests/run.py /path/to/n9e-plus
```

The runner extracts committed handler/store sources using `git show`, never local
uncommitted server files, and executes
`go test -mod=mod -race -v -count=1 -timeout=300s .` in an isolated HTTP/SQLite server.
It checks service/instance/all stop-resume, overlapping rule removal, no probe
authentication, cached/new tracers, all three signals, continued business traffic,
lost ACK, HTTP 503, invalid JSON, HTTP 429 Retry-After, protocol Unavailable,
ReportFullState and default-off operation. Native Linux x86_64 is used for Oracle
Java 6u45; this HTTP matrix does not establish Java 6 HTTPS interoperability or
exercise the deployed management authentication middleware.

The server baseline is main `5022f6c22e2f30b77c51ce9c76770127e7290de4`.
Handler/store match release-27 `c7f7a4f04d0357ca14726e9b93eae8b6fad3b5c8`.
The same harness can compare the official EDOT 1.13.0 JAR on Java 21.
`ConfigCompatibilityTest` and `ProtocolCompatibilityTest` separately verify
configuration precedence/defaults and the backported upstream protocol state machine.

## Verified on 2026-10-15

The complete isolated-PR candidate build passed. Both interoperability tests passed
on Oracle 6u45 (native Linux x86_64), Zulu 8u504, Zulu 11.0.32.1, Temurin 17.0.20.1
and Homebrew 21.0.3 (macOS ARM64). Official EDOT 1.13.0 passed the same expanded
harness on Java 21. An earlier official comparison attempt hit an initialization
race; see REUSE.md rather than treating repeated success as proof that EDOT has
no startup issue.

The Java configuration and protocol tests passed. Running
`python3 java6-agent/check_jdk6.py /path/to/jdk6/jre/lib/rt.jar java6-agent/build/degradation-java6`
checked 861 classes with zero missing JDK 6 links. Java format, Python compilation
and shell syntax checks passed. `git diff --check` passes excluding the verbatim
upstream EDOT-NOTICE, whose original trailing blank line is preserved.

Matrix-tested JAR SHA-256:
`cc1a8eabdaaef792dc95ff483658005ec497eaf3052851f4eb911de23c195a1f`.
Final packaged JAR SHA-256:
`096ee22d639a6433212d606a4f4fb30fd2a5a8cf90750e62ff04d3784e92c0cb`.
A ZIP-entry comparison verified that only `META-INF/sbom.cdx.json` and
`META-INF/provenance/inputs.json` changed when completing the source inventory;
all executable classes and runtime resources are byte-identical. CRC verification
passed. The candidate contains no unrelated uncommitted middleware changes.
