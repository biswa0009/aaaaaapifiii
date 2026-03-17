"""
themes.py
---------
Color palettes and layout presets for every chart in the dashboard.
All chart builders import from here so themes stay consistent.
"""

import plotly.express as px

# ── Named palettes ────────────────────────────────────────────────────────────
PALETTES: dict[str, list[str]] = {
    "Bold"  : px.colors.qualitative.Bold,
    "Vivid" : px.colors.qualitative.Vivid,
    "Pastel": px.colors.qualitative.Pastel,
    "Dark24": px.colors.qualitative.Dark24,
    "Set3"  : px.colors.qualitative.Set3,
    "Neon"  : [
        "#FF006E", "#FB5607", "#FFBE0B", "#3A86FF",
        "#8338EC", "#06D6A0", "#FF595E", "#1982C4",
    ],
}

# ── Dark-mode palette overrides ───────────────────────────────────────────────
_DARK_BG    = "#0e1117"
_DARK_GRID  = "rgba(255,255,255,0.07)"
_DARK_FONT  = "#e0e0e0"
_DARK_HOVER = "#1a1a2e"

_LIGHT_BG    = "rgba(0,0,0,0)"
_LIGHT_GRID  = "rgba(150,150,150,0.18)"
_LIGHT_FONT  = "#2d2d4e"
_LIGHT_HOVER = "#1e1e2e"


# ── Public: layout dict for update_layout() ───────────────────────────────────
def get_layout(dark: bool = False, title: str = "") -> dict:
    """
    Return a Plotly layout dict.
    Pass directly to fig.update_layout(**get_layout(...)).
    """
    bg    = _DARK_BG    if dark else _LIGHT_BG
    grid  = _DARK_GRID  if dark else _LIGHT_GRID
    font  = _DARK_FONT  if dark else _LIGHT_FONT
    hover = _DARK_HOVER if dark else _LIGHT_HOVER

    return dict(
        title         = dict(text=title, font=dict(size=15, color=font), x=0.03),
        font          = dict(family="Inter, system-ui, sans-serif", size=12, color=font),
        plot_bgcolor  = bg,
        paper_bgcolor = bg,
        hoverlabel    = dict(bgcolor=hover, font_color="white", font_size=13),
        margin        = dict(t=55, b=60, l=60, r=30),
        legend        = dict(
            bgcolor     = "rgba(30,30,30,0.5)" if dark else "rgba(255,255,255,0.85)",
            bordercolor = "rgba(255,255,255,0.15)" if dark else "rgba(0,0,0,0.1)",
            borderwidth = 1,
            font        = dict(color=font),
        ),
        xaxis = dict(
            showgrid   = False,
            tickangle  = -30,
            color      = font,
            title_font = dict(color=font, size=12),
            linecolor  = "rgba(150,150,150,0.3)",
        ),
        yaxis = dict(
            showgrid  = True,
            gridcolor = grid,
            color     = font,
            title_font= dict(color=font, size=12),
        ),
    )


def get_palette(name: str) -> list[str]:
    return PALETTES.get(name, PALETTES["Bold"])
