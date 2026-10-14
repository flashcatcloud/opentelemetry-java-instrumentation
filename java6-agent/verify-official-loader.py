#!/usr/bin/env python3
"""Verify the official Agent installer, not component tracing coverage."""
import argparse,json,subprocess,time,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--sdk',type=Path,required=True);p.add_argument('--jdk6',type=Path,required=True);p.add_argument('--logging',choices=['default','none','simple'],default='default');a=p.parse_args()
r=Path(__file__).resolve().parents[1];b=r/'java6-agent/build';results=[]
(b/'logs').mkdir(parents=True,exist_ok=True)
(b/'app').mkdir(parents=True,exist_ok=True)
artifact=b/'official-loader-candidate.jar'
artifact_sha=hashlib.sha256(artifact.read_bytes()).hexdigest()
subprocess.run(['docker','run','--rm','--platform','linux/amd64','-v',str(r)+':/repo','-w','/repo/java6-agent','eclipse-temurin:8-jdk','javac','-J-XX:TieredStopAtLevel=1','-source','6','-target','6','-d','build/app','tests/PlainApplication.java','tests/OfficialLoaderProbe.java'],check=True)
for version,image,platform,executable in [('6','debian:bookworm-slim','linux/amd64','/jdk/bin/java'),('8','eclipse-temurin:8-jdk','linux/amd64','java'),('17','eclipse-temurin:17-jre','linux/arm64','java')]:
 command=['docker','run','--rm','--platform',platform,'-v',str(r)+':/repo:ro','-v',str(a.sdk.resolve())+':/sdk:ro','-v',str(a.jdk6.resolve())+':/jdk:ro','-w','/repo/java6-agent',image,executable,'-Xverify:all']
 if version=='8':command+=['-XX:TieredStopAtLevel=1']
 if a.logging!='default':command+=['-Dotel.javaagent.logging='+a.logging]
 command+=['-Dotel.traces.exporter=none','-Dotel.metrics.exporter=none','-Dotel.logs.exporter=none','-javaagent:build/official-loader-candidate.jar','-cp','build/app','OfficialLoaderProbe']
 started=time.monotonic();process=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120)
 (b/'logs'/('official-loader-java'+version+'.log')).write_text(process.stdout)
 passed=process.returncode==0 and 'OFFICIAL_LOADER_OK installed=true bootstrap=true isolated=true' in process.stdout
 if a.logging!='none':passed=passed and 'Unrecognized value' not in process.stdout and 'opentelemetry-javaagent - version:' in process.stdout
 assert hashlib.sha256(artifact.read_bytes()).hexdigest()==artifact_sha,'Agent changed during verification'
 results.append(dict(sha256=artifact_sha,logging=a.logging,jvm=version,command=command,exit=process.returncode,passed=passed,seconds=round(time.monotonic()-started,2)))
 (b/('official-loader-'+a.logging+'-results.json')).write_text(json.dumps(results,indent=2)+'\n')
 print(process.stdout,flush=True)
 if not passed:raise RuntimeError('official loader failed on Java '+version)
