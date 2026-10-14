import io.grpc.*;
import io.grpc.stub.*;
import java.io.*;
import java.sql.*;
import java.util.concurrent.*;

/** Real gRPC transport with normal business handlers and no telemetry APIs. */
public final class GrpcClientProbe {
  private static final MethodDescriptor.Marshaller<String> STRINGS=new MethodDescriptor.Marshaller<String>() {
    public InputStream stream(String value) {
      try {return new ByteArrayInputStream(value.getBytes("UTF-8"));}catch(Exception e){throw new IllegalStateException(e);}
    }
    public String parse(InputStream input) {
      try {ByteArrayOutputStream bytes=new ByteArrayOutputStream();byte[] buffer=new byte[256];int n;while((n=input.read(buffer))!=-1)bytes.write(buffer,0,n);return new String(bytes.toByteArray(),"UTF-8");}catch(IOException e){throw new IllegalStateException(e);}
    }
  };
  public static void main(String[] args) throws Exception {
    Class.forName("com.mysql.jdbc.Driver");
    final MethodDescriptor<String,String> method=MethodDescriptor.<String,String>newBuilder().setType(MethodDescriptor.MethodType.UNARY).setFullMethodName("poc.Query/Query").setRequestMarshaller(STRINGS).setResponseMarshaller(STRINGS).build();
    Server server=ServerBuilder.forPort(0).addService(ServerServiceDefinition.builder("poc.Query").addMethod(method,ServerCalls.asyncUnaryCall(new ServerCalls.UnaryMethod<String,String>() {
      public void invoke(String request,StreamObserver<String> response) {
        if("error".equals(request)||"bad".equals(request)){response.onError(("bad".equals(request)?Status.INVALID_ARGUMENT:Status.INTERNAL).withDescription("expected-grpc-error").asRuntimeException());return;}
        try {
          if("slow".equals(request))Thread.sleep(250);
          Connection connection=DriverManager.getConnection(System.getenv("JDBC_URL"),System.getenv("JDBC_USER"),System.getenv("JDBC_PASSWORD"));
          try {Statement statement=connection.createStatement();try {ResultSet result=statement.executeQuery("SELECT 42 FROM dual");try {if(!result.next()||result.getInt(1)!=42)throw new AssertionError();}finally{result.close();}}finally{statement.close();}}finally{connection.close();}
          response.onNext("ok:"+request);response.onCompleted();
        } catch(Throwable error){response.onError(Status.INTERNAL.withCause(error).asRuntimeException());}
      }
    })).build()).build().start();
    ManagedChannelBuilder<?> builder=ManagedChannelBuilder.forAddress("127.0.0.1",server.getPort());
    try {ManagedChannelBuilder.class.getMethod("usePlaintext").invoke(builder);}catch(NoSuchMethodException old){ManagedChannelBuilder.class.getMethod("usePlaintext",boolean.class).invoke(builder,true);}
    ManagedChannel channel=builder.build();
    try {
      for(String request:new String[]{"one","two"})if(!("ok:"+request).equals(ClientCalls.blockingUnaryCall(channel,method,CallOptions.DEFAULT.withDeadlineAfter(20,TimeUnit.SECONDS),request)))throw new AssertionError();
      for(String request:new String[]{"bad","error"}){try {ClientCalls.blockingUnaryCall(channel,method,CallOptions.DEFAULT.withDeadlineAfter(20,TimeUnit.SECONDS),request);throw new AssertionError("missing error");}catch(StatusRuntimeException expected){if(expected.getStatus().getCode()!=("bad".equals(request)?Status.Code.INVALID_ARGUMENT:Status.Code.INTERNAL))throw expected;}}
      Future<String> future=ClientCalls.futureUnaryCall(channel.newCall(method,CallOptions.DEFAULT.withDeadlineAfter(20,TimeUnit.SECONDS)),"slow");
      if(!"ok:slow".equals(future.get(20,TimeUnit.SECONDS)))throw new AssertionError();
    } finally {channel.shutdownNow().awaitTermination(10,TimeUnit.SECONDS);server.shutdownNow().awaitTermination(10,TimeUnit.SECONDS);}
    System.out.println("GRPC_PROBE_OK");
  }
}
