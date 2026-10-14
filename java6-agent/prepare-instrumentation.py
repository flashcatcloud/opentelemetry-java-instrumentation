#!/usr/bin/env python3
"""Generate compatibility overlays from the pinned official instrumentation sources.

Original component sources remain the source of truth. Every adapted source is
recorded in a manifest and a reviewable patch, as for the SDK compatibility build.
"""
from pathlib import Path
import difflib
import hashlib
import json
import shutil
import re
from source_compat import adapt
from zipfile import ZipFile

root = Path(__file__).resolve().parents[1]
build = root / 'java6-agent/build'
output = build / 'instrumentation-src'
modules = ['instrumentation-api', 'instrumentation-api-incubator']
if output.exists():
    shutil.rmtree(output)
manifest = []
patch = []
for module in modules:
    source_root = root / module / 'src/main/java'
    for source in sorted(source_root.rglob('*.java')):
        relative = source.relative_to(source_root)
        original = source.read_text()
        updated = adapt(original, map_defaults=False)
        updated = updated.replace('Stream.of(', 'java8.util.stream.RefStreams.of(')
        updated = updated.replace('UnaryOperator.identity()', 'java8.util.function.UnaryOperators.identity()')
        updated = updated.replace('asList(value.split(",")).stream()', 'java8.util.stream.StreamSupport.stream(asList(value.split(",")))')
        updated = updated.replace('super.forEach(action)', 'java8.util.Maps.forEach(this, action)')
        # Cache.computeIfAbsent is an upstream API; only rewrite actual JDK Map calls.
        map_receivers = {
            'MapBackedCache.java': ['delegate'],
            'AbstractWeakConcurrentMap.java': ['target'],
            'InstrumenterContext.java': ['get()'],
            'SupportabilityMetrics.java': ['suppressionCounters', 'counters'],
            'ServicePeerResolver.java': ['servicePeersByHost'],
            'SqlQueryAnalyzerUtil.java': ['map'],
            'EmbeddedInstrumentationProperties.java': ['versions'],
        }
        for receiver in map_receivers.get(source.name, []):
            updated = re.sub(re.escape(receiver) + r'\s*\.computeIfAbsent\(',
                             'io.opentelemetry.java6.Maps.computeIfAbsent(' + receiver + ', ', updated)
        updated = updated.replace('attributesExtractors.forEach(', 'java8.lang.Iterables.forEach(attributesExtractors, ')
        for receiver in ['suppressionCounters', 'counters']:
            updated = updated.replace(receiver + '.forEach(', 'java8.util.Maps.forEach(' + receiver + ', ')
        if source.name == 'RuntimeVirtualFieldSupplier.java':
            updated = updated.replace('ownerToFieldToImplementationMap\n', 'io.opentelemetry.java6.Maps.computeIfAbsent(ownerToFieldToImplementationMap\n')
            updated = updated.replace('.computeIfAbsent(fieldType, c -> new ConcurrentHashMap<>())\n              .computeIfAbsent(fieldName,', '.computeIfAbsent(fieldType, c -> new ConcurrentHashMap<>()), fieldName,')
        updated = updated.replace('ConcurrentHashMap.newKeySet()', 'java.util.Collections.newSetFromMap(new ConcurrentHashMap<String, Boolean>())')
        updated = updated.replace('String.join(', 'io.opentelemetry.java6.InstrumentationStrings.join(')
        updated = updated.replace('import static java.util.Comparator.', 'import static java8.util.Comparators.')
        updated = updated.replace('rendered.sort(String::compareTo)', 'java.util.Collections.sort(rendered)')
        updated = updated.replace('parsed.subList(1, parsed.size()).sort(comparing(Endpoint::renderConfigured))', 'java.util.Collections.sort(parsed.subList(1, parsed.size()), comparing(Endpoint::renderConfigured))')
        updated = updated.replace('merged.merge(', 'java8.util.Maps.merge(merged, ')
        updated = updated.replace('SANITIZERS\n        .getOrDefault(', 'java8.util.Maps.getOrDefault(SANITIZERS, ')
        updated = updated.replace('import static java.util.Collections.emptyIterator;', '')
        updated = updated.replace('return emptyIterator();', 'return java.util.Collections.<E>emptyList().iterator();')
        if source.name == 'ServicePeerResolver.java':
            updated = updated.replace('comparing(PortPathMatcher::getPort, nullsFirst(naturalOrder()))\n              .thenComparing(PortPathMatcher::getPath, nullsFirst(naturalOrder()))', 'java8.util.Comparators.thenComparing(comparing(PortPathMatcher::getPort, nullsFirst(naturalOrder())), PortPathMatcher::getPath, nullsFirst(naturalOrder()))')
            updated = updated.replace('DeclarativeConfigUtil.getInstrumentationConfig(openTelemetry, "common")\n        .getStructuredList("service_peer_mapping", emptyList())\n        .forEach(', 'java8.lang.Iterables.forEach(DeclarativeConfigUtil.getInstrumentationConfig(openTelemetry, "common").getStructuredList("service_peer_mapping", emptyList()), ')
            for receiver in ['servicePeersByExactAddress', 'matchers']:
                updated = updated.replace(receiver + '.putIfAbsent(', 'java8.util.Maps.putIfAbsent(' + receiver + ', ')
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(updated)
        manifest.append({'module': module, 'path': relative.as_posix(),
                         'adapted': original != updated,
                         'source_sha256': hashlib.sha256(original.encode()).hexdigest()})
        if original != updated:
            patch.extend(difflib.unified_diff(original.splitlines(True), updated.splitlines(True),
                         fromfile=module + '/' + relative.as_posix(),
                         tofile='generated/' + relative.as_posix()))
with ZipFile(build / 'official-deps/opentelemetry-semconv-1.44.0-sources.jar') as archive:
    name = 'io/opentelemetry/semconv/AttributeKeyTemplate.java'
    original = archive.read(name).decode()
    updated = adapt(original)
    target = output / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(updated)
    manifest.append({'module': 'opentelemetry-semconv:1.44.0', 'path': name,
                     'adapted': original != updated,
                     'source_sha256': hashlib.sha256(original.encode()).hexdigest()})
    patch.extend(difflib.unified_diff(original.splitlines(True), updated.splitlines(True),
                                    fromfile='semconv/' + name, tofile='generated/' + name))
(build / 'instrumentation-sources.json').write_text(json.dumps(manifest, indent=2) + '\n')
(build / 'instrumentation-adaptation.patch').write_text(''.join(patch))
print('Prepared', len(manifest), 'official instrumentation API sources')
