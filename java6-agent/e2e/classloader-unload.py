#!/usr/bin/env python3
"""Verify disposable application loaders and actual Redis spans together."""
import argparse, hashlib, http.server, json, subprocess, threading
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
p = argparse.ArgumentParser()
p.add_argument('--jdk6', required=True, type=Path)
p.add_argument('--image')
p.add_argument('--platform', default='linux/amd64')
p.add_argument('--without-agent', action='store_true')
a = p.parse_args()
r = Path(__file__).resolve().parents[1]
stage = r / 'build/classloader-unload'
stage.mkdir(exist_ok=True)
subprocess.run(['docker','run','--rm','--platform','linux/amd64','-v',str(r)+':/test','eclipse-temurin:8-jdk','javac','-J-XX:TieredStopAtLevel=1','-source','6','-target','6','-d','/test/build/classloader-unload','/test/tests/ClassLoaderUnloadProbe.java'], check=True)
captured = []
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        req = ExportTraceServiceRequest()
        req.ParseFromString(self.rfile.read(int(self.headers['Content-Length'])))
        captured.append(MessageToDict(req))
        self.send_response(200); self.end_headers()
server = http.server.ThreadingHTTPServer(('127.0.0.1',0), Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
jar = r / 'build/official-loader-candidate.jar'
sha = hashlib.sha256(jar.read_bytes()).hexdigest()
try:
    cmd = ['docker','run','--rm','--platform',a.platform,'--network','sw6-poc','-v',str(r)+':/test:ro','-v',str(a.jdk6)+':/jdk:ro',a.image or 'debian:bookworm-slim','java' if a.image else '/jdk/bin/java','-Xverify:all','-Xmx256m']
    if a.image and a.image.startswith('eclipse-temurin:8'): cmd += ['-XX:TieredStopAtLevel=1']
    if not a.without_agent:
        cmd += ['-javaagent:/test/build/official-loader-candidate.jar','-Dotel.exporter.otlp.protocol=http/protobuf','-Dotel.exporter.otlp.endpoint=http://host.docker.internal:'+str(server.server_port),'-Dotel.bsp.schedule.delay=100','-Dotel.metrics.exporter=none','-Dotel.logs.exporter=none','-Dotel.semconv-stability.opt-in=database']
    cmd += ['-cp','/test/build/classloader-unload','ClassLoaderUnloadProbe','/test/build/app','/test/build/databases/deps/jedis.jar','/test/build/databases/deps/pool.jar']
    proc = subprocess.run(cmd,capture_output=True,text=True,timeout=180)
    spans = [s for d in captured for rs in d['resourceSpans'] for ss in rs['scopeSpans'] for s in ss['spans']]
    passed = proc.returncode == 0 and 'CLASSLOADER_UNLOAD_OK cycles=3' in proc.stdout and len(spans) == (0 if a.without_agent else 18)
    assert hashlib.sha256(jar.read_bytes()).hexdigest() == sha
    report = dict(passed=passed,sha256=sha,command=cmd,stdout=proc.stdout,stderr=proc.stderr,captured=captured)
    name = 'classloader-unload-'+(a.image or 'java6').replace(':','-')+('-baseline' if a.without_agent else '')+'.json'
    (r/'build/e2e'/name).write_text(json.dumps(report,indent=2)+'\n')
    assert passed, (proc.stdout,proc.stderr,len(spans))
    print('PASS',name,'3 collected loaders; spans=',len(spans))
finally:
    server.shutdown(); server.server_close()
