#!/usr/bin/env python3
"""Four business-only services across Java 6/8/17; verifies real cross-protocol spans."""
import argparse,base64,concurrent.futures,hashlib,http.server,json,os,subprocess,threading,time,urllib.request,uuid
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
p=argparse.ArgumentParser();p.add_argument('--poc',type=Path,required=True);p.add_argument('--without-agent',action='store_true');p.add_argument('--continuous',action='store_true');p.add_argument('--agent',default='official-loader-candidate.jar');p.add_argument('--capture-bind',default='127.0.0.1');p.add_argument('--capture-host',default='host.docker.internal');p.add_argument('--oracle-url',default='jdbc:oracle:thin:@host.docker.internal:11521:XE');p.add_argument('--java17-image',default='eclipse-temurin:17-jdk');p.add_argument('--compiler-image',default='eclipse-temurin:8-jdk@sha256:3a280002b0d1212a62e9f5095c10b07ef3b62c1b13916fe093438e7e9af44b8b');a=p.parse_args()
root=Path(__file__).resolve().parents[1];compare=a.poc/'mysql-otel-compare-20261013';suffix=uuid.uuid4().hex[:8];topic='mixed-'+suffix;names=[];captured=[];passed=False;urls={};logs={};forward=False
service_names={'entry':'mixed-java8-entry','legacy':'mixed-java6-dubbox','bridge':'mixed-java8-bridge','worker':'mixed-java17-worker'}
assert not (a.continuous and a.without_agent)
def run(cmd,**kwargs):
 r=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180,**kwargs)
 if r.returncode:raise RuntimeError(r.stdout)
 return r.stdout.strip()
def attrs(items):return {x['key']:next(iter(x['value'].values())) for x in items}
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  payload=self.rfile.read(int(self.headers['Content-Length']));req=ExportTraceServiceRequest();req.ParseFromString(payload);captured.append(MessageToDict(req))
  if forward:
   del captured[:-100]
   try:
    with urllib.request.urlopen(urllib.request.Request('http://10.98.1.111:4418/v1/traces',data=payload,headers={'Content-Type':'application/x-protobuf'}),timeout=5) as response:response.read()
   except Exception as error:
    print('FORWARD_ERROR',type(error).__name__,flush=True);self.send_response(503);self.end_headers();return
  self.send_response(200);self.end_headers()
server=http.server.ThreadingHTTPServer((a.capture_bind,0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
def spans():return [dict(s,service=next(k for k,v in service_names.items() if v==attrs(rs['resource']['attributes'])['service.name'])) for d in list(captured) for rs in d.get('resourceSpans',[]) for ss in rs.get('scopeSpans',[]) for s in ss.get('spans',[])]
base='/test/build/mixed/app:/compare/downloads/mysql.jar:/poc/downloads/tomcat-embed-core.jar:/poc/downloads/tomcat-embed-logging-juli.jar:/poc/downloads/annotations.jar'
legacy='/test/build/dubbox-2.8.4-java6-api/deps/*'
modern=':'.join('/test/build/dubbo3-3.2.15/deps/'+f.name for f in sorted((root/'build/dubbo3-3.2.15/deps').glob('*.jar')) if not f.name.startswith('dubbo-') or f.name=='dubbo-3.2.15.jar')
spring=':'.join('/test/build/component-deps/'+f.name for f in sorted((root/'build/component-deps').glob('*.jar')) if f.name.startswith(('spring-','commons-logging-')))
kafka=':'.join('/test/build/kafka-3.7.1/deps/'+f.name for f in sorted((root/'build/kafka-3.7.1/deps').glob('*.jar')) if not f.name.startswith('slf4j-'))
try:
 (root/'build/mixed/app').mkdir(parents=True,exist_ok=True)
 mount=['docker','run','--rm','--name','mixed-compile-'+suffix,'--platform','linux/amd64','-v',str(root)+':/test','-v',str(a.poc)+':/poc:ro','-v',str(compare)+':/compare:ro',a.compiler_image,'javac','-J-XX:TieredStopAtLevel=1','-d','/test/build/mixed/app']
 source='/test/tests/mixed/'
 run(mount+['-source','6','-target','6','-bootclasspath','/poc/oracle6u45-poc/runtime/jdk1.6.0_45/jre/lib/rt.jar','-cp',base+':'+legacy+':'+spring+':/test/build/component-deps/jedis.jar',source+'Business.java',source+'QueryService.java',source+'LegacyService.java',source+'EntryService.java'])
 run(mount+['-source','8','-target','8','-cp',base+':'+modern+':'+kafka,source+'ModernService.java'])
 print('COMPILE_OK',flush=True)
 run(['docker','exec','official-javaagent-kafka','/opt/kafka/bin/kafka-topics.sh','--bootstrap-server','localhost:9092','--create','--topic',topic,'--partitions','1','--replication-factor','1'])
 for role,jvm in [('worker','17'),('bridge','8'),('legacy','6'),('entry','8')]:
  n='mixed-'+suffix+'-'+role;names.append(n)
  cp=base+':'+(legacy+':'+spring+':/test/build/component-deps/jedis.jar:/test/build/databases/deps/ojdbc6.jar' if role in ('legacy','entry') else modern+':'+kafka)
  cmd=['docker','run','-d','--name',n,'--hostname',n,'--platform','linux/amd64','--network','sw6-poc','-p','127.0.0.1::8080','-v',str(root)+':/test:ro','-v',str(a.poc)+':/poc:ro','-v',str(compare)+':/compare:ro','--env-file',str(compare/'app.env'),'-e','OTEL_SERVICE_NAME='+service_names[role],'-e','DUBBO_HOST=mixed-'+suffix+('-legacy' if role=='entry' else '-worker'),'-e','DOWNSTREAM_URL=http://mixed-'+suffix+'-bridge:8080/call','-e','REDIS_HOST=java6-redis-db','-e','KAFKA_BROKER=official-javaagent-kafka:9092','-e','KAFKA_TOPIC='+topic]
  env=dict(os.environ)
  if role=='legacy':
   env['JDBC_PASSWORD']=os.environ['ORACLE_PASSWORD'];cmd+=['-e','JDBC_URL='+a.oracle_url,'-e','JDBC_USER=otel_poc','-e','JDBC_PASSWORD']
  cmd+=['debian:bookworm-slim' if jvm=='6' else a.java17_image if jvm=='17' else 'eclipse-temurin:8-jdk','/poc/oracle6u45-poc/runtime/jdk1.6.0_45/bin/java' if jvm=='6' else 'java','-Xmx128m','-Xverify:all','-Ddubbo.application.logger=slf4j']
  if jvm=='8':cmd+=['-XX:TieredStopAtLevel=1']
  if jvm=='17':cmd+=['--add-opens=java.base/java.lang=ALL-UNNAMED','--add-opens=java.base/java.math=ALL-UNNAMED']
  if not a.without_agent:cmd+=['-javaagent:/test/build/'+a.agent,'-Dotel.exporter.otlp.endpoint=http://'+a.capture_host+':'+str(server.server_port),'-Dotel.exporter.otlp.protocol=http/protobuf','-Dotel.metrics.exporter=none','-Dotel.logs.exporter=none','-Dotel.bsp.schedule.delay=100','-Dotel.semconv-stability.opt-in=database,http,messaging']
  cmd+=['-cp',cp]+(['mixed.EntryService'] if role=='entry' else ['mixed.LegacyService'] if role=='legacy' else ['mixed.ModernService',role])
  run(cmd,env=env);url='http://'+run(['docker','port',n,'8080/tcp']);urls[role]=url;deadline=time.time()+180
  while True:
   try:
    with urllib.request.urlopen(url+'/health',timeout=3) as r:assert r.read().strip()==b'ready'
    break
   except Exception:
    if time.time()>deadline:raise AssertionError('startup '+role+'\n'+run(['docker','logs',n]))
    time.sleep(1)
  print('READY',role,jvm,flush=True)
 traces=[uuid.uuid4().hex for _ in range(4)]
 def request(i,trace=None):
  req=urllib.request.Request(urls['entry']+'/call/'+('async' if i%2 else 'sync'),headers={'traceparent':'00-'+(trace or traces[i])+'-0123456789abcdef-01'})
  with urllib.request.urlopen(req,timeout=90) as r:assert r.read().strip()==b'42'
 for i in range(2):request(i)
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(request,[2,3]))
 deadline=time.time()+45
 while time.time()<deadline:
  if run(['docker','logs',names[0]]).count('PROCESSED ')>=4:break
  time.sleep(1)
 else:raise AssertionError('Kafka business delivery incomplete')
 if not a.without_agent:
  deadline=time.time()+20
  while time.time()<deadline:
   rows=spans()
   if all(sum(base64.b64decode(s['traceId']).hex()==trace for s in rows)>=15 for trace in traces):break
   time.sleep(.5)
  for trace in traces:
   group=[s for s in rows if base64.b64decode(s['traceId']).hex()==trace];ids={s['spanId']:s for s in group}
   assert len(group)==15 and len(ids)==15,group
   assert {s['service'] for s in group}=={'entry','legacy','bridge','worker'},group
   root_span=next(s for s in group if s['service']=='entry' and s['kind']=='SPAN_KIND_SERVER')
   assert base64.b64decode(root_span['parentSpanId']).hex()=='0123456789abcdef',root_span
   for s in group:
    if s is not root_span:assert s.get('parentSpanId') in ids,s
    assert s.get('status',{}).get('code')!='STATUS_CODE_ERROR',s
   databases={attrs(s.get('attributes',[])).get('db.system.name') for s in group}
   assert {'oracle.db','mysql','redis'}.issubset(databases),databases
   assert sum(s['kind']=='SPAN_KIND_PRODUCER' for s in group)==1,group
   assert sum(s['kind']=='SPAN_KIND_CONSUMER' for s in group)==1,group
   for svc in ('entry','legacy','bridge','worker'):
    assert any(attrs(s.get('attributes',[])).get('rpc.system')=='apache_dubbo' for s in group if s['service']==svc),svc
 passed=True;print('PASS mixed four-service chain', 'without agent' if a.without_agent else 'with agent',flush=True)
 if a.continuous:
  (root/'build/e2e/mixed-chain-live-validation.json').write_text(json.dumps({'pass':True,'sha256':hashlib.sha256((root/'build'/a.agent).read_bytes()).hexdigest(),'captured':captured,'containers':names,'urls':urls},indent=2))
  forward=True;print('CONTINUOUS forwarding to 10.98.1.111:4418',flush=True)
  i=0
  while True:
   try:request(i%2,uuid.uuid4().hex);print('TRAFFIC_OK',i,flush=True)
   except Exception as error:print('TRAFFIC_ERROR',type(error).__name__,flush=True)
   i+=1;time.sleep(10)
finally:
 subprocess.run(['docker','rm','-f','mixed-compile-'+suffix],capture_output=True,timeout=30)
 for n in names:
  log_result=subprocess.run(['docker','logs',n],capture_output=True,text=True,timeout=30)
  logs[n]=log_result.stdout+log_result.stderr
  subprocess.run(['docker','rm','-f',n],capture_output=True,timeout=30)
 subprocess.run(['docker','exec','official-javaagent-kafka','/opt/kafka/bin/kafka-topics.sh','--bootstrap-server','localhost:9092','--delete','--topic',topic],capture_output=True,timeout=30)
 server.shutdown();server.server_close()
 (root/'build/e2e'/('mixed-chain-baseline.json' if a.without_agent else 'mixed-chain.json')).write_text(json.dumps({'pass':passed,'sha256':hashlib.sha256((root/'build'/a.agent).read_bytes()).hexdigest(),'logs':logs,'captured':captured},indent=2))
