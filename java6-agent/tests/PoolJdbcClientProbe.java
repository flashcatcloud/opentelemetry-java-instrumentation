import java.sql.*;
/** JDBC business fixture: no tracing APIs or changes to JDBC usage. */
public final class PoolJdbcClientProbe {
  private static void set(Object pool,String method,String value) throws Exception {pool.getClass().getMethod(method,String.class).invoke(pool,value);}
  public static void main(String[] args) throws Exception {
    Class.forName(System.getenv("JDBC_DRIVER"));
    String poolClass=System.getenv("POOL_CLASS");
    Object pool=Class.forName(poolClass).newInstance();
    set(pool,"setDriverClassName",System.getenv("JDBC_DRIVER"));
    set(pool,poolClass.contains("Hikari")?"setJdbcUrl":"setUrl",System.getenv("JDBC_URL"));
    set(pool,"setUsername",System.getenv("JDBC_USER"));set(pool,"setPassword",System.getenv("JDBC_PASSWORD"));
    Connection connection=((javax.sql.DataSource)pool).getConnection();
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
    } finally { connection.close();pool.getClass().getMethod("close").invoke(pool); }
    System.out.println("JDBC_PROBE_OK");
  }
}
