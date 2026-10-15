#!/usr/bin/env python3
"""Prepare the Java 6 degradation module and pinned official OpAMP messages."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import urllib.request

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from source_compat import adapt

module = root / "degradation"
build = root / "build"
deps = build / "degradation-deps"
deps.mkdir(exist_ok=True)
for entry in json.loads((module / "deps.json").read_text()):
    path = deps / entry["file"]
    if not path.exists():
        urllib.request.urlretrieve(entry["url"], path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        raise ValueError("Dependency hash mismatch: " + str(path))
(deps / "protoc-3.3.0-linux-x86_64.exe").chmod(0o755)
out = build / "degradation-src"
if out.exists():
    shutil.rmtree(out)
out.mkdir()
for path in (module / "src/main/java").rglob("*.java"):
    target = out / path.relative_to(module / "src/main/java")
    target.parent.mkdir(parents=True, exist_ok=True)
    text = adapt(path.read_text()).replace("import com.google.auto.service.AutoService;", "")
    target.write_text(re.sub(r"@AutoService\([^\n]+\)\n", "", text))
for name, digest in json.loads((module / "schema.json").read_text())["sha256"].items():
    if hashlib.sha256((module / "proto" / name).read_bytes()).hexdigest() != digest:
        raise ValueError("Schema hash mismatch: " + name)
print("DEGRADATION_PREPARED")
