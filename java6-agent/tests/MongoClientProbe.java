import com.mongodb.MongoClient;
import com.mongodb.MongoCommandException;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import java.util.UUID;
/** Real MongoDB business operations without tracing APIs. */
public final class MongoClientProbe {
  public static void main(String[] args) throws Exception {
    MongoClient client=new MongoClient("official-javaagent-mongo",27017);
    MongoDatabase database=client.getDatabase("otel_"+UUID.randomUUID().toString().replace("-",""));
    try {
      MongoCollection<Document> collection=database.getCollection("items");
      collection.insertOne(new Document("_id",1).append("secret","private-value-93217").append("answer",42));
      Document found=collection.find(new Document("_id",1)).first();
      if(found==null||found.getInteger("answer")!=42)throw new AssertionError();
      collection.updateOne(new Document("_id",1),new Document("$set",new Document("answer",43)));
      if(collection.find(new Document("_id",1)).first().getInteger("answer")!=43)throw new AssertionError();
      try {database.runCommand(new Document("notARealCommand",1));throw new AssertionError("expected command error");}
      catch(MongoCommandException expected) {}
    } finally {database.drop();client.close();}
    System.out.println("MONGO_PROBE_OK");
  }
}
