#!/usr/bin/env python3
"""Exercise upstream JDBC advice using a tracing-free fixture and a real MySQL server."""
import argparse, hashlib, http.server, json, os, subprocess, threading
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
p=argparse.ArgumentParser()
p.add_argument('--jdk6',required=True,type=Path)
p.add_argument('--driver',required=True,type=Path)
p.add_argument('--image')
p.add_argument('--pool',choices=['dbcp','hikari'])
p.add_argument('--database',choices=['mysql','oracle'],default='mysql')
p.add_argument('--platform',default='linux/amd64')
a=p.parse_args();root=Path(__file__).resolve().parents[1];captured=[]
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        request=ExportTraceServiceRequest();request.ParseFromString(self.rfile.read(int(self.headers['Content-Length'])))
        captured.append(MessageToDict(request));self.send_response(200);self.end_headers()
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    if a.database=='mysql':
        settings=json.loads(subprocess.check_output(['docker','inspect','sw6-mysql']))[0]['Config']['Env']
        password=next(value.split('=',1)[1] for value in settings if value.startswith('MYSQL_ROOT_PASSWORD='))
        user='root';driver='com.mysql.jdbc.Driver';url='jdbc:mysql://sw6-mysql:3306/?useSSL=false&allowPublicKeyRetrieval=true'
    else:
        password=os.environ['JDBC_PASSWORD'];user='otel_poc';driver='oracle.jdbc.OracleDriver'
        url='jdbc:oracle:thin:@host.docker.internal:11521:XE'
    env=dict(os.environ,JDBC_PASSWORD=password)
    cmd=['docker','run','--rm','--platform',a.platform,'--network','sw6-poc','-v',str(root)+':/test:ro','-v',str(a.jdk6)+':/jdk:ro','-v',str(a.driver)+':/driver.jar:ro','-e','JDBC_PASSWORD','-e','JDBC_USER='+user,'-e','JDBC_DRIVER='+driver,'-e','JDBC_URL='+url,a.image or 'debian:bookworm-slim','java' if a.image else '/jdk/bin/java']
    if a.image and a.image.startswith('eclipse-temurin:8'):cmd+=['-XX:TieredStopAtLevel=1']
    cmd+=['-Xverify:all','-javaagent:/test/build/official-loader-candidate.jar','-Dotel.exporter.otlp.protocol=http/protobuf','-Dotel.exporter.otlp.endpoint=http://host.docker.internal:'+str(server.server_port),'-Dotel.metrics.exporter=none','-Dotel.logs.exporter=none','-Dotel.semconv-stability.opt-in=database','-cp','/test/build/app:/driver.jar','JdbcClientProbe']
    if a.pool:
        env['POOL_CLASS']='org.apache.commons.dbcp.BasicDataSource' if a.pool=='dbcp' else 'com.zaxxer.hikari.HikariDataSource'
        index=cmd.index(a.image or 'debian:bookworm-slim');cmd[index:index]=['-e','POOL_CLASS']
        cmd[-1]='PoolJdbcClientProbe';cmd[-2]+=':/test/build/pool-deps/*:/test/build/runtime-deps/*'
    result=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=90)
    evidence={'pass':False,'sha256':hashlib.sha256((root/'build/official-loader-candidate.jar').read_bytes()).hexdigest(),'command':cmd,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'captured':captured}
    path=root/'build/e2e'/('official-jdbc-'+(a.pool+'-' if a.pool else '')+a.database+'-'+(a.image or 'java6').replace(':','-')+'.json')
    path.write_text(json.dumps(evidence,indent=2)+'\n')
    assert result.returncode==0 and 'JDBC_PROBE_OK' in result.stdout,(result.stdout,result.stderr)
    spans=[s for d in captured for rs in d['resourceSpans'] for ss in rs['scopeSpans'] for s in ss['spans']]
    # Connector/J performs one real session-variable SELECT during its handshake.
    queries=[next(x['value']['stringValue'] for x in s['attributes'] if x['key']=='db.query.text') for s in spans]
    if a.database=='mysql':
        if a.pool:
            initialization=[q for q in queries if q not in ('SELECT ? FROM dual','SELECT missing_column FROM dual')]
            assert initialization and all('@@session.auto_increment_increment' in q or q in ('select @@session.transaction_read_only','SELECT @@session.transaction_isolation') for q in initialization),initialization
            assert len(spans)==3+len(initialization),queries
        else:
            assert len(spans)==4 and sum('@@session.auto_increment_increment' in q for q in queries)==1,spans
    else:assert len(spans)==3,spans
    assert queries.count('SELECT ? FROM dual')==2 and queries.count('SELECT missing_column FROM dual')==1,queries
    assert all(s['kind']=='SPAN_KIND_CLIENT' for s in spans),spans
    assert sum(s.get('status',{}).get('code')=='STATUS_CODE_ERROR' for s in spans)==1,spans
    for span in spans:
        attrs={x['key']:next(iter(x['value'].values())) for x in span['attributes']}
        assert attrs['db.system.name']==('oracle.db' if a.database=='oracle' else 'mysql'),attrs
        # Upstream DbServerTargetBuilder omits the database system's default port.
        if a.database=='mysql':assert attrs['server.address']=='sw6-mysql' and 'server.port' not in attrs,attrs
        else:assert attrs['server.address']=='host.docker.internal' and int(attrs['server.port'])==11521,attrs
        assert 'SELECT 42' not in attrs['db.query.text'] and 'SELECT 43' not in attrs['db.query.text'],attrs
    evidence['pass']=True
    path.write_text(json.dumps(evidence,indent=2)+'\n')
    print('PASS',a.database,a.image or 'Oracle6u45','upstream JDBC: statement/prepared/error, SQL sanitization, endpoint, application CLIENT spans and driver behavior')
finally:server.shutdown();server.server_close()
