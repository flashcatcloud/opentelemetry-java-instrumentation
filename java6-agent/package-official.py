#!/usr/bin/env python3
"""Stage and package the official loader candidate; not a release artifact."""
from pathlib import Path
import argparse, shutil, zipfile, subprocess, hashlib, sys, json
p=argparse.ArgumentParser();p.add_argument('--sdk',type=Path,required=True);a=p.parse_args()
r=Path(__file__).resolve().parents[1];b=r/'java6-agent/build'
source=b/'official-package-input';relocated=b/'official-package-relocated'
for directory in (source,relocated):
    if directory.exists():shutil.rmtree(directory)
shutil.copytree(b/'tooling-java6',source)
# Fail on stale prototype classes instead of silently shipping two implementations.
for prefix in ['io/opentelemetry/javaagent/tooling/ProtocolInstrumentation',
               'io/opentelemetry/javaagent/tooling/ProtocolTelemetry',
               'io/opentelemetry/javaagent/tooling/OracleAddress',
               'io/opentelemetry/javaagent/tooling/DubboInstrumentation',
               'io/opentelemetry/javaagent/tooling/OfficialSdkInstaller',
               'io/opentelemetry/javaagent/bootstrap/ProtocolBridge',
               'io/opentelemetry/javaagent/bootstrap/TelemetryBridge']:
    stale=list(source.glob(prefix+'*.class'))
    if stale:raise RuntimeError('Stale handwritten prototype classes: '+str(stale))
# Java 9-only upstream helpers remain conditional, as in the upstream distribution.
for helper in (b/'tooling-java9').rglob('*.class'):
    if helper.stem.split('$')[0] not in ('ModuleOpener', 'ExposeAgentBootstrapListener', 'Java9LambdaTransformer'):
        continue
    target=source/helper.relative_to(b/'tooling-java9')
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(helper,target)
for name in ['streamsupport-1.7.4.jar','threetenbp-1.6.8.jar','commons-codec-1.10.jar','jctools-core-4.0.7.jar']:
    with zipfile.ZipFile(a.sdk/'java6-compat/build/dist'/name) as archive:
        for item in archive.infolist():
            if item.is_dir() or (item.filename.startswith('META-INF/') and not item.filename.startswith('META-INF/services/')) or item.filename=='module-info.class':continue
            target=source/item.filename
            if target.exists():
                if name == 'threetenbp-1.6.8.jar' and item.filename in (
                    'org/threeten/bp/zone/TzdbZoneRulesProvider.class',
                    'org/threeten/bp/zone/TzdbZoneRulesProvider$Version.class'):
                    continue  # explicit source overlay; recorded in dependency-sources.json
                raise RuntimeError('Duplicate dependency '+item.filename)
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(item))
# Upstream JSON sanitizer is used only by Java 8+ Elasticsearch clients. Keep its
# official Jackson dependency in the isolated Agent loader, not bootstrap/application.
with zipfile.ZipFile(b/'component-deps/jackson-core-2.22.3.jar') as archive:
    for item in archive.infolist():
        if item.is_dir() or item.filename.startswith('META-INF/') or item.filename=='module-info.class':continue
        target=source/item.filename
        if target.exists():raise RuntimeError('Duplicate Jackson dependency '+item.filename)
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(item))
    for name in ('META-INF/LICENSE', 'META-INF/NOTICE'):
        if name in archive.namelist():
            target=source/'META-INF/licenses'/('jackson-core-'+name.split('/')[-1])
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(name))
# Only exporter references and transport dependencies are relocated. Application
# instrumentation must continue matching the application's original io.grpc types.
transport_input=b/'grpc-transport-input';transport_private=b/'grpc-transport-private'
for directory in (transport_input,transport_private):
    if directory.exists():shutil.rmtree(directory)
shutil.copytree(source/'io/opentelemetry/exporter',transport_input/'io/opentelemetry/exporter')
for transport_entry in json.loads((r/'java6-agent/grpc-export-deps.json').read_text()):
    dependency=b/'grpc-export-deps'/transport_entry['file']
    assert hashlib.sha256(dependency.read_bytes()).hexdigest()==transport_entry['sha256']
    with zipfile.ZipFile(dependency) as archive:
        for item in archive.infolist():
            if item.is_dir() or (item.filename.startswith('META-INF/') and not item.filename.startswith('META-INF/services/')):continue
            data=archive.read(item)
            if item.filename.endswith('.class') and int.from_bytes(data[6:8],'big')>50:
                raise RuntimeError('Non-Java6 transport class: '+dependency.name+':'+item.filename)
            target=transport_input/item.filename
            if target.exists():raise RuntimeError('Duplicate transport dependency: '+item.filename)
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
# Official gRPC header compatibility backport; private transport only.
for overlay in sorted((b/'grpc-overlay-classes').rglob('*.class')):
    name=overlay.relative_to(b/'grpc-overlay-classes').as_posix()
    assert name.startswith(('io/grpc/netty/AbstractHttp2Headers', 'io/grpc/netty/GrpcHttp2HeadersUtils', 'io/grpc/netty/ProtocolNegotiators')),name
    data=overlay.read_bytes();assert int.from_bytes(data[6:8],'big')<=50
    target=transport_input/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
subprocess.run(['docker','run','--rm','-v',str(r)+':/repo','-w','/repo/java6-agent','eclipse-temurin:25-jdk@sha256:8c0a84ea11c8f6ed52600fc19f1040121f2a162998e9f50a5faebbbad9172dcc','java','-cp','build/build-tools:build/official-deps/*','RelocateGrpcTransport','build/grpc-transport-input','build/grpc-transport-private'],check=True)
shutil.copytree(transport_private,source,dirs_exist_ok=True)
# Existing SDK OTLP providers are merged with upstream-generated tooling registrations.
for resource in (r/'java6-agent/src/resources/META-INF/services').iterdir():
    target=source/'META-INF/services'/resource.name
    lines=set(target.read_text().splitlines()) if target.exists() else set()
    lines.update(resource.read_text().splitlines());target.write_text('\n'.join(sorted(lines))+'\n')
subprocess.run(['docker','run','--rm','-v',str(r)+':/repo','-w','/repo/java6-agent','eclipse-temurin:25-jdk@sha256:8c0a84ea11c8f6ed52600fc19f1040121f2a162998e9f50a5faebbbad9172dcc','java','-cp','build/build-tools:build/official-deps/*','RelocateAgent','build/official-package-input','build/official-package-relocated'],check=True)
bootstrap=('io/opentelemetry/javaagent/bootstrap/','io/opentelemetry/javaagent/shaded/instrumentation/api/','io/opentelemetry/javaagent/shaded/io/opentelemetry/api/','io/opentelemetry/javaagent/shaded/io/opentelemetry/context/','io/opentelemetry/javaagent/shaded/io/opentelemetry/common/','io/opentelemetry/javaagent/shaded/io/opentelemetry/semconv/','io/opentelemetry/javaagent/shaded/io/opentelemetry/java6/','io/opentelemetry/javaagent/shaded/java8/','io/opentelemetry/javaagent/shaded/org/threeten/','io/opentelemetry/javaagent/shaded/org/apache/commons/codec/','io/opentelemetry/javaagent/shaded/org/jctools/')
subprocess.run([sys.executable, str(r/'java6-agent/prepare-licenses.py'), '--sdk', str(a.sdk)], check=True)
subprocess.run([sys.executable, str(r/'java6-agent/prepare-sbom.py'), '--sdk', str(a.sdk)], check=True)
subprocess.run([sys.executable, str(r/'java6-agent/prepare-provenance.py'), '--sdk', str(a.sdk)], check=True)
artifact=b/'official-loader-candidate.jar'
temporary=artifact.with_suffix('.jar.tmp')
with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
    def put(name,data):
        item=zipfile.ZipInfo(name,(1980,1,1,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;item.external_attr=0o644<<16;archive.writestr(item,data)
    put('META-INF/MANIFEST.MF',b'Manifest-Version: 1.0\nPremain-Class: io.opentelemetry.javaagent.OpenTelemetryAgent\nAgent-Class: io.opentelemetry.javaagent.OpenTelemetryAgent\nImplementation-Version: 2.32.0-java6-loader-candidate\nCan-Redefine-Classes: true\nCan-Retransform-Classes: true\n\n')
    put('META-INF/sbom.cdx.json',(b/'sbom.cdx.json').read_bytes())
    for file in sorted((b/'provenance').iterdir()):
        if file.is_file():put('META-INF/provenance/'+file.name,file.read_bytes())
    for file in sorted((b/'license-materials').iterdir()):
        if file.is_file():put('META-INF/licenses/'+file.name,file.read_bytes())
    for file in sorted(relocated.rglob('*')):
        if not file.is_file():continue
        name=file.relative_to(relocated).as_posix()
        if name.endswith('.class'):
            if '/' not in name or name.startswith('META-INF/'):continue
            if (name.startswith(bootstrap) and not name.startswith('io/opentelemetry/javaagent/shaded/io/opentelemetry/java6/FrameworkCollections')) or name=='io/opentelemetry/javaagent/OpenTelemetryAgent.class':target=name
            else:target='inst/'+name+'data'
        elif name.startswith('io/opentelemetry/javaagent/shaded/org/') or name.startswith('META-INF/services/io.opentelemetry.javaagent.shaded.org.'):
            # Backport library resource lookup happens from bootstrap classes.
            target=name
        else:target='inst/'+name
        put(target,file.read_bytes())
temporary.replace(artifact)
print(artifact)
print('sha256='+hashlib.sha256(artifact.read_bytes()).hexdigest())
