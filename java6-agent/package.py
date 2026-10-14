#!/usr/bin/env python3
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import argparse, hashlib
from zipfile import ZipInfo
p=argparse.ArgumentParser();p.add_argument('--sdk',required=True,type=Path);a=p.parse_args()
b=Path(__file__).resolve().parent/'build'
seen=set()
root=Path(__file__).resolve().parent
version=(root/'VERSION').read_text().strip()
digest=hashlib.sha256()
for source in sorted(root.rglob('*')):
    if source.is_file() and 'build' not in source.relative_to(root).parts and '__pycache__' not in source.parts:
        digest.update(source.relative_to(root).as_posix().encode());digest.update(b'\0');digest.update(source.read_bytes())
source_hash=digest.hexdigest()
# Fixed ZIP timestamps and sorted inputs make packaging independent of wall-clock time.

with ZipFile(b/'opentelemetry-javaagent-java6.jar','w',ZIP_DEFLATED) as z:
    def put(n,data):
        if n in seen: raise RuntimeError('duplicate '+n)
        seen.add(n)
        entry=ZipInfo(n,(1980,1,1,0,0,0));entry.compress_type=ZIP_DEFLATED;entry.external_attr=0o644<<16
        z.writestr(entry,data)
    put('META-INF/MANIFEST.MF',('Manifest-Version: 1.0\nPremain-Class: io.opentelemetry.javaagent.OpenTelemetryAgent\nMain-Class: io.opentelemetry.javaagent.bootstrap.DistributionInfo\nImplementation-Title: Flashcat Java Agent\nImplementation-Version: '+version+'\nCan-Retransform-Classes: true\n\n').encode())
    put('META-INF/flashcat-agent.properties',('version='+version+'\nsource.sha256='+source_hash+'\n').encode())
    put('META-INF/flashcat-upstream-exporter-sources.json',(b/'exporter-sources.json').read_bytes())
    put('META-INF/flashcat-upstream-framework-sources.json',(b/'framework-sources.json').read_bytes())
    for resource in sorted((root/'src/resources').rglob('*')):
        if resource.is_file(): put('inst/'+resource.relative_to(root/'src/resources').as_posix(),resource.read_bytes())
    for f in sorted((b/'bootstrap').rglob('*.class')):
        put(f.relative_to(b/'bootstrap').as_posix(),f.read_bytes())
    for f in sorted((b/'java6').rglob('*.class')):
        n=f.relative_to(b/'java6').as_posix()
        if n.startswith(('SdkCompatibilityTest','PropagationPeer','META-INF/')) or n=='module-info.class': continue
        data=f.read_bytes()
        assert int.from_bytes(data[6:8],'big')<=50,n
        put('inst/'+n+'data',data)
    for name in ['streamsupport-1.7.4.jar','threetenbp-1.6.8.jar','commons-codec-1.10.jar','jctools-core-4.0.7.jar']:
        with ZipFile(a.sdk/'java6-compat/build/dist'/name) as dep:
            for n in dep.namelist():
                if n.endswith('/') or n.startswith('META-INF/') or n=='module-info.class': continue
                data=dep.read(n)
                if n.endswith('.class'):
                    assert int.from_bytes(data[6:8],'big')<=50,n
                    put('inst/'+n+'data',data)
                else: put('inst/'+n,data)
    dependencies=[b/'deps/byte-buddy-1.18.14.jar',b/'deps/gson-2.8.9.jar'] + sorted((a.sdk/'java6-compat/build/dist').glob('*.jar'))
    for dependency in dependencies:
        if dependency.name in ('opentelemetry-trace-java6.jar','acceptance-tests.jar'): continue
        with ZipFile(dependency) as dep:
            for n in dep.namelist():
                if not n.endswith('/') and any(word in n.upper() for word in ('LICENSE','NOTICE','COPYING')):
                    put('META-INF/dependency-notices/'+dependency.stem+'/'+n,dep.read(n))
    put('META-INF/LICENSE',(Path(__file__).resolve().parents[1]/'LICENSE').read_bytes())
print(b/'opentelemetry-javaagent-java6.jar')

release=b/'dist';release.mkdir(exist_ok=True)
artifact=release/'flashcat-javaagent.jar';artifact.write_bytes((b/'opentelemetry-javaagent-java6.jar').read_bytes())
(release/'flashcat-javaagent.jar.sha256').write_text(hashlib.sha256(artifact.read_bytes()).hexdigest()+'  flashcat-javaagent.jar\n')
print(artifact)
