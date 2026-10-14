#!/usr/bin/env python3
"""Real Dubbo wire calls on unchanged fixture classes; existing HTTP services are untouched."""
import argparse, concurrent.futures, hashlib, json, shutil, subprocess, time, urllib.error, urllib.request, uuid
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--poc',required=True,type=Path)
p.add_argument('--compare',required=True,type=Path)
p.add_argument('--versions',default='2.5.3,2.5.10,2.6.2,2.6.12')
p.add_argument('--jvms',default='8,6')
p.add_argument('--no-agent',action='store_true')
a=p.parse_args();root=Path(__file__).resolve().parents[1];b=root/'build/dubbo';deps=b/'deps'
deps.mkdir(parents=True,exist_ok=True)
for item in json.loads((root/'e2e/dubbo-deps.json').read_text()):
    dest=deps/Path(item['path']).name
    if not dest.exists(): urllib.request.urlretrieve('https://repo.maven.apache.org/maven2/'+item['path'],dest)
    assert hashlib.sha256(dest.read_bytes()).hexdigest()==item['sha256'],dest
logs=b/'logs';logs.mkdir(exist_ok=True)
def command(cmd):
    x=subprocess.run([str(v) for v in cmd],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
    if x.returncode: raise RuntimeError(str(cmd)+'\n'+x.stdout)
    return x.stdout
common=['docker','run','--rm','--platform','linux/amd64','-v',str(root)+':/agent','-v',str(a.poc)+':/poc:ro','-v',str(a.compare)+':/compare:ro']
cpbase='/agent/build/dubbo/app:/compare/downloads/mysql.jar:/poc/downloads/tomcat-embed-core.jar:/poc/downloads/tomcat-embed-logging-juli.jar:/poc/downloads/annotations.jar'
cpdeps=':'.join('/agent/build/dubbo/deps/'+f.name for f in deps.glob('*.jar') if not f.name.startswith('dubbo-'))
app=b/'app';app.mkdir(exist_ok=True)
command(common+['eclipse-temurin:8-jdk','javac','-J-XX:TieredStopAtLevel=1','-source','6','-target','6','-cp',cpbase+':'+cpdeps+':/agent/build/dubbo/deps/dubbo-2.5.3.jar','-d','/agent/build/dubbo/app','/agent/tests/dubbo/QueryService.java','/agent/tests/dubbo/DubboApp.java'])
original={str(f.relative_to(app)):hashlib.sha256(f.read_bytes()).hexdigest() for f in app.rglob('*.class')}
agent=root/'build/opentelemetry-javaagent-java6.jar';sha=hashlib.sha256(agent.read_bytes()).hexdigest();frozen=b/('agent-'+sha+'.jar')
if not frozen.exists(): shutil.copyfile(agent,frozen)

def read_spans():
    result={}
    for path in (root/'build/e2e').glob('traces*.jsonl'):
        for line in path.read_text().splitlines():
            try: doc=json.loads(line)
            except json.JSONDecodeError: continue
            for rs in doc.get('resourceSpans',[]):
                attrs={x['key']:next(iter(x['value'].values())) for x in rs['resource'].get('attributes',[])}
                for ss in rs['scopeSpans']:
                    for span in ss['spans']:
                        span['service']=attrs.get('service.name');span['runtime']=attrs.get('process.runtime.version')
                        span['a']={x['key']:next(iter(x['value'].values())) for x in span.get('attributes',[])}
                        result[span['spanId']]=span
    return list(result.values())
def request(seed=None,fail=False,sampled=True,slow=False):
    headers={} if seed is None else {'traceparent':'00-'+seed+'-0123456789abcdef-'+('01' if sampled else '00'),'tracestate':'vendor=dubbo','baggage':'tenant=flashcat'}
    req=urllib.request.Request('http://127.0.0.1:18086/call'+('?slow=true' if slow else '?fail=true' if fail else ''),headers=headers)
    try: resp=urllib.request.urlopen(req,timeout=40)
    except urllib.error.HTTPError as e: resp=e
    with resp:
        text=resp.read().decode();assert resp.code==(500 if fail or slow else 200),(resp.code,text)
        expected='timeout' if slow else 'expected-dubbo-business-error' if fail else 'Dubbo JDBC answer=42'
        assert expected in (text.lower() if slow else text),text

def deploy(version,jvm):
    for role in ('a','b'):
        name='java6-dubbo-'+role
        if subprocess.run(['docker','inspect',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0: command(['docker','rm','-f',name])
    for role in ('b','a'):
        name='java6-dubbo-'+role
        cmd=['docker','run','-d','--name',name,'--network','sw6-poc','--restart','unless-stopped','--platform','linux/amd64',
             '--log-opt','max-size=10m','--log-opt','max-file=2','-p','127.0.0.1:'+('18086' if role=='a' else '18087')+':8080',
             '-v',str(root)+':/agent:ro','-v',str(a.poc)+':/poc:ro','-v',str(a.compare)+':/compare:ro','-v',str(frozen)+':/agent.jar:ro',
             '--env-file',str(a.compare/'app.env'),'-e','DUBBO_HOST=java6-dubbo-b','-e','OTEL_SERVICE_NAME=java'+jvm+'-dubbo-'+role,
             '-e','OTEL_EXPORTER_OTLP_ENDPOINT=http://java6-otel-capture:4318']
        cmd+=['debian:bookworm-slim','/poc/oracle6u45-poc/runtime/jdk1.6.0_45/bin/java'] if jvm=='6' else ['eclipse-temurin:8-jdk','java','-XX:TieredStopAtLevel=1']
        cmd+=['-Xverify:all','-Dio.opentelemetry.context.enableStrictContext=true']
        if not a.no_agent: cmd+=['-javaagent:/agent.jar']
        cmd+=['-cp',cpbase+':'+cpdeps+':/agent/build/dubbo/deps/dubbo-'+version+'.jar','example.DubboApp','provider' if role=='b' else 'consumer']
        command(cmd)
        port=18086 if role=='a' else 18087
        for _ in range(90):
            try:
                with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=1) as resp: assert resp.status==200
                break
            except Exception: time.sleep(1)
        else:
            print(command(['docker','logs',name]));raise RuntimeError(name+' not ready')

def check(group,seed,jvm,fail=False):
    assert len(group)==(3 if fail else 4),(seed,group)
    http=next(s for s in group if s['a'].get('http.method')=='GET')
    client=next(s for s in group if s['a'].get('rpc.system')=='apache_dubbo' and s['kind']==3)
    server=next(s for s in group if s['a'].get('rpc.system')=='apache_dubbo' and s['kind']==2)
    assert http['parentSpanId']=='0123456789abcdef'
    assert client['parentSpanId']==http['spanId'] and server['parentSpanId']==client['spanId']
    for s in (client,server):
        assert s['a']['rpc.service']=='example.QueryService' and s['a']['rpc.method']=='query'
        assert int(s['a']['server.port'])==20880
        assert s.get('status',{}).get('code',0)==(2 if fail else 0)
        if fail: assert s.get('events') and s['a']['error.type']=='java.lang.IllegalStateException'
    assert client['a']['server.address']=='java6-dubbo-b'
    assert int(http['a']['http.response.status_code'])==(500 if fail else 200)
    assert all(s['traceId']==seed and s.get('traceState')=='vendor=dubbo' for s in group)
    assert all(s['runtime'].startswith('1.'+jvm+'.') for s in group)
    if not fail:
        db=next(s for s in group if s['a'].get('db.system')=='mysql')
        assert db['parentSpanId']==server['spanId'] and db['kind']==3
        assert db['a']['db.query.text']=='SELECT answer FROM comparison_item WHERE id = ?'
        assert db['a']['server.address']=='sw6-mysql' and int(db['a']['server.port'])==3306
        assert all(s.get('status',{}).get('code',0)==0 for s in group)

report_path=b/('no-agent-results.json' if a.no_agent else 'results.json')
reports=[]
if report_path.exists():
    reports=[row for row in json.loads(report_path.read_text()).get('matrix',[]) if row['agent_sha256']==sha]
for jvm in a.jvms.split(','):
    for version in a.versions.split(','):
        if jvm=='6' and version=='2.6.12':
            print('SKIP 2.6.12 Java 6: bundled Hessian requires Java 7 (major 51)',flush=True);continue
        print('START Dubbo '+version+' Java '+jvm,flush=True)
        deploy(version,jvm)
        seeds=[uuid.uuid4().hex for _ in range(9)];failure=uuid.uuid4().hex;unsampled=uuid.uuid4().hex
        request(seeds[0]);request(failure,True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex: list(ex.map(request,seeds[1:]))
        request(unsampled,sampled=False)
        timeout_seed=uuid.uuid4().hex;request(timeout_seed,slow=True)
        if not a.no_agent:
            expected=set(seeds+[failure,timeout_seed]);deadline=time.time()+35
            while True:
                rows=read_spans();groups={seed:[s for s in rows if s['traceId']==seed] for seed in expected}
                if all(len(groups[x])==(3 if x in (failure,timeout_seed) else 4) for x in expected):break
                if time.time()>deadline: raise AssertionError({k:len(v) for k,v in groups.items()})
                time.sleep(.5)
            for seed in seeds:check(groups[seed],seed,jvm)
            check(groups[failure],failure,jvm,True)
            timed=groups[timeout_seed]
            client=next(s for s in timed if s['kind']==3)
            server=next(s for s in timed if s['a'].get('rpc.system')=='apache_dubbo' and s['kind']==2)
            http=next(s for s in timed if s['a'].get('http.method')=='GET')
            assert client['parentSpanId']==http['spanId'] and server['parentSpanId']==client['spanId']
            assert client['a']['error.type']=='com.alibaba.dubbo.rpc.RpcException' and client['status']['code']==2
            assert server.get('status',{}).get('code',0)==0 and int(http['a']['http.response.status_code'])==500
            assert int(server['endTimeUnixNano'])-int(server['startTimeUnixNano'])>=1000000000
            assert int(client['endTimeUnixNano'])<int(server['endTimeUnixNano'])
            time.sleep(1)
            assert not any(s['traceId']==unsampled for s in read_spans())
            (b/('spans-'+version+'-java'+jvm+'.json')).write_text(json.dumps(groups,indent=2)+'\n')
        for role in ('a','b'):
            log=command(['docker','logs','java6-dubbo-'+role]);(logs/(version+'-java'+jvm+'-'+role+'.log')).write_text(log)
            assert '[Byte Buddy] ERROR' not in log and 'IllegalAccessError' not in log and 'UnsupportedClassVersionError' not in log
        assert original=={str(f.relative_to(app)):hashlib.sha256(f.read_bytes()).hexdigest() for f in app.rglob('*.class')}
        reports=[row for row in reports if (row['dubbo'],row['java'])!=(version,jvm)]
        reports.append(dict(dubbo=version,java=jvm,success_traces=9,error_traces=1,timeout_traces=1,unsampled=not a.no_agent,trace_id=seeds[0],agent_sha256=sha,no_agent=a.no_agent))
        if a.no_agent:
            reports[-1].update(success_requests=9,business_error_requests=1,timeout_requests=1,success_traces=0,error_traces=0,timeout_traces=0)
        (b/('no-agent-results.json' if a.no_agent else 'results.json')).write_text(json.dumps({'matrix':reports,'application_sha256':original},indent=2)+'\n')
        print('PASS '+json.dumps(reports[-1]),flush=True)
