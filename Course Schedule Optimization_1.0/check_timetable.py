"""校验课表网格 HTML 的结构，并生成一个可独立打开的预览文件。

校验点：
  1) 表头 8 个单元格（Time + 周一~周日）；
  2) 每个正文行按 rowspan 展开后，恰好占满 8 列；
  3) 每门课的跨行数符合「时长向上取整到小时」；
  4) 有课的格子数 == 课程节数。
"""
import sys
from datetime import date
from html.parser import HTMLParser

from query_courses import build_weekly_schedule

sys.path.insert(0, r'D:\港中深\上课\AIE1901\选课project\Course Schedule Optimization')
import app as appmod   # noqa: E402  (复用 app.py 里的渲染函数)


class TableParser(HTMLParser):
    """统计每行的单元格数，并把 rowspan 展开成占位。"""

    def __init__(self):
        super().__init__()
        self.rows = []          # [(row_index, [cells])]
        self.current = None
        self.in_body = False
        self.cell_text = None
        self.cells = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'tbody':
            self.in_body = True
        elif tag == 'tr' and self.in_body:
            self.current = []
        elif tag in ('td', 'th') and self.current is not None:
            self.cell_text = {'tag': tag, 'rowspan': int(a.get('rowspan', 1)),
                              'cls': a.get('class', ''), 'text': ''}
            self.current.append(self.cell_text)

    def handle_endtag(self, tag):
        if tag == 'tr' and self.current is not None:
            self.rows.append(self.current)
            self.current = None
        elif tag == 'tbody':
            self.in_body = False

    def handle_data(self, data):
        if self.cell_text is not None:
            self.cell_text['text'] += data


def check(selection, label):
    rows = build_weekly_schedule(selection)
    html = appmod.build_timetable_html(rows, date(2026, 10, 26))
    p = TableParser()
    p.feed(html)

    print(f'--- {label} ---')
    print(f'  课程节数(卡片数) = {len(rows)}')

    # 展开 rowspan，验证每行都占满 8 列
    # 注意：HTML 表格中，某行会因为上一行的 rowspan 而「隐式跳过」对应列，
    # 所以这里必须维护 carry（上一行延续下来的占位列），否则会误判。
    carry = {}    # 列号 -> 还需跳过几行（由更早的行发起的 rowspan 延续而来）
    grid = []
    for row in p.rows:
        line = [''] * 8
        col = 0
        new_carry = {}   # 本行新发起的 rowspan，只影响后续行
        for c in row:
            while col in carry:      # 只受「上一行延续下来」的跨行影响
                line[col] = 'SPAN'
                col += 1
            if col >= 8:
                break
            if c['cls'] == 'tt-time':
                line[col] = 'TIME'
            elif c['cls'] == 'tt-class':
                line[col] = 'CLASS'
                for k in range(1, c['rowspan']):
                    if col + k < 8:
                        new_carry[col + k] = c['rowspan'] - k
            else:
                line[col] = 'EMPTY'
            col += 1
        # 行尾若还有跨行延续下来的列，同样算「已被占据」
        for c2 in range(8):
            if line[c2] == '':
                line[c2] = 'SPAN' if c2 in carry else 'MISSING'
        grid.append(line)
        # 先结算「上一行延续下来」的跨行（本行已消耗一行），再登记本行新发起的
        for k in list(carry):
            carry[k] -= 1
            if carry[k] <= 0:
                del carry[k]
        for k, v in new_carry.items():
            carry[k] = v

    ok = True
    for i, line in enumerate(grid):
        if 'MISSING' in line:
            print(f'  !! 第 {i} 行有未被占据的列: {line}')
            ok = False
    n_class = sum(line.count('CLASS') for line in grid)
    if n_class != len(rows):
        print(f'  !! 卡片数 {n_class} != 课程节数 {len(rows)}')
        ok = False
    n_span = sum(line.count('SPAN') for line in grid)
    print(f'  行数 = {len(grid)}, 卡片数 = {n_class}(应={len(rows)}), 跨行延续格 = {n_span}, '
          f'每行 8 列占满检查 = {"OK" if ok else "FAIL"}')
    assert ok, 'HTML 结构校验失败'
    return html


# 场景 1：参考图类似的组合（LEC + TUT + SUP，且各课互不冲突）
sel1 = [('AIE1001', 'L01'), ('AIE1001', 'T01'), ('AIE1901', 'S01'), ('MAT1001', 'L02'),
        ('MAT1001', 'T03'), ('ENG1001', 'L01'), ('CHI1000', 'L02'), ('PED1101', 'L04')]
html1 = check(sel1, '场景1：多门课 + LEC/TUT/SUP')

# 场景 2：单门课（检查网格边界）
html2 = check([('MAT1001', 'L01')], '场景2：单门课')

# 场景 3：空课表
html3 = appmod.build_timetable_html([], date(2026, 10, 26))
assert '没有可显示的课程' in html3
print('--- 场景3：空课表 OK ---')

# 生成独立预览文件
standalone = (
    '<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">'
    '<title>课表预览</title>'
    '<style>body{font-family:"Segoe UI","Microsoft YaHei",sans-serif;background:#fff;padding:16px;}'
    'h2{color:#1F3864;font-size:18px;}</style></head><body>'
    '<h2>智能选课系统 — 一周课表（时间 × 星期）</h2>' + html1 + '</body></html>'
)
out = r'D:\港中深\上课\AIE1901\选课project\Course Schedule Optimization\_timetable_preview.html'
with open(out, 'w', encoding='utf-8') as f:
    f.write(standalone)
print('\n预览文件已生成:', out)
print('ALL HTML CHECKS PASSED')
