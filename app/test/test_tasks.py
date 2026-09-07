import copy
import threading
import time
import unittest
from unittest.mock import patch
from autoelective.tasks import TaskManager, AccountLimiter, task_config, ConfigConflict
from autoelective.control import Cancelled
from autoelective.config import AutoElectiveConfig


def plan(name='测试甲'):
    return dict(courses=[dict(id='test',name=name,classNo=1,school='测试学院')],mutexes=[],delays={},
                client=dict(refreshInterval=5,randomDeviation=.2,page=1,maxLife=600,loginTimeout=30,requestTimeout=60))


class TaskTests(unittest.TestCase):
    def test_create_is_inert_and_config_isolated(self):
        manager=TaskManager()
        before=copy.deepcopy(AutoElectiveConfig()._config)
        data=plan()
        tid=manager.create(data)
        data['courses'][0]['name']='changed'
        self.assertFalse(manager.active())
        self.assertEqual(manager.snapshot()[0]['plan']['courses'][0]['name'],'测试甲')
        self.assertEqual(dict(before.items('user')),dict(AutoElectiveConfig()._config.items('user')))
        self.assertIsNot(manager.tasks[tid]['worker'].config._config,AutoElectiveConfig()._config)

    def test_duplicate_rejected_and_remove_allows_recreate(self):
        manager=TaskManager();tid=manager.create(plan())
        with self.assertRaises(ValueError):manager.create(plan())
        manager.command(tid,'remove')
        manager.create(plan())

    def test_invalid_frequency_rejected(self):
        data=plan();data['client']['refreshInterval']=0
        with self.assertRaises(ValueError):task_config(data)

    def test_task_update_does_not_change_other_task(self):
        manager=TaskManager();a=manager.create(plan());b=manager.create(plan('测试乙'))
        data=plan();data['client']['refreshInterval']=8
        manager.command(a,'update',data,manager.snapshot()[0]['configRevision'])
        self.assertEqual(manager.tasks[a]['worker'].config.refresh_interval,8)
        self.assertEqual(manager.tasks[b]['worker'].config.refresh_interval,5)

    def test_revision_blocks_stale_start_and_missing_confirmation(self):
        manager=TaskManager();tid=manager.create(plan())
        old=manager.snapshot()[0]['configRevision']
        changed=plan();changed['client']['refreshInterval']=9
        manager.command(tid,'update',changed,old)
        current=manager.snapshot()[0]['configRevision']
        self.assertNotEqual(old,current)
        worker=manager.tasks[tid]['worker']
        with patch.object(worker,'command') as command:
            for revision in (None,old):
                with self.assertRaises(ConfigConflict):manager.command(tid,'start',expected_revision=revision)
            command.assert_not_called()
            manager.command(tid,'start',expected_revision=current)
            command.assert_called_once_with('start')
        self.assertEqual(manager.snapshot()[0]['runningRevision'],current)

    def test_snapshot_is_not_mutable_and_update_cannot_overwrite_newer_plan(self):
        manager=TaskManager();tid=manager.create(plan())
        snapshot=manager.snapshot()[0]
        snapshot['plan']['courses'][0]['name']='external edit'
        self.assertEqual(manager.snapshot()[0]['plan']['courses'][0]['name'],'测试甲')
        changed=plan();changed['client']['refreshInterval']=10
        manager.command(tid,'update',changed,snapshot['configRevision'])
        with self.assertRaises(ConfigConflict):manager.command(tid,'update',plan(),snapshot['configRevision'])
        self.assertEqual(manager.snapshot()[0]['plan']['client']['refreshInterval'],10)

    def test_plan_displays_effective_normalized_values(self):
        manager=TaskManager();data=plan()
        data['courses'][0].update(name=' 测试甲 ',school=' 测试学院 ',classNo='1.0')
        data['client']['poolSize']=5
        manager.create(data)
        saved=manager.snapshot()[0]['plan']
        self.assertEqual(saved['courses'][0]['name'],'测试甲')
        self.assertEqual(saved['courses'][0]['classNo'],1)
        self.assertEqual(saved['client']['poolSize'],1)

    def test_api_returns_conflict_without_invoking_worker(self):
        from autoelective.monitor import monitor, CONTROL_TOKEN
        manager=TaskManager();tid=manager.create(plan())
        with patch('autoelective.monitor.manager',manager), patch.object(manager.tasks[tid]['worker'],'command') as command:
            response=monitor.test_client().post('/api/tasks/'+tid,json={'action':'start'},
                headers={'X-Control-Token':CONTROL_TOKEN})
            self.assertEqual(response.status_code,409)
            command.assert_not_called()

    def test_invalid_metadata_update_is_atomic(self):
        manager=TaskManager();tid=manager.create(plan());before=manager.snapshot()[0]
        changed=plan();changed['client']['refreshInterval']=9
        changed['courses'][0]['credits']=float('nan')
        with self.assertRaises(ValueError):manager.command(tid,'update',changed,before['configRevision'])
        self.assertEqual(manager.snapshot()[0]['configRevision'],before['configRevision'])
        self.assertEqual(manager.tasks[tid]['worker'].config.refresh_interval,5)

    def test_update_active_task_does_not_change_config(self):
        manager=TaskManager();tid=manager.create(plan());before=manager.snapshot()[0]
        with patch.object(manager.tasks[tid]['worker'],'active',return_value=True):
            with self.assertRaises(ValueError):manager.command(tid,'update',plan(),before['configRevision'])
        self.assertEqual(manager.snapshot()[0]['configRevision'],before['configRevision'])

    def test_independent_pause_and_stop_with_fake_loops(self):
        manager=TaskManager()
        workers=[manager.tasks[manager.create(plan(name))]['worker'] for name in ('甲','乙')]
        ticks=[threading.Event(),threading.Event()]
        def run(worker, event):
            try:
                while True:
                    worker.checkpoint();event.set();worker.stop_event.wait(.01)
            except Cancelled:pass
        try:
            for worker,event in zip(workers,ticks):
                worker.thread=threading.Thread(target=run,args=(worker,event));worker.thread.start()
                self.assertTrue(event.wait(1))
            workers[0].command('pause')
            workers[0].command('stop');workers[0].thread.join(1)
            self.assertFalse(workers[0].active())
            ticks[1].clear();self.assertTrue(ticks[1].wait(1))
            self.assertTrue(workers[1].active())
        finally:
            for worker in workers:
                worker.command('stop');worker.thread.join(1)

    def test_shared_limiter_serializes_calls(self):
        limiter=AccountLimiter(.02)
        manager=TaskManager()
        workers=[manager.tasks[manager.create(plan(name))]['worker'] for name in ('甲','乙')]
        times=[]
        threads=[threading.Thread(target=lambda w=w:limiter.call(w,lambda:times.append(time.monotonic()))) for w in workers]
        for t in threads:t.start()
        for t in threads:t.join(1)
        self.assertEqual(len(times),2)
        self.assertGreaterEqual(times[1]-times[0],.019)
