"""Shared source-level JDK compatibility rewrites for upstream sources."""
import re

def adapt(s, map_defaults=True):
    for a, c in [('java.util.function.', 'java8.util.function.'), ('java.util.stream.', 'java8.util.stream.'),
                 ('java.time.', 'org.threeten.bp.'), ('java.util.Objects', 'java8.util.Objects'),
                 ('java.util.StringJoiner', 'java8.util.StringJoiner'),
                 ('java.util.concurrent.ThreadLocalRandom', 'java8.util.concurrent.ThreadLocalRandom'),
                 ('java.nio.charset.StandardCharsets', 'io.opentelemetry.java6.StandardCharsets'),
                 ('import java.util.Base64;', 'import io.opentelemetry.java6.Base64;')]:
        s = s.replace(a, c)
    s = re.sub(r'\bAutoCloseable\b', 'java.io.Closeable', s)
    s = re.sub(r'(\b\w+(?:\.\w+|\(\))*)\.stream\(\)', r'java8.util.stream.StreamSupport.stream(\1)', s)
    if map_defaults:
        s = re.sub(r'([\w.]+)\.computeIfAbsent\(', r'java8.util.Maps.computeIfAbsent(\1, ', s)
    s = s.replace('nextIdCounters\n                    .computeIfAbsent(', 'java8.util.Maps.computeIfAbsent(nextIdCounters, ')
    s = s.replace('fields.spliterator()', 'java8.lang.Iterables.spliterator(fields)')
    s = s.replace('m.forEach(this::put)', 'java8.util.Maps.forEach(m, this::put)')
    s = s.replace('componentLoader.load(spiClass).forEach(result::add)', 'java8.lang.Iterables.forEach(componentLoader.load(spiClass), result::add)')
    s = s.replace('this.tracerSdkComponentRegistry\n        .getComponents()\n        .forEach(', 'java8.lang.Iterables.forEach(this.tracerSdkComponentRegistry.getComponents(), ')
    s = re.sub(r'(\w+)\.getSuppressed\(\)', r'io.opentelemetry.java6.Exceptions.getSuppressed(\1)', s)
    s = s.replace('Comparator.comparing(', 'java8.util.Comparators.comparing(').replace('Comparator.naturalOrder()', 'java8.util.Comparators.naturalOrder()')
    s = s.replace('Collections.emptyIterator()', 'Collections.<String>emptyList().iterator()')
    s = s.replace('Long.hashCode(', 'java8.lang.Longs.hashCode(').replace('Double.hashCode(', 'java8.lang.Doubles.hashCode(')
    s = s.replace('includedPredicate(this.included, globMatchingEnabled)\n              .and(excludedPredicate(this.excluded, globMatchingEnabled))', 'java8.util.function.Predicates.and(includedPredicate(this.included, globMatchingEnabled), excludedPredicate(this.excluded, globMatchingEnabled))')
    s = s.replace('result.or(', 'java8.util.function.Predicates.or(result, ').replace('result.and(', 'java8.util.function.Predicates.and(result, ')
    s = s.replace('createGlobPatternPredicate(exclude).negate()', 'java8.util.function.Predicates.negate(createGlobPatternPredicate(exclude))')
    s = s.replace('java8.util.Maps.computeIfAbsent', 'io.opentelemetry.java6.Maps.computeIfAbsent')
    s = s.replace('Boolean.hashCode(value)', '(value ? 1231 : 1237)')
    s = s.replace('System.lineSeparator()', 'System.getProperty("line.separator")')
    s=s.replace('java.util.Optional','java8.util.Optional')
    s=s.replace('Function.identity()', 'java8.util.function.Functions.identity()')
    s=s.replace('java.io.UncheckedIOException','io.opentelemetry.java6.UncheckedIOException')
    s=s.replace('ConcurrentLinkedDeque', 'ConcurrentLinkedQueue')
    s=s.replace('Character.isSurrogate(', 'io.opentelemetry.java6.Characters.isSurrogate(')
    s=s.replace('Arrays.stream(', 'java8.util.J8Arrays.stream(')
    s=s.replace('getList(ConfigUtil.normalizePropertyKey(name)).stream()', 'java8.util.stream.StreamSupport.stream(getList(ConfigUtil.normalizePropertyKey(name)))')
    s=s.replace('java8.util.stream.StreamSupport.stream(list)\n              .collect(groupingBy(java8.util.function.Functions.identity(), Collectors.counting()))\n              .entrySet()\n              .stream()', 'java8.util.stream.StreamSupport.stream(java8.util.stream.StreamSupport.stream(list).collect(groupingBy(java8.util.function.Functions.identity(), Collectors.counting())).entrySet())')
    if map_defaults:
        s=s.replace('import java.util.Deque;', 'import java.util.Queue;').replace('Deque<', 'Queue<')
    s=s.replace('Base64.getDecoder().decode(content)', 'org.apache.commons.codec.binary.Base64.decodeBase64(content)')
    s=s.replace('@Override\n  public void forEach(BiConsumer', 'public void forEach(BiConsumer')
    s=re.sub(r'(supplierResult|constantHeaders|headers|defaultProperties|environmentVariables|systemProperties|overrides|reusablePointsList|aggregatorHandles|holder\.aggregatorHandles|currentPoints|lastPoints|observableMeasurements|this.readerStorageRegistries.values\(\))\.forEach\(', r'io.opentelemetry.java6.FrameworkCollections.forEach(\1, ', s)
    s=s.replace('this.registry\n        .getComponents()\n        .forEach(', 'io.opentelemetry.java6.FrameworkCollections.forEach(this.registry.getComponents(), ')
    s=s.replace('this.loggerComponentRegistry\n        .getComponents()\n        .forEach(', 'io.opentelemetry.java6.FrameworkCollections.forEach(this.loggerComponentRegistry.getComponents(), ')
    s=s.replace('this.registry\n        .io.opentelemetry.java6.FrameworkCollections.forEach(getComponents(), ', 'io.opentelemetry.java6.FrameworkCollections.forEach(this.registry.getComponents(), ')
    s=s.replace('this.loggerComponentRegistry\n        .io.opentelemetry.java6.FrameworkCollections.forEach(getComponents(), ', 'io.opentelemetry.java6.FrameworkCollections.forEach(this.loggerComponentRegistry.getComponents(), ')
    s=s.replace('configureMetricReaders(\n            config, spiHelper, metricReaderCustomizer, metricExporterCustomizer, closeables)\n        .forEach(', 'io.opentelemetry.java6.FrameworkCollections.forEach(configureMetricReaders(config, spiHelper, metricReaderCustomizer, metricExporterCustomizer, closeables), ')
    s=s.replace('nameToImplementation\n        .computeIfAbsent(', 'io.opentelemetry.java6.Maps.computeIfAbsent(nameToImplementation, ')
    s=s.replace('result.sort(Comparator.comparingInt(Ordered::order))', 'Collections.sort(result, java8.util.Comparators.comparingInt(Ordered::order))')
    s=s.replace('Double.isFinite(', 'java8.lang.Doubles.isFinite(')
    s=s.replace('result.merge(\n', 'java8.util.Maps.merge(result,\n')
    if 'class AsynchronousMetricStorage' in s:s=s.replace('aggregatorHandles.putIfAbsent(', 'java8.util.Maps.putIfAbsent(aggregatorHandles, ')
    s=s.replace('registry.getComponents().forEach(', 'io.opentelemetry.java6.FrameworkCollections.forEach(registry.getComponents(), ')
    s=re.sub(r'catch \(NoSuchMethodException \| IllegalAccessException e\) \{([^{}]*)\}', lambda match: 'catch (NoSuchMethodException e) {'+match.group(1)+'} catch (IllegalAccessException e) {'+match.group(1)+'}',s)
    s=re.sub(r'catch \(((?:NoSuchMethodException|IllegalAccessException|InvocationTargetException)(?: \| (?:NoSuchMethodException|IllegalAccessException|InvocationTargetException))+) (\w+)\) \{([^{}]*)\}', lambda match: ' '.join('catch ('+kind+' '+match.group(2)+') {'+match.group(3)+'}' for kind in match.group(1).split(' | ')),s)
    return s
