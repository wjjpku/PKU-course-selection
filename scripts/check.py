"""Run offline regression checks with a disposable sample config, not your account."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'skj包'


def main():
    with tempfile.TemporaryDirectory(prefix='pku-offline-check-') as folder:
        sample = Path(folder) / 'config.ini'
        shutil.copyfile(PACKAGE / 'config.sample.ini', sample)
        script = """
import socket, sys, unittest
def denied(*args, **kwargs):
    raise RuntimeError('Offline checks: network access is disabled')
socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied
from autoelective.environ import Environ
Environ().config_ini = sys.argv[1]
result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover('test', pattern='test_*.py'))
raise SystemExit(not result.wasSuccessful())
"""
        result = subprocess.run([sys.executable, '-c', script, str(sample)], cwd=PACKAGE)
        if result.returncode:
            return result.returncode
    node = shutil.which('node')
    if not node:
        print('Python checks passed. Install Node.js to run the required frontend checks.', file=sys.stderr)
        return 1
    for test in ('test_course_query.cjs', 'test_course_planner.cjs', 'test_plan_helpers.cjs', 'test_workbench_insights.cjs'):
        result = subprocess.run([node, str(PACKAGE / 'test' / test)], cwd=PACKAGE)
        if result.returncode:
            return result.returncode
    for file in ('app.js', 'course-query.js', 'course-planner.js', 'workbench-insights.js'):
        result = subprocess.run([node, '--check', str(PACKAGE / 'web' / file)])
        if result.returncode:
            return result.returncode
    print('All offline checks passed. No school login, election or cancellation was performed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
