#!/usr/bin/env python3
"""Describe source dependencies embedded by package-official.py (not compile-only clients)."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

parser = argparse.ArgumentParser()
parser.add_argument('--sdk', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
inventory = {}
for manifest, directory in [
    (root / 'official-deps.json', root / 'build/official-deps'),
    (root / 'base-deps.json', root / 'build/deps'),
    (root / 'degradation/deps.json', root / 'build/degradation-deps'),
    (root / 'runtime-deps.json', root / 'build/runtime-deps'),
    (root / 'grpc-export-deps.json', root / 'build/grpc-export-deps'),
    (root / 'component-deps.json', root / 'build/component-deps'),
    (args.sdk / 'java6-compat/dependencies.json', args.sdk / 'java6-compat/build/dist'),
]:
    for entry in json.loads(manifest.read_text()):
        inventory[entry['file']] = (entry, directory / entry['file'])
for entry in json.loads((root / 'http-compat/sources.json').read_text()):
    if 'url' in entry:
        inventory[entry['file']] = (entry, root / 'build/http-source-deps' / entry['file'])
selected = {
    'protobuf-java-3.3.0.jar': 'BSD-3-Clause',
    'okhttp-3.12.13-sources.jar': 'Apache-2.0',
    'okio-1.17.2-sources.jar': 'Apache-2.0',
    'byte-buddy-dep-1.18.14.jar': 'Apache-2.0',
    'opentelemetry-semconv-1.44.0.jar': 'Apache-2.0',
    'opentelemetry-semconv-incubating-1.44.0-alpha.jar': 'Apache-2.0',
    'gson-2.8.9.jar': 'Apache-2.0',
    'slf4j-api-1.7.36.jar': 'MIT',
    'slf4j-simple-1.7.36.jar': 'MIT',
    'jackson-core-2.22.3.jar': 'Apache-2.0',
    'streamsupport-1.7.4.jar': '(GPL-2.0-only WITH Classpath-exception-2.0) AND CC0-1.0',
    'threetenbp-1.6.8.jar': 'BSD-3-Clause',
    'commons-codec-1.10.jar': 'Apache-2.0',
    'jctools-core-4.0.7.jar': 'Apache-2.0',
}
for name in ('asm', 'asm-tree', 'asm-commons', 'asm-util', 'asm-analysis'):
    selected[name + '-9.10.1.jar'] = 'BSD-3-Clause'
for entry in json.loads((root / 'grpc-export-deps.json').read_text()):
    selected[entry['file']] = 'Apache-2.0'
components = []
for filename, license_expression in sorted(selected.items()):
    entry, archive = inventory[filename]
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert digest == entry['sha256'], 'Dependency checksum mismatch: ' + filename
    parts = urlparse(entry['url']).path.split('/maven2/', 1)[1].split('/')
    group, name, version = '.'.join(parts[:-3]), parts[-3], parts[-2]
    purl = 'pkg:maven/' + group + '/' + name + '@' + version
    components.append(dict(type='library', **{'bom-ref': purl}, group=group, name=name,
                           version=version, purl=purl,
                           hashes=[dict(alg='SHA-256', content=digest)],
                           licenses=[dict(expression=license_expression)],
                           externalReferences=[dict(type='distribution', url=entry['url'])],
                           properties=[dict(name='flashcat:hash-scope', value='Original dependency archive before shading and compatibility transformation')]))
for name, version, url in [
    ('opentelemetry-java-instrumentation', '2.32.0', 'https://github.com/open-telemetry/opentelemetry-java-instrumentation/tree/v2.32.0'),
    ('opentelemetry-java', '1.66.0', 'https://github.com/open-telemetry/opentelemetry-java/tree/v1.66.0'),
    ('elastic-otel-java-dynamicconfig', '1.13.0', 'https://github.com/elastic/elastic-otel-java/tree/be989afffc981ab39374d271880494a4f6a3842d/custom/src/main/java/co/elastic/otel/dynamicconfig'),
    ('opentelemetry-opamp-client', '1.59.0-alpha', 'https://github.com/open-telemetry/opentelemetry-java-contrib/tree/ea31a2d440091cbd4e3684ad961764ad18629125/opamp-client'),
]:
    components.append(dict(type='library', **{'bom-ref': name}, name=name, version=version,
                           licenses=[dict(license=dict(id='Apache-2.0'))],
                           externalReferences=[dict(type='vcs', url=url)],
                           properties=[dict(name='flashcat:source-status', value='Selected upstream modules with Java 6 compatibility patches; not an unchanged upstream binary')]))
result = dict(bomFormat='CycloneDX', specVersion='1.5', version=1,
              metadata=dict(component=dict(type='application', name='flashcat-opentelemetry-javaagent',
                                           version='2.32.0-java6-loader-candidate')),
              components=components)
target = root / 'build/sbom.cdx.json'
target.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
print('SBOM_OK components=' + str(len(components)))
