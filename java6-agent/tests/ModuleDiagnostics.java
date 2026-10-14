/** Diagnostics outside the business fixture: inspect actual Muzzle and helper resources. */
public final class ModuleDiagnostics {
  public static void main(String[] args) throws Exception {
    ClassLoader app = ClassLoader.getSystemClassLoader();
    Class.forName("org.apache.dubbo.common.extension.ExtensionLoader");
    Class<?> initializer = Class.forName("io.opentelemetry.javaagent.bootstrap.AgentInitializer");
    ClassLoader agent = (ClassLoader) initializer.getMethod("getExtensionsClassLoader").invoke(null);
    Class<?> base = Class.forName("io.opentelemetry.javaagent.extension.instrumentation.InstrumentationModule", true, agent);
    Object module = Class.forName("io.opentelemetry.javaagent.instrumentation.apachedubbo.v2_7.DubboInstrumentationModule", true, agent).newInstance();
    Class<?> matcherType = Class.forName("io.opentelemetry.javaagent.tooling.muzzle.ReferenceMatcher", true, agent);
    Object matcher = matcherType.getMethod("of", base).invoke(null, module);
    System.out.println("MISMATCHES=" + matcherType.getMethod("getMismatchedReferenceSources", ClassLoader.class).invoke(matcher, app));
    java.util.Enumeration<java.net.URL> resources = app.getResources("META-INF/services/org.apache.dubbo.rpc.Filter");
    while(resources.hasMoreElements()) System.out.println("FILTER_RESOURCE="+resources.nextElement());
    System.out.println("FILTER_CLASS="+Class.forName("io.opentelemetry.javaagent.instrumentation.apachedubbo.v2_7.OpenTelemetryClientFilter", true, app));
  }
}
