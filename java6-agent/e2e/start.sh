#!/bin/bash
set -euo pipefail
: "${POC_ROOT:?existing SkyWalking PoC root}"
: "${COMPARE_ROOT:?existing MySQL comparison root}"
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$ROOT/build/e2e"
AGENT_SHA=$(shasum -a 256 "$ROOT/build/opentelemetry-javaagent-java6.jar" | cut -d " " -f1)
AGENT_JAR="$ROOT/build/e2e/agent-$AGENT_SHA.jar"
if [ ! -f "$AGENT_JAR" ]; then cp "$ROOT/build/opentelemetry-javaagent-java6.jar" "$AGENT_JAR"; fi
CP="/compare/app:/compare/downloads/mysql.jar:$POC_ROOT/downloads/tomcat-embed-core.jar:$POC_ROOT/downloads/tomcat-embed-logging-juli.jar:$POC_ROOT/downloads/annotations.jar"
# Only replace containers owned by this new Java6 OTel experiment.
for name in java6-otel-a java6-otel-b java6-otel-capture; do
  if docker inspect "$name" >/dev/null 2>&1; then docker rm -f "$name" >/dev/null; fi
done
docker run -d --entrypoint /home/flashcat/otel/otelcol-contrib --name java6-otel-capture --network sw6-poc --restart unless-stopped --platform linux/amd64 \
  -v "$ROOT/e2e/capture.yaml:/config.yaml:ro" -v "$ROOT/build/e2e:/evidence" \
  registry.flashcat.cloud/flashcat/otelcol-contrib:0.132.0.1-skywalkingv2-semconv2-20261013-amd64 --config=/config.yaml
for attempt in $(seq 1 60); do
  if docker logs java6-otel-capture 2>&1 | grep -q "Everything is ready"; then break; fi
  if [ "$attempt" = 60 ]; then echo "Collector not ready" >&2; exit 1; fi
  sleep 1
done
for role in b a; do
  if [ "$role" = a ]; then port=18084; else port=18085; fi
  docker run -d --name "java6-otel-$role" --network sw6-poc --restart unless-stopped --platform linux/amd64 \
    --log-opt max-size=10m --log-opt max-file=2 -p "127.0.0.1:$port:8080" \
    -v "$POC_ROOT:$POC_ROOT:ro" -v "$COMPARE_ROOT:/compare:ro" -v "$AGENT_JAR:/agent.jar:ro" \
    --env-file "$COMPARE_ROOT/app.env" -e DOWNSTREAM_URL=http://java6-otel-b:8080/query \
    -e "OTEL_SERVICE_NAME=java6-otel-$role" -e OTEL_EXPORTER_OTLP_ENDPOINT=http://java6-otel-capture:4318 \
    debian:bookworm-slim "$POC_ROOT/oracle6u45-poc/runtime/jdk1.6.0_45/bin/java" \
    -Xverify:all -javaagent:/agent.jar -cp "$CP" App "$role" 8080
done
