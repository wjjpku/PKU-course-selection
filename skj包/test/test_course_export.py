import csv
import io
import unittest
from autoelective.course_export import safe_url, parse_page, search_form, csv_bytes, entry_record, entry_label, BASE, QUERY
from lxml import html


def page(number=1, total=1, next_link=''):
    return '<html><title>课程查询</title><body><table><tr><th>课程号</th><th>课程名</th><th>班号</th><th>学分</th><th>备注</th><th>加入可选列表</th></tr><tr><td>00123</td><td>测试课</td><td>1</td><td>4</td><td>=1+1</td><td><a href="cancelCourse.do">退课</a></td></tr></table>Page %s of %s%s</body></html>' % (number, total, '<a href="%s">Next</a>' % next_link if next_link else '')


class ExportTests(unittest.TestCase):
    def test_query_allowlist(self):
        for link in ('cancelCourse.do', 'addCourse.do', 'javascript:alert(1)', '//other.example/queryCurriculum.jsp'):
            with self.assertRaises(ValueError):
                safe_url(BASE + QUERY, link)
        self.assertEqual(safe_url(BASE + QUERY, 'queryCurriculum.jsp?page=2'), BASE + QUERY + 'queryCurriculum.jsp?page=2')

    def test_extract_fields_without_action(self):
        rows, number, total, link = parse_page(page())
        self.assertEqual(rows[0]['课程号'], '00123')
        self.assertNotIn('加入可选列表', rows[0])
        self.assertIsNone(link)
        self.assertEqual((number, total), (1, 1))

    def test_missing_pagination_is_not_complete(self):
        with self.assertRaises(ValueError):
            parse_page(page(1, 2))
        with self.assertRaises(ValueError):
            parse_page(page().replace('Page 1 of 1', ''))
        with self.assertRaises(ValueError):
            parse_page('<title>系统提示</title>请不要用刷课机')

    def test_next_page(self):
        self.assertEqual(parse_page(page(1, 2, 'queryCurriculum.jsp?page=2'))[3], 'queryCurriculum.jsp?page=2')

    def test_header_excludes_filter_options(self):
        markup = page().replace('<th>备注</th>', '<th>大英级别<select><option>全部</option><option>A</option></select></th>')
        rows = parse_page(markup)[0]
        self.assertIn('大英级别', rows[0])
        self.assertNotIn('大英级别全部A', rows[0])

    def test_csv_bom_quotes_and_formula_safety(self):
        blob = csv_bytes([{'课程号': '00123', '课程名': '测试,课', '备注': '=1+1'}], '2026-09-07', False)
        self.assertTrue(blob.startswith(b'\xef\xbb\xbf'))
        row = list(csv.DictReader(io.StringIO(blob.decode('utf-8-sig'))))[0]
        self.assertEqual(row['课程号'], '00123')
        self.assertEqual(row['课程名'], '测试,课')
        self.assertEqual(row['备注'], "'=1+1")
        self.assertEqual(row['完整性'], '部分结果')

    def test_form_derived_parameters(self):
        markup = '<form action="getCurriculmByForm.do"><input type="hidden" name="token" value="example"><input type="text" name="courseName" value="old"><input type="radio" name="courseSettingType" value="speciality"><select name="deptID"><option value="">请选择</option><option value="00004">物理学院</option><option value="all">全部</option></select></form>'
        action, defaults, name, departments, modes = search_form(markup, BASE + QUERY + 'CourseQueryController.jpf')
        self.assertEqual(departments, [('all', '全部')])
        self.assertEqual(defaults['courseName'], '')
        self.assertEqual(defaults['token'], 'example')
        self.assertEqual(modes, [('courseSettingType', 'speciality', '未识别入口（speciality）')])
        with self.assertRaises(ValueError):
            search_form(markup.replace('getCurriculmByForm.do', 'cancelCourse.do'), BASE + QUERY)

    def test_entry_labels(self):
        for markup in ('<input value="s">专业课', '<label><input value="s">专业课</label>',
                       '<input id="s" value="s"><label for="s">专业课</label>',
                       '<input value="s"><span>专业课</span>'):
            form = html.fromstring('<form>' + markup + '</form>')
            self.assertEqual(entry_label(form.xpath('.//input')[0], form), '专业课')

    def test_entry_is_type_without_losing_school_category(self):
        row = {'课程号': '00123', '课程类别': '任选'}
        professional = entry_record(row, 's', '专业课')
        other = entry_record(row, 'g', '通选课')
        self.assertEqual(professional['课程类型'], '专业课')
        self.assertEqual(professional['课程类别'], '任选')
        self.assertNotEqual(professional, other)
        self.assertNotIn('课程类型', row)
        renamed = entry_record({'课程类型': '学校原值', '查询入口值': '学校标识'}, 's', '专业课')
        self.assertEqual(renamed['课程类型'], '专业课')
        self.assertEqual(renamed['学校原始课程类型'], '学校原值')
        self.assertEqual(renamed['查询入口值'], 's')
        exported = list(csv.DictReader(io.StringIO(csv_bytes([professional, other], 'now', True).decode('utf-8-sig'))))
        self.assertEqual([r['课程类型'] for r in exported], ['专业课', '通选课'])
