#!/usr/bin/env python3
"""Same existing business bytecode, official HTTP server/client and JDBC modules."""
import argparse, base64, concurrent.futures, hashlib, http.server, json, subprocess, threading, time, urllib.request, uuid
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
p=argparse.ArgumentParser();p.add_argument('--network',default='sw6-poc');p.add_argument('--collector-bind',default='127.0.0.1');p.add_argument('--collector-host',default='host.docker.internal');p.add_argument('--poc',required=True,type=Path);p.add_argument('--image');p.add_argument('--dubbo',action='store_true');p.add_argument('--executor',action='store_true');p.add_argument('--forkjoin',action='store_true');p.add_argument('--spring',action='store_true');p.add_argument('--modern-async',action='store_true');p.add_argument('--debug',action='store_true');p.add_argument('--dubbo3',action='store_true');p.add_argument('--dubbo3-version',default='3.0.0');p.add_argument('--without-agent',action='store_true');p.add_argument('--agent',default='official-loader-candidate.jar');p.add_argument('--legacy-dubbo',choices=['2.5.3','2.5.10','2.6.2','2.6.12','2.8.4']);p.add_argument('--async-modes',default='');p.add_argument('--async-baseline',action='store_true');p.add_argument('--dubbox-java6-api',action='store_true');p.add_argument('--no-field-injection',action='store_true');p.add_argument('--platform',default='linux/amd64');p.add_argument('--startup-timeout',type=float,default=75);p.add_argument('--rpc-semconv',choices=['old','stable','both'],default='old');a=p.parse_args()
a.dubbo=a.dubbo or bool(a.legacy_dubbo) or a.modern_async or a.dubbo3
a.executor=a.executor or a.forkjoin
root=Path(__file__).resolve().parents[1];compare=a.poc/'mysql-otel-compare-20261013';captured=[];names=[];async_logs={};passed=False
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        req=ExportTraceServiceRequest();req.ParseFromString(self.rfile.read(int(self.headers['Content-Length'])))
        captured.append(MessageToDict(req));self.send_response(200);self.end_headers()
server=http.server.ThreadingHTTPServer((a.collector_bind,0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
def run(cmd):
    result=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
    if result.returncode:raise RuntimeError(result.stdout)
    return result.stdout.strip()
def attr(items):return {x['key']:next(iter(x['value'].values())) for x in items}
def rows():
    result=[]
    for doc in list(captured):
        for rs in doc.get('resourceSpans',[]):
            service=attr(rs['resource']['attributes'])['service.name']
            for ss in rs['scopeSpans']:
                for span in ss['spans']:result.append(dict(span,service=service))
    return result
suffix=uuid.uuid4().hex[:8];urls={};seed=uuid.uuid4().hex
try:
    for role in ['b','a']:
        name='official-chain-'+suffix+'-'+role;names.append(name)
        cp='/compare/app:/compare/downloads/mysql.jar:/poc/downloads/tomcat-embed-core.jar:/poc/downloads/tomcat-embed-logging-juli.jar:/poc/downloads/annotations.jar'
        if a.spring:
            libraries=[p for p in sorted((root/'build/component-deps').glob('*.jar')) if p.name.startswith(('spring-','httpclient-','httpcore-','commons-logging-','commons-codec-'))]
            cp='/test/build/app:'+':'.join('/test/build/component-deps/'+p.name for p in libraries)+':'+cp
        if a.executor:cp='/test/build/app:'+cp
        if a.dubbo:cp='/test/build/dubbo-modern/app:/test/build/dubbo-modern/deps/*:'+cp
        if a.dubbo3:
            dubbo3_dir='dubbo3' if a.dubbo3_version=='3.0.0' else 'dubbo3-'+a.dubbo3_version
            libraries=[f for f in sorted((root/'build'/dubbo3_dir/'deps').glob('*.jar')) if not f.name.startswith('dubbo-') or f.name=='dubbo-'+a.dubbo3_version+'.jar']
            cp=cp.replace('/test/build/dubbo-modern/deps/*', ':'.join('/test/build/'+dubbo3_dir+'/deps/'+f.name for f in libraries)).replace('/test/build/dubbo-modern/app:', '/test/build/dubbo3/app:')
        if a.legacy_dubbo:
            dependency_dir='dubbox-2.8.4/deps' if a.legacy_dubbo=='2.8.4' else 'dubbo/deps'
            if a.dubbox_java6_api:
                assert a.legacy_dubbo == '2.8.4'
                dependency_dir='dubbox-2.8.4-java6-api/deps'
            deps=sorted((root/'build'/dependency_dir).glob('*.jar'))
            assert any(f.name=='dubbo-'+a.legacy_dubbo+'.jar' for f in deps), 'Missing requested legacy Dubbo artifact'
            cp='/test/build/dubbo/app:'+':'.join('/test/build/'+dependency_dir+'/'+f.name for f in deps if not f.name.startswith('dubbo-') or f.name=='dubbo-'+a.legacy_dubbo+'.jar')+':'+cp.split('/test/build/dubbo-modern/deps/*:',1)[1]
        cmd=['docker','run','-d','--name',name,'--platform',a.platform,'--network',a.network,'-p','127.0.0.1::8080','-v',str(root)+':/test:ro','-v',str(a.poc)+':/poc:ro','-v',str(compare)+':/compare:ro','--env-file',str(compare/'app.env'),'-e','DOWNSTREAM_URL=http://official-chain-'+suffix+'-b:8080/query','-e','DUBBO_HOST=official-chain-'+suffix+'-b','-e','OTEL_SERVICE_NAME='+role,a.image or 'debian:bookworm-slim','java' if a.image else '/poc/oracle6u45-poc/runtime/jdk1.6.0_45/bin/java']
        if a.image and a.image.startswith('eclipse-temurin:8'):cmd+=['-XX:TieredStopAtLevel=1']
        # Dubbo 2.7/Javassist and Hessian require these on Java 17, also without an agent.
        if a.dubbo and a.image and a.image.startswith('eclipse-temurin:17'):
            cmd+=['--add-opens=java.base/java.lang=ALL-UNNAMED','--add-opens=java.base/java.math=ALL-UNNAMED']
        if a.dubbo:cmd+=['-Ddubbo.application.logger=slf4j']
        cmd+=(['-Dotel.javaagent.debug=true'] if a.debug else [])
        cmd+=['-Xverify:all']+(['-Dotel.javaagent.experimental.field-injection.enabled=false'] if a.no_field_injection else [])+['-javaagent:/test/build/'+a.agent,'-Dotel.exporter.otlp.protocol=http/protobuf','-Dotel.exporter.otlp.endpoint=http://'+a.collector_host+':'+str(server.server_port),'-Dotel.metrics.exporter=none','-Dotel.logs.exporter=none','-Dotel.bsp.schedule.delay=100','-Dotel.semconv-stability.opt-in=database,http'+({'old':'','stable':',rpc','both':',rpc/dup'}[a.rpc_semconv]),'-cp',cp]+(['example.ModernDubboAsyncApp' if a.modern_async else 'example.DubboApp','provider' if role=='b' else 'consumer'] if a.dubbo else (['SpringHttpApplication'] if a.spring and role=='a' else ['ForkJoinHttpApplication' if a.forkjoin else 'ExecutorHttpApplication'] if a.executor and role=='a' else ['App',role,'8080']))
        if a.without_agent:cmd=[x for x in cmd if not x.startswith('-javaagent:')]
        run(cmd);urls[role]='http://'+run(['docker','port',name,'8080/tcp'])
        deadline=time.time()+a.startup_timeout
        last_health_error=None
        while time.time()<deadline:
            try:
                with urllib.request.urlopen(urls[role]+'/health',timeout=2) as response:assert response.read().strip()==b'ready'
                break
            except Exception as error:
                last_health_error=repr(error)
                time.sleep(.5)
        else:
            # Preserve a JVM thread dump before the test finally removes its own container.
            subprocess.run(['docker','kill','--signal=QUIT',name],capture_output=True,timeout=10)
            time.sleep(1)
            raise AssertionError('Health check timed out: '+str(last_health_error)+'\n'+run(['docker','logs',name]))
    def request(trace,sampled=True):
        path='/call/42' if a.spring else '/call'
        if a.executor and not a.forkjoin:
            modes=['callable','runnable','scheduled','invokeAll','rejected','cancelled','callable']
            path+='?mode='+modes[traces.index(trace) if trace in traces else 0]
        req=urllib.request.Request(urls['a']+path,headers={'traceparent':'00-'+trace+'-0123456789abcdef-'+('01' if sampled else '00'),'tracestate':'vendor=value'})
        try:
            with urllib.request.urlopen(req,timeout=20) as response:assert response.read().strip()==(b'Dubbo JDBC answer=42' if a.dubbo else b'A -> B JDBC answer=42')
        except urllib.error.HTTPError as error:
            raise AssertionError('HTTP '+str(error.code)+': '+error.read().decode('utf-8',errors='replace')) from error
    traces=[seed]+[uuid.uuid4().hex for _ in range(6)]
    request(seed)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:list(executor.map(request,traces[1:]))
    unsampled=uuid.uuid4().hex;request(unsampled,False)
    time.sleep(3)
    if a.without_agent:
        passed=True
        print("PASS agent-free business calls", a.image or "Java6")
        raise SystemExit(0)
    spans=rows()
    for trace in traces:
        group=[s for s in spans if base64.b64decode(s['traceId']).hex()==trace]
        server_a=next(s for s in group if s['service']=='a' and s['kind']=='SPAN_KIND_SERVER')
        clients=[s for s in group if s['service']=='a' and s['kind']=='SPAN_KIND_CLIENT']
        assert len(clients)==1,group
        client=clients[0]
        server_b=next(s for s in group if s['service']=='b' and s['kind']=='SPAN_KIND_SERVER')
        database=[s for s in group if s['service']=='b' and s['kind']=='SPAN_KIND_CLIENT']
        assert database and any('comparison_item' in attr(s['attributes']).get('db.query.text','') for s in database),group
        assert client['parentSpanId']==server_a['spanId'] and server_b['parentSpanId']==client['spanId'],group
        assert all(s['parentSpanId']==server_b['spanId'] for s in database),group
        if a.spring:
            assert attr(server_a['attributes'])['http.route']=='/call/{id}',server_a
        assert base64.b64decode(server_a['parentSpanId']).hex()=='0123456789abcdef'
        assert all(s.get('traceState')=='vendor=value' for s in group),group
        if a.modern_async:
            assert (int(client['endTimeUnixNano'])-int(client['startTimeUnixNano']))/1e6>=1400,client
        if a.dubbo:
            for rpc in [client,server_b]:
                values=attr(rpc['attributes']);method='slow' if a.modern_async else 'query'
                if a.rpc_semconv=='old':
                    assert values['rpc.system']=='apache_dubbo' and values['rpc.method']==method and 'rpc.system.name' not in values,rpc
                else:
                    assert values['rpc.system.name']=='dubbo' and values['rpc.method'].endswith('/'+method),rpc
                    assert ('rpc.system' in values)==(a.rpc_semconv=='both'),rpc
                    assert ('rpc.service' in values)==(a.rpc_semconv=='both'),rpc
        for span in ([server_a] if a.dubbo else [server_a,client,server_b]):assert int(attr(span['attributes'])['http.response.status_code'])==200,span
    assert not any(base64.b64decode(s['traceId']).hex()==unsampled for s in spans)
    if a.async_modes:
        assert a.legacy_dubbo, 'Async fixture uses the legacy Dubbo API'
        from official_dubbo_async_assertions import verify
        provider_ip=run(['docker','inspect','-f','{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}',names[0]])
        for mode in a.async_modes.split(','):
            service='async-'+mode+'-'+suffix
            async_name='official-chain-'+suffix+'-async-'+mode
            names.append(async_name)
            client=['docker','run','--rm','--name',async_name,'--platform',a.platform,'--network',a.network,'--add-host','java6-dubbo-b:'+provider_ip,'-v',str(root)+':/test:ro','-v',str(a.poc)+':/poc:ro','-v',str(compare)+':/compare:ro','-e','OTEL_SERVICE_NAME='+service,a.image or 'debian:bookworm-slim','java' if a.image else '/poc/oracle6u45-poc/runtime/jdk1.6.0_45/bin/java']
            start=cmd.index('-Xverify:all')
            client+=cmd[start:cmd.index('-cp')]+['-cp',cp.replace('/test/build/dubbo/app:', '/test/build/dubbo-isolated/app:'),'example.DubboAsyncProbe',mode]
            if a.image and a.image.startswith('eclipse-temurin:8'):
                client.insert(client.index('-Xverify:all'),'-XX:TieredStopAtLevel=1')
            if a.image and a.image.startswith('eclipse-temurin:17'):
                client[client.index('-Xverify:all'):client.index('-Xverify:all')]=['--add-opens=java.base/java.lang=ALL-UNNAMED','--add-opens=java.base/java.math=ALL-UNNAMED']
            if a.legacy_dubbo == '2.8.4':
                # Dubbox/Netty 3.7 retains a non-daemon timer after main returns even without Agent.
                # Apply identical external process lifecycle to baseline and instrumented fixtures.
                client.insert(client.index('example.DubboAsyncProbe'), 'ExitAfterMain')
                client[client.index('-cp')+1] = '/test/build/app:' + client[client.index('-cp')+1]
            if a.async_baseline:
                baseline=[arg for arg in client if not arg.startswith('-javaagent:')]
                baseline_log=run(baseline);async_logs[mode+'-no-agent']=baseline_log
                assert 'DUBBO_ASYNC_OK' in baseline_log,baseline_log
            log=run(client);async_logs[mode]=log
            assert 'DUBBO_ASYNC_OK' in log, log
            time.sleep(2)
            verify(rows(),service,mode,log,a.rpc_semconv)
            print('PASS',a.legacy_dubbo,a.image or 'Oracle6u45','async',mode,flush=True)
    passed=True
    print('PASS',a.image or 'Oracle6u45','official HTTP -> '+('Dubbo' if a.dubbo else 'HTTP')+' -> MySQL, 7 traces, concurrent isolation and unsampled parent')
finally:
    evidence={'rpc_semconv':a.rpc_semconv,'legacy_dependency_sha256': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in deps if not f.name.startswith('dubbo-') or f.name == 'dubbo-'+a.legacy_dubbo+'.jar'} if a.legacy_dubbo else {}, 'async_process_lifecycle': 'exit-after-main' if a.legacy_dubbo == '2.8.4' else 'natural-exit', 'async_fixture_sha256':{str(p.relative_to(root/'build/dubbo-isolated/app')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'build/dubbo-isolated/app').glob('example/DubboAsyncProbe*.class')},'async_logs':async_logs,'pass':passed,'field_injection':not a.no_field_injection,'image':a.image or 'Oracle6u45','sha256':hashlib.sha256((root/'build'/a.agent).read_bytes()).hexdigest(),'trace':seed,'captured':captured,'logs':{name:run(['docker','logs',name]) for name in names[:2]}}
    (root/'build/e2e'/('official-chain-'+('rpc-'+a.rpc_semconv+'-' if a.rpc_semconv!='old' else '')+('no-fields-' if a.no_field_injection else '')+('native-' if a.agent!='official-loader-candidate.jar' else '')+('baseline-' if a.without_agent else '')+('dubbo3-'+a.dubbo3_version+'-' if a.dubbo3 else '')+('modern-async-' if a.modern_async else '')+('spring-' if a.spring else '')+('forkjoin-' if a.forkjoin else 'executor-' if a.executor else '')+('dubbo-'+(a.legacy_dubbo+'-' if a.legacy_dubbo else '') if a.dubbo else '')+(a.image or 'java6').replace(':','-')+'.json')).write_text(json.dumps(evidence,indent=2)+'\n')
    for name in names:subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
    server.shutdown();server.server_close()
