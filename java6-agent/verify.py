#!/usr/bin/env python3
"""Real JVM acceptance: unchanged app bytecode, -javaagent, actual exported SpanData."""
import argparse, hashlib, json, subprocess, sys, time, urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--sdk',required=True,type=Path);p.add_argument('--jdk6',required=True,type=Path);a=p.parse_args()
root=Path(__file__).resolve().parents[1];b=root/'java6-agent/build';b.mkdir(parents=True,exist_ok=True)
logs=b/'logs';logs.mkdir(exist_ok=True);deps=b/'deps';deps.mkdir(exist_ok=True)
jar=deps/'byte-buddy-1.18.14.jar'
sha='b7f2b2f111c6ddc09d3d9718ca5895dde16217bb4e5f2d2a6eb571f274909a82'
if not jar.exists():
    with urllib.request.urlopen('https://repo.maven.apache.org/maven2/net/bytebuddy/byte-buddy/1.18.14/'+jar.name) as r: jar.write_bytes(r.read())
assert hashlib.sha256(jar.read_bytes()).hexdigest()==sha
gson=deps/'gson-2.8.9.jar'
if not gson.exists():
    with urllib.request.urlopen('https://repo.maven.apache.org/maven2/com/google/code/gson/gson/2.8.9/gson-2.8.9.jar') as r: gson.write_bytes(r.read())
assert hashlib.sha256(gson.read_bytes()).hexdigest()=='d3999291855de495c94c743761b8ab5176cfeabe281a5ab0d8e8d45326fd703e'
results=[]
def run(name,cmd,marker=None):
    cmd=[str(x) for x in cmd];start=time.monotonic()
    r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=300)
    (logs/(name+'.log')).write_text(r.stdout)
    results.append(dict(name=name,command=cmd,exit=r.returncode,seconds=round(time.monotonic()-start,2)))
    (b/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    if r.returncode or (marker and marker not in r.stdout):
        print(r.stdout);raise RuntimeError(name+' failed')
    print('PASS '+name,flush=True)
    return r.stdout
common=['docker','run','--rm','--platform','linux/amd64','-v',str(root)+':/repo','-w','/repo/java6-agent']
eight=common+['-v',str(a.sdk.resolve())+':/sdk:ro','-v',str(deps)+':/deps:ro','eclipse-temurin:8-jdk']
six=common+['-v',str(a.jdk6.resolve())+':/jdk:ro','debian:bookworm-slim','/jdk/bin/java','-Xverify:all']
run('prepare',[sys.executable,root/'java6-agent/prepare.py'])
run('prepare-exporter',[sys.executable,root/'java6-agent/prepare-exporter.py','--sdk',a.sdk])
run('prepare-framework',[sys.executable,root/'java6-agent/prepare-framework.py','--sdk',a.sdk])
run('build',eight+['sh','build.sh'])
run('jdk6-links',[sys.executable,root/'java6-agent/check_jdk6.py',a.jdk6/'jre/lib/rt.jar',b/'java6'],'missing JDK6 links: 0')
run('package',[sys.executable,root/'java6-agent/package.py','--sdk',a.sdk])
run('java6-version',six+['-version'],'1.6.0_45')
app=b/'app/PlainApplication.class';original=hashlib.sha256(app.read_bytes()).hexdigest()
run('no-agent',six+['-cp','build/app','PlainApplication'],'APPLICATION_OK')
for name,jvm in [('java6',six),('java6-strict',six+['-Dio.opentelemetry.context.enableStrictContext=true']),('java8',eight+['java','-XX:TieredStopAtLevel=1','-Xverify:all'])]:
    out=b/(name+'.tsv');out.unlink(missing_ok=True)
    log=run(name,jvm+['-Djava6.agent.output=build/'+out.name,'-Djava6.agent.type=PlainApplication','-Djava6.agent.methods=parent,child,fail,after','-javaagent:build/opentelemetry-javaagent-java6.jar','-cp','build/app','PlainApplication'],'APPLICATION_OK')
    assert 'JAVA6_AGENT_SDK_READY' in log and 'ERROR' not in log,log
    spans=[line.split('\t') for line in out.read_text().splitlines()]
    assert len(spans)==15,spans
    assert len({s[2] for s in spans})==15
    roots=[]
    for offset in range(0,15,5):
        group=spans[offset:offset+5]
        parent=next(s for s in group if s[0]=='parent');after=next(s for s in group if s[0]=='after')
        children=[s for s in group if s[0] in ('child','fail')]
        assert len(children)==3
        assert all(s[1]==parent[1] and s[3]==parent[2] for s in children)
        assert parent[3]==after[3]=='0000000000000000' and parent[1]!=after[1]
        roots.extend([parent[1],after[1]])
        failure=next(s for s in group if s[0]=='fail');assert failure[4:] == ['ERROR','1']
        assert all(s[4:] == ['UNSET','0'] for s in group if s[0]!='fail')
    assert len(set(roots))==6,'scope leaked between executor tasks'
    assert original==hashlib.sha256(app.read_bytes()).hexdigest()
    print('PASS '+name+' real spans,parents,error,context restoration,loader isolation,unchanged application',flush=True)
print('PASS agent SDK integration matrix')
