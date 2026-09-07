"""Conservative display-only timetable parser. Never used to submit courses."""
import re
from datetime import datetime

SESSION = re.compile(r'(\d{1,2})(?:\s*[~～\-至]\s*(\d{1,2}))?\s*周\s*(每周|单周|双周)\s*周([一二三四五六日天])\s*(\d{1,2})(?:\s*[~～\-至]\s*(\d{1,2}))?\s*节')


def parse_schedule(text):
    text = str(text or '').strip()
    sessions = []
    warnings = []
    for match in SESSION.finditer(text):
        first, last, parity, day, start, end = match.groups()
        first, last, start, end = int(first), int(last or first), int(start), int(end or start)
        if not (1 <= first <= last <= 32 and 1 <= start <= end <= 12):
            warnings.append('教学周或节次超出支持范围')
            continue
        weeks = [w for w in range(first, last + 1) if parity == '每周' or w % 2 == (1 if parity == '单周' else 0)]
        sessions.append(dict(weeks=weeks, day='一二三四五六日'.index('日' if day == '天' else day) + 1,
                             start=start, end=end))
    teaching = re.split(r'考试(?:时间|方式)', text)[0]
    occurrences = len(re.findall(r'周[一二三四五六日天]', teaching))
    known = bool(sessions) and occurrences == len(sessions) and teaching.count('节') == len(sessions) and not warnings and not re.search(r'待定|另行|自主', teaching)
    if not known:
        warnings.append('上课时间缺失或含未识别格式，请核对原文')
    exam_match = re.search(r'考试时间\s*[:：]\s*(\d{8})\s*(上午|下午|晚上)', text)
    exam = dict(date=exam_match[1], period=exam_match[2]) if exam_match else None
    if exam:
        try:
            datetime.strptime(exam['date'], '%Y%m%d')
        except ValueError:
            exam = None
    return dict(sessions=sessions, teachingKnown=known, exam=exam, warnings=warnings, raw=text)


def display_courses(tables):
    """Map header names, tolerate extra/reordered columns, retain raw schedule."""
    result = []
    for table in tables:
        headers = [h.strip() for h in table['headers']]
        def value(row, *names):
            for name in names:
                if name in headers:
                    return row[headers.index(name)].strip()
            return ''
        for row in table['rows']:
            name = value(row, '课程名', '课程名称')
            if not name:
                continue
            class_no = value(row, '班号', '教学班号')
            if not class_no.isdigit():
                continue
            time_text = value(row, '上课/考试信息', '教室信息', '上课时间', '时间地点', '上课时间地点')
            exam_text = value(row, '考试时间')
            raw = time_text + (' 考试时间：' + exam_text if exam_text else '')
            credits = value(row, '学分')
            result.append(dict(name=name, classNo=int(class_no), school=value(row, '开课单位', '开课院系'),
                courseCode=value(row, '课程号', '课程编号'), teacher=value(row, '教师', '授课教师'),
                credits=float(credits) if re.fullmatch(r'\d+(?:\.\d+)?', credits) else None,
                category=value(row, '课程类别', '课程类型'), result=value(row, '选课结果', '状态'),
                schedule=parse_schedule(raw)))
    return result
