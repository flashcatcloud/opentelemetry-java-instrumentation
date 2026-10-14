/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
import java.io.*;
import java.lang.reflect.*;
import java.util.zip.*;
public class HttpGzipExtraProbe {
 public static void main(String[] args)throws Exception {
  ClassLoader l=(ClassLoader)Class.forName("io.opentelemetry.javaagent.bootstrap.AgentInitializer").getMethod("getExtensionsClassLoader").invoke(null);
  String p="io.opentelemetry.javaagent.transport.okio.";
  Class<?> b=Class.forName(p+"Buffer",true,l),s=Class.forName(p+"Source",true,l),g=Class.forName(p+"GzipSource",true,l);
  ByteArrayOutputStream bytes=new ByteArrayOutputStream();GZIPOutputStream gz=new GZIPOutputStream(bytes);gz.write("safe".getBytes("UTF-8"));gz.close();byte[] original=bytes.toByteArray();
  for(int size:new int[]{0,32767,32768,65535}) {
   ByteArrayOutputStream wire=new ByteArrayOutputStream();wire.write(original,0,3);wire.write(4);wire.write(original,4,6);wire.write(size&255);wire.write(size>>>8);wire.write(new byte[size]);wire.write(original,10,original.length-10);
   Object input=b.newInstance(),output=b.newInstance();b.getMethod("write",byte[].class).invoke(input,new Object[]{wire.toByteArray()});Object source=g.getConstructor(s).newInstance(input);
   try {while(((Long)g.getMethod("read",b,long.class).invoke(source,output,Long.valueOf(1024))).longValue()!=-1){}if(!"safe".equals(b.getMethod("readUtf8").invoke(output)))throw new AssertionError("payload");System.out.println("XLEN_OK "+size);}finally{g.getMethod("close").invoke(source);}
  }
  byte[] truncated=new byte[]{31,(byte)139,8,4,0,0,0,0,0,0,(byte)255,(byte)255};
  Object input=b.newInstance(),output=b.newInstance();b.getMethod("write",byte[].class).invoke(input,new Object[]{truncated});Object source=g.getConstructor(s).newInstance(input);
  try {
   try {g.getMethod("read",b,long.class).invoke(source,output,Long.valueOf(1024));throw new AssertionError("truncated extra accepted");}
   catch(InvocationTargetException error){if(!(error.getCause() instanceof IOException))throw error;System.out.println("TRUNCATED_XLEN_IO_ERROR_OK");}
  } finally {g.getMethod("close").invoke(source);}
 }
}
