"""Independent feasibility pass. Does not import optimizer or its overlap helper."""
from datetime import timedelta
from model import validate_request


def check(cat,codes,selections,p):
    errors=validate_request(cat,codes,p)
    warnings=['数据库未提供 Lecture/Tutorial 班级绑定规则及个人先修课记录；这些规则未验证。']
    if errors:return {'passed':False,'errors':errors,'warnings':warnings}
    selected=[];seen=set();components={c:[] for c in codes}
    for code,sec in selections:
        if (code,sec) in seen: errors.append(f'重复班级：{code} {sec}')
        seen.add((code,sec))
        if code not in codes: errors.append(f'包含未请求课程：{code}');continue
        options=[s for s in cat.sections[code] if s.code==sec]
        if len(options)!=1: errors.append(f'班级不存在或不唯一：{code} {sec}');continue
        s=options[0];selected.append(s);components[code].append(s.component)
    for code in codes:
        required=set(cat.required[code]);offered={s.component for s in cat.sections[code]}
        missing=required-offered
        if missing and p.allow_missing_components:
            warnings.append(f'{code} 缺失组件 {sorted(missing)} 已由用户明确豁免；仅对现有班级验证。')
            required-=missing
        for comp in required:
            if components[code].count(comp)!=1: errors.append(f'{code} {comp} 必须恰选一个班。')
        if set(components[code])-required: errors.append(f'{code} 包含非必需组件。')
    calendar={}
    for s in selected:
        for m in s.meetings:
            # Expand each day independently; intentionally different from optimizer's interval test.
            d=m.first
            while d<=m.last:
                if d.isoweekday()==m.weekday:
                    label=f'{s.course} {s.code}'
                    if m.weekday in p.banned_days: errors.append(f'{label} 在禁止的星期上课')
                    if p.ban_early and m.start==510: errors.append(f'{label} 违反早八禁排')
                    for wd,a,b in p.blocked:
                        if wd==m.weekday and max(a,m.start)<min(b,m.end): errors.append(f'{label} 违反禁排时段')
                    for a,b,other in calendar.setdefault(d,[]):
                        if max(a,m.start)<min(b,m.end):errors.append(f'{d}：{label} 与 {other} 时间冲突')
                    calendar[d].append((m.start,m.end,label))
                d+=timedelta(days=1)
    errors=list(dict.fromkeys(errors))
    relevant=[w for w in cat.warnings if any(w.startswith(c+' ') for c in codes)]
    return {'passed':not errors,'errors':errors,'warnings':list(dict.fromkeys(warnings+relevant))}
