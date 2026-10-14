"""Async lifecycle assertions shared by the isolated legacy Dubbo matrix."""
def attrs(span):
    return {a['key']:next(iter(a['value'].values())) for a in span.get('attributes',[])}

def verify(rows,service,mode,log,rpc_semconv='old'):
    clients=[s for s in rows if s['service']==service]
    expected=50 if mode=='fast' else 3 if mode in ('get','ignored','cancel') else 4
    assert len(clients)==expected,(mode,clients)
    assert len({s['spanId'] for s in clients})==expected,'Duplicate span completion'
    assert all(s['kind']=='SPAN_KIND_CLIENT' for s in clients),clients
    roots=[s for s in clients if not s.get('parentSpanId')]
    assert len(roots)==(26 if mode=='fast' else 3),clients
    assert len({s['traceId'] for s in roots})==len(roots),'Caller context was not restored'
    children=[s for s in clients if s not in roots]
    assert len({s['parentSpanId'] for s in children})==len(children)
    for child in children:
        parent=next(s for s in roots if s['spanId']==child['parentSpanId'])
        assert parent['traceId']==child['traceId'],child
        assert int(child['startTimeUnixNano'])>=int(parent['endTimeUnixNano']),child
    clients.sort(key=lambda s:int(s['startTimeUnixNano']))
    first=clients[0]
    if mode!='fast':
        assert attrs(first)['rpc.method'].split('/')[-1]==('query' if mode=='error' else 'slow'),first
        error=mode in ('error','timeout','cancel')
        assert (first.get('status',{}).get('code')=='STATUS_CODE_ERROR')==error,first
        if error:
            exceptions=[event for event in first.get('events',[]) if event.get('name')=='exception']
            assert exceptions and all(attrs(event).get('exception.type') for event in exceptions),first
            if rpc_semconv!='old':assert attrs(first).get('error.type'),first
        if not error:
            duration=(int(first['endTimeUnixNano'])-int(first['startTimeUnixNano']))/1e6
            returned=int(next(x.split()[1] for x in log.splitlines() if x.startswith('RETURNED ')))
            assert duration>=1400 and int(first['endTimeUnixNano'])/1e6-returned>500,(mode,first,log)
    else:
        assert all(s.get('status',{}).get('code')!='STATUS_CODE_ERROR' for s in clients)
    for client in clients:
        server=next(s for s in rows if s['kind']=='SPAN_KIND_SERVER' and s['traceId']==client['traceId'] and s.get('parentSpanId')==client['spanId'])
        if rpc_semconv=='old':assert attrs(server)['rpc.system']=='apache_dubbo',server
        else:assert attrs(server)['rpc.system.name']=='dubbo',server
        if client==first and mode in ('timeout','cancel'):
            assert int(client['endTimeUnixNano'])<int(server['endTimeUnixNano']),client
