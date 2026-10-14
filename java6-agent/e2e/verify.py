#!/usr/bin/env python3
import concurrent.futures,hashlib,json,time,uuid,urllib.request
from pathlib import Path
b=Path(__file__).resolve().parents[1]/'build/e2e'
def attrs(a): return {x['key']:next(iter(x['value'].values())) for x in a}
def read():
    result={}
    for p in b.glob('traces*.jsonl'):
        for line in p.read_text().splitlines():
            try: doc=json.loads(line)
            except json.JSONDecodeError: continue # exporter may currently be writing last line
            for rs in doc.get('resourceSpans',[]):
                resource=attrs(rs['resource']['attributes'])
                for ss in rs['scopeSpans']:
                    for s in ss['spans']:
                        s['service']=resource['service.name'];s['a']=attrs(s.get('attributes',[]))
                        result[s['spanId']]=s
    return list(result.values())
def request(seed=None,sampled=True):
    headers={} if seed is None else {'traceparent':'00-'+seed+'-0123456789abcdef-'+('01' if sampled else '00'),'tracestate':'vendor=value','baggage':'tenant=flashcat'}
    r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18084/call',headers=headers),timeout=20)
    assert r.read().decode().strip()=='A -> B JDBC answer=42'
for _ in range(60):
    try:
        urllib.request.urlopen('http://127.0.0.1:18084/health',timeout=2).close()
        urllib.request.urlopen('http://127.0.0.1:18085/health',timeout=2).close()
        break
    except Exception: time.sleep(1)
else: raise RuntimeError('services not ready')
seed=uuid.uuid4().hex
request(seed)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor: list(executor.map(lambda _: request(),range(12)))
end=time.time()+30
while time.time()<end:
    rows=read();spans=[s for s in rows if s['traceId']==seed]
    if len(spans)==4: break
    time.sleep(.5)
assert len(spans)==4,(seed,spans)
def verify(spans):
    assert len(spans)==4
    serverA=next(s for s in spans if s['service']=='java6-otel-a' and s['kind']==2)
    client=next(s for s in spans if s['service']=='java6-otel-a' and s['kind']==3)
    serverB=next(s for s in spans if s['service']=='java6-otel-b' and s['kind']==2)
    db=next(s for s in spans if s['service']=='java6-otel-b' and s['kind']==3)
    assert client['parentSpanId']==serverA['spanId'] and serverB['parentSpanId']==client['spanId'] and db['parentSpanId']==serverB['spanId']
    assert all(s['a']['http.request.method']=='GET' and int(s['a']['http.response.status_code'])==200 for s in [serverA,client,serverB])
    assert db['a']['db.query.text']=='SELECT answer FROM comparison_item WHERE id = ?'
    assert db['a']['db.namespace']=='otel_compare' and db['a']['db.system.name']=='mysql'
    assert db['a']['server.address']=='sw6-mysql' and int(db['a']['server.port'])==3306
    assert all(s.get('status',{}).get('code',0)==0 for s in spans)
    return serverA
server=verify(spans);assert server['parentSpanId']=='0123456789abcdef'
assert all(s.get('traceState')=='vendor=value' for s in spans)
# Wait for all concurrently generated roots to flush.
time.sleep(2)
groups={}
for s in read(): groups.setdefault(s['traceId'],[]).append(s)
good=[]
for tid,group in groups.items():
    if len(group)==4: verify(group);good.append(tid)
assert len(good)>=13,len(good)
unsampled=uuid.uuid4().hex
request(unsampled,False)
time.sleep(2)
assert not any(s['traceId']==unsampled for s in read()),'unsampled remote parent was exported'
report={'unsampled_parent_respected':True,'trace_id':seed,'external_parent':'0123456789abcdef','verified_complete_traces':len(good),'chain':'java6-otel-a SERVER -> java6-otel-a CLIENT -> java6-otel-b SERVER -> MySQL CLIENT','spans':spans}
(b/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='spans'},indent=2))
