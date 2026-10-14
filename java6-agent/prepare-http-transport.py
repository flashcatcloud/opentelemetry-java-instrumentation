#!/usr/bin/env python3
"""Reproduce reviewed upstream HTTP sender sources; never use a local prototype tree."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sdk', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
build = root / 'build'
manifest = json.loads((root / 'http-compat/sources.json').read_text())
cache = build / 'http-source-deps'
cache.mkdir(parents=True, exist_ok=True)

def verify(data, expected, name):
    if hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError('HTTP source checksum mismatch: ' + name)

# Stage before replacing output: an upstream drift or failed patch must not leave usable partial output.
with tempfile.TemporaryDirectory(prefix='http-sources-', dir=build) as temporary:
    staging = Path(temporary)
    for entry in manifest:
        destination = staging / entry['name']
        destination.mkdir()
        if 'url' in entry:
            archive = cache / entry['file']
            if archive.exists():
                data = archive.read_bytes()
            else:
                with urllib.request.urlopen(entry['url'], timeout=60) as response:
                    data = response.read()
            verify(data, entry['sha256'], entry['file'])
            if not archive.exists():
                archive.write_bytes(data)
            with zipfile.ZipFile(archive) as contents:
                for member in contents.infolist():
                    relative = Path(member.filename)
                    if relative.is_absolute() or '..' in relative.parts:
                        raise RuntimeError('Unsafe archive member: ' + member.filename)
                    if member.is_dir():
                        continue
                    target = destination / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(contents.read(member))
        else:
            for name in entry['sources']:
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(args.sdk / entry['sdk_prefix'] / name, target)
        for name, expected in entry['sources'].items():
            verify((destination / name).read_bytes(), expected, name)
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i',
                        str(root / 'http-compat' / (entry['name'] + '.patch'))],
                       cwd=destination, check=True)
        for name, expected in entry['prepared'].items():
            verify((destination / name).read_bytes(), expected, name)
    output = build / 'http-transport-src'
    if output.exists():
        shutil.rmtree(output)
    shutil.move(str(staging), output)
print('Verified and prepared upstream HTTP transport sources')
