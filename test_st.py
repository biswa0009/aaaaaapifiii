import plotly.graph_objects as go
import streamlit as st

st.title("Test Kaleido")
fig = go.Figure(data=[go.Bar(x=[1, 2, 3], y=[1, 3, 2])])
try:
    img_bytes = fig.to_image(format="png", width=1200, height=600, scale=2)
    st.download_button("Download PNG", img_bytes, "test.png", "image/png")
    st.success("SUCCESS!")
except Exception as e:
    st.error(f"Failed: {e}")
