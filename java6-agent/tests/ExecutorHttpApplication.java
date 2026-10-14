import java.io.*;
import java.net.*;
import java.util.concurrent.*;
import javax.servlet.http.*;
import org.apache.catalina.Context;
import org.apache.catalina.startup.Tomcat;

/** Business-only fixture: no OpenTelemetry calls or tracing headers. */
public class ExecutorHttpApplication {
  public static void main(String[] args) throws Exception {
    final ExecutorService pool=Executors.newFixedThreadPool(2);
    final ScheduledExecutorService scheduled=Executors.newScheduledThreadPool(1);
    scheduled.submit(new Runnable(){public void run(){}}).get();
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
          Callable<String> task=new Callable<String>(){
            public String call() throws Exception {
              HttpURLConnection connection=(HttpURLConnection)new URL(System.getenv("DOWNSTREAM_URL")).openConnection();
              connection.setConnectTimeout(10000);connection.setReadTimeout(10000);
              try {
                BufferedReader reader=new BufferedReader(new InputStreamReader(connection.getInputStream(),"UTF-8"));
                try {return reader.readLine();} finally {reader.close();}
              } finally {connection.disconnect();}
            }
          };
          String mode=req.getParameter("mode");
          Future<String> future;
          if("runnable".equals(mode)) {
            FutureTask<String> runnable=new FutureTask<String>(task);pool.execute(runnable);future=runnable;
          } else if("scheduled".equals(mode)) {
            future=scheduled.schedule(task,10,TimeUnit.MILLISECONDS);
          } else if("invokeAll".equals(mode)) {
            future=pool.invokeAll(java.util.Collections.singletonList(task)).get(0);
          } else {
            if("cancelled".equals(mode)) {
              FutureTask<String> cancelled=new FutureTask<String>(task);
              if(!cancelled.cancel(false)) throw new AssertionError("cancel failed");
              pool.execute(cancelled);
            }
            if("rejected".equals(mode)) {
              ExecutorService stopped=Executors.newSingleThreadExecutor();stopped.shutdown();
              try {stopped.submit(task);throw new AssertionError("rejection missing");}
              catch(RejectedExecutionException expected) {}
            }
            future=pool.submit(task);
          }
          String result=future.get(20,TimeUnit.SECONDS);
          resp.getWriter().println("A -> "+result);
        } catch(Exception failure) {resp.sendError(500,failure.toString());}
      }
    });
    context.addServletMapping("/*","app");
    Runtime.getRuntime().addShutdownHook(new Thread(new Runnable(){public void run(){pool.shutdownNow();scheduled.shutdownNow();}}));
    tomcat.start();tomcat.getServer().await();
  }
}
