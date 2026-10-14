import java.util.Queue;
import java.util.Set;

/** Checks ordinary application dependencies against the Agent's private copies. */
public final class DependencyIsolationProbe {
  private static Class<?> applicationClass(String name) throws Exception {
    Class<?> type = Class.forName(name);
    if (type.getClassLoader() != ClassLoader.getSystemClassLoader()) {
      throw new AssertionError("Agent replaced application dependency: " + name);
    }
    return type;
  }
  public static void main(String[] args) throws Exception {
    Class<?> codec = applicationClass("org.apache.commons.codec.binary.Base64");
    Object encoded = codec.getMethod("encodeBase64String", byte[].class)
        .invoke(null, new Object[] {"isolation".getBytes("UTF-8")});
    if (!"aXNvbGF0aW9u".equals(encoded)) throw new AssertionError(encoded);
    Class<?> date = applicationClass("org.threeten.bp.LocalDate");
    Object value = date.getMethod("of", int.class, int.class, int.class).invoke(null, 2026, 10, 14);
    if (!"2026-10-14".equals(value.toString())) throw new AssertionError(value);
    Class<?> queueType = applicationClass("org.jctools.queues.SpscArrayQueue");
    @SuppressWarnings("unchecked")
    Queue<String> queue = (Queue<String>) queueType.getConstructor(int.class).newInstance(8);
    queue.offer("isolated");
    if (!"isolated".equals(queue.poll())) throw new AssertionError("queue");
    if (args.length > 0) {
      Class<?> zone = Class.forName(
          "io.opentelemetry.javaagent.shaded.org.threeten.bp.ZoneId", true, null);
      Set<?> zones = (Set<?>) zone.getMethod("getAvailableZoneIds").invoke(null);
      if (!zones.contains("Asia/Shanghai")) throw new AssertionError("Missing private TZDB resource");
    }
    System.out.println("DEPENDENCY_ISOLATION_OK java=" + System.getProperty("java.version"));
  }
}
