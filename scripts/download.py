"""Direct, SHA-verified selected-file downloads with resumable HTTP ranges."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import time
import urllib.parse
import urllib.error
import urllib.request

from common import direct_open, encode, safe_rel, sha, under, write_new

PROJECT=Path(__file__).resolve().parents[1]


def metadata(url):
    with direct_open(url,20) as r:
        raw=r.read(8*1024*1024+1)
    if len(raw)>8*1024*1024: raise ValueError('metadata response too large')
    return json.loads(raw)


def probe(c):
    url='https://modelscope.cn/api/v1/datasets/topdktu/UniRec40M/repo/tree?Revision=master&Root=&Recursive=true&PageNumber=1&PageSize=100'
    data=metadata(url)
    if data.get('Code')!=200: raise ValueError('ModelScope metadata request failed')
    files=data['Data']['Files']
    subsets=sorted({s['subset'] for s in c['sources']})
    available={s:sum(f.get('Size',0) for f in files if f['Path'].startswith(s+'/')) for s in subsets}
    return {'repository':'topdktu/UniRec40M','source_url':url,'listed_total':data.get('TotalCount'),
            'files':[{'path':f['Path'],'bytes':f.get('Size'),'sha256':f.get('Sha256')} for f in files],
            'subset_bytes':available,'usable':all(available.values()),
            'note':'An existing dataset card is not evidence that its data files exist.'}


def manifest():return json.loads((PROJECT/'research/source_files.json').read_text('utf8'))


def network_error(error):
    """Classify without leaking proxy credentials or signed redirect URLs."""
    cause=error.reason if isinstance(error,urllib.error.URLError) else error
    info={'error_type':type(error).__name__,'cause_type':type(cause).__name__}
    if isinstance(error,urllib.error.HTTPError):info.update(category='http',http_status=error.code)
    elif isinstance(cause,socket.gaierror):info.update(category='dns',errno=cause.errno)
    elif isinstance(cause,ssl.SSLCertVerificationError):info.update(category='tls_certificate',verify_code=cause.verify_code,verify_message=cause.verify_message)
    elif isinstance(cause,ssl.SSLError):info.update(category='tls',ssl_reason=cause.reason)
    elif isinstance(cause,TimeoutError):info['category']='timeout'
    elif isinstance(cause,ConnectionRefusedError):info.update(category='connection_refused',errno=cause.errno)
    elif isinstance(cause,OSError):info.update(category='network_os_error',errno=cause.errno)
    else:info['category']='response_or_protocol'
    return info


def file_url(c,f,base=None):
    base=(base or c['download']['base_url']).rstrip('/')
    parsed=urllib.parse.urlparse(base)
    if parsed.scheme!='https' or not parsed.netloc or parsed.username or parsed.password or parsed.path not in ('','/'):
        raise ValueError('mirror must be an HTTPS origin without credentials/path')
    return base+'/datasets/topdu/UniRec40M/resolve/'+manifest()['revision']+'/'+urllib.parse.quote(safe_rel(f['path']),safe='/')


def benchmark(c):
    f=next(f for f in manifest()['files'] if f['bytes']>1000000000)
    observations=[]
    print('[ocr-qa] NETWORK_POLICY '+json.dumps(network_report()),flush=True)
    for base in c['download']['benchmark_urls']:
        started=time.monotonic();redirects=[]
        try:
            req=urllib.request.Request(file_url(c,f,base),headers={'Range':'bytes=0-4194303','Accept-Encoding':'identity'})
            with direct_open(req,20,force_ipv4=c['download'].get('force_ipv4',False),redirect_hosts=redirects) as r:
                if r.status!=206:raise ValueError('server ignored Range; no unbounded read')
                raw=r.read(4194305)
            if len(raw)!=4194304:raise ValueError('invalid range body length')
            observations.append({'origin':base,'bytes':len(raw),'seconds':round(time.monotonic()-started,3),'mib_per_second':round(4/(time.monotonic()-started),3),'redirect_hosts':redirects})
        except Exception as e:observations.append({'origin':base,**network_error(e),'redirect_hosts':redirects})
    return {'scope':'4MiB per configured origin, sequential, no proxy; CDN/network-dependent, not full-run throughput','force_ipv4':c['download'].get('force_ipv4',False), 'results':observations}


def network_report():
    import subprocess
    keys=[k for k in os.environ if k.lower() in ('http_proxy','https_proxy','all_proxy')]
    git=subprocess.run(['git','config','--show-origin','--get-regexp',r'http\..*proxy|https\..*proxy'],capture_output=True,text=True,timeout=10)
    # Report presence only: proxy URLs can contain credentials.
    return {'proxy_environment_variable_names':keys,'git_proxy_setting_count':len(git.stdout.splitlines()),
            'policy':'HTTP downloader bypasses all environment proxies; no Git transfer; global settings unchanged'}


def verify(path,f):
    if path.stat().st_size!=f['bytes']:raise ValueError('download size mismatch: '+f['path'])
    if f.get('sha256'):
        actual=sha(path);expected=f['sha256']
    else:
        h=hashlib.sha1(('blob '+str(f['bytes'])+'\0').encode())
        with path.open('rb') as src:
            for raw in iter(lambda:src.read(8*1024*1024),b''):h.update(raw)
        actual=h.hexdigest();expected=f['git_blob_sha1']
    if actual!=expected:raise ValueError('upstream hash mismatch: '+f['path'])
    return actual


def range_bytes(c,url,start,end,dest):
    expected=end-start+1
    if dest.exists():
        if dest.stat().st_size!=expected:raise ValueError('committed range size mismatch')
        return
    for attempt in range(c['download']['retries']):
        temp=dest.with_name(dest.name+'.attempt-'+str(time.time_ns()))
        try:
            req=urllib.request.Request(url,headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity'})
            with direct_open(req,c['download']['timeout_seconds'],force_ipv4=c['download'].get('force_ipv4',False)) as r, temp.open('xb') as out:
                if urllib.parse.urlparse(r.geturl()).scheme!='https':raise ValueError('HTTPS downgrade refused')
                if r.status!=206 or not r.headers.get('Content-Range','').startswith(f'bytes {start}-{end}/'):
                    raise ValueError('origin does not support exact HTTP byte ranges')
                left=expected
                while left:
                    data=r.read(min(left,1024*1024))
                    if not data:raise ValueError('short range response')
                    out.write(data);left-=len(data)
                if r.read(1):raise ValueError('overlong range response')
                out.flush();os.fsync(out.fileno())
            os.rename(temp,dest);return
        except Exception:
            # Only our incomplete attempt is removed, never a source file.
            if temp.exists():temp.unlink()
            if attempt+1>=c['download']['retries']:raise
            time.sleep(min(2**attempt,8))


def download_one(c,f):
    root=Path(c['raw_root']);dest=under(root,f['path']);dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():
        verify(dest,f);return {'path':f['path'],'status':'verified_existing','bytes':f['bytes']}
    size=c['download']['segment_bytes']
    if size<1048576:raise ValueError('segment_bytes must be >=1MiB')
    part_root=Path(c['work_root'])/'download-parts'/hashlib.sha256(file_url(c,f).encode()).hexdigest()
    part_root.mkdir(parents=True,exist_ok=True)
    spans=[(i,min(i+size,f['bytes'])-1,part_root/str(i)) for i in range(0,f['bytes'],size)]
    def one(span):
        range_bytes(c,file_url(c,f),*span)
        if span[0]%(16*size)==0:
            print('[ocr-qa] DOWNLOAD_RANGE '+json.dumps({'path':f['path'],'completed_range_start':span[0],'completed_range_end':span[1],'file_bytes':f['bytes']}),flush=True)
    with ThreadPoolExecutor(max_workers=c['download']['segments_per_file']) as pool:list(pool.map(one,spans))
    temp=dest.with_name('.'+dest.name+'.assembling-'+str(time.time_ns()))
    with temp.open('xb') as out:
        for _,_,part in spans:
            with part.open('rb') as src:shutil.copyfileobj(src,out,8*1024*1024)
        out.flush();os.fsync(out.fileno())
    verify(temp,f)
    if dest.exists():raise FileExistsError(dest)
    os.link(temp,dest);temp.unlink()
    for _,_,part in spans:part.unlink()  # only exact verified owned range caches
    print('[ocr-qa] DOWNLOAD_FILE '+json.dumps({'path':f['path'],'bytes':f['bytes']}),flush=True)
    return {'path':f['path'],'status':'downloaded_verified','bytes':f['bytes']}


def download(c,subset=None):
    print('[ocr-qa] NETWORK_POLICY '+json.dumps(network_report()),flush=True)
    if c['download']['files_concurrency']*c['download']['segments_per_file']>128:
        raise ValueError('global HTTP concurrency cap is128')
    files=[f for f in manifest()['files'] if subset is None or f['path'].split('/')[0]==subset]
    if not files:raise ValueError('unknown/empty subset')
    root=Path(c['raw_root']);root.mkdir(parents=True,exist_ok=True)
    needed=sum(f['bytes'] for f in files if not under(root,f['path']).exists())
    # Includes one extra largest file for range assembly. Extracted image/LMDB workspace is separate.
    if shutil.disk_usage(root).free<needed+max(f['bytes'] for f in files)+2*1024**3:
        raise ValueError('insufficient download disk space')
    with ThreadPoolExecutor(max_workers=c['download']['files_concurrency']) as pool:
        results=list(pool.map(lambda f:download_one(c,f),files))
    return {'provider':'HF-compatible HTTPS','origin':c['download']['base_url'],'revision':manifest()['revision'], 'files':results,'bytes':sum(f['bytes'] for f in files)}


def assemble(c):
    """Join exact HWDB fragments into a derived LMDB, leaving all originals intact."""
    files=[f for f in manifest()['files'] if f['path'].startswith('HWDB2Train/image_lmdb/data.mdb.part_')]
    files.sort(key=lambda f:f['path'])
    if not files:raise ValueError('no bound HWDB fragments')
    out=Path(c['work_root'])/'assembled/HWDB2Train/image_lmdb/data.mdb'
    expected=sum(f['bytes'] for f in files)
    receipt=out.with_suffix('.receipt.json')
    binding={'revision':manifest()['revision'],'parts':[{'path':f['path'],'sha256':f['sha256']} for f in files],'bytes':expected}
    if out.exists():
        if not receipt.exists() or json.loads(receipt.read_text())['binding']!=binding or out.stat().st_size!=expected:
            raise ValueError('unverified assembled LMDB already exists')
        return {'output':str(out),'reused':True}
    out.parent.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(out.parent).free<expected+1024**3:raise ValueError('insufficient space for derived HWDB LMDB')
    temp=out.with_name('.data.mdb-'+str(time.time_ns()));h=hashlib.sha256()
    with temp.open('xb') as dst:
        for f in files:
            src=under(c['raw_root'],f['path']);verify(src,f)
            with src.open('rb') as stream:
                for raw in iter(lambda:stream.read(8*1024*1024),b''):dst.write(raw);h.update(raw)
        dst.flush();os.fsync(dst.fileno())
    os.rename(temp,out);write_new(receipt,encode({'binding':binding,'sha256':h.hexdigest()}))
    return {'output':str(out),'bytes':expected}
