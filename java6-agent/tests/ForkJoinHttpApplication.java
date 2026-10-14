import java.io.*;
import java.net.*;
import java.util.concurrent.*;
import javax.servlet.http.*;
import org.apache.catalina.Context;
import org.apache.catalina.startup.Tomcat;

/** Business-only fixture: no OpenTelemetry calls or tracing headers. */
public class ForkJoinHttpApplication {
  public static void main(String[] args) throws Exception {
    final ForkJoinPool pool=new ForkJoinPool(2);
    // Create workers before requests so inherited thread-local state cannot pass the test.
    final CountDownLatch started=new CountDownLatch(2), release=new CountDownLatch(1);
    for(int i=0;i<2;i++) pool.submit(new Runnable(){public void run(){
      started.countDown();try {release.await();} catch(InterruptedException e){Thread.currentThread().interrupt();}
    }});
    if(!started.await(10,TimeUnit.SECONDS)) throw new AssertionError("workers did not start");
    release.countDown();
    System.out.println("RUNTIME "+System.getProperty("java.runtime.version"));
    Tomcat tomcat=new Tomcat();tomcat.setPort(8080);tomcat.setBaseDir("/tmp/executor-tomcat");
    Context context=tomcat.addContext("", "/tmp");
    Tomcat.addServlet(context,"app",new HttpServlet(){
      protected void doGet(HttpServletRequest req,HttpServletResponse resp) throws IOException {
        if("/health".equals(req.getRequestURI())) {resp.getWriter().println("ready");return;}
        try {
          String result=pool.submit(new RecursiveTask<String>(){
            protected String compute() {
              RecursiveTask<String> nested=new RecursiveTask<String>() {
                protected String compute() {
                  try {
              HttpURLConnection connection=(HttpURLConnection)new URL(System.getenv("DOWNSTREAM_URL")).openConnection();
              connection.setConnectTimeout(10000);connection.setReadTimeout(10000);
              try {
                BufferedReader reader=new BufferedReader(new InputStreamReader(connection.getInputStream(),"UTF-8"));
                try {return reader.readLine();} finally {reader.close();}
              } finally {connection.disconnect();}
                  } catch(Exception e) {throw new IllegalStateException(e);}
                }
              };
              nested.fork();return nested.join();
            }
          }).get(20,TimeUnit.SECONDS);
          resp.getWriter().println("A -> "+result);
        } catch(Exception failure) {resp.sendError(500,failure.toString());}
      }
    });
    context.addServletMapping("/*","app");
    Runtime.getRuntime().addShutdownHook(new Thread(new Runnable(){public void run(){pool.shutdownNow();}}));
    tomcat.start();tomcat.getServer().await();
  }
}
