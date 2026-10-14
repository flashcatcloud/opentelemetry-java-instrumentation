#!/bin/sh
# Migration-stage linkage audit; does not package or replace the delivery agent.
set -eu
cd "$(dirname "$0")"
rm -rf build/tooling-combined build/tooling-java6
mkdir -p build/tooling-combined
cp -R build/instrumentation-combined/. build/tooling-combined/
cp -R build/tooling-classes/. build/tooling-combined/
# Legacy Dubbo advice crosses the application/agent loader boundary through this bridge.
mkdir -p build/tooling-combined/io/opentelemetry/javaagent/bootstrap
cp build/bootstrap/io/opentelemetry/javaagent/bootstrap/DubboBridge*.class build/tooling-combined/io/opentelemetry/javaagent/bootstrap/
if [ -d build/modules-classes ]; then cp -R build/modules-classes/. build/tooling-combined/; fi
# Tooling uses Byte Buddy's external-ASM artifact; override the prototype dependency.
(cd build/tooling-combined && jar -J-XX:TieredStopAtLevel=1 xf ../official-deps/byte-buddy-dep-1.18.14.jar)
for archive in build/official-deps/asm-*.jar build/runtime-deps/*.jar; do
  (cd build/tooling-combined && jar -J-XX:TieredStopAtLevel=1 xf "../../$archive")
done
rm -rf build/tooling-combined/META-INF
classpath="build/tooling-combined:build/bootstrap:build/tooling-java9"
for archive in /sdk/java6-compat/build/deps/build/*.jar build/official-deps/*.jar build/component-deps/*.jar build/grpc-export-deps/*.jar; do
  classpath="$classpath:$archive"
done
# Retrolambda otherwise drops suppressed cleanup exceptions even on Java 8+.
mkdir -p build/prebackport-tools
javac -J-XX:TieredStopAtLevel=1 -source 8 -target 8 -proc:none -cp 'build/official-deps/*' -d build/prebackport-tools build-tools/PreserveSuppressedExceptions.java
java -XX:TieredStopAtLevel=1 -cp 'build/prebackport-tools:build/official-deps/*' PreserveSuppressedExceptions build/tooling-combined
java -XX:TieredStopAtLevel=1 -Dretrolambda.quiet=true -Dretrolambda.inputDir=build/tooling-combined -Dretrolambda.outputDir=build/tooling-java6 -Dretrolambda.classpath="$classpath" -Dretrolambda.bytecodeVersion=50 -Dretrolambda.defaultMethods=true -javaagent:/sdk/java6-compat/build/deps/build/retrolambda-2.5.7.jar -jar /sdk/java6-compat/build/deps/build/retrolambda-2.5.7.jar

# Retain upstream generated and static provider registrations after class rewriting.
mkdir -p build/tooling-java6/META-INF
cp -R build/tooling-classes/META-INF/services build/tooling-java6/META-INF/
if [ -d build/modules-classes/META-INF/services ]; then
  for service in build/modules-classes/META-INF/services/*; do
    target="build/tooling-java6/META-INF/services/$(basename "$service")"
    cat "$service" >> "$target"
    sort -u "$target" -o "$target"
  done
fi

# Include application helper SPI resources for upstream modules such as Dubbo.
if [ -d build/module-resources ]; then cp -R build/module-resources/. build/tooling-java6/; fi
