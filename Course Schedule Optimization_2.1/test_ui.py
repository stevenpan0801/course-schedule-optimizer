"""UI regressions: a single preview, persistent manual edits and invalidation."""
import sys
from pathlib import Path
from datetime import timedelta
p=Path(__file__).resolve().parent
sys.path.insert(0,str(p))
from streamlit.testing.v1 import AppTest
at=AppTest.from_file(str(p/'app.py'),default_timeout=30).run()
assert not at.exception
assert at.button(key='generate').disabled
at.multiselect(key='courses').set_value(['AIE1001','AIE1901','MAT1001','ENG1001','CHI1000','PED1113']).run()
at.selectbox(key='early_mode').set_value('尽量避免').run()
at.button(key='generate').click().run()
assert not at.exception,at.exception
assert any('独立检查通过' in s.value for s in at.success),[e.value for e in at.error]
assert len(at.dataframe)==2  # One editable time grid plus one timetable detail table.
at.button(key='load_manual').click().run()
assert at.toggle(key='editing').value
assert any('独立检查通过' in s.value for s in at.success)
week=at.selectbox(key='week').value
at.selectbox(key='week').set_value(week-timedelta(days=7)).run()
assert not at.exception and len(at.dataframe)==2
assert any('独立检查通过' in s.value for s in at.success)
manual=next(x for x in at.selectbox if x.key and x.key.startswith('manual_'))
original=manual.value
manual.set_value('— 未选择 —').run()
assert len(at.error)>0 and len(at.dataframe)==1
at.selectbox(key=manual.key).set_value(original).run()
assert any('独立检查通过' in s.value for s in at.success)
at.toggle(key='editing').set_value(False).run()
assert len(at.dataframe)==2
at.radio(key='solution').set_value(1).run()
at.button(key='load_manual').click().run()
assert not at.exception and len(at.dataframe)==2
at.multiselect(key='banned_days').set_value([1,2,3,4,5,6,7]).run()
assert any('重新生成' in s.value for s in at.info)
at.button(key='generate').click().run()
assert not at.exception and len(at.error)>0
at.multiselect(key='courses').set_value(['MAT1001']).run()
assert at.button(key='generate').disabled
assert any('学分' in s.value for s in at.warning)
print('PASS: generate, one preview, manual persistence, missing component, switch solution, stale, infeasible, credits')
