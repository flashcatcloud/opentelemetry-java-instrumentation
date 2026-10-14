#!/bin/sh
# Build both compatibility forks without pre-existing generated files or binary caches.
set -eu
: "${JAVA6_HOME:?Set JAVA6_HOME to the Oracle JDK 6u45 directory}"
test -f "$JAVA6_HOME/jre/lib/rt.jar"
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
sdk=$(CDPATH= cd -- "${1:?Usage: build-all.sh /absolute/sdk-fork}" && pwd)
python3 "$sdk/java6-compat/fetch.py"
python3 "$sdk/java6-compat/prepare.py"
docker run --rm --platform linux/amd64 \
  -v "$sdk:/repo" -v "$sdk/java6-compat/build/deps/build:/deps:ro" \
  -w /repo eclipse-temurin:8-jdk@sha256:3a280002b0d1212a62e9f5095c10b07ef3b62c1b13916fe093438e7e9af44b8b sh java6-compat/build.sh
python3 "$sdk/java6-compat/package.py" "$sdk/java6-compat/build/deps/build"
sh "$root/java6-agent/build-official-candidate.sh" "$sdk"
