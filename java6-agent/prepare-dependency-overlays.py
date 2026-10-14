#!/usr/bin/env python3
"""Minimal source patches for bootstrap-loaded backport dependencies."""
from pathlib import Path
from zipfile import ZipFile
import difflib
import hashlib
import json
import shutil

root = Path(__file__).resolve().parent
build = root / 'build'
output = build / 'dependency-src'
if output.exists():
    shutil.rmtree(output)
name = 'org/threeten/bp/zone/TzdbZoneRulesProvider.java'
archive = build / 'deps/threetenbp-1.6.8-sources.jar'
with ZipFile(archive) as source:
    original = source.read(name).decode('utf-8')
before = 'Enumeration<URL> en = classLoader.getResources("org/threeten/bp/TZDB.dat");'
after = ('Enumeration<URL> en = classLoader == null '
         '? ClassLoader.getSystemResources("org/threeten/bp/TZDB.dat") '
         ': classLoader.getResources("org/threeten/bp/TZDB.dat");')
assert original.count(before) == 1, 'ThreeTenBP source boundary changed'
adapted = original.replace(before, after)
target = output / name
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(adapted)
(build / 'dependency-adaptation.patch').write_text(''.join(difflib.unified_diff(
    original.splitlines(True), adapted.splitlines(True), fromfile='threetenbp-1.6.8/'+name,
    tofile='generated/'+name)))
(build / 'dependency-sources.json').write_text(json.dumps([dict(
    dependency='threetenbp-1.6.8', path=name,
    archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
    source_sha256=hashlib.sha256(original.encode()).hexdigest(),
    adapted_sha256=hashlib.sha256(adapted.encode()).hexdigest())], indent=2)+'\n')
print('Prepared bootstrap resource lookup overlay for ThreeTenBP')
