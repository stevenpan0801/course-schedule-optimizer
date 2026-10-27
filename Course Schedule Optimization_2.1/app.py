"""Run with python -m streamlit run app.py."""
from datetime import date, timedelta, time
from dataclasses import asdict
import hashlib
import json
import pandas as pd
import streamlit as st
from model import DB, Preferences, load_catalog
from optimizer import solve
from checker import check
from timetable import DAYS, weekly_rows, render, hhmm

st.set_page_config(page_title='选课规划', page_icon='📅', layout='wide')
st.markdown('''<style>
.block-container{max-width:1440px;padding-top:2rem}
h1{letter-spacing:-.04em} [data-testid="stMetricValue"]{font-size:1.65rem}
[data-testid="stSidebar"]{border-right:1px solid #dce5eb}
.stDownloadButton button{width:100%}
</style>''', unsafe_allow_html=True)
st.title('选课规划')
st.caption('2026–27 · 第一学期　 /　选课程 → 设置偏好 → 比较与调整')
try:
    cat = load_catalog()
except Exception as exc:
    st.error(f'无法读取课程数据：{exc}')
    st.stop()

with st.sidebar:
    st.header('本学期课程')
    codes = st.multiselect('选择要修的课程', sorted(cat.courses),
        format_func=lambda c: f"{c} · {cat.courses[c]['name']}", key='courses')
    credits = sum(cat.courses[c]['credits'] for c in codes)
    st.metric('已选学分', f'{credits:g}', help='每门已选课程都必须安排，总学分须为 12–18。')
    if not codes:
        st.info('先选课程，建议从你的必修课开始。')
    elif credits < 12:
        st.warning(f'还需至少 {12-credits:g} 学分。')
    elif credits > 18:
        st.warning(f'超出上限 {credits-18:g} 学分，请减少课程。')
    else:
        st.caption(f'已选 {len(codes)} 门 · 符合 12–18 学分要求')
    with st.expander('搜索设置与使用说明'):
        timeout = st.number_input('最长搜索时间（秒）', 1, 120, 15, key='timeout')
        st.caption('超时后可增加搜索时间再试。评分只用于比较同一次设置下的推荐方案。')
        st.caption('尚不能验证 Lecture / Tutorial 绑定与个人先修记录，选课前请核对 SIS。')

with st.expander('排课偏好与不可用时间', expanded=True):
    time_tab, teacher_tab = st.tabs(['时间安排', '教师偏好'])
    with time_tab:
        left, right = st.columns(2)
        with left:
            early_mode = st.selectbox('08:30 早八', ['无偏好', '尽量避免', '优先安排', '禁止安排'], key='early_mode')
            early = {'尽量避免': 0, '优先安排': 5}.get(early_mode)
            ban_early = early_mode == '禁止安排'
        with right:
            banned = st.multiselect('整天不可用', range(1, 8), format_func=lambda d: DAYS[d-1], key='banned_days')
        weekdays = {}
        with st.expander('每周排课喜好（可选）'):
            days = st.multiselect('要设置喜好的星期', [d for d in range(1, 8) if d not in banned],
                format_func=lambda d: DAYS[d-1], key='rated_days')
            cols = st.columns(3)
            for i, d in enumerate(days):
                weekdays[d] = cols[i % 3].slider(DAYS[d-1], 0, 5, 0, key=f'day_{d}')
            st.caption('0 = 尽量少排，5 = 尽量多排；想完全空出一天，请用“整天不可用”。')
        with st.expander('添加每周不可用时段（可选）'):
            st.caption('例如社团活动、固定会议。完全相同的时段会自动去重。')
            # Editable rows allow adding/removing periods without a separate quantity control.
            frame = st.data_editor(pd.DataFrame(columns=['星期', '开始', '结束']), num_rows='dynamic',
                hide_index=True, key='blocked_editor', column_config={
                    '星期': st.column_config.SelectboxColumn('星期', options=DAYS, required=True),
                    '开始': st.column_config.TimeColumn('开始', format='HH:mm', required=True),
                    '结束': st.column_config.TimeColumn('结束', format='HH:mm', required=True)})
            blocked = []
            bad_block = False
            for _, row in frame.iterrows():
                d, a, b = row['星期'], row['开始'], row['结束']
                try:
                    a = time.fromisoformat(a) if isinstance(a, str) else a
                    b = time.fromisoformat(b) if isinstance(b, str) else b
                except ValueError:
                    bad_block = True
                    continue
                if d not in DAYS or not isinstance(a, time) or not isinstance(b, time) or a >= b:
                    bad_block = True
                    continue
                blocked.append((DAYS.index(d)+1, a.hour*60+a.minute, b.hour*60+b.minute))
            blocked = sorted(set(blocked))
            if bad_block:
                st.error('请补全每行的星期和时间，且结束时间须晚于开始时间；不用的行请删除。')
    with teacher_tab:
        teachers = {}
        if not codes:
            st.info('选择课程后，即可搜索并评价对应教师。')
        for code in codes:
            names = sorted({t for s in cat.sections[code] for t in s.teachers})
            selected = st.multiselect(f"{code} · {cat.courses[code]['name']}", names, key=f'teachers_{code}')
            if selected:
                teachers[code] = {t: st.slider(f'{code} · {t}', 0, 5, 5, key=f'teacher_{code}_{t}') for t in selected}
        st.caption('0 = 最不喜欢，5 = 最喜欢；未评分教师按中性处理，未设置的课程不参与教师评分。')

p = Preferences(early, weekdays, teachers, ban_early, tuple(banned), tuple(blocked))
db_hash = hashlib.sha256(DB.read_bytes()).hexdigest()
signature = hashlib.sha256((db_hash+json.dumps([codes, asdict(p)], sort_keys=True)).encode()).hexdigest()
ready = bool(codes) and 12 <= credits <= 18 and not bad_block


def seed_manual(selections):
    for code in codes:
        for comp in cat.required[code]:
            options = [s.code for s in cat.sections[code] if s.component == comp]
            st.session_state[f'manual_{signature}_{code}_{comp}'] = next(
                (sec for c, sec in selections if c == code and sec in options), '— 未选择 —')


if st.button('生成推荐方案', type='primary', key='generate', disabled=not ready):
    with st.spinner('正在搜索组合并检查冲突…'):
        result = solve(cat, codes, p, timeout=timeout)
        reports = [check(cat, codes, s['selections'], p) for s in result.solutions]
    st.session_state['result'] = (signature, result, reports)
    st.session_state['solution'] = 0
    st.session_state['editing'] = False
    if result.solutions:
        seed_manual(result.solutions[0]['selections'])

saved = st.session_state.get('result')
current = saved is not None and saved[0] == signature
if saved and not current:
    st.info('课程、偏好或数据库已变化，请重新生成课表。旧方案已隐藏。')

st.divider()
st.subheader('我的课表')
selections = None
report = None
sol = None
idx = 0
result = saved[1] if current else None
status = 'manual'
if result:
    labels = {'optimal': '搜索完成 · 已找到当前评分规则下的最佳方案',
        'infeasible': '当前课程与禁排要求下没有可行方案，请减少禁排限制或调整课程。',
        'invalid': '请修改输入',
        'timeout_feasible': '已到搜索时限 · 可使用当前方案，或增加搜索时间继续寻找',
        'timeout_no_solution': '暂未找到方案 · 可增加搜索时间；这不代表无解'}
    st.info(labels[result.status])
    for error in result.errors:
        st.error(error)
    if result.solutions:
        idx = st.radio('推荐方案', range(len(result.solutions)), horizontal=True,
            format_func=lambda i: f'方案 {i+1} · {result.solutions[i]["score"]:.1f} 分', key='solution')
        sol = result.solutions[idx]
        selections = sol['selections']
        report = saved[2][idx]
        status = result.status
        if st.button('以此方案调整班级', key='load_manual'):
            seed_manual(selections)
            st.session_state['editing'] = True
        with st.expander('评分与搜索详情'):
            st.caption(f'搜索用时 {result.elapsed:.2f} 秒 · 访问 {result.nodes:,} 个节点')
            if sol['breakdown']:
                st.write({{'early': '早八', 'weekdays': '星期', 'teachers': '教师'}.get(k,k): round(v,2) for k,v in sol['breakdown'].items()})
            st.caption('早八、星期、教师三类等权；未设置类别不参与。时间偏好按整个学期实际上课次数计算，分数不是满意百分比。')

# One shared preview/export area for recommended and edited selections.
editing = st.toggle('手动调整班级', key='editing', disabled=not ready)
if editing and ready:
    st.caption('每次改班都会自动复核。关闭此开关可返回推荐方案，手动选择会保留。')
    selections = []
    for code in codes:
        with st.expander(f"{code} · {cat.courses[code]['name']}", expanded=True):
            cols = st.columns(max(1, len(cat.required[code])))
            for i, comp in enumerate(sorted(cat.required[code])):
                opts = {s.code: s for s in cat.sections[code] if s.component == comp}
                def label(sec, opts=opts):
                    if sec not in opts:
                        return sec
                    s = opts[sec]
                    times = ' / '.join(dict.fromkeys(f'{DAYS[m.weekday-1]} {hhmm(m.start)}–{hhmm(m.end)}' for m in s.meetings))
                    return f'{sec} · {" / ".join(s.teachers) or "教师待定"} · {times}'
                value = cols[i].selectbox({'LEC':'Lecture · 讲授','TUT':'Tutorial · 辅导'}.get(comp,comp),
                    ['— 未选择 —']+list(opts), format_func=label, key=f'manual_{signature}_{code}_{comp}')
                if value in opts:
                    selections.append((code, value))
    report = check(cat, codes, selections, p)
    status = 'manual'
    sol = {'selections': selections}

if selections is not None and report is not None:
    if report['passed'] and not bad_block:
        st.success('独立检查通过 · 组件、学分、教学日期与禁排时间均符合要求')
        meetings = [m for code, sec in selections for s in cat.sections[code] if s.code == sec for m in s.meetings]
        first, last = min(m.first for m in meetings), max(m.last for m in meetings)
        weeks = []
        cursor = first-timedelta(days=first.weekday())
        while cursor <= last:
            weeks.append(cursor)
            cursor += timedelta(days=7)
        default = max(weeks[0], min(date.today()-timedelta(days=date.today().weekday()), weeks[-1]))
        monday = st.selectbox('显示教学周', weeks, index=weeks.index(default),
            format_func=lambda d: f'第 {weeks.index(d)+1} 周 · {d:%m/%d} – {d+timedelta(days=6):%m/%d}', key='week')
        rows = weekly_rows(cat, selections, monday)
        metrics = st.columns(3)
        metrics[0].metric('本周课次', len(rows))
        metrics[1].metric('早八课次', sum(r['start'] == 510 for r in rows))
        metrics[2].metric('无课天数', sum(not any(r['weekday'] == d for r in rows) for d in range(1,8)))
        st.markdown(render(rows), unsafe_allow_html=True)
        visible = [{k:v for k,v in r.items() if k not in ('weekday','start','end')} for r in rows]
        with st.expander('本周课程明细'):
            st.dataframe(pd.DataFrame(visible), hide_index=True)
        downloads = st.columns(2)
        downloads[0].download_button('导出本周 CSV', pd.DataFrame(visible).to_csv(index=False).encode('utf-8-sig'),
            f'timetable_{monday}.csv', 'text/csv', key='csv', disabled=not rows)
        payload = {'courses': codes, 'preferences': asdict(p), 'solution': sol, 'validation': report,
            'status': status, 'database_sha256': db_hash}
        downloads[1].download_button('导出完整学期方案', json.dumps(payload, ensure_ascii=False, indent=2),
            'schedule.json', 'application/json', key='json')
        st.caption('CSV 为当前周；完整方案包含整个学期的班级选择。')
    else:
        st.warning('当前方案未通过检查，请调整后再预览或导出。')
        for error in report['errors']:
            st.error(error)
    with st.expander('选课前需要核对'):
        for warning in report['warnings']:
            st.warning(warning)
elif not saved:
    st.info('选好 12–18 学分后点击“生成推荐方案”，也可以开启手动调整自行选班。')
