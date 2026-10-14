import java.nio.file.*;
import java.util.*;
import org.objectweb.asm.*;
/** Regression for Muzzle string descriptors and ordinary non-descriptor constants. */
public final class RelocateAgentTest {
  public static void main(String[] args) throws Exception {
    Path root=Files.createTempDirectory("relocation-test"), input=root.resolve("in"), output=root.resolve("out");
    Files.createDirectories(input);
    String[] values={"()Ljava8/util/Optional;", "Ljava8/util/Optional;", "[Ljava8/util/Optional;",
        "java8.util.Optional", "java8/util/Optional", "[", "(ordinary text)", "SELECT ? FROM dual", "org.slf4j.simpleLogger.logFile", "org/slf4j/Logger", "/org/threeten/bp/TZDB.dat", "org/threeten/bp/TZDB.dat", "org.threeten.bp.format.ChronologyText", "org/apache/commons/codec/binary/Base64", "org.jctools.queues.SpscArrayQueue"};
    ClassWriter writer=new ClassWriter(0);
    writer.visit(Opcodes.V1_6,Opcodes.ACC_PUBLIC,"Probe",null,"java/lang/Object",null);
    MethodVisitor method=writer.visitMethod(Opcodes.ACC_PUBLIC|Opcodes.ACC_STATIC,"probe","()V",null,null);
    method.visitCode();for(String value:values){method.visitLdcInsn(value);method.visitInsn(Opcodes.POP);}
    method.visitInsn(Opcodes.RETURN);method.visitMaxs(1,0);method.visitEnd();writer.visitEnd();
    Files.write(input.resolve("Probe.class"),writer.toByteArray());
    Path resource=input.resolve("org/threeten/bp/TZDB.dat");
    Files.createDirectories(resource.getParent());Files.write(resource,new byte[]{1,2,3});
    Path service=input.resolve("META-INF/services/org.threeten.bp.zone.ZoneRulesProvider");
    Files.createDirectories(service.getParent());
    Files.write(service,"org.threeten.bp.zone.TzdbZoneRulesProvider\n".getBytes("UTF-8"));
    RelocateAgent.main(new String[]{input.toString(),output.toString()});
    if(!Arrays.equals(new byte[]{1,2,3},Files.readAllBytes(output.resolve("io/opentelemetry/javaagent/shaded/org/threeten/bp/TZDB.dat"))))throw new AssertionError("Resource relocation");
    String provider=new String(Files.readAllBytes(output.resolve("META-INF/services/io.opentelemetry.javaagent.shaded.org.threeten.bp.zone.ZoneRulesProvider")),"UTF-8");
    if(!provider.equals("io.opentelemetry.javaagent.shaded.org.threeten.bp.zone.TzdbZoneRulesProvider\n"))throw new AssertionError(provider);
    List<String> actual=new ArrayList<>();
    new ClassReader(Files.readAllBytes(output.resolve("Probe.class"))).accept(new ClassVisitor(Opcodes.ASM9){
      public MethodVisitor visitMethod(int access,String name,String descriptor,String signature,String[] exceptions){
        return new MethodVisitor(Opcodes.ASM9){public void visitLdcInsn(Object value){actual.add((String)value);}};
      }
    },0);
    for(int i=0;i<values.length;i++) {
      String expected=values[i].replace("java8/", "io/opentelemetry/javaagent/shaded/java8/").replace("java8.", "io.opentelemetry.javaagent.shaded.java8.").replace("org.slf4j.","io.opentelemetry.javaagent.slf4j.").replace("org/slf4j/","io/opentelemetry/javaagent/slf4j/");
      for(String prefix:new String[]{"org/threeten/","org/jctools/","org/apache/commons/codec/"}) {
        expected=expected.replace(prefix,"io/opentelemetry/javaagent/shaded/"+prefix)
            .replace(prefix.replace('/','.'),"io.opentelemetry.javaagent.shaded."+prefix.replace('/','.'));
      }
      if(!expected.equals(actual.get(i)))throw new AssertionError(values[i]+" -> "+actual.get(i));
    }
    try(java.util.stream.Stream<Path> files=Files.walk(root)){for(Path path:(Iterable<Path>)files.sorted(Comparator.reverseOrder())::iterator)Files.delete(path);}
    System.out.println("RELOCATION_OK descriptors, arrays, class names, ordinary constants");
  }
}
