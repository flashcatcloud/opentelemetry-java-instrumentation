import http.server,threading,subprocess,json,os
from pathlib import Path
test_dir=str(Path(os.environ["RUNTIME_RESOURCE_TEST_DIR"]).resolve())
java6_home=os.environ["JAVA6_HOME"]
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
rows=[]
class H(http.server.BaseHTTPRequestHandler):
 def do_GET(self):self.send_response(200);self.end_headers()
 def do_POST(self):
  r=ExportTraceServiceRequest();r.ParseFromString(self.rfile.read(int(self.headers['Content-Length'])))
  for s in r.resource_spans:rows.append({a.key:a.value.string_value for a in s.resource.attributes})
  self.send_response(200);self.end_headers()
 def log_message(self,*a):pass
s=http.server.ThreadingHTTPServer(('0.0.0.0',0),H);threading.Thread(target=s.serve_forever,daemon=True).start()
url='http://host.docker.internal:'+str(s.server_port);results=[]
for v in ['6','8','17']:
 rows.clear()
 cmd=['docker','run','--rm','--platform','linux/amd64','-v',test_dir+':/test:ro','-v',java6_home+':/jdk:ro','debian:bookworm-slim' if v=='6' else 'eclipse-temurin:'+v+'-jdk','/jdk/bin/java' if v=='6' else 'java','-javaagent:/test/flashcat-javaagent.jar','-Dotel.exporter.otlp.protocol=http/protobuf','-Dotel.exporter.otlp.endpoint='+url,'-Dotel.metrics.exporter=none','-Dotel.logs.exporter=none','-Dotel.bsp.schedule.delay=100','-cp','/test','Smoke',url]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
 expected=next((l[9:] for l in p.stdout.splitlines() if l.startswith('EXPECTED=')),None)
 assert p.returncode==0 and rows and expected and all(r.get('process.runtime.version')==expected and r.get('process.runtime.name') and r.get('process.runtime.description') for r in rows),(p.stdout,p.stderr,rows)
 results.append(dict(java=v,expected=expected,resources=rows));print('PASS',v,expected,flush=True)
open(test_dir+'/results.json','w').write(json.dumps(results,indent=2))
