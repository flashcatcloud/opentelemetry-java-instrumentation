#!/usr/bin/env python3
"""Real MongoDB command listener acceptance for the official module."""
import argparse,hashlib,http.server,json,subprocess,threading,collections
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
p=argparse.ArgumentParser();p.add_argument('--jdk6',required=True,type=Path);p.add_argument('--image');p.add_argument('--platform',default='linux/amd64');p.add_argument('--debug',action='store_true');a=p.parse_args()
root=Path(__file__).resolve().parents[1];captured=[];passed=False;result=None
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        request=ExportTraceServiceRequest();request.ParseFromString(self.rfile.read(int(self.headers['Content-Length'])))
        captured.append(MessageToDict(request));self.send_response(200);self.end_headers()
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    cmd=['docker','run','--rm','--platform',a.platform,'--network','sw6-poc','-v',str(root)+':/test:ro','-v',str(a.jdk6)+':/jdk:ro',a.image or 'debian:bookworm-slim','java' if a.image else '/jdk/bin/java']
    if a.image and a.image.startswith('eclipse-temurin:8'):cmd+=['-XX:TieredStopAtLevel=1']
    if a.debug:cmd+=['-Dotel.javaagent.debug=true']
    cmd+=['-Xverify:all','-javaagent:/test/build/official-loader-candidate.jar','-Dotel.exporter.otlp.protocol=http/protobuf','-Dotel.exporter.otlp.endpoint=http://host.docker.internal:'+str(server.server_port),'-Dotel.metrics.exporter=none','-Dotel.logs.exporter=none','-Dotel.semconv-stability.opt-in=database','-cp','/test/build/app:/test/build/component-deps/mongo-java-driver-3.7.0.jar','MongoClientProbe']
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
    assert result.returncode==0 and 'MONGO_PROBE_OK' in result.stdout,(result.stdout,result.stderr)
    spans=[s for d in captured for rs in d['resourceSpans'] for ss in rs['scopeSpans'] for s in ss['spans']]
    attrs=[{x['key']:next(iter(x['value'].values())) for x in s['attributes']} for s in spans]
    operations=collections.Counter(v.get('db.operation.name') for v in attrs)
    assert operations=={'insert':1,'find':2,'update':1,'notARealCommand':1,'dropDatabase':1},operations
    assert all(s['kind']=='SPAN_KIND_CLIENT' for s in spans),spans
    assert sum(s.get('status',{}).get('code')=='STATUS_CODE_ERROR' for s in spans)==1,spans
    assert all(v['db.system.name']=='mongodb' and v['db.namespace'].startswith('otel_') for v in attrs),attrs
    assert all(v['server.address']=='official-javaagent-mongo' for v in attrs),attrs
    assert 'private-value-93217' not in json.dumps(captured),attrs
    passed=True;print('PASS',a.image or 'Oracle6u45','MongoDB 3.7 CRUD, exact command counts, server error, namespace, endpoint and redaction')
finally:
    (root/'build/e2e'/('official-mongo-'+(a.image or 'java6').replace(':','-')+'.json')).write_text(json.dumps({'pass':passed,'sha256':hashlib.sha256((root/'build/official-loader-candidate.jar').read_bytes()).hexdigest(),'stdout':result.stdout if result else '', 'stderr':result.stderr if result else '', 'captured':captured},indent=2)+'\n')
    server.shutdown();server.server_close()
