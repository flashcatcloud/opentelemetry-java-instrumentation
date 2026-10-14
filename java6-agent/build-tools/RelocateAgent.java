/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
import java.nio.file.*;
import org.objectweb.asm.*;
import org.objectweb.asm.commons.*;

/** Build-only relocation using upstream javaagent-shadowing conventions. */
public final class RelocateAgent {
  private static final String[][] RULES = {
    {"org/slf4j", "io/opentelemetry/javaagent/slf4j"},
    {"org/threeten", "io/opentelemetry/javaagent/shaded/org/threeten"},
    {"org/jctools", "io/opentelemetry/javaagent/shaded/org/jctools"},
    {"org/apache/commons/codec", "io/opentelemetry/javaagent/shaded/org/apache/commons/codec"},
    {"io/opentelemetry/javaagent/bootstrap/internal/classloader/stub", "java/lang"},
    {"io/opentelemetry/instrumentation", "io/opentelemetry/javaagent/shaded/instrumentation"},
    {"io/opentelemetry/api", "io/opentelemetry/javaagent/shaded/io/opentelemetry/api"},
    {"io/opentelemetry/semconv", "io/opentelemetry/javaagent/shaded/io/opentelemetry/semconv"},
    {"io/opentelemetry/context", "io/opentelemetry/javaagent/shaded/io/opentelemetry/context"},
    {"io/opentelemetry/common", "io/opentelemetry/javaagent/shaded/io/opentelemetry/common"},
    {"io/opentelemetry/java6", "io/opentelemetry/javaagent/shaded/io/opentelemetry/java6"},
    {"java8", "io/opentelemetry/javaagent/shaded/java8"}
  };
  static String relocate(String name) {
    if (name.equals("java/util/logging/Logger")) return "io/opentelemetry/javaagent/bootstrap/PatchLogger";
    if (name.startsWith("io/opentelemetry/instrumentation/resources/") || name.startsWith("io/opentelemetry/instrumentation/spring/resources/")) return name;
    for (String[] rule : RULES) {
      if (name.equals(rule[0]) || name.startsWith(rule[0] + "/")) return rule[1] + name.substring(rule[0].length());
    }
    return name;
  }
  public static void main(String[] args) throws Exception {
    final Path source = Paths.get(args[0]), destination = Paths.get(args[1]);
    final Remapper remapper = new Remapper(Opcodes.ASM9) {
      @Override public String map(String name) { return relocate(name); }
      @Override public Object mapValue(Object value) {
        if (value instanceof String) {
          String name = (String) value;
          // Muzzle stores method/field descriptors as strings, not ASM Type constants.
          // Relocate their embedded types as well as ordinary binary class names.
          if (name.startsWith("(") && name.indexOf(')') >= 0) {
            try { return mapMethodDesc(name); } catch (IllegalArgumentException | IndexOutOfBoundsException ignored) { }
          }
          if ((name.startsWith("L") && name.endsWith(";")) || name.startsWith("[")) {
            try { return mapDesc(name); } catch (IllegalArgumentException | IndexOutOfBoundsException ignored) { }
          }
          // Class.getResourceAsStream also accepts absolute resource paths.
          if (name.startsWith("/")) {
            String resource = relocate(name.substring(1));
            if (!resource.equals(name.substring(1))) return "/" + resource;
          }
          String internal = name.indexOf('/') >= 0 ? name : name.replace('.', '/');
          String relocated = relocate(internal);
          if (!internal.equals(relocated)) return name.indexOf('/') >= 0 ? relocated : relocated.replace('/', '.');
        }
        return super.mapValue(value);
      }
    };
    try (java.util.stream.Stream<Path> paths = Files.walk(source)) {
      for (Path path : (Iterable<Path>) paths.filter(Files::isRegularFile)::iterator) {
        String name = source.relativize(path).toString().replace('\\', '/');
        if (name.startsWith("io/opentelemetry/javaagent/bootstrap/internal/classloader/stub/")) continue;
        byte[] bytes = Files.readAllBytes(path);
        if (name.endsWith(".class")) {
          ClassReader reader = new ClassReader(bytes);
          ClassWriter writer = new ClassWriter(0);
          reader.accept(new ClassRemapper(writer, remapper), 0);
          bytes = writer.toByteArray();
          name = relocate(reader.getClassName()) + ".class";
        } else if (name.startsWith("META-INF/services/")) {
          name = "META-INF/services/" + relocate(name.substring(18).replace('.', '/')).replace('/', '.');
          StringBuilder body = new StringBuilder();
          for (String line : new String(bytes, "UTF-8").split("\\n")) {
            String provider = line.trim();
            body.append(provider.startsWith("#") ? line : relocate(provider.replace('.', '/')).replace('/', '.')).append('\n');
          }
          bytes = body.toString().getBytes("UTF-8");
        } else {
          name = relocate(name);
        }
        Path output = destination.resolve(name);
        Files.createDirectories(output.getParent());
        Files.write(output, bytes);
      }
    }
  }
}
