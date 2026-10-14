#!/usr/bin/env python3
"""Generate an experimental Java 6 bootstrap from the pinned upstream sources.
Never rewrites production sources or lowers binary class-file version numbers.
"""
from pathlib import Path
import difflib
import re

root = Path(__file__).resolve().parents[1]
out = root / 'java6-agent/build'
src = out / 'src'
base = root / 'javaagent-bootstrap/src/main/java'
files = ['io/opentelemetry/javaagent/OpenTelemetryAgent.java'] + [
    'io/opentelemetry/javaagent/bootstrap/' + n + '.java'
    for n in ['AgentInitializer', 'AgentClassLoader', 'AgentStarter',
              'InstrumentationHolder', 'JavaagentFileHolder']]
patch = []
for name in files:
    original = (base / name).read_text()
    text = original.replace('import javax.annotation.Nullable;\n', '').replace('@Nullable ', '')
    text = re.sub(r'^\s*@Nullable\n', '', text, flags=re.MULTILINE)
    if name.endswith('OpenTelemetryAgent.java'):
        text = text.replace('try (JarFile agentJar = new JarFile(javaagentFile, false)) {',
                            'JarFile agentJar = new JarFile(javaagentFile, false);\n    try {')
        text = text.replace('      }\n    }\n    return javaagentFile;',
                            '      }\n    } finally {\n      agentJar.close();\n    }\n    return javaagentFile;')
    if name.endswith('AgentInitializer.java'):
        text = text.replace('import static java.util.Objects.requireNonNull;', '')
        text = text.replace('Instrumentation inst, File javaagentFile, boolean fromPremain, String agentArgs)',
                            'final Instrumentation inst, final File javaagentFile, final boolean fromPremain, final String agentArgs)')
        text = text.replace('isConfigEnabled(String propertyName, String environmentVariableName)',
                            'isConfigEnabled(final String propertyName, final String environmentVariableName)')
        text = text.replace('  private AgentInitializer() {}', '''  private static <T> T requireNonNull(T value) {
    if (value == null) { throw new NullPointerException(); }
    return value;
  }
  private AgentInitializer() {}''')
    if name.endswith('AgentClassLoader.java'):
        text = text.replace('import java.util.function.Function;', '')
        text = text.replace('public class AgentClassLoader extends URLClassLoader {', '''public class AgentClassLoader extends URLClassLoader {
  // Prototype only: serialized class loading on all JVM versions.
  public interface Function<T, R> { R apply(T value); }''')
        text = text.replace('ClassLoader.registerAsParallelCapable();', '').replace('registerAsParallelCapable();', '')
        text = text.replace('getClassLoadingLock(name)', 'this')
        text = text.replace('    @Override\n    public long getContentLengthLong()', '    public long getContentLengthLong()')
        text = text.replace('if ("1.8".equals(javaSpecVersion)) {\n      return 8;',
                            'if (javaSpecVersion.startsWith("1.")) {\n      return Integer.parseInt(javaSpecVersion.substring(2));')
        text = text.replace('try (InputStream is = jarFile.getInputStream(jarEntry)) {',
                            'InputStream is = jarFile.getInputStream(jarEntry);\n    try {')
        text = text.replace('        offset += read;\n      }\n    }',
                            '        offset += read;\n      }\n    } finally {\n      is.close();\n    }')
        text = text.replace('Enumeration<URL> delegate = super.findResources(name);', 'final Enumeration<URL> delegate = super.findResources(name);')
        text = text.replace('URL url = findJarResource(name);', 'final URL url = findJarResource(name);')
        text = text.replace('catch (InvocationTargetException | NoSuchMethodException | IllegalAccessException e)', 'catch (Exception e)')
    target = src / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    patch.extend(difflib.unified_diff(original.splitlines(True), text.splitlines(True), fromfile=name, tofile='generated/' + name))
(out / 'bootstrap-adaptation.patch').write_text(''.join(patch))
