package mixed;
import com.alibaba.dubbo.common.URL;
import com.alibaba.dubbo.common.extension.ExtensionLoader;
import com.alibaba.dubbo.rpc.Protocol;
import com.alibaba.dubbo.rpc.ProxyFactory;
import redis.clients.jedis.Jedis;

public final class LegacyService {
  public static final class Implementation implements QueryService {
    public int query() {
      int answer=Business.sql();
      Jedis redis=new Jedis(System.getenv("REDIS_HOST"),6379);
      try {if(!"PONG".equals(redis.ping()))throw new IllegalStateException("redis failed");}
      finally {redis.close();}
      if(!"42".equals(Business.http(System.getenv("DOWNSTREAM_URL"))))throw new IllegalStateException("downstream failed");
      return answer;
    }
  }
  public static void main(String[] args) throws Exception {
    System.out.println("RUNTIME "+System.getProperty("java.runtime.version"));
    Class.forName("oracle.jdbc.OracleDriver");
    final Protocol p=ExtensionLoader.getExtensionLoader(Protocol.class).getExtension("dubbo");
    ProxyFactory f=ExtensionLoader.getExtensionLoader(ProxyFactory.class).getAdaptiveExtension();
    URL u=URL.valueOf("dubbo://0.0.0.0:20880/mixed.QueryService?server=netty&client=netty&threads=4&timeout=60000&serialization=hessian2");
    p.export(f.getInvoker(new Implementation(),QueryService.class,u));
    Runtime.getRuntime().addShutdownHook(new Thread(new Runnable(){public void run(){p.destroy();}}));
    Business.serve(new Business.Query(){public int query(){return 42;}});
  }
}
