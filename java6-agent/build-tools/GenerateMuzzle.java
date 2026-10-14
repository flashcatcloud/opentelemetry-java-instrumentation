/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
import java.io.File;
import io.opentelemetry.javaagent.tooling.muzzle.generation.MuzzleCodeGenerationPlugin;
import net.bytebuddy.ByteBuddy;
import net.bytebuddy.ClassFileVersion;
import net.bytebuddy.description.type.TypeDescription;
import net.bytebuddy.dynamic.ClassFileLocator;
import net.bytebuddy.pool.TypePool;

/** Invokes the upstream build plugin on the actual desugared module classes. */
public final class GenerateMuzzle {
  public static void main(String[] args) throws Exception {
    File directory = new File(args[0]);
    try (ClassFileLocator locator = new ClassFileLocator.Compound(
        new ClassFileLocator.ForFolder(directory), ClassFileLocator.ForClassLoader.ofSystemLoader());
        MuzzleCodeGenerationPlugin plugin = new MuzzleCodeGenerationPlugin(new File[] {directory})) {
      for (int i = 1; i < args.length; i++) {
        TypeDescription type = TypePool.Default.of(locator).describe(args[i]).resolve();
        if (!plugin.matches(type)) throw new IllegalArgumentException("Not an instrumentation module: " + args[i]);
        plugin.apply(new ByteBuddy(ClassFileVersion.JAVA_V6).redefine(type, locator), type, locator)
            .make().saveIn(directory);
        System.out.println("MUZZLE_GENERATED " + args[i]);
      }
    }
  }
}
