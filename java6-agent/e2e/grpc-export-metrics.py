#!/usr/bin/env python3
"""Capture actual OTLP gRPC traces and runtime metrics from an unchanged HTTP fixture."""
import argparse, concurrent.futures, hashlib, http.server, json, subprocess, threading, time
from pathlib import Path
import grpc
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest, ExportTraceServiceResponse
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest, ExportMetricsServiceResponse
p=argparse.ArgumentParser();p.add_argument('--jdk6',type=Path,required=True);p.add_argument('--image');p.add_argument('--bind',default='127.0.0.1');p.add_argument('--host',default='host.docker.internal');p.add_argument('--network');p.add_argument('--forward-grpc');p.add_argument('--service',default='grpc-metrics-acceptance');p.add_argument('--tls',choices=['trusted','untrusted','hostname-mismatch','unsupported']);a=p.parse_args()
r=Path(__file__).resolve().parents[1];jar=r/'build/official-loader-candidate.jar'
# Compile the test lifecycle helper with the real Java 6 compiler. It is not Agent code.
subprocess.run(['docker','run','--rm','--platform','linux/amd64','-v',str(r)+':/test','-v',str(a.jdk6)+':/jdk:ro','debian:bookworm-slim','/jdk/bin/javac','-source','6','-target','6','-cp','/test/build/app','-d','/test/build/app','/test/tests/RuntimeMetricsHttpProbe.java'],check=True,timeout=90)
traces=[];metrics=[];business=[];metadata=[];forward_acks=[];forward_errors=[]
class Business(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  business.append(self.path)
  time.sleep(.5);self.send_response({'/ok':200,'/missing':404,'/failure':503}[self.path]);self.end_headers();self.wfile.write(b'body')
http=http.server.ThreadingHTTPServer((a.bind,0),Business);threading.Thread(target=http.serve_forever,daemon=True).start()
forward=grpc.insecure_channel(a.forward_grpc) if a.forward_grpc else None
def receive(target,cls,method):
 def handle(payload,context):
  metadata.append(dict(context.invocation_metadata()));target.append(MessageToDict(cls.FromString(payload)))
  if forward is not None:
   try:
    response=forward.unary_unary(method)(payload,timeout=10)
    decoded=(ExportTraceServiceResponse if cls is ExportTraceServiceRequest else ExportMetricsServiceResponse).FromString(response)
    partial=decoded.partial_success
    rejected=partial.rejected_spans if cls is ExportTraceServiceRequest else partial.rejected_data_points
    if rejected or partial.error_message:raise RuntimeError(str(partial))
    forward_acks.append(method);return response
   except Exception as failure:
    forward_errors.append(str(failure));context.abort(grpc.StatusCode.UNAVAILABLE,str(failure))
  return b''
 return handle
pool=concurrent.futures.ThreadPoolExecutor(max_workers=4);server=grpc.server(pool)
server.add_generic_rpc_handlers([grpc.method_handlers_generic_handler('opentelemetry.proto.collector.'+signal+'.v1.'+name,{'Export':grpc.unary_unary_rpc_method_handler(receive(target,cls,'/opentelemetry.proto.collector.'+signal+'.v1.'+name+'/Export'))}) for signal,name,target,cls in [('trace','TraceService',traces,ExportTraceServiceRequest),('metrics','MetricsService',metrics,ExportMetricsServiceRequest)]])
certificate=None
if a.tls:
 stage=r/'build/grpc-tls';stage.mkdir(exist_ok=True)
 certificate=stage/'certificate.pem';key=stage/'key.pem';config=stage/'openssl.cnf'
 certificate_host='wrong-host.invalid' if a.tls=='hostname-mismatch' else a.host
 config.write_text('[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n[dn]\nCN='+certificate_host+'\n[ext]\nsubjectAltName=DNS:'+certificate_host+'\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,digitalSignature,keyEncipherment,keyCertSign\n')
 subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-sha256','-days','2','-keyout',str(key),'-out',str(certificate),'-config',str(config)],check=True,capture_output=True)
 port=server.add_secure_port(a.bind+':0',grpc.ssl_server_credentials([(key.read_bytes(),certificate.read_bytes())]))
else:port=server.add_insecure_port(a.bind+':0')
assert port;server.start()
cmd=['docker','run','--rm','--platform','linux/amd64','-v',str(r)+':/test:ro','-v',str(a.jdk6)+':/jdk:ro',a.image or 'debian:bookworm-slim','java' if a.image else '/jdk/bin/java','-XX:TieredStopAtLevel=1','-Xverify:all','-javaagent:/test/build/official-loader-candidate.jar','-Dotel.service.name='+a.service,'-Dotel.exporter.otlp.protocol=grpc','-Dotel.exporter.otlp.endpoint='+('https://' if a.tls else 'http://')+a.host+':'+str(port),'-Dotel.metrics.exporter=otlp','-Dotel.logs.exporter=none','-Dotel.metric.export.interval=250','-Dotel.exporter.otlp.timeout=5000','-Dotel.exporter.otlp.headers=Authorization=Bearer%20test-only','-Dotel.exporter.otlp.compression=gzip','-cp','/test/build/app','RuntimeMetricsHttpProbe','http://'+a.host+':'+str(http.server_port)]
if a.network:cmd[2:2]=['--network',a.network]
if a.tls in ('trusted','hostname-mismatch','unsupported'):cmd.insert(cmd.index('-cp'),'-Dotel.exporter.otlp.certificate=/test/build/grpc-tls/certificate.pem')
passed=False;output={}
try:
 result=subprocess.run(cmd,capture_output=True,text=True,timeout=120);output=dict(stdout=result.stdout,stderr=result.stderr,exit_code=result.returncode)
 assert result.returncode==0 and 'HTTP_PROBE_OK' in result.stdout,output
 assert sorted(business)==['/failure','/missing','/ok'],business
 spans=[s for t in traces for rs in t.get('resourceSpans',[]) for ss in rs.get('scopeSpans',[]) for s in ss.get('spans',[])]
 if a.tls in ('untrusted','hostname-mismatch','unsupported'):
  assert not spans and not metrics,'TLS failure must not silently export in plaintext'
  diagnostics=(result.stdout+'\n'+result.stderr).lower()
  expected=('pkix','certificate','certpath') if a.tls=='untrusted' else (('subject alternative','no name matching','hostname','certificate') if a.tls=='hostname-mismatch' else ('alpn','ssl','protocol','tls'))
  assert any(value in diagnostics for value in expected),diagnostics
 else:
  assert len(spans)==4,(len(spans),output)
  names={m['name'] for t in metrics for rs in t.get('resourceMetrics',[]) for ss in rs.get('scopeMetrics',[]) for m in ss.get('metrics',[])}
  assert {'jvm.memory.used','jvm.thread.count','jvm.class.loaded'}<=names,(names,output)
  for required in ('jvm.memory.used','jvm.thread.count','jvm.class.loaded'):
   points=[point for batch in metrics for resource in batch.get('resourceMetrics',[]) for scope in resource.get('scopeMetrics',[]) for metric in scope.get('metrics',[]) if metric['name']==required for point in metric.get('sum',metric.get('gauge',{})).get('dataPoints',[])]
   assert points and any(float(point.get('asInt',point.get('asDouble',0)))>0 for point in points),(required,points)
  assert all(span.get('kind')=='SPAN_KIND_CLIENT' for span in spans),spans

  assert metadata and all(x.get('authorization')=='Bearer test-only' for x in metadata),metadata
  if forward is not None:assert forward_acks and not forward_errors,(forward_acks,forward_errors)
 passed=True
finally:
 server.stop(0).wait();pool.shutdown();http.shutdown();http.server_close()
 if forward is not None:forward.close()
 target=r/'build/e2e'/('grpc-export-metrics-'+(a.image or 'java6').replace(':','-').replace('/','-')+('-tls-'+a.tls if a.tls else '')+'.json');target.parent.mkdir(exist_ok=True)
 target.write_text(json.dumps(dict(sha256=hashlib.sha256(jar.read_bytes()).hexdigest(),command=cmd,passed=passed,business=business,traces=traces,metrics=metrics,metadata=metadata,forward_acks=forward_acks,forward_errors=forward_errors,**output),indent=2)+'\n');print(target,flush=True)
