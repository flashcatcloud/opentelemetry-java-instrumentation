import java.io.*;
import java.net.*;
import java.lang.reflect.*;
import java.util.*;
import java.util.concurrent.*;
public class SenderBlockedWriteProbe {
 public static void main(String[] args) throws Exception {
  final ServerSocket server=new ServerSocket(0); server.setReceiveBufferSize(1024);
  final List<Socket> sockets=Collections.synchronizedList(new ArrayList<Socket>());
  Thread accept=new Thread(new Runnable(){public void run(){try{while(true)sockets.add(server.accept());}catch(IOException end){}}});accept.setDaemon(true);accept.start();
  final ClassLoader loader=(ClassLoader)Class.forName("io.opentelemetry.javaagent.bootstrap.AgentInitializer").getMethod("getExtensionsClassLoader").invoke(null);
  final boolean official=Boolean.parseBoolean(System.getProperty("probe.official", "true"));
  final String sdk="io.opentelemetry.";
  Class<?> cfg=Class.forName(sdk+"sdk.common.export.HttpSenderConfig",true,loader);
  final URI uri=new URI("http://127.0.0.1:"+server.getLocalPort()+"/v1/traces");
  Object config=java.lang.reflect.Proxy.newProxyInstance(loader,new Class[]{cfg},new InvocationHandler(){public Object invoke(Object p,Method m,Object[] a)throws Throwable{
   String n=m.getName(); if(n.equals("getEndpoint"))return uri; if(n.equals("getContentType"))return "application/x-protobuf";
   if(n.equals("getTimeout")||n.equals("getConnectTimeout"))return m.getReturnType().getMethod("ofMillis",long.class).invoke(null,Long.valueOf(3000));
   if(n.equals("getMaxResponseBodySize"))return Long.valueOf(4096);
   if(n.equals("getHeadersSupplier"))return java.lang.reflect.Proxy.newProxyInstance(loader,new Class[]{m.getReturnType()},new InvocationHandler(){public Object invoke(Object p,Method m,Object[] a){return Collections.emptyMap();}});
   return null;
  }});
  Class<?> provider=Class.forName(official?sdk+"exporter.sender.okhttp.internal.OkHttpHttpSenderProvider":"io.opentelemetry.javaagent.tooling.Java6HttpSenderProvider",true,loader);
  Object sender=provider.getMethod("createSender",cfg).invoke(provider.newInstance(),config);
  Class<?> api=Class.forName(sdk+"sdk.common.export.HttpSender",true,loader);
  Method send=null;for(Method m:api.getMethods())if(m.getName().equals("send"))send=m;
  final CountDownLatch callbacks=new CountDownLatch(4);
  Class<?>[] params=send.getParameterTypes();
  Object writer=java.lang.reflect.Proxy.newProxyInstance(loader,new Class[]{params[0]},new InvocationHandler(){public Object invoke(Object p,Method m,Object[] a)throws Throwable{
   if(m.getName().equals("getContentLength"))return Integer.valueOf(16*1024*1024);
   if(m.getName().equals("writeMessage")){byte[] b=new byte[65536];for(int i=0;i<256;i++)((OutputStream)a[0]).write(b);}return null;
  }});
  Object callback=java.lang.reflect.Proxy.newProxyInstance(loader,new Class[]{params[1]},new InvocationHandler(){public Object invoke(Object p,Method m,Object[] a){if(m.getName().equals("accept")){if(a[0] instanceof Throwable)System.out.println("CALLBACK "+a[0]);callbacks.countDown();}return null;}});
  try {
   for(int i=0;i<4;i++)send.invoke(sender,writer,callback,callback);
   if(!callbacks.await(10,TimeUnit.SECONDS))throw new AssertionError("timeout callbacks missing");
   Thread.sleep(1000);
   if(sockets.isEmpty())throw new AssertionError("probe never established a network connection");
   ThreadPoolExecutor worker;
   if(official){Field f=sender.getClass().getDeclaredField("client");f.setAccessible(true);Object client=f.get(sender);Object dispatcher=client.getClass().getMethod("dispatcher").invoke(client);worker=(ThreadPoolExecutor)dispatcher.getClass().getMethod("executorService").invoke(dispatcher);}
   else {Field f=sender.getClass().getDeclaredField("worker");f.setAccessible(true);worker=(ThreadPoolExecutor)f.get(sender);}
   System.out.println("AFTER_DEADLINE active="+worker.getActiveCount()+" queued="+worker.getQueue().size()+" sockets="+sockets.size());
   api.getMethod("shutdown").invoke(sender);Thread.sleep(500);
   System.out.println("AFTER_SHUTDOWN terminated="+worker.isTerminated()+" active="+worker.getActiveCount());
   if(!worker.isTerminated()){for(Map.Entry<Thread,StackTraceElement[]> entry:Thread.getAllStackTraces().entrySet())if(entry.getKey().getName().startsWith("otel-java6-http")){System.out.println("THREAD "+entry.getKey());for(StackTraceElement frame:entry.getValue())System.out.println("  "+frame);}throw new AssertionError("sender worker survives deadline and shutdown");}
  }finally{server.close();synchronized(sockets){for(Socket s:sockets)s.close();}}
 }
}
