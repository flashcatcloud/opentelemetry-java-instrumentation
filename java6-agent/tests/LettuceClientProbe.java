import io.lettuce.core.RedisClient;
import io.lettuce.core.RedisCommandExecutionException;
import io.lettuce.core.RedisFuture;
import io.lettuce.core.api.StatefulRedisConnection;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
/** Tracing-free synchronous and asynchronous Redis fixture. */
public final class LettuceClientProbe {
  public static void main(String[] args) throws Exception {
    RedisClient client=RedisClient.create("redis://java6-redis-db:6379/2");
    StatefulRedisConnection<String,String> connection=client.connect();
    String key="lettuce-probe:"+UUID.randomUUID();
    try {
      connection.sync().set(key,"private-value-93217");
      if(!"private-value-93217".equals(connection.sync().get(key)))throw new AssertionError();
      try {connection.sync().lpush(key,"x");throw new AssertionError("Expected WRONGTYPE");}
      catch(RedisCommandExecutionException expected) {}
      RedisFuture<String> get=connection.async().get(key);
      RedisFuture<String> ping=connection.async().ping();
      if(!"private-value-93217".equals(get.get(10,TimeUnit.SECONDS)))throw new AssertionError();
      if(!"PONG".equals(ping.get(10,TimeUnit.SECONDS)))throw new AssertionError();
    } finally {connection.sync().del(key);connection.close();client.shutdown();}
    System.out.println("REDIS_PROBE_OK");
  }
}
