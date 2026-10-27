"""Headless verification of app.py using Streamlit's AppTest harness.

Covers:
  Scenario A (error path): partial selection -> missing required / low credit / time conflict
  Scenario B (success path): a valid, conflict-free selection -> success + weekly DataFrame
"""
from streamlit.testing.v1 import AppTest
from query_courses import (
    get_course_components, get_sections_by_component,
    check_conflicts_multi, total_credits,
)

REQUIRED = ['AIE1001', 'AIE1901', 'MAT1001', 'ENG1001', 'CHI1000']
PED = 'PED1101'
CREDIT_MIN, CREDIT_MAX = 12, 18


def _cands(code, limit=12):
    """course -> {comp: [(section_code, status), ...]} (first `limit` sections)."""
    out = {}
    for comp in get_course_components(code):
        rows = get_sections_by_component(code, comp)[:limit]
        out[comp] = [(r['section_code'], r['status']) for r in rows]
    return out


def _label(sec, status):
    return f"{sec}  ·  {'开放' if status == '开放' else '关闭'}"


def solve_valid():
    """Backtracking search for a conflict-free selection covering required + 1 PED,
    with total credits in [12, 18]."""
    cand = {c: _cands(c) for c in REQUIRED}
    ped_cand = _cands(PED)

    import itertools
    best = None

    def rec(i, sel):
        nonlocal best
        if best is not None:
            return
        if i == len(REQUIRED):
            # try to attach a PED section
            for comp, secs in ped_cand.items():
                for sec, status in secs:
                    trial = sel + [(PED, sec)]
                    if (not check_conflicts_multi(trial)
                            and CREDIT_MIN <= total_credits([c for c, _ in trial]) <= CREDIT_MAX):
                        best = sel + [(PED, sec)]
                        return
            return
        code = REQUIRED[i]
        comps = cand[code]  # comp -> [(section, status), ...]
        comp_names = list(comps.keys())
        # pick exactly one section per component (cartesian product)
        for combo in itertools.product(*[comps[c] for c in comp_names]):
            trial = sel + [(code, sec) for (sec, status) in combo]
            if check_conflicts_multi(trial):
                continue
            rec(i + 1, trial)
            if best is not None:
                return
        return

    rec(0, [])
    if best is None:
        raise RuntimeError('No valid conflict-free schedule found within search limits')

    # build per-course per-component map + widget label map
    sel_map = {}
    for code, sec in best:
        comp = None
        for c, secs in _cands(code).items():
            if any(s == sec for s, _ in secs):
                comp = c
                break
        sel_map.setdefault(code, {})[comp] = sec
    return best, sel_map


print('=== Scenario A: error path (partial selection) ===')
at = AppTest.from_file('app.py', default_timeout=30)
at.run()
if at.exception:
    print('APP EXCEPTION during run:', at.exception)
at.multiselect(key='courses').set_value(['MAT1001', 'AIE1001'])
at.run()
if at.exception:
    print('APP EXCEPTION after course select:', at.exception)
# MAT1001: pick LEC L01 + TUT T01 (these overlap with AIE1001 L01 on Tue/Thu)
at.selectbox(key='sel_MAT1001_LEC').set_value(_label('L01', '关闭'))
at.selectbox(key='sel_MAT1001_TUT').set_value(_label('T01', '关闭'))
at.selectbox(key='sel_AIE1001_LEC').set_value(_label('L01', '开放'))
at.selectbox(key='sel_AIE1001_TUT').set_value(_label('T01', '开放'))
at.run()
at.button(key='gen_btn').click().run()
if at.exception:
    print('APP EXCEPTION after button:', at.exception)

err_text = ' | '.join(e.value for e in at.error)
print('errors captured:', len(at.error))
for e in at.error:
    print('  ERROR:', e.value)
assert any('缺少必修课' in e.value for e in at.error), 'expected missing-required error'
assert any('总学分' in e.value for e in at.error), 'expected credit error'
assert any('时间冲突' in e.value for e in at.error), 'expected conflict error (MAT1001 L01 vs AIE1001 L01)'
print('Scenario A PASS\n')

print('=== Scenario B: success path (valid schedule) ===')
best, sel_map = solve_valid()
print('valid selection:', best, '| credits:', total_credits([c for c, _ in best]))
at2 = AppTest.from_file('app.py', default_timeout=30)
at2.run()
courses = list(sel_map.keys())
at2.multiselect(key='courses').set_value(courses)
at2.run()
if at2.exception:
    print('APP EXCEPTION (scenario B) after course select:', at2.exception)
for code, comps in sel_map.items():
    for comp, sec in comps.items():
        w = at2.selectbox(key=f'sel_{code}_{comp}')
        opt = next((o for o in w.options if o.startswith(f'{sec}  ·')), None)
        if opt is None:
            raise RuntimeError(f'option for {code} {comp} {sec} not found; options={w.options}')
        w.set_value(opt)
at2.run()
at2.button(key='gen_btn').click().run()
if at2.exception:
    print('APP EXCEPTION (scenario B) after button:', at2.exception)
print('scenario B errors:', [e.value for e in at2.error])

print('success widgets:', len(at2.success))
for s in at2.success:
    print('  SUCCESS:', s.value)
print('dataframes:', len(at2.dataframe))
assert len(at2.success) >= 1, 'expected success message'
assert len(at2.dataframe) >= 1, 'expected a weekly schedule dataframe'
print('Scenario B PASS')

# ---------------------------------------------------------------------------
# Scenario C —— 回归测试：复现用户遇到的 ImportError
#   场景：服务进程在旧版 query_courses.py 还在时就启动了，sys.modules 里缓存着
#   「没有 get_course_components」的旧模块。此时热重载新版 app.py 就会报
#   ImportError: cannot import name 'get_course_components' from 'query_courses'。
#   期望：app.py 主动丢弃缓存的旧模块并重新从磁盘加载 → 恢复正常。
# ---------------------------------------------------------------------------
print('\n=== Scenario C: stale query_courses cached in sys.modules ===')
import types
import sys

stale = types.ModuleType('query_courses')
stale.__file__ = r'D:\港中深\上课\AIE1901\选课project\protect\query_courses.py'
stale.get_all_course_codes = lambda: ['OLD_COURSE']      # 旧版只有这几个函数
stale.get_schedule = lambda code: []
stale.check_conflict = lambda *a, **k: (False, [])
sys.modules['query_courses'] = stale                        # 模拟旧服务器缓存

at3 = AppTest.from_file('app.py', default_timeout=30)
at3.run()
if at3.exception:
    print('APP EXCEPTION (scenario C):', at3.exception)
assert not at3.exception, 'app must recover from a stale cached query_courses module'

n_courses = len(at3.multiselect(key='courses').options)
print('courses loaded:', n_courses)
assert n_courses > 5, 'should have loaded the REAL module (24 courses), not the stale one'
print('Scenario C PASS - recovered from stale module, loaded the real one')
sys.modules.pop('query_courses', None)

print('\nALL TESTS PASSED')
