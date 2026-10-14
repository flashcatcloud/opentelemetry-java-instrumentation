#!/usr/bin/env python3
"""Real Java 6 async RPC: lifecycle, callback context and unchanged application bytecode."""
import argparse,hashlib,json,subprocess,time,uuid
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--poc',required=True,type=Path);p.add_argument('--version',default='2.6.2');p.add_argument('--no-agent',action='store_true');p.add_argument('--modes',default='get,ignored,callback,late,error,timeout,cancel,throw,fast');a=p.parse_args()
r=Path(__file__).resolve().parents[1];b=r/'build/dubbo';deps=b/'deps'
cp='/agent/build/dubbo/app:'+':'.join('/agent/build/dubbo/deps/'+f.name for f in deps.glob('*.jar') if not f.name.startswith('dubbo-') or f.name=='dubbo-'+a.version+'.jar')
common=['docker','run','--rm','--platform','linux/amd64','--network','sw6-poc','-v',str(r)+':/agent','-v',str(a.poc)+':/poc:ro']
def run(cmd):
 x=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120)
 if x.returncode:raise RuntimeError(x.stdout)
 return x.stdout
run(common+['eclipse-temurin:8-jdk','javac','-J-XX:TieredStopAtLevel=1','-source','6','-target','6','-cp',cp,'-d','/agent/build/dubbo/app','/agent/tests/dubbo/DubboAsyncProbe.java'])
def hashes():return {str(f.relative_to(b/'app')):hashlib.sha256(f.read_bytes()).hexdigest() for f in (b/'app').glob('example/DubboAsyncProbe*.class')}
original=hashes()
def read():
 rows={}
 for path in (r/'build/e2e').glob('traces*.jsonl'):
  for line in path.read_text().splitlines():
   try:doc=json.loads(line)
   except json.JSONDecodeError:continue
   for rs in doc.get('resourceSpans',[]):
    attrs={x['key']:next(iter(x['value'].values())) for x in rs['resource']['attributes']}
    for ss in rs['scopeSpans']:
     for s in ss['spans']:
      s['service']=attrs.get('service.name');s['runtime']=attrs.get('process.runtime.version');s['a']={x['key']:next(iter(x['value'].values())) for x in s.get('attributes',[])};rows[s['spanId']]=s
 return list(rows.values())
reports=[]
for mode in a.modes.split(','):
 name='java6-dubbo-async-'+mode+'-'+uuid.uuid4().hex[:8]
 cmd=common+['-e','OTEL_SERVICE_NAME='+name,'-e','OTEL_EXPORTER_OTLP_ENDPOINT=http://java6-otel-capture:4318','debian:bookworm-slim','/poc/oracle6u45-poc/runtime/jdk1.6.0_45/bin/java','-Xverify:all','-Dio.opentelemetry.context.enableStrictContext=true']
 if not a.no_agent:cmd+=['-javaagent:/agent/build/opentelemetry-javaagent-java6.jar']
 cmd+=['-cp',cp,'example.DubboAsyncProbe',mode]
 log=run(cmd);(b/'logs'/('async-'+a.version+'-'+mode+('-no-agent' if a.no_agent else '')+'.log')).write_text(log)
 assert 'DUBBO_ASYNC_OK' in log and '1.6.0_45' in log and '[Byte Buddy] ERROR' not in log and 'AssertionError' not in log,log
 if not a.no_agent:
  count=50 if mode=='fast' else 3 if mode in ('get','ignored','cancel') else 4
  for _ in range(30):
   rows=read();clients=[s for s in rows if s['service']==name]
   if len(clients)==count:break
   time.sleep(.5)
  assert len(clients)==count,(mode,clients)
  if mode=='fast':
   roots=[s for s in clients if not s.get('parentSpanId') or s['parentSpanId']=='0000000000000000']
   assert len(roots)==26 and len({s['traceId'] for s in roots})==26,clients
   children=[s for s in clients if s not in roots]
   assert len(children)==24 and len({s['parentSpanId'] for s in children})==24
   for child in children:
    parent=next(s for s in roots if s['spanId']==child['parentSpanId'])
    assert parent['traceId']==child['traceId']
   for client in clients:
    assert client.get('status',{}).get('code',0)==0 and client['runtime'].startswith('1.6.0_45')
    assert any(s['kind']==2 and s['traceId']==client['traceId'] and s.get('parentSpanId')==client['spanId'] for s in rows)
   reports.append(dict(mode=mode,service=name,clients=clients))
   assert hashes()==original
   print('PASS '+a.version+' Java 6 async fast: 24 Futures / 2 in flight, isolated callbacks',flush=True)
   continue
  clients.sort(key=lambda s:int(s['startTimeUnixNano']));first=clients[0]
  assert first['a']['rpc.method']==('query' if mode=='error' else 'slow')
  roots=[s for s in clients if not s.get('parentSpanId') or s['parentSpanId']=='0000000000000000']
  assert len(roots)==3 and len({s['traceId'] for s in roots})==3,clients
  if count==4:
   child=next(s for s in clients if s not in roots)
   assert child['parentSpanId']==first['spanId'] and child['traceId']==first['traceId'],child
   assert int(child['startTimeUnixNano'])>=int(first['endTimeUnixNano']),clients
  assert all(s['runtime'].startswith('1.6.0_45') and s['kind']==3 for s in clients)
  assert first.get('status',{}).get('code',0)==(2 if mode in ('error','timeout','cancel') else 0),first
  if mode in ('error','timeout','cancel'):assert first.get('events') and first['a']['error.type']
  duration=(int(first['endTimeUnixNano'])-int(first['startTimeUnixNano']))/1e6
  returned=int(next(x.split()[1] for x in log.splitlines() if x.startswith('RETURNED ')))
  if mode not in ('error','timeout','cancel'):
   assert duration>=1400,(mode,duration)
   assert int(first['endTimeUnixNano'])/1e6-returned>500,(mode,first,log)
  for client in clients:
   server=next(s for s in rows if s['traceId']==client['traceId'] and s.get('parentSpanId')==client['spanId'] and s['kind']==2)
   assert server['a']['rpc.system']=='apache_dubbo'
   if client==first and mode in ('timeout','cancel'):assert int(first['endTimeUnixNano'])<int(server['endTimeUnixNano'])
   elif client==first and mode!='error':
    # Independent JVMs anchor epoch clocks separately; compare elapsed durations,
    # not sub-millisecond ordering of their absolute timestamps.
    server_ms=(int(server['endTimeUnixNano'])-int(server['startTimeUnixNano']))/1e6
    assert duration>=server_ms-100,(duration,server_ms)
  reports.append(dict(mode=mode,service=name,duration_ms=duration,clients=clients))
 assert hashes()==original
 print('PASS '+a.version+' Java 6 async '+mode+(' no-agent' if a.no_agent else ''),flush=True)
(b/('async-'+a.version+('-no-agent' if a.no_agent else '')+'.json')).write_text(json.dumps(dict(agent_sha256=hashlib.sha256((r/'build/opentelemetry-javaagent-java6.jar').read_bytes()).hexdigest(),application_sha256=original,results=reports),indent=2)+'\n')
