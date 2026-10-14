import java.io.IOException;
import org.apache.catalina.Context;
import org.apache.catalina.startup.Tomcat;
import org.apache.http.client.methods.HttpGet;
import org.apache.http.impl.client.BasicResponseHandler;
import org.apache.http.impl.client.CloseableHttpClient;
import org.apache.http.impl.client.HttpClients;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.context.support.GenericWebApplicationContext;
import org.springframework.web.servlet.DispatcherServlet;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

/** Framework-only fixture, no tracing API calls or manually propagated headers. */
public class SpringHttpApplication {
  @Controller
  public static class Routes {
    @RequestMapping("/health") @ResponseBody
    public String health(){return "ready";}
    @RequestMapping("/call/{id}") @ResponseBody
    public String call() throws IOException {
      CloseableHttpClient client=HttpClients.createDefault();
      try {return "A -> "+client.execute(new HttpGet(System.getenv("DOWNSTREAM_URL")),new BasicResponseHandler());}
      finally {client.close();}
    }
  }
  public static void main(String[] args) throws Exception {
    System.out.println("RUNTIME "+System.getProperty("java.runtime.version"));
    Tomcat tomcat=new Tomcat();tomcat.setPort(8080);tomcat.setBaseDir("/tmp/spring-tomcat");
    Context context=tomcat.addContext("","/tmp");
    GenericWebApplicationContext spring=new GenericWebApplicationContext();
    spring.registerBeanDefinition("routes",new RootBeanDefinition(Routes.class));
    spring.registerBeanDefinition("mapping",new RootBeanDefinition(RequestMappingHandlerMapping.class));
    spring.registerBeanDefinition("adapter",new RootBeanDefinition(RequestMappingHandlerAdapter.class));
    Tomcat.addServlet(context,"spring",new DispatcherServlet(spring)).setLoadOnStartup(1);
    context.addServletMapping("/","spring");
    tomcat.start();tomcat.getServer().await();
  }
}
