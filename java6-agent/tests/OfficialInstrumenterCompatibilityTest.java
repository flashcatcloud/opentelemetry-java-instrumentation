/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
import io.opentelemetry.api.trace.*;
import io.opentelemetry.context.*;
import io.opentelemetry.context.propagation.*;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.instrumentation.api.instrumenter.*;
import io.opentelemetry.instrumentation.api.incubator.semconv.db.*;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.export.*;
import io.opentelemetry.sdk.common.CompletableResultCode;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;

/** Tests the upstream Instrumenter, not agent bytecode transformation. */
public final class OfficialInstrumenterCompatibilityTest {
  static void check(boolean value, String message) {
    if (!value) throw new AssertionError(message);
  }
  public static void main(String[] args) throws Exception {
    final List<SpanData> spans = Collections.synchronizedList(new ArrayList<SpanData>());
    SdkTracerProvider provider = SdkTracerProvider.builder().addSpanProcessor(
        SimpleSpanProcessor.create(new SpanExporter() {
          public CompletableResultCode export(Collection<SpanData> batch) {
            spans.addAll(batch); return CompletableResultCode.ofSuccess();
          }
          public CompletableResultCode flush() { return CompletableResultCode.ofSuccess(); }
          public CompletableResultCode shutdown() { return CompletableResultCode.ofSuccess(); }
        })).build();
    OpenTelemetrySdk sdk = OpenTelemetrySdk.builder().setTracerProvider(provider)
        .setPropagators(ContextPropagators.create(W3CTraceContextPropagator.getInstance())).build();
    TextMapGetter<Map<String,String>> getter = new TextMapGetter<Map<String,String>>() {
      public Iterable<String> keys(Map<String,String> request) { return request.keySet(); }
      public String get(Map<String,String> request, String key) { return request.get(key); }
    };
    final Instrumenter<Map<String,String>,Object> server = Instrumenter
        .<Map<String,String>,Object>builder(sdk, "official-server", request -> "server")
        .buildServerInstrumenter(getter);
    final Instrumenter<Map<String,String>,Object> client = Instrumenter
        .<Map<String,String>,Object>builder(sdk, "official-client", request -> "client")
        .buildClientInstrumenter((request, key, value) -> request.put(key, value));
    String traceId = "0123456789abcdef0123456789abcdef";
    Map<String,String> incoming = new HashMap<String,String>();
    incoming.put("traceparent", "00-" + traceId + "-0123456789abcdef-01");
    Context initial = Context.current();
    check(server.shouldStart(initial, incoming), "server disabled");
    Context a = server.start(initial, incoming);
    Scope scope = a.makeCurrent();
    final Map<String,String> outgoing = new HashMap<String,String>();
    Context c = client.start(Context.current(), outgoing);
    check(outgoing.get("traceparent").contains(Span.fromContext(c).getSpanContext().getSpanId()), "missing injected parent");
    final CountDownLatch started = new CountDownLatch(1);
    final CountDownLatch finish = new CountDownLatch(1);
    final AtomicReference<Throwable> failure = new AtomicReference<Throwable>();
    Thread worker = new Thread(() -> {
      try {
        Context before = Context.current();
        Context b = server.start(Context.root(), outgoing);
        Scope workerScope = b.makeCurrent();
        started.countDown();
        check(finish.await(10, TimeUnit.SECONDS), "worker timeout");
        workerScope.close();
        server.end(b, outgoing, null, new IllegalStateException("expected failure"));
        check(Context.current() == before, "worker context leaked");
      } catch (Throwable error) { failure.set(error); started.countDown(); }
    });
    worker.start();
    check(started.await(10, TimeUnit.SECONDS), "start timeout");
    check(spans.isEmpty(), "span ended before completion");
    finish.countDown(); worker.join(15000);
    check(!worker.isAlive() && failure.get() == null, "worker failed: " + failure.get());
    client.end(c, outgoing, null, null);
    scope.close(); server.end(a, incoming, null, null);
    check(Context.current() == initial, "caller context leaked");
    check(spans.size() == 3, "span count: " + spans.size());
    SpanData b = spans.get(0), child = spans.get(1), root = spans.get(2);
    check(root.getParentSpanId().equals("0123456789abcdef"), "remote parent lost");
    check(child.getParentSpanId().equals(root.getSpanId()), "client parent lost");
    check(b.getParentSpanId().equals(child.getSpanId()), "server parent lost");
    for (SpanData span : spans) check(span.getTraceId().equals(traceId), "trace split");
    check(root.getKind() == SpanKind.SERVER && child.getKind() == SpanKind.CLIENT && b.getKind() == SpanKind.SERVER, "wrong kinds");
    check(b.getStatus().getStatusCode() == StatusCode.ERROR && b.getEvents().size() == 1, "error lost");
    SqlQuery query = SqlQueryAnalyzer.create(true).analyze("SELECT * FROM inventory WHERE id=42 AND secret='private-value'", SqlDialect.DOUBLE_QUOTES_ARE_STRING_LITERALS);
    check(!query.getQueryText().contains("private-value") && !query.getQueryText().contains("42"), "SQL sanitizer leaked values");
    check("SELECT".equals(query.getOperationName()) && "inventory".equals(query.getCollectionName()), "SQL metadata lost");
    String redis = RedisCommandSanitizer.create(true).sanitize("SET", Arrays.asList("key", "private-value"));
    check(!redis.contains("private-value"), "Redis sanitizer leaked value");
    provider.close();
    System.out.println("OFFICIAL_INSTRUMENTER_OK spans=3 propagation=ok async=ok errors=ok restored=ok sql=ok redis=ok java=" + System.getProperty("java.version"));
  }
}
