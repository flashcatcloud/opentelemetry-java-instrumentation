#!/usr/bin/env python3
"""Verify upstream RabbitMQ publish/process spans using a real broker and JDBC callback."""
import argparse,hashlib,http.server,json,os,subprocess,threading
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
p=argparse.ArgumentParser();p.add_argument('--jdk6',required=True,type=Path);p.add_argument('--driver',required=True,type=Path);p.add_argument('--image');p.add_argument('--platform',default='linux/amd64');p.add_argument('--debug',action='store_true');p.add_argument('--client-version',default='2.7.0');a=p.parse_args()
root=Path(__file__).resolve().parents[1];captured=[];passed=False;result=None
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
    cmd=['docker','run','--rm','--platform',a.platform,'--network','sw6-poc','-v',str(root)+':/test:ro','-v',str(a.jdk6)+':/jdk:ro','-v',str(a.driver)+':/driver.jar:ro','-e','JDBC_PASSWORD','-e','JDBC_USER=root','-e','JDBC_URL=jdbc:mysql://sw6-mysql:3306/?useSSL=false&allowPublicKeyRetrieval=true','-e','RABBIT_HOST=official-javaagent-rabbitmq',a.image or 'debian:bookworm-slim','java' if a.image else '/jdk/bin/java']
    if a.image and a.image.startswith('eclipse-temurin:8'):cmd+=['-XX:TieredStopAtLevel=1']
    if a.debug:cmd+=['-Dotel.javaagent.debug=true']
    cmd+=['-Xverify:all','-javaagent:/test/build/official-loader-candidate.jar','-Dotel.exporter.otlp.protocol=http/protobuf','-Dotel.exporter.otlp.endpoint=http://host.docker.internal:'+str(server.server_port),'-Dotel.metrics.exporter=none','-Dotel.logs.exporter=none','-Dotel.semconv-stability.opt-in=database,messaging','-cp','/test/build/app:/driver.jar:/test/build/rabbit/deps/*','RabbitClientProbe']
    if a.client_version!='2.7.0':cmd[-2]='/test/build/app:/driver.jar:/test/build/rabbit/amqp-client-'+a.client_version+'.jar:/test/build/runtime-deps/*'
    result=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=90)
    assert result.returncode==0 and 'RABBIT_PROBE_OK' in result.stdout,(result.stdout,result.stderr)
    spans=[s for d in captured for rs in d['resourceSpans'] for ss in rs['scopeSpans'] for s in ss['spans']]
    producers=[s for s in spans if s['kind']=='SPAN_KIND_PRODUCER'];consumers=[s for s in spans if s['kind']=='SPAN_KIND_CONSUMER']
    assert len(producers)==3 and len(consumers)==3,spans
    assert len({s['traceId'] for s in producers})==3,producers
    for consumer in consumers:
        producer=next(s for s in producers if s['traceId']==consumer['traceId'])
        assert consumer['parentSpanId']==producer['spanId'],consumer
    assert sum(s.get('status',{}).get('code')=='STATUS_CODE_ERROR' for s in consumers)==1,consumers
    queries=[s for s in spans if any(x['key']=='db.query.text' and x['value'].get('stringValue')=='SELECT ? FROM dual' for x in s.get('attributes',[]))]
    assert len(queries)==2,queries
    for query in queries:
        assert any(query['traceId']==s['traceId'] and query['parentSpanId']==s['spanId'] for s in consumers),query
    passed=True;print('PASS',a.image or 'Oracle6u45','RabbitMQ '+a.client_version+' producer -> consumer -> MySQL, three isolated traces, callback error and exact span counts')
finally:
    evidence={'pass':passed,'sha256':hashlib.sha256((root/'build/official-loader-candidate.jar').read_bytes()).hexdigest(),'stdout':result.stdout if result else '', 'stderr':result.stderr if result else '', 'captured':captured}
    (root/'build/e2e'/('official-rabbit-'+a.client_version+'-'+(a.image or 'java6').replace(':','-')+'.json')).write_text(json.dumps(evidence,indent=2)+'\n')
    server.shutdown();server.server_close()
