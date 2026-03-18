DARK_VARS = '''
  --bg-base: #050505; 
  --bg-gradient: radial-gradient(circle at 15% 50%, rgba(139, 92, 246, 0.08), transparent 25%), radial-gradient(circle at 85% 30%, rgba(168, 85, 247, 0.08), transparent 25%);
  --bg-card: rgba(15, 15, 15, 0.6); 
  --bg-card2: rgba(22, 22, 22, 0.7); 
  --bg-input: rgba(20, 20, 20, 0.8); 
  --border: rgba(255, 255, 255, 0.08); 
  --border-lite: rgba(255, 255, 255, 0.04); 
  --primary: #8B5CF6; 
  --primary-dark: #7C3AED; 
  --primary-glow: rgba(139, 92, 246, 0.4); 
  --success: #10B981; 
  --warning: #F59E0B; 
  --danger: #EF4444; 
  --cyan: #06B6D4; 
  --purple: #A855F7; 
  --text: #EDEDED; 
  --text-muted: #A1A1AA; 
  --text-dim: #71717A; 
  --shadow-sm: 0 4px 24px -1px rgba(0,0,0,0.4); 
  --shadow-md: 0 8px 32px -1px rgba(0,0,0,0.5); 
  --sidebar-bg: rgba(10, 10, 10, 0.65);
  --glass-blur: blur(16px);
'''

LIGHT_VARS = '''
  --bg-base: #F4F4F8;
  --bg-gradient: radial-gradient(circle at 15% 50%, rgba(124, 58, 237, 0.06), transparent 30%), radial-gradient(circle at 85% 30%, rgba(147, 51, 234, 0.06), transparent 30%);
  --bg-card: rgba(255, 255, 255, 0.95); 
  --bg-card2: rgba(241, 241, 247, 0.95); 
  --bg-input: #ffffff; 
  --border: rgba(0, 0, 0, 0.10); 
  --border-lite: rgba(0, 0, 0, 0.05); 
  --primary: #7C3AED; 
  --primary-dark: #6D28D9; 
  --primary-glow: rgba(124, 58, 237, 0.25); 
  --success: #059669; 
  --warning: #D97706; 
  --danger: #DC2626; 
  --cyan: #0891B2; 
  --purple: #9333EA; 
  --text: #1a1a2e; 
  --text-muted: #44445a; 
  --text-dim: #888899; 
  --shadow-sm: 0 4px 24px -1px rgba(0,0,0,0.07); 
  --shadow-md: 0 8px 32px -1px rgba(0,0,0,0.10); 
  --sidebar-bg: rgba(255, 255, 255, 0.92);
  --glass-blur: blur(16px);
'''

BASE_CSS = '''
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');

:root {
  --radius-sm: 10px;
  --radius-md: 16px;
  --radius-lg: 24px;
  --transition: all 0.25s cubic-bezier(0.2, 0.8, 0.2, 1);
}

/* ── Global base ─────────────────────────────────────────── */
html, body, .stApp,
[data-testid="stAppViewContainer"],
[data-testid="stVerticalBlock"],
[data-testid="stHorizontalBlock"],
[class*="css"] {
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif !important;
  background-color: var(--bg-base) !important;
  background-image: var(--bg-gradient) !important;
  background-attachment: fixed !important;
  color: var(--text) !important;
  -webkit-font-smoothing: antialiased;
}

/* Force all generic text spans/divs to use theme color */
.stApp p, .stApp span, .stApp div, .stApp label,
.stApp li, .stApp td, .stApp th,
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] span {
  color: var(--text) !important;
}

#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }
section[data-testid='stSidebar'] > div:first-child { padding-top: 0 !important; }
.block-container { padding: 2.5rem 2.5rem 4rem !important; max-width: 100% !important; }

/* ── Sidebar ─────────────────────────────────────────────── */
section[data-testid='stSidebar'] {
  background: var(--sidebar-bg) !important;
  backdrop-filter: var(--glass-blur) !important;
  -webkit-backdrop-filter: var(--glass-blur) !important;
  border-right: 1px solid var(--border) !important;
}
section[data-testid='stSidebar'] * { color: var(--text) !important; }
section[data-testid='stSidebar'] .stButton > button {
  width: 100% !important; text-align: left !important; justify-content: flex-start !important;
  padding: 10px 16px !important; background: transparent !important; border-color: transparent !important;
  border-radius: var(--radius-sm) !important; transition: var(--transition) !important;
  color: var(--text-muted) !important; font-size: 13px !important; font-weight: 500 !important;
  height: auto !important; min-height: 0 !important;
}
section[data-testid='stSidebar'] .stButton > button p {
  text-align: left !important; margin: 0 !important; width: 100% !important; color: var(--text-muted) !important;
}
section[data-testid='stSidebar'] .stButton > button:hover {
  background: var(--bg-card2) !important; border-color: var(--border) !important; color: var(--text) !important;
  transform: translateX(4px) !important;
}

.sb-brand {
  display: flex; align-items: center; gap: 14px; 
  padding: 32px 20px 24px; 
  border-bottom: 1px solid var(--border); 
  margin-bottom: 24px;
}
.sb-brand-icon {
  width: 44px; height: 44px; border-radius: 12px;
  background: linear-gradient(135deg, var(--primary), var(--purple));
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; flex-shrink: 0; box-shadow: 0 8px 16px var(--primary-glow);
}
.sb-brand-name { font-size: 18px; font-weight: 800; letter-spacing: -0.4px; color: var(--text) !important; }
.sb-brand-sub { font-size: 12px; color: var(--text-muted) !important; font-weight: 500; }

.sb-section-label { 
  font-size: 10.5px; font-weight: 800; letter-spacing: 1.5px; 
  color: var(--text-dim) !important; text-transform: uppercase; 
  padding: 16px 20px 10px; margin-top: 8px;
}

/* ── Query bar ───────────────────────────────────────────── */
.query-bar-wrapper {
  background: var(--bg-card) !important;
  backdrop-filter: var(--glass-blur) !important;
  -webkit-backdrop-filter: var(--glass-blur) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-lg) !important;
  padding: 24px 28px !important; margin-bottom: 32px !important; box-shadow: var(--shadow-sm) !important;
  position: relative; overflow: hidden;
}
.query-bar-wrapper::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px;
  background: linear-gradient(90deg, transparent, var(--primary), transparent); opacity: 0.3;
}
.query-bar-label { font-size: 11px; font-weight: 800; letter-spacing: 1.5px; color: var(--primary) !important; text-transform: uppercase; margin-bottom: 12px; display: block; }
.query-bar-wrapper [data-testid="column"] { display: flex !important; flex-direction: column !important; justify-content: center !important; }
.query-bar-wrapper .stButton, .query-bar-wrapper .stTextInput { margin: 0 !important; padding: 0 !important; }

/* ── Text inputs ─────────────────────────────────────────── */
.stTextInput [data-baseweb="input"],
[data-baseweb="input"] {
  background: var(--bg-input) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-md) !important;
  transition: var(--transition) !important;
  overflow: hidden;
}
.stTextInput [data-baseweb="input"]:focus-within,
[data-baseweb="input"]:focus-within {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 3px var(--primary-glow) !important;
}
.stTextInput input,
[data-baseweb="input"] input {
  color: var(--text) !important;
  background: transparent !important;
  font-size: 14px !important;
  font-weight: 500 !important;
  caret-color: var(--primary) !important;
}
.stTextInput input::placeholder,
[data-baseweb="input"] input::placeholder {
  color: var(--text-dim) !important;
  font-weight: 400 !important;
}
/* Password eye icon */
[data-testid="stInputPasswordEye"],
[data-testid="stInputPasswordEye"] > div {
  background: transparent !important;
  color: var(--text-muted) !important;
}
[data-testid="stInputPasswordEye"] svg { stroke: var(--text-muted) !important; fill: none !important; }

/* ── Buttons ─────────────────────────────────────────────── */
.stButton > button {
  background: var(--bg-card2) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important;
  font-weight: 600 !important;
  border-radius: var(--radius-md) !important;
  font-size: 14px !important;
  height: 48px !important;
  min-height: 48px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  transition: var(--transition) !important;
}
.stButton > button *, .stButton > button p {
  color: var(--text) !important;
  margin: 0 !important;
}
.stButton > button:hover {
  border-color: var(--primary) !important;
  background: rgba(124, 58, 237, 0.07) !important;
  color: var(--primary) !important;
  transform: translateY(-2px) !important;
}
.stButton > button:hover * { color: var(--primary) !important; }

/* Primary button override */
.stButton > button[kind='primary'],
.stButton > button[data-testid="baseButton-primary"] {
  background: linear-gradient(135deg, var(--primary), var(--primary-dark)) !important;
  border: none !important;
  color: #ffffff !important;
  font-weight: 600 !important;
  box-shadow: 0 8px 24px var(--primary-glow) !important;
}
.stButton > button[kind='primary'] *,
.stButton > button[data-testid="baseButton-primary"] * {
  color: #ffffff !important;
}
.stButton > button[kind='primary']:hover,
.stButton > button[data-testid="baseButton-primary"]:hover {
  box-shadow: 0 12px 32px var(--primary-glow) !important;
  color: #ffffff !important;
  background: linear-gradient(135deg, var(--primary), var(--primary-dark)) !important;
}
.stButton > button[kind='primary']:hover * { color: #ffffff !important; }

/* ── Radio buttons ───────────────────────────────────────── */
[data-testid="stRadio"] > div {
  background: var(--bg-card2) !important;
  border-radius: var(--radius-md) !important;
  padding: 6px 8px !important;
  gap: 4px !important;
  border: 1px solid var(--border) !important;
}
[data-testid="stRadio"] label {
  color: var(--text-muted) !important;
  font-size: 13px !important;
  font-weight: 500 !important;
  padding: 6px 14px !important;
  border-radius: var(--radius-sm) !important;
  transition: var(--transition) !important;
  cursor: pointer !important;
}
[data-testid="stRadio"] label:hover { color: var(--text) !important; background: var(--bg-card) !important; }
[data-testid="stRadio"] label[data-checked="true"],
[data-testid="stRadio"] label[aria-checked="true"] {
  background: var(--primary) !important;
  color: #ffffff !important;
}
[data-testid="stRadio"] label span { color: inherit !important; }
[data-testid="stRadio"] [data-baseweb="radio"] { display: none !important; }

/* ── Selectbox & Multiselect ─────────────────────────────── */
[data-baseweb="select"] > div,
[data-baseweb="select"] [data-baseweb="popover"] {
  background: var(--bg-input) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-md) !important;
  color: var(--text) !important;
}
[data-baseweb="select"] span,
[data-baseweb="select"] div { color: var(--text) !important; }
[data-baseweb="menu"] { background: var(--bg-card) !important; border: 1px solid var(--border) !important; border-radius: var(--radius-md) !important; }
[data-baseweb="menu"] li { color: var(--text) !important; }
[data-baseweb="menu"] li:hover { background: rgba(124, 58, 237, 0.08) !important; }

/* ── Toggle / checkbox ───────────────────────────────────── */
[data-testid="stToggle"] label span,
[data-testid="stCheckbox"] label span {
  color: var(--text) !important;
  font-size: 13px !important;
}

/* ── Sliders ─────────────────────────────────────────────── */
[data-testid="stSlider"] label, [data-testid="stSlider"] span {
  color: var(--text) !important;
}
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {
  background: var(--primary) !important;
  border-color: var(--primary) !important;
}

/* ── Expanders ───────────────────────────────────────────── */
[data-testid="stExpander"] {
  background: var(--bg-card) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-md) !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary svg {
  color: var(--text) !important;
  fill: var(--text) !important;
}
[data-testid="stExpander"] > div > div { color: var(--text) !important; }

/* ── Dataframe / Table ───────────────────────────────────── */
[data-testid="stDataFrame"] { border: 1px solid var(--border) !important; border-radius: var(--radius-md) !important; overflow: hidden; }
[data-testid="stDataFrame"] th { background: var(--bg-card2) !important; color: var(--text) !important; }
[data-testid="stDataFrame"] td { color: var(--text) !important; }

/* ── Metrics ─────────────────────────────────────────────── */
.chart-card, div[data-testid='metric-container'], .followup-card, .sql-card {
  background: var(--bg-card) !important;
  backdrop-filter: var(--glass-blur) !important;
  -webkit-backdrop-filter: var(--glass-blur) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-md) !important;
  box-shadow: var(--shadow-sm) !important;
  transition: var(--transition) !important;
}
.chart-card:hover, div[data-testid='metric-container']:hover {
  box-shadow: var(--shadow-md) !important;
  border-color: rgba(124,58,237,0.2) !important;
  transform: translateY(-4px) !important;
}
.chart-card { padding: 24px 24px 12px; margin-bottom: 24px; }
.chart-card-header { margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }
.chart-card-title { font-size: 15px; font-weight: 700; letter-spacing: -0.3px; color: var(--text) !important; }
.chart-card-badge { font-size: 10px; font-weight: 800; letter-spacing: 1px; padding: 4px 10px; border-radius: 20px; background: rgba(124, 58, 237, 0.1); color: var(--primary); border: 1px solid rgba(124, 58, 237, 0.2); text-transform: uppercase; }

div[data-testid='metric-container'] { padding: 24px !important; position: relative; overflow: hidden; }
div[data-testid='metric-container'] [data-testid='stMetricLabel'] { font-size: 11px !important; font-weight: 700 !important; letter-spacing: 1.2px !important; text-transform: uppercase !important; color: var(--text-muted) !important; }
div[data-testid='metric-container'] [data-testid='stMetricValue'] { font-size: 36px !important; font-weight: 800 !important; color: var(--text) !important; letter-spacing: -1.5px !important; margin-top: 4px !important; }

/* ── Page headings ───────────────────────────────────────── */
.page-title { font-size: 32px; font-weight: 800; color: var(--text) !important; letter-spacing: -1px; }
.page-subtitle { font-size: 16px; color: var(--text-muted) !important; margin-top: 8px; font-weight: 400; letter-spacing: -0.2px; }

/* ── Insight / Anomaly cards ─────────────────────────────── */
.insight-card {
  background: linear-gradient(145deg, rgba(124, 58, 237, 0.07), rgba(124, 58, 237, 0.01));
  border: 1px solid rgba(124, 58, 237, 0.2); border-left: 4px solid var(--primary);
  border-radius: var(--radius-md); padding: 28px 32px; margin: 24px 0;
  box-shadow: 0 10px 30px -5px rgba(124, 58, 237, 0.08);
}
.anomaly-card {
  background: linear-gradient(145deg, rgba(217, 119, 6, 0.07), rgba(217, 119, 6, 0.01));
  border: 1px solid rgba(217, 119, 6, 0.2); border-left: 4px solid var(--warning);
  border-radius: var(--radius-md); padding: 24px 28px; margin: 20px 0;
  box-shadow: 0 10px 30px -5px rgba(217, 119, 6, 0.08);
}
.insight-body, .anomaly-item { font-size: 15px; line-height: 1.8; color: var(--text) !important; font-weight: 400; letter-spacing: -0.2px; }
.insight-title { color: var(--primary) !important; font-size: 12px; font-weight: 800; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 12px; }
.anomaly-title { color: var(--warning) !important; font-size: 12px; font-weight: 800; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 12px; }

/* ── Tabs ────────────────────────────────────────────────── */
.stTabs [data-baseweb='tab-list'] { border-bottom: 2px solid var(--border) !important; gap: 32px !important; padding: 0 12px !important; background: transparent !important; }
[data-baseweb="tab-border"] { display: none !important; }
[data-baseweb="tab-highlight"] { background-color: var(--primary) !important; }
.stTabs [data-baseweb='tab'] { font-size: 14px !important; font-weight: 600 !important; letter-spacing: 0.5px !important; padding: 16px 0 !important; color: var(--text-muted) !important; transition: var(--transition) !important; background: transparent !important; }
.stTabs [data-baseweb='tab']:hover { color: var(--text) !important; }
.stTabs [aria-selected='true'] { color: var(--primary) !important; border-bottom-color: var(--primary) !important; }

/* ── Empty state ─────────────────────────────────────────── */
.empty-state { padding: 100px 24px; text-align: center; }
.empty-icon { font-size: 64px; animation: float 6s ease-in-out infinite; filter: drop-shadow(0 0 24px rgba(124, 58, 237, 0.4)); margin-bottom: 24px; color: var(--primary) !important; }
@keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-15px); } }
.empty-title { font-size: 28px; font-weight: 800; letter-spacing: -1px; color: var(--text) !important; margin-bottom: 12px; }
.empty-sub { font-size: 16px; color: var(--text-muted) !important; max-width: 480px; margin: 0 auto; line-height: 1.6; }

/* ── Chips ───────────────────────────────────────────────── */
.chip { background: var(--bg-card2); border: 1px solid var(--border); border-radius: 32px; padding: 8px 20px; font-size: 13.5px; margin: 6px; display: inline-block; transition: var(--transition); font-weight: 600; cursor: pointer; color: var(--text-muted); }
.chip:hover { border-color: var(--primary); background: rgba(124, 58, 237, 0.08); color: var(--primary); transform: translateY(-2px); box-shadow: 0 4px 12px rgba(124, 58, 237, 0.15); }

/* ── Progress ────────────────────────────────────────────── */
.stProgress > div > div > div > div { background: linear-gradient(90deg, var(--primary), var(--primary-dark)) !important; border-radius: 8px !important; }
.stProgress > div > div { background: var(--border) !important; border-radius: 8px !important; height: 8px !important; }

/* ── Dividers & selects ──────────────────────────────────── */
hr { border-color: var(--border) !important; margin: 32px 0 !important; opacity: 0.5; }

/* ── Drilldown / section labels ──────────────────────────── */
.section-label { font-size: 14px; font-weight: 700; color: var(--text) !important; margin: 24px 0 12px; letter-spacing: -0.2px; }
.drill-card { padding: 12px 20px; background: var(--bg-card2) !important; border: 1px solid var(--border) !important; border-radius: var(--radius-md); margin-bottom: 16px; font-size: 14px; color: var(--text-muted) !important; }
.drill-card strong { color: var(--text) !important; }
.sql-card { padding: 0; overflow: hidden; }
.sql-card-header { background: var(--bg-card2) !important; padding: 12px 20px; font-size: 12px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: var(--text-muted) !important; border-bottom: 1px solid var(--border); }
.sql-card-body { padding: 16px 20px; font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 13px; line-height: 1.7; color: var(--text) !important; white-space: pre-wrap; word-break: break-all; }

/* ── Warning / info text ─────────────────────────────────── */
[data-testid="stAlert"] { background: var(--bg-card) !important; border-color: var(--border) !important; }
[data-testid="stAlert"] * { color: var(--text) !important; }

/* ── Responsive ──────────────────────────────────────────── */
@media screen and (max-width: 768px) {
  .block-container { padding: 1.5rem 1.25rem 3rem !important; }
  .page-title { font-size: 24px; letter-spacing: -0.5px; }
  .page-subtitle { font-size: 14px; margin-top: 4px; }
  .query-bar-wrapper { padding: 20px !important; margin-bottom: 24px !important; border-radius: var(--radius-md) !important; }
  .stButton > button[kind='primary'] { font-size: 14px !important; padding: 0 20px !important; }
  .chart-card { padding: 16px 16px 8px; margin-bottom: 16px; }
  div[data-testid='metric-container'] { padding: 16px !important; }
  div[data-testid='metric-container'] [data-testid='stMetricValue'] { font-size: 28px !important; }
  .insight-card { padding: 20px 24px; margin: 16px 0; }
  .anomaly-card { padding: 16px 20px; margin: 16px 0; }
  .stTabs [data-baseweb='tab-list'] { gap: 16px !important; flex-wrap: nowrap !important; overflow-x: auto !important; -webkit-overflow-scrolling: touch; }
  .empty-state { padding: 60px 16px; }
  .empty-title { font-size: 22px; }
  .sb-brand { padding: 24px 16px 16px; flex-direction: column; align-items: flex-start; gap: 8px; }
}
'''

def get_css(theme: str = "dark") -> str:
    v = DARK_VARS if theme == "dark" else LIGHT_VARS
    return f"<style>:root{{{v}}}{BASE_CSS}</style>"

# Backwards-compat alias used by old code
CSS = get_css("dark")
