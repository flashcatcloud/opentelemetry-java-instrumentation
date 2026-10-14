#!/bin/sh
set -eu
cd "$(dirname "$0")"
rm -rf build/tooling-classes build/tooling-generated
mkdir -p build/tooling-classes build/tooling-generated
processorpath=/sdk/java6-compat/build/deps/build/auto-value-1.11.1.jar
for archive in build/official-deps/*.jar; do processorpath="$processorpath:$archive"; done
find build/tooling-src -name '*.java' > build/tooling-sources.txt
javac -J-XX:TieredStopAtLevel=1 -source 8 -target 8 -Xmaxerrs 200 -cp 'build/http-dependencies-java6:build/runtime-deps/*:build/official-deps/*:build/tooling-java9:build/instrumentation-classes:build/classes:build/bootstrap:/sdk/java6-compat/build/deps/build/*' -processorpath "$processorpath" -processor com.google.auto.value.processor.AutoValueProcessor,com.google.auto.service.processor.AutoServiceProcessor -s build/tooling-generated -d build/tooling-classes @build/tooling-sources.txt

javac -J-XX:TieredStopAtLevel=1 -source 8 -target 8 -proc:none -cp "build/tooling-classes:build/instrumentation-classes:build/classes:/sdk/java6-compat/build/deps/build/*" -d build/tooling-classes tests/ToolingClassCacheTest.java

# Merge upstream static service descriptors with AutoService-generated descriptors.
for servicefile in ../sdk-autoconfigure-support/src/main/resources/META-INF/services/io.opentelemetry.sdk.autoconfigure.spi.AutoConfigurationCustomizerProvider /sdk/exporters/logging/src/main/resources/META-INF/services/*; do
  case "$servicefile" in *internal.ComponentProvider) continue ;; esac
  target="build/tooling-classes/META-INF/services/$(basename "$servicefile")"
  cat "$servicefile" >> "$target"
  sort -u "$target" -o "$target"
done
