from pathlib import Path
import sys

import pandas as pd
import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "dashboard"))

from pages_top import voc_quality_view as view


view._render_voc_design_system()
view._render_voc_page_header("품질 평가 기준")
with st.container(key="voc_page_content"):
    st.metric("평가 총점", "100점")
    st.text_input("기준명", value="VOC 품질 평가")
    st.dataframe(pd.DataFrame([{"항목": "정확성", "배점": 25}]), hide_index=True)
