"""Read configured proxy metadata and exact local listeners. Never use a proxy."""
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.parse


def summarize(value):
    """Only scheme, host and port are retained; no userinfo, path or parameters."""
    try:
        parsed=urllib.parse.urlparse(value if '://' in value else 'http://'+value)
        host=parsed.hostname;port=parsed.port
        if not host:raise ValueError('missing host')
        if port is None:port={'https':443,'http':80,'socks5':1080,'socks5h':1080}.get(parsed.scheme)
        try:
            address=ipaddress.ip_address(host)
            kind='loopback' if address.is_loopback else 'private' if address.is_private else 'public'
        except ValueError:kind='loopback' if host.lower()=='localhost' else 'hostname_not_resolved'
        return {'scheme':parsed.scheme,'host':host,'port':port,'address_kind':kind,'credentials_present':parsed.username is not None or parsed.password is not None}
    except (ValueError,TypeError):return {'status':'invalid_or_non_url_value','raw_value_not_printed':True}


def local_listener(port):
    if not isinstance(port,int) or not 1<=port<=65535:return {'status':'no_valid_port'}
    ss=shutil.which('ss')
    if ss is None:return {'status':'ss_unavailable','no_fallback_process_scan':True}
    try:
        result=subprocess.run([ss,'-H','-ltnp',f'sport = :{port}'],capture_output=True,text=True,timeout=5)
        if result.returncode:return {'status':'listener_query_failed','stderr_not_printed':True}
        raw=result.stdout[:65536]
        pids=sorted(set(int(p) for p in re.findall(r'pid=(\d+)',raw)))[:8]
        processes=[]
        for pid in pids:
            process={'pid':pid}
            try:
                name=(Path('/proc')/str(pid)/'comm').read_text().strip()[:80]
                # comm is the executable name; do not read cmdline or environ.
                process['name']=name
                process['hint']='ssh_tunnel_owner_unknown' if name in ('ssh','sshd') else 'proxy_software_owner_unknown' if any(x in name.lower() for x in ('clash','mihomo','gost','sing-box','squid','tinyproxy','v2ray','xray')) else 'ownership_unknown'
            except OSError:process['name']='unavailable'
            processes.append(process)
        return {'status':'listening' if raw.strip() else 'no_local_tcp_listener','processes':processes}
    except subprocess.TimeoutExpired:return {'status':'listener_query_timeout'}


def inspect_proxies():
    values=[]
    for key,value in sorted(os.environ.items()):
        if key.lower() in ('http_proxy','https_proxy','all_proxy') and value:
            values.append({'source':'environment','variable':key,'endpoint':summarize(value)})
    result=subprocess.run(['git','config','--get-regexp',r'^(http|https)(\..*)?\.proxy$'],capture_output=True,text=True,timeout=10)
    if result.returncode not in (0,1):git_status='git_config_query_failed'
    else:
        git_status='read'
        for line in result.stdout.splitlines()[:16]:
            parts=line.split(None,1)
            if len(parts)==2:values.append({'source':'git_configuration','scope_not_printed':True,'endpoint':summarize(parts[1])})
    listeners={}
    for row in values:
        endpoint=row['endpoint']
        if endpoint.get('address_kind')=='loopback' and endpoint.get('port') not in listeners:
            listeners[endpoint['port']]=local_listener(endpoint['port'])
    return {'proxy_used':False,'external_requests':0,'configuration_changes':0,
            'git_config_status':git_status,'configured_proxies':values,
            'exact_loopback_port_listeners':listeners,
            'conclusion':'Process/address metadata cannot by itself prove public versus personal ownership. Do not use an unconfirmed proxy.',
            'scope':'read proxy env + git proxy values in memory; inspect ss only on configured loopback ports; no cmdline/environ/keys read; no requests sent'}


if __name__=='__main__':print(json.dumps(inspect_proxies(),ensure_ascii=False))
