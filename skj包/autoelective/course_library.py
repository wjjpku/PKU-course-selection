"""Read the account's exported course snapshot; no school/network operations."""
import csv
import json
import re
from functools import lru_cache
from pathlib import Path
from .schedule import parse_schedule

EXPORT_DIR = Path(__file__).resolve().parents[1] / 'data/exports'


def normalize_record(row):
    def value(*names):
        return next((row[n].strip() for n in names if row.get(n, '').strip()), '')
    number = value('班号', '教学班号')
    credits = value('学分')
    quota = re.fullmatch(r'(\d+)\s*/\s*(\d+)', value('限数/已选'))
    raw_time = value('上课时间及教室', '上课/考试信息', '上课时间', '时间地点', '教室信息')
    exam = value('考试时间')
    if exam:
        raw_time += ' 考试时间：' + exam
    return dict(name=value('课程名', '课程名称'), courseCode=value('课程号', '课程编号'),
                classNo=int(number) if number.isdigit() else None,
                school=value('开课单位', '开课院系'), teacher=value('教师', '授课教师'),
                credits=float(credits) if re.fullmatch(r'\d+(?:\.\d+)?', credits) else None,
                category=value('课程类别'), major=value('专业'), year=value('年级'),
                pnp=value('自选P/NP'), remarks=value('备注'),
                quota=int(quota[1]) if quota else None,
                remaining=max(0, int(quota[1])-int(quota[2])) if quota else None,
                schedule=parse_schedule(raw_time))


@lru_cache(maxsize=4)
def _read_snapshot(path, modified_ns, size):
    if size > 20 * 1024 * 1024:
        raise ValueError('课程库文件过大，请重新导出')
    grouped = {}
    source_rows = 0
    with open(path, encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not {'课程号', '课程名', '班号'}.issubset(reader.fieldnames or []):
            raise ValueError('课程库格式不匹配，请重新导出')
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('课程库行不完整，请重新导出')
            source_rows += 1
            if source_rows > 50000:
                raise ValueError('课程库超过支持的记录数量')
            original = {k: v for k, v in row.items() if k not in ('课程类型', '查询入口值', '查询时间', '完整性')}
            identity = json.dumps(original, ensure_ascii=False, sort_keys=True)
            if identity not in grouped:
                grouped[identity] = dict(normalize_record(row), types=[], entryValues=[], rawRows=[])
            course = grouped[identity]
            label = row.get('课程类型', '').strip() or '入口未记录'
            mode = row.get('查询入口值', '').strip()
            if label not in course['types']:
                course['types'].append(label)
            if mode and mode not in course['entryValues']:
                course['entryValues'].append(mode)
            course['rawRows'].append(row)
    return list(grouped.values()), source_rows


def read_library(metadata, directory=EXPORT_DIR):
    filename = (metadata or {}).get('filename')
    if not filename:
        return dict(courses=[], sourceRows=0, filename=None, complete=False)
    if not re.fullmatch(r'courses-[\w-]+\.csv', filename):
        raise ValueError('课程库文件名不合法')
    directory = Path(directory).resolve()
    path = (directory / filename).resolve()
    if path.parent != directory:
        raise ValueError('课程库文件不在导出目录')
    stat = path.stat()
    try:
        courses, source_rows = _read_snapshot(str(path), stat.st_mtime_ns, stat.st_size)
    except csv.Error as exc:
        raise ValueError('课程库 CSV 格式不正确，请重新导出') from exc
    return dict(courses=courses, sourceRows=source_rows, filename=filename,
                complete=bool(metadata.get('complete')), modifiedAt=stat.st_mtime,
                missingTypes=sum('入口未记录' in c['types'] for c in courses))
