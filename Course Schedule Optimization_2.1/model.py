"""Read-only SQLite adapter and explicit input contract. Python 3.10+."""
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
import sqlite3

DB = Path(__file__).with_name('freshman_term1_2026_2027.sqlite')
COMPONENTS = {'讲演':'LEC','指导教学':'TUT','监督':'SUP','实验':'LAB'}

@dataclass(frozen=True)
class Meeting:
    weekday: int
    start: int
    end: int
    first: date
    last: date
    rooms: tuple = ()
    teachers: tuple = ()

@dataclass(frozen=True)
class Section:
    course: str
    code: str
    component: str
    meetings: tuple
    teachers: tuple

@dataclass
class Preferences:
    early: float | None = None
    weekdays: dict = field(default_factory=dict)
    teachers: dict = field(default_factory=dict)  # course -> {exact teacher name: rating}
    ban_early: bool = False
    banned_days: tuple = ()
    blocked: tuple = ()  # (weekday, start minute, end minute)
    allow_missing_components: bool = False

@dataclass
class Catalog:
    courses: dict
    sections: dict
    required: dict
    warnings: list


def minutes(value):
    h,m = map(int,value.split(':'))
    if not (0 <= h <= 23 and 0 <= m < 60):
        raise ValueError(f'无效时间：{value}')
    return h*60+m


def dates(m):
    d=m.first+timedelta(days=(m.weekday-1-m.first.weekday())%7)
    while d<=m.last:
        yield d
        d+=timedelta(days=7)


def load_catalog(path=DB):
    con=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    con.row_factory=sqlite3.Row
    try:
        courses={r['code']:dict(r) for r in con.execute('SELECT * FROM courses')}
        required={code:set() for code in courses}
        for r in con.execute('SELECT * FROM course_components'):
            if r['requirement']=='必需':
                required[r['course_code']].add(COMPONENTS.get(r['component'],r['component']))
        sections={code:[] for code in courses}
        warnings=[]
        terms={r[0] for r in con.execute('SELECT DISTINCT term FROM sections')}
        if len(terms)>1:
            raise ValueError('数据库含多个学期，请先提供单学期数据。')
        for s in con.execute('SELECT * FROM sections ORDER BY course_code,section_code'):
            merged={}
            for r in con.execute('SELECT m.*,d.weekday FROM meetings m JOIN meeting_days d ON d.meeting_id=m.id WHERE m.section_id=?',(s['id'],)):
                try:
                    start,end=minutes(r['start_time']),minutes(r['end_time'])
                    first,last=date.fromisoformat(r['start_date']),date.fromisoformat(r['end_date'])
                    if start>=end or first>last: raise ValueError('时间或日期倒置')
                except (TypeError,ValueError) as exc:
                    raise ValueError(f"{s['course_code']} {s['section_code']} 时间数据异常：{exc}") from exc
                teachers={x[0] for x in con.execute('SELECT i.name FROM instructors i JOIN meeting_instructors mi ON mi.instructor_id=i.id WHERE mi.meeting_id=? AND i.is_placeholder=0',(r['id'],))}
                key=(r['weekday'],start,end,first,last)
                roomset,teachset=merged.setdefault(key,(set(),set()))
                if r['room']: roomset.add(r['room'])
                teachset.update(teachers)
            meetings=tuple(Meeting(*key,tuple(sorted(rooms)),tuple(sorted(teachers))) for key,(rooms,teachers) in merged.items())
            if not meetings or not any(list(dates(m)) for m in meetings):
                raise ValueError(f"{s['course_code']} {s['section_code']} 缺少有效上课安排")
            teachers=tuple(sorted({t for m in meetings for t in m.teachers}))
            sections[s['course_code']].append(Section(s['course_code'],s['section_code'],s['component'],meetings,teachers))
            if any(len(m.rooms)>1 for m in meetings):
                warnings.append(f"{s['course_code']} {s['section_code']} 同时段有多个教室；合并为一次课，教室并列显示，需核对原始安排。")
        for code,items in sections.items():
            if len({s.code for s in items})!=len(items): raise ValueError(f'{code} 班级代码不唯一')
            offered={s.component for s in items}
            if not required[code]: required[code]=offered
            missing=required[code]-offered
            if missing: warnings.append(f'{code} 缺少必需组件班级：{", ".join(sorted(missing))}')
        return Catalog(courses,sections,required,warnings)
    finally:
        con.close()


def validate_request(cat,codes,p):
    errors=[]
    if not codes: return ['请选择课程。']
    if len(set(codes))!=len(codes): errors.append('课程代码重复。')
    for code in codes:
        if code not in cat.courses: errors.append(f'未知课程：{code}')
    if errors: return errors
    credits=sum(float(cat.courses[c]['credits']) for c in codes)
    if not 12<=credits<=18: errors.append(f'总学分 {credits:g}，必须在 12–18 之间。')
    values=([p.early] if p.early is not None else [])+list(p.weekdays.values())
    for code,ratings in p.teachers.items():
        if code not in codes: errors.append(f'教师偏好属于未选课程：{code}')
        names={t for s in cat.sections.get(code,[]) for t in s.teachers}
        for name,v in ratings.items():
            if name not in names: errors.append(f'{code} 找不到教师：{name}')
            values.append(v)
    if any(not isinstance(v,(float,int)) or not 0<=v<=5 for v in values): errors.append('喜好分必须为 0–5。')
    if any(d not in range(1,8) for d in list(p.weekdays)+list(p.banned_days)): errors.append('星期必须为 1–7。')
    for d,a,b in p.blocked:
        if d not in range(1,8) or not 0<=a<b<=1440: errors.append('禁排时间区间无效。')
    return errors
