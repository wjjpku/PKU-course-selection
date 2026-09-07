#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# filename: parser.py
# modified: 2019-09-09

import re
from lxml import etree
from .course import Course
from .exceptions import UnexceptedHTMLFormat

_regexBzfxSida = re.compile(r'\?sida=(\S+?)&sttp=(?:bzx|bfx)')


def get_tree_from_response(r):
    return etree.HTML(r.text) # 不要用 r.content, 否则可能会以 latin-1 编码

def get_tree(content):
    return etree.HTML(content)

def get_tables(tree):
    return tree.xpath('.//table//table[@class="datagrid"]')

def get_table_header(table):
    return table.xpath('.//tr[@class="datagrid-header"]/th/text()')

def get_table_trs(table):
    return table.xpath('.//tr[@class="datagrid-odd" or @class="datagrid-even"]')

def get_title(tree):
    title = tree.find('.//head/title')
    if title is None: # 双学位 sso_login 后先到 主修/辅双 选择页，这个页面没有 title 标签
        return None
    return title.text

def get_errInfo(tree):
    tds = tree.xpath(".//table//table//table//td")
    if len(tds) != 1:
        raise UnexceptedHTMLFormat(msg="Unable to locate the elective error message")
    td = tds[0]
    children = td.getchildren()
    if not children:
        raise UnexceptedHTMLFormat(msg="Elective error message has no heading")
    strong = children[0]
    if strong.tag != 'strong' or strong.text not in ('出错提示:', '提示:'):
        raise UnexceptedHTMLFormat(msg="Unknown elective error message heading")
    return "".join(td.xpath('./text()')).strip()

def get_tips(tree):
    tips = tree.xpath('.//td[@id="msgTips"]')
    if len(tips) == 0:
        return None
    td = tips[0].xpath('.//table//table//td')[1]
    return "".join(td.xpath('.//text()')).strip()

def get_sida(r):
    match = _regexBzfxSida.search(r.text)
    if match is None:
        raise UnexceptedHTMLFormat(msg="Unable to parse dual-degree login identifier")
    return match.group(1)

def get_courses(table):
    header = get_table_header(table)
    trs = get_table_trs(table)
    ixs = tuple(map(header.index, ["课程名","班号","开课单位"]))
    cs = []
    for tr in trs:
        t = tr.xpath('./th | ./td')
        name, class_no, school = map(lambda ix: t[ix].xpath('.//text()')[0], ixs)
        c = Course(name, class_no, school)
        cs.append(c)
    return cs

def get_display_tables(tree):
    """Extract text only; never expose or follow action links from school HTML."""
    tables = []
    for table in tree.xpath('.//table'):
        headers = [' '.join(cell.itertext()).strip() for cell in table.xpath('./tr/th | ./thead/tr/th | ./tbody/tr[@class="datagrid-header"]/th | ./tr[@class="datagrid-header"]/td')]
        if not any('课程名' in h or '课程名称' in h for h in headers):
            continue
        rows = []
        for tr in table.xpath('./tr | ./tbody/tr'):
            cells = tr.xpath('./td')
            if len(cells) != len(headers):
                continue
            rows.append([' '.join(' '.join(cell.itertext()).split()) for cell in cells])
        tables.append(dict(headers=headers, rows=rows))
    if not tables:
        raise UnexceptedHTMLFormat(msg='未识别到课程表，不能将此响应认定为没有课程')
    return tables

def get_courses_with_detail(table):
    header = get_table_header(table)
    trs = get_table_trs(table)
    ixs = tuple(map(header.index, ["课程名","班号","开课单位","限数/已选","补选"]))
    cs = []
    for tr in trs:
        t = tr.xpath('./th | ./td')
        name, class_no, school, status, _ = map(lambda ix: t[ix].xpath('.//text()')[0], ixs)
        status = tuple(map(int, status.split("/")))
        href = t[ixs[-1]].xpath('./a/@href')[0]
        c = Course(name, class_no, school, status, href)
        cs.append(c)
    return cs
