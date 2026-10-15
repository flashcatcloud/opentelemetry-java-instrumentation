# EDOT and merged n9e-plus alignment

## Pinned references

- EDOT Java **v1.13.0**, commit `be989afffc981ab39374d271880494a4f6a3842d`:
  <https://github.com/elastic/elastic-otel-java/tree/v1.13.0/custom/src/main/java/co/elastic/otel/dynamicconfig>.
- Its declared OpAMP dependency, OpenTelemetry Java Contrib **v1.59.0**:
  <https://github.com/open-telemetry/opentelemetry-java-contrib/tree/v1.59.0/opamp-client>.
- n9e-plus main `5022f6c22e2f30b77c51ce9c76770127e7290de4`, with handler/store
  identical to release-27 `c7f7a4f04d0357ca14726e9b93eae8b6fad3b5c8`.
- Final decisions from “查找 Java Agent 热关闭插桩支持”: no probe token, existing
  administrator authentication only on management routes, instance/service/all
  rules combined with OR semantics, no bytecode unloading.

`upstream.json` records the original source paths and hashes. Original copyright
headers are retained, and EDOT LICENSE/NOTICE are included in the candidate JAR.
This is source reuse with the adaptations below, not an unchanged EDOT binary.

## Reused code

| Source | Port | Changes |
| --- | --- | --- |
| EDOT `CentralConfig` connection helpers | `EdotSettings` | Preserve original keys and suffix/service/environment precedence; retain the already introduced neutral key as an optional fallback alias |
| EDOT `CentralConfig.Configs` and `ConfigOption` behavior | `DegradationConfig` | Five n9e-plus controls only; existing Gson parser replaces Java 8 DSL-JSON; omitted keys reset defaults, unknown keys ignored, invalid string booleans retain old values |
| EDOT `Blockable*Exporter` | Same classes | Package rename; per-exporter instances instead of one global last-exporter singleton; forward current SDK memory mode and close |
| EDOT `OpampManager` wiring and callbacks | `OpampConnection` | Current protobuf API, existing SDK controller, bounded JSON body; unchanged remote namespace and APPLIED/FAILED hash behavior |
| EDOT `OpampTlsConfigurer` | Same class | Java 6 file reads and existing Commons Codec Base64; preserve TLS/CA/client-key configuration behavior |
| Upstream `OpampClient`, builder, state, recipes and appenders | `opampclient/` | Package isolation and Wire-to-protobuf APIs, explicit omission of null optional messages |
| Upstream HTTP request service, sender, retry delays and Retry-After parser | `opampclient/` | Existing backported OkHttp runtime, Java 6 APIs, lifecycle/error-boundary corrections described below |

The earlier hand-written HTTP loop and `Gated*Exporter` classes have been removed.
Wire 6 / Kotlin and modern OkHttp binaries cannot load on Java 6. The port uses
existing Java 6 OkHttp 3.12/Okio and protobuf-java 3.3; Retrolambda and the branch's
existing Java 8/time API adapters handle source-level compatibility. AutoValue is
only used at build time. The protocol state machine is reused, not reimplemented.

## Configuration and control contract

| Item | EDOT / existing n9e-plus | This module |
| --- | --- | --- |
| Enablement | `elastic.otel.opamp.endpoint`, absent means off | Same; no new required flag/token |
| Endpoint path | Append `/v1/opamp`, including URL path prefixes | Copied helper |
| Headers | Optional EDOT headers; n9e probe requires none | No Authorization sent in integration tests |
| Service | `otel.service.name`, then resource `service.name`, then default | Copied helper |
| Environment | `deployment.environment.name`, then `deployment.environment` | Copied helper; neither is required |
| Poll interval | Starts at 30s, n9e sends 5s | Same |
| Remote config | `elastic` JSON map, string boolean controls | Same; JSON booleans also accepted |
| Defaults | Missing keys return to defaults; unknown keys ignored | Same for the five controls in scope |
| Invalid boolean string | Log and preserve that property's previous value | Same |
| ACK | Applied hash only on APPLIED; FAILED does not claim an applied hash | Same |
| State messages | Sequence number, stable UID, changed-field compression, ReportFullState | Upstream client implementation |
| Retry | Exponential backoff, HTTP 429/503 Retry-After, protocol Unavailable | Upstream implementation |
| Stop | Disable tracer recording and gate three exporters | Same effect for cached and new tracers |
| Resume | Re-enable through SDK configurator | Restore pre-control configurator, preserving local scope restrictions |
| Control scope | Instance, service and all; any matching stop remains effective | Server unchanged; all three scopes and overlapping resume tested |
| Restart | New UID; service/global rules remain, old instance rule does not transfer | New opaque 16-byte UID per JVM |
| Management auth | Existing `X-User-Token`/`X-User-Name`/`X-Cluster` | Server unchanged; never copied into probe settings |

Other EDOT features (sampling-rate control, inferred spans, selective
instrumentation, log-level changes, profiling) are outside this module. No new
server API, table, token or policy model is introduced.

## Deliberate compatibility and robustness differences

- UID generation uses Java 6 `UUID.randomUUID()` rather than a Java 8 UUIDv7
  dependency; OpAMP accepts opaque 16-byte IDs, and n9e does not inspect UUID version.
- Restore the original SDK tracer configurator instead of replacing local scope
  rules with an unconditional enabled configurator. The SDK currently needs a
  one-time reflective read because it has no getter.
- Unlike Wire setters, protobuf setters reject null. Optional appenders explicitly
  omit null values; field numbers and enum values remain protocol-compatible.
- On transport `IOException`, also notify the upstream request-failure path so
  the previous request recipe (especially ACK) is retained. Preserve scheduled
  polling after unexpected request-construction errors.
- Reject mismatched response UIDs. Cap HTTP response bytes at 128 KiB and config
  JSON at 64 KiB; reject duplicate recognized fields and trailing JSON. Reject zero/negative or
  nanosecond-overflow polling intervals by retaining the previous interval.
- Saturate exponential retry arithmetic instead of overflowing into a negative
  scheduling delay. These bounds do not change n9e's fixed 5-second config.
- Close is idempotent, cancels the scheduled poll, attempts final disconnect with
  a bounded wait, and releases the module's HTTP resources.
- Initialize the OpAMP manager from the agent listener after SDK construction.
  An official EDOT comparison run exposed an early GlobalOpenTelemetry.set race;
  the port does not move configuration application back into SDK initialization.
- HTTPS behavior depends on the actual JVM's enabled protocols/ciphers. Java 6
  HTTPS interoperability is not claimed by the HTTP regression matrix.

## Verification

`ConfigCompatibilityTest` checks copied endpoint/service/environment semantics,
legacy keys, aliases, default resets, partial values and parser boundaries.
`ProtocolCompatibilityTest` directly drives the backported upstream state machine
for capabilities, sequence, compression, full-state requests, failed ACK retries,
identity reassignment, disconnect and retry delays.

The Go harness extracts committed n9e-plus sources with `git show`; local
uncommitted server files can never enter the test. It runs actual agent JVMs and
checks three scopes, overlapping rule removal, no Authorization, continued
business traffic, three signal exports, cached/new tracer recording, dropped
ACK, HTTP outage, malformed config, HTTP 429 Retry-After and full-state reporting.
The invalid-config proxy preserves the real server's ACK persistence and only
changes the response, matching status compression semantics.

The relevant message field numbers were also compared with the OpAMP v0.14.0
schema used by the EDOT client: AgentToServer, ServerToAgent, AgentDescription,
AgentRemoteConfig, AgentConfigMap, RemoteConfigStatus, AgentIdentification,
AgentDisconnect, ServerErrorResponse and RetryInfo retain the same field numbers.
This is a structural check in addition to the real EDOT differential run, not a
claim of support for every operation in newer OpAMP schemas.
