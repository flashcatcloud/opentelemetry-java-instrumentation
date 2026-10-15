#!/bin/sh
# Rebuild the current official-module migration candidate, not the release artifact.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
sdk=${1:?Usage: build-official-candidate.sh /absolute/sdk-fork}
: "${JAVA6_HOME:?Set JAVA6_HOME to the Oracle JDK 6u45 directory}"
cd "$root"
python3 java6-agent/prepare-component-deps.py
python3 java6-agent/prepare-grpc-transport.py
python3 java6-agent/prepare-http-transport.py --sdk "$sdk"
docker run --rm --platform linux/amd64 -v "$root:/repo" -v "$sdk:/sdk" -v "$JAVA6_HOME:/jdk:ro" -e JAVA6_HOME=/jdk -w /repo eclipse-temurin:8-jdk@sha256:3a280002b0d1212a62e9f5095c10b07ef3b62c1b13916fe093438e7e9af44b8b sh java6-agent/build-http-transport.sh
python3 java6-agent/prepare.py
python3 java6-agent/prepare-dependency-overlays.py
python3 java6-agent/prepare-exporter.py --sdk "$sdk"
python3 java6-agent/prepare-framework.py --sdk "$sdk"
docker run --rm --platform linux/amd64 -v "$root:/repo" -v "$sdk:/sdk" -w /repo eclipse-temurin:8-jdk@sha256:3a280002b0d1212a62e9f5095c10b07ef3b62c1b13916fe093438e7e9af44b8b sh java6-agent/build.sh
docker run --rm -v "$root:/repo" -v "$sdk:/sdk" -w /repo eclipse-temurin:25-jdk@sha256:8c0a84ea11c8f6ed52600fc19f1040121f2a162998e9f50a5faebbbad9172dcc sh java6-agent/build-java9.sh
python3 java6-agent/prepare-instrumentation.py
docker run --rm --platform linux/amd64 -v "$root:/repo" -v "$sdk:/sdk" -w /repo eclipse-temurin:8-jdk@sha256:3a280002b0d1212a62e9f5095c10b07ef3b62c1b13916fe093438e7e9af44b8b sh java6-agent/build-instrumentation.sh
python3 java6-agent/prepare-tooling.py --sdk "$sdk"
python3 java6-agent/prepare-modules.py
for stage in build-tooling.sh build-modules.sh backport-tooling.sh; do
  docker run --rm --platform linux/amd64 -v "$root:/repo" -v "$sdk:/sdk" -w /repo eclipse-temurin:8-jdk@sha256:3a280002b0d1212a62e9f5095c10b07ef3b62c1b13916fe093438e7e9af44b8b sh "java6-agent/$stage"
done
docker run --rm -v "$root:/repo" -w /repo/java6-agent eclipse-temurin:25-jdk@sha256:8c0a84ea11c8f6ed52600fc19f1040121f2a162998e9f50a5faebbbad9172dcc javac -proc:none -cp 'build/official-deps/*:build/tooling-classes' -d build/build-tools build-tools/RelocateAgent.java build-tools/RelocateGrpcTransport.java build-tools/RelocateAgentTest.java build-tools/GenerateMuzzle.java
docker run --rm -v "$root:/repo" -w /repo/java6-agent eclipse-temurin:25-jdk@sha256:8c0a84ea11c8f6ed52600fc19f1040121f2a162998e9f50a5faebbbad9172dcc java -cp 'build/build-tools:build/official-deps/*' RelocateAgentTest
docker run --rm -v "$root:/repo" -v "$sdk:/sdk" -w /repo/java6-agent eclipse-temurin:25-jdk@sha256:8c0a84ea11c8f6ed52600fc19f1040121f2a162998e9f50a5faebbbad9172dcc java -cp 'build/build-tools:build/tooling-java6:build/official-deps/*:build/component-deps/*:/sdk/java6-compat/build/dist/*' GenerateMuzzle build/tooling-java6 \
  io.opentelemetry.javaagent.instrumentation.httpurlconnection.HttpUrlConnectionInstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.jdbc.JdbcInstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.jdbc.datasource.DataSourceInstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.internal.classloader.ClassLoaderInstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.servlet.v3_0.Servlet3InstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.tomcat.v7_0.Tomcat7InstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.jedis.v2_0.JedisInstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.jedis.v2_0.JedisClusterInstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.apachedubbo.v2_7.DubboInstrumentationModule \
  io.opentelemetry.javaagent.tooling.LegacyDubboInstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.executors.ExecutorsInstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.executors.ForkJoinExecutorsInstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.spring.webmvc.v3_1.SpringWebMvcInstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.spring.webmvc.v3_1.springweb.SpringWebInstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.apachehttpclient.v4_0.ApacheHttpClientInstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.lettuce.v5_1.LettuceInstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.rabbitmq.v2_7.RabbitMqInstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.mongo.v3_1.Mongo31InstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.mongo.v3_1.Mongo37InstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.kafkaclients.v0_11.KafkaClientsInstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.kafkaclients.v0_11.metrics.KafkaMetricsInstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.grpc.v1_6.GrpcInstrumentationModule \
  io.opentelemetry.javaagent.instrumentation.elasticsearch.rest.v7_0.ElasticsearchRest7InstrumentationModule
docker run --rm --platform linux/amd64 -v "$root:/repo" -w /repo eclipse-temurin:8-jdk@sha256:3a280002b0d1212a62e9f5095c10b07ef3b62c1b13916fe093438e7e9af44b8b sh java6-agent/build-grpc-transport.sh
python3 java6-agent/degradation/prepare.py
docker run --rm --platform linux/amd64 -v "$root:/repo" -v "$sdk:/sdk" -w /repo eclipse-temurin:8-jdk@sha256:3a280002b0d1212a62e9f5095c10b07ef3b62c1b13916fe093438e7e9af44b8b sh java6-agent/degradation/build.sh
python3 java6-agent/package-official.py --sdk "$sdk"
