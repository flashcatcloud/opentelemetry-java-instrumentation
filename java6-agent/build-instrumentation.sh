#!/bin/sh
# Compile the official instrumentation APIs separately while migrating the loader.
set -eu
cd "$(dirname "$0")"
rm -rf build/instrumentation-classes build/instrumentation-generated
mkdir -p build/instrumentation-classes build/instrumentation-generated
java -XX:TieredStopAtLevel=1 -cp 'build/official-deps/*' jflex.Main -d build/instrumentation-generated --nobak ../instrumentation-api-incubator/src/main/jflex/SqlSanitizer.jflex ../instrumentation-api-incubator/src/main/jflex/SqlSanitizerWithSummary.jflex
find build/instrumentation-src build/instrumentation-generated src/instrumentation-compat -name '*.java' > build/instrumentation-sources.txt
javac -J-XX:TieredStopAtLevel=1 -source 8 -target 8 -Xmaxerrs 200 -cp 'build/classes:build/official-deps/*:/sdk/java6-compat/build/deps/build/*' -processorpath /sdk/java6-compat/build/deps/build/auto-value-1.11.1.jar -s build/instrumentation-generated -d build/instrumentation-classes @build/instrumentation-sources.txt

rm -rf build/instrumentation-combined build/instrumentation-java6
mkdir -p build/instrumentation-combined
cp -R build/classes/. build/instrumentation-combined/
(cd build/instrumentation-combined && jar -J-XX:TieredStopAtLevel=1 xf ../official-deps/opentelemetry-semconv-1.44.0.jar && jar -J-XX:TieredStopAtLevel=1 xf ../official-deps/opentelemetry-semconv-incubating-1.44.0-alpha.jar)
cp -R build/instrumentation-classes/. build/instrumentation-combined/
rm -rf build/instrumentation-combined/META-INF
javac -J-XX:TieredStopAtLevel=1 -source 8 -target 8 -proc:none -cp 'build/instrumentation-combined:/sdk/java6-compat/build/deps/build/*' -d build/instrumentation-combined tests/OfficialInstrumenterCompatibilityTest.java
grpc_classpath=""
for archive in build/grpc-export-deps/*.jar; do grpc_classpath="$grpc_classpath:$archive"; done
java -XX:TieredStopAtLevel=1 -Dretrolambda.quiet=true -Dretrolambda.inputDir=build/instrumentation-combined -Dretrolambda.outputDir=build/instrumentation-java6 -Dretrolambda.classpath="build/instrumentation-combined:build/bootstrap$grpc_classpath:/sdk/java6-compat/build/deps/build/streamsupport-1.7.4.jar:/sdk/java6-compat/build/deps/build/threetenbp-1.6.8.jar:/sdk/java6-compat/build/deps/build/jctools-core-4.0.7.jar:/sdk/java6-compat/build/deps/build/commons-codec-1.10.jar" -Dretrolambda.bytecodeVersion=50 -Dretrolambda.defaultMethods=true -javaagent:/sdk/java6-compat/build/deps/build/retrolambda-2.5.7.jar -jar /sdk/java6-compat/build/deps/build/retrolambda-2.5.7.jar
