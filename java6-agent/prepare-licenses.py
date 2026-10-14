#!/usr/bin/env python3
"""Preserve license materials for dependencies embedded in the candidate JAR."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument('--sdk', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
out = root / 'build/license-materials'
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True)
manifest = json.loads((root / 'licenses/sources.json').read_text())
for entry in manifest:
    source = root / 'licenses' / entry['file']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == entry['sha256'], source
    shutil.copyfile(source, out / source.name)
# These archives carry their own copyright notices; retain the exact bytes.
archives = [
    root / 'build/official-deps/byte-buddy-dep-1.18.14.jar',
    root / 'build/component-deps/jackson-core-2.22.3.jar',
    args.sdk / 'java6-compat/build/dist/threetenbp-1.6.8.jar',
    args.sdk / 'java6-compat/build/dist/commons-codec-1.10.jar',
]
for source in archives:
    count = 0
    with zipfile.ZipFile(source) as archive:
        for name in sorted(archive.namelist()):
            if not name.startswith('META-INF/') or name.rsplit('/', 1)[-1].upper() not in (
                    'LICENSE', 'LICENSE.TXT', 'NOTICE', 'NOTICE.TXT'):
                continue
            data = archive.read(name)
            target = source.stem + '-' + name.rsplit('/', 1)[-1]
            (out / target).write_bytes(data)
            manifest.append(dict(file=target, sha256=hashlib.sha256(data).hexdigest(),
                                 archive=source.name, archive_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                                 entry=name))
            count += 1
    assert count, 'Missing license: ' + str(source)
(out / 'sources.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
(out / 'README.txt').write_text('''Third-party license materials for the Java 6 compatibility candidate.

Apache-2.0.txt: OpenTelemetry Agent/SDK/semantic conventions, Gson and JCTools.
gRPC/Guava/instrumentation-api/OpenCensus/Netty: exact-version source license
headers retained with hashes. Netty NOTICE and all its referenced license files
are preserved; optional dependencies mentioned in that upstream NOTICE are not
thereby asserted to be embedded in this artifact. Guava COPYING is retained.
ASM and SLF4J: complete license headers from the exact published source archives.
Byte Buddy, Jackson, ThreeTenBP and Commons Codec: license/notice entries preserved
from the embedded archive versions.
streamsupport: GPL version 2 with the Classpath Exception; CC0 applies to the
JSR-166-derived source files as identified by the upstream sources.

sources.json records material hashes and source/archive provenance. Compile-only
middleware dependencies are not included in this JAR. This inventory is license
material preservation, not a claim of a completed release compliance review.
''')
print('LICENSE_MATERIALS_OK entries=' + str(len(manifest)))
