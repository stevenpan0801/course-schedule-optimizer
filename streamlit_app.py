"""Streamlit Cloud entry point for the current 2.1 application."""
from pathlib import Path
import runpy
import sys

APP_DIR = Path(__file__).resolve().parent / "Course Schedule Optimization_2.1"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
runpy.run_path(str(APP_DIR / "app.py"), run_name="__main__")
