package example;

import com.alibaba.dubbo.common.URL;
import com.alibaba.dubbo.common.extension.ExtensionLoader;
import com.alibaba.dubbo.rpc.*;
import java.io.IOException;
import java.sql.*;
import javax.servlet.http.*;
import org.apache.catalina.startup.Tomcat;
import org.apache.catalina.Context;

/** Business fixture: no OTel imports, tracing calls or agent-specific configuration. */
public class DubboApp {
  public static final class QueryServiceImpl implements QueryService {
    public int slow() {
      try { Thread.sleep(1500); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
      return 42;
    }
    public int query(boolean fail) {
      if (fail) throw new IllegalStateException("expected-dubbo-business-error");
      try {
        Connection c = DriverManager.getConnection(System.getenv("JDBC_URL"),
            System.getenv("JDBC_USER"), System.getenv("JDBC_PASSWORD"));
        try {
          PreparedStatement s = c.prepareStatement("SELECT answer FROM comparison_item WHERE id = ?");
          try {
            s.setInt(1, 1);
            ResultSet rs = s.executeQuery();
            try { if (!rs.next()) throw new IllegalStateException("no answer"); return rs.getInt(1); }
            finally { rs.close(); }
          } finally { s.close(); }
        } finally { c.close(); }
      } catch (SQLException e) { throw new IllegalStateException(e); }
    }
  }
  public static void main(String[] args) throws Exception {
    final boolean provider = "provider".equals(args[0]);
    System.out.println("RUNTIME " + System.getProperty("java.runtime.version"));
    Class.forName("com.mysql.jdbc.Driver");
    final Protocol protocol = ExtensionLoader.getExtensionLoader(Protocol.class).getExtension("dubbo");
    ProxyFactory factory = ExtensionLoader.getExtensionLoader(ProxyFactory.class).getAdaptiveExtension();
    String host = provider ? "0.0.0.0" : System.getenv("DUBBO_HOST");
    URL url = URL.valueOf("dubbo://" + host + ":20880/example.QueryService?server=netty&client=netty&threads=4&timeout=10000&serialization=hessian2&slow.timeout=200");
    final QueryService service;
    if (provider) {
      protocol.export(factory.getInvoker(new QueryServiceImpl(), QueryService.class, url));
      service = null;
    } else {
      service = factory.getProxy(protocol.refer(QueryService.class, url));
    }
    Runtime.getRuntime().addShutdownHook(new Thread(new Runnable() {
      public void run() { protocol.destroy(); }
    }));
    Tomcat server = new Tomcat();server.setPort(8080);server.setBaseDir("/tmp/dubbo-tomcat");
    Context context = server.addContext("", "/tmp");
    Tomcat.addServlet(context, "app", new HttpServlet() {
      protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        resp.setContentType("text/plain");
        if ("/health".equals(req.getRequestURI())) { resp.getWriter().println("ready");return; }
        if (provider) { resp.sendError(404);return; }
        try { resp.getWriter().println("Dubbo JDBC answer=" + ("true".equals(req.getParameter("slow")) ? service.slow() : service.query("true".equals(req.getParameter("fail"))))); }
        catch (RuntimeException e) { resp.setStatus(500);resp.getWriter().println(e.getMessage()); }
      }
    });
    context.addServletMapping("/*", "app");
    server.start();server.getServer().await();
  }
}
