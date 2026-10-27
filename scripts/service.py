"""Foreground owned service only; never stop or reconfigure an existing service."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys


def service_command(c):
    cmd=[c['python'],'-B','-m','vllm.entrypoints.cli.main','serve',c['model_path'],
         '--served-model-name',c['served_model_name'],'--host',c['host'],'--port',str(c['port']),
         '--tensor-parallel-size',str(c['tp']),'--data-parallel-size',str(c['dp']),
         '--data-parallel-size-local',str(c['dp']),'--data-parallel-backend','mp','--api-server-count','4',
         '--max-model-len',str(c['max_model_len']),'--max-num-seqs',str(c['max_num_seqs']),
         '--max-num-batched-tokens',str(c['max_num_batched_tokens']),'--gpu-memory-utilization',str(c['memory_utilization']),
         '--enable-prefix-caching','--mamba-cache-mode','align','--enable-chunked-prefill','--async-scheduling',
         '--compilation-config','{"cudagraph_mode":"FULL_DECODE_ONLY"}','--block-size','128',
         '--generation-config','vllm','--mm-processor-cache-gb','0',
         '--limit-mm-per-prompt',json.dumps({'image':1 if c['vision'] else 0,'audio':0,'video':0})]
    if not c['vision']:cmd+=['--language-model-only']
    return cmd


def native_check(c):
    import torch_npu
    npu=torch_npu.npu
    if npu.device_count()!=c['tp']*c['dp']:raise ValueError('visible NPU count differs from TP*DP')
    for i in range(npu.device_count()):
        free,total=npu.mem_get_info(i)
        if free<total*c['memory_utilization']:raise ValueError('NPU memory busy; nothing stopped')
    print('[ocr-qa] DEVICE_MEMORY_PASS',flush=True)


def start(path):
    c=json.loads(Path(path).read_text('utf8'))
    if not Path(c['model_path']).is_dir() or not Path(c['vllm_path']).is_dir():raise ValueError('existing model/vLLM path missing; no download attempted')
    with socket.socket() as sock:
        sock.settimeout(1)
        if sock.connect_ex(('127.0.0.1',c['port']))==0:raise ValueError('service port occupied; reuse API or select another port')
    env=os.environ.copy();env['VLLM_PATH']=c['vllm_path'];env['PYTHONPATH']=c['vllm_path']+os.pathsep+env.get('PYTHONPATH','')
    subprocess.run([c['python'],str(Path(__file__).resolve()),'native-check',str(path)],env=env,check=True,timeout=90)
    print('[ocr-qa] SERVICE_COMMAND '+json.dumps(service_command(c)),flush=True)
    # Foreground child inherits terminal SIGINT; no detached unrelated process groups.
    subprocess.run(service_command(c),env=env,check=True)


if __name__=='__main__':
    if sys.argv[1]=='native-check':native_check(json.loads(Path(sys.argv[2]).read_text('utf8')))
    else:start(sys.argv[1])
