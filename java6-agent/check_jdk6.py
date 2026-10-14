#!/usr/bin/env python3
"""Check JDK method/field links in emitted OTel classes against actual Oracle6 rt.jar.
No reachability exemptions for our generated classes. Backport libraries are runtime-tested separately.
"""
import struct, sys, zipfile
from pathlib import Path
class ClassFile:
    def __init__(self, data):
        self.d=data; self.i=8; self.cp=[None]
        n=self.u2()
        while len(self.cp)<n:
            t=self.u1()
            if t==1: v=self.take(self.u2()).decode('utf-8',errors='replace')
            elif t in (3,4): v=self.take(4)
            elif t in (5,6):
                self.cp.append((t,self.take(8)));self.cp.append(None);continue
            elif t in (7,8,16,19,20): v=self.u2()
            elif t in (9,10,11,12,18): v=(self.u2(),self.u2())
            elif t==15: v=(self.u1(),self.u2())
            else: raise ValueError(t)
            self.cp.append((t,v))
        self.u2();self.name=self.cl(self.u2());parent=self.u2()
        self.parents=([self.cl(parent)] if parent else [])+[self.cl(self.u2()) for _ in range(self.u2())]
        self.members=set()
        for kind in ['field','method']:
            for _ in range(self.u2()):
                self.u2();name=self.utf(self.u2());desc=self.utf(self.u2());self.members.add((kind,name,desc))
                for _ in range(self.u2()): self.u2();self.take(self.u4())
    def take(self,n): x=self.d[self.i:self.i+n];self.i+=n;return x
    def u1(self): return self.take(1)[0]
    def u2(self): return struct.unpack('>H',self.take(2))[0]
    def u4(self): return struct.unpack('>I',self.take(4))[0]
    def utf(self,n): return self.cp[n][1]
    def cl(self,n): return self.utf(self.cp[n][1])
rt=zipfile.ZipFile(sys.argv[1]);extras=[zipfile.ZipFile(p) for p in Path(sys.argv[1]).parent.glob('*.jar') if p.name != 'rt.jar'];cache={}
def get(name):
    if name not in cache:
        try: cache[name]=ClassFile(rt.read(name+'.class'))
        except KeyError:
            cache[name]=None
            for extra in extras:
                try: cache[name]=ClassFile(extra.read(name+'.class'));break
                except KeyError: pass
    return cache[name]
def has(name,member,seen=None):
    seen=set() if seen is None else seen
    if name in seen: return False
    seen.add(name);c=get(name)
    if c is None:return False
    if member in c.members:return True
    if member[1]=='<init>':return False
    return any(has(p,member,seen) for p in c.parents)
errors=set();count=0
for p in Path(sys.argv[2]).rglob('*.class'):
    c=ClassFile(p.read_bytes());count+=1
    if b'java/lang/ReflectiveOperationException' in p.read_bytes(): errors.add((c.name,'java/lang/ReflectiveOperationException',('class','','')))
    for item in c.cp[1:]:
        if item and item[0] in (9,10,11):
            owner_idx,nt_idx=item[1];owner=c.cl(owner_idx)
            if not owner.startswith(('java/','javax/')) or owner.startswith('javax/annotation/'):continue
            ni,di=c.cp[nt_idx][1];member=('field' if item[0]==9 else 'method', c.utf(ni),c.utf(di))
            if not has(owner,member):errors.add((c.name,owner,member))
for e in sorted(errors):print(e)
print('Checked',count,'classes; missing JDK6 links:',len(errors))
if count == 0:
    print("ERROR: no class files were checked")
    sys.exit(2)
sys.exit(bool(errors))
