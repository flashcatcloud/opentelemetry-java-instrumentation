/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
import java.io.*;
import java.net.*;
import java.lang.reflect.*;
import java.util.*;
import java.util.concurrent.*;
public class SenderRetryRecoveryProbe {
 public static void main(String[] args) throws Exception {
  final ServerSocket server=new ServerSocket(0);
  final java.util.concurrent.atomic.AtomicBoolean healthy=new java.util.concurrent.atomic.AtomicBoolean();
  final java.util.concurrent.atomic.AtomicInteger attempts=new java.util.concurrent.atomic.AtomicInteger();
  Thread accept=new Thread(new Runnable(){public void run(){try{while(true){Socket socket=server.accept();try{
   socket.setSoTimeout(2000);InputStream in=socket.getInputStream();ByteArrayOutputStream header=new ByteArrayOutputStream();int last=0,c;
   while((c=in.read())>=0){header.write(c);last=(last<<8)|c;if(last==0x0d0a0d0a)break;if(header.size()>8192)throw new IOException("header too large");}
   int length=0;for(String line:header.toString("US-ASCII").split("\r\n"))if(line.toLowerCase(java.util.Locale.ENGLISH).startsWith("content-length:"))length=Integer.parseInt(line.substring(15).trim());
   while(length-->0)if(in.read()<0)throw new EOFException();attempts.incrementAndGet();
   String status=healthy.get()?"200 OK":"503 Service Unavailable";
   socket.getOutputStream().write(("HTTP/1.1 "+status+"\r\nContent-Length: 0\r\nConnection: close\r\n\r\n").getBytes("US-ASCII"));
  }catch(IOException cancelled){/* A deadline may close an in-flight request. */}finally{socket.close();}}}catch(IOException end){if(!server.isClosed())throw new RuntimeException(end);}}});accept.setDaemon(true);accept.start();
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
   if(n.equals("getRetryPolicy"))return m.getReturnType().getMethod("getDefault").invoke(null);
   return null;
  }});
  Class<?> provider=Class.forName(official?sdk+"exporter.sender.okhttp.internal.OkHttpHttpSenderProvider":"io.opentelemetry.javaagent.tooling.Java6HttpSenderProvider",true,loader);
  Object sender=provider.getMethod("createSender",cfg).invoke(provider.newInstance(),config);
  Class<?> api=Class.forName(sdk+"sdk.common.export.HttpSender",true,loader);
  Method send=null;for(Method m:api.getMethods())if(m.getName().equals("send"))send=m;
  Class<?>[] params=send.getParameterTypes();
  Object writer=java.lang.reflect.Proxy.newProxyInstance(loader,new Class[]{params[0]},new InvocationHandler(){public Object invoke(Object p,Method m,Object[] a)throws Throwable{
   if(m.getName().equals("getContentLength"))return Integer.valueOf(1024);
   if(m.getName().equals("writeMessage")){((OutputStream)a[0]).write(new byte[1024]);}return null;
  }});
  ThreadPoolExecutor worker;
  ScheduledThreadPoolExecutor timer=null;
  Set<?> pending=null;
  Object dispatcher=null;
  Semaphore admissions=null;
  if(official) {
   Field field=sender.getClass().getDeclaredField("client");field.setAccessible(true);
   Object client=field.get(sender);dispatcher=client.getClass().getMethod("dispatcher").invoke(client);
   worker=(ThreadPoolExecutor)dispatcher.getClass().getMethod("executorService").invoke(dispatcher);
   Field permits=sender.getClass().getDeclaredField("admissions");permits.setAccessible(true);admissions=(Semaphore)permits.get(sender);
  } else {
   // Retain the old path only for explicit comparisons against historical RC3 artifacts.
   Field field=sender.getClass().getDeclaredField("worker");field.setAccessible(true);worker=(ThreadPoolExecutor)field.get(sender);
   Field timerField=sender.getClass().getDeclaredField("timer");timerField.setAccessible(true);timer=(ScheduledThreadPoolExecutor)timerField.get(sender);
   Field pendingField=sender.getClass().getDeclaredField("pending");pendingField.setAccessible(true);pending=(Set<?>)pendingField.get(sender);
  }
  try {
   for(int round=0;round<20;round++) {
    healthy.set(round%2==1);int before=attempts.get();
    final java.util.concurrent.atomic.AtomicInteger successes=new java.util.concurrent.atomic.AtomicInteger();
    final CountDownLatch callbacks=new CountDownLatch(8);
    final java.util.concurrent.atomic.AtomicIntegerArray counts=new java.util.concurrent.atomic.AtomicIntegerArray(8);
    final java.util.concurrent.atomic.AtomicInteger rejected=new java.util.concurrent.atomic.AtomicInteger();
    for(int i=0;i<8;i++) {
     final int index=i;
     Object callback=java.lang.reflect.Proxy.newProxyInstance(loader,new Class[]{params[1]},new InvocationHandler(){public Object invoke(Object p,Method m,Object[] a){if(m.getName().equals("accept")){counts.incrementAndGet(index);if(a[0] instanceof RejectedExecutionException)rejected.incrementAndGet();if(!(a[0] instanceof Throwable)){try{Class<?> response=Class.forName("io.opentelemetry.sdk.common.export.HttpResponse",true,loader);if(((Integer)response.getMethod("getStatusCode").invoke(a[0])).intValue()==200)successes.incrementAndGet();}catch(Exception e){throw new RuntimeException(e);}}callbacks.countDown();}return null;}});
     send.invoke(sender,writer,callback,callback);
     if(worker.getPoolSize()>(official?Math.max(Runtime.getRuntime().availableProcessors(),5):2) || worker.getQueue().size()>(official?0:64))throw new AssertionError("unbounded worker");
    }
    if(!callbacks.await(12,TimeUnit.SECONDS))throw new AssertionError("missing callbacks");
    Thread.sleep(1000);
    for(int i=0;i<8;i++)if(counts.get(i)!=1)throw new AssertionError("callback count "+counts.get(i));
    if(worker.getActiveCount()!=0 || worker.getQueue().size()!=0)throw new AssertionError("retained worker tasks");
    if(official) {
     if(admissions.availablePermits()!=5 || ((Integer)dispatcher.getClass().getMethod("queuedCallsCount").invoke(dispatcher)).intValue()!=0 || ((Integer)dispatcher.getClass().getMethod("runningCallsCount").invoke(dispatcher)).intValue()!=0)throw new AssertionError("retained dispatcher calls or admissions");
    } else if(pending.size()!=0 || timer.getQueue().size()!=0)throw new AssertionError("retained legacy timers");
    int count=attempts.get()-before;
    if(count<1 || count>8*5)throw new AssertionError("retry attempts outside bound: "+count);
    if(healthy.get() && successes.get()!=8-rejected.get())throw new AssertionError("recovery failed: "+successes.get());
    if(!healthy.get() && successes.get()!=0)throw new AssertionError("false success");
    System.out.println("RETRY_RECOVERY_ROUND_OK "+round+" callbacks=8 rejected="+rejected.get()+" active=0 queued=0");
   }
   api.getMethod("shutdown").invoke(sender);Thread.sleep(500);
   if(!worker.isTerminated() || (timer!=null && !timer.isTerminated()))throw new AssertionError("shutdown leaked threads");
   System.out.println("RETRY_RECOVERY_OK");
  }finally{api.getMethod("shutdown").invoke(sender);server.close();}
 }
}
