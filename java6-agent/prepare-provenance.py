#!/usr/bin/env python3
"""Record deterministic compatibility recipes and prepared-source identities."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

parser = argparse.ArgumentParser()
parser.add_argument('--sdk', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
out = root / 'build/provenance'
if out.exists(): shutil.rmtree(out)
out.mkdir(parents=True)
records = {}
def record(path, name):
    records[name] = hashlib.sha256(path.read_bytes()).hexdigest()
def tree(directory, prefix):
    assert directory.is_dir(), directory
    for file in sorted(directory.rglob('*')):
        if file.is_file() and file.suffix in ('.java', '.py', '.sh', '.json', '.patch') and '__pycache__' not in file.parts:
            record(file, prefix + '/' + file.relative_to(directory).as_posix())
for file in sorted(root.iterdir()):
    if file.is_file() and file.suffix in ('.py', '.sh', '.json'): record(file, 'agent/' + file.name)
for directory in ('src', 'build-tools', 'legacy-dubbo', 'http-compat'):
    tree(root / directory, 'agent/' + directory)
for directory in ('src', 'exporter-src', 'framework-src', 'grpc-overlay-src', 'http-transport-src', 'dependency-src', 'instrumentation-src', 'tooling-src', 'modules-src'):
    tree(root / 'build' / directory, 'agent/prepared/' + directory)
sdk = args.sdk / 'java6-compat'
for file in sorted(sdk.iterdir()):
    if file.is_file() and file.suffix in ('.py', '.sh', '.json'): record(file, 'sdk/' + file.name)
tree(sdk / 'src', 'sdk/src')
tree(sdk / 'build/src', 'sdk/prepared')
for source in sorted((root / 'build').glob('*-sources.json')) + sorted((root / 'build').glob('*-adaptation.patch')):
    shutil.copyfile(source, out / source.name)
    record(source, 'evidence/' + source.name)
shutil.copyfile(sdk / 'build/adaptation.patch', out / 'sdk-adaptation.patch')
record(sdk / 'build/adaptation.patch', 'evidence/sdk-adaptation.patch')
result = dict(upstream=dict(instrumentation='v2.32.0', sdk='v1.66.0'),
              scope='Compatibility recipe and prepared-source hashes; source tags identify baselines, not unchanged output binaries.',
              sha256=dict(sorted(records.items())))
(out / 'inputs.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
print('PROVENANCE_OK inputs=' + str(len(records)))
