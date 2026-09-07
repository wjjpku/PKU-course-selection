#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# filename: monitor.py
# modified: 2019-09-11

import logging
import os
import sys
import secrets
import copy
import tempfile
import math
import hashlib
import json
from urllib.parse import urlsplit
from importlib.util import find_spec
import werkzeug._internal as _werkzeug_internal
from flask import Flask, current_app, jsonify, send_from_directory, request, abort
from flask.logging import default_handler
from .environ import Environ
from .config import AutoElectiveConfig
from .logger import ConsoleLogger
from ._internal import absp
from .const import CNN_MODEL_FILE
from .control import controller
from .tasks import manager
from .selftest import selftests

CONTROL_TOKEN = secrets.token_urlsafe(32)

environ = Environ()
config = AutoElectiveConfig()
cout = ConsoleLogger("monitor")
ferr = ConsoleLogger("monitor.error")

FRONTEND_DIR = absp("../web")
monitor = Flask(__name__, static_folder=None)
monitor.config['MAX_CONTENT_LENGTH'] = 128 * 1024


@monitor.before_request
def check_local_request():
    if request.host.split(':')[0] not in ('127.0.0.1', 'localhost', '[', '::1'):
        abort(403)
    if request.method != 'GET':
        if not secrets.compare_digest(request.headers.get('X-Control-Token', ''), CONTROL_TOKEN):
            abort(403)
        if request.headers.get('Origin') and urlsplit(request.headers['Origin']).netloc != request.host:
            abort(403)

monitor.json.ensure_ascii = False
monitor.json.sort_keys = False

_werkzeug_internal._logger = cout  # custom _logger for werkzeug

monitor.logger.removeHandler(default_handler)
for logger in [cout, ferr]:
    for handler in logger.handlers:
        monitor.logger.addHandler(handler)


@monitor.route("/rules", methods=["GET"])
@monitor.route("/stat", methods=["GET"], strict_slashes=False)
def _root():
    rules = []
    for r in sorted(current_app.url_map.iter_rules(), key=lambda r: r.rule):
        line = "{method}  {rule}".format(
                method=','.join( m for m in r.methods if m not in ("HEAD","OPTIONS") ),
                rule=r.rule
            )
        rules.append(line)
    return jsonify({
        "rules": rules,
    })


@monitor.after_request
def _secure_local_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; script-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
    )
    return response


@monitor.route("/", methods=["GET"])
def _dashboard():
    return send_from_directory(FRONTEND_DIR, "index.html")


@monitor.route("/assets/<path:filename>", methods=["GET"])
def _dashboard_asset(filename):
    return send_from_directory(FRONTEND_DIR, filename)


def _safe_config():
    courses = []
    for priority, (course_id, course) in enumerate(config.courses.items(), start=1):
        courses.append({
            "id": course_id,
            "name": course.name,
            "classNo": course.class_no,
            "school": course.school,
            "priority": priority,
        })

    mutexes = [
        {"id": mutex_id, "courses": list(mutex.cids)}
        for mutex_id, mutex in config.mutexes.items()
    ]
    delays = {
        delay.cid: delay.threshold
        for delay in config.delays.values()
    }

    minimum_interval = max(0, config.refresh_interval * (1 - max(0, config.refresh_random_deviation)))
    issues = []
    for course in courses:
        if not course["name"].strip():
            issues.append({"level": "error", "message": "课程 %s 缺少课程名称" % course["id"]})
        if not course["school"].strip():
            issues.append({"level": "error", "message": "课程 %s 缺少开课单位" % course["id"]})
    for mutex in mutexes:
        if len(mutex["courses"]) < 2:
            issues.append({"level": "warning", "message": "互斥组 %s 少于两门课程，不会产生效果" % mutex["id"]})
    if minimum_interval <= 0:
        issues.append({"level": "error", "message": "轮询间隔必须大于 0"})

    return {
        "courses": courses,
        "mutexes": mutexes,
        "delays": delays,
        "client": {
            "page": config.supply_cancel_page,
            "loginTimeout": config.iaaa_client_timeout,
            "requestTimeout": config.elective_client_timeout,
            "refreshInterval": config.refresh_interval,
            "randomDeviation": config.refresh_random_deviation,
            "minimumInterval": minimum_interval,
            "poolSize": config.elective_client_pool_size,
            "maxLife": config.elective_client_max_life,
        },
        "issues": issues,
    }


def _safe_diagnostics():
    modules = ("requests", "lxml", "flask", "numpy", "ddddocr")
    return {
        "pythonVersion": sys.version.split()[0],
        "dependencies": {
            module: find_spec(module) is not None
            for module in modules
        },
        "modelReady": os.path.isfile(CNN_MODEL_FILE),
        "modelSize": os.path.getsize(CNN_MODEL_FILE) if os.path.isfile(CNN_MODEL_FILE) else 0,
        "localOnly": True,
    }


def config_revision():
    return hashlib.sha256(json.dumps(_safe_config(), sort_keys=True).encode()).hexdigest()


@monitor.route("/api/overview", methods=["GET"])
def _api_overview():
    it = environ.iaaa_loop_thread
    et = environ.elective_loop_thread
    with environ.lock:
        runtime = {
            "phase": environ.phase,
            "operationEnabled": environ.operation_enabled,
            "startedAt": environ.started_at,
            "lastPollAt": environ.last_poll_at,
            "nextPollAt": environ.next_poll_at,
            "iaaaLoop": environ.iaaa_loop,
            "electiveLoop": environ.elective_loop,
            "iaaaAlive": it is not None and it.is_alive(),
            "electiveAlive": et is not None and et.is_alive(),
            "errors": dict(environ.errors),
            "events": list(environ.events)[:30],
        }
    return jsonify({
        "controlToken": CONTROL_TOKEN,
        "configRevision": config_revision(),
        "control": controller.snapshot(),
        "tasks": manager.snapshot(),
        "selftests": selftests.snapshot(),
        "account": {"configured": bool(config.iaaa_id and config.iaaa_password),
                    "maskedId": ('***' + config.iaaa_id[-4:]) if config.iaaa_id else '',
                    "dualDegree": config.is_dual_degree, "identity": config.identity},
        "runtime": runtime,
        "config": _safe_config(),
        "diagnostics": _safe_diagnostics(),
    })


@monitor.route('/api/control', methods=['POST'])
def control_action():
    try:
        data = request.get_json() or {}
        if manager.active() and data.get('action') in ('start','login','read-courses','logout','export-courses'):
            return jsonify(error='请先停止刷课任务，再操作账号或读取课程，以免影响运行会话'), 409
        with manager.lock, controller.lock:
            if data.get('action') == 'export-courses' and manager.active():
                return jsonify(error='请先停止刷课任务再全量查询'), 409
            if data.get('action') == 'start' and data.get('configRevision') != config_revision():
                return jsonify(error='配置已变化或页面版本过旧，请刷新并核对已生效配置后再启动'), 409
            controller.command(data.get('action'))
        return jsonify(controller.snapshot())
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@monitor.route('/api/course-export/download', methods=['GET'])
def download_course_export():
    from pathlib import Path
    filename = controller.export.get('filename')
    if not filename or controller.export.get('status') == 'running':
        return jsonify(error='尚无可下载的查询结果'), 404
    return send_from_directory(Path(__file__).resolve().parents[1] / 'data/exports', filename,
                               as_attachment=True, download_name=filename, mimetype='text/csv; charset=utf-8')


@monitor.route('/api/course-library', methods=['GET'])
def course_library():
    from .course_library import read_library
    # Read only the current account's saved export, never enumerate other files.
    if manager.store and manager.store.account_key != manager.store.account():
        return jsonify(error='账号已切换，请重启后端后载入该账号的课程库'), 409
    metadata = manager.store.load_library_export() if manager.store else controller.export
    try:
        result = read_library(metadata)
        result['accountScope'] = manager.store.account() if manager.store else hashlib.sha256(
            (config.iaaa_id + ':' + config.identity).encode()).hexdigest()
        return jsonify(result)
    except FileNotFoundError:
        return jsonify(error='已导出的课程库文件不存在，请重新查询'), 404
    except (ValueError, OSError) as exc:
        return jsonify(error='无法读取课程库：' + (str(exc) if isinstance(exc, ValueError) else '文件读取失败')), 400


@monitor.route('/api/config', methods=['POST'])
def save_configuration():
    with manager.lock, controller.lock:
        if controller.active() or manager.active():
            return jsonify(error='请先停止任务，再保存配置'), 409
        previous = config._config
        candidate = copy.deepcopy(previous)
        try:
            data = request.get_json()
            if not isinstance(data, dict):
                raise ValueError('配置格式错误')
            if 'account' in data:
                account = data['account']
                if account.get('studentId'):
                    candidate.set('user', 'student_id', str(account['studentId']).strip())
                if account.get('password'):
                    candidate.set('user', 'password', str(account['password']))
                if account.get('identity') not in ('bzx', 'bfx'):
                    raise ValueError('请选择主修或辅双身份')
                candidate.set('user', 'identity', account['identity'])
                candidate.set('user', 'dual_degree', str(bool(account.get('dualDegree'))))
            if 'plan' in data:
                plan = data['plan']
                for section in list(candidate.sections()):
                    if section.startswith(('course:', 'mutex:', 'delay:')):
                        candidate.remove_section(section)
                ids = set()
                import re
                for course in plan['courses']:
                    cid = course['id']
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', cid) or cid in ids:
                        raise ValueError('课程标识无效或重复')
                    ids.add(cid)
                    section = 'course:' + cid
                    candidate.add_section(section)
                    for key, value in [('name', course['name']), ('class', course['classNo']), ('school', course['school'])]:
                        if '\n' in str(value) or '\r' in str(value):
                            raise ValueError('课程字段不能包含换行')
                        candidate.set(section, key, str(value))
                    if int(course['classNo']) != float(course['classNo']) or int(course['classNo']) < 0:
                        raise ValueError('班号必须为非负整数')
                for index, group in enumerate(plan['mutexes']):
                    members = group['courses']
                    if len(set(members)) < 2 or not set(members) <= ids:
                        raise ValueError('互斥组需至少两门有效课程')
                    section = 'mutex:' + str(index)
                    candidate.add_section(section)
                    candidate.set(section, 'courses', ','.join(members))
                for index, (cid, threshold) in enumerate(plan['delays'].items()):
                    if cid not in ids or int(threshold) != float(threshold) or int(threshold) <= 0:
                        raise ValueError('名额阈值必须为正整数且对应有效课程')
                    section = 'delay:' + str(index)
                    candidate.add_section(section)
                    candidate.set(section, 'course', cid)
                    candidate.set(section, 'threshold', str(threshold))
                mapping = {'refreshInterval':'refresh_interval', 'randomDeviation':'random_deviation',
                           'poolSize':'elective_client_pool_size', 'maxLife':'elective_client_max_life',
                           'page':'supply_cancel_page', 'loginTimeout':'iaaa_client_timeout',
                           'requestTimeout':'elective_client_timeout'}
                for key, option in mapping.items():
                    if key in plan['client']:
                        value = plan['client'][key]
                        if not math.isfinite(float(value)):
                            raise ValueError('数值必须有限')
                        candidate.set('client', option, str(value))
                config._config = candidate
                errors = config.election_validation_errors()
                errors = [e for e in errors if e not in ('学号不能为空', '密码不能为空')]
                if errors:
                    raise ValueError('；'.join(errors))
            from .const import DEFAULT_CONFIG_INI
            target = os.path.abspath(environ.config_ini or DEFAULT_CONFIG_INI)
            fd, temporary = tempfile.mkstemp(dir=os.path.dirname(target), prefix='.config-')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as output:
                    candidate.write(output)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            config._config = candidate
            if 'account' in data:
                controller.close_session()
            environ.add_event('info', '配置已保存，下次任务使用新配置')
            return jsonify(ok=True)
        except (ValueError, TypeError, KeyError) as exc:
            config._config = previous
            return jsonify(error=str(exc)), 400
        except Exception:
            config._config = previous
            raise


@monitor.route('/api/tasks', methods=['POST'])
def create_task():
    try:
        data=request.get_json() or {}
        tid=manager.create(data['plan'])
        return jsonify(id=tid), 201
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return jsonify(error=str(exc)), 400


@monitor.route('/api/tasks/<tid>', methods=['POST'])
def task_action(tid):
    try:
        data=request.get_json() or {}
        manager.command(tid,data.get('action'),data.get('plan'))
        return jsonify(ok=True)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return jsonify(error=str(exc)), 400


@monitor.route('/api/selftest', methods=['POST'])
def run_selftest():
    try:
        selftests.start((request.get_json() or {}).get('test','all'))
        return jsonify(ok=True)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

@monitor.route("/stat/loop", methods=["GET"])
def _stat_iaaa_loop():
    it = environ.iaaa_loop_thread
    et = environ.elective_loop_thread
    it_alive = it is not None and it.is_alive()
    et_alive = et is not None and et.is_alive()
    finished = not it_alive and not et_alive
    error_encountered = not finished and ( not it_alive or not et_alive )
    return jsonify({
        "iaaa_loop": environ.iaaa_loop,
        "elective_loop": environ.elective_loop,
        "iaaa_loop_is_alive": it_alive,
        "elective_loop_is_alive": et_alive,
        "finished": finished,
        "error_encountered": error_encountered,
    })

@monitor.route("/stat/course", methods=["GET"])
def _stat_course():
    goals = environ.goals # [course]
    ignored = environ.ignored # {course, reason}
    return jsonify({
        "goals": [ str(c) for c in goals ],
        "current": [ str(c) for c in goals if c not in ignored ],
        "ignored": { str(c): r for c, r in ignored.items() },
    })

@monitor.route("/stat/error", methods=["GET"])
def _stat_error():
    return jsonify({
        "errors": environ.errors,
    })


def run_monitor():
    from pathlib import Path
    manager.enable_storage(Path(__file__).resolve().parents[1] / 'data/workbench.sqlite3')
    cached = manager.store.load_catalog()
    if cached:
        controller.catalog = cached
        controller.catalog['note'] = '数据库历史缓存，非实时结果；登录后可重新读取课程'
    controller.catalog_sink = manager.store.save_catalog
    saved_export = manager.store.load_export()
    if saved_export:
        controller.export = saved_export
    controller.export_sink = manager.store.save_export
    host = config.monitor_host
    if host not in ("127.0.0.1", "localhost", "::1"):
        cout.warning("Dashboard has no remote authentication; binding to 127.0.0.1 instead of %s", host)
        host = "127.0.0.1"
    cout.info("Preparation dashboard: http://%s:%s", host, config.monitor_port)
    monitor.run(
        host=host,
        port=config.monitor_port,
        debug=False,
        use_reloader=False,
    )
