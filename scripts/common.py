"""Small immutable-stage primitives; never load credentials from config files."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import socket
import tempfile
import time
import urllib.request
import urllib.parse
import uuid


def encode(x):
    return (json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n').encode('utf8')


def digest(x):
    return hashlib.sha256(encode(x)).hexdigest()


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
    return h.hexdigest()


def write_new(path, raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():raise FileExistsError(path)
    temp=path.with_name('.'+path.name+'.staging-'+uuid.uuid4().hex)
    with temp.open('xb') as f:
        f.write(raw);f.flush();os.fsync(f.fileno())
    os.link(temp,path)  # atomic no-clobber publication on the same filesystem
    temp.unlink()


def records(path):
    with Path(path).open(encoding='utf8') as f:
        for line in f:
            if line.strip(): yield json.loads(line)


def config(path):
    c=json.loads(Path(path).read_text(encoding='utf8'))
    if (c['mix']['oe_percent'],c['mix']['mcq_percent']) != (70,30):
        raise ValueError('this recipe requires 70% OE /30% MCQ')
    if c['judge']['mode'] not in ('text','vision'):raise ValueError('judge mode must be text or vision')
    if any(c['download'][key]<=0 for key in ('files_concurrency','segments_per_file','retries')):
        raise ValueError('download concurrency and retries must be positive')
    if not c['judge']['base_url'].startswith(('http://','https://')) or not c['judge']['base_url'].rstrip('/').endswith('/v1'):
        raise ValueError('base_url must be http(s)://HOST:PORT/v1')
    return c


def ipv4_connect(address,timeout=30,source_address=None):
    """Per-connection IPv4 selection; never monkey-patch global DNS/socket state."""
    host,port=address
    if not isinstance(timeout,(int,float)):timeout=30
    deadline=time.monotonic()+timeout;last_error=None
    for family,kind,proto,_,sockaddr in socket.getaddrinfo(host,port,socket.AF_INET,socket.SOCK_STREAM):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('IPv4 connect deadline exceeded')
        sock=socket.socket(family,kind,proto)
        try:
            sock.settimeout(remaining)
            if source_address:sock.bind(source_address)
            sock.connect(sockaddr);return sock
        except OSError as e:last_error=e;sock.close()
    if last_error:raise last_error
    raise OSError('no IPv4 addresses returned')


class IPv4HTTPSConnection(http.client.HTTPSConnection):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self._create_connection=ipv4_connect


class IPv4HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self,req):
        return self.do_open(IPv4HTTPSConnection,req,context=self._context)


class HostTraceRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self,trace):self.trace=trace
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        old,new=urllib.parse.urlparse(req.full_url),urllib.parse.urlparse(newurl)
        if self.trace is not None:self.trace.append({'status':code,'host':new.hostname,'scheme':new.scheme})
        if old.scheme=='https' and new.scheme!='https':raise ValueError('HTTPS redirect downgrade refused')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def direct_open(req, timeout=30,force_ipv4=False,redirect_hosts=None):
    # Both local model API and downloads bypass environment proxies.
    handlers=[urllib.request.ProxyHandler({}),HostTraceRedirect(redirect_hosts)]
    if force_ipv4:handlers.append(IPv4HTTPSHandler())
    return urllib.request.build_opener(*handlers).open(req,timeout=timeout)


def safe_rel(value):
    if not isinstance(value,str) or not value or '\\' in value or ':' in value or value.startswith('/') or any(p in ('','.','..') for p in value.split('/')):
        raise ValueError('unsafe relative path')
    return value


def under(root, rel):
    root=Path(root).resolve(); path=(root/safe_rel(rel)).resolve()
    if root not in path.parents: raise ValueError('path escapes root')
    return path


def code_sha():
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=Path(__file__).resolve().parents[1],timeout=10,text=True).strip()


def identity(path):
    p=Path(path);s=p.stat()
    return {'path':str(p.resolve()),'bytes':s.st_size,'mtime_ns':s.st_mtime_ns}


class Stage:
    def __init__(self,root,name,binding):
        self.binding=binding;self.key=digest(binding)
        self.final=Path(root)/name/self.key[:20]
        self.reused=self.final.exists()
        if self.reused:
            receipt=json.loads((self.final/'receipt.json').read_text('utf8'))
            if receipt['binding']!=binding: raise ValueError('stage binding mismatch')
            for name,info in receipt['files'].items():
                if (self.final/name).stat().st_size!=info['bytes']:raise ValueError('stage size mismatch')
            self.path=self.final
        else:
            self.final.parent.mkdir(parents=True,exist_ok=True)
            self.path=Path(tempfile.mkdtemp(prefix='.'+self.key[:12]+'-',dir=self.final.parent))

    def commit(self,stats):
        if self.reused:return self.final
        files={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in self.path.iterdir() if p.is_file()}
        write_new(self.path/'receipt.json',encode({'binding':self.binding,'files':files,'stats':stats,'time':time.time()}))
        # Final is never overwritten; stages are serialized by the outer run lock.
        if self.final.exists(): raise FileExistsError(self.final)
        os.rename(self.path,self.final);return self.final


class RunLock:
    def __init__(self,root):self.path=Path(root)/'.run.lock'
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.f=self.path.open('a+b')
        try:
            if os.name=='nt':
                import msvcrt
                self.f.seek(0);self.f.write(b'0');self.f.flush();self.f.seek(0);msvcrt.locking(self.f.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except Exception:self.f.close();raise RuntimeError('another run holds the lock')
        return self
    def __exit__(self,*exc):self.f.close()
