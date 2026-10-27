"""智能选课系统 —— 基于 Streamlit + SQLite 的前端。

工作流：
  ① 左侧边栏：st.multiselect 多选课程；
  ② 左侧边栏：为每门课的每个 component（讲座/辅导/督导…）动态生成 selectbox 选区段；
  ③ 右侧主面板：点击「生成一周课表」→ 硬性约束校验（必修课 / 学分 12–18 / 时间冲突）→
     通过则展示按星期+时间排序的一周课表，否则用 st.error 指明原因。

说明：本系统只做硬性约束校验，不接入任何 LLM。
"""
import math
import sys
from datetime import date, timedelta
from html import escape
from pathlib import Path

import streamlit as st
import pandas as pd

# ---------------------------------------------------------------------------
# 稳健导入 query_courses：强制使用「与 app.py 同目录」的那一份。
#
# 为什么会报 ImportError: cannot import name 'get_course_components'？
#   1) 从别的目录启动 streamlit 时（例如 streamlit run "…/Course Schedule
#      Optimization/app.py"，或 python -m streamlit），Python 可能在 sys.path
#      里先找到另一个同名的 query_courses.py（例如备份目录 protect/ 里的旧版），
#      于是导入了「没有新函数」的旧模块。
#   2) 服务进程在旧版 query_courses.py 还在时就已启动，sys.modules 里缓存着旧
#      模块对象；之后即使改了文件，热重载 app.py 时 import 仍然拿旧模块 → 报同样的错。
#
# 处理办法：
#   - 把 app.py 所在目录插到 sys.path 最前面，保证优先级最高；
#   - 丢掉 sys.modules 里可能缓存的旧模块，让本次运行重新从磁盘加载最新代码。
# 这样即使从任意目录启动、甚至只是点一下浏览器里的「Rerun」，也能拿到正确的模块。
# ---------------------------------------------------------------------------
_APP_DIR = str(Path(__file__).resolve().parent)
if _APP_DIR in sys.path:
    sys.path.remove(_APP_DIR)
sys.path.insert(0, _APP_DIR)
sys.modules.pop('query_courses', None)   # 丢弃可能缓存的旧版本

try:
    from query_courses import (
        get_all_course_codes,
        get_course_components,
        get_sections_by_component,
        total_credits,
        check_conflicts_multi,
        build_weekly_schedule,
        COMPONENT_LABEL,
    )
except ImportError as exc:
    st.error(
        f'导入 query_courses 失败：{exc}\n\n'
        f'请确认 query_courses.py 与 app.py 位于同一目录，且 query_courses.py 中已包含 '
        f'get_course_components / total_credits / check_conflicts_multi / build_weekly_schedule 等函数。'
    )
    st.stop()

# ----------------------------- 配置 -----------------------------
# 大一人工智能专业必修课（固定部分）
REQUIRED_FIXED = ['AIE1001', 'AIE1901', 'MAT1001', 'ENG1001', 'CHI1000']
# 体育课：PED1101–PED1123 中任选一门
REQUIRED_PED_PREFIX = 'PED11'
CREDIT_MIN, CREDIT_MAX = 12, 18


def comp_label(comp: str) -> str:
    """component 的中文友好名，未知类型回退为原始代码。"""
    return COMPONENT_LABEL.get(comp, comp)


# ----------------------------- 课表网格样式 -----------------------------
# 仿照「时间轴 × 星期」的经典课表：左侧时间列，上方星期表头，
# 有课的格子显示绿色卡片（课程-区段 / 类型 / 上课时间 / 教室），没课的格子是淡黄色。
WEEKDAY_EN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONTH_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
TYPE_EN = {
    'LEC': 'Lecture', 'TUT': 'Tutorial', 'SUP': 'Supervision', 'LAB': 'Laboratory',
    'SEM': 'Seminar', 'REC': 'Recitation', 'DIS': 'Discussion', 'PRJ': 'Project',
    'STU': 'Studio', 'IND': 'Independent Study', 'FLD': 'Fieldwork', 'CLN': 'Clinic',
}

TIMETABLE_CSS = """
<style>
.tt-wrap { width: 100%; overflow-x: auto; }
table.tt { border-collapse: collapse; width: 100%; table-layout: fixed;
           font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif; }
table.tt th, table.tt td { border: 1px solid #B4C6E7; }
table.tt th.tt-head { background: #D9D9D9; color: #1F3864; font-weight: 700;
                      font-size: 13px; padding: 6px 2px; text-align: center; line-height: 1.3; }
table.tt th.tt-head-time { width: 52px; background: #D9D9D9; color: #1F3864;
                           font-size: 12px; font-weight: 700; text-align: center; }
table.tt td.tt-time { background: #FFFFFF; color: #1F3864; font-size: 12px;
                      text-align: center; height: 36px; }
table.tt td.tt-slot { background: #FFFCDB; height: 36px; }
table.tt td.tt-class { background: #C3D69B; color: #1F3864; font-size: 12px; font-weight: 700;
                       text-align: center; vertical-align: middle; line-height: 1.35;
                       padding: 4px 2px; }
table.tt td.tt-class .tt-code { font-size: 13px; }
</style>
"""


def _to_min(t: str) -> int:
    """'HH:MM' → 距离 00:00 的分钟数。"""
    h, m = str(t).split(':')
    return int(h) * 60 + int(m)


def _hhmm(mins: int) -> str:
    """分钟数 → 'HH:MM'。"""
    return f'{mins // 60:02d}:{mins % 60:02d}'


def build_timetable_html(rows, week_monday: date) -> str:
    """
    把课表行渲染成「时间 × 星期」的 HTML 网格。

    排版规则（与参考课表一致）：
      - 时间轴以 1 小时为一行，从最早课的半小时对齐点开始；
      - 每门课放进「开始时间所在的那一行」，并按自身时长向上跨行
        （如 10:30-11:50 跨 2 行，09:00-11:50 跨 3 行）；
      - 有课 → 绿色卡片；没课 → 淡黄色空格。
    """
    if not rows:
        return '<p style="color:#888;">没有可显示的课程。</p>'

    # ---- 1. 时间轴范围 ----
    starts = [_to_min(r['开始']) for r in rows]
    ends = [_to_min(r['结束']) for r in rows]
    grid_start = (min(starts) // 30) * 30          # 向下取整到半小时
    grid_end = ((max(ends) // 30) + 1) * 30        # 向上取整到半小时
    n_rows = max(1, math.ceil((grid_end - grid_start) / 60))

    # ---- 2. 放置课程卡片（含跨行）----
    placed = {}    # (行号, 星期) -> html
    occupied = set()   # 已被上方卡片跨行占用的 (行号, 星期)

    for r in sorted(rows, key=lambda x: (x['weekday'], _to_min(x['开始']))):
        st_min, et_min = _to_min(r['开始']), _to_min(r['结束'])
        row = (st_min - grid_start) // 60
        span = max(1, math.ceil((et_min - st_min) / 60))   # 按时长跨行
        wd = r['weekday']

        # 若目标位置已被别的卡片占用（理论上不会，因为已做过冲突校验），往下顺延
        while row < n_rows and ((row, wd) in placed or (row, wd) in occupied):
            row += 1
        if row >= n_rows:
            continue
        span = min(span, n_rows - row)

        type_en = TYPE_EN.get(r['类型'], r['类型'])
        # 用 % 格式化而非嵌套 f-string，兼容 Python 3.8+
        code = escape(str(r['课程代码']))
        section = escape(str(r['区段']))
        time_range = escape('{} - {}'.format(r['开始'], r['结束']))
        room = escape(str(r['教室']))
        placed[(row, wd)] = (
            '<td class="tt-class" rowspan="%d">' % span
            + '<div class="tt-code">%s - %s</div>' % (code, section)
            + '<div>%s</div>' % escape(type_en)
            + '<div>%s</div>' % time_range
            + '<div>%s</div>' % room
            + '</td>'
        )
        for k in range(1, span):
            occupied.add((row + k, wd))

    # ---- 3. 组装表头 ----
    head = ['<th class="tt-head-time">Time</th>']
    for i in range(7):
        d = week_monday + timedelta(days=i)
        head.append(f'<th class="tt-head">{WEEKDAY_EN[i]}<br>{MONTH_EN[d.month - 1]} {d.day}</th>')

    # ---- 4. 组装每一行 ----
    body = []
    for row in range(n_rows):
        t = grid_start + row * 60
        cells = [f'<td class="tt-time">{_hhmm(t)}</td>']
        for wd in range(1, 8):
            if (row, wd) in occupied:
                continue                       # 已被上方卡片合并
            if (row, wd) in placed:
                cells.append(placed[(row, wd)])
            else:
                cells.append('<td class="tt-slot"></td>')
        body.append('<tr>' + ''.join(cells) + '</tr>')

    return (
        TIMETABLE_CSS
        + '<div class="tt-wrap"><table class="tt"><thead><tr>'
        + ''.join(head)
        + '</tr></thead><tbody>'
        + ''.join(body)
        + '</tbody></table></div>'
    )


def render_html(html: str):
    """优先用 st.html（支持 <style>），旧版本 Streamlit 则退回 markdown。"""
    if hasattr(st, 'html'):
        st.html(html)
    else:
        st.markdown(html, unsafe_allow_html=True)


# ----------------------------- 页面 -----------------------------
st.set_page_config(page_title='智能选课系统', page_icon='📅', layout='wide')
st.title('📅 智能选课系统')
st.caption('硬性约束校验：必修课 · 学分 12–18 · 时间冲突')

# 读取课程列表（数据库读取失败时优雅报错）
try:
    all_courses = get_all_course_codes()
except Exception as e:
    st.error(f'读取数据库失败，请确认本文件与 freshman_term1_2026_2027.sqlite 在同一目录。错误信息：{e}')
    st.stop()

# ================= 左侧边栏：选课 =================
with st.sidebar:
    st.header('① 选择课程')
    selected_courses = st.multiselect('选择要修读的课程（可多选）', all_courses, key='courses')

    selections = []   # [(course_code, section_code), ...] 已选定的区段
    missing = []      # [(course_code, component), ...] 尚未选完的区段

    if selected_courses:
        st.header('② 选择区段')
        st.caption('每门课的每种类型（讲座 / 辅导 / 督导）都需选一个区段；关闭的区段也会列出并标注。')
        for code in selected_courses:
            for comp in get_course_components(code):
                opts = get_sections_by_component(code, comp)
                option_labels = [
                    f"{o['section_code']}  ·  {'开放' if o['status'] == '开放' else '关闭'}"
                    for o in opts
                ]
                choice = st.selectbox(
                    f'{code} · {comp_label(comp)} ({comp})',
                    ['— 请选择 —'] + option_labels,
                    key=f'sel_{code}_{comp}',
                )
                if choice != '— 请选择 —':
                    sec = choice.split('  ·  ')[0].strip()
                    selections.append((code, sec))
                else:
                    missing.append((code, comp))

    st.header('③ 显示周')
    st.caption('选择该周任意一天即可（课表按整周绘制）。')
    picked_date = st.date_input('周起始（选该周任意一天）', value=date.today(), key='week_date')
    week_monday = picked_date - timedelta(days=picked_date.weekday())   # 对齐到周一

# ================= 右侧主面板：生成课表 =================
st.header('③ 生成课表')
st.write('选好课程与区段后，点击按钮进行硬性约束校验并生成一周课表。')

# 当前已选预览（便于在生成前确认）
with st.expander('当前已选区段预览', expanded=False):
    if selections:
        for code, sec in selections:
            st.write(f'- {code} · {sec}')
    else:
        st.write('（尚未选择任何区段）')

if st.button('生成一周课表', type='primary', width='stretch', key='gen_btn'):
    errors = []
    conflict_lines = []

    # 1) 区段是否选全
    if missing:
        miss_txt = '、'.join(f'{c} 的 {comp_label(comp)}' for c, comp in missing)
        errors.append(f'⚠️ 以下课程的区段尚未选完：{miss_txt}')

    # 2) 必修课（固定 5 门 + 体育课任选一门）
    missing_required = [c for c in REQUIRED_FIXED if c not in selected_courses]
    ped_ok = any(c.startswith(REQUIRED_PED_PREFIX) for c in selected_courses)
    if missing_required:
        errors.append(f'❌ 缺少必修课：{", ".join(missing_required)}')
    if not ped_ok:
        errors.append('❌ 缺少体育课：请在 PED1101–PED1123 中至少选一门')

    # 3) 学分区间 12–18
    total = total_credits(selected_courses)
    if total < CREDIT_MIN or total > CREDIT_MAX:
        errors.append(f'❌ 总学分 {total:.1f} 不在 12–18 区间内（需 {CREDIT_MIN}–{CREDIT_MAX}）')

    # 4) 时间冲突（仅当所有区段都选齐时才校验，否则无意义）
    conflict_flag = False
    if not missing:
        conflicts = check_conflicts_multi(selections)
        if conflicts:
            conflict_flag = True
            for c in conflicts:
                conflict_lines.append(
                    f'{c["course_a"]} {c["section_a"]}（{c["time_a"]}）与 '
                    f'{c["course_b"]} {c["section_b"]}（{c["time_b"]}）在星期{c["weekday"]}冲突'
                )

    # ----------------- 结果展示 -----------------
    if errors or conflict_flag:
        for e in errors:
            st.error(e)
        if conflict_flag:
            st.error('❌ 存在时间冲突：')
            for line in conflict_lines:
                st.write(f'  - {line}')
    else:
        st.success(
            f'✅ 校验通过！共 {len(selected_courses)} 门课，'
            f'总学分 {total:.1f}（区间 {CREDIT_MIN}–{CREDIT_MAX}）。'
        )
        rows = build_weekly_schedule(selections)

        # ---- 主展示：时间 × 星期的网格课表 ----
        st.subheader(f'一周课表（{week_monday.strftime("%Y-%m-%d")} 当周）')
        render_html(build_timetable_html(rows, week_monday))

        # ---- 次要展示：文本明细表 ----
        with st.expander('明细列表（文本版）', expanded=False):
            df = pd.DataFrame(rows)
            col_order = ['星期', '开始', '结束', '课程代码', '课程名称', '区段', '类型', '教室']
            st.dataframe(df[col_order], width='stretch', hide_index=True)

        st.metric('总学分', f'{total:.1f} / {CREDIT_MAX}')
