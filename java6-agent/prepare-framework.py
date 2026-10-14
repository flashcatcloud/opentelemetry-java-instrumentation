#!/usr/bin/env python3
"""Prepare upstream framework sources; preserve upstream files and record adaptations."""
from pathlib import Path
import argparse, difflib, hashlib, json, re, shutil
p=argparse.ArgumentParser();p.add_argument('--sdk', required=True,type=Path);a=p.parse_args()
r=Path(__file__).resolve().parent;b=r/'build';out=b/'framework-src'
if out.exists():shutil.rmtree(out)
modules=['sdk/trace','api/all','sdk/all','sdk/metrics','sdk/logs','api/incubator','sdk-extensions/autoconfigure-spi','sdk-extensions/autoconfigure','exporters/common','exporters/otlp/common','exporters/otlp/all','exporters/sender/grpc-managed-channel']
patch=[];manifest=[]
from source_compat import adapt

for module in modules:
 for f in sorted((a.sdk/module/'src/main/java').rglob('*.java')):
    name=f.relative_to(a.sdk/module/'src/main/java').as_posix()
    if module=='sdk/trace' and f.name!='SdkTracerProviderUtil.java':continue
    if module=='api/all' and f.name!='GlobalOpenTelemetry.java':continue
    if module=='api/incubator' and ('/trace/' in name or '/propagation/' in name):continue
    if (b/'exporter-src'/name).exists():continue
    if f.name in ('DeclarativeConfigUtil.java','InstrumentationConfigUtil.java','JreDoubleAdder.java','JreLongAdder.java'):continue
    if f.name.endswith('ComponentProvider.java') or f.name=='OtlpDeclarativeConfigUtil.java':continue
    original=f.read_text();s=adapt(original)
    if f.name=='AutoConfiguredOpenTelemetrySdkBuilder.java':
      s=s.replace('DeclarativeConfigUtil.configureFromSpi(componentLoader)', 'null')
      s=s.replace('return DeclarativeConfigUtil.configureFromFile(logger, configurationFile, componentLoader);','throw new io.opentelemetry.sdk.autoconfigure.spi.ConfigurationException("Declarative YAML configuration is not included in this Java 6 distribution");')
    s=s.replace('import org.codehaus.mojo.animal_sniffer.IgnoreJRERequirement;', '').replace('@IgnoreJRERequirement','')
    if f.name=='AdderUtil.java':
      s=s.replace('hasJreAdder ? new JreLongAdder() : new AtomicLongLongAdder()', 'new AtomicLongLongAdder()').replace('hasJreAdder ? new JreDoubleAdder() : new AtomicLongDoubleAdder()', 'new AtomicLongDoubleAdder()')
    if f.name=='UpstreamGrpcSenderProvider.java':
      s=s.replace('minimalFallbackManagedChannel(grpcSenderConfig.getEndpoint())', 'configuredManagedChannel(grpcSenderConfig)')
      boundary=s.index('  /**\n   * If {@link ManagedChannel}')
      s=s[:boundary]+'  /** Configure the private transport using the SDK\'s already parsed settings. */\n  private static ManagedChannel configuredManagedChannel(GrpcSenderConfig config) {\n    URI endpoint = config.getEndpoint();\n    boolean tls = endpoint.getScheme().equals("https");\n    int port = endpoint.getPort() < 0 ? (tls ? 443 : 80) : endpoint.getPort();\n    io.grpc.netty.NettyChannelBuilder builder =\n        io.grpc.netty.NettyChannelBuilder.forAddress(endpoint.getHost(), port);\n    long connectMillis = config.getConnectTimeout().toMillis();\n    builder.withOption(io.netty.channel.ChannelOption.CONNECT_TIMEOUT_MILLIS,\n        Integer.valueOf((int) Math.min(Integer.MAX_VALUE, Math.max(1, connectMillis))));\n    builder.maxInboundMessageSize((int) Math.min(Integer.MAX_VALUE, config.getMaxResponseBodySize()));\n    if (!tls) {\n      builder.usePlaintext(true);\n    } else {\n      javax.net.ssl.SSLContext ssl = config.getSslContext();\n      if (ssl == null) {\n        try {\n          ssl = javax.net.ssl.SSLContext.getDefault();\n        } catch (java.security.NoSuchAlgorithmException error) {\n          throw new IllegalStateException("Default TLS context is unavailable", error);\n        }\n      }\n      java.util.List<String> enabled = config.getEnabledProtocols();\n      String[] protocols = enabled == null ? null : enabled.toArray(new String[enabled.size()]);\n      io.netty.handler.ssl.ApplicationProtocolConfig alpn =\n          new io.netty.handler.ssl.ApplicationProtocolConfig(\n              io.netty.handler.ssl.ApplicationProtocolConfig.Protocol.ALPN,\n              io.netty.handler.ssl.ApplicationProtocolConfig.SelectorFailureBehavior.NO_ADVERTISE,\n              io.netty.handler.ssl.ApplicationProtocolConfig.SelectedListenerFailureBehavior.ACCEPT,\n              "h2");\n      builder.sslContext(new io.netty.handler.ssl.JdkSslContext(\n          ssl, true, io.netty.handler.codec.http2.Http2SecurityUtil.CIPHERS,\n          io.netty.handler.ssl.SupportedCipherSuiteFilter.INSTANCE, alpn,\n          io.netty.handler.ssl.ClientAuth.NONE, protocols, false));\n    }\n    return builder.build();\n  }\n}\n'
    if f.name=='UpstreamGrpcSender.java':
      s=s.replace('requestCallOptions.withDeadlineAfter(timeout)', 'requestCallOptions.withDeadlineAfter(timeout.toNanos(), TimeUnit.NANOSECONDS)')
      s=s.replace('for (Map.Entry<String, List<String>> entry : headers.entrySet()) {', 'for (Map.Entry<String, List<String>> entry : headers.entrySet()) {\n        java8.util.StringJoiner joined = new java8.util.StringJoiner(",");\n        for (String value : entry.getValue()) { joined.add(value); }')
      s=s.replace('String.join(",", entry.getValue())', 'joined.toString()')
    dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(s)
    if s!=original:patch.extend(difflib.unified_diff(original.splitlines(True),s.splitlines(True),fromfile=module+'/'+name,tofile='generated/'+name))
    manifest.append({'module':module,'path':name,'adapted':s!=original,'source_sha256':hashlib.sha256(original.encode()).hexdigest()})
(b/'framework-adaptation.patch').write_text(''.join(patch))
(b/'framework-sources.json').write_text(json.dumps(manifest,indent=2))
print('Prepared',len(manifest),'framework sources')
