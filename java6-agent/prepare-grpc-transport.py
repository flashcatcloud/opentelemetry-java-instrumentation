#!/usr/bin/env python3
"""Backport upstream gRPC header iteration for maintained Netty; no protocol rewrite."""
from pathlib import Path
import difflib, hashlib, json, shutil, zipfile
root = Path(__file__).resolve().parent
build = root / 'build'
output = build / 'grpc-overlay-src'
if output.exists(): shutil.rmtree(output)
archives = {}
for entry in json.loads((root / 'grpc-source-deps.json').read_text()):
    path = build / 'grpc-source-deps' / entry['file']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']
    archives[entry['file']] = path
name = 'io/grpc/netty/GrpcHttp2HeadersUtils.java'
with zipfile.ZipFile(archives['grpc-netty-1.6.0-sources.jar']) as z:
    original = z.read(name).decode()
    negotiation_original = z.read('io/grpc/netty/ProtocolNegotiators.java').decode()
with zipfile.ZipFile(archives['grpc-netty-1.68.1-sources.jar']) as z:
    upstream = z.read(name).decode()
    abstract = z.read('io/grpc/netty/AbstractHttp2Headers.java').decode()
    negotiation_upstream = z.read('io/grpc/netty/ProtocolNegotiators.java').decode()
assert 'SSLParameters sslParams = sslEngine.getSSLParameters();' in negotiation_upstream
assert negotiation_original.count('SSLParameters sslParams = new SSLParameters();') == 1
negotiation = negotiation_original.replace('SSLParameters sslParams = new SSLParameters();', 'SSLParameters sslParams = sslEngine.getSSLParameters();')
negotiation = negotiation.replace('import javax.annotation.Nullable;', '').replace('@Nullable', '')
def method(source, marker):
    assert source.count(marker) == 1
    start = source.index(marker)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        if source[end] == '{': depth += 1
        elif source[end] == '}': depth -= 1
        end += 1
    return source[start:end]
iterator = method(upstream, '    public Iterator<Map.Entry<CharSequence, CharSequence>> iterator()')
listing = method(upstream, '    private List<Map.Entry<CharSequence, CharSequence>> namesAndValuesToImmutableList()')
listing = listing.replace('new ArrayList<>(values.length)', 'new ArrayList<Map.Entry<CharSequence, CharSequence>>(values.length)')
adapted = original.replace('import java.util.List;', 'import java.util.List;\nimport java.util.Map;\nimport java.util.Iterator;\nimport java.util.AbstractMap;')
marker = '    protected final String namesAndValuesToString()'
assert adapted.count(marker) == 1
adapted = adapted.replace(marker, '    @Override\n' + iterator + '\n\n' + listing + '\n\n' + marker)
records = []
for path, text in [(name, adapted), ('io/grpc/netty/AbstractHttp2Headers.java', abstract), ('io/grpc/netty/ProtocolNegotiators.java', negotiation)]:
    target = output / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    records.append(dict(path=path, prepared_sha256=hashlib.sha256(text.encode()).hexdigest()))
(build / 'grpc-overlay-sources.json').write_text(json.dumps(dict(archives=json.loads((root/'grpc-source-deps.json').read_text()), sources=records, rationale='Reuse upstream gRPC 1.68.1 iterator and abstract header API with Java 6 syntax on gRPC 1.6'), indent=2)+'\n')
(build / 'grpc-overlay-adaptation.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True), adapted.splitlines(True), fromfile='grpc-netty-1.6.0/'+name, tofile='generated/'+name)))
print('Prepared upstream gRPC header compatibility overlay')

with (build / 'grpc-overlay-adaptation.patch').open('a') as out:
    out.write(''.join(difflib.unified_diff(negotiation_original.splitlines(True), negotiation.splitlines(True), fromfile='grpc-netty-1.6.0/io/grpc/netty/ProtocolNegotiators.java', tofile='generated/io/grpc/netty/ProtocolNegotiators.java')))
