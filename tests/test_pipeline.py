import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import random
import socket
import ssl
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'scripts'))
from common import Stage,config,digest,encode,records,safe_rel,under,ipv4_connect,IPv4HTTPSConnection,HostTraceRedirect
from download import download_one,file_url,verify,range_bytes,network_error
from mechanical import bucket_rows,datatrove_repetition,mechanical,normalize_label
from qa import api_check,build_drafts,choose_question,distractors,draft,judge_one,parse_verdict,score
from delivery import allocate,deliver,final_row,register
from service import service_command


class Handler(BaseHTTPRequestHandler):
    calls=0
    def log_message(self,*args):pass
    def do_GET(self):
        raw=encode({'data':[{'id':'test-qwen'}]});self.send_response(200);self.end_headers();self.wfile.write(raw)
    def do_POST(self):
        Handler.calls+=1;payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert payload['model']=='test-qwen'
        assert payload['chat_template_kwargs']=={'enable_thinking':False}
        raw=encode({'choices':[{'message':{'content':'9,1,1'}}],'usage':{'completion_tokens':5}})
        self.send_response(200);self.end_headers();self.wfile.write(raw)


class CoreTests(unittest.TestCase):
    def test_ocr_not_semantically_rewritten(self):
        c=config(PROJECT/'config/pipeline.json')
        text='錯别字，ＡＢ１２，x^2。<<<change_line_token_wrap>>>下一行'
        actual,issues=normalize_label(text,c['mechanical'])
        self.assertEqual(actual,'錯别字，ＡＢ１２，x^2。\n下一行');self.assertEqual(issues,[])
    def test_unknown_marker_review(self):
        c=config(PROJECT/'config/pipeline.json');self.assertIn('unresolved_marker_or_control',normalize_label('中文<<<null>>>',c['mechanical'])[1])
    def test_empty_and_non_chinese(self):
        c=config(PROJECT/'config/pipeline.json')
        self.assertIn('empty_label',normalize_label(' ',c['mechanical'])[1]);self.assertIn('no_han',normalize_label('ABC123',c['mechanical'])[1])
    def test_list_label_is_not_stringified(self):
        c=config(PROJECT/'config/pipeline.json');self.assertEqual(normalize_label(['中文'],c['mechanical']),(None,['non_string_label']))
    def test_ngram_review(self):
        c=config(PROJECT/'config/pipeline.json');self.assertIn('ngram_loop_review',normalize_label('中文文字'*7,c['mechanical'])[1])
    def test_datatrove_repetition_rule(self):
        c=config(PROJECT/'config/pipeline.json')
        self.assertFalse(datatrove_repetition('中文文字'*7,c['mechanical'])['flagged'])
        repeated='中文'*100
        result=datatrove_repetition(repeated,c['mechanical'])
        self.assertGreaterEqual(result['tokens'],128);self.assertTrue(result['flagged'])
    def test_question_templates_are_diverse_and_grounded(self):
        c=config(PROJECT/'config/pipeline.json')
        rows=[{'image_sha256':str(i),'id':str(i),'kind':'handwriting_line','label':'中文文字'} for i in range(40)]
        questions={choose_question('oe','handwriting',r,c['seed'])[0] for r in rows}
        self.assertGreater(len(questions),5)
        out=draft(rows[0],c)
        self.assertEqual(out['answer'],'中文文字')
        self.assertIn(out['question'],questions)
    def test_paths(self):
        for value in ['/etc/passwd','../x','a/../b','a\\b','C:/x','a//b','a/./b']:
            with self.assertRaises(ValueError):safe_rel(value)
    def test_distractors(self):
        text='今日天明，未入本土，王先生买书。'
        ds=distractors(text,1);self.assertEqual(len(ds),3);self.assertEqual(len(set(ds+[text])),4)
        self.assertTrue(all(len(x)==len(text) for x in ds));self.assertEqual(ds,distractors(text,1))
    def test_long_mcq_not_forced(self):self.assertEqual(distractors('中文'*200,1),[])
    def test_verdict(self):
        self.assertEqual(parse_verdict('10,1,2')['quality'],10)
        for raw in ['```9,1,1```','9,1,1 because','0,1,1','9,3,1','9,1']:
            with self.assertRaises(ValueError):parse_verdict(raw)
    def test_allocate(self):
        self.assertEqual(allocate({'a':2,'b':100,'c':100},100),{'a':2,'b':49,'c':49})
        with self.assertRaises(ValueError):allocate({'a':3},4)
    def test_stage_no_clobber_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Stage(tmp,'x',{'seed':1});(a.path/'data').write_bytes(b'xx');p=a.commit({'ok':1})
            self.assertEqual(Stage(tmp,'x',{'seed':1}).path,p)
            self.assertNotEqual(Stage(tmp,'x',{'seed':2}).path,p)
            (p/'data').write_bytes(b'x')
            with self.assertRaises(ValueError):Stage(tmp,'x',{'seed':1})
    def test_full_source_manifest_is_allowlisted(self):
        d=json.loads((PROJECT/'research/source_files.json').read_text())
        self.assertEqual(len({x['path'].split('/')[0] for x in d['files']}),9)
        self.assertTrue(all(x.get('sha256') or x.get('git_blob_sha1') for x in d['files']))
    def test_mirror_must_be_https_origin(self):
        c=config(PROJECT/'config/pipeline.json')
        for base in ['http://example.com','https://a/b','https://user:pass@a']:
            with self.assertRaises(ValueError):file_url(c,{'path':'K-12/x'},base)
    def test_hash_not_just_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'file';p.write_bytes(b'ab')
            with self.assertRaises(ValueError):verify(p,{'path':'x','bytes':2,'sha256':hashlib.sha256(b'cd').hexdigest()})
    def test_network_failure_details_without_signed_urls(self):
        detail=network_error(urllib.error.URLError(socket.gaierror(-2,'lookup failed')))
        self.assertEqual(detail['category'],'dns');self.assertEqual(detail['errno'],-2)
        detail=network_error(urllib.error.URLError(ConnectionRefusedError(111,'refused')))
        self.assertEqual(detail['category'],'connection_refused')
        detail=network_error(urllib.error.HTTPError('https://example/a?secret=redacted',403,'Forbidden',{},None))
        self.assertEqual(detail['http_status'],403);self.assertNotIn('secret',json.dumps(detail))
    def test_ipv4_connection_is_local_to_one_connection(self):
        original=socket.getaddrinfo
        with patch('common.socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('192.0.2.1',443))]) as resolve,patch('common.socket.socket') as sock:
            result=ipv4_connect(('example.test',443),3)
            self.assertIs(result,sock.return_value)
            resolve.assert_called_once_with('example.test',443,socket.AF_INET,socket.SOCK_STREAM)
            sock.return_value.connect.assert_called_once_with(('192.0.2.1',443))
        self.assertIs(socket.getaddrinfo,original)
        conn=IPv4HTTPSConnection('example.test')
        self.assertEqual(conn._context.verify_mode,ssl.CERT_REQUIRED);self.assertTrue(conn._context.check_hostname)
        self.assertIs(conn._create_connection,ipv4_connect)
    def test_redirect_trace_has_hosts_only_and_refuses_downgrade(self):
        trace=[];handler=HostTraceRedirect(trace);request=urllib.request.Request('https://origin.test/file')
        handler.redirect_request(request,None,302,'Found',{},'https://cdn.test/file?secret=token')
        self.assertEqual(trace,[{'status':302,'host':'cdn.test','scheme':'https'}]);self.assertNotIn('token',json.dumps(trace))
        with self.assertRaises(ValueError):handler.redirect_request(request,None,302,'Found',{},'http://cdn.test/file')
    def test_network_diagnose_reports_dns_without_raw_credentials(self):
        from network_diagnose import diagnose_origin
        with patch('network_diagnose.socket.getaddrinfo',side_effect=socket.gaierror(-2,'lookup failed')):
            result=diagnose_origin('https://example.test')
        self.assertEqual(result['dns_error']['category'],'dns')
        with self.assertRaises(ValueError):diagnose_origin('https://user:secret@example.test')
    def test_service_vision_and_text_are_separate(self):
        c=json.loads((PROJECT/'config/service.json').read_text())
        vision=service_command(c);self.assertNotIn('--language-model-only',vision);self.assertEqual(json.loads(vision[vision.index('--limit-mm-per-prompt')+1])['image'],1)
        c['vision']=False;self.assertIn('--language-model-only',service_command(c))
    def test_segment_resume_and_exact_range(self):
        c=config(PROJECT/'config/pipeline.json');c['download']['retries']=1
        class Response(io.BytesIO):
            status=206
            headers={'Content-Range':'bytes 2-5/10'}
            def geturl(self):return 'https://cdn.test/file'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'segment'
            with patch('download.direct_open',return_value=Response(b'cdef')) as request:
                range_bytes(c,'https://test/file',2,5,p);range_bytes(c,'https://test/file',2,5,p)
                self.assertEqual(request.call_count,1);self.assertEqual(p.read_bytes(),b'cdef')
            p2=Path(tmp)/'bad'
            response=Response(b'abcd');response.headers={'Content-Range':'bytes 0-3/10'}
            with patch('download.direct_open',return_value=response),self.assertRaises(ValueError):range_bytes(c,'https://test/file',2,5,p2)
            self.assertFalse(p2.exists())
    def test_download_reuses_only_verified_existing(self):
        c=config(PROJECT/'config/pipeline.json')
        with tempfile.TemporaryDirectory() as tmp:
            c['raw_root']=tmp;c['work_root']=str(Path(tmp)/'work')
            p=Path(tmp)/'K-12/x';p.parent.mkdir();p.write_bytes(b'ab')
            f={'path':'K-12/x','bytes':2,'sha256':hashlib.sha256(b'ab').hexdigest()}
            self.assertEqual(download_one(c,f)['status'],'verified_existing')
            p.write_bytes(b'cd')
            with self.assertRaises(ValueError):download_one(c,f)
    def test_mcq_rotation_preserves_truth(self):
        c=config(PROJECT/'config/pipeline.json')
        row={'original':{'file_name':'abc','label':'中文'},'id':'x','source_dataset':'test','source_subset':'s','source_annotation':'label','source_index':1,'image':'images/x.jpg','qa_type':'mcq','question':'选一项','answer':'A','options':['中文','中又','中丈','中义'],'correct_index':0}
        for i in range(4):
            final,v=final_row(row,c,i);self.assertEqual(v['options'][i],'中文');self.assertTrue(final['conversations'][1]['value'].startswith(chr(65+i)+'. 中文'))
            self.assertEqual(final['file_name'],'abc');self.assertEqual(final['images'],['images/x.jpg'])


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import lmdb,ijson
        from datatrove.data import Document
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.c=config(PROJECT/'config/pipeline.json')
        self.c.update(raw_root=str(root/'raw'),work_root=str(root/'work'),training_root=str(root/'training'),delivery_json=str(root/'publish/qa.jsonl'),delivery_readme=str(root/'publish/readme.md'))
        self.c['judge'].update(base_url='http://127.0.0.1:'+str(self.server.server_port)+'/v1',model='test-qwen',mode='text',concurrency=8)
        self.c['mix']['target_qa']=40
    def tearDown(self):self.tmp.cleanup()
    def fixture(self,n=20):
        import lmdb
        from PIL import Image
        rng=random.Random(123);groups={}
        for source in self.c['sources']:
            path=Path(self.c['raw_root'])/source['lmdb']
            if source['subset']=='HWDB2Train':path=Path(self.c['work_root'])/'assembled/HWDB2Train/image_lmdb'
            groups.setdefault(str(path),[]).append(source)
        for path,sources in groups.items():
            Path(path).mkdir(parents=True);env=lmdb.open(path,map_size=16*1024**2)
            with env.begin(write=True) as txn:
                for source_index,source in enumerate(sources):
                    rows=[]
                    for i in range(n):
                        key=source['prefix']+str(source_index)+'_'+str(i)+'.png'
                        im=Image.frombytes('RGB',(16,16),rng.randbytes(16*16*3));buf=io.BytesIO();im.save(buf,format='PNG')
                        txn.put(key.encode(),buf.getvalue());rows.append({'file_name':key,'label':'今日天明，未入本土，王先生买书。'+str(i),'native_field':'preserved'})
                    label=Path(self.c['raw_root'])/source['label'];label.parent.mkdir(parents=True,exist_ok=True);label.write_bytes(encode({'16_16':rows}))
            env.close()
    def test_stream_size_buckets(self):
        p=Path(self.tmp.name)/'bucket.json';p.write_bytes(encode({'64_64':[{'file_name':'a','label':'中文'}],'128_64':[{'file_name':'b','label':['中','文']}]}))
        rows=list(bucket_rows(p));self.assertEqual(len(rows),2);self.assertEqual(dict(rows)['128_64']['label'],['中','文'])
    def test_end_to_end_exact_mix_and_resume(self):
        self.fixture();first=mechanical(self.c);drafts=build_drafts(self.c,first)
        before=Handler.calls;quality=score(self.c,drafts);used=Handler.calls-before
        final=deliver(self.c,quality);summary=json.loads((final/'summary.json').read_text())
        self.assertEqual(summary['rows'],40);self.assertEqual(summary['formats'],{'oe':28,'mcq':12});self.assertEqual(summary['mcq_letters'],dict.fromkeys('ABCD',3))
        self.assertEqual(len(summary['subsets']),9);self.assertGreater(used,0)
        self.assertEqual(mechanical(self.c),first);self.assertEqual(score(self.c,drafts),quality);self.assertEqual(Handler.calls-before,used)
        rows=list(records(final/(self.c['name']+'.jsonl')))
        self.assertTrue(all(row['modal_mask']==1 and row['native_field']=='preserved' for row in rows))
        self.assertTrue(all(row['conversations'][0]['value'].count('<image>')==len(row['images']) for row in rows))
        self.assertTrue(all('estimated_tokens' not in row for row in rows))
        result=register(self.c,final);self.assertTrue(Path(result['jsonl']).exists());register(self.c,final)
    def test_dedup_conflicting_labels_go_to_review(self):
        self.fixture(2);s=self.c['sources'][0];p=Path(self.c['raw_root'])/s['label'];data=json.loads(p.read_text('utf8'))
        data['16_16'].append(dict(data['16_16'][0],label='另一个文字'));p.write_bytes(encode(data))
        stage=mechanical(self.c);reviews=list(records(stage/'review.jsonl'))
        self.assertEqual(sum(r['original']['file_name']==data['16_16'][0]['file_name'] for r in reviews),2)
    def test_same_text_different_images_retained(self):
        self.fixture(2);s=self.c['sources'][0];p=Path(self.c['raw_root'])/s['label'];data=json.loads(p.read_text('utf8'))
        data['16_16'][1]['label']=data['16_16'][0]['label'];p.write_bytes(encode(data))
        stage=mechanical(self.c);rows=[r for r in records(stage/'candidate.jsonl') if r['source_annotation']==s['label']]
        self.assertEqual(len(rows),2)
    def test_request_cache_and_pending_guard(self):
        row={'id':'synthetic','label':'中文','question':'读字','answer':'中文','qa_type':'oe','options':None}
        before=Handler.calls;a=judge_one(row,self.c);b=judge_one(row,self.c)
        self.assertEqual(a['state'],'accepted');self.assertEqual(b['state'],'accepted');self.assertEqual(Handler.calls-before,1)
        key=a['judge']['request_hash'];p=Path(self.c['work_root'])/'request-cache'/key[:2]/(key+'.json');p.unlink()
        with self.assertRaises(RuntimeError):judge_one(row,self.c)
    def test_concurrent_identical_payload_uses_one_request(self):
        import qa
        row={'id':'duplicate','label':'中文','question':'同一请求并发','answer':'中文','qa_type':'oe','options':None}
        barrier=threading.Barrier(16);before=Handler.calls;original=qa.direct_open
        def slow_open(*args,**kwargs):
            time.sleep(.08)
            return original(*args,**kwargs)
        def one(i):
            barrier.wait(timeout=5)
            return judge_one(dict(row,id='source-'+str(i)),self.c)
        with patch('qa.direct_open',side_effect=slow_open),ThreadPoolExecutor(max_workers=16) as pool:
            results=list(pool.map(one,range(16)))
        self.assertTrue(all(r['state']=='accepted' for r in results))
        self.assertEqual(Handler.calls-before,1)
        self.assertEqual(qa._FLIGHTS,{})
        self.assertEqual(len({r['id'] for r in results}),16)
    def test_wrong_model_rejected_before_generation(self):
        self.c['judge']['model']='absent'
        before=Handler.calls
        with self.assertRaises(ValueError):api_check(self.c)
        self.assertEqual(Handler.calls,before)


if __name__=='__main__':unittest.main()
