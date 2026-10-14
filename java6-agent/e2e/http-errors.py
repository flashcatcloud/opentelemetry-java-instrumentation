#!/usr/bin/env python3
import argparse,http.server,json,subprocess,threading,base64,hashlib
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from pathlib import Path
from urllib.parse import urlparse
p=argparse.ArgumentParser();p.add_argument('--jdk6',required=True,type=Path);p.add_argument('--no-propagation',action='store_true');p.add_argument('--agent-disabled',action='store_true');p.add_argument('--agent',default='opentelemetry-javaagent-java6.jar');p.add_argument('--image');p.add_argument('--platform',default='linux/amd64');p.add_argument('--host-check',choices=['auto','override']);p.add_argument('--config-failure',choices=['endpoint','exporter','protocol']);a=p.parse_args()
root=Path(__file__).resolve().parents[1];captured=[];headers=[];attempts=[]
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        headers.append(dict(self.headers));code={'/ok':200,'/missing':404,'/failure':503}[self.path]
        self.send_response(code);self.end_headers();self.wfile.write(b'body')
    def do_POST(self):
        request=ExportTraceServiceRequest();request.ParseFromString(self.rfile.read(int(self.headers['Content-Length'])))
        doc=MessageToDict(request);attempts.append(doc)
        if len(attempts)==1: self.send_response(503);self.end_headers();return
        captured.append(doc);self.send_response(200);self.send_header('Content-Type','application/x-protobuf');self.end_headers()
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
url='http://host.docker.internal:'+str(server.server_port)
try:
    cmd=['docker','run','--rm','--platform','linux/amd64','-v',str(root)+':/test:ro','-v',str(a.jdk6.resolve())+':/jdk:ro','debian:bookworm-slim','/jdk/bin/java','-Xverify:all','-javaagent:/test/build/'+a.agent,'-Dotel.exporter.otlp.protocol=http/protobuf','-Dotel.exporter.otlp.endpoint='+url,'-Dotel.metrics.exporter=none','-Dotel.logs.exporter=none','-cp','/test/build/app','HttpClientProbe',url]
    if a.host_check:
        cmd[3:3]=['--hostname','otel-resource-probe']
        if a.host_check=='override':cmd.insert(cmd.index('-cp'),'-Dotel.resource.attributes=host.name=configured-host,service.instance.id=resource-probe')
    if a.config_failure:
        config={'endpoint':'-Dotel.exporter.otlp.endpoint=not-a-url','exporter':'-Dotel.traces.exporter=missing-test-exporter','protocol':'-Dotel.exporter.otlp.protocol=missing-test-protocol'}
        cmd.insert(cmd.index('-cp'),config[a.config_failure])
    if a.agent_disabled:cmd.insert(cmd.index('-cp'),'-Dotel.javaagent.enabled=false')
    if a.no_propagation:cmd.insert(cmd.index('-cp'),'-Dotel.propagators=none')
    if a.image:
        cmd[cmd.index('linux/amd64')]=a.platform
        cmd[cmd.index('debian:bookworm-slim')]=a.image
        cmd[cmd.index('/jdk/bin/java')]='java'
        if a.image.startswith('eclipse-temurin:8'):cmd.insert(cmd.index('-Xverify:all'),'-XX:TieredStopAtLevel=1')
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
    assert r.returncode==0 and 'HTTP_PROBE_OK' in r.stdout,(r.stdout,r.stderr)
    spans=[s for d in captured for rs in d['resourceSpans'] for ss in rs['scopeSpans'] for s in ss['spans']]
    if a.agent_disabled or a.config_failure:
        if a.config_failure:assert 'ERROR' in r.stderr or 'Exception' in r.stderr,(r.stdout,r.stderr)
        assert not spans and not attempts, (spans, attempts)
        assert len(headers)==3
        assert all('traceparent' not in header and 'baggage' not in header for header in headers),headers
    else:
        assert len(spans)==4,spans
        for s in spans:
            at={x['key']:next(iter(x['value'].values())) for x in s['attributes']};path=at.get('url.path') or urlparse(at.get('url.full',at.get('http.url',''))).path
            assert s['kind']=='SPAN_KIND_CLIENT'
            assert s.get('status',{}).get('code','STATUS_CODE_UNSET')==('STATUS_CODE_UNSET' if path=='/ok' else 'STATUS_CODE_ERROR'),(path,s)
            if path=='/unreachable': assert 'http.response.status_code' not in at and s['events']
            else: assert int(at['http.response.status_code'])=={'/ok':200,'/missing':404,'/failure':503}[path]
        assert len(attempts)>=2 and attempts[0]==attempts[1],'retry payload changed'
        assert len(headers)==3
        if a.no_propagation:
            assert all('traceparent' not in header and 'baggage' not in header for header in headers),headers
        else:
            assert all('traceparent' in header for header in headers),headers
            by_path={urlparse(next(x['value']['stringValue'] for x in span['attributes'] if x['key'] in ('url.full','http.url'))).path:span for span in spans}
            for path, header in zip(['/ok','/missing','/failure'],headers):
                span=by_path[path]
                assert header['traceparent'].split('-')[1:3]==[base64.b64decode(span['traceId']).hex(),base64.b64decode(span['spanId']).hex()]
    resource_attributes=[{x['key']:next(iter(x['value'].values())) for x in rs['resource']['attributes']} for d in captured for rs in d['resourceSpans']]
    if a.host_check:
        assert resource_attributes, 'No resources exported'
        for attrs in resource_attributes:
            assert attrs.get('host.name')==('configured-host' if a.host_check=='override' else 'otel-resource-probe'),attrs
            assert attrs.get('host.arch'),attrs
            if a.host_check=='override':assert attrs.get('service.instance.id')=='resource-probe',attrs
    result={'resources':resource_attributes,'host_check':a.host_check,'pass':True,'sha256':hashlib.sha256((root/'build'/a.agent).read_bytes()).hexdigest(),'spans':len(spans),'retry_attempts':len(attempts),'cases':['200','404','503','connection refused'],'command':cmd,'stdout':r.stdout,'stderr':r.stderr}
    (root/('build/e2e/http-errors-'+a.agent+'-'+(a.image or 'java6').replace(':','-')+('-host-'+a.host_check if a.host_check else '')+('-config-'+a.config_failure if a.config_failure else '-disabled' if a.agent_disabled else '-none' if a.no_propagation else '')+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    if a.config_failure:
        print('PASS invalid '+a.config_failure+': diagnosed initialization failure; unchanged HTTP business behavior, no OTLP')
    elif a.agent_disabled:
        print('PASS global Agent disabled: unchanged HTTP behavior, no propagation or OTLP after process exit')
    else:
        print('PASS '+(a.image or 'Java6')+(' propagators=none' if a.no_propagation else ' W3C')+' HTTP 200/404/503/connection failure, W3C injection, OTLP 503 retry, no exporter self-tracing')
finally: server.shutdown();server.server_close()
