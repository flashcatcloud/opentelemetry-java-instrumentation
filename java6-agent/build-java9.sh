#!/bin/sh
# Keep upstream JPMS helpers conditional, compiled from source for Java 9+.
set -eu
cd "$(dirname "$0")"
rm -rf build/tooling-java9
mkdir -p build/tooling-java9
javac --release 9 -proc:none \
  -cp 'build/bootstrap:build/official-deps/*:/sdk/java6-compat/build/deps/build/*' \
  -d build/tooling-java9 \
  ../javaagent-bootstrap/src/main/java/io/opentelemetry/javaagent/bootstrap/LambdaTransformer.java \
  ../javaagent-tooling/javaagent-tooling-java9/src/main/java/io/opentelemetry/javaagent/tooling/ModuleOpener.java \
  ../javaagent-tooling/javaagent-tooling-java9/src/main/java/io/opentelemetry/javaagent/tooling/ExposeAgentBootstrapListener.java \
  ../javaagent-tooling/javaagent-tooling-java9/src/main/java/io/opentelemetry/javaagent/tooling/Java9LambdaTransformer.java
