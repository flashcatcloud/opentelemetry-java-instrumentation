import pathlib,subprocess,hashlib,os,sys,time,urllib.request,json
r=pathlib.Path(__file__).resolve().parents[1]
poc=pathlib.Path(os.environ['POC_ROOT']).resolve()
b=r/'build/databases';b.mkdir(exist_ok=True)
for dep in json.loads((r/'e2e/databases-deps.json').read_text()):
 f=b/'deps'/dep['file'];f.parent.mkdir(exist_ok=True)
 if not f.exists():
  with urllib.request.urlopen(dep['url'],timeout=30) as response:f.write_bytes(response.read())
 assert hashlib.sha256(f.read_bytes()).hexdigest()==dep['sha256'],f

def run(*a):
 p=subprocess.run([str(x) for x in a],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
 if p.returncode:print(p.stdout);p.check_returncode()
 return p.stdout
cp='/db/app:/deps/ojdbc6.jar:/deps/jedis.jar:/deps/pool.jar:'+':'.join('/poc/downloads/'+n+'.jar' for n in ['tomcat-embed-core','tomcat-embed-logging-juli','annotations'])
if sys.argv[1]=='compile':
 (b/'app').mkdir(exist_ok=True)
 print(run('docker','run','--rm','--platform','linux/amd64','-v',str(b)+':/db','-v',str(b/'deps')+':/deps:ro','-v',str(poc)+':/poc:ro','-v',str(r/'tests')+':/tests:ro','eclipse-temurin:8-jdk','javac','-J-XX:TieredStopAtLevel=1','-source','6','-target','6','-cp',cp,'-d','/db/app','/tests/DatabaseApplication.java'))
else:
 agent=sys.argv[1]=='agent'
 jar=r/'build/opentelemetry-javaagent-java6.jar';sha=hashlib.sha256(jar.read_bytes()).hexdigest();frozen=b/('agent-'+sha+'.jar')
 if not frozen.exists():frozen.write_bytes(jar.read_bytes())
 for role,port in [('b',18089),('a',18088)]:
  name='java6-db-'+role
  subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  args=['docker','run','-d','--name',name,'--platform','linux/amd64','--network','sw6-poc','--restart','unless-stopped','--log-opt','max-size=5m','-p','127.0.0.1:'+str(port)+':8080','-v',str(b)+':/db:ro','-v',str(b/'deps')+':/deps:ro','-v',str(poc)+':/poc:ro','-e','REDIS_HOST=java6-redis-db','-e','JDBC_URL='+os.environ.get('JDBC_URL','jdbc:oracle:thin:@host.docker.internal:11521:XE'),'-e','OTEL_SERVICE_NAME='+name,'-e','OTEL_EXPORTER_OTLP_ENDPOINT=http://java6-otel-capture:4318','debian:bookworm-slim','/poc/oracle6u45-poc/runtime/jdk1.6.0_45/bin/java','-Xverify:all','-Dio.opentelemetry.context.enableStrictContext=true']
  if agent:args+=['-javaagent:/db/'+frozen.name]
  print(run(*(args+['-cp',cp,'DatabaseApplication',role])))
 for port in [18088,18089]:
  for i in range(90):
   try: urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=2).close();break
   except Exception:time.sleep(1)
  else:raise RuntimeError('startup timeout')
 print('READY',sys.argv[1])
