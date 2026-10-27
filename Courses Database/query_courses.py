"""与 freshman_term1_2026_2027.sqlite 放在同一目录；运行 python3 query_courses.py。"""
from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).with_name('freshman_term1_2026_2027.sqlite')

def connect():
    conn = sqlite3.connect(DB_PATH.as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn

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

if __name__ == '__main__':
    with connect() as conn:
        for row in conn.execute('SELECT * FROM course_summary ORDER BY code'):
            print(dict(row))
    print('\nMAT1001 前三个区段：')
    for row in get_schedule('MAT1001')[:3]:
        print(row)
    print('\n星期一的时段记录数量：', len(find_by_weekday(1)))
    print('Pinjia HE 的时段：', find_by_instructor('Pinjia HE'))
