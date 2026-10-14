#!/usr/bin/env python3
"""Verify upstream gRPC client/server spans using a real broker and JDBC callback."""
import argparse,hashlib,http.server,json,os,subprocess,threading,uuid
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
p=argparse.ArgumentParser();p.add_argument('--jdk6',required=True,type=Path);p.add_argument('--driver',required=True,type=Path);p.add_argument('--image');p.add_argument('--platform',default='linux/amd64');p.add_argument('--debug',action='store_true');p.add_argument('--client-version',default='1.6.0');p.add_argument('--agent',default='official-loader-candidate.jar');a=p.parse_args()
root=Path(__file__).resolve().parents[1];captured=[];passed=False;result=None
container="grpc-probe-"+uuid.uuid4().hex[:10];timeout_evidence=None
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        request=ExportTraceServiceRequest();request.ParseFromString(self.rfile.read(int(self.headers['Content-Length'])))
        captured.append(MessageToDict(request));self.send_response(200);self.end_headers()
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    settings=json.loads(subprocess.check_output(['docker','inspect','sw6-mysql']))[0]['Config']['Env']
    password=next(x.split('=',1)[1] for x in settings if x.startswith('MYSQL_ROOT_PASSWORD='))
    env=dict(os.environ,JDBC_PASSWORD=password)
    cmd=['docker','run','--rm','--name',container,'--platform',a.platform,'--network','sw6-poc','-v',str(root)+':/test:ro','-v',str(a.jdk6)+':/jdk:ro','-v',str(a.driver)+':/driver.jar:ro','-e','JDBC_PASSWORD','-e','JDBC_USER=root','-e','JDBC_URL=jdbc:mysql://sw6-mysql:3306/?useSSL=false&allowPublicKeyRetrieval=true',a.image or 'debian:bookworm-slim','java' if a.image else '/jdk/bin/java']
    if a.image and a.image.startswith('eclipse-temurin:8'):cmd+=['-XX:TieredStopAtLevel=1']
    if a.debug:cmd+=['-Dotel.javaagent.debug=true']
    cmd+=['-Xverify:all','-javaagent:/test/build/'+a.agent,'-Dotel.exporter.otlp.protocol=http/protobuf','-Dotel.exporter.otlp.endpoint=http://host.docker.internal:'+str(server.server_port),'-Dotel.metrics.exporter=none','-Dotel.logs.exporter=none','-Dotel.semconv-stability.opt-in=database,rpc','-cp','/test/build/app:/driver.jar:/test/build/grpc-'+a.client_version+'/deps/*','GrpcClientProbe']
    try:
        result=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=90)
    except subprocess.TimeoutExpired as failure:
        logs=subprocess.run(['docker','logs',container],capture_output=True,text=True,timeout=15)
        stack=subprocess.run(['docker','exec',container,'sh','-c','kill -QUIT 1'],capture_output=True,text=True,timeout=15)
        import time
        time.sleep(1)
        after=subprocess.run(['docker','logs',container],capture_output=True,text=True,timeout=15)
        timeout_evidence=dict(stdout=logs.stdout,stderr=logs.stderr,thread_dump=after.stdout+after.stderr,signal_exit=stack.returncode)
        raise
    assert result.returncode==0 and 'GRPC_PROBE_OK' in result.stdout,(result.stdout,result.stderr)
    spans=[s for d in captured for rs in d['resourceSpans'] for ss in rs['scopeSpans'] for s in ss['spans']]
    def attributes(span):return {x['key']:next(iter(x['value'].values())) for x in span.get('attributes',[])}
    rpc=[s for s in spans if attributes(s).get('rpc.system.name',attributes(s).get('rpc.system'))=='grpc']
    clients=[s for s in rpc if s['kind']=='SPAN_KIND_CLIENT'];servers=[s for s in rpc if s['kind']=='SPAN_KIND_SERVER']
    assert len(clients)==5 and len(servers)==5,spans
    assert len({s['traceId'] for s in clients})==5,clients
    for server_span in servers:
        client=next(s for s in clients if s['traceId']==server_span['traceId'])
        assert server_span['parentSpanId']==client['spanId'],server_span
    assert sum(s.get('status',{}).get('code')=='STATUS_CODE_ERROR' for s in clients)==2,clients
    assert sum(s.get('status',{}).get('code')=='STATUS_CODE_ERROR' for s in servers)==1,servers
    slow=max(clients,key=lambda s:int(s['startTimeUnixNano']))
    assert int(slow['endTimeUnixNano'])-int(slow['startTimeUnixNano'])>=250000000,slow
    assert sorted(attributes(s)['rpc.response.status_code'] for s in servers)==['INTERNAL','INVALID_ARGUMENT','OK','OK','OK'],servers
    queries=[s for s in spans if any(x['key']=='db.query.text' and x['value'].get('stringValue')=='SELECT ? FROM dual' for x in s.get('attributes',[]))]
    assert len(queries)==3,queries
    for query in queries:
        assert any(query['traceId']==s['traceId'] and query['parentSpanId']==s['spanId'] for s in servers),query
    passed=True;print('PASS',a.image or 'Oracle6u45','gRPC '+a.client_version+' client -> server -> MySQL, sync/async/error, five isolated traces and exact span counts')
finally:
    evidence={'timeout':timeout_evidence,'command':cmd,'pass':passed,'sha256':hashlib.sha256((root/'build'/a.agent).read_bytes()).hexdigest(),'stdout':result.stdout if result else '', 'stderr':result.stderr if result else '', 'captured':captured}
    (root/'build/e2e'/('official-grpc-'+('native-' if a.agent.startswith('native-') else '')+a.client_version+'-'+(a.image or 'java6').replace(':','-')+'.json')).write_text(json.dumps(evidence,indent=2)+'\n')
    subprocess.run(['docker','rm','-f',container],capture_output=True,timeout=30)
    server.shutdown();server.server_close()
