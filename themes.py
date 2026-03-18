"""
themes.py  (v6)
---------------
Color palettes and Plotly layout presets.
"BI" is the new default palette using the brand color system.
"""

import plotly.express as px

PALETTES: dict[str, list[str]] = {
    "BI"    : [
        "#6366F1", "#22C55E", "#F59E0B", "#EF4444",
        "#06B6D4", "#A855F7", "#F97316", "#14B8A6",
        "#8B5CF6", "#EC4899",
    ],
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


def get_layout(dark: bool = False, title: str = "") -> dict:
    """Return Plotly layout dict for update_layout(**get_layout(...))."""
    # Always transparent background so it inherits the page theme
    bg   = "rgba(0,0,0,0)"
    grid = "rgba(255,255,255,0.07)" if dark else "rgba(0,0,0,0.06)"
    font = "#e0e0e0"              if dark else "#374151"
    hover= "#1a1a2e"              if dark else "#1e293b"

    return dict(
        title         = dict(text=title, font=dict(size=14, color=font), x=0.02),
        font          = dict(family="Inter, system-ui, sans-serif", size=12, color=font),
        plot_bgcolor  = bg,
        paper_bgcolor = bg,
        hoverlabel    = dict(bgcolor=hover, font_color="white", font_size=13,
                             bordercolor="rgba(255,255,255,0.1)"),
        margin        = dict(t=20, b=55, l=55, r=20),
        legend        = dict(
            bgcolor     = "rgba(0,0,0,0.05)" if not dark else "rgba(255,255,255,0.05)",
            bordercolor = "rgba(0,0,0,0.08)" if not dark else "rgba(255,255,255,0.08)",
            borderwidth = 1,
            font        = dict(color=font, size=11),
        ),
        xaxis = dict(
            showgrid   = False,
            tickangle  = -30,
            color      = font,
            title_font = dict(color=font, size=11),
            linecolor  = "rgba(150,150,150,0.2)",
            tickfont   = dict(size=11),
        ),
        yaxis = dict(
            showgrid   = True,
            gridcolor  = grid,
            color      = font,
            title_font = dict(color=font, size=11),
            tickfont   = dict(size=11),
        ),
    )


def get_palette(name: str) -> list[str]:
    return PALETTES.get(name, PALETTES["BI"])
