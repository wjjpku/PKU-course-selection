import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from autoelective.course_export import csv_bytes
from autoelective.course_library import read_library, normalize_record


class LibraryTests(unittest.TestCase):
    def row(self, **extra):
        return {'课程号': '00123', '课程名': '测试课', '班号': '01', '开课单位': '物理学院',
                '课程类别': '任选', '学分': '4', '年级': '2025',
                '上课时间及教室': '1~16周 单周周一1~2节 理教101', '限数/已选': '10 / 8', **extra}

    def test_raw_schedule_quota_and_unknowns(self):
        course = normalize_record(self.row())
        self.assertEqual(course['courseCode'], '00123')
        self.assertEqual(course['remaining'], 2)
        self.assertTrue(course['schedule']['teachingKnown'])
        unknown = normalize_record({'课程名': '无时间课', '限数/已选': '未知'})
        self.assertIsNone(unknown['remaining'])
        self.assertIsNone(unknown['classNo'])
        self.assertFalse(unknown['schedule']['teachingKnown'])

    def test_entry_merge_keeps_original_rows_and_different_years(self):
        rows = [self.row(课程类型='专业课', 查询入口值='s'), self.row(课程类型='通选课', 查询入口值='g'), self.row(年级='2026')]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'courses-test.csv'
            path.write_bytes(csv_bytes(rows, '2026-09-07', False))
            result = read_library({'filename': path.name, 'complete': False}, folder)
        self.assertEqual(result['sourceRows'], 3)
        self.assertEqual(len(result['courses']), 2)
        self.assertEqual(result['courses'][0]['types'], ['专业课', '通选课'])
        self.assertEqual(len(result['courses'][0]['rawRows']), 2)
        self.assertEqual(result['courses'][1]['types'], ['入口未记录'])
        self.assertFalse(result['complete'])

    def test_missing_snapshot_and_path_rejection(self):
        self.assertIsNone(normalize_record(self.row())['term'])
        self.assertEqual(normalize_record(self.row(学期='2026秋'))['term'],'2026秋')
        self.assertEqual(read_library(None)['courses'], [])
        for filename in ('../config.ini', '/tmp/courses-test.csv', 'config.ini'):
            with self.assertRaises(ValueError):
                read_library({'filename': filename})

    def test_library_api_is_read_only_and_host_guarded(self):
        from autoelective.monitor import monitor, controller, manager
        with patch.object(manager, 'store', None), patch.object(controller, 'export', {}), patch.object(controller, 'command') as command:
            client = monitor.test_client()
            response = client.get('/api/course-library')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['courses'], [])
            self.assertNotIn('password', response.json)
            self.assertEqual(client.get('/api/course-library', headers={'Host': 'other.example'}).status_code, 403)
            command.assert_not_called()

    def test_failed_refresh_keeps_last_library_after_restart(self):
        from autoelective.task_store import TaskStore
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.sqlite3'
            store = TaskStore(path)
            store.save_export({'filename': 'courses-previous.csv', 'complete': True})
            store.save_export({'filename': None, 'status': 'failed', 'complete': False})
            self.assertIsNone(store.load_export()['filename'])
            self.assertEqual(store.load_library_export()['filename'], 'courses-previous.csv')
            store.db.close()
            restored = TaskStore(path)
            self.assertEqual(restored.load_library_export()['filename'], 'courses-previous.csv')
            restored.db.close()
