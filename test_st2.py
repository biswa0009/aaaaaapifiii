import streamlit as st
import plotly.graph_objects as go
from exports import png_download_button
import traceback

st.title("Testing PNG Download under Streamlit")
fig = go.Figure(data=[go.Bar(x=[1, 2, 3], y=[1, 3, 2])])
try:
    png_download_button(fig)
    print("Test ST: png_download_button finished without explicit throw")
except Exception as e:
    print(f"Test ST Error: {e}")
