import java.io.Closeable;
import java.io.IOException;

/** Exercise javac-generated resource cleanup, not a direct compatibility-helper call. */
public final class SuppressedExceptionProbe {
  private static int closed;
  private static final class FailingClose implements Closeable {
    public void close() throws IOException {closed++;throw new IOException("cleanup-failure");}
  }
  public static void main(String[] args) throws Exception {
    try (Closeable resource=new FailingClose()) {
      throw new IOException("primary-failure");
    } catch(IOException primary) {
      if(!"primary-failure".equals(primary.getMessage()))throw new AssertionError(primary);
      try {
        Throwable[] suppressed=(Throwable[])Throwable.class.getMethod("getSuppressed").invoke(primary);
        if(suppressed.length!=1 || !"cleanup-failure".equals(suppressed[0].getMessage()))throw new AssertionError("lost cleanup failure");
      } catch(NoSuchMethodException expectedOnJava6) {
        if(!"1.6".equals(System.getProperty("java.specification.version")))throw expectedOnJava6;
      }
    }
    try (Closeable resource=new FailingClose()) {
      // A lone close failure must still be thrown normally.
    } catch(IOException cleanup) {
      if(!"cleanup-failure".equals(cleanup.getMessage()))throw new AssertionError(cleanup);
    }
    if(closed!=2)throw new AssertionError("resource leak");
    System.out.println("RESOURCE_CLEANUP_OK java="+System.getProperty("java.version"));
  }
}
