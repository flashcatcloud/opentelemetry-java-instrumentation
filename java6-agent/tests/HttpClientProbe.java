/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
import java.net.*;
import java.io.*;
/** Tests instrumentation against real HTTP responses without using OTel APIs. */
public final class HttpClientProbe {
  public static void main(String[] args) throws Exception {
    for(String path:new String[]{"/ok","/missing","/failure"}) {
      HttpURLConnection c=(HttpURLConnection)new URL(args[0]+path).openConnection();
      c.setConnectTimeout(1000);c.setReadTimeout(2000);
      try {c.getInputStream().close();if(!path.equals("/ok")) throw new AssertionError("expected HTTP failure");}
      catch(IOException e) {if(path.equals("/ok")) throw e;}
      finally {c.disconnect();}
    }
    HttpURLConnection c=(HttpURLConnection)new URL("http://127.0.0.1:1/unreachable").openConnection();
    c.setConnectTimeout(1000);
    try {c.getInputStream();throw new AssertionError("expected connection failure");}
    catch(IOException expected) {} finally {c.disconnect();}
    System.out.println("HTTP_PROBE_OK");
  }
}
