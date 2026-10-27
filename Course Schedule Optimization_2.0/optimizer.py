"""Exact top-k branch-and-bound over sections; no third-party solver required."""
from dataclasses import dataclass, field
from time import monotonic
from model import dates, validate_request

@dataclass
class Result:
    status: str
    solutions: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    nodes: int = 0
    elapsed: float = 0


def overlap(a,b):
    if a.weekday!=b.weekday or a.start>=b.end or b.start>=a.end: return False
    lo,hi=max(a.first,b.first),min(a.last,b.last)
    if lo>hi: return False
    from datetime import timedelta
    return lo+timedelta(days=(a.weekday-1-lo.weekday())%7)<=hi


def conflict(a,b):
    return any(overlap(x,y) for x in a.meetings for y in b.meetings)


def allowed(s,p):
    for i,m in enumerate(s.meetings):
        if not any(dates(m)): continue
        if m.weekday in p.banned_days or (p.ban_early and m.start==510): return False
        if any(d==m.weekday and m.start<b and a<m.end for d,a,b in p.blocked): return False
        if any(overlap(m,n) for n in s.meetings[i+1:]): return False
    return True


def make_groups(cat,codes,p):
    groups=[]
    for code in codes:
        offered={s.component for s in cat.sections[code]}
        missing=cat.required[code]-offered
        if missing and not p.allow_missing_components:
            raise ValueError(f'{code} 缺少必需组件 {sorted(missing)}；补充数据或明确选择暂按现有班级规划。')
        for comp in sorted(cat.required[code]&offered):
            candidates=[s for s in cat.sections[code] if s.component==comp and allowed(s,p)]
            if not candidates: raise ValueError(f'{code} {comp} 没有满足禁排要求且内部无冲突的班级。')
            groups.append(candidates)
    return groups


def scoring(groups,p):
    """Fixed per-request denominators yield additive, bounded category scores.
    Time counts are actual semester occurrences, deduplicated in the adapter.
    Each rated day interpolates between avoiding/maximizing its occurrence count.
    Unrated teachers are neutral (2.5), blank categories are excluded.
    """
    counts={s: [(m,len(list(dates(m)))) for m in s.meetings] for g in groups for s in g}
    early=lambda s:sum(n for m,n in counts[s] if m.start==510)
    onday=lambda s,d:sum(n for m,n in counts[s] if m.weekday==d)
    maxima={d:sum(max(onday(s,d) for s in g) for g in groups) for d in p.weekdays}
    earlymax=sum(max(early(s) for s in g) for g in groups)
    teacher_groups=[g for g in groups if any(t in p.teachers.get(s.course,{}) for s in g for t in s.teachers)]
    active=[];base={};part={s:{} for g in groups for s in g}
    if p.early is not None:
        active.append('早八');base['早八']=20*(5-p.early)
        for s in part: part[s]['早八']=20*(2*p.early-5)*early(s)/earlymax if earlymax else 0
    if p.weekdays:
        active.append('星期');base['星期']=sum(20*(5-v) for v in p.weekdays.values())/len(p.weekdays)
        for s in part:
            part[s]['星期']=sum(20*(2*v-5)*onday(s,d)/maxima[d] if maxima[d] else 0 for d,v in p.weekdays.items())/len(p.weekdays)
    if teacher_groups:
        active.append('教师');base['教师']=0
        for s in part:
            part[s]['教师']=0
        for g in teacher_groups:
            for s in g:
                ratings=p.teachers.get(s.course,{})
                rating=sum(ratings.get(t,2.5) for t in s.teachers)/len(s.teachers) if s.teachers else 2.5
                part[s]['教师']=20*rating/len(teacher_groups)
    def breakdown(selected):
        return {k:base[k]+sum(part[s].get(k,0) for s in selected) for k in active}
    scores={s:sum(part[s].values())/len(active) if active else 0 for s in part}
    constant=sum(base.values())/len(active) if active else 50
    return scores,constant,breakdown


def solve(cat,codes,p,top_k=3,timeout=15):
    start=monotonic()
    errors=validate_request(cat,codes,p)
    if errors: return Result('invalid',errors=errors)
    if top_k<1 or timeout<0: return Result('invalid',errors=['top_k 须为正数，timeout 须非负。'])
    try: groups=make_groups(cat,codes,p)
    except ValueError as exc: return Result('infeasible',errors=[str(exc)])
    scores,constant,breakdown=scoring(groups,p)
    groups.sort(key=lambda g:(len(g),g[0].course,g[0].component))
    for g in groups: g.sort(key=lambda s:(-scores[s],s.code))
    upper=[0]*(len(groups)+1)
    for i in range(len(groups)-1,-1,-1): upper[i]=upper[i+1]+max(scores[s] for s in groups[i])
    best=[];nodes=0;timed_out=False;cache={}
    def clashes(a,b):
        key=(a,b)
        if key not in cache: cache[key]=conflict(a,b)
        return cache[key]
    def search(i,chosen,value):
        nonlocal nodes,timed_out
        if monotonic()-start>=timeout: timed_out=True;return
        nodes+=1
        if len(best)==top_k and value+upper[i]<=best[-1][0]+1e-9: return
        if i==len(groups):
            best.append((value,tuple(chosen)));best.sort(key=lambda v:-v[0]);del best[top_k:];return
        for s in groups[i]:
            if any(clashes(s,t) for t in chosen): continue
            search(i+1,chosen+[s],value+scores[s])
            if timed_out:return
    search(0,[],constant)
    solutions=[{'selections':[(s.course,s.code) for s in chosen],'score':value,'breakdown':breakdown(chosen)} for value,chosen in best]
    status=('timeout_feasible' if best else 'timeout_no_solution') if timed_out else ('optimal' if best else 'infeasible')
    return Result(status,solutions,[] if best or timed_out else ['所有候选组合均违反时间约束；未找到可行课表。'],nodes,monotonic()-start)
