public final class ExecutorModuleDiagnostics {
 public static void main(String[] args) throws Exception {
  Class<?> init=Class.forName("io.opentelemetry.javaagent.bootstrap.AgentInitializer");
  ClassLoader loader=(ClassLoader)init.getMethod("getExtensionsClassLoader").invoke(null);
  Class<?> base=Class.forName("io.opentelemetry.javaagent.extension.instrumentation.InstrumentationModule",true,loader);
  Class<?> matcher=Class.forName("io.opentelemetry.javaagent.tooling.muzzle.ReferenceMatcher",true,loader);
  Class<?> elementMatcher=Class.forName("net.bytebuddy.matcher.ElementMatcher",true,loader);
  for(String name:new String[]{"ExecutorsInstrumentationModule","ForkJoinExecutorsInstrumentationModule"}) {
   Object module=Class.forName("io.opentelemetry.javaagent.instrumentation.executors."+name,true,loader).newInstance();
   Object check=matcher.getMethod("of",base).invoke(null,module);
   Object clMatcher=base.getMethod("classLoaderMatcher").invoke(module);
   for(ClassLoader target:new ClassLoader[]{null,ClassLoader.getSystemClassLoader()}) {
    boolean actual=((Boolean)elementMatcher.getMethod("matches",Object.class).invoke(clMatcher,target)).booleanValue();
    boolean expected=true;
    if(name.startsWith("ForkJoin")) {
      try {Class.forName("java.util.concurrent.ForkJoinTask",false,null);} catch(ClassNotFoundException absent){expected=false;}
    }
    if(actual!=expected) throw new AssertionError(name+" loader="+target+" match="+actual+" expected="+expected);
    System.out.println(name+" loader="+target+" match="+actual);
    System.out.println("MISMATCHES="+matcher.getMethod("getMismatchedReferenceSources",ClassLoader.class).invoke(check,target));
   }
  }
 }
}
