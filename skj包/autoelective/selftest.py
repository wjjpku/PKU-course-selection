"""Offline, separate-process checks. No live controller/config mutation."""
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS = {'logic':'任务、配置与接口回归', 'ocr':'本地验证码历史样本'}


class SelfTests:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.results = {}

    def snapshot(self):
        with self.lock:
            return dict(running=self.running, results=[dict(id=k,name=v,**self.results.get(k, {'status':'未测试'})) for k,v in CHECKS.items()])

    def start(self, name):
        if name not in (*CHECKS, 'all'):
            raise ValueError('未知测试项')
        with self.lock:
            if self.running:
                raise ValueError('自检进行中，请等待完成')
            self.running = True
        threading.Thread(target=self.run,args=(list(CHECKS) if name=='all' else [name],),daemon=True).start()

    def run(self, names):
        try:
            for name in names:
                tick=time.monotonic()
                with self.lock:
                    self.results[name] = dict(status='测试中')
                deny = "import socket\ndef denied(*a,**k): raise RuntimeError('offline self-test: network disabled')\nsocket.socket.connect=denied\nsocket.socket.connect_ex=denied\nsocket.create_connection=denied\n"
                if name == 'logic':
                    script = "import unittest\nr=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover('test',pattern='test_*.py'))\nraise SystemExit(not r.wasSuccessful())"
                else:
                    script = "from pathlib import Path\nfrom autoelective.captcha import CaptchaRecognizer\nm=CaptchaRecognizer()\nfiles=sorted(Path('test/data').glob('*.jpg'))\nassert files, 'No samples'\nn=sum(m.recognize(p.read_bytes()).code==p.name.split('_')[0] for p in files)\nprint('历史样本: %s / %s 正确; 未验证学校在线验证码' % (n,len(files)))\nraise SystemExit(n!=len(files))"
                try:
                    proc = subprocess.run([sys.executable,'-c',deny+script],cwd=ROOT,capture_output=True,text=True,timeout=90)
                    result=dict(status='通过' if proc.returncode==0 else '失败',detail=(proc.stdout+proc.stderr)[-10000:])
                except Exception as exc:
                    result=dict(status='失败',detail=str(exc))
                result['durationMs']=round((time.monotonic()-tick)*1000)
                with self.lock:
                    self.results[name]=result
        finally:
            with self.lock:
                self.running=False


selftests=SelfTests()
