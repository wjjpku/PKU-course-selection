"""Bounded read-only course-query export. Never follow course action/detail links."""
import csv
import io
import json
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from lxml import html

BASE = 'https://elective.pku.edu.cn'
QUERY = '/elective2008/edu/pku/stu/elective/controller/courseQuery/'
ALLOWED = {QUERY + 'CourseQueryController.jpf', QUERY + 'getCurriculmByForm.do', QUERY + 'queryCurriculum.jsp'}
ACTION_COLUMNS = {'加入可选列表', '加入选课计划', '操作', '补选', '退课'}


def safe_url(base, link):
    url = urljoin(base, link)
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.netloc != 'elective.pku.edu.cn' or parts.path.split(';')[0] not in ALLOWED:
        raise ValueError('非查询地址，已拒绝访问')
    return url


def parse_page(text):
    tree = html.fromstring(text)
    if '课程查询' not in ''.join(tree.xpath('//title/text()')):
        raise ValueError('学校未返回课程查询页；可能会话失效或访问受限，已停止')
    records = []
    found = False
    for table in tree.xpath('//table'):
        heads = table.xpath('./tr/th | ./thead/tr/th | ./tbody/tr/th')
        headers = [' '.join(''.join(h.xpath('.//text()[not(ancestor::select) and not(ancestor::script)]')).split()) for h in heads]
        if not {'课程号', '课程名', '班号', '学分'}.issubset(headers):
            continue
        found = True
        for row in table.xpath('./tr | ./tbody/tr'):
            cells = row.xpath('./td')
            if len(cells) != len(headers):
                continue
            values = [' '.join(' '.join(c.itertext()).split()) for c in cells]
            record = {h: v for h, v in zip(headers, values) if h not in ACTION_COLUMNS}
            if record.get('课程号', '').isdigit():
                records.append(record)
    if not found:
        raise ValueError('未识别课程表，不能视为空列表')
    body = ' '.join(tree.xpath('//body//text()[not(ancestor::script) and not(ancestor::style)]'))
    if re.search('请不要用刷课机|访问过于频繁|禁止刷课', body):
        raise ValueError('学校返回访问限制，已停止查询')
    paging = re.search(r'Page\s+(\d+)\s+of\s+(\d+)', body)
    if not paging and not re.search(r'No data to display', body, re.I):
        raise ValueError('未识别分页总数，不能保证结果完整')
    next_links = tree.xpath('//a[normalize-space(.)="Next"]/@href')
    page, total = (int(paging[1]), int(paging[2])) if paging else (1, 1)
    if page < total and len(next_links) != 1:
        raise ValueError('缺少下一页查询链接')
    return records, page, total, next_links[0] if page < total else None


def entry_label(radio, form):
    """Read the query entry's displayed name, never infer it from course rows."""
    labels = form.xpath('.//label[@for=$id]', id=radio.get('id', '')) if radio.get('id') else []
    if not labels:
        labels = radio.xpath('ancestor::label[1]')
    text = ' '.join(labels[0].itertext()) if labels else (radio.tail or '')
    if not text.strip():
        sibling = radio.getnext()
        if sibling is not None and sibling.tag in ('span', 'font') and not sibling.xpath('.//input'):
            text = ' '.join(sibling.itertext())
    return ' '.join(text.split()).strip('：:') or '未识别入口（%s）' % radio.get('value', '')


def entry_record(row, mode, label):
    # The same school row under different entries remains separate provenance.
    original = {('学校原始课程类型' if k == '课程类型' else '学校原始查询入口值' if k == '查询入口值' else k): v
                for k, v in row.items()}
    return {'课程类型': label, '查询入口值': mode, **original}


def search_form(text, url):
    tree = html.fromstring(text)
    forms = tree.xpath('//form')
    for form in forms:
        action = urljoin(url, form.get('action', ''))
        if urlsplit(action).path != QUERY + 'getCurriculmByForm.do':
            continue
        safe_url(url, action)
        data = {}
        for el in form.xpath('.//input[@name]'):
            kind = el.get('type', 'text').lower()
            if kind in ('hidden', 'text'):
                data[el.get('name')] = el.get('value', '') if kind == 'hidden' else ''
        departments = []
        for select in form.xpath('.//select[@name]'):
            name = select.get('name')
            if 'deptID' in name:
                departments = [(o.get('value'), ''.join(o.itertext()).strip()) for o in select.xpath('./option')
                               if o.get('value') and ''.join(o.itertext()).strip() not in ('请选择', '')]
                all_depts = [d for d in departments if d[1] == '全部']
                if all_depts:
                    departments = all_depts
                dept_name = name
            else:
                data[name] = ''
        modes = [(r.get('name'), r.get('value'), entry_label(r, form)) for r in form.xpath('.//input[@type="radio"]')
                 if 'courseSettingType' in r.get('name', '') and r.get('value')]
        if not departments or not modes:
            raise ValueError('未识别院系或课程分类筛选，不猜测全量查询参数')
        return action, data, dept_name, departments, list(dict.fromkeys(modes))
    raise ValueError('未识别学校的课程搜索表单')


def csv_bytes(records, captured_at, complete):
    headers = list(dict.fromkeys(key for row in records for key in row))
    headers += ['查询时间', '完整性']
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(headers)
    def cell(value):
        value = str(value)
        return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value
    for row in records:
        writer.writerow([cell(row.get(h, '')) for h in headers[:-2]] + [captured_at, '完整（当前账号可查询范围）' if complete else '部分结果'])
    return output.getvalue().encode('utf-8-sig')


def export_courses(worker, cfg):
    from .control import Cancelled
    worker.export = dict(status='running', pages=0, rows=0, scope='当前学期、当前账号可查询的分类列表字段', message='读取查询表单', filename=None)
    records, seen, visits = [], set(), 0
    last_request = 0
    def fetch(url, data=None):
        nonlocal last_request, visits
        safe_url(BASE, url)
        if visits >= 300:
            raise ValueError('已达到单次 300 页请求上限，保留部分结果')
        while time.monotonic() - last_request < 4:
            worker.checkpoint()
            worker.stop_event.wait(.1)
        worker.checkpoint()
        visits += 1
        response = worker.call(worker.client._post if data is not None else worker.client._get,
                               url, **({'data': data} if data is not None else {}),
                               allow_redirects=False,
                               headers={'Referer': BASE + QUERY + 'CourseQueryController.jpf'})
        last_request = time.monotonic()
        response.raise_for_status()
        if 300 <= response.status_code < 400:
            raise ValueError('查询返回跳转，可能登录失效，已停止；请重新登录后查询')
        safe_url(BASE, response.url)
        # requests sometimes guesses Latin-1 for the UTF-8 school pages.
        response.encoding = 'utf-8'
        return response
    complete = False
    try:
        initial = fetch(BASE + QUERY + 'CourseQueryController.jpf')
        action, defaults, dept_name, departments, modes = search_form(initial.text, initial.url)
        worker.export['groupsTotal'] = len(departments) * len(modes)
        worker.export['groupsDone'] = 0
        for department, label in departments:
            for mode_name, mode, mode_label in modes:
                params = dict(defaults)
                params.update({dept_name: department, 'deptIdHide': department, mode_name: mode})
                worker.export['message'] = '查询 %s / %s' % (label, mode_label)
                response = fetch(action, params)
                expected_page = 1
                total_pages = None
                while True:
                    rows, page, total, next_link = parse_page(response.text)
                    if page != expected_page or (total_pages is not None and total != total_pages):
                        raise ValueError('分页发生变化或重复，不能保证完整性')
                    total_pages = total
                    for row in rows:
                        row = entry_record(row, mode, mode_label)
                        # Preserve differing year/major/time rows rather than collapse by code.
                        identity = json.dumps(row, sort_keys=True, ensure_ascii=False)
                        if identity not in seen:
                            seen.add(identity)
                            records.append(row)
                    worker.export.update(pages=worker.export['pages'] + 1, rows=len(records))
                    if not next_link:
                        break
                    expected_page += 1
                    response = fetch(safe_url(response.url, next_link))
                worker.export['groupsDone'] += 1
        complete = True
        worker.export.update(status='completed', message='分类与分页读取完成；不含课程大纲等详情页，也不保证后续余量不变')
    except Cancelled:
        worker.export.update(status='cancelled', message='用户已停止，保留已读取部分')
    except Exception as exc:
        from .logger import redact_sensitive
        worker.export.update(status='failed', message=redact_sensitive(str(exc)))
    finally:
        directory = Path(__file__).resolve().parents[1] / 'data/exports'
        directory.mkdir(parents=True, exist_ok=True)
        if records or complete:
            filename = time.strftime('courses-%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8] + ('' if complete else '-partial') + '.csv'
            path = directory / filename
            path.write_bytes(csv_bytes(records, time.strftime('%Y-%m-%d %H:%M:%S %z'), complete))
            worker.export['filename'] = filename
        worker.export['complete'] = complete
        worker.export['rows'] = len(records)
        if hasattr(worker, 'export_sink'):
            worker.export_sink(worker.export)
