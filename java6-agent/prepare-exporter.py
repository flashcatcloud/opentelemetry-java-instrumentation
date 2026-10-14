#!/usr/bin/env python3
"""Reuse pinned upstream OTLP marshalers with explicit Java6 API adaptations."""
from pathlib import Path
from zipfile import ZipFile
import argparse,difflib,hashlib,json,re,shutil,urllib.request
p=argparse.ArgumentParser();p.add_argument('--sdk',required=True,type=Path);a=p.parse_args()
r=Path(__file__).resolve().parent;b=r/'build';out=b/'exporter-src'
if out.exists():shutil.rmtree(out)
modules={'opentelemetry-exporter-common':'acf2b186d7b21c7f935340bbe60ef3e24e977c8e0370a3977ffb01d1f2a96311','opentelemetry-exporter-otlp-common':'2c0729b531834d6862cf954a0965152b5df34949473e474137beaccb7c507430'}
patch=[];sources=[]
for module,sha in modules.items():
 jar=b/'deps'/(module+'-1.66.0-sources.jar')
 if not jar.exists():jar.write_bytes(urllib.request.urlopen('https://repo.maven.apache.org/maven2/io/opentelemetry/'+module+'/1.66.0/'+jar.name,timeout=30).read())
 assert hashlib.sha256(jar.read_bytes()).hexdigest()==sha
 with ZipFile(jar) as z:
  for name in sorted(z.namelist()):
   if not name.endswith('.java'):continue
   selected=(name.startswith('io/opentelemetry/exporter/internal/marshal/')
    or name.startswith('io/opentelemetry/proto/')
    or name.startswith('io/opentelemetry/exporter/internal/otlp/traces/')
    or name.startswith('io/opentelemetry/exporter/internal/otlp/') and name.count('/')==5)
   if not selected or name.endswith('SpanReusableDataMarshaler.java'):continue
   original=z.read(name).decode()
   module_path='exporters/common' if module=='opentelemetry-exporter-common' else 'exporters/otlp/common'
   local=a.sdk/module_path/'src/main/java'/name
   if local.exists():original=local.read_text()
   s=original
   for before,after in [('java.util.function.','java8.util.function.'),('java.util.Optional','java8.util.Optional'),('java.nio.charset.StandardCharsets','io.opentelemetry.java6.StandardCharsets'),('java.io.UncheckedIOException','io.opentelemetry.java6.UncheckedIOException')]:s=s.replace(before,after)
   s=s.replace('import java.util.Base64;','').replace('Base64.getEncoder().encode(value)','org.apache.commons.codec.binary.Base64.encodeBase64(value)')
   s=re.sub(r'([\w.]+)\.computeIfAbsent\(',r'io.opentelemetry.java6.Maps.computeIfAbsent(\1, ',s)
   for var in ['messages','dataList','items']:s=s.replace(var+'.forEach(', 'java8.lang.Iterables.forEach('+var+', ')
   if name.endswith('Serializer.java'):
    marker='RepeatedElementPairWriter<K, V> writer'
    if marker in s:
     i=s.index(marker);s=s[:i]+s[i:].replace('java8.lang.Iterables.forEach(messages, writer);','java8.util.Maps.forEach(messages, writer);',1)
   if name.endswith('StatelessMarshalerUtil.java'):
    marker='RepeatedElementPairSizeCalculator<K, V> sizeCalculator'
    i=s.index(marker);s=s[:i]+s[i:].replace('java8.lang.Iterables.forEach(messages, sizeCalculator);','java8.util.Maps.forEach(messages, sizeCalculator);',1)
   for primitive,boxed in [('boolean','Boolean'),('long','Long'),('double','Double')]:s=s.replace('('+primitive+') value.getValue()', '('+boxed+') value.getValue()')
   s=s.replace('Character.isSurrogate(', 'io.opentelemetry.java6.Characters.isSurrogate(')
   s=s.replace('AutoCloseable','java.io.Closeable')
   dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(s)
   if original!=s:patch.extend(difflib.unified_diff(original.splitlines(True),s.splitlines(True),fromfile=module+'/'+name,tofile='generated/'+name))
   sources.append({'module':module,'path':name,'source_sha256':hashlib.sha256(original.encode()).hexdigest(),'adapted':original!=s})
(b/'exporter-adaptation.patch').write_text(''.join(patch))
(b/'exporter-sources.json').write_text(json.dumps({'version':'1.66.0','source_archives':modules,'sources':sources},indent=2))
print('Prepared',len(sources),'official exporter sources')
