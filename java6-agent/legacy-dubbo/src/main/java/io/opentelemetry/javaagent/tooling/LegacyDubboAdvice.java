package io.opentelemetry.javaagent.tooling;
import net.bytebuddy.asm.Advice;
/** Existing legacy async advice without a separate AgentBuilder installation. */
public final class LegacyDubboAdvice {
  public static class ClientAdvice {
    @Advice.OnMethodEnter(suppress = Throwable.class)
    public static Object enter(@Advice.This Object invoker, @Advice.Argument(0) Object invocation) throws Exception {
      return DubboTelemetry.INSTANCE.enter(false, invoker, invocation);
    }
    @Advice.OnMethodExit(onThrowable = Throwable.class, suppress = Throwable.class)
    public static void exit(@Advice.Enter Object state, @Advice.Return Object result,
        @Advice.Thrown Throwable error) throws Exception { DubboTelemetry.INSTANCE.exit(state, result, error); }
  }
  public static class ServerAdvice {
    @Advice.OnMethodEnter(suppress = Throwable.class)
    public static Object enter(@Advice.This Object invoker, @Advice.Argument(0) Object invocation) throws Exception {
      return DubboTelemetry.INSTANCE.enter(true, invoker, invocation);
    }
    @Advice.OnMethodExit(onThrowable = Throwable.class, suppress = Throwable.class)
    public static void exit(@Advice.Enter Object state, @Advice.Return Object result,
        @Advice.Thrown Throwable error) throws Exception { DubboTelemetry.INSTANCE.exit(state, result, error); }
  }
  public static class RequestSnapshot {
    @Advice.OnMethodEnter(suppress = Throwable.class)
    public static void enter(@Advice.Argument(value = 0, readOnly = false) Object request) {
      request = LegacyDubboRequestSnapshot.copyIfAsync(request);
    }
  }
  public static class FutureCreated {
    @Advice.OnMethodExit(suppress = Throwable.class)
    public static void exit(@Advice.This Object future) throws Exception {
      // Read response AFTER publication in the virtual field, in the helper.
      DubboTelemetry.INSTANCE.futureCreated(future, LegacyDubboFutureAccess.INSTANCE);
    }
  }
  public static class Completed {
    @Advice.OnMethodEnter(suppress = Throwable.class)
    public static void enter(@Advice.This Object future, @Advice.Argument(0) Object response) throws Exception {
      DubboTelemetry.INSTANCE.completed(future, response, false, LegacyDubboFutureAccess.INSTANCE);
    }
    @Advice.OnMethodExit(suppress = Throwable.class)
    public static void exit(@Advice.This Object future, @Advice.Argument(0) Object response) throws Exception {
      // Covers the race where construction publishes tracing state after method enter.
      DubboTelemetry.INSTANCE.completed(future, response, false, LegacyDubboFutureAccess.INSTANCE);
    }
  }
  public static class Cancelled {
    @Advice.OnMethodExit(suppress = Throwable.class)
    public static void exit(@Advice.This Object future) throws Exception {
      DubboTelemetry.INSTANCE.completed(future, null, true, LegacyDubboFutureAccess.INSTANCE);
    }
  }
  public static class Callback {
    @Advice.OnMethodEnter(suppress = Throwable.class)
    public static Object enter(@Advice.This Object future) throws Exception { return DubboTelemetry.INSTANCE.callbackEnter(future, LegacyDubboFutureAccess.INSTANCE); }
    @Advice.OnMethodExit(onThrowable = Throwable.class, suppress = Throwable.class)
    public static void exit(@Advice.Enter Object scope) { DubboTelemetry.INSTANCE.callbackExit(scope); }
  }

}
