# Legacy Dubbo / Dubbox implementation reuse audit

## Current replacement (2026-10-14, RC3 candidate verification)

The build now generates the legacy library from the pinned official Apache Dubbo library sources through `../legacy_dubbo_overlay.py`. `../build/module-sources.json` records each original source hash and `../build/module-adaptation.patch` records every generated difference. The generated package is separate from the modern Apache module, so both can coexist.

The handwritten `Request`, RPC/network `Getter`, and client/server Instrumenter construction have been removed from the legacy lifecycle helper. It now calls the generated upstream `DubboRequest`, `DubboTelemetryBuilder`, RPC/network attribute getters, propagation helpers, official Instrumenter, RPC metrics and exception extractors. Typed helpers are injected into the application loader by the official module loader/Muzzle. The global bootstrap handler and per-call reflection dispatch have been removed; bootstrap retains only the VirtualField state holder/access interface.

Remaining deviations and reasons:

| Compatibility code | Why upstream cannot be used unchanged | Boundary |
| --- | --- | --- |
| `org.apache.dubbo` → `com.alibaba.dubbo` overlay | Alibaba/Dubbox types have a different namespace | Generated from pinned upstream; does not duplicate semantic conventions |
| Telemetry Instrumenter accessors | The upstream public entry points return modern Filter instances | Expose the upstream-built Instrumenters to the legacy lifecycle adapter |
| Legacy request snapshot factory | Async legacy RpcContext may retain its Future; hooking inside the transport needs explicit Invoker metadata | Snapshot metadata without business arguments or RpcContext; clear request after completion |
| Header setter removes RpcContext write | Legacy transport hooks run after context-to-invocation copying; the outgoing Invocation is the transport carrier | Preserve outgoing header injection/restoration and deferred-encoder snapshot; no thread-local contamination |
| Header getter uses cached Method | Java 6 lacks MethodHandle | Preserve optional object-attachment lookup/fallback |
| Registry accessor compatibility | Java 6 lacks ClassValue/MethodHandle | Reflection cache has weak class keys and weak metadata values, avoiding a strong member-to-class retention cycle; lookup failure remains best effort |
| DefaultFuture completion/cancellation/timeout adapter | Legacy versions lack `RpcContext.getCompletableFuture().whenComplete` | Reuse official Instrumenter start/end; preserve atomic completion, response-publication race handling and callback scope restoration |
| Async outgoing invocation copy | Legacy transport may encode after the caller's attachments have been restored | Copy only invocation metadata/attachments for async transport, never business arguments or serialization |

The first runtime attempt selected a Dubbox artifact compiled against Java 8 APIs and failed on Java 6 `ConcurrentHashMap.KeySetView`; use the existing Java-6-API build. The next attempt exposed a missing-context assumption in the upstream header setter: business calls succeeded but client spans were missing. It is preserved as `../build/e2e/legacy-overlay-initial-missing-context.json` and prompted the narrowly scoped setter adaptation above. Neither failure is counted as a pass.

This replacement is published as the RC3 candidate, SHA-256 `e6bfaf529d73fb0bdbbea0df7fb80357660e901ec493885e911ce5cce322601d`. Local real-JVM runs passed Dubbo 2.5.3/2.6.2 and Dubbox 2.8.4 on Oracle 6u45, Dubbox on Java 8, Dubbo 2.6.12 and upstream 3.2.15 on Java 17. Exact commands and reports are under `../build/e2e/legacy-official-reuse/`. Native 10.98.1.245 runs additionally passed Dubbox Java 8 and Dubbo 2.6.12 Java 17 nine-mode async/no-agent baselines, Java 6 VirtualField fallback and stable RPC semantics, and upstream 3.2.15 (`../build/e2e/native-legacy-reuse-rc3/`). Dedicated application-loader collection probes passed on Java 6/8/17; these do not prove all live async retention paths. The previous RC2 is unchanged. Full mixed-chain revalidation and longer application safety tests remain incomplete. Historical evidence below predates this replacement.

## Historical implementation and audit


The default is to reuse upstream implementation. Every handwritten addition must identify the exact upstream alternative examined, the concrete incompatibility, the remaining scope, and behavioral evidence. Passing tests alone does not justify duplication. This applies to future changes as well as the current implementation.

## Upstream implementation retained

The extension uses upstream InstrumentationModule discovery, Byte Buddy integration, helper injection and VirtualField. DubboTelemetry now uses upstream Instrumenter, RpcSpanNameExtractor, RpcClient/ServerAttributesExtractor, NetworkAttributesExtractor, ServerAttributesExtractor, ServicePeerAttributesExtractor, RPC metrics and exception handling. Context, propagation, SDK, sampling, autoconfiguration and export are shared with the compatible upstream Agent. The upstream Apache Dubbo 2.7/3.x module remains separate and unchanged.

This does NOT mean the upstream DubboTelemetry/TracingFilter is used verbatim for Alibaba Dubbo. The legacy module still assembles the upstream generic instrumenter with legacy request accessors. Those accessors and the assembly are handwritten and remain part of this audit.

## Handwritten inventory and justification

Paths below are relative to this directory, except the bootstrap bridge.

| Area | Upstream alternative examined | Concrete reason for current adaptation | Boundary and remaining risk |
| --- | --- | --- | --- |
| LegacyDubboInstrumentationModule and client/server advice | apache-dubbo-2.7 DubboInstrumentationModule / OpenTelemetryClientFilter / OpenTelemetryServerFilter | Upstream matches org.apache.dubbo types; these libraries expose com.alibaba.dubbo types. Current hooks target DubboInvoker.doInvoke and AbstractProxyInvoker.invoke. | Namespace adaptation is necessary; these exact hook locations are a design choice, not proven to be the minimum. A generated package/API overlay or legacy Filter adapter must still be evaluated before claiming maximum reuse. |
| DubboTelemetry.Request and Getter | Upstream DubboRequest, DubboRpcAttributesGetter, DubboClientNetworkAttributesGetter and DubboNetworkServerAttributesGetter | Upstream request/getters link org.apache types and newer APIs. Legacy values must be obtained from legacy Invocation, Invoker and RpcContext. | Only obtain source values; naming, attributes and metrics are delegated to upstream extractors. Reflection avoids application classes in the Agent loader, but is not inherently mandatory: typed injected helpers are an alternative to evaluate. No fabricated peer IP for unresolved addresses. |
| Client/server Instrumenter construction | Upstream DubboTelemetryBuilder | Upstream builder is parameterized with its own DubboRequest and org.apache Result. It cannot directly accept the legacy request adapter. | Small assembly duplication remains; generic upstream extractors/metrics/exception facilities are reused. Keep this assembly aligned with the pinned upstream builder; do not implement a parallel semantic convention. |
| Async state and DefaultFuture advice | Upstream TracingFilter uses RpcContext.getCompletableFuture().whenComplete | Legacy Future/DefaultFuture does not offer that modern completion API. Returning from doInvoke does not mean the RPC completed. | The adapter must observe response, timeout and cancellation. Response recheck handles completion before state publication; AtomicBoolean prevents duplicate completion. Late callbacks require retained context. One-way remains unsupported; do not infer coverage from two-way tests. |
| Callback context adapter | Upstream Context/Scope and Instrumenter suppression | Passing the instrumenter's entire completed RPC context into a later callback would retain in-flight RPC suppression keys and suppress a subsequent RPC. | Retain the original parent context with the completed RPC span as callback parent; restore the prior thread scope on exit. Nested/late/throwing callback tests cover this behavior. It is a legacy lifecycle adapter, not a new Context implementation. |
| LegacyDubboRequestSnapshot | Upstream modern TracingFilter and legacy HeaderExchangeChannel request flow | Existing legacy regression showed deferred encoding could read attachments after caller restoration, breaking cross-process parentage. | Copy only asynchronous RpcInvocation attachments before transport ownership. Do not rewrite serialization or business arguments. This copy/restoration strategy is a choice to review, not an upstream guarantee; one-way transport is not covered. |
| LegacyDubboFutureAccess | Upstream VirtualField | Legacy DefaultFuture needs a carrier for completion state. | Reuse official field injection/fallback, no handwritten global weak registry. Retention/classloader-GC validation remains a separate delivery gate; ordinary functional tests do not prove it. |
| ../src/bootstrap/DubboBridge.java | Upstream injected helpers and isolated Agent classloader | Current advice runs across application/bootstrap/Agent loader boundaries; the bridge exposes opaque state without linking application classes into the Agent loader. | This is architecture glue, not a protocol necessity. Evaluate consolidation into typed injected helpers; do not claim the current bridge/reflection combination is irreducible. |
| Response/error adapter in DubboTelemetry.completed | Upstream modern Result / CompletableFuture throwable completion | Legacy Response exposes numeric completion status and a wrapped RpcResult rather than the modern completion throwable API. | Interpret legacy completion and pass a Throwable to official Instrumenter.end; exception recording/status/semantic fields remain upstream-owned. Preserve tests for errors, timeout and cancellation. |

## Evidence and acceptance limits

Candidate SHA-256 256d03f0602952db4ffb256af27d60157de5a64c377ecb001336abdaf64fed74 passed:

- Oracle 6u45 and Java 8: Dubbox 2.8.4 HTTP→Dubbo→MySQL, seven seeded/concurrent traces, unsampled parent, and nine async modes with no-agent baselines.
- Oracle 6u45: stable and dual RPC semantics, error and callback propagation.
- Java 17: unchanged upstream Dubbo 3.2.15 seven-trace chain.
- Java 6/8/17: official loader and isolation probe.

Reports are in ../build/e2e/official-chain-*.json and ../build/official-loader-default-results.json; exact history and limitations are in ../MIGRATION.md. The same candidate also passed the full synchronous/nine-mode asynchronous legacy matrix: 2.5.3 and 2.6.2 on Oracle 6u45, and 2.6.12 on Java 8/17. Dubbox tests use an unmodified upstream source build, not the customer's actual binary or enterprise bridge. REST, one-way, complete retry/generic-call coverage and classloader collection are not established by these results. Dubbox async tests use the explicit-exit test launcher because the no-agent Netty timer also prevents natural process exit.

## Change review gate

For every new handwritten behavior, record: upstream source considered; exact incompatible class/method/lifecycle; why a compatibility overlay or existing helper is insufficient; affected versions/JVMs; tests including failure and cleanup paths; and whether the exception is permanent or still provisional. If there is no concrete reason, reuse upstream or remove the code. A provisional choice cannot be described as necessary merely because it works.

## Namespace-overlay compile experiment (2026-10-14)

An isolated local compile of the 15 generated upstream Apache Dubbo source files plus the upstream AutoValue_DubboRequest source, replacing only `org.apache.dubbo` with `com.alibaba.dubbo`, was checked against `dubbo-2.5.3.jar`. With the existing compatible framework dependencies and Java 8 javac, compilation exited 1 with exactly one diagnostic: `TracingFilter.java:55`, missing `RpcContext.getCompletableFuture()`. The initial attempt omitted the AutoValue generated source; those scaffold errors were corrected before recording this result.

This is evidence that a namespace overlay deserves implementation evaluation: it does not justify retaining handwritten request/getter/builder assembly solely because the upstream Java types use the Apache namespace. It is not a successful build, a Java 6 runtime test, an injection test, or proof of async compatibility. The existing published candidate was not changed. Next evaluate typed upstream helper injection and an explicit legacy future-completion adapter, then rerun propagation, deferred encoding, callback and application-safety tests before replacing the current extension.

The experiment used `javac -source 8 -target 8 -proc:none` in `eclipse-temurin:8-jdk`, limited to one CPU and 384 MiB, with the source and SDK repositories mounted read-only. Temporary sources and their input hashes are under `/tmp/dubbo-reuse-audit-qnn6aap_`; the durable source inputs remain the generated upstream module sources and AutoValue source described above. No runtime source or delivery JAR was modified.

The same namespace-only compilation was repeated against 2.6.2, 2.6.12 and the local unmodified-source Dubbox 2.8.4 dependency. All three exited 1 with the same single missing `getCompletableFuture()` diagnostic. Commands, dependency hashes and compiler output are preserved in `../build/e2e/legacy-upstream-overlay-audit/matrix.json`; the input source hashes and isolated sources are alongside it. These are Java 8 compiler checks, not claims that those dependencies all run on Java 6.

Source inspection also identified Java 7 runtime dependencies not exposed by this compiler: `DubboHeadersGetter` uses MethodHandle/MethodHandles/MethodType, and `internal/DubboRegistryUtil` uses MethodHandles plus ClassValue caches. A legacy overlay must adapt these lookups and preserve classloader unloading rather than mechanically copying them into Java 6. Registry lookup, typed helper injection, attachment restoration/deferred encoding and async completion are separate runtime acceptance requirements. This narrows the candidate compatibility work; it does not certify the current handwritten adapter as minimal or authorize calling this experiment production-ready.
