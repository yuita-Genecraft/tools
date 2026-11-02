import concurrent.futures, importlib.util, json, os, pathlib, subprocess, sys, tempfile, unittest
P=pathlib.Path(__file__).resolve().parents[1]/'cc-seizon/observe.py'
spec=importlib.util.spec_from_file_location('observer',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Observer(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name).resolve();self.data=self.root/'data'
 def runobs(self,mode,payload=None,*args):
  return subprocess.run([sys.executable,str(P),mode,'--dir',str(self.data),*args],input=json.dumps(payload or {}),text=True,capture_output=True)
 def hook(self):return {'session_id':'private-session','hook_event_name':'SessionStart','source':'resume','transcript_path':'SECRET','cwd':'SECRET','prompt':'SECRET'}
 def test_minimum_and_private(self):
  r=self.runobs('hook',self.hook());self.assertEqual(r.returncode,0);self.assertEqual(r.stdout,'');p=next(self.data.glob('*.jsonl'));s=p.read_text();self.assertNotIn('SECRET',s);self.assertNotIn('private-session',s);self.assertEqual(p.stat().st_mode&0o777,0o600);self.assertEqual(self.data.stat().st_mode&0o777,0o700)
 def test_settings_allowlist(self):
  p=self.root/'config';p.write_text(json.dumps({'model':'opus','effortLevel':'high','autoCompactWindow':400000,'env':{'TOKEN':'SECRET'}}));r=self.runobs('hook',self.hook(),'--settings',str(p));self.assertEqual(r.stderr,'');s=next(self.data.glob('*.jsonl')).read_text();self.assertNotIn('SECRET',s);self.assertEqual(json.loads(s)['settings'][0]['values']['effortLevel'],'high')
 def test_missing_settings(self):
  self.runobs('hook',self.hook(),'--settings',str(self.root/'absent'));self.assertEqual(json.loads(next(self.data.glob('*.jsonl')).read_text())['settings'][0]['state'],'unavailable')
 def test_status_missing_not_zero(self):
  self.runobs('status',{'session_id':'x'});r=json.loads(next(self.data.glob('*.jsonl')).read_text());self.assertIsNone(r['inputTotal']);self.assertEqual(r['limits'],{})
 def test_status_quota(self):
  r=m.normalize({'session_id':'x','rate_limits':{'five_hour':{'used_percentage':0,'resets_at':1800000000},'seven_day':{'used_percentage':-1,'resets_at':1800000000}}},b'x','status',[]);self.assertEqual(r['limits'],{'five_hour':{'used':0,'resetsAt':1800000000}})
 def test_parallel_first_capture(self):
  with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:rs=list(pool.map(lambda _:self.runobs('hook',self.hook()),range(16)))
  self.assertTrue(all(not r.stderr for r in rs));rows=[json.loads(x) for x in next(self.data.glob('*.jsonl')).read_text().splitlines()];self.assertEqual(len(rows),16);self.assertEqual(len({r['session'] for r in rows}),1);self.assertEqual(len({r['id'] for r in rows}),16)
 def test_symlink_directory(self):
  self.data.symlink_to(self.root,target_is_directory=True);r=self.runobs('hook',self.hook());self.assertIn('failed',r.stderr);self.assertEqual(r.returncode,0);self.assertFalse((self.root/'.key').exists())
 def test_symlink_key(self):
  self.data.mkdir(mode=0o700);target=self.root/'target';target.write_text('intact');(self.data/'.key').symlink_to(target);r=self.runobs('hook',self.hook());self.assertIn('failed',r.stderr);self.assertEqual(target.read_text(),'intact')
 def test_hardlink(self):
  self.data.mkdir(mode=0o700);target=self.root/'target';target.write_bytes(b'a'*32);os.chmod(target,0o600);os.link(target,self.data/'.key');r=self.runobs('hook',self.hook());self.assertIn('failed',r.stderr)
 def test_bad_mode(self):
  self.data.mkdir(mode=0o755);self.assertIn('failed',self.runobs('hook',self.hook()).stderr)
 def test_unsupported_event_nonblocking(self):
  self.assertIn('failed',self.runobs('hook',{'session_id':'x','hook_event_name':'Stop'}).stderr);self.assertFalse(list(self.data.glob('*.jsonl')))
 def test_export_and_no_overwrite(self):
  self.runobs('hook',self.hook());out=self.root/'export.json';r=self.runobs('export',None,'--out',str(out));self.assertEqual(r.returncode,0);self.assertEqual(len(json.loads(out.read_text())['events']),1);self.assertEqual(self.runobs('export',None,'--out',str(out)).returncode,1)
 def test_config_no_mutation(self):
  r=self.runobs('config');self.assertEqual(r.returncode,0);o=json.loads(r.stdout);self.assertEqual(set(o['hooks']),m.EVENTS);self.assertFalse(self.data.exists())
 def test_merge_config_preserves_hooks(self):
  p=self.root/'base.json';base={'hooks':{'Stop':[{'hooks':[{'type':'command','command':'old'}]}]},'permissions':{'defaultMode':'default'}};p.write_text(json.dumps(base));r=self.runobs('config',None,'--base-settings',str(p));o=json.loads(r.stdout);self.assertEqual(o['hooks']['Stop'],base['hooks']['Stop']);self.assertEqual(o['permissions'],base['permissions']);self.assertEqual(json.loads(p.read_text()),base)
 def test_existing_statusline_refused(self):
  p=self.root/'base.json';p.write_text('{"statusLine":{"type":"command","command":"old"}}');r=self.runobs('config',None,'--base-settings',str(p));self.assertEqual(r.returncode,1);self.assertEqual(r.stdout,'')
 def test_fifo_settings_nonblocking(self):
  p=self.root/'pipe';os.mkfifo(p);self.runobs('hook',self.hook(),'--settings',str(p));self.assertEqual(json.loads(next(self.data.glob('*.jsonl')).read_text())['settings'][0]['state'],'unavailable')
 def test_failure_exported_as_gap(self):
  self.runobs('hook',{'session_id':'x','hook_event_name':'invalid'});out=self.root/'export.json';self.assertEqual(self.runobs('export',None,'--out',str(out)).returncode,0);rs=json.loads(out.read_text())['events'];self.assertEqual(len(rs),1);self.assertEqual(rs[0]['kind'],'gap')
 def test_success_removes_pending(self):
  self.runobs('hook',self.hook());self.assertEqual(list((self.data/'pending').glob('*.json')),[])
 def test_daily_byte_limit_before_append(self):
  root=m.safe_dir(self.data);p=root/(m.datetime.datetime.now(m.datetime.timezone.utc).strftime('%Y-%m-%d')+'.jsonl');fd=m.open_private(p,os.O_WRONLY|os.O_CREAT)
  with os.fdopen(fd,'wb') as f:f.truncate(50*1024*1024-1)
  with self.assertRaises(ValueError):m.capture(root,{'x':'large'})
  self.assertEqual(p.stat().st_size,50*1024*1024-1)
 def test_export_during_parallel_capture(self):
  m.safe_dir(self.data)
  def capture(i):return self.runobs('hook',self.hook())
  def export(i):return self.runobs('export',None,'--out',str(self.root/('e'+str(i)+'.json')))
  with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
   fs=[pool.submit(capture,i) for i in range(24)]+[pool.submit(export,i) for i in range(12)]
   results=[f.result() for f in fs]
  self.assertTrue(all(r.returncode==0 and not r.stderr for r in results),[r.stderr for r in results])
  for p in self.root.glob('e*.json'):
   events=json.loads(p.read_text())['events'];self.assertEqual(len({e['id'] for e in events}),len(events));self.assertTrue(all(e['kind']=='hook' for e in events))
 def test_invalid_input_does_not_expose(self):
  r=self.runobs('hook',{'session_id':'SECRET','hook_event_name':'SECRET'});self.assertNotIn('SECRET',r.stderr);self.assertEqual(r.returncode,0)
if __name__=='__main__':unittest.main()
