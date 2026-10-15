# JVM runtime resource validation

Set RUNTIME_RESOURCE_TEST_DIR to a directory containing flashcat-javaagent.jar and Smoke.class (compile Smoke.java with javac -source 6 -target 6). Set JAVA6_HOME to an Oracle 6u45 Linux JDK. With Docker and Python opentelemetry-proto installed, run `python java6-agent/tests/runtime-resource/verify.py`.

The fixture sends a real HTTP request. The receiver checks exported OTLP resource name, description and runtime version against the tested JVM's java.runtime.version. It uses isolated ephemeral containers and an ephemeral HTTP receiver.

2026-10-15: module build and backport-tooling.sh passed. The packaged RC5 runtime-resource increment passed all three actual export checks: Oracle 1.6.0_45-b06, Temurin 1.8.0_504-b01, and 17.0.20.1+1.

Package SHA256: d871a14579877c2c6a0939856a97a88da9657b2a70d77f2404a1494da15e9898. This increment preserves RC5 payloads except the ResourceProvider registration and adds the two relocated official runtime resource classes; it is not a clean rebuild of unrelated worktree changes.
