import sys
from pathlib import Path
p=Path(__file__).resolve().parent;sys.path.insert(0,str(p))
from streamlit.testing.v1 import AppTest
at=AppTest.from_file(str(p/'app.py'),default_timeout=30).run()
assert not at.exception,at.exception
at.multiselect(key='courses').set_value(['AIE1001','AIE1901','MAT1001','ENG1001','CHI1000','PED1113']).run()
at.checkbox(key='rate_early').check().run()
at.button(key='generate').click().run()
assert not at.exception,at.exception
assert any('独立检查通过' in s.value for s in at.success),[e.value for e in at.error]
assert len(at.dataframe)>0
at.button(key='check_manual').click().run()
assert not at.exception,at.exception
assert any('手动方案检查通过' in s.value for s in at.success), [s.value for s in at.error]
at.multiselect(key='banned_days').set_value([1,2,3,4,5,6,7]).run()
assert any('重新生成' in s.value for s in at.info)
at.button(key='generate').click().run()
assert not at.exception,at.exception
assert len(at.error)>0
at.multiselect(key='courses').set_value(['MAT1001']).run()
at.button(key='generate').click().run()
assert any('学分' in s.value for s in at.error)
print('UI PASS: auto, manual, stale results, infeasible, credit validation')
