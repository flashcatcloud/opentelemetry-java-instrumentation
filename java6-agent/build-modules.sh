#!/bin/sh
set -eu
cd "$(dirname "$0")"
rm -rf build/modules-classes build/modules-generated
mkdir -p build/modules-classes build/modules-generated
processorpath=/sdk/java6-compat/build/deps/build/auto-value-1.11.1.jar
for archive in build/official-deps/*.jar; do processorpath="$processorpath:$archive"; done
find build/modules-src -name '*.java' > build/modules-sources.txt
javac -J-XX:TieredStopAtLevel=1 -source 8 -target 8 -cp 'build/component-deps/dubbo-2.5.3.jar:build/component-deps/*:build/official-deps/*:build/tooling-classes:build/instrumentation-classes:build/classes:build/bootstrap:/sdk/java6-compat/build/deps/build/*' -processorpath "$processorpath" -processor com.google.auto.value.processor.AutoValueProcessor,com.google.auto.service.processor.AutoServiceProcessor -s build/modules-generated -d build/modules-classes @build/modules-sources.txt

cp -R build/module-resources/. build/modules-classes/
