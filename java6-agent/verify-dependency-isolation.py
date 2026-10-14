#!/usr/bin/env python3
"""Verify that application dependencies remain independent of Agent bootstrap copies."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--sdk', required=True, type=Path)
parser.add_argument('--jdk6', required=True, type=Path)
parser.add_argument('--agent', default='official-loader-candidate.jar')
parser.add_argument('--without-agent', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parent
build = root / 'build'
stage = build / 'dependency-isolation'
(stage / 'app').mkdir(parents=True, exist_ok=True)
(stage / 'deps').mkdir(exist_ok=True)
for name in ('commons-codec-1.10.jar', 'threetenbp-1.6.8.jar', 'jctools-core-4.0.7.jar'):
    shutil.copyfile(args.sdk / 'java6-compat/build/dist' / name, stage / 'deps' / name)
subprocess.run([
    'docker', 'run', '--rm', '--platform', 'linux/amd64', '-v', str(root) + ':/test',
    '-w', '/test', 'eclipse-temurin:8-jdk', 'javac', '-J-XX:TieredStopAtLevel=1',
    '-source', '6', '-target', '6', '-d', 'build/dependency-isolation/app',
    'tests/DependencyIsolationProbe.java'], check=True)
artifact = build / args.agent
checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
results = []
for version, image, platform, executable in (
    ('6', 'debian:bookworm-slim', 'linux/amd64', '/jdk/bin/java'),
    ('8', 'eclipse-temurin:8-jdk', 'linux/amd64', 'java'),
    ('17', 'eclipse-temurin:17-jre', 'linux/arm64', 'java'),
):
    command = ['docker', 'run', '--rm', '--platform', platform,
               '-v', str(root) + ':/test:ro', '-v', str(args.jdk6.resolve()) + ':/jdk:ro',
               image, executable, '-Xverify:all']
    if version == '8':
        command.append('-XX:TieredStopAtLevel=1')
    if not args.without_agent:
        command += ['-javaagent:/test/build/' + args.agent, '-Dotel.traces.exporter=none',
                    '-Dotel.metrics.exporter=none', '-Dotel.logs.exporter=none']
    command += ['-cp', '/test/build/dependency-isolation/app:/test/build/dependency-isolation/deps/*',
                'DependencyIsolationProbe']
    if not args.without_agent:
        command.append('check-private')
    process = subprocess.run(command, capture_output=True, text=True, timeout=120)
    passed = process.returncode == 0 and 'DEPENDENCY_ISOLATION_OK' in process.stdout
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == checksum, 'Agent changed during test'
    results.append(dict(java=version, agent=not args.without_agent, sha256=checksum,
                        passed=passed, command=command, stdout=process.stdout, stderr=process.stderr))
    report = 'dependency-isolation-baseline.json' if args.without_agent else 'dependency-isolation-results.json'
    (build / report).write_text(json.dumps(results, indent=2) + '\n')
    print(process.stdout + process.stderr, flush=True)
    if not passed:
        raise RuntimeError('Dependency isolation failed on Java ' + version)
