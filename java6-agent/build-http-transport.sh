#!/bin/sh
# Build source-pinned private HTTP dependencies; compile-only Android/Conscrypt never ship.
set -eu
cd "$(dirname "$0")"
: "${JAVA6_HOME:?Mount Oracle JDK 6u45 and set JAVA6_HOME for API verification}"
boot="$JAVA6_HOME/jre/lib/rt.jar:$JAVA6_HOME/jre/lib/jce.jar:$JAVA6_HOME/jre/lib/jsse.jar"
rm -rf build/http-okio-classes build/http-okhttp-classes build/http-dependencies-java6
mkdir -p build/http-okio-classes build/http-okhttp-classes build/http-dependencies-java6
find build/http-transport-src/okio -name '*.java' > build/http-okio-sources.txt
javac -J-XX:TieredStopAtLevel=1 -source 6 -target 6 -bootclasspath "$boot" -cp '/sdk/java6-compat/build/deps/build/*:build/http-compile-deps/*' -d build/http-okio-classes @build/http-okio-sources.txt
# Android 10 is outside this server-JVM distribution; retain upstream JVM platform selection.
find build/http-transport-src/okhttp -name '*.java' ! -name Android10Platform.java > build/http-okhttp-sources.txt
javac -J-XX:TieredStopAtLevel=1 -source 8 -target 8 -bootclasspath "$boot" -cp 'build/http-okio-classes:/sdk/java6-compat/build/deps/build/*:build/http-compile-deps/*' -d build/http-okhttp-classes @build/http-okhttp-sources.txt
classpath="build/http-okhttp-classes:build/http-okio-classes"
for archive in /sdk/java6-compat/build/deps/build/*.jar build/http-compile-deps/*.jar; do
  classpath="$classpath:$archive"
done
java -XX:TieredStopAtLevel=1 -Dretrolambda.quiet=true -Dretrolambda.inputDir=build/http-okhttp-classes -Dretrolambda.outputDir=build/http-dependencies-java6 -Dretrolambda.classpath="$classpath" -Dretrolambda.bytecodeVersion=50 -Dretrolambda.defaultMethods=true -javaagent:/sdk/java6-compat/build/deps/build/retrolambda-2.5.7.jar -jar /sdk/java6-compat/build/deps/build/retrolambda-2.5.7.jar
cp -R build/http-okio-classes/. build/http-dependencies-java6/
# Class-relative public suffix resource is required by upstream OkHttp.
find build/http-transport-src/okhttp -name '*.gz' | while IFS= read -r resource; do
  relative=${resource#build/http-transport-src/okhttp/}
  mkdir -p "build/http-dependencies-java6/$(dirname "$relative")"
  cp "$resource" "build/http-dependencies-java6/$relative"
done
