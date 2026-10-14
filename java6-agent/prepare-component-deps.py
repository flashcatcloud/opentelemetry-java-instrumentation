#!/usr/bin/env python3
"""Resolve checksum-pinned build, component and isolated runtime dependencies."""
import hashlib,json,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parent
for manifest,directory in [('official-deps.json','official-deps'),('base-deps.json','deps'),('component-deps.json','component-deps'),('runtime-deps.json','runtime-deps'),('grpc-export-deps.json','grpc-export-deps'),('grpc-source-deps.json','grpc-source-deps'),('http-compile-deps.json','http-compile-deps')]:
    out=root/'build'/directory;out.mkdir(parents=True,exist_ok=True)
    for item in json.loads((root/manifest).read_text()):
        target=out/item['file']
        if target.exists():
            data=target.read_bytes()
        else:
            with urllib.request.urlopen(item['url'],timeout=60) as response:data=response.read()
        digest=hashlib.sha256(data).hexdigest()
        if digest!=item['sha256']:raise RuntimeError('Dependency checksum mismatch: '+item['file'])
        if not target.exists():target.write_bytes(data)
        print('VERIFIED',item['file'],digest)

expected={entry['file'] for entry in json.loads((root/'grpc-export-deps.json').read_text())}
stale={path.name for path in (root/'build/grpc-export-deps').glob('*.jar')}-expected
if stale:raise RuntimeError('Stale isolated gRPC dependencies outside manifest: '+str(sorted(stale)))
