import pathlib,urllib.request,uuid,json,time,concurrent.futures,hashlib,sys
r=pathlib.Path(__file__).resolve().parents[1]
b=r/'build/databases'
def request(mode,sampled=True):
 tid=uuid.uuid4().hex
 req=urllib.request.Request('http://127.0.0.1:18088/call?mode='+mode,headers={'traceparent':'00-'+tid+'-0123456789abcdef-'+('01' if sampled else '00'),'tracestate':'test=java6'})
 with urllib.request.urlopen(req,timeout=30) as res:body=res.read().decode().strip()
 assert body=='A -> Oracle=42 Redis=42',(mode,body)
 return {'mode':mode,'trace_id':tid}
mode=sys.argv[1]
cases=[request(x) for x in ['normal','statement','batch','error','binary','blocking','normal']]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:cases+=list(ex.map(request,['normal']*8))
unsampled=request('normal',False)
hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (b/'app').glob('*.class')}
if mode=='baseline':
 (b/'baseline.json').write_text(json.dumps({'cases':cases,'app_sha256':hashes},indent=2));print('PASS baseline',len(cases));sys.exit()
assert hashes==json.loads((b/'baseline.json').read_text())['app_sha256']
def read():
 out={}
 for p in (r/'build/e2e').glob('traces*.jsonl'):
  for line in p.read_text().splitlines():
   try:d=json.loads(line)
   except ValueError:continue
   for resource in d.get('resourceSpans',[]):
    ra={a['key']:next(iter(a['value'].values())) for a in resource['resource']['attributes']}
    for scope in resource['scopeSpans']:
     for s in scope['spans']:
      s=dict(s);s['service']=ra['service.name'];s['runtime']=ra.get('process.runtime.version');s['a']={a['key']:next(iter(a['value'].values())) for a in s.get('attributes',[])};out[s['spanId']]=s
 return list(out.values())
for attempt in range(60):
 rows=read()
 if all(len([s for s in rows if s['traceId']==c['trace_id'] and s['kind']==2])==2 for c in cases):break
 time.sleep(1)
for c in cases:
 spans=[s for s in rows if s['traceId']==c['trace_id']]
 a=next(s for s in spans if s['service']=='java6-db-a' and s['kind']==2)
 client=next(s for s in spans if s['service']=='java6-db-a' and s['kind']==3)
 server=next(s for s in spans if s['service']=='java6-db-b' and s['kind']==2)
 assert a['parentSpanId']=='0123456789abcdef'
 assert client['parentSpanId']==a['spanId'] and server['parentSpanId']==client['spanId']
 assert all(s['runtime']=='1.6.0_45' and s.get('traceState')=='test=java6' for s in spans)
 db=[s for s in spans if s['a'].get('db.system')]
 oracle=[s for s in db if s['a']['db.system']=='oracle'];redis=[s for s in db if s['a']['db.system']=='redis']
 assert len(oracle)==(2 if c['mode']=='error' else 1),(c,oracle)
 assert len([s for s in redis if s['name']=='SELECT']) in (1,2),(c,redis)
 assert sorted(s['name'] for s in redis if s['name']!='SELECT')==sorted(['SET','GET']+({'error':['LPUSH'],'binary':['GET'],'blocking':['BLPOP']}.get(c['mode'],[]))),(c,redis)
 assert len(spans)==3+len(db),(c,len(spans))
 for s in db:
  assert s['kind']==3 and s['parentSpanId']==server['spanId']
  assert int(s['endTimeUnixNano'])>=int(s['startTimeUnixNano'])
  assert s['a']['db.system']==s['a']['db.system.name']
  assert 'db.namespace' in s['a'] and 'server.address' in s['a'] and int(s['a']['server.port'])>0
 for s in oracle:
  assert s['a']['db.namespace']=='XE'
  assert s['a']['db.query.text']==s['a']['db.statement']
  assert s['a']['server.address']=='host.docker.internal' and int(s['a']['server.port'])==11521
 for s in redis:
  assert s['a']['server.address']=='java6-redis-db' and int(s['a']['server.port'])==6379
  if s['name']!='SELECT':assert s['a']['db.namespace']=='1'
  assert 'db.query.text' not in s['a']
 errors=[s for s in spans if s.get('status',{}).get('code')==2]
 assert len(errors)==(2 if c['mode']=='error' else 0),(c,errors)
 assert all(s['events'] and s['a'].get('error.type') for s in errors)
 if c['mode']=='blocking':
  blocked=next(s for s in redis if s['name']=='BLPOP');assert int(blocked['endTimeUnixNano'])-int(blocked['startTimeUnixNano'])>=900000000
 c['spans']=spans
assert not any(s['traceId']==unsampled['trace_id'] for s in rows)
report={'cases':cases,'app_sha256':hashes,'unsampled':unsampled,'agent_sha256':hashlib.sha256((r/'build/opentelemetry-javaagent-java6.jar').read_bytes()).hexdigest()}
(b/'verification.json').write_text(json.dumps(report,indent=2))
print('PASS Oracle6u45 Oracle/Redis',len(cases),'traces',sum(len(c['spans']) for c in cases),'spans; unchanged business; parents; errors; recovery; blocking; concurrency; unsampled')
print('TRACE',cases[0]['trace_id'])
