/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
import java.nio.file.*;
import org.objectweb.asm.*;

/** Replace calls before Retrolambda drops them, retaining Java 7+ cleanup diagnostics. */
public final class PreserveSuppressedExceptions {
  public static void main(String[] args) throws Exception {
    final int[] rewritten = {0};
    try (java.util.stream.Stream<Path> files = Files.walk(Paths.get(args[0]))) {
      for (Path file : (Iterable<Path>) files.filter(p -> p.toString().endsWith(".class"))::iterator) {
        ClassReader reader = new ClassReader(Files.readAllBytes(file));
        ClassWriter writer = new ClassWriter(0);
        final boolean[] changed = {false};
        reader.accept(new ClassVisitor(Opcodes.ASM9, writer) {
          @Override public MethodVisitor visitMethod(int access, String name, String descriptor, String signature, String[] exceptions) {
            MethodVisitor delegate = super.visitMethod(access, name, descriptor, signature, exceptions);
            return new MethodVisitor(Opcodes.ASM9, delegate) {
              @Override public void visitMethodInsn(int opcode, String owner, String method, String desc, boolean isInterface) {
                if (opcode == Opcodes.INVOKEVIRTUAL && owner.equals("java/lang/Throwable") && method.equals("addSuppressed") && desc.equals("(Ljava/lang/Throwable;)V")) {
                  super.visitMethodInsn(Opcodes.INVOKESTATIC, "io/opentelemetry/java6/SuppressedExceptions", method, "(Ljava/lang/Throwable;Ljava/lang/Throwable;)V", false);
                  changed[0] = true;
                  rewritten[0]++;
                } else {
                  super.visitMethodInsn(opcode, owner, method, desc, isInterface);
                }
              }
            };
          }
        }, 0);
        if (changed[0]) Files.write(file, writer.toByteArray());
      }
    }
    System.out.println("SUPPRESSED_CALLS_PRESERVED=" + rewritten[0]);
  }
}
