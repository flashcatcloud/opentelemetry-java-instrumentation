import java.io.*;
import java.net.*;
import java.sql.*;
import javax.servlet.http.*;
import org.apache.catalina.startup.Tomcat;
import org.apache.catalina.Context;
import redis.clients.jedis.Jedis;
import redis.clients.jedis.JedisPool;

/** Acceptance business fixture: no tracing imports, calls or headers. */
public class DatabaseApplication {
  public static void main(String[] args) throws Exception {
    final String role=args[0];
    System.out.println("RUNTIME " + System.getProperty("java.runtime.version"));
    Class.forName("oracle.jdbc.OracleDriver");
    final JedisPool pool=new JedisPool(System.getenv("REDIS_HOST"),6379);
    Tomcat server=new Tomcat(); server.setPort(8080);server.setBaseDir("/tmp/tomcat-db-"+role);
    Context context=server.addContext("","/tmp");
    Tomcat.addServlet(context,"app",new HttpServlet() {
      protected void doGet(HttpServletRequest req,HttpServletResponse resp) throws IOException {
        if("/health".equals(req.getRequestURI())) {resp.getWriter().println("ready");return;}
        String mode=req.getParameter("mode");if(mode==null) mode="normal";
        try {
          if("a".equals(role)) {
            HttpURLConnection conn=(HttpURLConnection)new URL("http://java6-db-b:8080/query?mode="+mode).openConnection();
            conn.setConnectTimeout(5000);conn.setReadTimeout(20000);
            try {BufferedReader reader=new BufferedReader(new InputStreamReader(conn.getInputStream(),"UTF-8"));
              try {resp.getWriter().println("A -> "+reader.readLine());} finally {reader.close();}
            } finally {conn.disconnect();}
            return;
          }
          int answer=42;
          if(!"redis".equals(mode)) {
            Connection c=DriverManager.getConnection(System.getenv("JDBC_URL"),"otel_poc","java6_poc_test");
            try {
              if("error".equals(mode)) {
                PreparedStatement bad=c.prepareStatement("SELECT missing_column FROM dual");
                try {try {bad.executeQuery();throw new AssertionError("expected SQL exception");} catch(SQLException expected) {}}
                finally {bad.close();}
              }
              if("statement".equals(mode)) {
                Statement st=c.createStatement();try {ResultSet rs=st.executeQuery("SELECT 42 FROM dual");try {rs.next();answer=rs.getInt(1);} finally {rs.close();}} finally {st.close();}
              } else if("batch".equals(mode)) {
                PreparedStatement ps=c.prepareStatement("UPDATE java6_item SET answer = ? WHERE id = ?");
                try {for(int i=1;i<=2;i++){ps.setInt(1,42);ps.setInt(2,i);ps.addBatch();}ps.executeBatch();} finally {ps.close();}
              } else {
                PreparedStatement ps=c.prepareStatement("SELECT ? FROM dual");
                try {ps.setInt(1,42);ResultSet rs=ps.executeQuery();try {rs.next();answer=rs.getInt(1);}finally{rs.close();}}finally{ps.close();}
              }
            } finally {c.close();}
          }
          Jedis j=pool.getResource();
          try {
            j.select(1);
            j.set("java6:poc",Integer.toString(answer));
            if("error".equals(mode)) {
              try {j.lpush("java6:poc","x");throw new AssertionError("expected WRONGTYPE");}catch(redis.clients.jedis.exceptions.JedisDataException expected) {}
            }
            if("binary".equals(mode)) j.get("java6:poc".getBytes("UTF-8"));
            if("blocking".equals(mode)) j.blpop(1,"java6:missing");
            resp.getWriter().println("Oracle="+answer+" Redis="+j.get("java6:poc"));
          } finally {j.close();}
        } catch(Exception e) {e.printStackTrace();resp.setStatus(500);resp.getWriter().println(e.toString());}
      }
    });
    context.addServletMapping("/*","app");server.start();server.getServer().await();
  }
}
