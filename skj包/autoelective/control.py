"""Single local worker with cooperative pause/stop and observable results."""
import copy
import threading
import time
import random
from requests.exceptions import RequestException
from .config import AutoElectiveConfig
from .environ import Environ
from .logger import redact_sensitive


class Cancelled(BaseException):
    pass


class Controller:
    def __init__(self, config=None, environment=None, limiter=None):
        self.config = config
        self.environment = environment
        self.limiter = limiter
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.resume_event = threading.Event()
        self.resume_event.set()
        self.thread = None
        self.client = None
        self.phase = 'preparation'
        self.rows = {}
        self.captcha = {}
        self.logged_in = False
        self.failure = None
        self.outcome = None
        self.login_time = 0
        self.logout_requested = False
        self.catalog = dict(results=[], available=[], updatedAt=None, note='尚未读取', page=None)
        self.export = dict(status='idle', pages=0, rows=0, message='尚未查询', filename=None)

    def active(self):
        return self.thread is not None and self.thread.is_alive()

    def checkpoint(self):
        while not self.resume_event.wait(.1):
            if self.stop_event.is_set():
                raise Cancelled()
        if self.stop_event.is_set():
            raise Cancelled()

    def call(self, fn, *args, **kwargs):
        self.checkpoint()
        result = self.limiter.call(self, fn, *args, **kwargs) if self.limiter else fn(*args, **kwargs)
        self.checkpoint()
        return result

    def snapshot(self):
        with self.lock:
            return dict(phase=self.phase, active=self.active(), loggedIn=self.logged_in,
                        failure=self.failure, outcome=copy.deepcopy(self.outcome), courses=copy.deepcopy(list(self.rows.values())),
                        captcha=copy.deepcopy(self.captcha), catalog=copy.deepcopy(self.catalog), export=copy.deepcopy(self.export))

    def log_round(self, env):
        """Report observed outcomes, never infer election success from a submission."""
        details = '；'.join('%s：%s' % (r['name'], r['status']) for r in self.rows.values())
        self.log_poll(env, 'info', '第 %s 轮检查结果：%s' % (env.elective_loop, details))

    def log_poll(self, env, level, message):
        env.add_event(level, message)
        if hasattr(env, 'add_poll_log'):
            env.add_poll_log(level, message)

    def command(self, action):
        with self.lock:
            if action in ('pause', 'resume', 'stop', 'logout'):
                if action == 'pause':
                    if not self.active():
                        raise ValueError('没有正在运行的任务')
                    self.resume_event.clear()
                    self.phase = 'paused'
                elif action == 'resume':
                    if self.phase != 'paused':
                        raise ValueError('任务未暂停')
                    self.phase = 'running'
                    self.resume_event.set()
                else:
                    self.logout_requested = action == 'logout'
                    self.stop_event.set()
                    self.resume_event.set()
                    self.phase = 'stopping' if self.active() else 'stopped'
                    if not self.active() and self.logout_requested:
                        self.close_session()
                return
            if action not in ('start', 'login', 'ocr-test', 'read-courses', 'export-courses'):
                raise ValueError('未知操作')
            if self.active():
                raise ValueError('请先停止当前任务')
            cfg = self.config or AutoElectiveConfig()
            if action == 'start':
                errors = cfg.election_validation_errors()
                if errors:
                    raise ValueError('；'.join(errors))
                self.rows = {cid: dict(id=cid, name=c.name, status='等待登录', attempts=0)
                             for cid, c in cfg.courses.items()}
            if action in ('login', 'start', 'read-courses', 'export-courses') and (not cfg.iaaa_id or not cfg.iaaa_password):
                raise ValueError('请先保存账号和密码')
            self.stop_event.clear()
            self.logout_requested = False
            self.resume_event.set()
            self.failure = None
            self.outcome = None
            if action == 'export-courses':
                self.export = dict(status='running', pages=0, rows=0, message='准备登录查询', filename=None)
            self.phase = 'testing' if action == 'ocr-test' else 'starting'
            self.thread = threading.Thread(target=self.run, args=(action,), daemon=True)
            self.thread.start()

    def close_session(self):
        if self.client is not None:
            self.client.clear_cookies()
            self.client._session.close()
        self.client = None
        self.logged_in = False

    def login(self, cfg):
        from .iaaa import IAAAClient
        from .elective import ElectiveClient
        from .parser import get_sida
        self.close_session()
        auth = IAAAClient(timeout=cfg.iaaa_client_timeout)
        try:
            self.call(auth.oauth_home)
            response = self.call(auth.oauth_login, cfg.iaaa_id, cfg.iaaa_password)
            self.client = ElectiveClient(1, timeout=cfg.elective_client_timeout)
            response = self.call(self.client.sso_login, response.json()['token'])
            if cfg.is_dual_degree:
                self.call(self.client.sso_login_dual_degree, get_sida(response), cfg.identity, response.url)
            self.logged_in = True
            self.login_time = time.monotonic()
            (self.environment or Environ()).add_event('success', '登录成功')
        finally:
            auth._session.close()

    def run(self, action):
        env = self.environment or Environ()
        cfg = self.config or AutoElectiveConfig()
        try:
            if action == 'ocr-test':
                from pathlib import Path
                from .captcha import CaptchaRecognizer
                model = CaptchaRecognizer()
                samples = sorted((Path(__file__).resolve().parents[1] / 'test/data').glob('*.jpg'))
                correct = 0
                for sample in samples:
                    self.checkpoint()
                    tick = time.perf_counter()
                    result = model.recognize(sample.read_bytes()).code
                    correct += result == sample.name.split('_')[0]
                    with self.lock:
                        self.captcha = dict(code=result, latencyMs=round((time.perf_counter()-tick)*1000, 2),
                                            correct=correct, total=len(samples), source='历史样本',
                                            validation='离线测试，未调用学校校验接口')
                env.add_event('success', '本地验证码测试：%d / %d 正确' % (correct, len(samples)))
                self.phase = 'ready'
                return
            if not self.logged_in or (cfg.elective_client_max_life > 0 and time.monotonic() - self.login_time >= cfg.elective_client_max_life):
                self.login(cfg)
            if action == 'export-courses':
                from .course_export import export_courses
                self.phase = 'reading'
                export_courses(self, cfg)
                self.phase = 'stopped' if self.export['status'] == 'cancelled' else 'ready'
                return
            if action == 'read-courses':
                self.read_courses(cfg)
                self.phase = 'ready'
                return
            if action == 'login':
                self.phase = 'ready'
                return
            from .captcha import CaptchaRecognizer
            from .parser import get_tables, get_courses, get_courses_with_detail
            from .exceptions import (ElectionSuccess, NotInOperationTimeError,
                                     SessionExpiredError, InvalidTokenError, TipsException, CaughtCheatingError)
            model = CaptchaRecognizer()
            goals = cfg.courses
            delays = {d.cid: d.threshold for d in cfg.delays.values()}
            done = set()
            failures = 0
            self.rows = {cid: dict(id=cid, name=c.name, status='等待检查', attempts=0) for cid,c in goals.items()}
            self.phase = 'running'
            while True:
                self.checkpoint()
                env.next_poll_at = None
                env.add_event('info', '开始检查课程，正在等待学校响应（账号请求按限速排队）')
                try:
                    if cfg.elective_client_max_life > 0 and time.monotonic() - self.login_time >= cfg.elective_client_max_life:
                        self.login(cfg)
                    page = self.call(self.client.get_SupplyCancel, cfg.iaaa_id)
                    if cfg.supply_cancel_page > 1:
                        page = self.call(self.client.get_supplement, cfg.iaaa_id, page=cfg.supply_cancel_page)
                    tables = get_tables(page._tree)
                    elected = get_courses(tables[1])
                    plans = get_courses_with_detail(tables[0])
                    env.last_poll_at = int(time.time())
                    env.elective_loop += 1
                    for cid, row in self.rows.items():
                        if cid not in done and row['status'] != '互斥跳过':
                            row['status'] = '本轮尚未检查：先处理前序课程，下一轮继续检查'
                            row['reasonCode'] = 'queued'
                    for cid, goal in goals.items():
                        if goal in elected:
                            done.add(cid)
                            self.rows[cid]['status'] = '已选上'
                            self.rows[cid]['reasonCode'] = 'confirmed'
                    for rule in cfg.mutexes.values():
                        if any(cid in done for cid in rule.cids):
                            for cid in rule.cids:
                                if cid not in done:
                                    self.rows[cid]['status'] = '互斥跳过'
                                    self.rows[cid]['reasonCode'] = 'mutex'
                    for cid, goal in goals.items():
                        self.checkpoint()
                        row = self.rows[cid]
                        if cid in done or row['status'] == '互斥跳过':
                            continue
                        course = next((c for c in plans if c == goal), None)
                        if course is None:
                            row['status'] = '当前第 %s 页未找到，不代表课程不存在；请核对页码与班号' % cfg.supply_cancel_page
                            row['reasonCode'] = 'not_found'
                            continue
                        row.update(remaining=course.remaining_quota, quota=course.max_quota)
                        if not course.is_available():
                            row['status'] = '暂无空位（余量 %s / 总名额 %s），继续等待' % (course.remaining_quota, course.max_quota)
                            row['reasonCode'] = 'no_seats'
                            continue
                        if cid in delays and course.remaining_quota > delays[cid]:
                            row['status'] = '未达到设置的提交条件：余量 %s，需不超过 %s' % (course.remaining_quota, delays[cid])
                            row['reasonCode'] = 'threshold'
                            continue
                        image = self.call(self.client.get_DrawServlet)
                        tick = time.perf_counter()
                        code = model.recognize(image.content).code
                        latency = round((time.perf_counter()-tick)*1000, 2)
                        checked = self.call(self.client.get_Validate, cfg.iaaa_id, code).json().get('valid')
                        self.captcha = dict(code=code, latencyMs=latency,
                                            source='选课网', validation='通过' if checked == '2' else '失败')
                        if checked != '2':
                            row['status'] = '验证码失败，下一轮重试'
                            row['reasonCode'] = 'captcha'
                            break
                        row['attempts'] += 1
                        try:
                            self.call(self.client.get_ElectSupplement, course.href)
                            row['status'] = '响应待确认'
                            row['reasonCode'] = 'pending_confirmation'
                        except ElectionSuccess:
                            row['status'] = '提交成功，等待复核'
                            row['reasonCode'] = 'pending_confirmation'
                        except TipsException as exc:
                            row['status'] = '学校返回提示，尚未确认选上：' + redact_sensitive(str(exc))
                            row['reasonCode'] = 'ineligible' if any(text in str(exc) for text in
                                ('不符合选课条件', '不满足选课条件', '没有选课资格', '不具备选课资格')) else 'school_notice'
                        # Refresh official results before any second submission.
                        break
                    failures = 0
                    self.outcome = None
                    self.log_round(env)
                    if all(cid in done or r['status'] == '互斥跳过' for cid,r in self.rows.items()):
                        self.phase = 'completed'
                        return
                except NotInOperationTimeError:
                    self.phase = 'waiting_window'
                    self.outcome = dict(code='window_closed', message='学校返回不在操作时段；任务已停止，不会自动重试')
                    self.log_poll(env, 'warning', '本次未选上：学校返回不在操作时段，任务已停止')
                    return
                except CaughtCheatingError:
                    self.outcome = dict(code='school_block', message='学校禁止当前自动操作，已停止；请使用官方页面')
                    self.log_poll(env, 'error', '学校提示禁止刷课，本次未确认选上，任务停止，不再重试')
                    raise RuntimeError('学校提示禁止刷课，已停止。请改用学校官方页面，不自动重试。')
                except (SessionExpiredError, InvalidTokenError):
                    self.outcome = dict(code='session_expired', message='登录会话失效，本轮未完成检查；正在重新登录')
                    self.log_poll(env, 'warning', '登录会话失效，本次未完成检查；正在重新登录')
                    self.login(cfg)
                except Exception as exc:
                    failures += 1
                    self.outcome = dict(code='network_error' if isinstance(exc, RequestException) else 'check_failed',
                                        message='本轮检查未完成：' + redact_sensitive(str(exc)))
                    self.log_poll(env, 'error', '本次检查未完成（连续失败 %s 次），不能确认当前余量或选课结果：%s' % (failures, redact_sensitive(str(exc))))
                    if failures >= 5:
                        raise RuntimeError('连续失败 5 次，已停止。请查看运行记录。') from exc
                interval = cfg.refresh_interval * (1 + random.uniform(-cfg.refresh_random_deviation, cfg.refresh_random_deviation))
                wait = max(interval, min(120, 4 * 2**failures) if failures else 0)
                env.next_poll_at = int(time.time() + wait)
                env.add_event('info', '等待 %.1f 秒后再次检查，预计 %s；暂停或账号请求排队可能延后' % (wait, time.strftime('%H:%M:%S', time.localtime(env.next_poll_at))))
                deadline = time.monotonic() + wait
                while time.monotonic() < deadline:
                    self.checkpoint()
                    self.stop_event.wait(.1)
        except Cancelled:
            self.phase = 'stopped'
            if action == 'export-courses' and self.export['status'] == 'running':
                self.export.update(status='cancelled', message='查询已停止')
        except Exception as exc:
            self.failure = redact_sensitive(str(exc))
            if action == 'export-courses':
                self.export.update(status='failed', message=self.failure)
            self.phase = 'error'
            env.add_event('error', self.failure)
        finally:
            if self.logout_requested or self.phase == 'error':
                self.close_session()
            env.next_poll_at = None
            env.add_event('info', '任务状态：' + self.phase)

    def read_courses(self, cfg):
        """Bounded read-only fetch. No CAPTCHA, election, cancellation or link traversal."""
        from .parser import get_display_tables, get_tables, get_courses_with_detail
        from .schedule import display_courses
        self.phase = 'reading'
        with self.lock:
            self.catalog = dict(results=[], available=[], updatedAt=None, note='正在读取选课结果', page=cfg.supply_cancel_page)
        response = self.call(self.client.get_ShowResults)
        results = get_display_tables(response._tree)
        with self.lock:
            self.catalog.update(results=results, enrolled=[c for c in display_courses(results) if c['result'] == '已选上'], updatedAt=int(time.time()), note='选课结果已读取；正在读取可选列表')
        try:
            response = self.call(self.client.get_SupplyCancel, cfg.iaaa_id)
            if cfg.supply_cancel_page > 1:
                response = self.call(self.client.get_supplement, cfg.iaaa_id, page=cfg.supply_cancel_page)
            tables = get_tables(response._tree)
            if not tables:
                raise ValueError('未识别到可选课程表')
            courses = get_courses_with_detail(tables[0])
            details = display_courses(get_display_tables(response._tree))
            indexed = {(c['name'], c['classNo'], c['school']): c for c in details}
            available = [dict(name=c.name, classNo=c.class_no, school=c.school,
                              remaining=c.remaining_quota, quota=c.max_quota,
                              **{k:v for k,v in indexed.get((c.name,c.class_no,c.school),{}).items() if k not in ('name','classNo','school')}) for c in courses]
            with self.lock:
                self.catalog.update(available=available, note='只读完成；可选列表仅包含配置页，不代表全部课程')
        except Exception as exc:
            with self.lock:
                self.catalog['note'] = '选课结果已读取；可选列表暂不可用：' + redact_sensitive(str(exc))
        (self.environment or Environ()).add_event('info', '课程只读查询完成，未执行选课或退课')
        if hasattr(self, 'catalog_sink'):
            self.catalog_sink(self.catalog)


controller = Controller()
