#!/usr/bin/env python3
"""Prepare pinned official component sources for the compatibility build."""
from pathlib import Path
import json,hashlib,difflib,shutil,re
from source_compat import adapt
r=Path(__file__).resolve().parents[1];b=r/'java6-agent/build';out=b/'modules-src'
if out.exists():shutil.rmtree(out)
resources=b/'module-resources'
if resources.exists():shutil.rmtree(resources)
resources.mkdir()
manifest=[];patch=[]
for module in ['instrumentation/runtime-telemetry/library', 'instrumentation/runtime-telemetry/javaagent', 'instrumentation/resources/library', 'instrumentation/http-url-connection/javaagent', 'instrumentation/jdbc/library', 'instrumentation/jdbc/javaagent', 'instrumentation/internal/internal-class-loader/javaagent', 'instrumentation/internal/internal-class-loader/compile-stub',
               'instrumentation/servlet/servlet-common/bootstrap', 'instrumentation/servlet/servlet-common/library',
               'instrumentation/servlet/servlet-common-javax/library', 'instrumentation/servlet/servlet-common/javaagent',
               'instrumentation/servlet/servlet-3.0/library', 'instrumentation/servlet/servlet-3.0/javaagent',
               'instrumentation/tomcat/tomcat-common-7.0/javaagent', 'instrumentation/tomcat/tomcat-7.0/javaagent', 'instrumentation/jedis/jedis-common-1.4/javaagent', 'instrumentation/jedis/jedis-2.0/javaagent', 'instrumentation/apache-dubbo-2.7/library-autoconfigure', 'instrumentation/apache-dubbo-2.7/javaagent', 'java6-agent/legacy-dubbo', 'instrumentation/executors/bootstrap', 'instrumentation/executors/javaagent', 'instrumentation/spring/spring-webmvc/spring-webmvc-common-3.1/javaagent', 'instrumentation/spring/spring-webmvc/spring-webmvc-3.1/javaagent', 'instrumentation/apache-httpclient/apache-httpclient-4.0/javaagent', 'instrumentation/lettuce/lettuce-common/library', 'instrumentation/lettuce/lettuce-5.1/library', 'instrumentation/lettuce/lettuce-5.1/javaagent', 'instrumentation/rabbitmq-2.7/javaagent', 'instrumentation/mongo/mongo-3.1/library', 'instrumentation/mongo/mongo-3.1/javaagent', 'instrumentation/kafka/kafka-clients/kafka-clients-common-0.11/library', 'instrumentation/kafka/kafka-clients/kafka-clients-0.11/bootstrap', 'instrumentation/kafka/kafka-clients/kafka-clients-0.11/javaagent', 'instrumentation/grpc-1.6/library', 'instrumentation/grpc-1.6/javaagent', 'instrumentation/elasticsearch/elasticsearch-rest-common-5.0/bootstrap', 'instrumentation/elasticsearch/elasticsearch-rest-common-5.0/javaagent', 'instrumentation/elasticsearch/elasticsearch-rest-7.0/javaagent']:
    if module.endswith('/javaagent'):
        resource_base=r/module/'src/main/resources'
        for resource in resource_base.rglob('*'):
            if resource.is_file():
                target=resources/resource.relative_to(resource_base);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(resource,target)
    base=r/module/'src/main/java'
    for source in sorted(base.rglob('*.java')):
        relative=source.relative_to(base)
        # Reuse upstream host detection and SPI; other resource detectors need separate JVM audits.
        if module == 'instrumentation/resources/library' and source.name not in ('HostResource.java', 'HostResourceProvider.java'):
            continue
        # The Agent needs internal instrumentation helpers, not JDBC decorator APIs.
        if module == 'instrumentation/jdbc/library' and (
            '/internal/' not in source.as_posix() or source.name.startswith('OpenTelemetry')
            or '/datasource/' in source.as_posix()):
            continue
        if module == 'instrumentation/runtime-telemetry/javaagent' and source.name != 'RuntimeTelemetryInstaller.java':
            continue
        original=source.read_text();text=original
        if module == 'instrumentation/runtime-telemetry/library' and source.name == 'Threads.java':
            text=text.replace('import java.lang.invoke.MethodHandle;', 'import java.lang.reflect.Method;').replace('import java.lang.invoke.MethodHandles;\n', '').replace('import java.lang.invoke.MethodType;\n', '')
            text=text.replace('MethodHandle', 'Method')
            text=text.replace('MethodHandles.publicLookup()\n              .findVirtual(ThreadInfo.class, "isDaemon", MethodType.methodType(boolean.class))', 'ThreadInfo.class.getMethod("isDaemon")')
            # The type replacement above also touches the MethodHandles token.
            text=text.replace('Methods.publicLookup()\n              .findVirtual(ThreadInfo.class, "isDaemon", MethodType.methodType(boolean.class))', 'ThreadInfo.class.getMethod("isDaemon")')
            text=text.replace('NoSuchMethodException | IllegalAccessException', 'NoSuchMethodException')
            text=text.replace('counts.compute(', 'java8.util.Maps.compute(counts, ').replace('counts.forEach(', 'java8.util.Maps.forEach(counts, ')
        text=adapt(text,map_defaults=False)
        if module == 'instrumentation/runtime-telemetry/library' and source.name == 'GarbageCollector.java':
            text=text.replace('result.add(() -> notificationEmitter.removeNotificationListener(listener));', 'result.add(() -> { try { notificationEmitter.removeNotificationListener(listener); } catch (javax.management.ListenerNotFoundException failure) { throw new java.io.IOException("GC listener cleanup failed", failure); } });')
        if module == 'instrumentation/runtime-telemetry/library' and source.name == 'JmxRuntimeMetricsFactory.java':
            text=text.replace('observables.addAll(BufferPools.registerObservers(meter, metricNamePredicate));', 'if (hasBufferPoolMxBean()) { observables.addAll(BufferPools.registerObservers(meter, metricNamePredicate)); }')
            text=text.replace('  private JmxRuntimeMetricsFactory() {}', '  private static boolean hasBufferPoolMxBean() { try { Class.forName("java.lang.management.BufferPoolMXBean", false, null); return true; } catch (ClassNotFoundException unavailable) { return false; } }\n\n  private JmxRuntimeMetricsFactory() {}')

        text=text.replace("UnaryOperator.identity()", "java8.util.function.UnaryOperators.identity()")
        # ForkJoinTask does not exist on Java 6. Give its upstream advice its own
        # Muzzle boundary, so absence does not disable Runnable/Callable propagation.
        if source.name == 'ExecutorsInstrumentationModule.java':
            fork=text.replace('ExecutorsInstrumentationModule', 'ForkJoinExecutorsInstrumentationModule')
            start=fork.index('    return asList(');end=fork.index(');',start)+2
            fork=fork[:start]+'    return asList(new JavaForkJoinTaskInstrumentation(), new ForkJoinExecutorInstrumentation());'+fork[end:]
            fork=fork.replace('  @Override\n  public List<TypeInstrumentation>', '  @Override\n  public net.bytebuddy.matcher.ElementMatcher.Junction<ClassLoader> classLoaderMatcher() { try { Class.forName("java.util.concurrent.ForkJoinTask", false, null); return net.bytebuddy.matcher.ElementMatchers.any(); } catch (ClassNotFoundException absent) { return net.bytebuddy.matcher.ElementMatchers.none(); } }\n\n  @Override\n  public List<TypeInstrumentation>')
            target=out/relative.with_name('ForkJoinExecutorsInstrumentationModule.java')
            target.parent.mkdir(parents=True,exist_ok=True);target.write_text(fork)
            patch.extend(difflib.unified_diff(original.splitlines(True),fork.splitlines(True),fromfile=str(source.relative_to(r)),tofile='generated/'+str(target.relative_to(out))))
            text=text.replace('        new JavaForkJoinTaskInstrumentation(),\n','')
        if source.name == 'KafkaConsumerInstrumentation.java':
            # This type belongs to Kafka's public JVM API, not the Agent's clock API.
            # Match by name so Java6 need not load java.time.Duration.
            assert 'takesArgument(0, Duration.class)' in text
            text=text.replace('import org.threeten.bp.Duration;\n', '')
            text=text.replace('takesArgument(0, Duration.class)', 'takesArgument(0, named("java.time.Duration"))')
        if source.name == 'VirtualFieldHelper.java':
            start=text.index('  public static final VirtualField<ForkJoinTask')
            end=text.index('  public static final VirtualField<Future',start)
            field=text[start:end]
            fork='package io.opentelemetry.javaagent.instrumentation.executors;\nimport io.opentelemetry.instrumentation.api.util.VirtualField;\nimport io.opentelemetry.javaagent.bootstrap.executors.PropagatedContext;\nimport java.util.concurrent.ForkJoinTask;\npublic final class ForkJoinVirtualFieldHelper {\n'+field+'}\n'
            target=out/relative.with_name('ForkJoinVirtualFieldHelper.java');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(fork)
            patch.extend(difflib.unified_diff([],fork.splitlines(True),fromfile='/dev/null',tofile='generated/'+str(target.relative_to(out))))
            text=text[:start]+text[end:]
            text=text.replace('import java.util.concurrent.ForkJoinTask;\n','')
        if source.name == 'JavaExecutorInstrumentation.java':
            blocks=re.findall(r'    transformer.applyAdviceToMethod\(\n        named\("(?:execute|submit|invoke)"\)\.and\(takesArgument\(0, ForkJoinTask.class\)\),\n        getClass\(\)\.getName\(\) \+ "\$SetJavaForkJoinStateAdvice"\);\n',text)
            assert len(blocks)==3, 'Upstream ForkJoin submission advice changed'
            start=text.index('  @SuppressWarnings("unused")\n  public static class SetJavaForkJoinStateAdvice')
            end=text.index('  @SuppressWarnings("unused")',start+10)
            advice=text[start:end]
            header=text[:text.index('class JavaExecutorInstrumentation')]
            fork=header+'class ForkJoinExecutorInstrumentation implements TypeInstrumentation {\n  public ElementMatcher<TypeDescription> typeMatcher() { return executorNameMatcher().and(isExecutor()); }\n  public void transform(TypeTransformer transformer) {\n'+''.join(blocks)+'  }\n'+advice+'}\n'
            fork=fork.replace('executors.VirtualFieldHelper.FORKJOINTASK', 'executors.ForkJoinVirtualFieldHelper.FORKJOINTASK').replace('takesArgument(0, ForkJoinTask.class)', 'takesArgument(0, named("java.util.concurrent.ForkJoinTask"))')
            target=out/relative.with_name('ForkJoinExecutorInstrumentation.java');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(fork)
            patch.extend(difflib.unified_diff(original.splitlines(True),fork.splitlines(True),fromfile=str(source.relative_to(r)),tofile='generated/'+str(target.relative_to(out))))
            text=text[:start]+text[end:]
            for block in blocks:text=text.replace(block,'')
            text=text.replace('import java.util.concurrent.ForkJoinTask;\n','').replace('import static io.opentelemetry.javaagent.instrumentation.executors.VirtualFieldHelper.FORKJOINTASK_PROPAGATED_CONTEXT;\n','')
        if source.name == 'JavaForkJoinTaskInstrumentation.java':
            text=text.replace('executors.VirtualFieldHelper.FORKJOINTASK', 'executors.ForkJoinVirtualFieldHelper.FORKJOINTASK').replace('ForkJoinTask.class.getName()', '"java.util.concurrent.ForkJoinTask"')
        if '/lettuce/v5_1/' in str(relative) and source.name == 'CompatibilityChecker.java':
            text=text.replace('Tracing.getContext();', 'Tracing.class.getMethod("getContext").invoke(null);')
        if '/kafkaclients/' in str(relative):
            # Keep the public JDK Iterator callback ABI on supported Java 8+ clients.
            if source.name in ('TracingIterator.java', 'TracingListIterator.java', 'TracingIterable.java'):
                text = text.replace('import java8.util.function.Consumer;', 'import java.util.function.Consumer;')
            for expression in ('carrier.getRecord().headers()', 'carrier.getRecord().headers().headers(key)',
                               'consumerRecord.headers().headers(name)', 'consumerRecord.headers()',
                               'request.getRecord().headers().headers(name)', 'request.getRecord().headers()',
                               'request.getRecord().headers().headers(key)'):
                text = text.replace(expression + '.spliterator()', 'java8.lang.Iterables.spliterator(' + expression + ')')
        if source.name == 'ElasticsearchDbAttributesGetter.java':
            text = text.replace('return reader.lines().collect(joining());', 'StringBuilder body = new StringBuilder();\n      String line;\n      while ((line = reader.readLine()) != null) body.append(line);\n      return body.toString();')
        if source.name == 'ElasticsearchQuerySanitizerInstaller.java':
            text = text.replace('    ElasticsearchQuerySanitizerAccess.internalSetSanitizer(', '    String javaVersion = System.getProperty("java.specification.version");\n    if ("1.6".equals(javaVersion) || "1.7".equals(javaVersion)) return;\n    ElasticsearchQuerySanitizerAccess.internalSetSanitizer(')
        if source.name == 'GrpcRequestGetter.java':
            text = text.replace('import static java.util.Collections.emptyIterator;\n', '')
            text = text.replace('emptyIterator()', 'java.util.Collections.<String>emptyList().iterator()')
        if source.name == 'GrpcConfig.java':
            text = text.replace('ConcurrentHashMap.newKeySet()', 'java.util.Collections.newSetFromMap(new ConcurrentHashMap<String, Boolean>())')
        if source.name == 'GrpcRpcAttributesGetter.java':
            text = text.replace('values.spliterator()', 'java8.lang.Iterables.spliterator(values)')
        if source.name == 'MongoDbAttributesGetter.java':
            # javac merges multi-catch reflection failures to a Java 7 superclass.
            text = re.sub(r'catch \((InstantiationException\s*\|\s*IllegalAccessException\s*\|\s*InvocationTargetException\s*\|\s*NoSuchMethodException) ignored\) \{([^{}]*)\}',
                lambda m: ' '.join('catch (' + kind.strip() + ' ignored) {' + m.group(2) + '}' for kind in m.group(1).split('|')), text)
        if source.name == 'IsGrailsHandler.java':
            start = text.index('  private static final ClassValue<Boolean> cache =')
            end = text.index('  public static boolean isGrailsHandler', start)
            text = text[:start] + text[end:]
            text = text.replace('return cache.get(handler.getClass());', 'return handler.getClass().getName().startsWith("org.grails.");')
        if source.name == 'OpenTelemetryHandlerMappingFilter.java':
            text=text.replace('import java.lang.invoke.MethodHandle;', 'import java.lang.reflect.Method;').replace('import java.lang.invoke.MethodHandles;\n','').replace('import java.lang.invoke.MethodType;\n','')
            text=re.sub(r'\bMethodHandle\b','Method',text)
            text=text.replace('return MethodHandles.lookup()\n          .findVirtual(\n              HandlerMapping.class, "usesPathPatterns", MethodType.methodType(boolean.class));',
                'Method method = HandlerMapping.class.getMethod("usesPathPatterns");\n      return method.getReturnType() == boolean.class ? method : null;')
            text=text.replace('catch (NoSuchMethodException | IllegalAccessException ignored)', 'catch (NoSuchMethodException ignored)')
            text=text.replace('return MethodHandles.lookup()\n          .findStatic(\n              pathUtilsClass,\n              "parseAndCache",\n              MethodType.methodType(requestPathClass, HttpServletRequest.class));',
                'Method method = pathUtilsClass.getMethod("parseAndCache", HttpServletRequest.class);\n      return method.getReturnType() == requestPathClass && java.lang.reflect.Modifier.isStatic(method.getModifiers()) ? method : null;')
            text=text.replace('catch (ClassNotFoundException | NoSuchMethodException | IllegalAccessException ignored)',
                'catch (ClassNotFoundException ignored) {\n      return null;\n    } catch (NoSuchMethodException ignored)')
            text=text.replace('    } catch (IllegalAccessException ignored) {\n      return null;', '')
            text=text.replace('parseAndCacheMh.invoke(request)', 'parseAndCacheMh.invoke(null, request)')
            text=text.replace('Class.forName("org.springframework.web.util.ServletRequestPathUtils")', 'Class.forName("org.springframework.web.util.ServletRequestPathUtils", false, HandlerMapping.class.getClassLoader())')
            text=text.replace('Class.forName("org.springframework.http.server.RequestPath")', 'Class.forName("org.springframework.http.server.RequestPath", false, HandlerMapping.class.getClassLoader())')
            assert 'MethodHandles' not in text and 'MethodType' not in text
        if source.name == 'JedisRequestContext.java':
            text=text.replace('  public void detachAndEnd() {',
                '  public void detachAndEnd() { detachAndEnd(null); }\n\n'
                '  public void detachAndEnd(@Nullable Throwable methodThrowable) {\n'
                '    if (methodThrowable != null) throwable = methodThrowable;')
        if '/jedis/v2_0/' in str(relative) and source.name == 'JedisInstrumentation.java':
            text=text.replace('@Advice.Enter @Nullable JedisRequestContext<JedisRequest> requestContext)',
                '@Advice.Enter @Nullable JedisRequestContext<JedisRequest> requestContext,\n'
                '        @Advice.Thrown @Nullable Throwable throwable)')
            text=text.replace('requestContext.detachAndEnd();', 'requestContext.detachAndEnd(throwable);')
        if '/jedis/v2_0/' in str(relative) and source.name == 'JedisConnectionInstrumentation.java':
            # sendCommand(Command) delegates to sendCommand(Command, byte[][]).
            # Share a depth counter so each logical command is captured once, including pipelines.
            for expression in ('JedisRequest.create(connection, command)', 'JedisRequest.create(connection, command, asList(args))'):
                text=text.replace('      JedisRequest request = '+expression+';',
                    '      if (io.opentelemetry.javaagent.bootstrap.CallDepth.forClass(AdviceScope.class).getAndIncrement() > 0) return null;\n'
                    '      JedisRequest request = '+expression+';')
            text=text.replace('      if (adviceScope != null) {\n        adviceScope.end(throwable);',
                '      if (io.opentelemetry.javaagent.bootstrap.CallDepth.forClass(AdviceScope.class).decrementAndGet() > 0) return;\n'
                '      if (adviceScope != null) {\n        adviceScope.end(throwable);')
        # Match the upstream JDBC shadow/bootstrap package split.
        text=text.replace('io.opentelemetry.instrumentation.jdbc.internal.dbinfo', 'io.opentelemetry.javaagent.bootstrap.jdbc')
        relative=Path(str(relative).replace('io/opentelemetry/instrumentation/jdbc/internal/dbinfo', 'io/opentelemetry/javaagent/bootstrap/jdbc'))
        target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
        manifest.append(dict(module=module,path=str(relative),source_sha256=hashlib.sha256(original.encode()).hexdigest(),adapted=text!=original))
        patch.extend(difflib.unified_diff(original.splitlines(True),text.splitlines(True),fromfile=module+'/'+str(relative),tofile='generated/'+str(relative)))
from legacy_dubbo_overlay import generate as generate_legacy_dubbo
generate_legacy_dubbo(r, out, manifest, patch)
(b/'module-sources.json').write_text(json.dumps(manifest,indent=2)+'\n');(b/'module-adaptation.patch').write_text(''.join(patch))
print('Prepared official component sources:',len(manifest))
