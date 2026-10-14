package io.opentelemetry.javaagent.tooling;
public class OracleAddressProbe {
  static void check(String url,String host,int port,String database) {
    OracleAddress a=OracleAddress.parse(url);
    if(!same(host,a.host)||port!=a.port||!same(database,a.database)) throw new AssertionError(url+" -> "+a.host+":"+a.port+"/"+a.database);
  }
  static boolean same(String a,String b){return a==null?b==null:a.equals(b);}
  public static void main(String[] args){
    check("jdbc:oracle:thin:@db.example:1522:ORCL","db.example",1522,"ORCL");
    check("jdbc:oracle:thin:@//db.example:1523/service.example","db.example",1523,"service.example");
    check("jdbc:oracle:thin:@//db.example/service.example","db.example",1521,"service.example");
    check("jdbc:oracle:thin:@(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=db.example)(PORT=1524))(CONNECT_DATA=(SERVICE_NAME=test)))","db.example",1524,"test");
    check("jdbc:oracle:thin:@(DESCRIPTION=(ADDRESS=(HOST=db.example))(CONNECT_DATA=(SID=test)))","db.example",-1,"test");
    check("jdbc:oracle:thin:@(DESCRIPTION=(ADDRESS_LIST=(ADDRESS=(HOST=db1)(PORT=1521))(ADDRESS=(HOST=db2)(PORT=1521)))(CONNECT_DATA=(SID=test)))",null,-1,"test");
    check("jdbc:oracle:thin:@TNS_ALIAS",null,-1,null);
    System.out.println("PASS Oracle address SID/service/descriptor/unknown endpoint");
  }
}
