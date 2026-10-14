#!/bin/bash
set -eu
while true; do
  date -u +%FT%TZ
  timeout 10 bash -c 'exec 3<>/dev/tcp/java6-otel-a/8080; printf "GET /call HTTP/1.1\r\nHost: java6-otel-a:8080\r\nConnection: close\r\n\r\n" >&3; cat <&3' || true
  sleep 1
done
