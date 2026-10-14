import com.rabbitmq.client.*;
import java.io.IOException;
import java.sql.*;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
/** Business fixture: publish messages, consume them and query MySQL without telemetry APIs. */
public final class RabbitClientProbe {
  public static void main(String[] args) throws Exception {
    Class.forName("com.mysql.jdbc.Driver");
    ConnectionFactory factory=new ConnectionFactory();factory.setHost(System.getenv("RABBIT_HOST"));
    factory.setUsername("poc");factory.setPassword("poc-test-only");
    com.rabbitmq.client.Connection connection=factory.newConnection();
    final Channel consumer=connection.createChannel();Channel producer=connection.createChannel();
    String queue="otel-probe-"+UUID.randomUUID();
    final CountDownLatch completed=new CountDownLatch(3);final AtomicReference<Throwable> failure=new AtomicReference<Throwable>();
    try {
      consumer.queueDeclare(queue,false,true,true,null);
      consumer.basicConsume(queue,true,new DefaultConsumer(consumer){
        public void handleDelivery(String tag,Envelope envelope,AMQP.BasicProperties properties,byte[] body) throws IOException {
          try {
            if("fail".equals(new String(body,"UTF-8")))throw new IOException("expected-consumer-error");
            java.sql.Connection c=DriverManager.getConnection(System.getenv("JDBC_URL"),System.getenv("JDBC_USER"),System.getenv("JDBC_PASSWORD"));
            try {Statement statement=c.createStatement();try {ResultSet result=statement.executeQuery("SELECT 42 FROM dual");try {if(!result.next()||result.getInt(1)!=42)throw new AssertionError();}finally{result.close();}}finally{statement.close();}}finally{c.close();}
          } catch(IOException expected){throw expected;} catch(Throwable error){failure.set(error);throw new IOException(error.toString());}
          finally{completed.countDown();}
        }
      });
      for(String body:new String[]{"one","fail","two"})producer.basicPublish("",queue,null,body.getBytes("UTF-8"));
      if(!completed.await(30,TimeUnit.SECONDS))throw new AssertionError("delivery timeout");
      if(failure.get()!=null)throw new AssertionError(failure.get());
      Thread.sleep(200);
    } finally {if(producer.isOpen())producer.close();if(consumer.isOpen())consumer.close();if(connection.isOpen())connection.close();}
    System.out.println("RABBIT_PROBE_OK");
  }
}
