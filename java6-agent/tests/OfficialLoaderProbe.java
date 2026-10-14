/** Installation diagnostics only; the business fixture remains unchanged. */
public final class OfficialLoaderProbe {
  public static void main(String[] args) throws Exception {
    PlainApplication.main(args);
    Class<?> initializer = Class.forName("io.opentelemetry.javaagent.bootstrap.AgentInitializer");
    ClassLoader loader = (ClassLoader) initializer.getMethod("getExtensionsClassLoader").invoke(null);
    if (loader == null) throw new AssertionError("no official extensions loader");
    Class<?> installer = Class.forName("io.opentelemetry.javaagent.tooling.AgentInstaller", false, loader);
    java.lang.reflect.Field installed = installer.getDeclaredField("instrumentationInstalled");
    installed.setAccessible(true);
    if (!installed.getBoolean(null)) throw new AssertionError("official installer incomplete");
    Class<?> api = Class.forName("io.opentelemetry.javaagent.shaded.io.opentelemetry.api.GlobalOpenTelemetry");
    if (api.getClassLoader() != null) throw new AssertionError("API not on bootstrap");
    Class<?> sdk = Class.forName("io.opentelemetry.sdk.OpenTelemetrySdk", false, loader);
    if (sdk.getClassLoader() == null || sdk.getClassLoader() == ClassLoader.getSystemClassLoader()) throw new AssertionError("SDK not isolated");
    System.out.println("OFFICIAL_LOADER_OK installed=true bootstrap=true isolated=true java=" + System.getProperty("java.version"));
  }
}
