"""Generate legacy namespace overlay from pinned upstream Dubbo library sources.

The transport lifecycle stays in the legacy helper; request/getters/instrumenter
assembly come from upstream. Every generated difference enters the build manifest.
"""
from pathlib import Path
import hashlib, difflib
from source_compat import adapt

def generate(root, out, manifest, patches):
    module = 'instrumentation/apache-dubbo-2.7/library-autoconfigure'
    base = root / module / 'src/main/java'
    for source in sorted(base.rglob('*.java')):
        if source.name in ('TracingFilter.java', 'OpenTelemetryClientFilter.java', 'OpenTelemetryServerFilter.java'):
            continue  # CompletableFuture lifecycle is replaced by the legacy future adapter.
        original = source.read_text()
        text = original.replace('org.apache.dubbo', 'com.alibaba.dubbo').replace(
            'apachedubbo.v2_7', 'alibabadubbo.v2_5')
        if source.name == 'DubboTelemetry.java':
            start = text.index('  /** Returns a new Dubbo client')
            text = text[:start] + """  public Instrumenter<DubboRequest, Result> clientInstrumenter() {
    return clientInstrumenter;
  }
  public Instrumenter<DubboRequest, Result> serverInstrumenter() {
    return serverInstrumenter;
  }
}
"""
            text = text.replace('import com.alibaba.dubbo.rpc.Filter;\n', '')
        if source.name == 'DubboRequest.java':
            marker = '  static DubboRequest createForUnknownService('
            factory = """  // Copy only tracing metadata, not business arguments or thread-local RpcContext.
  // Async state must not retain RpcContext's Future or the caller's mutable invocation.
  public static DubboRequest legacy(com.alibaba.dubbo.rpc.Invoker<?> invoker,
      RpcInvocation original, RpcContext context, boolean server) {
    RpcInvocation snapshot = new RpcInvocation();
    snapshot.setMethodName(original.getMethodName());
    snapshot.setInvoker(invoker);
    snapshot.setAttachments(original.getAttachments());
    return new AutoValue_DubboRequest(snapshot, null, invoker.getUrl(),
        context.getRemoteAddress(), server ? context.getLocalAddress() : null,
        DubboRegistryUtil.extractRegistryAddress(original), null);
  }

"""
            text = text.replace(marker, factory + marker)
        if source.name == 'DubboHeadersSetter.java':
            # Legacy transport owns propagation; do not retain or mutate RpcContext.
            text = text.replace('    request.context().setAttachment(key, value);\n', '')
        if source.name == 'DubboHeadersGetter.java':
            text = text.replace('import java.lang.invoke.MethodHandle;', 'import java.lang.reflect.Method;')
            text = text.replace('import java.lang.invoke.MethodHandles;\n', '').replace('import java.lang.invoke.MethodType;\n', '')
            text = text.replace('MethodHandles.Lookup lookup = MethodHandles.lookup();', '')
            text = text.replace('MethodHandle', 'Method')
            text = text.replace('lookup.findVirtual(\n              RpcInvocation.class, "getObjectAttachments", MethodType.methodType(Map.class))',
                                'RpcInvocation.class.getMethod("getObjectAttachments")')
        if source.name == 'DubboRegistryUtil.java':
            text = text.replace('import java.lang.invoke.MethodHandle;\n', '').replace('import java.lang.invoke.MethodHandles;\n', '').replace('import java.util.Optional;\n', '')
            start = text.index('  private static final MethodHandles.Lookup')
            end = text.index('  private static final ThreadLocal', start)
            text = text[:start] + text[end:]
            text = text.replace('MethodHandle mh = DIRECTORY_ACCESSOR.get(invoker.getClass()).orElse(null);',
                                'Accessor mh = resolveAccessor(invoker.getClass(), "getDirectory", "directory");')
            text = text.replace('MethodHandle getRegistry = REGISTRY_ACCESSOR.get(directory.getClass()).orElse(null);',
                                'Accessor getRegistry = resolveAccessor(directory.getClass(), "getRegistry", "registry");')
            text = text.replace('MethodHandle getUrl = URL_ACCESSOR.get(registry.getClass()).orElse(null);',
                                'Accessor getUrl = resolveAccessor(registry.getClass(), "getUrl", null);')
            start = text.index('  private static ClassValue<')
            text = text[:start] + """  // Java 6 has no ClassValue. Bound metadata to each loaded helper, with weak
  // class keys AND weak accessor values: reflection members point back to classes.
  private static final java.util.Map<Class<?>, java.lang.ref.WeakReference<java.util.Map<String, Accessor>>>
      ACCESSORS = new java.util.WeakHashMap<Class<?>, java.lang.ref.WeakReference<java.util.Map<String, Accessor>>>();

  private static synchronized Accessor resolveAccessor(Class<?> type, String method, String field) {
    java.lang.ref.WeakReference<java.util.Map<String, Accessor>> reference = ACCESSORS.get(type);
    java.util.Map<String, Accessor> values = reference == null ? null : reference.get();
    if (values == null) {
      values = new java.util.HashMap<String, Accessor>();
      ACCESSORS.put(type, new java.lang.ref.WeakReference<java.util.Map<String, Accessor>>(values));
    }
    String key = method + ":" + field;
    if (values.containsKey(key)) return values.get(key);
    Accessor value = null;
    try { value = new Accessor(type.getMethod(method), null); }
    catch (Exception ignored) { }
    if (value == null && field != null) {
      for (Class<?> current = type; current != null && current != Object.class; current = current.getSuperclass()) {
        try {
          Field member = current.getDeclaredField(field);
          member.setAccessible(true);
          value = new Accessor(null, member);
          break;
        } catch (Exception ignored) { }
      }
    }
    values.put(key, value);
    return value;
  }

  private static final class Accessor {
    private final Method method;
    private final Field field;
    Accessor(Method method, Field field) { this.method = method; this.field = field; }
    Object invoke(Object receiver) throws Exception {
      return method != null ? method.invoke(receiver) : field.get(receiver);
    }
  }
  private DubboRegistryUtil() {}
}
"""
        text = adapt(text, map_defaults=False).replace('UnaryOperator.identity()', 'java8.util.function.UnaryOperators.identity()')
        relative = Path(str(source.relative_to(base)).replace('apachedubbo/v2_7', 'alibabadubbo/v2_5'))
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        manifest.append(dict(module=module, path=str(relative), source_sha256=hashlib.sha256(original.encode()).hexdigest(), adapted=True, overlay='legacy-dubbo'))
        patches.extend(difflib.unified_diff(original.splitlines(True), text.splitlines(True), fromfile=str(source.relative_to(root)), tofile='generated/' + str(relative)))
