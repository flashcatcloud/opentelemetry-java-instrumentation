#!/usr/bin/env python3
"""Run against the Oracle6/Dubbo2.6.2 provider left by dubbo.py."""
import argparse, hashlib, json, subprocess, time, uuid
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--poc',type=Path,required=True);a=p.parse_args()
r=Path(__file__).resolve().parents[1];b=r/'build/dubbo';name='java6-dubbo-reuse-'+uuid.uuid4().hex[:8]
cp='/agent/build/dubbo/app:'+':'.join('/agent/build/dubbo/deps/'+f.name for f in (b/'deps').glob('*.jar') if not f.name.startswith('dubbo-') or f.name=='dubbo-2.6.2.jar')
common=['docker','run','--rm','--platform','linux/amd64','--network','sw6-poc','-v',str(r)+':/agent','-v',str(a.poc)+':/poc:ro']
def run(cmd):
    x=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120)
    if x.returncode: raise RuntimeError(x.stdout)
    return x.stdout
run(common+['eclipse-temurin:8-jdk','javac','-J-XX:TieredStopAtLevel=1','-source','6','-target','6','-cp',cp,'-d','/agent/build/dubbo/app','/agent/tests/dubbo/DubboReuseProbe.java'])
cmd=common+['-e','OTEL_SERVICE_NAME='+name,'-e','OTEL_EXPORTER_OTLP_ENDPOINT=http://java6-otel-capture:4318','debian:bookworm-slim','/poc/oracle6u45-poc/runtime/jdk1.6.0_45/bin/java','-Xverify:all','-Dio.opentelemetry.context.enableStrictContext=true','-javaagent:/agent/build/opentelemetry-javaagent-java6.jar','-cp',cp,'example.DubboReuseProbe']
log=run(cmd);(b/'logs/reuse.log').write_text(log);assert 'DUBBO_REUSE_OK' in log and '[Byte Buddy] ERROR' not in log

def read():
    rows={}
    for path in (r/'build/e2e').glob('traces*.jsonl'):
        for line in path.read_text().splitlines():
            try: doc=json.loads(line)
            except json.JSONDecodeError:continue
            for rs in doc.get('resourceSpans',[]):
                attrs={x['key']:next(iter(x['value'].values())) for x in rs['resource']['attributes']}
                for ss in rs['scopeSpans']:
                    for s in ss['spans']:s['service']=attrs.get('service.name');rows[s['spanId']]=s
    return list(rows.values())
for _ in range(30):
    rows=read();clients=[s for s in rows if s['service']==name]
    if len(clients)==3 and sum(1 for s in rows if any(s['traceId']==c['traceId'] for c in clients))==8:break
    time.sleep(1)
assert len(clients)==3 and len({s['traceId'] for s in clients})==3,clients
assert all(s.get('parentSpanId','0000000000000000')=='0000000000000000' for s in clients)
assert all(s['traceId']!='11111111111111111111111111111111' and not s.get('traceState') for s in clients)
assert sorted(s.get('status',{}).get('code',0) for s in clients)==[0,0,2]
for client in clients:
    group=[s for s in rows if s['traceId']==client['traceId']]
    assert len(group)==(2 if client.get('status',{}).get('code')==2 else 3),group
    server=next(s for s in group if s['kind']==2)
    assert server['parentSpanId']==client['spanId']
    for s in group:
        if s!=client and s!=server:assert s['parentSpanId']==server['spanId']
report={'service':name,'attachment_restoration':True,'same_thread_scope_restoration':True,'stale_trace_not_reused':True,'agent_sha256':hashlib.sha256((r/'build/opentelemetry-javaagent-java6.jar').read_bytes()).hexdigest(),'clients':clients,'command':cmd}
(b/'reuse.json').write_text(json.dumps(report,indent=2)+'\n');print('PASS Dubbo attachment restoration, scope cleanup after error, three independent roots')
