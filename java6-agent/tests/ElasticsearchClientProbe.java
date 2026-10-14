import java.util.UUID;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import org.apache.http.HttpHost;
import org.apache.http.util.EntityUtils;
import org.elasticsearch.client.*;

/** Real search/index operations without any instrumentation API. */
public final class ElasticsearchClientProbe {
  public static void main(String[] args) throws Exception {
    final String index="otel-probe-"+UUID.randomUUID();
    RestClient client=RestClient.builder(new HttpHost("official-javaagent-elasticsearch",9200,"http")).build();
    boolean created=false;
    try {
      Request create=new Request("PUT","/"+index);create.setJsonEntity("{\"settings\":{\"number_of_shards\":1,\"number_of_replicas\":0}}");client.performRequest(create);created=true;
      Request insert=new Request("PUT","/"+index+"/_doc/1");insert.addParameter("refresh","true");insert.setJsonEntity("{\"secret\":\"private-query-447\"}");client.performRequest(insert);
      Request search=new Request("POST","/"+index+"/_search");search.setJsonEntity("{\"query\":{\"match\":{\"secret\":\"private-query-447\"}}}");
      if(!EntityUtils.toString(client.performRequest(search).getEntity()).contains("private-query-447"))throw new AssertionError("missing document");
      final CountDownLatch done=new CountDownLatch(1);final AtomicReference<Throwable> failure=new AtomicReference<Throwable>();
      client.performRequestAsync(new Request("GET","/"+index+"/_doc/1"),new ResponseListener(){
        public void onSuccess(Response response){try {if(!EntityUtils.toString(response.getEntity()).contains("private-query-447"))throw new AssertionError("missing async document");}catch(Throwable error){failure.set(error);}finally{done.countDown();}}
        public void onFailure(Exception error){failure.set(error);done.countDown();}
      });
      if(!done.await(20,TimeUnit.SECONDS))throw new AssertionError("async timeout");
      if(failure.get()!=null)throw new AssertionError(failure.get());
      try {client.performRequest(new Request("GET","/"+index+"/_doc/missing"));throw new AssertionError("missing 404");}catch(ResponseException expected){if(expected.getResponse().getStatusLine().getStatusCode()!=404)throw expected;}
    } finally {try {if(created)client.performRequest(new Request("DELETE","/"+index));}finally{client.close();}}
    System.out.println("ELASTICSEARCH_PROBE_OK");
  }
}
