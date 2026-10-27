from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'scripts'))
from common import code_sha
from sync import sync


class StandaloneTests(unittest.TestCase):
    def test_code_provenance_is_this_repository(self):
        root=subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PROJECT,text=True,timeout=10).strip()
        self.assertEqual(Path(root).resolve(),PROJECT.resolve())
        expected=subprocess.check_output(['git','rev-parse','HEAD'],cwd=PROJECT,text=True,timeout=10).strip()
        self.assertEqual(code_sha(),expected)
    def test_sync_refuses_dirty_checkout_before_fetch(self):
        responses=['https://github.com/Tiachi/chinese-ocr-qa.git\n','main\n',' M README.md\n']
        def fake(*args,**kwargs):return subprocess.CompletedProcess(args[0],0,stdout=responses.pop(0),stderr='')
        with patch('sync.subprocess.run',side_effect=fake) as call,self.assertRaises(ValueError):sync()
        self.assertEqual(call.call_count,3)
    def test_sync_preserves_global_proxy_but_disables_child(self):
        calls=[]
        def fake(args,**kwargs):
            calls.append((args,kwargs))
            if 'get-url' in args:out='https://github.com/Tiachi/chinese-ocr-qa.git\n'
            elif '--show-current' in args:out='main\n'
            elif '--get-regexp' in args:out='http.proxy\n'
            elif 'rev-parse' in args:out='a'*40+'\n'
            else:out=''
            return subprocess.CompletedProcess(args,0,stdout=out,stderr='')
        with patch.dict('os.environ',{'HTTPS_PROXY':'http://user:secret@127.0.0.1:7890'}),patch('sync.subprocess.run',side_effect=fake):
            sync()
            import os
            self.assertIn('secret',os.environ['HTTPS_PROXY'])
        fetch=next((a,k) for a,k in calls if 'fetch' in a)
        self.assertNotIn('HTTPS_PROXY',fetch[1]['env']);self.assertIn('http.proxy=',fetch[0])


if __name__=='__main__':unittest.main()
