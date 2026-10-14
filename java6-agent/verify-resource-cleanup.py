#!/usr/bin/env python3
"""Run compiler-generated cleanup paths through the real backport/relocation pipeline."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--sdk', type=Path, required=True)
parser.add_argument('--jdk6', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
for name in ('suppressed-test-input', 'suppressed-test-backport', 'suppressed-test'):
    shutil.rmtree(root / 'build' / name, ignore_errors=True)
script = '''set -eu
mkdir -p build/suppressed-test-input build/suppressed-test-tools
javac -J-XX:TieredStopAtLevel=1 -source 8 -target 8 -d build/suppressed-test-input tests/SuppressedExceptionProbe.java
javac -J-XX:TieredStopAtLevel=1 -proc:none -cp 'build/official-deps/*' -d build/suppressed-test-tools build-tools/PreserveSuppressedExceptions.java build-tools/RelocateAgent.java
java -XX:TieredStopAtLevel=1 -cp 'build/suppressed-test-tools:build/official-deps/*' PreserveSuppressedExceptions build/suppressed-test-input
java -XX:TieredStopAtLevel=1 -Dretrolambda.quiet=true -Dretrolambda.inputDir=build/suppressed-test-input -Dretrolambda.outputDir=build/suppressed-test-backport -Dretrolambda.classpath=build/suppressed-test-input:build/classes -Dretrolambda.bytecodeVersion=50 -javaagent:/sdk/java6-compat/build/deps/build/retrolambda-2.5.7.jar -jar /sdk/java6-compat/build/deps/build/retrolambda-2.5.7.jar
java -XX:TieredStopAtLevel=1 -cp 'build/suppressed-test-tools:build/official-deps/*' RelocateAgent build/suppressed-test-backport build/suppressed-test
'''
subprocess.run(['docker', 'run', '--rm', '--platform', 'linux/amd64', '-v', str(root)+':/test', '-v', str(args.sdk)+':/sdk:ro', '-w', '/test', 'eclipse-temurin:8-jdk', 'sh', '-c', script], check=True)
artifact = root / 'build/official-loader-candidate.jar'
checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
results = []
for version, image, platform, java in [('6', 'debian:bookworm-slim', 'linux/amd64', '/jdk/bin/java'), ('8', 'eclipse-temurin:8-jdk', 'linux/amd64', 'java'), ('17', 'eclipse-temurin:17-jre', 'linux/arm64', 'java')]:
    command = ['docker', 'run', '--rm', '--platform', platform, '-v', str(root)+':/test:ro', '-v', str(args.jdk6)+':/jdk:ro', image, java]
    if version == '8': command.append('-XX:TieredStopAtLevel=1')
    command += ['-Xverify:all', '-Dotel.traces.exporter=none', '-Dotel.metrics.exporter=none', '-Dotel.logs.exporter=none', '-javaagent:/test/build/official-loader-candidate.jar', '-cp', '/test/build/suppressed-test', 'SuppressedExceptionProbe']
    completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
    passed = completed.returncode == 0 and 'RESOURCE_CLEANUP_OK' in completed.stdout
    results.append(dict(jvm=version, sha256=checksum, passed=passed, command=command, stdout=completed.stdout, stderr=completed.stderr))
    (root / 'build/resource-cleanup-results.json').write_text(json.dumps(results, indent=2)+'\n')
    assert passed, results[-1]
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == checksum, 'Artifact changed during verification'
    print(completed.stdout.strip())
