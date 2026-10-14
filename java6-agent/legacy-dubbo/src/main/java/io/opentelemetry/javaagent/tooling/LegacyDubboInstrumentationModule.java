package io.opentelemetry.javaagent.tooling;

import com.google.auto.service.AutoService;
import io.opentelemetry.javaagent.extension.instrumentation.InstrumentationModule;
import io.opentelemetry.javaagent.extension.instrumentation.TypeInstrumentation;
import io.opentelemetry.javaagent.extension.instrumentation.TypeTransformer;
import java.util.Arrays;
import java.util.List;
import net.bytebuddy.description.type.TypeDescription;
import net.bytebuddy.matcher.ElementMatcher;
import static net.bytebuddy.matcher.ElementMatchers.*;

/** Necessary com.alibaba Dubbo extension, installed through the upstream module lifecycle. */
@AutoService(InstrumentationModule.class)
public final class LegacyDubboInstrumentationModule extends InstrumentationModule {
  public LegacyDubboInstrumentationModule() {
    super("dubbo-2.5", "dubbo");
  }
  @Override
  public boolean isHelperClass(String className) {
    return className.startsWith("io.opentelemetry.instrumentation.alibabadubbo.v2_5.")
        || className.equals("io.opentelemetry.javaagent.tooling.DubboTelemetry")
        || className.startsWith("io.opentelemetry.javaagent.tooling.DubboTelemetry$")
        || className.equals("io.opentelemetry.javaagent.tooling.LegacyDubboFutureAccess")
        || className.equals("io.opentelemetry.javaagent.tooling.LegacyDubboRequestSnapshot");
  }
  public List<TypeInstrumentation> typeInstrumentations() {
    return Arrays.<TypeInstrumentation>asList(new Client(),new Server(),new Future(),new ExchangeRequest());
  }
  private static String advice(String name) {return LegacyDubboAdvice.class.getName()+"$"+name;}
  private static final class Client implements TypeInstrumentation {
    public ElementMatcher<TypeDescription> typeMatcher(){return named("com.alibaba.dubbo.rpc.protocol.dubbo.DubboInvoker");}
    public void transform(TypeTransformer transformer){
      transformer.applyAdviceToMethod(named("doInvoke").and(takesArguments(1)).and(takesArgument(0,named("com.alibaba.dubbo.rpc.Invocation"))),advice("ClientAdvice"));
    }
  }
  private static final class Server implements TypeInstrumentation {
    public ElementMatcher<TypeDescription> typeMatcher(){return named("com.alibaba.dubbo.rpc.proxy.AbstractProxyInvoker");}
    public void transform(TypeTransformer transformer){
      transformer.applyAdviceToMethod(named("invoke").and(takesArguments(1)).and(takesArgument(0,named("com.alibaba.dubbo.rpc.Invocation"))),advice("ServerAdvice"));
    }
  }
  private static final class ExchangeRequest implements TypeInstrumentation {
    public ElementMatcher<TypeDescription> typeMatcher() {
      return named("com.alibaba.dubbo.remoting.exchange.support.header.HeaderExchangeChannel");
    }
    public void transform(TypeTransformer transformer) {
      transformer.applyAdviceToMethod(named("request").and(takesArguments(Object.class, int.class)),
          advice("RequestSnapshot"));
    }
  }
  private static final class Future implements TypeInstrumentation {
    public ElementMatcher<TypeDescription> typeMatcher(){return named("com.alibaba.dubbo.remoting.exchange.support.DefaultFuture");}
    public void transform(TypeTransformer transformer){
      transformer.applyAdviceToMethod(isConstructor(),advice("FutureCreated"));
      transformer.applyAdviceToMethod(named("doReceived").and(takesArguments(1)),advice("Completed"));
      transformer.applyAdviceToMethod(named("cancel").and(takesArguments(0)),advice("Cancelled"));
      transformer.applyAdviceToMethod(named("invokeCallback").and(takesArguments(1)),advice("Callback"));
    }
  }
}
