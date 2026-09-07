#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from autoelective.cli import create_default_parser
from autoelective.config import AutoElectiveConfig, BaseConfig
from autoelective.logger import redact_sensitive
from autoelective.monitor import config, monitor


class DashboardSafetyTest(unittest.TestCase):

    def setUp(self):
        self.client = monitor.test_client()

    def test_dashboard_is_the_safe_default(self):
        options, _ = create_default_parser().parse_args([])
        self.assertFalse(options.enable_election)

    def test_overview_never_contains_credentials(self):
        response = self.client.get("/api/overview")
        self.assertEqual(response.status_code, 200)
        body = response.get_data()
        self.assertEqual(body.find(config.iaaa_id.encode("utf-8")), -1)
        self.assertEqual(body.find(config.iaaa_password.encode("utf-8")), -1)
        self.assertFalse(response.json["runtime"]["operationEnabled"])

    def test_dashboard_uses_local_security_headers(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        response.close()

    def test_sensitive_log_fields_are_redacted(self):
        message = "GET /login?xh=1234567890&token=secret Cookie: JSESSIONID=abc"
        redacted = redact_sensitive(message)
        self.assertNotIn("1234567890", redacted)
        self.assertNotIn("secret", redacted)
        self.assertIn("[REDACTED]", redacted)


class ConfigurationValidationTest(unittest.TestCase):

    def _config_from_text(self, content):
        handle = tempfile.NamedTemporaryFile("w", suffix=".ini", encoding="utf-8", delete=False)
        self.addCleanup(lambda: os.unlink(handle.name))
        with handle:
            handle.write(content)
        instance = object.__new__(AutoElectiveConfig)
        BaseConfig.__init__(instance, handle.name)
        return instance

    def test_invalid_plan_is_blocked_before_network_access(self):
        candidate = self._config_from_text("""
[user]
student_id = 1234567890
password = local-only
dual_degree = false
identity = bzx
[client]
supply_cancel_page = 1
refresh_interval = 3.25
random_deviation = 0.2
iaaa_client_timeout = 30
elective_client_timeout = 60
elective_client_pool_size = 2
elective_client_max_life = 600
login_loop_interval = 2
print_mutex_rules = true
debug_print_request = false
debug_dump_request = false
[monitor]
host = 127.0.0.1
port = 7074
[course:sample]
name =
class = 1
school = 数学科学学院
""")
        errors = candidate.election_validation_errors()
        self.assertTrue(any("课程名称" in error for error in errors))
        self.assertFalse(any("间隔" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
