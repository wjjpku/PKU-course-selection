#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# filename: config.py
# modified: 2019-09-10

import os
import re
import hashlib
import math
from configparser import RawConfigParser, DuplicateSectionError
from collections import OrderedDict
from .environ import Environ
from .course import Course
from .rule import Mutex, Delay
from .utils import Singleton
from .const import DEFAULT_CONFIG_INI
from .exceptions import UserInputException

_reNamespacedSection = re.compile(r'^\s*(?P<ns>[^:]+?)\s*:\s*(?P<id>[^,]+?)\s*$')
_reCommaSep = re.compile(r'\s*,\s*')

environ = Environ()


class BaseConfig(object):

    def __init__(self, config_file=None):
        if self.__class__ is __class__:
            raise NotImplementedError
        file = os.path.normpath(os.path.abspath(config_file))
        if not os.path.exists(file):
            raise FileNotFoundError("Config file was not found: %s" % file)
        self._config = RawConfigParser()
        self._config.read(file, encoding="utf-8-sig")

    def get(self, section, key):
        return self._config.get(section, key)

    def getint(self, section, key):
        return self._config.getint(section, key)

    def getfloat(self, section, key):
        return self._config.getfloat(section, key)

    def getboolean(self, section, key):
        return self._config.getboolean(section, key)

    def getdict(self, section, options):
        assert isinstance(options, (list, tuple, set))
        d = dict(self._config.items(section))
        if not all( k in d for k in options ):
            raise UserInputException("Incomplete course in section %r, %s must all exist." % (section, options))
        return d

    def getlist(self, section, option, *args, **kwargs):
        v = self.get(section, option, *args, **kwargs)
        return _reCommaSep.split(v)

    def ns_sections(self, ns):
        ns = ns.strip()
        ns_sects = OrderedDict() # { id: str(section) }
        for s in self._config.sections():
            mat = _reNamespacedSection.match(s)
            if mat is None:
                continue
            if mat.group('ns') != ns:
                continue
            id_ = mat.group('id')
            if id_ in ns_sects:
                raise DuplicateSectionError("%s:%s" % (ns, id_))
            ns_sects[id_] = s
        return [ (id_, s) for id_, s in ns_sects.items() ] # [ (id, str(section)) ]


class AutoElectiveConfig(BaseConfig, metaclass=Singleton):

    def __init__(self):
        super().__init__(environ.config_ini or DEFAULT_CONFIG_INI)

    ## Constraints

    ALLOWED_IDENTIFY = ("bzx","bfx")

    ## Model

    # [user]

    @property
    def iaaa_id(self):
        return self.get("user", "student_id")

    @property
    def iaaa_password(self):
        return self.get("user", "password")

    @property
    def is_dual_degree(self):
        return self.getboolean("user", "dual_degree")

    @property
    def identity(self):
        return self.get("user", "identity").lower()

    # [client]

    @property
    def supply_cancel_page(self):
        return self.getint("client", "supply_cancel_page")

    @property
    def refresh_interval(self):
        return self.getfloat("client", "refresh_interval")

    @property
    def refresh_random_deviation(self):
        return self.getfloat("client", "random_deviation")

    @property
    def iaaa_client_timeout(self):
        return self.getfloat("client", "iaaa_client_timeout")

    @property
    def elective_client_timeout(self):
        return self.getfloat("client", "elective_client_timeout")

    @property
    def elective_client_pool_size(self):
        return self.getint("client", "elective_client_pool_size")

    @property
    def elective_client_max_life(self):
        return self.getint("client", "elective_client_max_life")

    @property
    def login_loop_interval(self):
        return self.getfloat("client", "login_loop_interval")

    @property
    def is_print_mutex_rules(self):
        return self.getboolean("client", "print_mutex_rules")

    @property
    def is_debug_print_request(self):
        return self.getboolean("client", "debug_print_request")

    @property
    def is_debug_dump_request(self):
        return self.getboolean("client", "debug_dump_request")

    # [monitor]

    @property
    def monitor_host(self):
        return self.get("monitor", "host")

    @property
    def monitor_port(self):
        return self.getint("monitor", "port")

    # [course]

    @property
    def courses(self):
        cs = OrderedDict()  # { id: Course }
        rcs = {}
        for id_, s in self.ns_sections('course'):
            d = self.getdict(s, ('name','class','school'))
            d.update(class_no=d.pop('class'))
            c = Course(**d)
            cs[id_] = c
            rid = rcs.get(c)
            if rid is not None:
                raise UserInputException("Duplicated courses in sections 'course:%s' and 'course:%s'" % (rid, id_))
            rcs[c] = id_
        return cs

    # [mutex]

    @property
    def mutexes(self):
        ms = OrderedDict()  # { id: Mutex }
        for id_, s in self.ns_sections('mutex'):
            lst = self.getlist(s, 'courses')
            ms[id_] = Mutex(lst)
        return ms

    # [delay]

    @property
    def delays(self):
        ds = OrderedDict()  # { id: Delay }
        cid_id = {} # { cid: id }
        for id_, s in self.ns_sections('delay'):
            cid = self.get(s, 'course')
            threshold = self.getint(s, 'threshold')
            if not threshold > 0:
                raise UserInputException("Invalid threshold %d in 'delay:%s', threshold > 0 must be satisfied" % (threshold, id_))
            id0 = cid_id.get(cid)
            if id0 is not None:
                raise UserInputException("Duplicated delays of 'course:%s' in 'delay:%s' and 'delay:%s'" % (cid, id0, id_))
            cid_id[cid] = id_
            ds[id_] = Delay(cid, threshold)
        return ds

    ## Method

    def check_identify(self, identity):
        limited = self.__class__.ALLOWED_IDENTIFY
        if identity not in limited:
            raise ValueError("unsupported identity %s for elective, identity must be in %s" % (identity, limited))

    def check_supply_cancel_page(self, page):
        if page <= 0:
            raise ValueError("supply_cancel_page must be positive number, not %s" % page)

    def election_validation_errors(self):
        """Return every blocking configuration issue before network access."""
        errors = []
        if not self.iaaa_id.strip():
            errors.append("学号不能为空")
        if not self.iaaa_password.strip():
            errors.append("密码不能为空")

        try:
            self.check_identify(self.identity)
        except ValueError as exc:
            errors.append(str(exc))
        try:
            self.check_supply_cancel_page(self.supply_cancel_page)
        except ValueError as exc:
            errors.append(str(exc))

        deviation = self.refresh_random_deviation
        if not 0 <= deviation < 1:
            errors.append("random_deviation 必须介于 0（含）和 1（不含）之间")
        minimum_interval = self.refresh_interval * (1 - max(0, deviation))
        if not math.isfinite(minimum_interval) or minimum_interval <= 0:
            errors.append("轮询间隔必须是大于 0 的有限数值")
        if not 1 <= self.elective_client_pool_size <= 5:
            errors.append("elective_client_pool_size 必须介于 1 和 5 之间")
        if self.iaaa_client_timeout <= 0 or self.elective_client_timeout <= 0:
            errors.append("客户端超时必须为正数")
        if self.elective_client_max_life != -1 and self.elective_client_max_life <= 0:
            errors.append("elective_client_max_life 必须为 -1 或正数")

        courses = self.courses
        if not courses:
            errors.append("至少需要一门目标课程")
        for course_id, course in courses.items():
            if not course.name.strip():
                errors.append("课程 %s 缺少课程名称" % course_id)
            if not course.school.strip():
                errors.append("课程 %s 缺少开课单位" % course_id)
        for mid, rule in self.mutexes.items():
            if len(set(rule.cids)) < 2 or not set(rule.cids) <= set(courses):
                errors.append("互斥组 %s 需至少两门有效课程" % mid)
        for did, rule in self.delays.items():
            if rule.cid not in courses or rule.threshold <= 0:
                errors.append("名额阈值 %s 必须对应有效课程且为正数" % did)
        return errors

    def get_user_subpath(self):
        identity = "bzx"
        if self.is_dual_degree:
            identity = self.identity
            self.check_identify(identity)
        digest = hashlib.sha256((self.iaaa_id + ":" + identity).encode("utf-8")).hexdigest()
        return "user_%s" % digest[:12]
