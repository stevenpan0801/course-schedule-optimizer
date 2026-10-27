# Course Schedule Optimizer

在线使用：[打开选课规划网站](https://cuhksz-course-optimizer.streamlit.app/)

当前线上版本：2.1。选择课程、设置偏好后即可生成课表，无需本地安装。

一个基于 Python、Streamlit 和 SQLite 的课程表优化项目，
以香港中文大学（深圳）的课程数据为应用场景。

用户选择课程并输入早八、星期和教师偏好后，
系统自动搜索班级组合，输出推荐课表，
并通过独立检查器验证方案的可行性。

## Features

- 按课程代码自动选择 Lecture、Tutorial 等所需班级
- 支持 0–5 分的早八、星期和教师偏好
- 支持禁止早八、指定禁排日和禁排时段
- 保留 12–18 学分限制
- 使用回溯搜索与分支定界生成最多三个推荐方案
- 独立检查课程组件、教学日期、时间冲突及禁排要求
- 支持手动调整、课表展示和 CSV / JSON 导出

## Project Status

目前为课程项目原型，已完成核心算法及界面流程测试。

搜索完成时，结果在当前数据、约束和评分规则下最优；
搜索超时时，仅展示当前找到的最佳方案。

系统尚未接入学校选课系统，不执行实际选课操作。
当前数据库未提供的班级绑定关系和个人先修要求不在验证范围内。

## 本地启动与云端部署

在仓库根目录执行：

```bash
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

Streamlit Community Cloud 新建应用时，选择 `main` 分支、入口 `streamlit_app.py`、Python 3.13。根目录入口加载 `Course Schedule Optimization_2.1/app.py`，数据库由该版本目录读取。
