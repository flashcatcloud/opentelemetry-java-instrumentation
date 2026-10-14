#!/bin/sh
# Compile the compatible upstream SDK/autoconfiguration/exporter base.
# The official module loader and components are assembled by build-official-candidate.sh.
set -eu
cd "$(dirname "$0")"
rm -rf build/bootstrap build/classes build/java6 build/exporter-generated
mkdir -p build/bootstrap build/classes build/app build/exporter-generated
find build/src src/bootstrap -name '*.java' > build/bootstrap-sources.txt
javac -J-XX:TieredStopAtLevel=1 -source 6 -target 6 -d build/bootstrap @build/bootstrap-sources.txt
cp -R /sdk/java6-compat/build/classes/. build/classes/
(cd build/classes && jar -J-XX:TieredStopAtLevel=1 xf ../deps/gson-2.8.9.jar)
# Java 6 never selects multi-release implementations.
rm -rf build/classes/META-INF
find build/exporter-src build/framework-src build/dependency-src src/compat -name '*.java' > build/exporter-sources.txt
javac -J-XX:TieredStopAtLevel=1 -source 8 -target 8 -cp 'build/classes:build/grpc-export-deps/*:/sdk/java6-compat/build/deps/build/*' -processorpath /sdk/java6-compat/build/deps/build/auto-value-1.11.1.jar -s build/exporter-generated -d build/classes @build/exporter-sources.txt
javac -J-XX:TieredStopAtLevel=1 -source 8 -target 8 -proc:none -cp 'build/bootstrap:build/classes:/sdk/java6-compat/build/deps/build/*' -d build/classes src/tooling/*.java
grpc_classpath=""
for archive in build/grpc-export-deps/*.jar; do grpc_classpath="$grpc_classpath:$archive"; done
java -XX:TieredStopAtLevel=1 -Dretrolambda.quiet=true -Dretrolambda.inputDir=build/classes -Dretrolambda.outputDir=build/java6 -Dretrolambda.classpath="build/classes:build/bootstrap$grpc_classpath:/sdk/java6-compat/build/deps/build/streamsupport-1.7.4.jar:/sdk/java6-compat/build/deps/build/threetenbp-1.6.8.jar:/sdk/java6-compat/build/deps/build/jctools-core-4.0.7.jar:/sdk/java6-compat/build/deps/build/commons-codec-1.10.jar" -Dretrolambda.bytecodeVersion=50 -Dretrolambda.defaultMethods=true -javaagent:/sdk/java6-compat/build/deps/build/retrolambda-2.5.7.jar -jar /sdk/java6-compat/build/deps/build/retrolambda-2.5.7.jar
javac -J-XX:TieredStopAtLevel=1 -source 6 -target 6 -d build/app tests/PlainApplication.java tests/HttpClientProbe.java tests/ExitAfterMain.java
