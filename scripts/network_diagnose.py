"""Bounded direct DNS/TCP/TLS probes. No media, model, proxy or global changes."""
import json
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
import urllib.parse

from download import network_error,network_report


def diagnose_origin(origin):
    parsed=urllib.parse.urlparse(origin)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/'):
        raise ValueError('expected credential-free HTTPS origin')
    host=parsed.hostname;port=parsed.port or 443
    result={'origin':origin,'probes':[]}
    start=time.monotonic()
    try:
        addresses=socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
        result['dns_seconds']=round(time.monotonic()-start,3)
    except OSError as error:result['dns_error']=network_error(error);return result
    # At most one IPv4 and one IPv6 endpoint per origin. Parent kills child at20s.
    for family in (socket.AF_INET,socket.AF_INET6):
        entry=next((x for x in addresses if x[0]==family),None)
        label='IPv4' if family==socket.AF_INET else 'IPv6'
        if entry is None:result['probes'].append({'family':label,'status':'no_dns_address'});continue
        kind,proto,address=entry[1],entry[2],entry[4]
        probe={'family':label,'address':address[0]};start=time.monotonic()
        try:
            with socket.socket(family,kind,proto) as conn:
                conn.settimeout(3);conn.connect(address);probe['tcp']='ok'
                with ssl.create_default_context().wrap_socket(conn,server_hostname=host) as secure:
                    probe['tls']='ok';probe['tls_version']=secure.version()
        except Exception as e:probe.update(network_error(e))
        probe['seconds']=round(time.monotonic()-start,3);result['probes'].append(probe)
    return result


def diagnose(c):
    results=[]
    origins=list(dict.fromkeys(c['download']['benchmark_urls']))
    if len(origins)>4:raise ValueError('diagnostic origin budget is4; narrow config first')
    for origin in origins:
        try:
            run=subprocess.run([sys.executable,str(Path(__file__).resolve()),origin],capture_output=True,text=True,timeout=20)
            if run.returncode:results.append({'origin':origin,'status':'diagnostic_child_failed','stderr_not_printed':True})
            else:results.append(json.loads(run.stdout))
        except subprocess.TimeoutExpired:results.append({'origin':origin,'status':'dns_or_connect_probe_budget_exceeded'})
    return {'network_policy':network_report(),'scope':'up to4 origins, one IPv4/IPv6 TCP443+verified TLS handshake each; <=20s child budget/origin; no file body download','results':results}


if __name__=='__main__':print(json.dumps(diagnose_origin(sys.argv[1])))
