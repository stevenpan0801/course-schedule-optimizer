"""Compatibility data access for the updated database (no status column)."""
from model import DB,load_catalog
import sqlite3

def connect():
    c=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c

def get_course(code):
    with connect() as c:
        r=c.execute('SELECT * FROM courses WHERE code=?',(code,)).fetchone();return dict(r) if r else None

def get_schedule(code):
    with connect() as c:return [dict(r) for r in c.execute('SELECT * FROM schedule WHERE course_code=?',(code,))]

def get_all_course_codes():return sorted(load_catalog().courses)
def get_course_components(code):return sorted(load_catalog().required[code])
def get_sections_by_component(code,component):
    with connect() as c:return [dict(r) for r in c.execute('SELECT section_code,class_number FROM sections WHERE course_code=? AND component=? ORDER BY section_code',(code,component))]
def total_credits(codes):
    cat=load_catalog();return sum(cat.courses[c]['credits'] for c in set(codes))
def find_by_weekday(day):
    with connect() as c:return [dict(r) for r in c.execute('SELECT s.* FROM schedule s JOIN meeting_days d ON d.meeting_id=s.meeting_id WHERE d.weekday=?',(day,))]
def find_by_instructor(name):
    with connect() as c:return [dict(r) for r in c.execute('SELECT s.* FROM schedule s JOIN meeting_instructors mi ON mi.meeting_id=s.meeting_id JOIN instructors i ON i.id=mi.instructor_id WHERE i.name=?',(name,))]
if __name__=='__main__':
    print('\n'.join(get_all_course_codes()))
