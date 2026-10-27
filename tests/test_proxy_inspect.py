import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from proxy_inspect import summarize,inspect_proxies,local_listener


class ProxyInspectTests(unittest.TestCase):
    def test_userinfo_and_query_are_never_returned(self):
        data=summarize('http://user:PRIVATE_PASSWORD@127.0.0.1:7890/private?token=SECRET')
        self.assertEqual(data['host'],'127.0.0.1');self.assertEqual(data['address_kind'],'loopback');self.assertTrue(data['credentials_present'])
        self.assertNotIn('PRIVATE',json.dumps(data));self.assertNotIn('SECRET',json.dumps(data));self.assertNotIn('user',json.dumps(data))
    def test_hostname_does_not_trigger_dns(self):
        with patch('socket.getaddrinfo',side_effect=AssertionError('no DNS allowed')):
            data=summarize('socks5h://gateway.example:1080')
        self.assertEqual(data['address_kind'],'hostname_not_resolved')
    def test_config_is_not_used_for_external_requests(self):
        run=subprocess.CompletedProcess([],0,stdout='http.proxy http://u:PW@10.0.0.1:8080\n',stderr='')
        with patch.dict('os.environ',{'HTTPS_PROXY':'http://127.0.0.1:7890'},clear=True),patch('proxy_inspect.subprocess.run',return_value=run) as call,patch('proxy_inspect.local_listener',return_value={'status':'listening','processes':[{'name':'sshd','hint':'ssh_tunnel_owner_unknown'}]}) as listener:
            data=inspect_proxies()
        self.assertEqual(data['external_requests'],0);self.assertFalse(data['proxy_used']);self.assertEqual(data['configuration_changes'],0)
        self.assertEqual(call.call_count,1);listener.assert_called_once_with(7890)
        self.assertNotIn('PW',json.dumps(data))
    def test_missing_ss_does_not_scan_process_tree(self):
        with patch('proxy_inspect.shutil.which',return_value=None):
            self.assertEqual(local_listener(7890)['status'],'ss_unavailable')


if __name__=='__main__':unittest.main()
