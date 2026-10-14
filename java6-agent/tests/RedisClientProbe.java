import redis.clients.jedis.Jedis;
import redis.clients.jedis.Pipeline;
import redis.clients.jedis.Response;
import redis.clients.jedis.exceptions.JedisDataException;
import java.util.UUID;
/** Business-style Redis operations without tracing APIs. */
public final class RedisClientProbe {
  public static void main(String[] args) throws Exception {
    Jedis jedis = new Jedis("java6-redis-db", 6379);
    String key = "official-probe:" + UUID.randomUUID().toString();
    try {
      jedis.select(2);
      jedis.set(key, "private-value-93217");
      if (!"private-value-93217".equals(jedis.get(key))) throw new AssertionError();
      try { jedis.lpush(key, "x"); throw new AssertionError("Expected WRONGTYPE"); }
      catch (JedisDataException expected) {}
      Pipeline pipeline = jedis.pipelined();
      Response<String> response = pipeline.get(key);
      pipeline.ping();
      pipeline.sync();
      if (!"private-value-93217".equals(response.get())) throw new AssertionError();
    } finally { jedis.del(key); jedis.close(); }
    System.out.println("REDIS_PROBE_OK");
  }
}
