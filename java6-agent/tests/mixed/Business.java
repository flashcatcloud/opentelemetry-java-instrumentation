package mixed;

import java.io.*;
import java.net.*;
import java.sql.*;
import javax.servlet.http.*;
import org.apache.catalina.Context;
import org.apache.catalina.startup.Tomcat;

/** Ordinary business operations shared by the mixed-stack acceptance fixture. */
public final class Business {
  public interface Query { int query(); }
  public static int sql() {
    try {
      Connection c=DriverManager.getConnection(System.getenv("JDBC_URL"),System.getenv("JDBC_USER"),System.getenv("JDBC_PASSWORD"));
      try {
        PreparedStatement p=c.prepareStatement("SELECT ? FROM dual");
        try {
          p.setInt(1,42);ResultSet r=p.executeQuery();
          try {if(!r.next())throw new IllegalStateException("missing answer");return r.getInt(1);}
          finally {r.close();}
        } finally {p.close();}
      } finally {c.close();}
    } catch(SQLException e) {throw new IllegalStateException(e);}
  }
  public static String http(String url) {
    try {
      HttpURLConnection c=(HttpURLConnection)new URL(url).openConnection();
      c.setConnectTimeout(5000);c.setReadTimeout(30000);
      try {
        BufferedReader r=new BufferedReader(new InputStreamReader(c.getInputStream(),"UTF-8"));
        try {return r.readLine();} finally {r.close();}
      } finally {c.disconnect();}
    } catch(IOException e) {throw new IllegalStateException(e);}
  }
  public static void serve(final Query query) throws Exception {
    Tomcat t=new Tomcat();t.setPort(8080);t.setBaseDir("/tmp/mixed-tomcat");
    Context c=t.addContext("","/tmp");
    Tomcat.addServlet(c,"business",new HttpServlet() {
      protected void doGet(HttpServletRequest req,HttpServletResponse res) throws IOException {
        if("/health".equals(req.getRequestURI())) {res.getWriter().println("ready");return;}
        try {res.getWriter().println(query.query());}
        catch(RuntimeException e) {e.printStackTrace();res.setStatus(500);res.getWriter().println("business failure");}
      }
    });
    c.addServletMapping("/*","business");t.start();t.getServer().await();
  }
}
