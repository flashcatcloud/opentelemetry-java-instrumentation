# Flashcat Java 6+ Agent compatibility branch

This branch adapts upstream instrumentation **v2.32.0** and SDK **v1.66.0** for a single Agent JAR on Oracle JDK 6u45, Java 8 and Java 17. It is a pre-release compatibility build, not a claim that the entire upstream component catalog is supported.

The implementation uses upstream AgentInstaller, InstrumentationModule discovery, Muzzle, helper injection, Instrumenter APIs, SDK autoconfiguration and OTLP protobuf export. All JVMs use this framework. Replaced handwritten HTTP/JDBC/Redis instrumentation and the prototype starter have been removed. Legacy com.alibaba Dubbo 2.5/2.6 retains the necessary extension under the official module lifecycle. The current candidate reuses the official SDK OkHttp sender beneath the HTTP exporter, with source-pinned Java 6 dependency backports and bounded admission/cancellation overlays; see `http-compat/README.md`. The previous handwritten HTTP sender has been removed. OTLP/gRPC reuses the official managed-channel sender with privately relocated Java 6-compatible transport dependencies.

## Build and verify

From this instrumentation fork, build both matching flashcatcloud forks. The SDK directory must contain the flashcatcloud `v1.66.0` **branch**, not the identically named upstream tag. SDK PR #1 is merged at `3a96a956aee3b269e85bffbd046a7784ae4bc05a`; pin that commit for this candidate. `build-all.sh` compiles the supplied SDK source directory and packages its output into the Agent; it does not automatically fetch the latest SDK. SDK changes require rebuilding and validating the Agent.

Build:

```sh
JAVA6_HOME=/absolute/path/to/jdk1.6.0_45 \
  sh java6-agent/build-all.sh /absolute/path/to/opentelemetry-java
python3 java6-agent/verify-official-loader.py \
  --sdk /absolute/path/to/opentelemetry-java \
  --jdk6 /absolute/path/to/jdk1.6.0_45
```

The current output is `java6-agent/build/official-loader-candidate.jar` from the repository root. Docker/JDKs/Python are build and verification tools, not customer runtime dependencies. The build resolves checksum-pinned dependencies, builds the matching SDK sources and compiles conditional Java 9 helpers from upstream source. Build and packaging JDK container images are pinned by digest. Candidate `bb2951f602ebf8845d49d731bc600cbfb5d7ad0876f8a369cea8f377e91ad351` passed a byte-identical source-only clean-directory rebuild of both forks; see `build/grpc-clean-build-comparison.json`. Runtime reports retain their actual tested checksum. The native matrix's original Java 6 Dubbox readiness timeout remains unexplained despite three successful complete rechecks; see MIGRATION.md. This is not a final release declaration.

```sh
java -javaagent:official-loader-candidate.jar \
  -Dotel.service.name=my-service \
  -Dotel.exporter.otlp.protocol=http/protobuf \
  -Dotel.exporter.otlp.endpoint=http://collector:4318 \
  -Dotel.metrics.exporter=otlp -Dotel.logs.exporter=none \
  -jar application.jar
```

For a plaintext OTLP/gRPC receiver, use `-Dotel.exporter.otlp.protocol=grpc`
and `-Dotel.exporter.otlp.endpoint=http://collector:4317` instead. This applies to
the new candidate, not the already published HTTP-only rc1. Core JVM JMX metrics
(memory, threads, loaded classes and CPU) have actual Java 6/8/17 export evidence;
the Collector must also route metrics. Setting `otel.metrics.exporter=none`
disables their export and is only appropriate when metrics are intentionally unwanted.
The bb2951f6 candidate has Java 8/17 evidence for trusted TLS and rejection of
untrusted or hostname-mismatched certificates. Oracle6u45 gRPC TLS is not supported
by the verified transport path; use the explicitly configured plaintext receiver
where appropriate. Retry parity and client-certificate/protocol options remain
unverified release gates; see MIGRATION.md for exact evidence and limitations.

No business tracing calls or manually propagated headers are required. The default official simple logger uses privately relocated SLF4J 1.7.36 with a small level-API compatibility overlay; application logging libraries remain separate.

## Evidence and scope

[MIGRATION.md](MIGRATION.md) records the expanded user-approved scope, actual artifact hashes, test evidence and unresolved boundaries. [DELIVERY.md](DELIVERY.md) tracks release gates. Test results under `build/e2e/` include OTLP payloads and the tested JAR checksum. Results from different candidate hashes must not be combined into a claim that one final artifact passed the entire matrix.

Validated paths during migration include Tomcat/Servlet and HttpURLConnection, Spring MVC 4.3.16 and Apache HttpClient 4.5.14, JDBC MySQL/Oracle, DBCP/Hikari query instrumentation, Jedis 2.9, Lettuce 5.1/6.1, legacy Dubbo asynchronous lifecycle, Apache Dubbo 2.7 and 3.2.15, RabbitMQ clients 2.7/3.6/5.20, MongoDB driver 3.7, Kafka clients 0.11/3.7, gRPC 1.6/1.68, and official executor propagation. Exact version × JVM results and gaps are in MIGRATION.md; this list does not imply every listed version passed every JVM or one frozen release artifact. Elasticsearch REST clients 7.17/8.17 also passed Java 8/17 during migration. Component version and JVM combinations require explicit runtime validation; Java 8+-only application libraries are not claimed to run on Java 6.

`build/dist/flashcat-javaagent.jar`, `verify.py`, `package.py` and older prototype test reports belong to the previous implementation. They are not the current delivery entry point and must not be used to certify the official-module build. Some existing continuous PoC containers still use frozen earlier artifacts. The dedicated dubbox284-java6-a/b services use the 256d03f0... candidate; do not treat other service names as evidence for that artifact.
