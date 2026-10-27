"""Post-acceptance exact70/30 selection, MCQ label rotation, immutable publication."""
from collections import Counter
from datetime import date
import json
import os
from pathlib import Path
import sqlite3

from common import Stage, code_sha, digest, encode, identity, records, sha, under, write_new
from qa import render_question


def allocate(capacities,target):
    if target>sum(capacities.values()):raise ValueError('insufficient candidate capacity')
    out={k:0 for k in capacities};remaining=target
    while remaining:
        active=[k for k in sorted(capacities) if out[k]<capacities[k]]
        step=max(1,remaining//len(active))
        for k in active:
            take=min(step,capacities[k]-out[k],remaining);out[k]+=take;remaining-=take
    return out


def final_row(row,c,mcq_index):
    out=dict(row['original'])
    # Preserve all native fields at top level; collisions receive explicit original_ aliases.
    for key in ('id','conversations','images','videos','audios','modal_mask','source_dataset','source_subset','source_annotation','source_index'):
        if key in out:out['original_'+key]=out.pop(key)
    view=dict(row)
    if row['qa_type']=='mcq':
        slot=mcq_index%4;opts=list(row['options']);truth=opts.pop(row['correct_index']);opts.insert(slot,truth)
        view.update(options=opts,correct_index=slot,answer=chr(65+slot)+'. '+truth)
    out.update(id=c['name']+'_'+row['id'],conversations=[{'from':'human','value':'<image>\n'+render_question(view)},{'from':'gpt','value':view['answer']}],
               images=[row['image']],videos=[],audios=[],modal_mask=1,
               source_dataset=row['source_dataset'],source_subset=row['source_subset'],
               source_annotation=row['source_annotation'],source_index=row['source_index'])
    return out,view


def readme(c,stats,fields):
    text='# '+c['name']+'\n\n完成日期：'+date.today().isoformat()+'｜维护者：Tiachi\n\n## 一、数据集介绍\n\n'
    text+='来自UniRec40M九个中文候选子库，仅构造图像文字转写及转写辨别QA，不生成试题解答。\n\n|指标|数量|\n|---|---:|\n'
    for key,value in [('样本/QA',stats['qa_pairs']),('图像引用',stats['qa_pairs']),('独立图像',stats['unique_images']),('modal_mask=1',stats['qa_pairs'])]:text+=f'|{key}|{value}|\n'
    text+='\n|题型|QA|\n|---|---:|\n'
    for key,value in stats['formats'].items():text+=f'|{key}|{value}|\n'
    text+='\n|来源子库|QA|\n|---|---:|\n'
    for key,value in stats['subsets'].items():text+=f'|{key}|{value}|\n'
    text+='\n## 二、原始字段说明\n\n|字段|类型|含义/示例|\n|---|---|---|\n'
    notes={'file_name':'原始LMDB精确键，如k12_2.jpg；不是交付媒体路径','label':'原始转写，保留未经改写的标注','bbox':'源区域坐标，若存在则原样保留；未再次裁图'}
    for k,types in sorted(fields.items()):text+=f'|{k}|{", ".join(sorted(types))}|{notes.get(k,"源自原标注，未改写；需结合source_annotation回溯")}|\n'
    text+='|source_dataset/source_subset|字符串|上游数据集及九个子库名|\n|source_annotation/source_index|字符串/整数|原标注相对路径与桶展平序号|\n'
    text+='\n## 三、处理说明\n\n原LMDB只读，按作者的file_name精确取图，导出字节相同的原始图像；不缩放、不裁剪、不增强。已检查解码/尺寸、空标注、控制符、已知换行标记、可选模糊代理；原图像重复与标签冲突分开处理。无语义纠错，无自动补CoT。\n\n'
    text+='按清洗后有效QA精确70%OE/30%MCQ，A/B/C/D各25%，每张图最多选一条。分来源限额水位分配；标签原文不用于单独去重。\n\n'
    text+='质量范围：'+stats['judge_scope']+'；模型评分是代理判断，不是人工图文金标验收。没有配置holdout时不声称去污染；未知原页关系不声称原页级去重。当前只导出训练集，不自动创建可能泄漏的随机验证集。\n\n'
    text+='## 四、路径对应\n\n|用途|路径|\n|---|---|\n'
    for k,v in [('源文件',c['raw_root']),('训练JSONL',c['delivery_json']),('README',c['delivery_readme']),('图片相对路径基准',c['training_root']),('中间产物/统计',c['work_root']),('旁路属性','04_delivery/<run>/attributes.jsonl')]:text+=f'|{k}|`{v}`|\n'
    text+='\n示例：`images/'+c['name']+'/ab/<sha256>.jpg` 对应 `'+c['training_root']+'/images/'+c['name']+'/ab/<sha256>.jpg`。\n'
    return text


def deliver(c,quality):
    stage=Stage(c['work_root'],'04_delivery',{'config':c,'parent':identity(quality/'receipt.json'),'code_sha':code_sha()})
    if stage.reused:return stage.final
    db=sqlite3.connect(stage.path/'selection.sqlite3')
    db.execute('CREATE TABLE pool(subset TEXT,mode TEXT,sortkey TEXT PRIMARY KEY,raw TEXT)')
    caps=Counter()
    for row in records(quality/'accepted.jsonl'):
        key=digest([c['seed'],row['id']]);db.execute('INSERT INTO pool VALUES(?,?,?,?)',(row['source_subset'],row['qa_type'],key,json.dumps(row,ensure_ascii=False)))
        caps[row['source_subset'],row['qa_type']]+=1
    db.execute('CREATE INDEX by_group ON pool(subset,mode,sortkey)');db.commit()
    total_oe=sum(v for (s,m),v in caps.items() if m=='oe');total_mcq=sum(v for (s,m),v in caps.items() if m=='mcq')
    target=c['mix']['target_qa']
    if target is None:target=(min(total_oe*10//7,total_mcq*10//3)//40)*40
    if target<=0 or target%40:raise ValueError('exact70/30 plus four balanced MCQ labels requires target_qa positive multiple of40')
    quotas={}
    for mode,number in [('oe',target*7//10),('mcq',target*3//10)]:
        quotas.update({(s,mode):n for s,n in allocate({s:v for (s,m),v in caps.items() if m==mode},number).items()})
    all_subsets={s['subset'] for s in c['sources']}
    missing=[s for s in sorted(all_subsets) if sum(v for (ss,m),v in quotas.items() if ss==s)<c['mix']['per_subset_min']]
    if missing:raise ValueError('required subset capacity missing: '+str(missing))
    counts=Counter();subsets=Counter();labels=Counter();fields={};seen_images=set();mcq_index=0
    with (stage.path/(c['name']+'.jsonl')).open('xb') as out,(stage.path/'attributes.jsonl').open('xb') as attrs:
        for (subset,mode),number in sorted(quotas.items()):
            for raw, in db.execute('SELECT raw FROM pool WHERE subset=? AND mode=? ORDER BY sortkey LIMIT ?',(subset,mode,number)):
                row=json.loads(raw);final,view=final_row(row,c,mcq_index)
                if mode=='mcq':mcq_index+=1;labels[view['answer'][0]]+=1
                for key,value in row['original'].items():fields.setdefault(key,set()).add(type(value).__name__)
                path=under(c['training_root'],row['image'])
                if not path.is_file():raise ValueError('delivery media missing')
                out.write(encode(final));attrs.write(encode({'id':final['id'],'qa_type':mode,'ocr_kind':row['kind'],'quality':row['judge']['quality'],'judge_scope':c['judge']['mode'],'image_sha256':row['image_sha256'],'pixel_sha256':row['media']['pixel_sha256']}))
                counts[mode]+=1;subsets[subset]+=1;seen_images.add(row['image_sha256'])
    db.close()
    if counts!=Counter(oe=target*7//10,mcq=target*3//10) or set(labels)!=set('ABCD') or len(set(labels.values()))!=1:raise ValueError('post-export ratio validation failed')
    if len(seen_images)!=target:raise ValueError('duplicate image in final selection')
    stats={'qa_pairs':target,'rows':target,'unique_images':len(seen_images),'formats':dict(counts),'subsets':dict(subsets),
           'mcq_letters':dict(labels),'judge_scope':c['judge']['mode'],'strict_data_format_verified':False,
           'status':'MODEL_VISION_REVIEWED_NOT_GOLD' if c['judge']['mode']=='vision' else 'TEXT_PROXY_ONLY_NOT_VISUAL_VERIFIED',
           'selection_capacity':{'oe':total_oe,'mcq':total_mcq},'accuracy_certified':False}
    write_new(stage.path/'summary.json',encode(stats));write_new(stage.path/'README.md',readme(c,stats,fields).encode('utf8'))
    write_new(stage.path/'stats.md',('# OCR QA统计\n\n```json\n'+json.dumps(stats,ensure_ascii=False,indent=2)+'\n```\n').encode('utf8'))
    return stage.commit(stats)


def register(c,delivery):
    """No-clobber hardlinks. A failed second link is safely resumable, never copied over."""
    destinations={Path(c['delivery_json']):delivery/(c['name']+'.jsonl'),Path(c['delivery_readme']):delivery/'README.md'}
    for dest,source in destinations.items():
        dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():
            if not os.path.samefile(dest,source):raise ValueError('published path already belongs to another delivery: '+str(dest))
        else:os.link(source,dest)
    return {'jsonl':c['delivery_json'],'readme':c['delivery_readme'],'delivery':str(delivery),'attributes':str(delivery/'attributes.jsonl'),'stats':str(delivery/'summary.json')}
