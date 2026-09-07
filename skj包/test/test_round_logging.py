import unittest
from autoelective.control import Controller
from autoelective.tasks import TaskEnvironment


class RoundLoggingTests(unittest.TestCase):
    def test_round_records_each_reason_and_preserves_state(self):
        worker = Controller()
        env = TaskEnvironment()
        env.elective_loop = 8
        reasons = ['暂无空位（余量 0 / 总名额 30），继续等待',
                   '当前第 2 页未找到', '验证码失败，下一轮重试',
                   '提交成功，等待复核', '互斥跳过']
        worker.rows = {str(i): dict(name='课程' + str(i), status=reason)
                       for i, reason in enumerate(reasons)}
        worker.log_round(env)
        self.assertEqual(len(env.events), 1)
        message = env.events[0]['message']
        self.assertIn('第 8 轮检查结果', message)
        for reason in reasons:
            self.assertIn(reason, message)
        self.assertNotIn('已选上', message)
        self.assertIsNone(worker.client)

    def test_unchanged_wait_is_still_reported_each_round(self):
        worker = Controller()
        env = TaskEnvironment()
        worker.rows = {'one': dict(name='测试课程', status='暂无空位')}
        for number in range(1, 105):
            env.elective_loop = number
            worker.log_round(env)
        self.assertEqual(len(env.events), 100)
        self.assertIn('第 104 轮', env.events[0]['message'])
        self.assertEqual(len(env.poll_logs), 100)
        self.assertIn('第 104 轮', env.poll_logs[0]['message'])
        self.assertIn('第 5 轮', env.poll_logs[-1]['message'])
        for _ in range(110):
            env.add_event('info', '等待下一轮')
        self.assertIn('第 104 轮', env.poll_logs[0]['message'])

    def test_errors_retained_and_tasks_isolated(self):
        worker = Controller()
        first, second = TaskEnvironment(), TaskEnvironment()
        worker.log_poll(first, 'error', '网络超时，本次无法确认余量')
        self.assertEqual(first.poll_logs[0]['level'], 'error')
        self.assertIn('网络超时', first.poll_logs[0]['message'])
        self.assertEqual(len(second.poll_logs), 0)
