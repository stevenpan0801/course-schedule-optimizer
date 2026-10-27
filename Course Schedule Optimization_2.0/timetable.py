"""Date-aware timetable with exact time boundaries; never move a class."""
from datetime import timedelta
from html import escape

DAYS=['周一','周二','周三','周四','周五','周六','周日']
def hhmm(n):return f'{n//60:02d}:{n%60:02d}'

def weekly_rows(cat,selections,monday):
    rows=[]
    for code,sec in selections:
        s=next(s for s in cat.sections[code] if s.code==sec)
        for m in s.meetings:
            d=monday+timedelta(days=m.weekday-1)
            if not m.first<=d<=m.last:continue
            rows.append({'日期':d.isoformat(),'星期':DAYS[m.weekday-1],'课程代码':code,'课程名称':cat.courses[code]['name'],'班级':sec,'类型':s.component,'开始':hhmm(m.start),'结束':hhmm(m.end),'教师':' / '.join(m.teachers) or '待定','教室':' / '.join(m.rooms),'weekday':m.weekday,'start':m.start,'end':m.end})
    return sorted(rows,key=lambda r:(r['weekday'],r['start']))


def render(rows):
    if not rows:return '<p>本周没有课程（已按教学起止日期筛选）。</p>'
    bounds=sorted({r[k] for r in rows for k in ('start','end')})
    html=['<style>.schedule{border-collapse:collapse;width:100%;table-layout:fixed}.schedule th,.schedule td{border:1px solid #a8b9c7;padding:7px;vertical-align:top;font-size:12px}.schedule th{background:#edf2f7;color:#203347}.schedule .lesson{background:#dceee4;color:#173d30}.schedule .time{width:95px}</style><div style="overflow-x:auto"><table class="schedule"><thead><tr><th class="time">时间</th>']
    html += [f'<th>{d}</th>' for d in DAYS]+['</tr></thead><tbody>']
    for i,t in enumerate(bounds[:-1]):
        html.append(f'<tr><td>{hhmm(t)}–{hhmm(bounds[i+1])}</td>')
        for wd in range(1,8):
            matches=[r for r in rows if r['weekday']==wd and r['start']==t]
            if matches:
                r=matches[0];span=bounds.index(r['end'])-i
                text='<br>'.join(escape(str(r[k])) for k in ('课程代码','班级','类型'))
                text+=f"<br>{r['开始']}–{r['结束']}<br>"+escape(r['教师'])+'<br>'+escape(r['教室'])
                html.append(f'<td class="lesson" rowspan="{span}">{text}</td>')
            elif not any(r['weekday']==wd and r['start']<t<r['end'] for r in rows):html.append('<td></td>')
        html.append('</tr>')
    return ''.join(html)+ '</tbody></table></div>'
