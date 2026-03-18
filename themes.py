"""
themes.py (v7)
---------------
Theme variables and Plotly presets.
"""

import plotly.express as px

PALETTES: dict[str, list[str]] = {
    "BI"    : ["#6366F1", "#22C55E", "#F59E0B", "#EF4444", "#06B6D4", "#A855F7", "#F97316", "#14B8A6", "#8B5CF6", "#EC4899"],
    "Bold"  : px.colors.qualitative.Bold,
    "Vivid" : px.colors.qualitative.Vivid,
    "Pastel": px.colors.qualitative.Pastel,
    "Dark24": px.colors.qualitative.Dark24,
    "Set3"  : px.colors.qualitative.Set3,
    "Neon"  : ["#FF006E", "#FB5607", "#FFBE0B", "#3A86FF", "#8338EC", "#06D6A0", "#FF595E", "#1982C4"],
}

THEME_VARS = {
    "dark": {
        "bg-base": "#050505",
        "bg-gradient": "radial-gradient(circle at 15% 50%, rgba(139, 92, 246, 0.08), transparent 25%), radial-gradient(circle at 85% 30%, rgba(168, 85, 247, 0.08), transparent 25%)",
        "bg-card": "rgba(15, 15, 15, 0.6)",
        "bg-card2": "rgba(22, 22, 22, 0.7)",
        "bg-input": "rgba(20, 20, 20, 0.8)",
        "border": "rgba(255, 255, 255, 0.08)",
        "border-lite": "rgba(255, 255, 255, 0.04)",
        "primary": "#8B5CF6",
        "primary-dark": "#7C3AED",
        "primary-glow": "rgba(139, 92, 246, 0.4)",
        "primary-01": "rgba(139, 92, 246, 0.01)",
        "primary-05": "rgba(139, 92, 246, 0.05)",
        "primary-07": "rgba(139, 92, 246, 0.07)",
        "primary-08": "rgba(139, 92, 246, 0.08)",
        "primary-10": "rgba(139, 92, 246, 0.10)",
        "primary-15": "rgba(139, 92, 246, 0.15)",
        "primary-20": "rgba(139, 92, 246, 0.20)",
        "success": "#10B981",
        "warning": "#F59E0B",
        "warning-01": "rgba(245, 158, 11, 0.01)",
        "warning-07": "rgba(245, 158, 11, 0.07)",
        "warning-08": "rgba(245, 158, 11, 0.08)",
        "warning-20": "rgba(245, 158, 11, 0.20)",
        "danger": "#EF4444",
        "cyan": "#06B6D4",
        "purple": "#A855F7",
        "text": "#EDEDED",
        "text-muted": "#A1A1AA",
        "text-dim": "#71717A",
        "shadow-sm": "0 4px 24px -1px rgba(0,0,0,0.4)",
        "shadow-md": "0 8px 32px -1px rgba(0,0,0,0.5)",
        "sidebar-bg": "rgba(10, 10, 10, 0.65)",
        "glass-blur": "blur(16px)"
    },
    "light": {
        "bg-base": "#F4F4F8",
        "bg-gradient": "radial-gradient(circle at 15% 50%, rgba(124, 58, 237, 0.06), transparent 30%), radial-gradient(circle at 85% 30%, rgba(147, 51, 234, 0.06), transparent 30%)",
        "bg-card": "rgba(255, 255, 255, 0.95)",
        "bg-card2": "rgba(241, 241, 247, 0.95)",
        "bg-input": "#ffffff",
        "border": "rgba(0, 0, 0, 0.10)",
        "border-lite": "rgba(0, 0, 0, 0.05)",
        "primary": "#7C3AED",
        "primary-dark": "#6D28D9",
        "primary-glow": "rgba(124, 58, 237, 0.25)",
        "primary-01": "rgba(124, 58, 237, 0.01)",
        "primary-05": "rgba(124, 58, 237, 0.05)",
        "primary-07": "rgba(124, 58, 237, 0.07)",
        "primary-08": "rgba(124, 58, 237, 0.08)",
        "primary-10": "rgba(124, 58, 237, 0.10)",
        "primary-15": "rgba(124, 58, 237, 0.15)",
        "primary-20": "rgba(124, 58, 237, 0.20)",
        "success": "#059669",
        "warning": "#D97706",
        "warning-01": "rgba(217, 119, 6, 0.01)",
        "warning-07": "rgba(217, 119, 6, 0.07)",
        "warning-08": "rgba(217, 119, 6, 0.08)",
        "warning-20": "rgba(217, 119, 6, 0.20)",
        "danger": "#DC2626",
        "cyan": "#0891B2",
        "purple": "#9333EA",
        "text": "#1a1a2e",
        "text-muted": "#44445a",
        "text-dim": "#888899",
        "shadow-sm": "0 4px 24px -1px rgba(0,0,0,0.07)",
        "shadow-md": "0 8px 32px -1px rgba(0,0,0,0.10)",
        "sidebar-bg": "rgba(255, 255, 255, 0.92)",
        "glass-blur": "blur(16px)"
    }
}

def get_layout(dark: bool = False, title: str = "") -> dict:
    bg   = "rgba(0,0,0,0)"
    vars = THEME_VARS["dark" if dark else "light"]
    font_color = vars["text"]
    grid_color = vars["border-lite"]
    hover_bg   = vars["bg-card2"]

    return dict(
        title         = dict(text=title, font=dict(size=14, color=font_color), x=0.02),
        font          = dict(family="Plus Jakarta Sans, system-ui, sans-serif", size=12, color=font_color),
        plot_bgcolor  = bg,
        paper_bgcolor = bg,
        hoverlabel    = dict(bgcolor=hover_bg, font_color=font_color, font_size=13, bordercolor=vars["border"]),
        margin        = dict(t=20, b=55, l=55, r=20),
        legend        = dict(bgcolor="rgba(0,0,0,0.05)", bordercolor=vars["border"], borderwidth=1, font=dict(color=font_color, size=11)),
        xaxis = dict(showgrid=False, tickangle=-30, color=font_color, linecolor=vars["border"]),
        yaxis = dict(showgrid=True, gridcolor=grid_color, color=font_color),
    )

def get_palette(name: str) -> list[str]:
    return PALETTES.get(name, PALETTES["BI"])
