/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package io.opentelemetry.javaagent.bootstrap;
import java.io.InputStream;
import java.util.Properties;
/** Read-only single-JAR identification; does not install instrumentation. */
public final class DistributionInfo {
  public static void main(String[] args) throws Exception {
    Properties info=new Properties();
    InputStream in=DistributionInfo.class.getResourceAsStream("/META-INF/flashcat-agent.properties");
    if(in==null) throw new IllegalStateException("Missing distribution metadata");
    try {info.load(in);} finally {in.close();}
    System.out.println("Flashcat Java Agent "+info.getProperty("version"));
    System.out.println("Source SHA256: "+info.getProperty("source.sha256"));
    System.out.println("Runtime: "+System.getProperty("java.version"));
    System.out.println("Transport: OTLP http/protobuf; official SDK autoconfigure; status: pre-release");
    System.out.println("Usage: java -javaagent:flashcat-javaagent.jar -jar application.jar");
  }
}
