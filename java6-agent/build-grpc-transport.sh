#!/bin/sh
set -eu
cd "$(dirname "$0")"
rm -rf build/grpc-overlay-classes
mkdir -p build/grpc-overlay-classes
find build/grpc-overlay-src -name '*.java' > build/grpc-overlay-sources.txt
javac -J-XX:TieredStopAtLevel=1 -source 6 -target 6 -cp 'build/grpc-export-deps/*' -d build/grpc-overlay-classes @build/grpc-overlay-sources.txt
