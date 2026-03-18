import plotly.graph_objects as go
fig = go.Figure(data=[go.Bar(x=[1, 2, 3], y=[1, 3, 2])])
try:
    img_bytes = fig.to_image(format="png", width=1200, height=600, scale=2)
    print("SUCCESS: Generated", len(img_bytes), "bytes")
except Exception as e:
    import traceback
    print("ERROR:")
    traceback.print_exc()
