#!/usr/bin/env python3
"""Exercise the official exporter with a real network transport and unchanged HTTP fixture."""
import argparse
import gzip
import hashlib
import http.server
import json
from pathlib import Path
import ssl
import subprocess
import threading
import time
import uuid
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

p = argparse.ArgumentParser()
p.add_argument('--jdk6', type=Path, required=True)
p.add_argument('--image')
p.add_argument('--native-java', type=Path)
p.add_argument('--export-timeout-ms', type=int, default=10000)
p.add_argument('--tls-debug', action='store_true')
p.add_argument('--platform', default='linux/amd64')
p.add_argument('--mode', choices=['auth-gzip', 'gzip-response', 'tls', 'untrusted-tls', 'timeout'], required=True)
a = p.parse_args()
root = Path(__file__).resolve().parents[1]
artifact = root / 'build/official-loader-candidate.jar'
checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
captured, requests, business = [], [], []
class Business(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        business.append(self.path)
        self.send_response({'/ok': 200, '/missing': 404, '/failure': 503}[self.path])
        self.end_headers()
        self.wfile.write(b'body')
class Collector(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        # Official OkHttp streams compressed requests using HTTP chunked transfer encoding.
        if self.headers.get('Transfer-Encoding', '').lower() == 'chunked':
            chunks = []
            total = 0
            while True:
                line = self.rfile.readline(8193)
                if len(line) > 8192 or not line.endswith(b'\r\n'):
                    raise ValueError('Invalid fixture chunk header')
                size = int(line.split(b';', 1)[0].strip(), 16)
                if size == 0:
                    for _ in range(100):
                        if self.rfile.readline(8193) == b'\r\n': break
                    else: raise ValueError('Too many fixture trailers')
                    break
                total += size
                if size < 0 or total > 16 * 1024 * 1024:
                    raise ValueError('Fixture body too large')
                chunk = self.rfile.read(size)
                if len(chunk) != size or self.rfile.read(2) != b'\r\n':
                    raise ValueError('Incomplete fixture chunk')
                chunks.append(chunk)
            payload = b''.join(chunks)
        else:
            payload = self.rfile.read(int(self.headers['Content-Length']))
        requests.append(dict(received=time.monotonic(), path=self.path, authorization=self.headers.get('Authorization'),
                             encoding=self.headers.get('Content-Encoding')))
        if a.mode == 'timeout':
            time.sleep(3)
        else:
            if self.headers.get('Content-Encoding') == 'gzip': payload = gzip.decompress(payload)
            message = ExportTraceServiceRequest()
            message.ParseFromString(payload)
            captured.append(MessageToDict(message))
        try:
            self.send_response(200)
            response = b''
            if a.mode == 'gzip-response':
                compressed = gzip.compress(b'')  # Empty protobuf ExportTraceServiceResponse.
                response = compressed[:3] + bytes([compressed[3] | 4]) + compressed[4:10] + b'\xff\xff' + bytes(65535) + compressed[10:]
                self.send_header('Content-Encoding', 'gzip')
                self.send_header('Content-Type', 'application/x-protobuf')
                self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            if response: self.wfile.write(response)
        except (BrokenPipeError, ConnectionResetError): pass
servers = [http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler) for handler in (Business, Collector)]
if 'tls' in a.mode:
    stage = root / 'build/export-transport'
    stage.mkdir(exist_ok=True)
    config = stage / 'openssl.cnf'
    config.write_text('[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n[dn]\nCN=host.docker.internal\n[ext]\nsubjectAltName=DNS:host.docker.internal,DNS:localhost\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,digitalSignature,keyEncipherment,keyCertSign\n')
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-days', '2',
                    '-keyout', str(stage / 'key.pem'), '-out', str(stage / 'certificate.pem'),
                    '-config', str(config)], check=True, capture_output=True)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    # Oracle 6u45 has TLS 1.0. This is an isolated test endpoint, not a deployment default.
    context.minimum_version = ssl.TLSVersion.TLSv1
    context.set_ciphers('AES128-SHA:AES256-SHA:@SECLEVEL=0')
    context.load_cert_chain(stage / 'certificate.pem', stage / 'key.pem')
    servers[1].socket = context.wrap_socket(servers[1].socket, server_side=True)
for server in servers:
    threading.Thread(target=server.serve_forever, daemon=True).start()
container = 'official-export-' + uuid.uuid4().hex[:10]
command = ['docker', 'run', '--rm', '--name', container, '--platform', a.platform, '-v', str(root) + ':/test:ro',
           '-v', str(a.jdk6.resolve()) + ':/jdk:ro', a.image or 'debian:bookworm-slim',
           'java' if a.image else '/jdk/bin/java']
if a.image and a.image.startswith('eclipse-temurin:8'): command.append('-XX:TieredStopAtLevel=1')
command += ['-Xverify:all', '-javaagent:/test/build/official-loader-candidate.jar',
            '-Dotel.exporter.otlp.protocol=http/protobuf',
            '-Dotel.exporter.otlp.endpoint=' + ('https' if 'tls' in a.mode else 'http') + '://host.docker.internal:' + str(servers[1].server_port),
            '-Dotel.metrics.exporter=none', '-Dotel.logs.exporter=none',
            '-Dotel.exporter.otlp.headers=Authorization=Bearer%20test-only',
            '-Dotel.exporter.otlp.timeout=' + ('300' if a.mode == 'timeout' else str(a.export_timeout_ms))]
if a.tls_debug: command += ['-Djavax.net.debug=ssl:handshake']
if a.mode == 'tls': command += ['-Dotel.exporter.otlp.certificate=/test/build/export-transport/certificate.pem']
if a.mode == 'auth-gzip': command += ['-Dotel.exporter.otlp.compression=gzip']
command += ['-cp', '/test/build/app', 'HttpClientProbe', 'http://host.docker.internal:' + str(servers[0].server_port)]
if a.native_java:
    command = [str(a.native_java)] + [value.replace('/test/', str(root) + '/').replace('host.docker.internal', 'localhost') for value in command[command.index('-Xverify:all'):]]
passed = False
stdout, stderr = '', ''
try:
    started = time.monotonic()
    process = subprocess.run(command, capture_output=True, text=True, timeout=180)
    elapsed = time.monotonic() - started
    stdout, stderr = process.stdout, process.stderr
    assert process.returncode == 0 and 'HTTP_PROBE_OK' in stdout, (stdout, stderr)
    assert sorted(business) == ['/failure', '/missing', '/ok'], business
    if a.mode in ('auth-gzip', 'gzip-response', 'tls'):
        spans = [s for d in captured for rs in d['resourceSpans'] for ss in rs['scopeSpans'] for s in ss['spans']]
        assert len(spans) == 4, (captured, stderr)  # also excludes exporter self-tracing
        assert requests and all(r['authorization'] == 'Bearer test-only' and r['path'] == '/v1/traces' for r in requests), requests
        if a.mode == 'gzip-response':
            assert not any(value in (stdout + stderr) for value in ('Failed to export', 'byteCount < 0', 'Exception in thread')), (stdout, stderr)
        if a.mode == 'auth-gzip': assert all(r['encoding'] == 'gzip' for r in requests), requests
    elif a.mode == 'untrusted-tls':
        assert not captured and not requests, requests
        # Oracle 6 JSSE handshake diagnostics use stdout; newer JVMs may use stderr.
        diagnostics = stdout + '\n' + stderr
        assert 'SSLHandshakeException' in diagnostics or 'PKIX' in diagnostics, diagnostics
    else:
        assert requests and not captured, requests
        assert 'deadline exceeded' in stderr or 'timed out' in stderr, stderr
        assert time.monotonic() - requests[0]['received'] < 10, 'Export timeout did not bound process exit'
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == checksum
    passed = True
    print('PASS', a.image or 'Oracle6u45', a.mode, 'unchanged business and exporter boundary')
finally:
    if not a.native_java:
        subprocess.run(['docker', 'rm', '-f', container], capture_output=True, timeout=30)
    result = dict(passed=passed, sha256=checksum, mode=a.mode, command=command,
                  stdout=stdout, stderr=stderr, requests=requests, captured=captured)
    (root / 'build/e2e' / ('export-transport-' + a.mode + '-' + (a.image or 'java6').replace(':', '-') + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    for server in servers: server.shutdown(); server.server_close()
