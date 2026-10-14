import java.sql.*;
/** JDBC business fixture: no tracing APIs or changes to JDBC usage. */
public final class JdbcClientProbe {
  public static void main(String[] args) throws Exception {
    Class.forName(System.getenv("JDBC_DRIVER"));
    Connection connection = DriverManager.getConnection(System.getenv("JDBC_URL"),
        System.getenv("JDBC_USER"), System.getenv("JDBC_PASSWORD"));
    try {
      Statement statement = connection.createStatement();
      try {
        ResultSet result = statement.executeQuery("SELECT 42 FROM dual");
        try { if (!result.next() || result.getInt(1) != 42) throw new AssertionError(); }
        finally { result.close(); }
        try { statement.executeQuery("SELECT missing_column FROM dual"); throw new AssertionError(); }
        catch (SQLException expected) {}
      } finally { statement.close(); }
      PreparedStatement prepared = connection.prepareStatement("SELECT ? FROM dual");
      try {
        prepared.setInt(1, 43);
        ResultSet result = prepared.executeQuery();
        try { if (!result.next() || result.getInt(1) != 43) throw new AssertionError(); }
        finally { result.close(); }
      } finally { prepared.close(); }
    } finally { connection.close(); }
    System.out.println("JDBC_PROBE_OK");
  }
}
