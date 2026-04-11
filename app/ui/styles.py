import streamlit as st


# Dark design tokens
#   bg        #0f172a (slate-900)
#   panel     #1e293b (slate-800)
#   border    #334155 (slate-700)
#   text      #f1f5f9 (slate-100)
#   muted     #94a3b8 (slate-400)
#   primary   #3b82f6 (blue-500)

_GLOBAL_STYLES = """
<style>
/* ── Hide Streamlit chrome ─────────────────────────────────────────── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; height: 0; }

/* ── Global typography ─────────────────────────────────────────────── */
/* NOTE: do NOT match [class*="st-"] here — that would clobber the
   Material Symbols font on Streamlit's icon elements (avatars,
   dropdown chevrons, etc.), leaking raw ligature text like
   "smart_toy" / "arrow_drop_down". */
html, body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
}

/* Make sure Material Symbols icons always render as icons, even if
   some other rule tries to set a text font on their container. */
.material-symbols-rounded,
.material-symbols-outlined,
[data-testid="stIconMaterial"],
span[data-testid*="Icon"] {
    font-family: "Material Symbols Rounded", "Material Symbols Outlined",
        "Material Icons" !important;
    font-feature-settings: "liga";
}

/* ── Main content container ────────────────────────────────────────── */
.main .block-container {
    padding-top: 2.25rem;
    padding-bottom: 7rem;
    max-width: 820px;
}

/* ── Hero header ───────────────────────────────────────────────────── */
.wf-hero {
    padding: 0 0 1.25rem 0;
    margin-bottom: 1.5rem;
    border-bottom: 1px solid #334155;
}
.wf-hero-title {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-size: 1.85rem;
    font-weight: 700;
    letter-spacing: -0.025em;
    color: #f1f5f9;
    margin: 0 0 0.35rem 0;
}
.wf-hero-icon {
    font-size: 1.7rem;
}
.wf-hero-subtitle {
    font-size: 0.93rem;
    color: #94a3b8;
    margin: 0;
    font-weight: 400;
}

/* ── Chat input ────────────────────────────────────────────────────── */
[data-testid="stChatInput"] {
    border-radius: 14px;
    border: 1px solid #334155;
    background: #1e293b;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.25);
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
[data-testid="stChatInput"]:focus-within {
    border-color: #3b82f6;
    box-shadow: 0 2px 16px rgba(59, 130, 246, 0.15);
}

/* ── Sidebar ───────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #0b1220;
    border-right: 1px solid #334155;
}
[data-testid="stSidebar"] .block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
}

/* Sidebar brand */
.wf-brand {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    font-size: 1.1rem;
    font-weight: 700;
    color: #f1f5f9;
    letter-spacing: -0.015em;
    padding-bottom: 1rem;
    margin-bottom: 0.5rem;
    border-bottom: 1px solid #334155;
}
.wf-brand-icon {
    font-size: 1.25rem;
}

/* Sidebar section label */
.wf-label {
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.09em;
    color: #94a3b8;
    text-transform: uppercase;
    margin: 1.1rem 0 0.45rem 0.15rem;
}

/* Sidebar card */
.wf-card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 0.85rem 0.95rem;
    margin-bottom: 0.6rem;
}
.wf-card-title {
    font-size: 0.93rem;
    font-weight: 600;
    color: #f1f5f9;
    margin: 0;
}
.wf-card-meta {
    font-size: 0.76rem;
    color: #94a3b8;
    margin-top: 0.2rem;
}

/* ── Sidebar buttons ───────────────────────────────────────────────── */
[data-testid="stSidebar"] button {
    border-radius: 9px;
    transition: all 0.15s ease;
    font-size: 0.88rem;
    font-weight: 500;
}
[data-testid="stSidebar"] button[kind="secondary"] {
    border: 1px solid #334155;
    background: #1e293b;
    color: #e2e8f0;
}
[data-testid="stSidebar"] button[kind="secondary"]:hover {
    border-color: #3b82f6;
    color: #93c5fd;
    background: #1e3a8a33;
}

/* ── Inputs in sidebar ─────────────────────────────────────────────── */
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    border-radius: 9px !important;
    background: #1e293b !important;
    color: #f1f5f9 !important;
    border-color: #334155 !important;
}

/* ── Sidebar dividers (softer) ─────────────────────────────────────── */
[data-testid="stSidebar"] hr {
    margin: 1rem 0;
    border: none;
    border-top: 1px solid #334155;
}

/* ── Alerts ────────────────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: 10px;
    border: 1px solid #334155;
    padding: 0.7rem 0.9rem;
    font-size: 0.87rem;
}

/* ── Metric ────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 0.9rem 1rem;
}
[data-testid="stMetricLabel"] {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #94a3b8;
    font-weight: 600;
}
[data-testid="stMetricValue"] {
    color: #f1f5f9;
    font-weight: 700;
    font-size: 1.75rem;
}

/* ── Expander ──────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    border: 1px solid #334155;
    border-radius: 10px;
    background: #1e293b;
}
[data-testid="stExpander"] summary {
    font-size: 0.85rem;
    font-weight: 500;
    color: #cbd5e1;
}

/* ── Streaming cursor ──────────────────────────────────────────────── */
.streaming-response {
    white-space: pre-wrap;
    line-height: 1.65;
    font-family: inherit;
}
.blinking-cursor {
    display: inline-block;
    margin-left: 2px;
    animation: blink 1s steps(1) infinite;
    color: #3b82f6;
    font-weight: bold;
}
@keyframes blink {
    50% { opacity: 0; }
}
</style>
"""


def inject_global_styles() -> None:
    st.html(_GLOBAL_STYLES)
