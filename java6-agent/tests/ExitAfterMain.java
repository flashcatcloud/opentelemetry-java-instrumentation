import java.lang.reflect.InvocationTargetException;
import java.util.Arrays;

/** Test process lifecycle only: preserve the unchanged fixture and run JVM shutdown hooks. */
public final class ExitAfterMain {
  public static void main(String[] args) throws Throwable {
    try {
      Class.forName(args[0]).getMethod("main", String[].class)
          .invoke(null, (Object) Arrays.copyOfRange(args, 1, args.length));
    } catch (InvocationTargetException failure) {
      failure.getCause().printStackTrace();
      System.exit(1);
      return;
    }
    System.exit(0);
  }
}
