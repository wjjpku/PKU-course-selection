import sys
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from autoelective import parser
from autoelective.control import Controller, Cancelled
from autoelective.monitor import monitor, CONTROL_TOKEN, controller, config, environ


class ControlTests(unittest.TestCase):
    def test_read_reuses_and_preserves_valid_login(self):
        c = Controller()
        c.logged_in = True
        c.login_time = time.monotonic()
        with patch.object(c, 'login') as login, patch.object(c, 'read_courses'), patch.object(c, 'close_session') as close:
            c.run('read-courses')
        login.assert_not_called()
        close.assert_not_called()
        self.assertTrue(c.logged_in)

    def test_stop_preserves_session_logout_closes_it(self):
        c = Controller()
        c.logged_in = True
        c.command('stop')
        self.assertTrue(c.logged_in)
        c.command('logout')
        self.assertFalse(c.logged_in)

    def test_stale_start_never_dispatches_worker(self):
        with patch.object(controller, 'command') as command:
            response = monitor.test_client().post('/api/control', json={'action':'start', 'configRevision':'stale'}, headers={'X-Control-Token':CONTROL_TOKEN})
        self.assertEqual(response.status_code, 409)
        command.assert_not_called()

    def test_saved_plan_is_used_by_next_start_and_invalid_save_rolls_back(self):
        import copy
        original, old_path = config._config, environ.config_ini
        try:
            with tempfile.TemporaryDirectory() as folder:
                environ.config_ini = str(Path(folder)/'config.ini')
                client = monitor.test_client()
                headers = {'X-Control-Token':CONTROL_TOKEN}
                plan = client.get('/api/overview').json['config']
                plan['courses'] = [dict(id='test',name='测试课程',classNo=1,school='测试学院')]
                plan['mutexes'] = []
                plan['delays'] = {}
                plan['client'].update(refreshInterval=5, randomDeviation=.2)
                self.assertEqual(client.post('/api/config',json={'plan':plan},headers=headers).status_code,200)
                saved_bytes = Path(environ.config_ini).read_bytes()
                overview = client.get('/api/overview').json
                self.assertEqual(overview['config']['courses'][0]['name'], '测试课程')
                observed = []
                with patch.object(controller, 'command', side_effect=lambda action: observed.append(config.courses['test'].name)):
                    response = client.post('/api/control',json={'action':'start','configRevision':overview['configRevision']},headers=headers)
                self.assertEqual(response.status_code,200)
                self.assertEqual(observed, ['测试课程'])
                invalid = copy.deepcopy(plan)
                invalid['courses'][0]['name'] = ''
                self.assertEqual(client.post('/api/config',json={'plan':invalid},headers=headers).status_code,400)
                self.assertEqual(Path(environ.config_ini).read_bytes(),saved_bytes)
                self.assertEqual(config.courses['test'].name,'测试课程')
        finally:
            config._config, environ.config_ini = original, old_path

    def test_course_read_uses_only_read_methods_and_keeps_results(self):
        calls = []
        def results():
            calls.append('results')
            return SimpleNamespace(_tree=parser.get_tree('<html><table><tr><th>课程名</th><th>班号</th></tr><tr><td>测试课程</td><td>01</td></tr></table></html>'))
        def available(username):
            calls.append('available')
            raise ValueError('当前未开放')
        c = Controller()
        # Deliberately no election/cancellation methods on this fake client.
        c.client = SimpleNamespace(get_ShowResults=results, get_SupplyCancel=available)
        c.read_courses(SimpleNamespace(supply_cancel_page=1, iaaa_id='test'))
        self.assertEqual(calls, ['results', 'available'])
        self.assertEqual(c.catalog['results'][0]['rows'], [['测试课程', '01']])
        self.assertIn('当前未开放', c.catalog['note'])

    def test_unknown_course_page_is_not_empty_success(self):
        with self.assertRaises(Exception):
            parser.get_display_tables(parser.get_tree('<html><body>访问受限</body></html>'))

    def test_pause_stop_prevents_next_request(self):
        c = Controller()
        c.stop_event.set()
        called = []
        with self.assertRaises(Cancelled):
            c.call(lambda: called.append(1))
        self.assertEqual(called, [])

    def test_control_requires_token(self):
        client = monitor.test_client()
        self.assertEqual(client.post('/api/control', json={'action':'start'}).status_code,403)
        self.assertEqual(client.get('/api/overview', headers={'Host':'evil.example'}).status_code,403)

    def test_stop_during_request_prevents_continuation(self):
        c = Controller()
        continued = []
        def request():
            c.stop_event.set()
            return 'response'
        with self.assertRaises(Cancelled):
            c.call(request)
            continued.append(True)
        self.assertEqual(continued, [])

    def test_cross_origin_write_rejected(self):
        response = monitor.test_client().post('/api/control', json={'action':'stop'},
            headers={'X-Control-Token':CONTROL_TOKEN, 'Origin':'http://evil.example'})
        self.assertEqual(response.status_code,403)

    def test_account_save_roundtrip_without_secret_response(self):
        original = config._config
        old_path = environ.config_ini
        try:
            with tempfile.TemporaryDirectory() as folder:
                environ.config_ini = str(Path(folder)/'config.ini')
                client = monitor.test_client()
                response = client.post('/api/config', json={'account':{'studentId':'test123456',
                    'password':'unique-test-secret', 'dualDegree':False,'identity':'bzx'}},
                    headers={'X-Control-Token':CONTROL_TOKEN})
                self.assertEqual(response.status_code,200)
                self.assertIn('unique-test-secret', Path(environ.config_ini).read_text())
                body = client.get('/api/overview').get_data(as_text=True)
                self.assertNotIn('unique-test-secret',body)
                self.assertNotIn('test123456',body)
                self.assertEqual(Path(environ.config_ini).stat().st_mode & 0o777,0o600)
        finally:
            config._config = original
            environ.config_ini = old_path

    def test_login_worker_failure_is_observable(self):
        c = Controller()
        with patch.object(c, 'login', side_effect=RuntimeError('mock login failure')):
            c.run('login')
        self.assertEqual(c.snapshot()['phase'],'error')
        self.assertFalse(c.logged_in)
        self.assertEqual(c.failure,'mock login failure')


if __name__ == '__main__':
    unittest.main()
