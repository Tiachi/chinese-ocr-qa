"""Configurable download → mechanical → grounded QA → model review →70/30 delivery."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from common import RunLock, config, encode, write_new

PROJECT=Path(__file__).resolve().parents[1]
DEFAULT_CONFIG='/mnt/sfs/ltj/ocr_qa/config/unirec9.json'


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',default=os.environ.get('OCR_QA_CONFIG',DEFAULT_CONFIG))
    p.add_argument('command',choices=['init','configure','probe','proxy-inspect','network-diagnose','download-bench','download-fast','download','assemble','inspect','mechanical','draft','api-check','pilot','run','register','self-test','service'])
    p.add_argument('--base-url');p.add_argument('--model');p.add_argument('--mirror');p.add_argument('--mode',choices=['text','vision'])
    p.add_argument('--concurrency',type=int);p.add_argument('--subset');p.add_argument('--limit',type=int)
    p.add_argument('--retry-errors',action='store_true');p.add_argument('--delivery',type=Path)
    p.add_argument('--ipv4',action='store_true',help='force IPv4 only for this download/benchmark; no global network changes')
    p.add_argument('--service-config',default=str(PROJECT/'config/service.json'))
    return p


def main():
    args=parser().parse_args();path=Path(args.config)
    if args.command=='self-test':
        subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(PROJECT/'tests'),'-v'],check=True,timeout=180);return
    if args.command=='service':
        from service import start
        start(args.service_config);return
    if args.command=='proxy-inspect':
        from proxy_inspect import inspect_proxies
        print('[ocr-qa] PROXY_INSPECTION '+json.dumps(inspect_proxies(),ensure_ascii=False),flush=True);return
    if args.command=='init':
        if path.exists():print('[ocr-qa] CONFIG_REUSED '+str(path));return
        write_new(path,(PROJECT/'config/pipeline.json').read_bytes());print('[ocr-qa] CONFIG_CREATED '+str(path));return
    c=config(path if path.exists() else PROJECT/'config/pipeline.json')
    if args.ipv4:c['download']['force_ipv4']=True
    if args.command=='configure':
        if args.base_url:c['judge']['base_url']=args.base_url
        if args.model:c['judge']['model']=args.model
        if args.mirror:c['download']['base_url']=args.mirror
        if args.mode:c['judge']['mode']=args.mode
        if args.concurrency:c['judge']['concurrency']=args.concurrency
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():write_new(path.with_name(path.name+'.backup-'+str(time.time_ns())),path.read_bytes())
        temp=path.with_name('.'+path.name+'-'+str(time.time_ns()));write_new(temp,encode(c));config(temp);os.replace(temp,path)
        print('[ocr-qa] CONFIGURED '+str(path));return
    if args.subset and args.command not in ('probe','network-diagnose','download-bench','download-fast','download','assemble','register','api-check'):
        c['sources']=[s for s in c['sources'] if s['subset']==args.subset]
        if not c['sources']:raise ValueError('unknown subset')
    print('[ocr-qa] SCOPE '+json.dumps({'command':args.command,'source':'nine allowlisted UniRec40M subsets','raw_root':c['raw_root'],'work_root':c['work_root'],'personal_proxy':False}),flush=True)
    if args.command in ('download','download-fast','assemble','mechanical','draft','pilot','run','register'):
        dirty=subprocess.check_output(['git','status','--porcelain'],cwd=PROJECT,timeout=10)
        if dirty.strip():raise ValueError('formal operations require a clean reviewed checkout; existing work was not changed')
    with RunLock(c['work_root']):
        if args.command=='network-diagnose':
            from network_diagnose import diagnose
            result=diagnose(c)
            report=Path(c['work_root'])/'00_download'/f'network-diagnose-{time.time_ns()}.json'
            write_new(report,encode(result));print('[ocr-qa] NETWORK_DIAGNOSIS '+json.dumps(result),flush=True);print('[ocr-qa] REPORT '+str(report));return
        if args.command in ('probe','download-bench','download-fast','download','assemble'):
            from download import probe,benchmark,download,assemble
            if args.command=='probe':result=probe(c)
            elif args.command=='download-bench':result=benchmark(c)
            elif args.command=='assemble':result=assemble(c)
            else:
                # Never download a guessed ModelScope repository or silently switch providers.
                if args.command=='download-fast':
                    observations=benchmark(c);print('[ocr-qa] DOWNLOAD_BENCH '+json.dumps(observations),flush=True)
                    ok=[r for r in observations['results'] if 'mib_per_second' in r]
                    if not ok:raise ValueError('no configured origin passed bounded Range benchmark; no full download attempted')
                    c['download']['base_url']=max(ok,key=lambda r:r['mib_per_second'])['origin']
                result=download(c,args.subset)
            report=Path(c['work_root'])/'00_download'/f'{args.command}-{time.time_ns()}.json'
            write_new(report,encode(result));print('[ocr-qa] RESULT '+json.dumps({'report':str(report),'result':result},ensure_ascii=False),flush=True);return
        if args.command=='api-check':
            from qa import api_check
            print('[ocr-qa] API_CHECK '+json.dumps(api_check(c)));return
        if args.command=='register':
            from delivery import register
            if args.delivery is None:raise ValueError('--delivery must name a completed04_delivery run')
            root=(Path(c['work_root'])/'04_delivery').resolve()
            if root not in args.delivery.resolve().parents:raise ValueError('delivery outside configured04_delivery')
            receipt=json.loads((args.delivery/'receipt.json').read_text())
            if receipt['binding']['config']!=c:raise ValueError('delivery config differs')
            print('[ocr-qa] REGISTERED '+json.dumps(register(c,args.delivery)));return
        from mechanical import bucket_rows,mechanical
        if args.command=='inspect':
            from common import under
            result=[]
            for source in c['sources']:
                it=bucket_rows(under(c['raw_root'],source['label']))
                samples=[]
                for _,row in zip(range(3),it):
                    bucket,value=row;samples.append({'bucket':bucket,'keys':list(value),'label_type':type(value.get('label')).__name__,'key_prefix_ok':str(value.get('file_name','')).startswith(source['prefix'])})
                result.append({'source':source['label'],'sample_structure':samples})
            print('[ocr-qa] INSPECT '+json.dumps(result));return
        limit=args.limit
        if args.command=='pilot' and limit is None:limit=100
        if limit is not None and limit<=0:raise ValueError('limit must be positive')
        first=mechanical(c,limit)
        if args.command=='mechanical':print('[ocr-qa] MECHANICAL_PASS '+str(first));return
        from qa import build_drafts,score
        drafts=build_drafts(c,first)
        if args.command=='draft':print('[ocr-qa] DRAFT_PASS '+str(drafts));return
        quality=score(c,drafts,args.retry_errors)
        from delivery import deliver
        final=deliver(c,quality)
        print('[ocr-qa] DELIVERY_PASS '+json.dumps({'delivery':str(final),'summary':json.loads((final/'summary.json').read_text('utf8'))}),flush=True)


if __name__=='__main__':
    try:main();print('[ocr-qa] PASS requested command',flush=True)
    except Exception as e:
        print('[ocr-qa] FAIL '+json.dumps({'error_type':type(e).__name__,'message':str(e)[:1000],'original_writes':0,'completed_stages_retained':True}),file=sys.stderr,flush=True);sys.exit(1)
