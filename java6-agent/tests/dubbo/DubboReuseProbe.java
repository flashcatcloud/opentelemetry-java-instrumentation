package example;

import com.alibaba.dubbo.common.URL;
import com.alibaba.dubbo.common.extension.ExtensionLoader;
import com.alibaba.dubbo.rpc.*;
import java.util.*;
import java.util.concurrent.*;

/** Checks application-owned attachments and reuse after business failure; no OTel API. */
public class DubboReuseProbe {
  public static void main(String[] args) throws Exception {
    final Protocol protocol = ExtensionLoader.getExtensionLoader(Protocol.class).getExtension("dubbo");
    URL url = URL.valueOf("dubbo://java6-dubbo-b:20880/example.QueryService?client=netty&timeout=10000&serialization=hessian2");
    final Invoker<QueryService> invoker = protocol.refer(QueryService.class, url);
    final Map<String,String> saved = new HashMap<String,String>();
    saved.put("traceparent", "00-11111111111111111111111111111111-2222222222222222-01");
    saved.put("tracestate", "stale=value");saved.put("baggage", "stale=value");saved.put("business", "preserve");
    final RpcInvocation invocation = new RpcInvocation("query", new Class<?>[]{Boolean.TYPE},
        new Object[]{Boolean.FALSE}, new HashMap<String,String>(saved));
    ExecutorService executor = Executors.newSingleThreadExecutor();
    try {
      for (int i=0;i<3;i++) {
        final boolean fail=i==1;
        executor.submit(new Callable<Void>() {
          public Void call() throws Exception {
            invocation.setArguments(new Object[]{Boolean.valueOf(fail)});
            Result result=invoker.invoke(invocation);
            if (result.hasException()!=fail) throw new AssertionError("result changed");
            if (!fail && !Integer.valueOf(42).equals(result.getValue())) throw new AssertionError("answer changed");
            for (Map.Entry<String,String> entry:saved.entrySet()) {
              if (!entry.getValue().equals(invocation.getAttachment(entry.getKey()))) throw new AssertionError("attachment changed: "+entry.getKey());
            }
            return null;
          }
        }).get();
      }
      System.out.println("DUBBO_REUSE_OK");
    } finally { executor.shutdown();invoker.destroy();protocol.destroy(); }
  }
}
