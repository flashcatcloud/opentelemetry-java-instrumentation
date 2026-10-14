import java.sql.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.producer.*;
import org.apache.kafka.clients.consumer.*;
import org.apache.kafka.common.TopicPartition;

/** Business-only messaging and database fixture; no telemetry APIs. */
public final class KafkaClientProbe {
  public static void main(String[] args) throws Exception {
    Class.forName("com.mysql.jdbc.Driver");
    String topic=System.getenv("KAFKA_TOPIC");
    Properties properties=new Properties();
    properties.put("bootstrap.servers","official-javaagent-kafka:9092");
    properties.put("key.serializer","org.apache.kafka.common.serialization.StringSerializer");
    properties.put("value.serializer","org.apache.kafka.common.serialization.StringSerializer");
    properties.put("acks","all");
    KafkaProducer<String,String> producer=new KafkaProducer<String,String>(properties);
    try {
      for(int i=0;i<3;i++)producer.send(new ProducerRecord<String,String>(topic,0,"key"+i,"message"+i)).get(30,TimeUnit.SECONDS);
    } finally {producer.close();}
    properties=new Properties();
    properties.put("bootstrap.servers","official-javaagent-kafka:9092");
    properties.put("group.id","probe-"+UUID.randomUUID());
    properties.put("key.deserializer","org.apache.kafka.common.serialization.StringDeserializer");
    properties.put("value.deserializer","org.apache.kafka.common.serialization.StringDeserializer");
    properties.put("enable.auto.commit","false");
    KafkaConsumer<String,String> consumer=new KafkaConsumer<String,String>(properties);
    final Set<String> received=new HashSet<String>();
    final boolean callbackError=args.length>0;
    boolean expectedError=false;
    try {
      List<TopicPartition> partitions=Collections.singletonList(new TopicPartition(topic,0));
      consumer.assign(partitions);consumer.seekToBeginning(partitions);
      long deadline=System.currentTimeMillis()+30000;
      while(received.size()<3 && System.currentTimeMillis()<deadline){
        @SuppressWarnings("unchecked")
        ConsumerRecords<String,String> records=Boolean.getBoolean("probe.duration.poll")
            ? (ConsumerRecords<String,String>)KafkaConsumer.class.getMethod("poll",java.time.Duration.class)
                .invoke(consumer,java.time.Duration.ofMillis(1000))
            : consumer.poll(1000);
        if(callbackError){
          try {java.util.function.Consumer<ConsumerRecord<String,String>> action=new java.util.function.Consumer<ConsumerRecord<String,String>>() {
            public void accept(ConsumerRecord<String,String> record) {
              try {process(record,received);} catch(Exception error) {throw new IllegalStateException(error);}
              if("message2".equals(record.value()))throw new IllegalStateException("expected-kafka-callback-error");
            }
          };
          if("iterable-error".equals(args[0]))records.forEach(action);
          else records.iterator().forEachRemaining(action);
          } catch(IllegalStateException error) {
            if(!"expected-kafka-callback-error".equals(error.getMessage()))throw error;
            expectedError=true;
          }
        } else {for(ConsumerRecord<String,String> record:records)process(record,received);}

      }
      if(callbackError && !expectedError)throw new AssertionError("missing callback error");
      if(received.size()!=3)throw new AssertionError("missing messages: "+received);
    } finally {consumer.close();}
    System.out.println("KAFKA_PROBE_OK");
  }
  private static void process(ConsumerRecord<String,String> record,Set<String> received) throws Exception {
    if(!received.add(record.value()))throw new AssertionError("duplicate delivery");
    Connection connection=DriverManager.getConnection(System.getenv("JDBC_URL"),System.getenv("JDBC_USER"),System.getenv("JDBC_PASSWORD"));
    try {Statement statement=connection.createStatement();try {ResultSet result=statement.executeQuery("SELECT 42 FROM dual");try {if(!result.next()||result.getInt(1)!=42)throw new AssertionError();}finally{result.close();}}finally{statement.close();}}finally{connection.close();}
  }
}
