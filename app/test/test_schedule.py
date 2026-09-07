import unittest
from autoelective.schedule import parse_schedule, display_courses


class ScheduleTests(unittest.TestCase):
    def test_live_supplement_time_header(self):
        # Actual supplement-page header and schedule format, no account data.
        tables=[dict(headers=['课程号','课程名','班号','开课单位','上课/考试信息'],
                     rows=[['03835730','美国文化概览','5','英语语言文学系',
                            '1~16周 每周周四3~4节 一教204 考试方式：堂考、论文、或统一时间考试']])]
        schedule=display_courses(tables)[0]['schedule']
        self.assertTrue(schedule['teachingKnown'])
        self.assertEqual(schedule['sessions'],[dict(weeks=list(range(1,17)),day=4,start=3,end=4)])
        self.assertIn('一教204',schedule['raw'])
        self.assertIsNone(schedule['exam'])

    def test_multiple_sessions_and_exam(self):
        s=parse_schedule('1~16周 每周周一1~2节 理教106 1~16周 单周周四1~2节 理教106 考试时间：20270104上午；')
        self.assertTrue(s['teachingKnown'])
        self.assertEqual(len(s['sessions']),2)
        self.assertEqual(s['sessions'][1]['weeks'],list(range(1,17,2)))
        self.assertEqual(s['exam'],{'date':'20270104','period':'上午'})

    def test_even_and_single_week(self):
        self.assertEqual(parse_schedule('2~16周 双周周日3~4节')['sessions'][0]['weeks'],list(range(2,17,2)))
        self.assertEqual(parse_schedule('3周 每周周二2节')['sessions'][0]['weeks'],[3])

    def test_missing_partial_and_invalid_are_unknown(self):
        for text in ('', '时间待定', '每周周一1~2节', '1~16周 每周周一1~2节；周二另行通知', '1~99周 每周周二1~2节'):
            self.assertFalse(parse_schedule(text)['teachingKnown'],text)
        self.assertIsNone(parse_schedule('考试时间：20261399上午')['exam'])

    def test_extra_reordered_columns(self):
        tables=[dict(headers=['自选P/NP','班号','课程名','教师','开课单位','学分','教室信息','课程号','选课结果'],
                     rows=[['可申请','01','测试课程','测试老师','学院','3.0','1~16周 每周周二1~2节','001','已选上']])]
        c=display_courses(tables)[0]
        self.assertEqual(c['courseCode'],'001')
        self.assertEqual(c['credits'],3)
        self.assertEqual(c['classNo'],1)
        self.assertTrue(c['schedule']['teachingKnown'])
