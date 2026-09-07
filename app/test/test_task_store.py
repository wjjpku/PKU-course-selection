import tempfile
from pathlib import Path
import unittest
from autoelective.tasks import TaskManager, task_config
from test_tasks import plan


class StoreTests(unittest.TestCase):
    def test_restore_identity_plan_logs_without_start(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tasks.sqlite'
            first = TaskManager()
            first.enable_storage(path)
            data = plan()
            data['client']['refreshInterval'] = .5
            task_config(data)
            tid = first.create(data)
            env = first.tasks[tid]['env']
            revision=first.snapshot()[0]['configRevision']
            first.tasks[tid]['runningRevision']=revision
            for i in range(105):
                env.add_poll_log('info', '暂无空位 ' + str(i))
            second = TaskManager()
            second.enable_storage(path)
            restored = second.snapshot()[0]
            self.assertEqual(restored['id'], tid)
            self.assertEqual(restored['plan']['client']['refreshInterval'], .5)
            self.assertEqual(len(restored['pollLogs']), 100)
            self.assertEqual(restored['runningRevision'],revision)
            self.assertEqual(restored['pollLogs'][0]['configRevision'],revision)
            self.assertIn('104', restored['pollLogs'][0]['message'])
            self.assertFalse(restored['state']['active'])
            self.assertFalse(restored['state']['loggedIn'])
            self.assertEqual(restored['state']['phase'], 'stopped')
            self.assertEqual(len(second.store.load()), 1)
            second.command(tid, 'remove')
            self.assertEqual(second.store.load(), [])
            first.store.db.close()
            second.store.db.close()
