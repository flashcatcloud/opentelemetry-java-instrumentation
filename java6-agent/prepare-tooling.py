#!/usr/bin/env python3
"""Prepare source overlays for upstream Agent loading, injection and Muzzle."""
from pathlib import Path
import argparse, difflib, hashlib, json, re, shutil
p = argparse.ArgumentParser(); p.add_argument("--sdk", required=True, type=Path); args = p.parse_args()
from source_compat import adapt

root = Path(__file__).resolve().parents[1]
build = root / 'java6-agent/build'
output = build / 'tooling-src'
if output.exists(): shutil.rmtree(output)
modules = ['javaagent-bootstrap', 'javaagent-extension-api', 'muzzle', 'javaagent-tooling',
           'instrumentation-annotations-support', 'sdk-autoconfigure-support', 'declarative-config-bridge', 'sdk:exporters/logging', 'javaagent-internal-logging-simple']
manifest, patch, excluded = [], [], []
for module in modules:
    base = (args.sdk / module[4:] if module.startswith('sdk:') else root / module) / 'src/main/java'
    for source in sorted(base.rglob('*.java')):
        relative = source.relative_to(base)
        name = source.name
        # Java 6 has no invokedynamic. Use upstream's injecting implementation on all JVMs.
        # Declarative YAML is not part of this distribution's SDK configuration yet.
        original = source.read_text()
        if ('/indy/' in source.as_posix() and name not in ('AdviceInliningPoolStrategy.java', 'ForceDynamicallyTypedAssignReturnedFactory.java')) or name.endswith('LookupSupplier.java') or 'import io.opentelemetry.sdk.autoconfigure.declarativeconfig.' in original or name.endswith('ComponentProvider.java') or name in (
                'IndyBootstrapDispatcher.java', 'JavaagentDistributionAccessCustomizerProvider.java'):
            excluded.append({'module': module, 'path': str(relative)})
            continue
        original = source.read_text()
        prepared_bootstrap = build / 'src' / relative
        text = prepared_bootstrap.read_text() if module == 'javaagent-bootstrap' and prepared_bootstrap.exists() else adapt(original, map_defaults=False)
        text = text.replace('import io.opentelemetry.instrumentation.config.internal.DeclarativeConfigV3Preview;\n', '')
        text = text.replace('DeclarativeConfigV3Preview.V3_PREVIEW_PROPERTY', '"otel.instrumentation.common.v3-preview"')
        text = text.replace('import org.jetbrains.annotations.Nullable;', 'import javax.annotation.Nullable;')
        text = text.replace('import org.jetbrains.annotations.NotNull;', 'import javax.annotation.Nonnull;').replace('@NotNull', '@Nonnull')
        text = text.replace('UnaryOperator.identity()', 'java8.util.function.UnaryOperators.identity()')
        if name == 'Slf4jSimpleLogger.java':
            levels=['ERROR','WARN','INFO','DEBUG','TRACE']
            enabled='switch (level) {\n'+''.join('      case '+v+': return logger.is'+v.title()+'Enabled();\n' for v in levels)+'      default: throw new IllegalStateException("Unknown logging level");\n    }'
            emit='switch (level) {\n'+''.join('      case '+v+': logger.'+v.lower()+'(message, error); return;\n' for v in levels)+'      default: throw new IllegalStateException("Unknown logging level");\n    }'
            text=text.replace('return logger.isEnabledForLevel(toSlf4jLevel(level));',enabled)
            text=text.replace('logger.makeLoggingEventBuilder(toSlf4jLevel(level)).setCause(error).log(message);',emit)
        text = text.replace('Stream.of(', 'java8.util.stream.RefStreams.of(')
        text = text.replace('Stream.empty()', 'java8.util.stream.RefStreams.empty()')
        text = text.replace('Stream.concat(', 'java8.util.stream.RefStreams.concat(')
        text = text.replace('String.join(', 'io.opentelemetry.java6.InstrumentationStrings.join(')
        if name == 'DefineClassHandler.java':
            text = text.replace('ThreadLocal.withInitial(() -> DefineClassContextImpl.ROOT)', 'new ThreadLocal<DefineClassContextImpl>() { @Override protected DefineClassContextImpl initialValue() { return DefineClassContextImpl.ROOT; } }')
        if name == 'InClassLoaderMatcher.java':
            text = text.replace('ThreadLocal.withInitial(() -> new boolean[1])', 'new ThreadLocal<boolean[]>() { @Override protected boolean[] initialValue() { return new boolean[1]; } }')
        if name == 'ExperimentalConfig.java':
            text = text.replace('ConcurrentHashMap.newKeySet()', 'java.util.Collections.newSetFromMap(new ConcurrentHashMap<String, Boolean>())')
        if name == 'AgentInstaller.java':
            text = text.replace('classLoadCallbacks.computeIfAbsent(', 'java8.util.Maps.computeIfAbsent(classLoadCallbacks, ')
        if name == 'ClassLoaderMap.java':
            text = text.replace('getClassLoaderData(classLoader, classInjector, true)\n        .computeIfAbsent(key, unused -> value.get())', 'java8.util.Maps.computeIfAbsent(getClassLoaderData(classLoader, classInjector, true), key, unused -> value.get())')
        if name == 'TrieImpl.java':
            text = text.replace('node.children.computeIfAbsent(', 'java8.util.Maps.computeIfAbsent(node.children, ')
            text = text.replace('Map.Entry.comparingByKey()', 'java8.util.Maps.Entry.comparingByKey()')
        if name == 'HelperInjector.java':
            text = text.replace('additionalResources.forEach(', 'java8.util.Maps.forEach(additionalResources, ')
            text = text.replace('map.putIfAbsent(', 'java8.util.Maps.putIfAbsent(map, ')
        if name == 'DeclarativeConfigPropertiesBridge.java':
            text = text.replace('propertyValue\n        .getPropertyKeys()\n        .forEach(', 'java8.lang.Iterables.forEach(propertyValue.getPropertyKeys(), ')
        if name == 'AgentTooling.java':
            text = text.replace('ServiceLoader.load(ClassFileLocatorProvider.class, AgentTooling.class.getClassLoader())\n        .forEach(', 'java8.lang.Iterables.forEach(ServiceLoader.load(ClassFileLocatorProvider.class, AgentTooling.class.getClassLoader()), ')
        if name == 'RegexUrlTemplateCustomizerInitializer.java':
            text = text.replace('    DeclarativeConfigUtil.getInstrumentationConfig(', '    java8.lang.Iterables.forEach(DeclarativeConfigUtil.getInstrumentationConfig(')
            text = text.replace('.getStructuredList("url_template_rules", emptyList())\n        .forEach(', '.getStructuredList("url_template_rules", emptyList()), ')
        if name == 'ReferencesPrinter.java':
            text = text.replace('System.lineSeparator()', 'System.getProperty("line.separator")')
        if name == 'AgentBuilderUtil.java':
            text = text.replace('Collections.emptyIterator()', 'Collections.emptyList().iterator()')
        if name == 'CallDepthThreadLocalMap.java':
            start = text.index('  private static final ClassValue<ThreadLocalDepth> TLS =')
            end = text.index('  static CallDepth getCallDepth', start)
            text = text[:start] + '  private static final io.opentelemetry.instrumentation.api.internal.cache.Cache<Class<?>, ThreadLocalDepth> TLS = io.opentelemetry.instrumentation.api.internal.cache.Cache.weak();\n\n' + text[end:]
            text = text.replace('TLS.get(k).get()', 'TLS.computeIfAbsent(k, unused -> new ThreadLocalDepth()).get()')
        if name == 'InstrumentedTaskClasses.java':
            start = text.index('  private static final ClassValue<Boolean> INSTRUMENTED_TASK_CLASS =')
            body = text.index('          // do not instrument ignored task classes', start)
            end = text.index('\n        }\n      };', body)
            method = text[body:end]
            text = text[:start] + '  private static final io.opentelemetry.instrumentation.api.internal.cache.Cache<Class<?>, Boolean> INSTRUMENTED_TASK_CLASS = io.opentelemetry.instrumentation.api.internal.cache.Cache.weak();\n\n  private static Boolean computeInstrumentedTaskClass(Class<?> taskClass) {\n' + method + '\n  }' + text[end + len('\n        }\n      };'):]
            text = text.replace('INSTRUMENTED_TASK_CLASS.get(taskClass)', 'INSTRUMENTED_TASK_CLASS.computeIfAbsent(taskClass, InstrumentedTaskClasses::computeInstrumentedTaskClass)')
        if name == 'ReferencesPrinter.java':
            text = text.replace('import static java.lang.System.lineSeparator;\n', '')
            text = text.replace('lineSeparator()', 'System.getProperty("line.separator")')
        if name == 'AgentBuilderUtil.java':
            text = text.replace('import static java.util.Collections.emptyIterator;\n', '')
            text = text.replace('return emptyIterator();', 'return java.util.Collections.emptyList().iterator();')
        if name in ('AsyncOperationEndStrategiesImpl.java', 'WeakRefAsyncOperationEndStrategies.java'):
            text = text.replace('    registerStrategy(Jdk8AsyncOperationEndStrategy.INSTANCE);', '    try {\n      Class.forName("java.util.concurrent.CompletionStage", false, null);\n      registerStrategy(Jdk8AsyncOperationEndStrategy.INSTANCE);\n    } catch (ClassNotFoundException unavailableOnJava6) {\n      // Keep user-registered asynchronous strategies available on older JVMs.\n    }')
        if name == 'WeakRefAsyncOperationEndStrategies.java':
            start = text.index('    strategies.removeIf(')
            end = text.index('        });', start) + len('        });')
            text = text[:start] + '    for (WeakReference<AsyncOperationEndStrategy> ref : strategies) {\n      AsyncOperationEndStrategy s = ref.get();\n      if (s == null || s == strategy) strategies.remove(ref);\n    }' + text[end:]
            text = text.replace('strategies.removeIf(ref -> ref.get() == null);', 'for (WeakReference<AsyncOperationEndStrategy> ref : strategies) {\n          if (ref.get() == null) strategies.remove(ref);\n        }')
        if name == 'HelperResources.java':
            text = text.replace('RESOURCES\n        .computeIfAbsent(classLoader, unused -> new ConcurrentHashMap<>())\n        .compute(path, (k, v) -> append(v, urls))', 'java8.util.Maps.compute(RESOURCES.computeIfAbsent(classLoader, unused -> new ConcurrentHashMap<>()), path, (k, v) -> append(v, urls))')
            text = text.replace('allClassLoadersResources.compute(', 'java8.util.Maps.compute(allClassLoadersResources, ')
        if name == 'ExtensionClassLoader.java':
            text = text.replace('import java.nio.file.Files;\n', '')
            text = text.replace('tempFile\n              .getCanonicalFile()\n              .toPath()\n              .startsWith(tempDirectory.getCanonicalFile().toPath())', '(tempFile.getCanonicalFile().equals(tempDirectory.getCanonicalFile()) || tempFile.getCanonicalPath().startsWith(tempDirectory.getCanonicalPath() + File.separator))')
            text = text.replace('tempDirectory = Files.createTempDirectory("otel-extensions").toFile();', 'tempDirectory = File.createTempFile("otel-extensions", "");\n      if (!tempDirectory.delete() || !tempDirectory.mkdir()) {\n        throw new IOException("Cannot create extension directory");\n      }')
        if name == 'RuntimeFieldBasedImplementationSupplier.java':
            text = text.replace('type.getTypeName(), fieldType.getTypeName()', 'getTypeName(type), getTypeName(fieldType)')
            index = text.rfind('}')
            text = text[:index] + '  private static String getTypeName(Class<?> type) {\n    int dimensions = 0;\n    while (type.isArray()) { dimensions++; type = type.getComponentType(); }\n    StringBuilder name = new StringBuilder(type.getName());\n    for (int i = 0; i < dimensions; i++) name.append("[]");\n    return name.toString();\n  }\n' + text[index:]
        if name == 'SafeServiceLoader.java':
            text = text.replace('Collections.sort(', 'java.util.Collections.sort(')
        if name == 'MethodCache.java':
            text = text.replace('this.get(key.getDeclaringClass()).computeIfAbsent(key, mappingFunction)', 'java8.util.Maps.computeIfAbsent(this.get(key.getDeclaringClass()), key, mappingFunction)')
        if name == 'AgentInstaller.java':
            text = text.replace('iterable.spliterator()', 'java8.util.Spliterators.spliteratorUnknownSize(iterable.iterator(), 0)')
            text = text.replace('public void close() throws Exception {', 'public void close() throws java.io.IOException {')
        text = text.replace('ClassLoader.registerAsParallelCapable();', '')
        text = text.replace('getClassLoadingLock(name)', 'this')
        if name == 'InstrumentationModuleInstaller.java':
            text = re.sub(r'import io.opentelemetry.javaagent.tooling.instrumentation.indy.[^;]+;\n', '', text)
            text = text.replace('boolean useIndy = useIndy(instrumentationModule);', 'boolean useIndy = false;')
            start = text.index('    if (useIndy) {')
            end = text.index('  private AgentBuilder installInjectingModule(', start)
            text = text[:start] + '    return installInjectingModule(instrumentationModule, parentAgentBuilder);\n  }\n\n' + text[end:]
        if name == 'InstrumentationModuleInstaller.java':
            text = text.replace('experimentalModule\n                          .jpmsModulesToOpen()\n                          .forEach(', 'java8.util.Maps.forEach(experimentalModule.jpmsModulesToOpen(), ')
        if name == 'GlobalIgnoredTypesConfigurer.java':
            text = text.replace('import io.opentelemetry.javaagent.tooling.instrumentation.indy.InstrumentationModuleClassLoader;\n', '')
            text = text.replace('InstrumentationModuleClassLoader.class.getName()', '"io.opentelemetry.javaagent.tooling.instrumentation.indy.InstrumentationModuleClassLoader"')
        if name == 'HelperInjector.java':
            text = re.sub(r'import [^;]+LookupSupplier;\n', '', text)
            text = text.replace('import java.lang.invoke.MethodHandles;\n', '')
            text = text.replace('import java.nio.file.Files;\n', '')
            start = text.index('  private static final Map<String, MethodHandles.Lookup> packageLookups')
            end = text.index('  private void injectBootstrapClassLoader(', start)
            text = text[:start] + '  private static final boolean denyUnsafe = Boolean.getBoolean("otel.javaagent.testing.deny-unsafe");\n\n' + text[end:]
            start = text.index('    if (ClassInjector.UsingLookup.isAvailable()) {')
            end = text.index('    if (classnameToBytes.isEmpty()) {', start)
            text = text[:start] + text[end:]
            text = text.replace('return Files.createTempDirectory("opentelemetry-temp-jars").toFile();', 'File directory = File.createTempFile("opentelemetry-temp-jars", "");\n      if (!directory.delete() || !directory.mkdir()) throw new IOException("Cannot create helper directory");\n      return directory;')
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        manifest.append({'module': module, 'path': str(relative), 'adapted': text != original,
                         'source_sha256': hashlib.sha256(original.encode()).hexdigest()})
        if text != original:
            patch.extend(difflib.unified_diff(original.splitlines(True), text.splitlines(True),
                         fromfile=module + '/' + str(relative), tofile='generated/' + str(relative)))
# Reuse the official SDK HTTP sender with the reviewed compatibility overlay.
http_manifest = json.loads((root / 'java6-agent/http-compat/sources.json').read_text())[-1]
for relative_name, expected in http_manifest['prepared'].items():
    relative = Path(relative_name)
    source = build / 'http-transport-src/sender' / relative
    data = source.read_bytes()
    assert hashlib.sha256(data).hexdigest() == expected, source
    target = output / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    manifest.append({'module': 'sdk:exporters/sender/okhttp', 'path': relative_name,
                     'adapted': expected != http_manifest['sources'][relative_name],
                     'source_sha256': http_manifest['sources'][relative_name]})
patch.append((root / 'java6-agent/http-compat/sender.patch').read_text())
(build / 'tooling-sources.json').write_text(json.dumps(manifest, indent=2) + '\n')
(build / 'tooling-excluded.json').write_text(json.dumps(excluded, indent=2) + '\n')
(build / 'tooling-adaptation.patch').write_text(''.join(patch))
print('Prepared', len(manifest), 'upstream tooling sources')
