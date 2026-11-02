#!/usr/bin/env python3
"""Passive local Claude hook/status-line observer. No network or model calls."""
import contextlib, argparse, datetime, fcntl, hashlib, hmac, json, math, os, re, stat, sys, uuid
from pathlib import Path
SCHEMA = 'logmap-observations/1'
EVENTS = {'SessionStart','SessionEnd','ConfigChange','PostCompact'}
def number(v, maximum=1e15):
    return v if type(v) in (int,float) and math.isfinite(v) and 0 <= v <= maximum else None
def label(v):
    return v if isinstance(v,str) and re.fullmatch(r'[\w .:/-]{1,96}',v) else None
def obj(v): return v if isinstance(v,dict) else {}
def safe_dir(path):
    p=Path(path).absolute()
    for part in [*reversed(p.parents),p]:
        if part.is_symlink(): raise ValueError('symlink directory refused')
    p.mkdir(mode=0o700,parents=True,exist_ok=True)
    st=p.stat()
    if st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)&0o077: raise ValueError('output directory must be owned by you with mode 700')
    return p
def open_private(path,flags):
    fd=os.open(path, flags|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
    st=os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.getuid() or st.st_nlink!=1 or stat.S_IMODE(st.st_mode)&0o077:
        os.close(fd);raise ValueError('private regular file required')
    return fd
def key(root):
    p=root/'.key'
    # Lock the key file before initialization so concurrent first events agree.
    fd=open_private(p,os.O_RDWR|os.O_CREAT)
    with os.fdopen(fd,'r+b') as f:
        fcntl.flock(f,fcntl.LOCK_EX); b=f.read(33)
        if not b: b=os.urandom(32);f.write(b);f.flush();os.fsync(f.fileno())
        if len(b)!=32:raise ValueError('invalid observer key')
        return b
def settings(paths):
    out=[]
    for i,p in enumerate(paths):
        try:
            fd=os.open(p,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW)
            with os.fdopen(fd,'rb') as f:
                if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):raise ValueError()
                raw=f.read(1024*1024+1)
            if len(raw)>1024*1024:raise ValueError()
            o=obj(json.loads(raw)); values={}
            for k in ('model','effortLevel','autoCompactWindow'):
                v=o.get(k);v=number(v) if k=='autoCompactWindow' else label(v)
                if v is not None:values[k]=v
            out.append({'slot':i+1,'state':'read','sha256':hashlib.sha256(raw).hexdigest(),'values':values})
        except (OSError,ValueError,TypeError):out.append({'slot':i+1,'state':'unavailable'})
    return out
def normalize(o,secret,kind,paths):
    if not isinstance(o,dict):raise ValueError('object input required')
    sid=o.get('session_id')
    if not isinstance(sid,str) or not 1<=len(sid)<=256:raise ValueError('session_id required')
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    r={'schema':SCHEMA,'id':str(uuid.uuid4()),'observedAt':now,'tool':'claude','session':hmac.new(secret,sid.encode(),hashlib.sha256).hexdigest()[:24],'kind':kind}
    if kind=='hook':
        event=o.get('hook_event_name')
        if event not in EVENTS:raise ValueError('unsupported event')
        r.update(event=event,source=label(o.get('source')),model=label(o.get('model')),settings=settings(paths))
    else:
        context=obj(o.get('context_window'));cost=obj(o.get('cost'))
        r.update(model=label(obj(o.get('model')).get('id')),version=label(o.get('version')),effort=label(obj(o.get('effort')).get('level')),
          contextWindow=number(context.get('context_window_size')),inputTotal=number(context.get('total_input_tokens')),outputTotal=number(context.get('total_output_tokens')),estimatedUsd=number(cost.get('total_cost_usd')),limits={})
        for name in ('five_hour','seven_day'):
            x=obj(obj(o.get('rate_limits')).get(name));used=number(x.get('used_percentage'),100);reset=number(x.get('resets_at'),4102444800)
            if used is not None and reset is not None:r['limits'][name]={'used':used,'resetsAt':reset}
    return r
def begin(root):
    # A durable pending marker survives failures/crashes; export exposes the gap.
    pending=safe_dir(root/'pending')
    r={'schema':SCHEMA,'id':str(uuid.uuid4()),'observedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'tool':'claude','session':'0'*24,'kind':'gap','source':'capture_incomplete'}
    path=pending/(r['id']+'.json')
    with os.fdopen(open_private(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL),'w') as f:
        json.dump(r,f);f.flush();os.fsync(f.fileno())
    return path

def capture(root,r):
    p=root/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')+'.jsonl')
    fd=open_private(p,os.O_WRONLY|os.O_APPEND|os.O_CREAT)
    with os.fdopen(fd,'a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        line=json.dumps(r,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n'
        if os.fstat(f.fileno()).st_size+len(line.encode('utf-8'))>50*1024*1024:raise ValueError('daily 50MB limit reached')
        f.write(line);f.flush();os.fsync(f.fileno())
def export(root,dest):
    events=[]
    for p in sorted(root.glob('*.jsonl')):
        with os.fdopen(open_private(p,os.O_RDONLY)) as f:
            fcntl.flock(f,fcntl.LOCK_SH)
            while True:
                line=f.readline(65537)
                if not line:break
                if len(line)>65536 or len(events)>=100000:raise ValueError('export limit exceeded')
                events.append(json.loads(line))
    pending=root/'pending'
    if pending.exists() or pending.is_symlink():
        pending=safe_dir(pending)
        for p in sorted(pending.glob('*.json')):
            if len(events)>=100000:raise ValueError('export limit exceeded')
            with os.fdopen(open_private(p,os.O_RDONLY)) as f:
                raw=f.read(65537)
                if len(raw)>65536:raise ValueError('gap record too large')
                events.append(json.loads(raw))
    # Local output contains pseudonyms, numeric activity, allowlisted settings only.
    payload={'schema':SCHEMA,'events':events}
    fd=open_private(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
    with os.fdopen(fd,'w') as f:json.dump(payload,f,ensure_ascii=False,allow_nan=False);f.flush();os.fsync(f.fileno())
@contextlib.contextmanager
def transaction(root):
    # Export and capture see a consistent pending/event state. flock is released
    # by the OS on crash/timeout; the already-fsynced pending marker survives.
    with os.fdopen(open_private(root/'.lock',os.O_RDWR|os.O_CREAT),'r+b') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        yield

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['hook','status','export','config']);p.add_argument('--dir',required=True);p.add_argument('--settings',action='append',default=[]);p.add_argument('--out');p.add_argument('--base-settings');a=p.parse_args()
    if len(a.settings)>20:raise ValueError('at most 20 explicit settings files')
    if a.mode=='config':
        import shlex
        base=[sys.executable,str(Path(__file__).resolve()),'hook','--dir',str(Path(a.dir).absolute())]
        for f in a.settings:base+=['--settings',str(Path(f).absolute())]
        cmd=shlex.join(base)
        fragment={'hooks':{e:[{'hooks':[{'type':'command','command':cmd,'timeout':5}]}] for e in sorted(EVENTS)},'statusLine':{'type':'command','command':shlex.join([sys.executable,str(Path(__file__).resolve()),'status','--dir',str(Path(a.dir).absolute())])}}
        if a.base_settings:
            with open(a.base_settings,'rb') as f:raw=f.read(1024*1024+1)
            if len(raw)>1024*1024:raise ValueError('settings too large')
            original=json.loads(raw)
            if not isinstance(original,dict) or 'statusLine' in original:raise ValueError('existing statusLine must not be overwritten')
            hooks=original.setdefault('hooks',{})
            if not isinstance(hooks,dict):raise ValueError('invalid hooks')
            for event,items in fragment['hooks'].items():
                prior=hooks.setdefault(event,[])
                if not isinstance(prior,list):raise ValueError('invalid hook list')
                if items[0] not in prior:prior.extend(items)
            original['statusLine']=fragment['statusLine'];fragment=original
        print(json.dumps(fragment,ensure_ascii=False,indent=2));return
    root=safe_dir(a.dir)
    with transaction(root):
        if a.mode=='export':
            if not a.out:raise ValueError('--out required')
            export(root,a.out);return
        pending=begin(root)
        raw=sys.stdin.buffer.read(1024*1024+1)
        if len(raw)>1024*1024:raise ValueError('input too large')
        r=normalize(json.loads(raw),key(root),a.mode,a.settings);capture(root,r)
        pending.unlink()
        if a.mode=='status':print('LOGMAP · '+(r.get('model') or '記録中'))
if __name__=='__main__':
    try:main()
    except Exception as e:
        # No payload, path or exception text (which may contain secrets) in output.
        print('LOGMAP: observation failed ('+type(e).__name__+'); existing AI work is not blocked.',file=sys.stderr)
        # Hooks/status are passive and must never become an approval gate.
        sys.exit(0 if len(sys.argv)>1 and sys.argv[1] in ('hook','status') else 1)
