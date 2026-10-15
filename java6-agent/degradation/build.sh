#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
rm -rf build/degradation-classes build/degradation-java6 build/degradation-combined build/degradation-transformed
mkdir -p build/degradation-classes build/degradation-java6
build/degradation-deps/protoc-3.3.0-linux-x86_64.exe -I degradation/proto --java_out=build/degradation-src degradation/proto/opamp/v1/anyvalue.proto degradation/proto/opamp/v1/opamp.proto
find build/degradation-src -name '*.java' > build/degradation-sources.txt
classpath="build/tooling-combined:build/http-dependencies-java6:build/bootstrap:build/degradation-deps/protobuf-java-3.3.0.jar"
for jarfile in /sdk/java6-compat/build/deps/build/*.jar build/official-deps/*.jar build/grpc-export-deps/*.jar build/component-deps/*.jar; do classpath="$classpath:$jarfile"; done
javac -J-XX:TieredStopAtLevel=1 -source 8 -target 8 -proc:none -cp "$classpath" -d build/degradation-classes @build/degradation-sources.txt
# Analyze SDK interfaces with their callers so static/default interface calls use
# exactly the same companion classes as the existing Java 6 SDK transformation.
mkdir -p build/degradation-combined
cp -R build/tooling-combined/. build/degradation-combined/
cp -R build/degradation-classes/. build/degradation-combined/
java -XX:TieredStopAtLevel=1 -Dretrolambda.quiet=true -Dretrolambda.inputDir=build/degradation-combined -Dretrolambda.outputDir=build/degradation-transformed -Dretrolambda.classpath="build/degradation-combined:$classpath" -Dretrolambda.bytecodeVersion=50 -Dretrolambda.defaultMethods=true -javaagent:/sdk/java6-compat/build/deps/build/retrolambda-2.5.7.jar -jar /sdk/java6-compat/build/deps/build/retrolambda-2.5.7.jar
mkdir -p build/degradation-java6/io/opentelemetry/javaagent build/degradation-java6/opamp
cp -R build/degradation-transformed/io/opentelemetry/javaagent/degradation build/degradation-java6/io/opentelemetry/javaagent/
cp -R build/degradation-transformed/opamp/. build/degradation-java6/opamp/
(cd build/degradation-java6 && jar xf ../degradation-deps/protobuf-java-3.3.0.jar)
rm -rf build/degradation-java6/META-INF
mkdir -p build/degradation-java6/META-INF/services
printf '%s\n' io.opentelemetry.javaagent.degradation.DegradationAgentListener > build/degradation-java6/META-INF/services/io.opentelemetry.javaagent.extension.AgentListener
printf '%s\n' io.opentelemetry.javaagent.degradation.DegradationCustomizer > build/degradation-java6/META-INF/services/io.opentelemetry.sdk.autoconfigure.spi.AutoConfigurationCustomizerProvider
