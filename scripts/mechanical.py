"""Stream official size buckets; exact LMDB keys, no guessed basename mapping."""
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import subprocess

from common import Stage, code_sha, digest, encode, identity, safe_rel, under, write_new


def bucket_rows(path):
    import ijson
    from ijson.common import ObjectBuilder
    builder=None;depth=0;bucket=None
    with Path(path).open('rb') as f:
        for prefix,event,value in ijson.parse(f,use_float=True):
            if prefix=='' and event=='map_key':bucket=value
            if builder is None:
                if prefix==str(bucket)+'.item' and event=='start_map':
                    builder=ObjectBuilder();depth=1;builder.event(event,value)
            else:
                builder.event(event,value)
                if event in ('start_map','start_array'):depth+=1
                elif event in ('end_map','end_array'):depth-=1
                if depth==0:
                    yield bucket,builder.value;builder=None


TOKEN_RE=re.compile(r'[一-鿿]|[A-Za-z0-9_]+|[^\s]')


def datatrove_repetition(text,rules):
    """Datatrove SFT mechanical rule: 8-gram repetition at >=128 tokens and >=0.6."""
    if not isinstance(text,str):return {'tokens':0,'ratio':0.0,'flagged':False}
    tokens=TOKEN_RE.findall(text[:200000])
    n=int(rules.get('text_ngram_n',8));minimum=int(rules.get('text_min_tokens',128))
    threshold=float(rules.get('text_repetition_threshold',0.6))
    if len(tokens)<max(n,minimum):return {'tokens':len(tokens),'ratio':0.0,'flagged':False}
    grams=[tuple(tokens[i:i+n]) for i in range(len(tokens)-n+1)]
    ratio=1-len(set(grams))/len(grams)
    return {'tokens':len(tokens),'ratio':round(ratio,6),'flagged':ratio>=threshold}


def ffmpeg_blur(path,width,height,rules):
    """image-video-cleaner FFmpeg blurdetect; adaptive block for tiny OCR crops."""
    threshold=rules.get('ffmpeg_blur_review_above')
    if threshold is None:return None
    binary=rules.get('ffmpeg_bin','/mnt/sfs/ltj/runtime/ffmpeg-blur/linuxarm64/bin/ffmpeg')
    timeout=int(rules.get('ffmpeg_blur_timeout',20))
    side=min(int(width),int(height))
    block=32 if side>=64 else (16 if side>=32 else (8 if side>=16 else 4))
    vf=(f'blurdetect=low=0.078431372549:high=0.196078431373:radius=50:'
        f'block_width={block}:block_height={block}:block_pct=100:planes=1,'
        'metadata=mode=print:key=lavfi.blur:file=-')
    command=[binary,'-hide_banner','-loglevel','error','-nostdin','-threads','1','-filter_threads','1',
             '-protocol_whitelist','file','-i',str(path),'-map','0:v:0','-an','-sn','-dn',
             '-frames:v','1','-vf',vf,'-f','null','-']
    try:
        result=subprocess.run(command,capture_output=True,text=True,timeout=timeout)
        match=re.search(r'^lavfi\.blur=([^\r\n]+)',result.stdout,re.M)
        score=float(match.group(1)) if match else None
        return {'score':score,'threshold':float(threshold),'block':block,
                'error':None if score is not None else (result.stderr[-200:] if result.returncode else 'no_score')}
    except Exception as e:
        return {'score':None,'threshold':float(threshold),'block':block,
                'error':type(e).__name__+': '+str(e)[:160]}


def normalize_label(value,rules):
    if not isinstance(value,str):return None,['non_string_label']
    # No NFKC, spelling/grammar repair, punctuation simplification, or LaTeX edits.
    text=value.replace('\r\n','\n').replace('\r','\n')
    for marker,replacement in rules['marker_map'].items():text=text.replace(marker,replacement)
    issues=[]
    if not text.strip():issues.append('empty_label')
    if len(text)>rules['label_max_chars']:issues.append('long_label')
    if re.search(r'<<<|<\||\|>|[\ufffd\ufffe\uffff]|[\x00-\x08\x0b\x0c\x0e-\x1f]',text):issues.append('unresolved_marker_or_control')
    if rules['require_han'] and not re.search(r'[\u3400-\u9fff\U00020000-\U0002fa1f]',text):issues.append('no_han')
    # Repeated textbook/formula content is valid OCR: flag for review, never rewrite.
    if re.search(r'(.{3,30})\1{5,}',text,flags=re.DOTALL):issues.append('ngram_loop_review')
    return text,issues


def source_files(c):
    values=[]
    for s in c['sources']:
        db=under(c['raw_root'],s['lmdb'])/'data.mdb'
        if s['subset']=='HWDB2Train':db=Path(c['work_root'])/'assembled/HWDB2Train/image_lmdb/data.mdb'
        values.extend([identity(under(c['raw_root'],s['label'])),identity(db)])
    if c['mechanical']['holdout_sha256_file']:values.append(identity(c['mechanical']['holdout_sha256_file']))
    return values


def envelope(source,bucket,index,row):
    return {'id':digest([source['label'],bucket,index,row])[:32], 'source_dataset':'topdu/UniRec40M',
            'source_subset':source['subset'],'source_annotation':source['label'],'source_bucket':bucket,
            'source_index':index,'kind':source['kind'],'original':row}


def inspect_media(blob,rules):
    from PIL import Image, ImageFilter, ImageStat
    Image.MAX_IMAGE_PIXELS=rules['max_pixels']
    with Image.open(io.BytesIO(blob)) as image:
        if image.width*image.height>rules['max_pixels']:raise ValueError('image pixel budget exceeded')
        image.load()
        if min(image.size)<rules['min_side']:raise ValueError('image side too small')
        rgb=image.convert('RGB');pixel_sha=hashlib.sha256(encode(rgb.size)+rgb.tobytes()).hexdigest()
        # Optional review statistic only; no arbitrary universal blur cutoff.
        edge_variance=None
        if rules['blur_review_below'] is not None:
            edge_variance=ImageStat.Stat(rgb.convert('L').filter(ImageFilter.FIND_EDGES)).var[0]
        return {'width':image.width,'height':image.height,'format':image.format,'pixel_sha256':pixel_sha,'edge_variance':edge_variance}


def mechanical(c,limit=None):
    import lmdb
    relevant={k:c[k] for k in ('name','raw_root','work_root','training_root','mechanical','sources')}
    binding={'config':relevant,'inputs':source_files(c),'limit_per_source':limit,'code_sha':code_sha()}
    stage=Stage(c['work_root'],'01_mechanical',binding)
    if stage.reused:return stage.final
    db=sqlite3.connect(stage.path/'index.sqlite3')
    db.execute('CREATE TABLE rows(id TEXT PRIMARY KEY,pixel TEXT,label TEXT,state TEXT,row TEXT)')
    db.execute('CREATE INDEX by_pixel ON rows(pixel)')
    holdout=set()
    if c['mechanical']['holdout_sha256_file']:
        holdout={line.strip() for line in Path(c['mechanical']['holdout_sha256_file']).read_text().splitlines() if line.strip()}
    handles={};envs={};counts=Counter();reasons=Counter()
    try:
        for s in c['sources']:
            lmdb_path=under(c['raw_root'],s['lmdb'])
            if s['subset']=='HWDB2Train':lmdb_path=Path(c['work_root'])/'assembled/HWDB2Train/image_lmdb'
            if str(lmdb_path) not in handles:
                env=lmdb.open(str(lmdb_path),readonly=True,create=False,lock=False,readahead=False,meminit=False,max_readers=32)
                envs[str(lmdb_path)]=env;handles[str(lmdb_path)]=env.begin()
            txn=handles[str(lmdb_path)]
            for index,(bucket,row) in enumerate(bucket_rows(under(c['raw_root'],s['label']))):
                if limit is not None and index>=limit:break
                out=envelope(s,bucket,index,row);out['issues']=[];out['state']='candidate';pixel=None;label=None
                try:
                    label,issues=normalize_label(row.get('label'),c['mechanical'])
                    repetition=datatrove_repetition(label,c['mechanical'])
                    out['text_repetition']=repetition
                    if repetition['flagged']:issues.append('possible_repetition')
                    out['issues'].extend(issues)
                    out['label']=label
                    if issues:
                        out['state']='rejected' if any(i in issues for i in ('empty_label','no_han')) else 'review'
                    key=row.get('file_name')
                    if not isinstance(key,str) or not key.startswith(s['prefix']):raise ValueError('unresolved_source_key')
                    blob=txn.get(key.encode('utf8'))
                    if blob is None:raise ValueError('missing_lmdb_key')
                    info=inspect_media(blob,c['mechanical']);out['media']=info;pixel=info['pixel_sha256']
                    byte_sha=hashlib.sha256(blob).hexdigest();out['image_sha256']=byte_sha
                    ext={'JPEG':'.jpg','PNG':'.png','WEBP':'.webp','BMP':'.bmp','TIFF':'.tif'}.get(info['format'])
                    if ext is None:raise ValueError('unsupported_image_format')
                    rel='images/'+safe_rel(c['name'])+'/'+byte_sha[:2]+'/'+byte_sha+ext
                    image_path=under(c['training_root'],rel)
                    if image_path.exists():
                        if image_path.stat().st_size!=len(blob):raise ValueError('existing_media_size_conflict')
                    else:write_new(image_path,blob)
                    out['image']=rel
                    if pixel in holdout or byte_sha in holdout:out['state']='rejected';out['issues'].append('explicit_holdout_image')
                    threshold=c['mechanical']['blur_review_below']
                    if threshold is not None and info['edge_variance']<threshold:
                        if out['state']=='candidate':out['state']='review'
                        out['issues'].append('blur_proxy_review')
                    previous=db.execute('SELECT label,state FROM rows WHERE pixel=?',(pixel,)).fetchall()
                    if previous:
                        if any(p[0]!=label for p in previous):
                            db.execute("UPDATE rows SET state='review' WHERE pixel=? AND state IN ('candidate','duplicate')",(pixel,))
                            out['state']='review';out['issues'].append('same_pixels_conflicting_labels')
                        elif any(p[1]=='candidate' for p in previous):out['state']='duplicate';out['issues'].append('same_pixels_same_label')
                    if out['state']!='rejected':
                        blur=ffmpeg_blur(image_path,info['width'],info['height'],c['mechanical'])
                        if blur is not None:
                            out['blur']=blur
                            if blur.get('score') is None:
                                out['issues'].append('clarity_probe_failed')
                                if out['state'] in ('candidate','duplicate'):out['state']='review'
                            elif blur['score']>blur['threshold']:
                                out['issues'].append('blur_review')
                                if out['state'] in ('candidate','duplicate'):out['state']='review'
                except Exception as e:
                    # Structural issues remain visible; never randomly substitute another sample.
                    out['state']='review';out['issues'].append(str(e)[:160])
                for issue in out['issues']:reasons[issue]+=1
                db.execute('INSERT INTO rows VALUES(?,?,?,?,?)',(out['id'],pixel,label,out['state'],json.dumps(out,ensure_ascii=False)))
                if index%10000==0:db.commit();print('[ocr-qa] MECHANICAL '+json.dumps({'subset':s['subset'],'rows':index+1}),flush=True)
        db.commit()
        with (stage.path/'all.jsonl').open('xb') as all_out:
            outputs={state:(stage.path/(state+'.jsonl')).open('xb') for state in ('candidate','review','rejected','duplicate')}
            try:
                for state,raw in db.execute('SELECT state,row FROM rows ORDER BY rowid'):
                    out=json.loads(raw)
                    if out['state']!=state:out['issues'].append('same_pixels_conflicting_labels');out['state']=state
                    data=encode(out);outputs[state].write(data);all_out.write(data)
                    counts[state]+=1;counts[out['source_subset']+'|'+state]+=1
            finally:
                for f in outputs.values():f.close()
    finally:
        db.close()
        for txn in handles.values():txn.abort()
        for env in envs.values():env.close()
    stats={'counts':dict(counts),'reasons':dict(reasons),'media_operation':'byte-identical LMDB image extraction; no resize/crop/transcode',
           'holdout_protection':'explicit image hashes only' if holdout else 'not_configured',
           'sampling':'per-label-file prefix' if limit else 'full'}
    write_new(stage.path/'stats.json',encode(stats));return stage.commit(stats)
