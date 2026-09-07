"""Independent task state; bounded account-wide traffic, no cancellation API."""
import copy
import math
import threading
import time
import uuid
from collections import deque
from .config import AutoElectiveConfig
from .control import Controller, controller
from .logger import redact_sensitive


class AccountLimiter:
    def __init__(self, interval=0):
        self.interval = interval
        self.lock = threading.Lock()
        self.next_at = 0

    def call(self, worker, fn, *args, **kwargs):
        while True:
            worker.checkpoint()
            if not self.lock.acquire(timeout=.1):
                continue
            try:
                remaining = self.next_at - time.monotonic()
                if remaining <= 0:
                    # Never wait for one paused task while holding the account lock.
                    if not worker.resume_event.is_set() or worker.stop_event.is_set():
                        continue
                    try:
                        return fn(*args, **kwargs)
                    finally:
                        self.next_at = time.monotonic() + self.interval
            finally:
                self.lock.release()
            worker.stop_event.wait(min(.1, remaining))


class TaskEnvironment:
    def __init__(self):
        self.lock = threading.RLock()
        self.events = deque(maxlen=100)
        self.poll_logs = deque(maxlen=100)
        self.last_poll_at = self.next_poll_at = None
        self.elective_loop = 0
        self.on_change = lambda: None

    def add_event(self, level, message):
        with self.lock:
            self.events.appendleft(dict(timestamp=int(time.time()), level=level, message=redact_sensitive(message)))
            self.on_change()

    def add_poll_log(self, level, message):
        """Independent bounded polling history; lifecycle events cannot evict it."""
        with self.lock:
            self.poll_logs.appendleft(dict(timestamp=int(time.time()), level=level,
                                          message=redact_sensitive(message)))
            self.on_change()


def task_config(plan):
    """Copy settings, never replace global configuration or write account files."""
    cfg = copy.copy(AutoElectiveConfig())
    cfg._config = copy.deepcopy(cfg._config)
    p = cfg._config
    for section in list(p.sections()):
        if section.startswith(('course:', 'mutex:', 'delay:')):
            p.remove_section(section)
    courses = plan.get('courses', [])
    if not 1 <= len(courses) <= 30:
        raise ValueError('每个任务请选择 1 至 30 门课')
    ids = set()
    for c in courses:
        cid = str(c['id'])
        if not cid or not cid.replace('_', '').replace('-', '').isalnum() or cid in ids or len(cid) > 32:
            raise ValueError('课程标识无效或重复')
        ids.add(cid)
        number = float(c['classNo'])
        if not math.isfinite(number) or number < 0 or not number.is_integer():
            raise ValueError('班号必须为非负整数')
        section = 'course:' + cid
        p.add_section(section)
        for key, value in [('name', c['name']), ('class', int(number)), ('school', c['school'])]:
            if '\n' in str(value) or '\r' in str(value):
                raise ValueError('课程字段不能包含换行')
            p.set(section, key, str(value).strip())
    for i, group in enumerate(plan.get('mutexes', [])):
        section = 'mutex:' + str(i)
        p.add_section(section)
        p.set(section, 'courses', ','.join(group['courses']))
    for i, (cid, threshold) in enumerate(plan.get('delays', {}).items()):
        number = float(threshold)
        if not math.isfinite(number) or not number.is_integer() or number <= 0:
            raise ValueError('阈值必须为正整数')
        section = 'delay:' + str(i)
        p.add_section(section)
        p.set(section, 'course', cid)
        p.set(section, 'threshold', str(int(number)))
    mapping = {'refreshInterval':'refresh_interval', 'randomDeviation':'random_deviation',
               'page':'supply_cancel_page', 'loginTimeout':'iaaa_client_timeout',
               'requestTimeout':'elective_client_timeout', 'maxLife':'elective_client_max_life'}
    for key, option in mapping.items():
        if key in plan.get('client', {}):
            value = float(plan['client'][key])
            if not math.isfinite(value) or (key in ('page','maxLife') and not value.is_integer()):
                raise ValueError('任务参数无效')
            p.set('client', option, str(int(value)) if key in ('page','maxLife') else str(value))
    errors = [e for e in cfg.election_validation_errors() if e not in ('学号不能为空', '密码不能为空')]
    if errors:
        raise ValueError('；'.join(errors))
    return cfg


class TaskManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.tasks = {}
        self.limiter = AccountLimiter()
        self.store = None

    def enable_storage(self, path):
        from .task_store import TaskStore
        storage = TaskStore(path)
        for saved in storage.load():
            tid = self.create(saved['plan'])
            task = self.tasks.pop(tid)
            task['id'] = saved['id']
            task['createdAt'] = saved['createdAt']
            self.tasks[task['id']] = task
            env = task['env']
            env.events.extend(saved.get('events', [])[:99])
            env.poll_logs.extend(saved.get('pollLogs', [])[:100])
            env.elective_loop = saved.get('loops', 0)
            env.last_poll_at = saved.get('lastPollAt')
            task['worker'].rows = saved.get('rows', task['worker'].rows)
            task['worker'].phase = 'stopped'
            env.add_event('info', '已从本地数据库恢复；历史状态仅供查看，需手动启动，不自动提交选课')
        self.store = storage
        for task in self.tasks.values():
            self.persist(task)

    def persist(self, task):
        if self.store:
            env = task['env']
            self.store.save(dict(id=task['id'], createdAt=task['createdAt'], plan=task['plan'],
                events=list(env.events), pollLogs=list(env.poll_logs), loops=env.elective_loop,
                lastPollAt=env.last_poll_at, rows=task['worker'].rows))

    def active(self):
        with self.lock:
            return any(t['worker'].active() for t in self.tasks.values())

    def create(self, plan):
        with self.lock:
            if len(self.tasks) >= 20:
                raise ValueError('最多保留 20 个任务，请先移除不需要的任务')
            cfg = task_config(plan)
            identity = set(cfg.courses.values())
            for task in self.tasks.values():
                if identity.intersection(task['worker'].config.courses.values()):
                    raise ValueError('已有任务包含相同课程，请先移除原任务，避免重复提交')
            tid = uuid.uuid4().hex[:12]
            env = TaskEnvironment()
            worker = Controller(cfg, env, self.limiter)
            worker.rows = {cid:dict(id=cid,name=c.name,status='尚未启动',attempts=0) for cid,c in cfg.courses.items()}
            self.tasks[tid] = dict(id=tid, createdAt=int(time.time()), plan=copy.deepcopy(plan), worker=worker, env=env)
            task = self.tasks[tid]
            env.on_change = lambda: self.persist(task)
            env.add_event('info', '任务已创建，尚未启动；配置与其他任务独立')
            return tid

    def command(self, tid, action, plan=None):
        with self.lock:
            if tid not in self.tasks:
                raise ValueError('任务不存在')
            task = self.tasks[tid]
            worker = task['worker']
            if action == 'update':
                if worker.active():
                    raise ValueError('请先停止任务再调整配置')
                cfg = task_config(plan)
                for other_id, other in self.tasks.items():
                    if other_id != tid and set(cfg.courses.values()).intersection(other['worker'].config.courses.values()):
                        raise ValueError('课程已存在于其他任务')
                worker.config = cfg
                task['plan'] = copy.deepcopy(plan)
                task['env'].add_event('info', '任务配置已更新，下次启动生效')
                return
            if action == 'remove':
                if worker.active():
                    raise ValueError('请先停止任务再移除')
                worker.close_session()
                if self.store:
                    self.store.delete(tid)
                del self.tasks[tid]
                return
            if action not in ('start','pause','resume','stop'):
                raise ValueError('不支持的任务操作')
            if action == 'start':
                if controller.active():
                    raise ValueError('账号操作进行中，请稍后再启动')
                if sum(t['worker'].active() for t in self.tasks.values()) >= 3:
                    raise ValueError('同时运行上限为 3 个任务，共用账号限速')
                # Account credentials are refreshed only when explicitly starting.
                for key, value in AutoElectiveConfig()._config.items('user'):
                    worker.config._config.set('user', key, value)
            worker.command(action)
            task['env'].add_event('info', '用户操作：' + action)

    def snapshot(self):
        with self.lock:
            result = []
            for task in self.tasks.values():
                env = task['env']
                with env.lock:
                    result.append(dict(id=task['id'], createdAt=task['createdAt'], plan=task['plan'],
                        state=task['worker'].snapshot(), loops=env.elective_loop,
                        lastPollAt=env.last_poll_at, nextPollAt=env.next_poll_at, events=list(env.events),
                        pollLogs=list(env.poll_logs)))
            return result


manager = TaskManager()
controller.limiter = manager.limiter
