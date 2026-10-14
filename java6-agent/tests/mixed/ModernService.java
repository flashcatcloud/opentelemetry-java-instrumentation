package mixed;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.apache.dubbo.config.*;
import org.apache.dubbo.config.bootstrap.DubboBootstrap;
import org.apache.kafka.clients.consumer.*;
import org.apache.kafka.clients.producer.*;
import org.apache.kafka.common.TopicPartition;

public final class ModernService {
  public static final class Implementation implements QueryService {public int query(){return Business.sql();}}
  static Properties properties() {
    Properties p=new Properties();p.put("bootstrap.servers",System.getenv("KAFKA_BROKER"));return p;
  }
  public static void main(String[] args) throws Exception {
    System.out.println("RUNTIME "+System.getProperty("java.runtime.version"));
    final boolean worker="worker".equals(args[0]);
    final String topic=System.getenv("KAFKA_TOPIC");
    final DubboBootstrap b=DubboBootstrap.getInstance();b.application(new ApplicationConfig("mixed-"+args[0]));
    RegistryConfig registry=new RegistryConfig();registry.setAddress("N/A");b.registry(registry);
    if(worker) {
      Class.forName("com.mysql.jdbc.Driver");
      ProtocolConfig protocol=new ProtocolConfig();protocol.setName("dubbo");protocol.setPort(20880);
      ServiceConfig<QueryService> config=new ServiceConfig<QueryService>();config.setInterface(QueryService.class);config.setRef(new Implementation());config.setRegistry(registry);
      b.protocol(protocol).service(config).start();
      final AtomicBoolean ready=new AtomicBoolean();
      Thread consumerThread=new Thread(new Runnable(){public void run(){
        Properties p=properties();p.put("group.id","mixed-"+topic);p.put("enable.auto.commit","false");
        p.put("key.deserializer","org.apache.kafka.common.serialization.StringDeserializer");p.put("value.deserializer","org.apache.kafka.common.serialization.StringDeserializer");
        KafkaConsumer<String,String> c=new KafkaConsumer<String,String>(p);
        try {
          List<TopicPartition> partitions=Collections.singletonList(new TopicPartition(topic,0));c.assign(partitions);c.seekToBeginning(partitions);ready.set(true);
          while(!Thread.currentThread().isInterrupted())for(ConsumerRecord<String,String> r:c.poll(Duration.ofMillis(500))){
            if(Business.sql()!=42)throw new IllegalStateException("mysql answer");
            System.out.println("PROCESSED "+r.value());
          }
        }finally{ready.set(false);c.close();}
      }},"mixed-kafka-consumer");consumerThread.setDaemon(true);consumerThread.start();
      Business.serve(new Business.Query(){public int query(){if(!ready.get())throw new IllegalStateException("consumer stopped");return 42;}});
    } else {
      ReferenceConfig<QueryService> config=new ReferenceConfig<QueryService>();config.setInterface(QueryService.class);config.setUrl("dubbo://"+System.getenv("DUBBO_HOST")+":20880/mixed.QueryService?timeout=30000");
      b.reference(config).start();final QueryService service=config.get();
      Properties p=properties();p.put("key.serializer","org.apache.kafka.common.serialization.StringSerializer");p.put("value.serializer","org.apache.kafka.common.serialization.StringSerializer");p.put("acks","all");
      final KafkaProducer<String,String> producer=new KafkaProducer<String,String>(p);
      Runtime.getRuntime().addShutdownHook(new Thread(new Runnable(){public void run(){producer.close();b.destroy();}}));
      Business.serve(new Business.Query(){public int query(){
        int result=service.query();
        try {producer.send(new ProducerRecord<String,String>(topic,0,"mixed",UUID.randomUUID().toString())).get(30,TimeUnit.SECONDS);}
        catch(Exception e){throw new IllegalStateException(e);}return result;
      }});
    }
  }
}
