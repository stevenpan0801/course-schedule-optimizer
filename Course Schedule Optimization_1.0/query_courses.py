"""与 freshman_term1_2026_2027.sqlite 放在同一目录；运行 python3 query_courses.py。

本模块提供两层能力：
1) 单/双门课程查询（历史函数：get_course / get_schedule / find_by_weekday /
   find_by_instructor / check_conflict / get_all_course_codes）保持不变，便于兼容旧代码。
2) 多课程选课系统所需的辅助函数（新增）：
   - get_course_components / get_sections_by_component：驱动前端“每门课按 component 选区段”
   - total_credits：学分累加（按课程去重，同一门课的 LEC+TUT 只计一次）
   - check_conflicts_multi / build_weekly_schedule：多区段冲突检测与一周课表生成
"""
from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).with_name('freshman_term1_2026_2027.sqlite')

# 星期映射（meeting_days.weekday: 1=周一 ... 7=周日）
WEEKDAY_LABELS = {1: '周一', 2: '周二', 3: '周三', 4: '周四', 5: '周五', 6: '周六', 7: '周日'}

# component 的稳定展示顺序（前端下拉按此排序，未知的排后面）
_COMPONENT_ORDER = ['LEC', 'TUT', 'SUP', 'LAB', 'SEM', 'REC', 'DIS', 'PRJ', 'STU', 'IND', 'FLD', 'CLN', 'EXM', 'FIN']
# component 的中文友好名（仅用于界面展示）
COMPONENT_LABEL = {
    'LEC': '讲座', 'TUT': '辅导', 'SUP': '督导', 'LAB': '实验', 'SEM': '研讨',
    'REC': '习题', 'DIS': '讨论', 'PRJ': '项目', 'STU': '自习', 'IND': '个别指导',
    'FLD': '实习', 'CLN': '临床', 'EXM': '考试', 'FIN': '期末',
}


def connect():
    conn = sqlite3.connect(DB_PATH.as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ----------------------------------------------------------------------------
# 历史函数（保留，仅做小幅整理）
# ----------------------------------------------------------------------------
def get_course(code):
    """返回课程详情；例如 MAT1001。"""
    with connect() as conn:
        row = conn.execute('SELECT * FROM courses WHERE code = ?', (code,)).fetchone()
        return dict(row) if row else None


def get_schedule(code):
    """返回课程的所有可选区段，并非个人已选课表。"""
    with connect() as conn:
        return [dict(row) for row in conn.execute(
            'SELECT * FROM schedule WHERE course_code = ? ORDER BY section_code, meeting_id',
            (code,))]


def find_by_weekday(weekday):
    """星期一=1，星期日=7。"""
    if weekday not in range(1, 8):
        raise ValueError('weekday 必须为 1 到 7')
    with connect() as conn:
        return [dict(row) for row in conn.execute('''
            SELECT s.* FROM schedule s JOIN meeting_days d ON d.meeting_id = s.meeting_id
            WHERE d.weekday = ? ORDER BY s.start_time, s.course_code, s.section_code
        ''', (weekday,))]


def find_by_instructor(name):
    """按讲师姓名精确查询；姓名使用数据库中的原始拼写。"""
    with connect() as conn:
        return [dict(row) for row in conn.execute('''
            SELECT s.* FROM schedule s
            JOIN meeting_instructors mi ON mi.meeting_id = s.meeting_id
            JOIN instructors i ON i.id = mi.instructor_id
            WHERE i.name = ? ORDER BY s.course_code, s.section_code
        ''', (name,))]


def check_conflict(course_a, section_a, course_b, section_b):
    """
    判断两门课程的两个特定区段时间是否冲突。
    返回: (是否冲突, 冲突的具体信息)
    """
    times_a = _section_meetings(course_a, section_a)
    times_b = _section_meetings(course_b, section_b)

    conflicts = []
    for t_a in times_a:
        for t_b in times_b:
            if t_a['weekday'] == t_b['weekday']:
                # 时间重叠：A开始 < B结束 且 B开始 < A结束
                if t_a['start_time'] < t_b['end_time'] and t_b['start_time'] < t_a['end_time']:
                    conflicts.append({
                        'weekday': t_a['weekday'],
                        'time_a': f"{t_a['start_time']} - {t_a['end_time']}",
                        'time_b': f"{t_b['start_time']} - {t_b['end_time']}",
                    })

    is_conflict = len(conflicts) > 0
    return is_conflict, conflicts


def get_all_course_codes():
    """获取所有课程的代码列表，用于前端下拉菜单"""
    with connect() as conn:
        rows = conn.execute('SELECT code FROM courses ORDER BY code').fetchall()
        return [row['code'] for row in rows]


# ----------------------------------------------------------------------------
# 新增：多课程选课系统辅助函数
# ----------------------------------------------------------------------------
def _section_meetings(course_code, section_code):
    """
    内部工具：返回某个区段的所有上课时间。
    每行: {weekday, start_time, end_time, room}
    通过 sections -> meetings -> meeting_days 三表关联获得。
    """
    with connect() as conn:
        rows = conn.execute('''
            SELECT d.weekday            AS weekday,
                   m.start_time         AS start_time,
                   m.end_time           AS end_time,
                   m.room               AS room
            FROM sections s
            JOIN meetings m      ON m.section_id = s.id
            JOIN meeting_days d  ON d.meeting_id = m.id
            WHERE s.course_code = ? AND s.section_code = ?
            ORDER BY d.weekday, m.start_time
        ''', (course_code, section_code)).fetchall()
        return [dict(r) for r in rows]


def get_course_components(course_code):
    """
    返回某门课程提供的所有 component 类型（去重，按稳定顺序排序）。
    例: MAT1001 -> ['LEC', 'TUT'];  ENG1001 -> ['LEC'];  AIE1901 -> ['SUP']
    """
    with connect() as conn:
        rows = conn.execute(
            'SELECT DISTINCT component FROM sections WHERE course_code = ?',
            (course_code,)).fetchall()
    comps = [r['component'] for r in rows]
    comps.sort(key=lambda c: _COMPONENT_ORDER.index(c) if c in _COMPONENT_ORDER else len(_COMPONENT_ORDER))
    return comps


def get_sections_by_component(course_code, component):
    """
    返回某课程某 component 下的所有区段，用于前端下拉菜单。
    每行: {section_code, status, class_number}
    status 为 '开放' / '关闭'，前端据此标注。
    """
    with connect() as conn:
        rows = conn.execute('''
            SELECT section_code, status, class_number
            FROM sections
            WHERE course_code = ? AND component = ?
            ORDER BY section_code
        ''', (course_code, component)).fetchall()
        return [dict(r) for r in rows]


def get_course_credits(course_code):
    """返回单门课程的学分（REAL）；课程不存在时返回 0.0。"""
    with connect() as conn:
        row = conn.execute('SELECT credits FROM courses WHERE code = ?', (course_code,)).fetchone()
        return float(row['credits']) if row else 0.0


def total_credits(course_codes):
    """
    对多个课程代码累加学分。
    按课程去重：同一门课的 LEC+TUT 只计一次该课学分（学分属于整门课，不按区段拆分）。
    """
    total = 0.0
    seen = set()
    with connect() as conn:
        for code in course_codes:
            if code in seen:
                continue
            seen.add(code)
            row = conn.execute('SELECT credits FROM courses WHERE code = ?', (code,)).fetchone()
            if row:
                total += float(row['credits'])
    return total


def check_conflicts_multi(selections):
    """
    多区段两两时间冲突检测。
    selections: [(course_code, section_code), ...]
    返回冲突列表，每条:
        {course_a, section_a, course_b, section_b, weekday, time_a, time_b}
    weekday 为整数（1=周一）。
    """
    conflicts = []
    n = len(selections)
    for i in range(n):
        ca, sa = selections[i]
        times_a = _section_meetings(ca, sa)
        for j in range(i + 1, n):
            cb, sb = selections[j]
            times_b = _section_meetings(cb, sb)
            for ta in times_a:
                for tb in times_b:
                    if ta['weekday'] == tb['weekday']:
                        if ta['start_time'] < tb['end_time'] and tb['start_time'] < ta['end_time']:
                            conflicts.append({
                                'course_a': ca, 'section_a': sa,
                                'course_b': cb, 'section_b': sb,
                                'weekday': ta['weekday'],
                                'time_a': f"{ta['start_time']} - {ta['end_time']}",
                                'time_b': f"{tb['start_time']} - {tb['end_time']}",
                            })
    return conflicts


def build_weekly_schedule(selections):
    """
    生成按 星期 -> 开始时间 排序的一周课表行列表，供 pandas DataFrame 使用。
    selections: [(course_code, section_code), ...]
    每行: {weekday(整数1-7), 星期, 开始, 结束, 课程代码, 课程名称, 区段, 类型, 教室}
    其中 weekday 为整数（1=周一），便于前端绘制「时间 × 星期」网格课表。
    """
    rows = []
    with connect() as conn:
        for code, sec in selections:
            name_row = conn.execute('SELECT name FROM courses WHERE code = ?', (code,)).fetchone()
            course_name = name_row['name'] if name_row else code
            comps = conn.execute('''
                SELECT s.component   AS component,
                       d.weekday     AS weekday,
                       m.start_time  AS start_time,
                       m.end_time    AS end_time,
                       m.room        AS room
                FROM sections s
                JOIN meetings m     ON m.section_id = s.id
                JOIN meeting_days d ON d.meeting_id = m.id
                WHERE s.course_code = ? AND s.section_code = ?
                ORDER BY d.weekday, m.start_time
            ''', (code, sec)).fetchall()
            for r in comps:
                rows.append({
                    'weekday': r['weekday'],
                    '星期': WEEKDAY_LABELS.get(r['weekday'], str(r['weekday'])),
                    '开始': r['start_time'],
                    '结束': r['end_time'],
                    '课程代码': code,
                    '课程名称': course_name,
                    '区段': sec,
                    '类型': r['component'],
                    '教室': r['room'] or '',
                })
    rows.sort(key=lambda x: (x['weekday'], x['开始']))
    return rows


if __name__ == '__main__':
    with connect() as conn:
        for row in conn.execute('SELECT * FROM course_summary ORDER BY code'):
            print(dict(row))
    print('\nMAT1001 前三个区段：')
    for row in get_schedule('MAT1001')[:3]:
        print(row)
    print('\n星期一的时段记录数量：', len(find_by_weekday(1)))
    print('Pinjia HE 的时段：', find_by_instructor('Pinjia HE'))

    print("\n--- 开始测试时间冲突检测 ---")
    test_course_1 = 'MAT1001'
    test_section_1 = 'L01'
    test_course_2 = 'CSC1001'
    test_section_2 = 'L01'

    has_conflict, details = check_conflict(test_course_1, test_section_1, test_course_2, test_section_2)
    if has_conflict:
        print(f"⚠️ 发现冲突！{test_course_1} 和 {test_course_2} 冲突：")
        for c in details:
            print(f"星期{c['weekday']} 冲突: {c['time_a']} 与 {c['time_b']}")
    else:
        print(f"✅ {test_course_1} ({test_section_1}) 与 {test_course_2} ({test_section_2}) 时间不冲突，可以同选！")

    print("\n--- 多课程辅助函数自检 ---")
    print('MAT1001 components:', get_course_components('MAT1001'))
    print('MAT1001 TUT 区段数:', len(get_sections_by_component('MAT1001', 'TUT')))
    print('学分累加 [MAT1001, AIE1001, MAT1001]:', total_credits(['MAT1001', 'AIE1001', 'MAT1001']))
    print('课表行示例 (MAT1001 L01):', build_weekly_schedule([('MAT1001', 'L01')]))
