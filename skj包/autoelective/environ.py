#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# filename: environ.py
# modified: 2020-02-16

from .utils import Singleton
from collections import defaultdict
from collections import deque
from threading import RLock
import time

class Environ(object, metaclass=Singleton):

    def __init__(self):
        self.config_ini = None
        self.with_monitor = None
        self.iaaa_loop = 0
        self.elective_loop = 0
        self.errors = defaultdict(lambda: 0)
        self.iaaa_loop_thread = None
        self.elective_loop_thread = None
        self.monitor_thread = None
        self.goals = [] # [Course]
        self.ignored = {} # {Course, reason}
        self.phase = "preparation"
        self.operation_enabled = False
        self.started_at = int(time.time())
        self.last_poll_at = None
        self.next_poll_at = None
        self.events = deque(maxlen=200)
        self.lock = RLock()

    def add_event(self, level, message):
        with self.lock:
            self.events.appendleft({
                "timestamp": int(time.time()),
                "level": level,
                "message": message,
            })
