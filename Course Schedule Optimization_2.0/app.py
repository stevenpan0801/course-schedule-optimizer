"""Run: python -m streamlit run app.py"""
from datetime import date,timedelta,time
from dataclasses import asdict
import hashlib,json
import pandas as pd
import streamlit as st
from model import DB,Preferences,load_catalog,minutes
from optimizer import solve
from checker import check
from timetable import DAYS,weekly_rows,render

st.set_page_config(page_title='选课优化 2.0',page_icon='📅',layout='wide')
st.title('📅 选课优化 2.0')
st.caption('选课程、填偏好，自动选班并独立复核。12–18 学分；所有班级均参与规划。')
try:cat=load_catalog()
except Exception as exc:st.error(f'无法读取数据库：{exc}');st.stop()
with st.sidebar:
    codes=st.multiselect('要修的课程',list(cat.courses),format_func=lambda c:f"{c} · {cat.courses[c]['name']}",key='courses')
    credits=sum(cat.courses[c]['credits'] for c in codes)
    st.metric('总学分',f'{credits:g} / 12–18')
    picked=st.date_input('显示周（任意一天）',date.today(),key='week')
    monday=picked-timedelta(days=picked.weekday())
    timeout=st.number_input('搜索时限（秒）',min_value=1,max_value=120,value=15,key='timeout')

st.subheader('偏好设置')
st.caption('0 = 最不喜欢，5 = 最喜欢。不勾选的项目不参与评分；0 分不是禁止。')
early=None
if st.checkbox('设置早八喜好',key='rate_early'):
    early=st.slider('08:30 开始的课',0,5,0,key='early')
weekdays={}
with st.expander('每周哪几天喜欢上课'):
    days=st.multiselect('要评分的星期',range(1,8),format_func=lambda d:DAYS[d-1],key='rated_days')
    for d in days:weekdays[d]=st.slider(f'{DAYS[d-1]}排课喜好',0,5,0,key=f'day_{d}')
teachers={}
with st.expander('喜欢哪些老师（可输入姓名搜索）'):
    for code in codes:
        names=sorted({t for s in cat.sections[code] for t in s.teachers})
        selected=st.multiselect(f'{code} 教师姓名',names,key=f'teachers_{code}')
        if selected:
            teachers[code]={t:st.slider(f'{code} · {t}',0,5,5,key=f'teacher_{code}_{t}') for t in selected}
    st.caption('未评分教师按中性 2.5 分处理；系统自动识别教师对应的班级。')
with st.expander('硬约束：绝对不能排的时间'):
    ban_early=st.checkbox('禁止所有 08:30 开始的课',key='ban_early')
    banned=st.multiselect('完全不能上课的星期',range(1,8),format_func=lambda d:DAYS[d-1],key='banned_days')
    blocked=[];bad_block=False
    count=st.number_input('额外禁排时段数量',0,10,0,key='block_count')
    for i in range(count):
        cols=st.columns(3)
        d=cols[0].selectbox(f'时段 {i+1} 星期',range(1,8),format_func=lambda d:DAYS[d-1],key=f'block_day_{i}')
        a=cols[1].time_input('开始',value=time(18),key=f'block_a_{i}')
        b=cols[2].time_input('结束',value=time(21),key=f'block_b_{i}')
        if a>=b:bad_block=True;st.error('禁排时段结束时间必须晚于开始时间。')
        blocked.append((d,a.hour*60+a.minute,b.hour*60+b.minute))
p=Preferences(early,weekdays,teachers,ban_early,tuple(banned),tuple(blocked))
signature=hashlib.sha256(DB.read_bytes()+json.dumps([codes,asdict(p)],sort_keys=True).encode()).hexdigest()

if st.button('自动生成课表',type='primary',key='generate',disabled=bad_block):
    with st.spinner('搜索班级组合并独立复核…'):
        result=solve(cat,codes,p,timeout=timeout)
        reports=[check(cat,codes,s['selections'],p) for s in result.solutions]
        st.session_state['result']=(signature,result,reports)
        if result.solutions:
            for code,sec in result.solutions[0]['selections']:
                comp=next(s.component for s in cat.sections[code] if s.code==sec)
                st.session_state[f'manual_{signature}_{code}_{comp}']=sec


def show(selections,key):
    rows=weekly_rows(cat,selections,monday)
    st.markdown(render(rows),unsafe_allow_html=True)
    visible=[{k:v for k,v in r.items() if k not in ('weekday','start','end')} for r in rows]
    if visible:
        st.dataframe(pd.DataFrame(visible),hide_index=True)
        csv=pd.DataFrame(visible).to_csv(index=False).encode('utf-8-sig')
        st.download_button('下载本周 CSV',csv,f'timetable_{monday}.csv','text/csv',key=f'csv_{key}')
    st.caption(f'本周早八 {sum(r["start"]==510 for r in rows)} 次；无课日：'+ '、'.join(DAYS[d-1] for d in range(1,8) if not any(r['weekday']==d for r in rows)))

saved=st.session_state.get('result')
if saved and saved[0]!=signature:st.info('课程、偏好或数据库已变化，请重新生成课表。')
if saved and saved[0]==signature:
    _,result,reports=saved
    labels={'optimal':'搜索完成：已找到按当前评分规则排名最高的方案','infeasible':'当前数据与约束下无可行方案','invalid':'请修改输入','timeout_feasible':'已到搜索时限：展示当前最佳方案，尚未证明最优','timeout_no_solution':'已到搜索时限，暂未找到方案；不能据此认定无解'}
    st.info(labels[result.status])
    st.caption(f'访问 {result.nodes:,} 个搜索节点，用时 {result.elapsed:.2f} 秒。')
    for error in result.errors:st.error(error)
    if result.solutions:
        idx=st.selectbox('查看方案',range(len(result.solutions)),format_func=lambda i:f'方案 {i+1} · {result.solutions[i]["score"]:.1f} 分',key='solution')
        sol=result.solutions[idx];report=reports[idx]
        if st.button('将当前方案载入手动检查区',key='load_manual'):
            for code,sec in sol['selections']:
                comp=next(s.component for s in cat.sections[code] if s.code==sec)
                st.session_state[f'manual_{signature}_{code}_{comp}']=sec
        if report['passed']:
            st.success('独立检查通过：课程、组件、学分、教学日期及禁排时间。')
            if sol['breakdown']:st.write({k:round(v,2) for k,v in sol['breakdown'].items()})
            show(sol['selections'],'auto')
        else:
            st.error('独立检查未通过，不展示为可行课表。')
            for error in report['errors']:st.error(error)
        with st.expander('数据说明与验证范围'):
            for warning in report['warnings']:st.warning(warning)
        payload={'courses':codes,'preferences':asdict(p),'solution':sol,'validation':report,'status':result.status,'database_sha256':hashlib.sha256(DB.read_bytes()).hexdigest()}
        st.download_button('下载完整方案 JSON',json.dumps(payload,ensure_ascii=False,indent=2),'schedule.json','application/json',key='json')

with st.expander('手动选班／独立可行性检查'):
    selections=[]
    defaults=saved[1].solutions[0]['selections'] if saved and saved[0]==signature and saved[1].solutions else []
    for code in codes:
        for comp in sorted(cat.required[code]):
            opts=[s.code for s in cat.sections[code] if s.component==comp]
            options=['— 未选择 —']+opts
            seed=next((sec for c,sec in defaults if c==code and sec in opts),options[0])
            value=st.selectbox(f'{code} {comp}',options,index=options.index(seed),key=f'manual_{signature}_{code}_{comp}')
            if value!=options[0]:selections.append((code,value))
    if st.button('检查手动方案',key='check_manual'):
        report=check(cat,codes,selections,p)
        if report['passed']:st.success('手动方案检查通过');show(selections,'manual')
        else:
            for error in report['errors']:st.error(error)
        for warning in report['warnings']:st.warning(warning)
with st.expander('评分规则'):
    st.write('早八、星期、教师三类等权，未设置类别不计入。早八严格指 08:30 开始。时间偏好按学期内实际上课次数计算；0 分推动减少，5 分推动增加。星期项是所评分各天的平均分。教师项只统计存在已评分教师的组件，未评分教师中性。分数用于比较本次请求的方案，不代表绝对满意率；修改硬约束后不宜跨请求比较。')
