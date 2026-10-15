#!/usr/bin/env python3
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Run against an unmodified copy of the local n9e-plus HTTP handler and store."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("n9e_repo", type=Path)
parser.add_argument("--n9e-ref", default="b078fdd6801dd2b6e7c04736e78aed855be3b8e4",
                    help="Committed n9e-plus revision; working-tree files are never used")
args = parser.parse_args()
revision = subprocess.check_output(
    ["git", "-C", str(args.n9e_repo), "rev-parse", args.n9e_ref + "^{commit}"], text=True).strip()
print("n9e-plus commit=" + revision, flush=True)
agent = Path(os.environ["INTEROP_AGENT"])
print("Agent SHA256=" + hashlib.sha256(agent.read_bytes()).hexdigest(), flush=True)
subprocess.run([os.environ["INTEROP_JAVA"], "-version"], check=True)
with tempfile.TemporaryDirectory(prefix="otel-n9e-interop-") as directory:
    work = Path(directory)
    for name in ("handler.go", "store.go"):
        content = subprocess.check_output(
            ["git", "-C", str(args.n9e_repo), "show", revision + ":plus/opamp/" + name])
        (work / name).write_bytes(content)
        print(f"n9e-plus {name} sha256={hashlib.sha256((work / name).read_bytes()).hexdigest()}", flush=True)
    shutil.copy2(Path(__file__).with_name("interop_test.go"), work / "interop_test.go")
    (work / "go.mod").write_text("""module interop

go 1.25.0

require (
    github.com/open-telemetry/opamp-go v0.25.0
    google.golang.org/protobuf v1.36.11
    gorm.io/driver/sqlite v1.5.7
    gorm.io/gorm v1.25.12
)
""")
    subprocess.run(["go", "test", "-mod=mod", "-race", "-v", "-count=1", "-timeout=300s", "."], cwd=work, check=True)
