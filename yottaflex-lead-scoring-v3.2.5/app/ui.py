"""YottaFlex design system (V3.2.5).

Reusable tokens and Streamlit component helpers implementing the premium dark
enterprise design language:

  Background    #080D1B / #0D1528       Cards   #111E38 / elevated #17284A
  Accents       #3B82F6 / #6366F1 / AI #8B5CF6
  Status        success #22C55E · warning #F59E0B · danger #EF4444
  Text          #F8FAFC primary · #94A3B8 secondary
  Borders       rgba(148, 163, 184, 0.16)

All components render from real data supplied by callers; this module contains
no business logic and performs no data access.
"""

from __future__ import annotations

import html
from typing import Iterable

import streamlit as st

BG = "#080D1B"
BG_SOFT = "#0D1528"
CARD = "#111E38"
CARD_ELEVATED = "#17284A"
ACCENT = "#3B82F6"
ACCENT_2 = "#6366F1"
AI = "#8B5CF6"
SUCCESS = "#22C55E"
WARNING = "#F59E0B"
DANGER = "#EF4444"
TEXT = "#F8FAFC"
MUTED = "#94A3B8"
BORDER = "rgba(148, 163, 184, 0.16)"

SEVERITY_COLOR = {"critical": DANGER, "high": WARNING, "medium": ACCENT, "low": MUTED}
CATEGORY_COLOR = {"hot": DANGER, "warm": WARNING, "nurture": ACCENT, "cold": MUTED}
STAGE_COLOR = {
    "new_lead": MUTED,
    "qualified": ACCENT,
    "demo": ACCENT_2,
    "proposal": AI,
    "won": SUCCESS,
    "lost": DANGER,
}
STATUS_COLOR = {"pending": WARNING, "blocked": DANGER, "completed": SUCCESS}


def esc(value: object) -> str:
    return html.escape(str(value))


def inject_css() -> None:
    """Global stylesheet: tokens, typography, cards, controls, motion, responsive."""
    st.markdown(
        f"""
        <style>
        :root {{
          --yf-bg: {BG}; --yf-bg-soft: {BG_SOFT}; --yf-card: {CARD};
          --yf-card-2: {CARD_ELEVATED}; --yf-accent: {ACCENT}; --yf-accent-2: {ACCENT_2};
          --yf-ai: {AI}; --yf-success: {SUCCESS}; --yf-warning: {WARNING};
          --yf-danger: {DANGER}; --yf-text: {TEXT}; --yf-muted: {MUTED};
          --yf-border: {BORDER}; --yf-radius: 14px;
        }}
        html, body, [class*="css"], [data-testid="stAppViewContainer"] {{
          font-family: Inter, "Segoe UI", -apple-system, "SF Pro Text", Roboto, sans-serif;
          color: var(--yf-text);
        }}
        [data-testid="stAppViewContainer"] {{
          background:
            radial-gradient(1100px 480px at 85% -10%, rgba(59,130,246,0.10), transparent 60%),
            radial-gradient(900px 420px at 0% 0%, rgba(139,92,246,0.07), transparent 55%),
            var(--yf-bg);
        }}
        .block-container {{padding-top: 1.1rem; padding-bottom: 2.2rem; max-width: 1500px;}}
        div[data-testid="stVerticalBlock"] {{gap: 0.7rem;}}
        h1, h2, h3, h4 {{letter-spacing: -0.01em;}}
        h3 {{margin-bottom: 0.1rem;}}

        /* ---- sidebar ---- */
        section[data-testid="stSidebar"] {{
          background: var(--yf-bg-soft);
          border-right: 1px solid var(--yf-border);
        }}
        section[data-testid="stSidebar"] .block-container {{padding-top: 1.2rem;}}
        section[data-testid="stSidebar"] div[role="radiogroup"] label {{
          padding: 0.42rem 0.6rem; border-radius: 10px; width: 100%;
          transition: background 140ms ease, transform 140ms ease;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{
          background: rgba(59,130,246,0.10); transform: translateX(2px);
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {{
          background: linear-gradient(90deg, rgba(59,130,246,0.22), rgba(99,102,241,0.12));
          border: 1px solid rgba(59,130,246,0.35);
        }}

        /* ---- cards around widgets ---- */
        div[data-testid="stVerticalBlockBorderWrapper"] {{
          background: var(--yf-card); border: 1px solid var(--yf-border);
          border-radius: var(--yf-radius); padding: 0.35rem 0.6rem;
          transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
        }}
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {{
          transform: translateY(-1px); border-color: rgba(59,130,246,0.35);
          box-shadow: 0 8px 26px rgba(2, 6, 23, 0.55);
        }}

        /* ---- buttons / inputs ---- */
        .stButton > button, .stDownloadButton > button {{
          border-radius: 10px; border: 1px solid rgba(59,130,246,0.45);
          background: linear-gradient(180deg, rgba(59,130,246,0.20), rgba(59,130,246,0.10));
          color: var(--yf-text); font-weight: 600; transition: all 150ms ease;
        }}
        .stButton > button:hover, .stDownloadButton > button:hover {{
          border-color: var(--yf-accent); transform: translateY(-1px);
          box-shadow: 0 6px 18px rgba(59,130,246,0.25);
        }}
        [data-testid="stTextInput"] input, [data-testid="stSelectbox"] div[data-baseweb="select"],
        [data-testid="stMultiSelect"] div[data-baseweb="select"] {{
          background: var(--yf-bg-soft); border-radius: 10px;
        }}

        /* ---- tables ---- */
        [data-testid="stDataFrame"] {{border: 1px solid var(--yf-border); border-radius: 12px;}}
        [data-testid="stDataFrame"] [role="row"]:hover {{background: rgba(59,130,246,0.08) !important;}}

        /* ---- plotly containers ---- */
        [data-testid="stPlotlyChart"] {{
          background: var(--yf-card); border: 1px solid var(--yf-border);
          border-radius: var(--yf-radius); padding: 0.4rem 0.5rem 0.1rem;
        }}

        /* ---- hide default streamlit chrome for a clean app-like look ---- */
        [data-testid="stToolbar"] {{visibility: hidden;}}
        [data-testid="stDecoration"] {{display: none;}}

        /* ---- html components ---- */
        .yf-kpi-grid {{display: flex; flex-wrap: wrap; gap: 0.7rem;}}
        .yf-kpi {{
          flex: 1 1 170px; min-width: 150px; background: var(--yf-card);
          border: 1px solid var(--yf-border); border-radius: var(--yf-radius);
          padding: 0.85rem 0.95rem; animation: yf-fade 320ms ease both;
          transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
        }}
        .yf-kpi:hover {{transform: translateY(-2px); border-color: rgba(59,130,246,0.40);
          box-shadow: 0 10px 26px rgba(2,6,23,0.55);}}
        .yf-kpi .label {{font-size: 0.72rem; color: var(--yf-muted); text-transform: uppercase;
          letter-spacing: 0.055em; font-weight: 600;}}
        .yf-kpi .value {{font-size: 1.55rem; font-weight: 700; margin-top: 0.22rem; line-height: 1.15;}}
        .yf-kpi .sub {{font-size: 0.74rem; color: var(--yf-muted); margin-top: 0.28rem;}}
        .yf-kpi .accent-bar {{height: 3px; border-radius: 2px; margin-top: 0.55rem;
          background: linear-gradient(90deg, var(--bar, {ACCENT}), transparent);}}

        .yf-badge {{display: inline-block; padding: 0.08rem 0.5rem; border-radius: 999px;
          font-size: 0.7rem; font-weight: 600; border: 1px solid; margin-right: 0.3rem;}}
        .yf-chip {{display: inline-block; padding: 0.22rem 0.65rem; border-radius: 999px;
          font-size: 0.74rem; color: var(--yf-muted); border: 1px solid var(--yf-border);
          background: rgba(13,21,40,0.8); margin-right: 0.35rem;}}

        .yf-insight {{background: linear-gradient(180deg, rgba(139,92,246,0.10), rgba(17,30,56,0.9));
          border: 1px solid rgba(139,92,246,0.30); border-radius: var(--yf-radius);
          padding: 0.8rem 0.9rem; margin-bottom: 0.6rem; animation: yf-fade 380ms ease both;}}
        .yf-insight .kind {{font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.07em;
          color: #C4B5FD; font-weight: 700;}}
        .yf-insight .title {{font-size: 0.95rem; font-weight: 650; margin-top: 0.2rem;}}
        .yf-insight .body {{font-size: 0.8rem; color: #CBD5E1; margin-top: 0.3rem; line-height: 1.45;}}
        .yf-insight .foot {{font-size: 0.7rem; color: var(--yf-muted); margin-top: 0.4rem;}}

        .yf-progress {{height: 6px; background: rgba(148,163,184,0.15); border-radius: 4px; overflow: hidden;}}
        .yf-progress > div {{height: 100%; border-radius: 4px;
          transition: width 500ms cubic-bezier(0.22, 1, 0.36, 1);}}

        .yf-empty {{border: 1px dashed var(--yf-border); border-radius: var(--yf-radius);
          padding: 1.1rem; text-align: center; color: var(--yf-muted); font-size: 0.85rem;
          background: rgba(13,21,40,0.5);}}
        .yf-section {{display: flex; align-items: baseline; gap: 0.6rem; margin: 0.2rem 0 0.1rem;}}
        .yf-section .t {{font-size: 1.12rem; font-weight: 700;}}
        .yf-section .c {{font-size: 0.78rem; color: var(--yf-muted);}}
        .yf-header {{display: flex; flex-wrap: wrap; align-items: center; gap: 0.7rem;
          padding: 0.4rem 0 0.7rem; border-bottom: 1px solid var(--yf-border); margin-bottom: 0.6rem;}}
        .yf-brand {{display: flex; align-items: center; gap: 0.6rem;}}
        .yf-brand .logo {{width: 34px; height: 34px; border-radius: 10px;
          background: linear-gradient(135deg, {ACCENT}, {AI});
          display: flex; align-items: center; justify-content: center;
          font-weight: 800; font-size: 0.95rem; color: white;}}
        .yf-brand .name {{font-size: 1.02rem; font-weight: 750;}}
        .yf-brand .tag {{font-size: 0.7rem; color: var(--yf-muted);}}

        @keyframes yf-fade {{from {{opacity: 0; transform: translateY(4px);}} to {{opacity: 1; transform: none;}}}}

        @media (max-width: 900px) {{
          .block-container {{padding-left: 0.8rem; padding-right: 0.8rem;}}
          .yf-kpi {{flex: 1 1 44%;}}
          .yf-kpi .value {{font-size: 1.3rem;}}
        }}
        @media (max-width: 560px) {{
          .yf-kpi {{flex: 1 1 100%;}}
        }}

        /* ---- top pill navigation (segmented control, always-rendered) ---- */
        [data-testid="stSegmentedControl"] {{gap: 0.3rem;}}
        [data-testid="stSegmentedControl"] button {{
          font-weight: 600; font-size: 0.82rem; border-radius: 999px;
          padding: 0.28rem 0.85rem; transition: all 140ms ease;
        }}
        [data-testid="stSegmentedControl"] button[aria-checked="true"],
        [data-testid="stSegmentedControl"] button[kind="segmentedActive"] {{
          background: linear-gradient(180deg, #3B82F6, #2563EB);
          color: #ffffff; border-color: #3B82F6;
          box-shadow: 0 6px 18px rgba(59,130,246,0.35);
        }}

        /* ---- previous pills styling kept for any st.pills usage ---- */
        [data-testid="stPills"] {{gap: 0.35rem;}}
        [data-testid="stPills"] button {{
          border: 1px solid transparent; border-radius: 999px; background: transparent;
          color: var(--yf-muted); padding: 0.30rem 0.95rem; font-weight: 600; font-size: 0.84rem;
          transition: all 140ms ease;
        }}
        [data-testid="stPills"] button:hover {{color: var(--yf-text); background: rgba(59,130,246,0.10);}}
        [data-testid="stPills"] button[kind="pillsActive"],
        [data-testid="stPills"] button[aria-checked="true"],
        [data-testid="stPills"] button[kind="pills"][aria-pressed="true"] {{
          background: linear-gradient(180deg, #3B82F6, #2563EB); color: #fff;
          border-color: #3B82F6; box-shadow: 0 6px 18px rgba(59,130,246,0.35);
        }}

        /* ---- kanban deal board ---- */
        .yf-board {{display: flex; gap: 0.85rem; align-items: flex-start; flex-wrap: wrap;}}
        .yf-col {{
          flex: 1 1 215px; min-width: 205px; border-radius: 16px; padding: 0.7rem 0.7rem 0.85rem;
          background: linear-gradient(180deg, rgba(23,40,74,0.60), rgba(13,21,40,0.75));
          border: 1px solid var(--yf-border); animation: yf-fade 380ms ease both;
        }}
        .yf-col .head {{display: flex; justify-content: space-between; align-items: baseline;}}
        .yf-col .head .t {{font-weight: 700; font-size: 0.92rem;}}
        .yf-col .head .a {{color: var(--yf-muted); font-size: 0.74rem;}}
        .yf-deal {{
          background: linear-gradient(180deg, #141F3A, #111E38);
          border: 1px solid var(--yf-border); border-radius: 14px; padding: 0.72rem 0.78rem;
          margin-top: 0.62rem; transition: transform 150ms ease, box-shadow 150ms ease, border-color 150ms ease;
        }}
        .yf-deal:hover {{transform: translateY(-2px); border-color: rgba(59,130,246,0.42);
          box-shadow: 0 10px 24px rgba(2,6,23,0.55);}}
        .yf-deal .t {{font-weight: 650; font-size: 0.88rem; line-height: 1.25;}}
        .yf-deal .stage {{color: var(--yf-muted); font-size: 0.7rem; margin-top: 0.1rem;}}
        .yf-deal .amount {{font-size: 1.18rem; font-weight: 750; margin: 0.4rem 0 0.2rem;}}
        .yf-step {{display: flex; gap: 4px; margin: 0.25rem 0 0.4rem;}}
        .yf-step i {{flex: 1; height: 5px; border-radius: 3px; background: rgba(148,163,184,0.16);}}
        .yf-step i.on {{background: linear-gradient(90deg, #3B82F6, #8B5CF6);}}
        .yf-meta {{font-size: 0.71rem; color: var(--yf-muted); display: flex; justify-content: space-between;}}
        .yf-tag {{display: inline-block; margin-top: 0.45rem; padding: 0.14rem 0.52rem;
          border-radius: 8px; font-size: 0.67rem; font-weight: 700; letter-spacing: 0.02em;}}
        .yf-more {{color: var(--yf-muted); font-size: 0.72rem; margin-top: 0.5rem; text-align: center;}}

        /* ---- activity timeline ---- */
        .yf-tl {{list-style: none; padding: 0; margin: 0.2rem 0 0;}}
        .yf-tl li {{position: relative; padding: 0 0 0.85rem 1.5rem; font-size: 0.8rem;}}
        .yf-tl li:before {{
          content: ""; position: absolute; left: 0; top: 1px; width: 13px; height: 13px;
          border-radius: 50%; background: rgba(34,197,94,0.16); border: 1px solid #22C55E;
        }}
        .yf-tl li:not(:last-child):after {{
          content: ""; position: absolute; left: 6px; top: 17px; bottom: 2px;
          width: 1px; background: var(--yf-border);
        }}
        .yf-tl .d {{color: var(--yf-muted); font-size: 0.69rem;}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def app_header(title: str, subtitle: str, chips: Iterable[str] = ()) -> None:
    chip_html = "".join(f'<span class="yf-chip">{esc(c)}</span>' for c in chips)
    st.markdown(
        f"""
        <div class="yf-header">
          <div class="yf-brand">
            <div class="logo">YF</div>
            <div>
              <div class="name">{esc(title)}</div>
              <div class="tag">{esc(subtitle)}</div>
            </div>
          </div>
          <div style="flex:1"></div>
          <div>{chip_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section(title: str, caption: str | None = None) -> None:
    cap = f'<span class="c">{esc(caption)}</span>' if caption else ""
    st.markdown(f'<div class="yf-section"><span class="t">{esc(title)}</span>{cap}</div>', unsafe_allow_html=True)


def badge(text: str, color: str) -> str:
    return (
        f'<span class="yf-badge" style="color:{color};border-color:{color}44;'
        f'background:{color}1A;">{esc(text)}</span>'
    )


def kpi_card(label: str, value: str, sub: str | None = None, accent: str = ACCENT) -> str:
    sub_html = f'<div class="sub">{esc(sub)}</div>' if sub else ""
    return (
        f'<div class="yf-kpi"><div class="label">{esc(label)}</div>'
        f'<div class="value">{esc(value)}</div>{sub_html}'
        f'<div class="accent-bar" style="--bar:{accent};"></div></div>'
    )


def kpi_grid(cards: Iterable[str]) -> None:
    st.markdown(f'<div class="yf-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def progress_bar(value: float, color: str = ACCENT) -> str:
    pct = max(0.0, min(1.0, value)) * 100
    return (
        f'<div class="yf-progress"><div style="width:{pct:.1f}%;'
        f'background:linear-gradient(90deg,{color},{color}88);"></div></div>'
    )


def insight_card(kind: str, title: str, body: str, foot: str) -> None:
    st.markdown(
        f"""
        <div class="yf-insight">
          <div class="kind">{esc(kind)}</div>
          <div class="title">{esc(title)}</div>
          <div class="body">{body}</div>
          <div class="foot">{esc(foot)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_state(message: str, hint: str | None = None) -> None:
    hint_html = f'<div style="margin-top:0.3rem;font-size:0.75rem;">{esc(hint)}</div>' if hint else ""
    st.markdown(f'<div class="yf-empty">{esc(message)}{hint_html}</div>', unsafe_allow_html=True)


def chart_style(fig, height: int = 320):
    """Apply the shared plotly look: transparent bg, muted grid, consistent palette."""
    fig.update_layout(
        height=height,
        margin=dict(t=42, b=8, l=8, r=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=MUTED, size=12, family="Inter, Segoe UI, sans-serif"),
        title_font=dict(color=TEXT, size=14),
        legend=dict(font=dict(color=MUTED), bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor="rgba(148,163,184,0.10)", zerolinecolor="rgba(148,163,184,0.10)"),
        yaxis=dict(gridcolor="rgba(148,163,184,0.10)", zerolinecolor="rgba(148,163,184,0.10)"),
    )
    return fig


def deal_card(
    title: str,
    stage_label: str,
    amount: float,
    step_index: int,
    total_steps: int,
    meta_left: str,
    meta_right: str,
    tag: str | None = None,
    tag_color: str = ACCENT,
) -> str:
    """One kanban deal card (stage position shown as factual step bar, not a forecast)."""
    steps = "".join(
        f'<i class="{"on" if i < step_index else ""}"></i>' for i in range(total_steps)
    )
    tag_html = (
        f'<span class="yf-tag" style="background:{tag_color}22;color:{tag_color};'
        f'border:1px solid {tag_color}44;">{esc(tag)}</span>'
        if tag
        else ""
    )
    return (
        f'<div class="yf-deal"><div class="t">{esc(title)}</div>'
        f'<div class="stage">{esc(stage_label)}</div>'
        f'<div class="amount">${amount:,.0f}</div>'
        f'<div class="yf-step">{steps}</div>'
        f'<div class="yf-meta"><span>{esc(meta_left)}</span><span>{esc(meta_right)}</span></div>'
        f"{tag_html}</div>"
    )


def kanban_board(columns: list[dict]) -> None:
    """columns: [{title, total, cards: [html], more, accent}]"""
    parts = ['<div class="yf-board">']
    for col in columns:
        header = (
            f'<div class="head"><span class="t">{esc(col["title"])}</span>'
            f'<span class="a">{esc(col.get("total", ""))}</span></div>'
        )
        cards = "".join(col.get("cards", []))
        more = f'<div class="yf-more">{esc(col["more"])}</div>' if col.get("more") else ""
        parts.append(f'<div class="yf-col">{header}{cards}{more}</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def timeline(events: list[dict]) -> None:
    """events: [{title, date}] rendered as a vertical activity timeline."""
    if not events:
        empty_state("No recorded activity.")
        return
    items = "".join(
        f'<li><div>{esc(e["title"])}</div><div class="d">{esc(e["date"])}</div></li>' for e in events
    )
    st.markdown(f'<ul class="yf-tl">{items}</ul>', unsafe_allow_html=True)


def gauge(value: float, title: str, sub: str, color: str = ACCENT) -> None:
    """Compact plotly gauge for a real 0-100 metric."""
    import plotly.graph_objects as go

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            number={"font": {"color": TEXT, "size": 34}, "suffix": " / 100"},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": MUTED, "tickfont": {"size": 9, "color": MUTED}},
                "bar": {"color": color, "thickness": 0.24},
                "bgcolor": "rgba(148,163,184,0.08)",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 50], "color": "rgba(239,68,68,0.10)"},
                    {"range": [50, 80], "color": "rgba(99,102,241,0.12)"},
                    {"range": [80, 100], "color": "rgba(34,197,94,0.12)"},
                ],
            },
            title={"text": f"<span style='font-size:0.8rem;color:{MUTED}'>{esc(title)}</span>"},
        )
    )
    fig.update_layout(
        height=230,
        margin=dict(t=30, b=6, l=16, r=16),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color=MUTED, size=11),
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(sub)
