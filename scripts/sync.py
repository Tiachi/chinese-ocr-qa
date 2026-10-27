"""Clean fast-forward sync of this public repo; child-only direct Git routing."""
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def sync():
    env=os.environ.copy()
    for key in list(env):
        if key.lower() in ('http_proxy','https_proxy','all_proxy'):env.pop(key)
    env.update(GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never')
    def git(*args,check=True):
        return subprocess.run(['git',*args],cwd=ROOT,env=env,capture_output=True,text=True,timeout=60,check=check)
    if git('remote','get-url','origin').stdout.strip()!='https://github.com/Tiachi/chinese-ocr-qa.git':raise ValueError('origin is not this public repository HTTPS URL')
    if git('branch','--show-current').stdout.strip()!='main':raise ValueError('sync expects main; do not switch away from task work')
    if git('status','--porcelain').stdout.strip():raise ValueError('dirty checkout; no stash/reset/clean attempted')
    result=git('config','--name-only','--get-regexp',r'^(http|https)(\..*)?\.proxy$',check=False)
    if result.returncode not in (0,1):raise ValueError('cannot inspect Git proxy settings')
    overrides=['-c','http.proxy=','-c','https.proxy=']
    keys=result.stdout.splitlines()
    for key in keys:
        if '@' in key or '?' in key or '\n' in key:raise ValueError('sensitive Git proxy scope; not printed or used')
        overrides+=['-c',key+'=']
    print('[ocr-sync] ROUTING '+json.dumps({'personal_proxy':False,'git_proxy_keys_overridden_for_child':len(keys),'global_config_changes':0}),flush=True)
    git(*overrides,'fetch','origin','main')
    git('merge','--ff-only','origin/main')
    local=git('rev-parse','HEAD').stdout.strip();remote=git('rev-parse','origin/main').stdout.strip()
    if local!=remote:raise ValueError('local/remote SHA mismatch')
    print('[ocr-sync] PASS '+local,flush=True)


if __name__=='__main__':
    try:sync()
    except Exception as e:raise SystemExit('[ocr-sync] FAIL '+type(e).__name__+'; existing work retained')
