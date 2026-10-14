#!/usr/bin/env python3
"""Exercise the shipped JAR in isolation, using identical unmodified application classes."""
import argparse, gzip, hashlib, http.server, json, pathlib, subprocess, tempfile, threading, time
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest, ExportTraceServiceResponse
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
p=argparse.ArgumentParser();p.add_argument('--jdk6',required=True,type=pathlib.Path);p.add_argument('--modern-image',default='eclipse-temurin:17-jre');a=p.parse_args()
r=pathlib.Path(__file__).resolve().parents[1];b=r/'build';records=[];requests=[];behavior='ok'
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  wire=self.rfile.read(int(self.headers['Content-Length']))
  if self.headers.get('Content-Encoding')=='gzip':wire=gzip.decompress(wire)
  message=ExportMetricsServiceRequest() if self.path.endswith('/metrics') else ExportTraceServiceRequest();message.ParseFromString(wire)
  body=MessageToDict(message)
  for rs in body.get('resourceSpans',[]):
   for scope in rs.get('scopeSpans',[]):
    for span in scope.get('spans',[]):
     span.setdefault('status',{})['code']=2 if span.get('status',{}).get('code')=='STATUS_CODE_ERROR' else 0
  requests.append({'path':self.path,'headers':dict(self.headers),'body':body,'time':time.monotonic()})
  if behavior=='timeout':time.sleep(5)
  code=503 if behavior=='retry' and len(requests)==1 else 401 if behavior=='unauthorized' else 200
  self.send_response(code);self.send_header('Content-Type','application/x-protobuf');self.end_headers()
  reply=ExportTraceServiceResponse()
  if behavior=='partial':reply.partial_success.rejected_spans=1
  try:self.wfile.write(reply.SerializeToString())
  except (BrokenPipeError,ConnectionResetError):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
url='http://host.docker.internal:'+str(server.server_port)
jar=b/'dist/flashcat-javaagent.jar';sha=hashlib.sha256(jar.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='flashcat-single-jar-') as tmp:
 clean=pathlib.Path(tmp);(clean/'flashcat-javaagent.jar').write_bytes(jar.read_bytes());(clean/'app').mkdir()
 for f in (b/'app').glob('PlainApplication*.class'):(clean/'app'/f.name).write_bytes(f.read_bytes())
 apphash={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (clean/'app').glob('*')}
 def run(jvm,name,opts=(),env=(),mode='ok',attached=True,info=False):
  global behavior
  behavior=mode;requests.clear()
  runtime,platform,java,mount=jvm
  cmd=['docker','run','--rm','--platform',platform,'-v',str(clean)+':/delivery:ro']+mount
  for v in env:cmd+=['-e',v]
  cmd += [runtime,java,'-XX:TieredStopAtLevel=1','-Xverify:all']
  if info:cmd+=['-jar','/delivery/flashcat-javaagent.jar']
  else:
   cmd+=['-Dotel.exporter.otlp.endpoint='+url,'-Dotel.metrics.exporter=none','-Dotel.logs.exporter=none','-Djava6.agent.type=PlainApplication','-Djava6.agent.methods=parent,child,fail,after']+list(opts)
   if attached:cmd+=['-javaagent:/delivery/flashcat-javaagent.jar']
   cmd+=['-cp','/delivery/app','PlainApplication']
  started=time.monotonic();result=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
  assert result.returncode==0,(name,result.stdout,result.stderr)
  assert ('Flashcat Java Agent' if info else 'APPLICATION_OK') in result.stdout,(name,result.stdout,result.stderr)
  record={'jvm':runtime if not mount else 'Oracle6u45','case':name,'seconds':round(time.monotonic()-started,2),'requests':len(requests),'stdout':result.stdout,'stderr':result.stderr}
  records.append(record)
  (b/'delivery-results.json').write_text(json.dumps({'agent_sha256':sha,'app_sha256':apphash,'results':records},indent=2))
  return result
 try:
  for jvm in [('debian:bookworm-slim','linux/amd64','/jdk/bin/java',['-v',str(a.jdk6.resolve())+':/jdk:ro']),('eclipse-temurin:8-jdk','linux/amd64','java',[]),(a.modern_image,'linux/arm64','java',[])]:
   for name in ['info','baseline','normal','disabled','sdk-disabled','invalid-protocol','invalid-secret','retry','partial','unauthorized','timeout','gzip','sampler-off','resource','span-limit','no-export','propagators-none','all-signals']:
    opts=[];env=[];mode='ok'
    if name=='normal':
     opts=['-Dotel.service.name=property-service','-Dotel.exporter.otlp.endpoint='+url+'/','-Dotel.exporter.otlp.traces.endpoint='+url+'/custom','-Dotel.exporter.otlp.traces.headers=Authorization=Bearer%20delivery-test','-Dotel.exporter.otlp.traces.protocol=http/protobuf']
     env=['OTEL_SERVICE_NAME=env-service','OTEL_EXPORTER_OTLP_PROTOCOL=grpc','OTEL_EXPORTER_OTLP_HEADERS=bad=ignored']
    if name=='disabled':opts=['-Dotel.javaagent.enabled=false']
    if name=='sdk-disabled':env=['OTEL_SDK_DISABLED=true']
    if name=='invalid-protocol':opts=['-Dotel.exporter.otlp.protocol=grpc']
    if name=='invalid-secret':opts=['-Dotel.exporter.otlp.headers=Authorization=secret%0D%0AInjected%3Ayes']
    if name in ['retry','partial','unauthorized','timeout','gzip','sampler-off','resource','span-limit','no-export','propagators-none','all-signals']:mode=name
    if name=='all-signals':opts=['-Dotel.metrics.exporter=otlp','-Dotel.logs.exporter=otlp']
    if name=='gzip':opts=['-Dotel.exporter.otlp.compression=gzip']
    if name=='sampler-off':opts=['-Dotel.traces.sampler=always_off']
    if name=='resource':opts=['-Dotel.resource.attributes=deployment.environment.name=acceptance,custom.flag=yes']
    if name=='span-limit':opts=['-Dotel.span.event.count.limit=0']
    if name=='no-export':opts=['-Dotel.traces.exporter=none']
    if name=='propagators-none':opts=['-Dotel.propagators=none']
    if name=='timeout':opts=['-Dotel.exporter.otlp.timeout=1000']
    result=run(jvm,name,opts,env,mode,attached=name!='baseline',info=name=='info')
    if name in ['info','baseline','disabled','sdk-disabled','invalid-protocol','invalid-secret']:
     assert not requests,(name,len(requests))
     if name not in ['info','baseline']:assert 'FLASHCAT_AGENT_DISABLED' in result.stderr
     assert 'secret' not in result.stderr
    elif name=='all-signals':
     assert any(req['body'].get('resourceSpans') for req in requests),requests
     assert any(req['body'].get('resourceMetrics') for req in requests),requests
    elif name in ['sampler-off','no-export']:
     assert not requests and 'JAVA6_AGENT_SDK_READY' in result.stderr
    elif name in ['normal','retry','gzip','resource','span-limit','propagators-none']:
     assert len(requests)==(2 if name=='retry' else 1),(name,len(requests))
     spans=[s for rs in requests[-1]['body']['resourceSpans'] for ss in rs['scopeSpans'] for s in ss['spans']]
     assert len(spans)==15
     assert len({s['traceId'] for s in spans})==6
     parentids={s['spanId'] for s in spans if s['name']=='parent'}
     assert all(s['parentSpanId'] in parentids for s in spans if s['name'] in ['child','fail'])
     assert sum(s.get('status',{}).get('code',0)==2 for s in spans)==3
     if name=='normal':
      assert requests[0]['path']=='/custom' and requests[0]['headers']['Authorization']=='Bearer delivery-test'
      for rs in requests[0]['body']['resourceSpans']:
       attrs={x['key']:x['value'].get('stringValue') for x in rs['resource']['attributes']}
       assert attrs['service.name']=='property-service'
     elif name=='retry':assert requests[0]['body']==requests[1]['body'] and requests[-1]['path']=='/v1/traces'
     if name=='gzip':assert requests[0]['headers']['Content-Encoding']=='gzip'
     if name=='span-limit':assert all(not span.get('events') for span in spans)
     if name=='resource':
      attrs={x['key']:x['value'].get('stringValue') for x in requests[0]['body']['resourceSpans'][0]['resource']['attributes']}
      assert attrs['deployment.environment.name']=='acceptance' and attrs['custom.flag']=='yes'
     assert requests[0]['headers']['Content-Type']=='application/x-protobuf'
    elif name in ['partial','unauthorized']:assert len(requests)==1
    elif name=='timeout':
     assert len(requests)<=1
     if requests:assert time.monotonic()-requests[0]['time']<3, 'export waited for the 5-second server response'
     else:
      normal=next(row for row in records if row['jvm']==records[-1]['jvm'] and row['case']=='normal')
      assert records[-1]['seconds']<normal['seconds']+3, 'pre-request timeout exceeded budget'
    assert apphash=={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (clean/'app').glob('*')}
    print('PASS',records[-1]['jvm'],name,flush=True)
  assert sha==hashlib.sha256(jar.read_bytes()).hexdigest()
 finally:server.shutdown();server.server_close()
print('PASS same standalone JAR, unchanged application, config/failure/export matrix')
