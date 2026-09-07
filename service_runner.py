"""launchd entry point: bounded console logs and sleep assertion tied to this PID."""
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
(ROOT / 'service-logs').mkdir(exist_ok=True)
handler = RotatingFileHandler(ROOT / 'service-logs/backend.log', maxBytes=2_000_000,
                              backupCount=3, encoding='utf-8')
handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
logger = logging.getLogger('service-console')
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False


class Console:
    def write(self, text):
        if text.strip():
            logger.info(text.rstrip())
        return len(text)

    def flush(self):
        handler.flush()

    def isatty(self):
        return False


sys.stdout = sys.stderr = Console()
# Does not prevent screen lock/display sleep. Assertion ends when this PID exits.
subprocess.Popen(['/usr/bin/caffeinate', '-i', '-s', '-w', str(os.getpid())],
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
sys.path.insert(0, str(ROOT / 'app'))
sys.argv = [str(ROOT / 'app/main.py')]
runpy.run_path(sys.argv[0], run_name='__main__')
