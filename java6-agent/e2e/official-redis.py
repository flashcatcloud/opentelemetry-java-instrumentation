#!/usr/bin/env python3
import argparse,hashlib,http.server,json,subprocess,threading
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
p=argparse.ArgumentParser();p.add_argument('--jdk6',required=True,type=Path);p.add_argument('--image');p.add_argument('--lettuce',action='store_true');p.add_argument('--lettuce-version',default='5.1.0.RELEASE');p.add_argument('--debug',action='store_true');p.add_argument('--platform',default='linux/amd64');a=p.parse_args()
root=Path(__file__).resolve().parents[1];captured=[];passed=False
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        request=ExportTraceServiceRequest();request.ParseFromString(self.rfile.read(int(self.headers['Content-Length'])))
        captured.append(MessageToDict(request));self.send_response(200);self.end_headers()
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    cmd=['docker','run','--rm','--platform',a.platform,'--network','sw6-poc','-v',str(root)+':/test:ro','-v',str(a.jdk6)+':/jdk:ro',a.image or 'debian:bookworm-slim','java' if a.image else '/jdk/bin/java']
    if a.image and a.image.startswith('eclipse-temurin:8'):cmd+=['-XX:TieredStopAtLevel=1']
    cmd+=['-Xverify:all','-javaagent:/test/build/official-loader-candidate.jar','-Dotel.exporter.otlp.protocol=http/protobuf','-Dotel.exporter.otlp.endpoint=http://host.docker.internal:'+str(server.server_port),'-Dotel.metrics.exporter=none','-Dotel.logs.exporter=none','-Dotel.semconv-stability.opt-in=database','-cp','/test/build/app:/test/build/databases/deps/*','RedisClientProbe']
    if a.lettuce:
        cmd[-1]='LettuceClientProbe';cmd[-2]='/test/build/app:/test/build/'+('lettuce' if a.lettuce_version=='5.1.0.RELEASE' else 'lettuce-'+a.lettuce_version)+'/deps/*'
    if a.debug:cmd.insert(cmd.index('-Xverify:all'),'-Dotel.javaagent.debug=true')
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
    assert result.returncode==0 and 'REDIS_PROBE_OK' in result.stdout,(result.stdout,result.stderr)
    spans=[s for d in captured for rs in d['resourceSpans'] for ss in rs['scopeSpans'] for s in ss['spans']]
    attrs=[{x['key']:next(iter(x['value'].values())) for x in s['attributes']} for s in spans]
    if a.lettuce:
        operations=[v.get('db.operation.name', '') for v in attrs]
        for operation,count in [('GET',2),('SET',1),('LPUSH',1),('PING',1),('DEL',1)]:assert operations.count(operation)==count,operations
        allowed=('GET','SET','LPUSH','PING','DEL','SELECT')
        if a.lettuce_version.startswith('6.'):
            assert operations.count('HELLO')==1,operations
            allowed+=('HELLO',)
        assert all(op in allowed for op in operations),operations
    else:assert len(spans)==6,(spans,attrs)
    assert all(s['kind']=='SPAN_KIND_CLIENT' for s in spans)
    assert sum(s.get('status',{}).get('code')=='STATUS_CODE_ERROR' for s in spans)==1,spans
    assert all(v['db.system.name']=='redis' and v['server.address']=='java6-redis-db' for v in attrs),attrs
    assert all('private-value-93217' not in v.get('db.query.text','') for v in attrs),attrs
    if not a.lettuce:assert any(int(v.get('db.operation.batch.size',0))==2 for v in attrs),attrs
    if a.lettuce:
        assert any(v.get('db.query.text')=='SELECT 2' for v in attrs),attrs
        assert all(v.get('db.namespace') in (None,'2') for v in attrs),attrs
    else:assert any(v.get('db.namespace')=='2' for v in attrs),attrs
    passed=True;print('PASS',a.image or 'Oracle6u45',('official Lettuce '+a.lettuce_version+' sync/async commands, WRONGTYPE, SELECT and redaction; namespace='+str(any(v.get('db.namespace')=='2' for v in attrs)) if a.lettuce else 'official Jedis 2.9 commands, WRONGTYPE, pipeline batch, database namespace and redaction'))
finally:
    (root/'build/e2e'/('official-redis-'+('lettuce-'+a.lettuce_version+'-' if a.lettuce else '')+(a.image or 'java6').replace(':','-')+'.json')).write_text(json.dumps({'pass':passed,'sha256':hashlib.sha256((root/'build/official-loader-candidate.jar').read_bytes()).hexdigest(),'command':cmd,'stdout':result.stdout,'stderr':result.stderr,'captured':captured},indent=2)+'\n')
    server.shutdown();server.server_close()
