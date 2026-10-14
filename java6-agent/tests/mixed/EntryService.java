package mixed;
import com.alibaba.dubbo.common.URL;
import com.alibaba.dubbo.common.extension.ExtensionLoader;
import com.alibaba.dubbo.rpc.Protocol;
import com.alibaba.dubbo.rpc.ProxyFactory;
import java.util.concurrent.*;
import org.apache.catalina.Context;
import org.apache.catalina.startup.Tomcat;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.context.support.GenericWebApplicationContext;
import org.springframework.web.servlet.DispatcherServlet;
import org.springframework.web.servlet.mvc.method.annotation.*;

public final class EntryService {
  static QueryService service;
  static final ThreadPoolExecutor pool=(ThreadPoolExecutor)Executors.newFixedThreadPool(2);
  @Controller public static class Routes {
    @RequestMapping("/health") @ResponseBody public String health(){return "ready";}
    @RequestMapping("/call/{mode}") @ResponseBody public String call(@PathVariable("mode") String mode) throws Exception {
      int answer;
      if("async".equals(mode))answer=pool.submit(new Callable<Integer>(){public Integer call(){return service.query();}}).get(60,TimeUnit.SECONDS);
      else answer=service.query();
      return Integer.toString(answer);
    }
  }
  public static void main(String[] args) throws Exception {
    System.out.println("RUNTIME "+System.getProperty("java.runtime.version"));pool.prestartAllCoreThreads();
    final Protocol p=ExtensionLoader.getExtensionLoader(Protocol.class).getExtension("dubbo");
    ProxyFactory f=ExtensionLoader.getExtensionLoader(ProxyFactory.class).getAdaptiveExtension();
    service=f.getProxy(p.refer(QueryService.class,URL.valueOf("dubbo://"+System.getenv("DUBBO_HOST")+":20880/mixed.QueryService?client=netty&timeout=60000&serialization=hessian2")));
    Runtime.getRuntime().addShutdownHook(new Thread(new Runnable(){public void run(){pool.shutdownNow();p.destroy();}}));
    Tomcat t=new Tomcat();t.setPort(8080);t.setBaseDir("/tmp/mixed-entry");Context c=t.addContext("","/tmp");
    GenericWebApplicationContext s=new GenericWebApplicationContext();
    s.registerBeanDefinition("routes",new RootBeanDefinition(Routes.class));
    s.registerBeanDefinition("mapping",new RootBeanDefinition(RequestMappingHandlerMapping.class));
    s.registerBeanDefinition("adapter",new RootBeanDefinition(RequestMappingHandlerAdapter.class));
    Tomcat.addServlet(c,"spring",new DispatcherServlet(s)).setLoadOnStartup(1);c.addServletMapping("/","spring");
    t.start();t.getServer().await();
  }
}
