#!/usr/bin/env python3
"""Verify bounded retries, cleanup and recovery using a real HTTP endpoint."""
import argparse, hashlib, json, subprocess, uuid
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--jdk6', required=True, type=Path)
p.add_argument('--image')
p.add_argument('--platform', default='linux/amd64')
p.add_argument('--agent', default='official-loader-candidate.jar')
a = p.parse_args()
r = Path(__file__).resolve().parents[1]
artifact = r / 'build' / a.agent
sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
stage = r / 'build' / ('retry-recovery-' + (a.image or 'java6').replace(':','-'))
stage.mkdir(exist_ok=True)
compiler = 'otel-write-compile-' + uuid.uuid4().hex[:8]
container = 'otel-write-test-' + uuid.uuid4().hex[:8]
result = dict(passed=False, sha256=sha, runtime=a.image or 'Oracle6u45', platform=a.platform)
try:
    subprocess.run(['docker','run','--rm','--name',compiler,'--platform','linux/amd64',
        '-v',str(r)+':/test','-v',str(a.jdk6.resolve())+':/jdk:ro','-w','/test',
        'eclipse-temurin:8-jdk','javac','-J-XX:TieredStopAtLevel=1','-source','6','-target','6',
        '-bootclasspath','/jdk/jre/lib/rt.jar','-d',str(stage.relative_to(r)),
        'tests/SenderRetryRecoveryProbe.java'],check=True,timeout=120)
    cmd=['docker','run','--rm','--name',container,'--platform',a.platform,
         '-v',str(r)+':/test:ro','-v',str(a.jdk6.resolve())+':/jdk:ro',
         a.image or 'debian:bookworm-slim', 'java' if a.image else '/jdk/bin/java',
         '-Xmx256m','-Xverify:all','-javaagent:/test/build/'+a.agent,
         '-Dotel.instrumentation.common.default-enabled=false','-Dotel.traces.exporter=none','-Dotel.metrics.exporter=none','-Dotel.logs.exporter=none',
         '-cp','/test/'+str(stage.relative_to(r)),'SenderRetryRecoveryProbe']
    result['command']=cmd
    run=subprocess.run(cmd,capture_output=True,text=True,timeout=300)
    result.update(exit_code=run.returncode,stdout=run.stdout,stderr=run.stderr)
    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stdout.count('RETRY_RECOVERY_ROUND_OK') == 20, run.stdout
    assert 'RETRY_RECOVERY_OK' in run.stdout, run.stdout
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == sha
    result['passed']=True
    print('PASS',result['runtime'],'bounded retries and recovery passed')
except subprocess.TimeoutExpired as exc:
    result.update(error='process timeout', stdout=(exc.stdout or b'').decode(errors='replace') if isinstance(exc.stdout, bytes) else exc.stdout, stderr=(exc.stderr or b'').decode(errors='replace') if isinstance(exc.stderr, bytes) else exc.stderr)
    raise
finally:
    for name in (compiler,container):
        subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=30)
    out=r/'build/e2e'/('retry-recovery-'+(a.image or 'java6').replace(':','-')+'.json')
    out.write_text(json.dumps(result,indent=2)+'\n')
