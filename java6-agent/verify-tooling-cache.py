#!/usr/bin/env python3
"""Verify upstream tooling class caches on real JVMs; not an agent E2E claim."""
import argparse,json,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--sdk',type=Path,required=True);p.add_argument('--jdk6',type=Path,required=True);a=p.parse_args()
r=Path(__file__).resolve().parents[1];b=r/'java6-agent/build';results=[]
for version,image,platform,executable in [('6','debian:bookworm-slim','linux/amd64','/jdk/bin/java'),('8','eclipse-temurin:8-jdk','linux/amd64','java'),('17','eclipse-temurin:17-jre','linux/arm64','java')]:
 command=['docker','run','--rm','--platform',platform,'-v',str(r)+':/repo:ro','-v',str(a.sdk.resolve())+':/sdk:ro','-v',str(a.jdk6.resolve())+':/jdk:ro','-w','/repo/java6-agent',image,executable,'-Xverify:all']
 if version=='8':command+=['-XX:TieredStopAtLevel=1']
 command+=['-Dio.opentelemetry.context.enableStrictContext=true','-cp','build/tooling-java6:/sdk/java6-compat/build/dist/*','ToolingClassCacheTest']
 started=time.monotonic();process=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120)
 (b/'logs'/('tooling-class-cache-java'+version+'.log')).write_text(process.stdout)
 passed=process.returncode==0 and 'TOOLING_CLASS_CACHE_OK depth=ok threads=ok filtering=ok' in process.stdout
 results.append(dict(jvm=version,command=command,exit=process.returncode,passed=passed,seconds=round(time.monotonic()-started,2)))
 (b/'tooling-class-cache-results.json').write_text(json.dumps(results,indent=2)+'\n')
 print(process.stdout,flush=True)
 if not passed:raise RuntimeError('tooling class cache failed on Java '+version)
