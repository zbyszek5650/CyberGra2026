"""
CyberGra v4 — Silnik Symulacji Kryzysowej
==========================================
Streamlit-based crisis simulation engine.
No database — all state via @st.cache_resource.
5 Scenarios × 6 Sub-stages = 30 decision rounds.
2-lives system for teams.
v4.1: metric clamp (default 100) + base upkeep costs between rounds,
learning_points debrief shown only AFTER a team submits its decision,
end-of-scenario summary, option-count consistency check in admin.
"""

import streamlit as st
import pandas as pd
import yaml
import plotly.graph_objects as go
import os
import hashlib
from datetime import datetime

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="🛡️ CyberGra v4 — Symulacja Kryzysowa",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# CSS THEME: Modern Executive UI + Glassmorphism
# Injected via st.html() so the <style> block is NOT stripped.
# ============================================================
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap');

:root {
    --bg-primary: #0a0e1a;
    --bg-secondary: #111827;
    --bg-glass: rgba(17, 24, 39, 0.72);
    --border-glass: rgba(99, 102, 241, 0.3);
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --accent-blue: #6366f1;
    --accent-cyan: #06b6d4;
    --accent-red: #ef4444;
    --accent-green: #10b981;
    --accent-amber: #f59e0b;
    --neon-glow: 0 0 20px rgba(99, 102, 241, 0.3);
}

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}
body, p, li, span, div, label {
    font-size: 1.1rem !important;
    line-height: 1.6 !important;
}
h1 { font-size: 2.3rem !important; font-weight: 800 !important; letter-spacing: -0.02em !important; }
h2 { font-size: 1.8rem !important; font-weight: 700 !important; }
h3 { font-size: 1.5rem !important; font-weight: 600 !important; }

.stApp {
    background: linear-gradient(135deg, #0a0e1a 0%, #111827 50%, #0f172a 100%) !important;
}

.stButton > button {
    padding: 16px 24px !important;
    font-size: 1.05rem !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.3s ease !important;
    border: 1px solid rgba(99, 102, 241, 0.3) !important;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 0 24px rgba(99, 102, 241, 0.35) !important;
}

.stRadio > div { gap: 0.75rem !important; }
.stRadio > div > label {
    padding: 12px 16px !important;
    border-radius: 8px !important;
    border: 1px solid rgba(99, 102, 241, 0.2) !important;
    font-size: 1.05rem !important;
    transition: all 0.2s ease !important;
    background: rgba(17, 24, 39, 0.4) !important;
}
.stRadio > div > label:hover {
    background: rgba(99, 102, 241, 0.1) !important;
    border-color: var(--accent-blue) !important;
}

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a, #111827) !important;
}

[data-testid="stMetricValue"] { font-size: 1.6rem !important; font-weight: 700 !important; }
[data-testid="stMetricDelta"]  { font-size: 1.0rem !important; }

.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [data-baseweb="tab"] {
    padding: 12px 20px !important;
    font-size: 1.0rem !important;
    font-weight: 600 !important;
    border-radius: 8px 8px 0 0 !important;
}

::-webkit-scrollbar       { width: 6px; }
::-webkit-scrollbar-track  { background: var(--bg-secondary); }
::-webkit-scrollbar-thumb  { background: var(--accent-blue); border-radius: 3px; }
</style>
"""
st.html(_CSS)


# ============================================================
# HTML helper — renders raw HTML via st.html() (zero-height
# iframes handled by Streamlit ≥ 1.33).  For older Streamlit
# that lacks st.html, fall back to st.markdown.
# ============================================================
def _html(content: str):
    """Render arbitrary HTML safely."""
    st.html(content)


# ============================================================
# GLOBAL ENGINE — in-memory, cached across reruns
# ============================================================
@st.cache_resource
def get_global_engine():
    return {
        "config": None,
        "teams": {},
        "admin_pin": "admin2024",
        "current_scenario_idx": 0,
        "current_round_idx": 0,
        "phase": "lobby",
        "decisions": {},
        "round_evaluated": False,
        "history": [],
        "version": 0,            # bumped on every admin action
        "created_at": datetime.now().isoformat(),
    }


# ============================================================
# TEAM RECORD
# ============================================================
def new_team_record(name: str, pin: str, config: dict) -> dict:
    metrics = {}
    for m in config["metrics"]:
        metrics[m["id"]] = m["initial"]
    return {
        "name": name,
        "pin": pin,
        "lives": 2,
        "is_eliminated_current": False,
        "is_permanently_eliminated": False,
        "eliminated_history": [],
        "metrics": dict(metrics),
        "stock_price": config.get("initial_stock_price", 100.0),
        "stock_history": [config.get("initial_stock_price", 100.0)],
        "total_score": 0,
        "scenario_scores": [],
    }


# ============================================================
# CONFIG LOADER
# ============================================================
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "bank_cyber_crisis.yaml")


def load_config_from_path(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_config_from_bytes(raw: bytes) -> dict:
    return yaml.safe_load(raw)


def ensure_config(engine: dict):
    if engine["config"] is None:
        if os.path.exists(DEFAULT_CONFIG_PATH):
            engine["config"] = load_config_from_path(DEFAULT_CONFIG_PATH)


# ============================================================
# HELPERS
# ============================================================
def get_active_teams(engine):
    return {tid: t for tid, t in engine["teams"].items() if not t["is_permanently_eliminated"]}


def get_scenario(engine, idx=None):
    cfg = engine["config"]
    if cfg is None:
        return None
    scenarios = cfg.get("scenarios", [])
    i = idx if idx is not None else engine["current_scenario_idx"]
    return scenarios[i] if 0 <= i < len(scenarios) else None


def get_round_data(engine, s_idx=None, r_idx=None):
    si = s_idx if s_idx is not None else engine["current_scenario_idx"]
    ri = r_idx if r_idx is not None else engine["current_round_idx"]
    scenario = get_scenario(engine, si)
    if scenario is None:
        return None
    rounds = scenario.get("rounds", [])
    return rounds[ri] if 0 <= ri < len(rounds) else None


def total_scenarios(engine):
    cfg = engine["config"]
    return len(cfg.get("scenarios", [])) if cfg else 0


def total_rounds_in_scenario(engine, s_idx=None):
    s = get_scenario(engine, s_idx)
    return len(s.get("rounds", [])) if s else 0


def compute_score(team, config):
    m_avg = sum(team["metrics"].values()) / max(len(team["metrics"]), 1)
    init_stock = config.get("initial_stock_price", 100.0)
    stock_pct = (team["stock_price"] / init_stock) * 100 if init_stock > 0 else 100
    return round(m_avg * 0.6 + stock_pct * 0.4, 1)


def get_metric_max(cfg):
    """Upper clamp for metrics (default 100). Overridable in YAML: metric_max: 100."""
    try:
        return int(cfg.get("metric_max", 100))
    except (TypeError, ValueError):
        return 100


def get_round_upkeep(cfg):
    """Base running costs applied every round (default: -2 to each metric).

    YAML config options:
        round_upkeep: -3            # global, all metrics
        upkeep:                      # per metric
            plynnosc: -3
            cyber: -2
    """
    val = cfg.get("upkeep", cfg.get("round_upkeep", -2))
    if isinstance(val, dict):
        return val
    if not isinstance(val, (int, float)):
        val = -2
    return {m["id"]: val for m in cfg.get("metrics", [])}


def get_upkeep_stock_delta(cfg):
    """Small per-round stock decay (default -1.0). YAML: upkeep_stock_delta."""
    try:
        return float(cfg.get("upkeep_stock_delta", -1.0))
    except (TypeError, ValueError):
        return -1.0


def bump_version(engine):
    """Increment version counter so that team fragments detect a change."""
    engine["version"] = engine.get("version", 0) + 1


# ---- HTML snippets ----
def lives_html(lives: int) -> str:
    if lives >= 2:
        hearts = "❤️ ❤️"
    elif lives == 1:
        hearts = "❤️ 💔"
    else:
        hearts = "☠️"
    return (
        f'<div style="font-size:2.2rem; text-align:center; padding:0.5rem 0; '
        f'animation: pulse-lives 1.5s ease-in-out infinite;">{hearts}</div>'
        f'<style>@keyframes pulse-lives {{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.06)}}}}</style>'
    )


def kpi_card_html(icon, label, value, color):
    bar_w = max(0, min(100, int(value)))
    return (
        f'<div style="background:rgba(17,24,39,0.72); backdrop-filter:blur(12px); '
        f'border:1px solid rgba(99,102,241,0.3); border-radius:12px; padding:1.2rem; '
        f'text-align:center; min-height:120px; box-shadow:0 0 20px rgba(99,102,241,0.3);">'
        f'<div style="font-size:1.6rem;">{icon}</div>'
        f'<div style="font-size:0.8rem; text-transform:uppercase; letter-spacing:0.08em; '
        f'color:#94a3b8; margin:4px 0;">{label}</div>'
        f'<div style="font-size:2.2rem; font-weight:800; font-family:JetBrains Mono,monospace; '
        f'color:{color};">{value}</div>'
        f'<div style="background:rgba(255,255,255,0.08); border-radius:4px; height:6px; margin-top:6px;">'
        f'<div style="width:{bar_w}%; height:100%; background:{color}; border-radius:4px;"></div>'
        f'</div></div>'
    )


def stock_arrow_html(current, prev):
    if current > prev:
        cls = "color:#10b981;"
        icon = "📈"
    elif current < prev:
        cls = "color:#ef4444;"
        icon = "📉"
    else:
        cls = "color:#94a3b8;"
        icon = "➡️"
    return (
        f'<span style="font-size:2.2rem; font-weight:800; font-family:JetBrains Mono,monospace; {cls}">'
        f'{icon} {current:.2f} PLN</span>'
    )


def scenario_header_html(line1, line2, line3=""):
    return (
        f'<div style="background:linear-gradient(135deg,rgba(99,102,241,0.15),rgba(6,182,212,0.15)); '
        f'backdrop-filter:blur(12px); border:1px solid rgba(99,102,241,0.3); border-radius:12px; '
        f'padding:2rem; text-align:center; box-shadow:0 0 20px rgba(99,102,241,0.3); margin-bottom:1rem;">'
        f'<div style="font-size:1rem; color:#94a3b8;">{line1}</div>'
        f'<h2 style="margin:0.3rem 0; font-size:1.8rem; font-weight:700;">{line2}</h2>'
        f'<div style="font-size:1.1rem; color:#06b6d4;">{line3}</div>'
        f'</div>'
    )


def broadcast_bar_html(text):
    return (
        f'<div style="background:linear-gradient(90deg,rgba(239,68,68,0.12),rgba(245,158,11,0.12)); '
        f'backdrop-filter:blur(12px); border:1px solid rgba(239,68,68,0.35); border-radius:12px; '
        f'padding:1rem 1.5rem; font-size:1.1rem; margin-bottom:1rem; '
        f'animation:pulse-border 2s ease-in-out infinite;">'
        f'📢 {text}</div>'
        f'<style>@keyframes pulse-border {{0%,100%{{border-color:rgba(239,68,68,0.3);box-shadow:0 0 8px rgba(239,68,68,0.1)}}'
        f'50%{{border-color:rgba(239,68,68,0.7);box-shadow:0 0 16px rgba(239,68,68,0.25)}}}}</style>'
    )


def panel_html(content):
    return (
        f'<div style="background:rgba(17,24,39,0.72); backdrop-filter:blur(12px); '
        f'border:1px solid rgba(99,102,241,0.3); border-radius:12px; padding:1.5rem; '
        f'margin:0.75rem 0; box-shadow:0 0 20px rgba(99,102,241,0.3);">{content}</div>'
    )


def banner_html(content):
    return (
        f'<div style="background:linear-gradient(135deg,rgba(99,102,241,0.2),rgba(6,182,212,0.2)); '
        f'border:2px solid rgba(99,102,241,0.5); border-radius:16px; padding:3rem; text-align:center; '
        f'animation:glow-int 3s ease-in-out infinite;">{content}</div>'
        f'<style>@keyframes glow-int {{0%,100%{{box-shadow:0 0 20px rgba(99,102,241,0.2)}}'
        f'50%{{box-shadow:0 0 40px rgba(99,102,241,0.4)}}}}</style>'
    )


def eliminated_html(content):
    return (
        f'<div style="background:rgba(239,68,68,0.08); border:2px solid rgba(239,68,68,0.4); '
        f'border-radius:12px; padding:2rem; text-align:center;">{content}</div>'
    )


def ranking_row_html(medal, name, status, lives_str, score):
    return (
        f'<div style="background:rgba(17,24,39,0.72); border:1px solid rgba(99,102,241,0.3); '
        f'border-radius:8px; padding:0.75rem 1rem; margin:0.3rem 0; display:flex; '
        f'align-items:center; justify-content:space-between;">'
        f'<span style="font-size:1.3rem;">{medal} <strong>{name}</strong>{status}</span>'
        f'<span>{lives_str} &nbsp;|&nbsp; '
        f'<span style="font-size:1.3rem; font-weight:800; font-family:JetBrains Mono,monospace;">'
        f'{score}</span> pkt</span></div>'
    )


def team_status_row_html(name, lives_h, status_text):
    return (
        f'<div style="background:rgba(17,24,39,0.72); backdrop-filter:blur(12px); '
        f'border:1px solid rgba(99,102,241,0.3); border-radius:12px; padding:0.75rem 1.2rem; '
        f'margin:0.4rem 0; display:flex; align-items:center; justify-content:space-between;">'
        f'<strong>{name}</strong>'
        f'<span>{lives_h}</span>'
        f'<span style="font-size:0.9rem;">{status_text}</span></div>'
    )


# ============================================================
# EVALUATION & ADVANCEMENT
# ============================================================
def evaluate_round_and_advance(engine):
    cfg = engine["config"]
    if cfg is None:
        return

    s_idx = engine["current_scenario_idx"]
    r_idx = engine["current_round_idx"]
    rd = get_round_data(engine, s_idx, r_idx)
    if rd is None:
        return

    scenario = get_scenario(engine, s_idx)
    elim_stock_pct = cfg.get("elimination_stock_drop_pct", 60)
    elim_metric_min = cfg.get("elimination_metric_min", 5)
    init_stock = scenario.get("initial_stock_price", cfg.get("initial_stock_price", 100.0))
    metric_max = get_metric_max(cfg)
    upkeep = get_round_upkeep(cfg)
    upkeep_stock = get_upkeep_stock_delta(cfg)

    for tid, team in engine["teams"].items():
        if team["is_permanently_eliminated"] or team["is_eliminated_current"]:
            continue

        key = f"{s_idx}_{r_idx}_{tid}"
        decision = engine["decisions"].get(key)
        if decision is None:
            for mid in team["metrics"]:
                team["metrics"][mid] = max(0, team["metrics"][mid] - 5)
            team["stock_price"] = max(0, round(team["stock_price"] - 3.0, 2))
        else:
            ciso_choice = decision.get("ciso", 0)
            ceo_choice = decision.get("ceo", 0)

            ciso_opts = rd.get("ciso_question", {}).get("options", [])
            if 0 <= ciso_choice < len(ciso_opts):
                opt = ciso_opts[ciso_choice]
                for mid, delta in opt.get("impacts", {}).items():
                    if mid in team["metrics"]:
                        team["metrics"][mid] = max(0, min(metric_max, team["metrics"][mid] + delta))
                team["stock_price"] = max(0, round(team["stock_price"] + opt.get("stock_delta", 0), 2))

            ceo_opts = rd.get("ceo_question", {}).get("options", [])
            if 0 <= ceo_choice < len(ceo_opts):
                opt = ceo_opts[ceo_choice]
                for mid, delta in opt.get("impacts", {}).items():
                    if mid in team["metrics"]:
                        team["metrics"][mid] = max(0, min(metric_max, team["metrics"][mid] + delta))
                team["stock_price"] = max(0, round(team["stock_price"] + opt.get("stock_delta", 0), 2))

            # --- Base running costs (upkeep) between rounds ---
            # Keeps late scenarios tense: metrics cannot pile up a safety buffer.
            for mid, cost in upkeep.items():
                if mid in team["metrics"]:
                    team["metrics"][mid] = max(0, min(metric_max, team["metrics"][mid] + cost))
            if upkeep_stock:
                team["stock_price"] = max(0, round(team["stock_price"] + upkeep_stock, 2))

        team["stock_history"].append(team["stock_price"])

        stock_threshold = init_stock * (elim_stock_pct / 100.0)
        reason = None
        if team["stock_price"] < stock_threshold:
            reason = f"Kurs akcji spadł poniżej progu ({team['stock_price']:.2f} < {stock_threshold:.2f})"
        else:
            for mid, val in team["metrics"].items():
                if val <= elim_metric_min:
                    metric_name = mid
                    for m_def in cfg["metrics"]:
                        if m_def["id"] == mid:
                            metric_name = m_def["name"]
                            break
                    reason = f"Wskaźnik '{metric_name}' spadł do {val} (próg: {elim_metric_min})"
                    break

        if reason:
            team["lives"] -= 1
            team["is_eliminated_current"] = True
            team["eliminated_history"].append({
                "scenario": scenario.get("title", f"S{s_idx+1}"),
                "round": rd.get("title", f"R{r_idx+1}"),
                "reason": reason,
            })
            if team["lives"] <= 0:
                team["is_permanently_eliminated"] = True

        team["total_score"] = compute_score(team, cfg)

    engine["history"].append({
        "scenario_idx": s_idx, "round_idx": r_idx,
        "timestamp": datetime.now().isoformat(),
    })
    engine["round_evaluated"] = True
    bump_version(engine)


def advance_to_next_round(engine):
    s_idx = engine["current_scenario_idx"]
    r_idx = engine["current_round_idx"]

    if r_idx + 1 < total_rounds_in_scenario(engine, s_idx):
        engine["current_round_idx"] = r_idx + 1
        engine["round_evaluated"] = False
        engine["phase"] = "playing"
    else:
        if s_idx + 1 < total_scenarios(engine):
            engine["phase"] = "intermission"
        else:
            engine["phase"] = "finished"
    bump_version(engine)


def start_next_scenario(engine):
    cfg = engine["config"]
    s_idx = engine["current_scenario_idx"] + 1
    if s_idx >= total_scenarios(engine):
        engine["phase"] = "finished"
        bump_version(engine)
        return

    engine["current_scenario_idx"] = s_idx
    engine["current_round_idx"] = 0
    engine["round_evaluated"] = False
    engine["phase"] = "playing"

    scenario = get_scenario(engine, s_idx)
    new_stock = scenario.get("initial_stock_price", cfg.get("initial_stock_price", 100.0))

    for tid, team in engine["teams"].items():
        if team["is_permanently_eliminated"]:
            continue
        if team["lives"] > 0:
            team["is_eliminated_current"] = False
            for m_def in cfg["metrics"]:
                team["metrics"][m_def["id"]] = m_def["initial"]
            team["stock_price"] = new_stock
            team["stock_history"] = [new_stock]
            team["scenario_scores"].append(team["total_score"])
            team["total_score"] = compute_score(team, cfg)
    bump_version(engine)


def calculate_ranking(engine):
    ranking = []
    for tid, t in engine["teams"].items():
        ranking.append({
            "id": tid, "name": t["name"], "score": t["total_score"],
            "lives": t["lives"], "eliminated": t["is_permanently_eliminated"],
            "eliminated_current": t["is_eliminated_current"],
        })
    ranking.sort(key=lambda x: (-x["score"], -x["lives"]))
    return ranking


# ============================================================
# SESSION STATE INIT
# ============================================================
if "role" not in st.session_state:
    st.session_state["role"] = None
if "team_id" not in st.session_state:
    st.session_state["team_id"] = None
if "last_seen_version" not in st.session_state:
    st.session_state["last_seen_version"] = -1


# ============================================================
# AUTO-REFRESH: detects engine version changes and reruns
# ============================================================
@st.fragment(run_every=2)
def _auto_refresh_watcher():
    """Runs every 2 s.  If the engine version changed (admin advanced round),
    the whole page is rerun so the team sees the new round."""
    engine = get_global_engine()
    cur_ver = engine.get("version", 0)
    phase = engine["phase"]
    s_idx = engine["current_scenario_idx"]
    r_idx = engine["current_round_idx"]

    phase_labels = {
        "lobby": "🟡 LOBBY", "playing": "🟢 GRA",
        "evaluating": "🔵 EWALUACJA", "intermission": "🟠 PRZERWA",
        "finished": "🏆 KONIEC",
    }
    st.sidebar.markdown(f"**Status:** {phase_labels.get(phase, phase.upper())}")
    st.sidebar.markdown(f"S{s_idx+1}/R{r_idx+1} | Zespołów: {len(engine['teams'])}")

    if st.session_state.get("last_seen_version", -1) != cur_ver:
        st.session_state["last_seen_version"] = cur_ver
        st.rerun()


# ============================================================
# LOGIN PAGE
# ============================================================
def login_page():
    engine = get_global_engine()
    ensure_config(engine)

    _html(scenario_header_html(
        "", "🛡️ CyberGra v4", "Symulacja Kryzysu Cyberbezpieczeństwa"
    ))

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        login_type = st.radio(
            "Zaloguj się jako:", ["🎓 Zespół (Student)", "🔐 Administrator"],
            horizontal=True,
        )

        if "Zespół" in login_type:
            team_name = st.text_input("Nazwa zespołu", placeholder="np. CyberWolves")
            pin = st.text_input("PIN zespołu", type="password", placeholder="4-cyfrowy PIN")
            if st.button("🚀 DOŁĄCZ DO GRY", use_container_width=True):
                if not team_name or not pin:
                    st.error("Podaj nazwę zespołu i PIN.")
                else:
                    tid = hashlib.md5(team_name.lower().encode()).hexdigest()[:8]
                    if tid in engine["teams"]:
                        if engine["teams"][tid]["pin"] == pin:
                            st.session_state["role"] = "team"
                            st.session_state["team_id"] = tid
                            st.rerun()
                        else:
                            st.error("❌ Nieprawidłowy PIN.")
                    else:
                        st.error("❌ Zespół nie jest zarejestrowany. Poproś admina o rejestrację.")
        else:
            admin_pin = st.text_input("PIN Administratora", type="password", placeholder="Hasło admina")
            if st.button("🔐 ZALOGUJ JAKO ADMIN", use_container_width=True):
                if admin_pin == engine["admin_pin"]:
                    st.session_state["role"] = "admin"
                    st.rerun()
                else:
                    st.error("❌ Nieprawidłowy PIN administratora.")


# ============================================================
# TEAM VIEW
# ============================================================
def team_view():
    engine = get_global_engine()
    ensure_config(engine)
    cfg = engine["config"]
    tid = st.session_state["team_id"]
    team = engine["teams"].get(tid)

    if team is None:
        st.error("Zespół nie znaleziony. Zaloguj się ponownie.")
        if st.button("🔙 Wyloguj"):
            st.session_state["role"] = None
            st.session_state["team_id"] = None
            st.rerun()
        return

    # ---- Top bar ----
    top1, top2, top3, top4, top5 = st.columns([3, 2, 1, 1, 1])
    with top1:
        st.markdown(f"### 🎓 {team['name']}")
    with top2:
        prev = team["stock_history"][-2] if len(team["stock_history"]) >= 2 else team["stock_price"]
        _html(stock_arrow_html(team["stock_price"], prev))
    with top3:
        _html(lives_html(team["lives"]))
    with top4:
        if st.button("🔄 Odśwież", help="Pobierz aktualny stan gry"):
            st.rerun()
    with top5:
        if st.button("🚪", help="Wyloguj"):
            st.session_state["role"] = None
            st.session_state["team_id"] = None
            st.rerun()

    st.divider()

    # ---- Permanently eliminated ----
    if team["is_permanently_eliminated"]:
        _html(eliminated_html(
            "<h2>☠️ ELIMINACJA PERMANENTNA</h2>"
            "<p>Twój zespół stracił oba życia i przechodzi w tryb obserwatora.</p>"
        ))
        _render_ranking(engine)
        return

    phase = engine["phase"]

    if phase == "lobby":
        _html(banner_html(
            "<h2>⏳ POCZEKALNIA</h2>"
            "<p>Gra jeszcze się nie rozpoczęła. Czekaj na decyzję administratora.</p>"
        ))

    elif phase == "intermission":
        next_s = get_scenario(engine, engine["current_scenario_idx"] + 1)
        extra = ""
        if next_s:
            extra = f"<p><strong>Następny scenariusz:</strong> {next_s.get('icon','')} {next_s['title']}</p>"
        _html(banner_html(
            f"<h2>🔄 PRZERWA MIĘDZY SCENARIUSZAMI</h2>{extra}"
            "<p>Czekaj na rozpoczęcie przez administratora.</p>"
        ))
        _render_scenario_debrief(engine, engine["current_scenario_idx"])
        _render_ranking(engine)

    elif phase == "finished":
        _html(banner_html(
            "<h2>🏆 GRA ZAKOŃCZONA</h2>"
            "<p>Wszystkie scenariusze zostały rozegrane!</p>"
        ))
        _render_scenario_debrief(engine, engine["current_scenario_idx"])
        _render_ranking(engine)

    elif phase in ("playing", "evaluating"):
        _render_game_round(engine, team, tid)


def _render_game_round(engine, team, tid):
    cfg = engine["config"]
    s_idx = engine["current_scenario_idx"]
    r_idx = engine["current_round_idx"]
    scenario = get_scenario(engine, s_idx)
    rd = get_round_data(engine, s_idx, r_idx)

    if scenario is None or rd is None:
        st.warning("Brak danych rundy.")
        return

    # Scenario header
    _html(scenario_header_html(
        f"SCENARIUSZ {s_idx+1}/{total_scenarios(engine)} &nbsp;•&nbsp; RUNDA {r_idx+1}/{total_rounds_in_scenario(engine, s_idx)}",
        f"{scenario.get('icon','🛡️')} {scenario['title']}",
        rd.get("title", ""),
    ))

    # Broadcast
    if rd.get("broadcast"):
        _html(broadcast_bar_html(rd["broadcast"]))

    # Narrative
    with st.expander("📋 SYTUACJA — Briefing", expanded=True):
        st.markdown(rd.get("narrative", ""))

    # KPI Dashboard
    metric_defs = cfg.get("metrics", [])
    kpi_cols = st.columns(len(metric_defs) + 1)
    for i, m_def in enumerate(metric_defs):
        with kpi_cols[i]:
            val = team["metrics"].get(m_def["id"], 0)
            _html(kpi_card_html(
                m_def.get("icon", "📊"), m_def["name"], val,
                m_def.get("color", "#6366f1"),
            ))
    with kpi_cols[-1]:
        _html(kpi_card_html("📈", "Notowania Akcji", round(team["stock_price"]), "#06b6d4"))

    # Eliminated this scenario?
    if team["is_eliminated_current"]:
        reason_text = ""
        if team["eliminated_history"]:
            last = team["eliminated_history"][-1]
            reason_text = f"<p><strong>Powód:</strong> {last['reason']}</p>"
        extra = ""
        if team["lives"] > 0:
            extra = f"<p>Pozostałe życia: <strong>{team['lives']}</strong>. Wrócisz w następnym scenariuszu!</p>"
        else:
            extra = "<p><strong>Brak żyć.</strong> Przechodzisz w tryb obserwatora.</p>"
        _html(eliminated_html(f"<h2>💔 ELIMINACJA W TYM SCENARIUSZU</h2>{reason_text}{extra}"))
        _render_ranking(engine)
        return

    # Decision form
    key_base = f"{s_idx}_{r_idx}_{tid}"
    already_decided = key_base in engine["decisions"]

    if already_decided:
        st.success("✅ Twoja decyzja została złożona. Czekaj na ewaluację rundy przez admina.")
        _render_round_debrief(rd)
        _render_ranking(engine)
        return

    if engine["round_evaluated"]:
        st.info("⏳ Runda została zewaluowana. Czekaj na następną rundę.")
        _render_round_debrief(rd)
        _render_ranking(engine)
        return

    st.markdown("---")
    st.markdown("### 🎯 PODEJMIJ DECYZJE")

    col_ciso, col_ceo = st.columns(2)

    with col_ciso:
        ciso_q = rd.get("ciso_question", {})
        st.markdown(f"#### 🔒 {ciso_q.get('role', 'CISO')}")
        st.markdown(ciso_q.get("text", ""))
        ciso_options = ciso_q.get("options", [])
        ciso_labels = [o["label"] for o in ciso_options]
        ciso_choice = st.radio(
            "Wybór CISO:", range(len(ciso_labels)),
            format_func=lambda i: ciso_labels[i],
            key=f"ciso_{key_base}",
        )
        if ciso_choice is not None and 0 <= ciso_choice < len(ciso_options):
            st.caption(f"ℹ️ {ciso_options[ciso_choice].get('description', '')}")

    with col_ceo:
        ceo_q = rd.get("ceo_question", {})
        st.markdown(f"#### 🏛️ {ceo_q.get('role', 'CEO')}")
        st.markdown(ceo_q.get("text", ""))
        ceo_options = ceo_q.get("options", [])
        ceo_labels = [o["label"] for o in ceo_options]
        ceo_choice = st.radio(
            "Wybór CEO:", range(len(ceo_labels)),
            format_func=lambda i: ceo_labels[i],
            key=f"ceo_{key_base}",
        )
        if ceo_choice is not None and 0 <= ceo_choice < len(ceo_options):
            st.caption(f"ℹ️ {ceo_options[ceo_choice].get('description', '')}")

    st.markdown("")
    if st.button("📤 ZŁÓŻ DECYZJĘ", use_container_width=True, type="primary"):
        engine["decisions"][key_base] = {
            "ciso": ciso_choice if ciso_choice is not None else 0,
            "ceo": ceo_choice if ceo_choice is not None else 0,
            "timestamp": datetime.now().isoformat(),
        }
        st.rerun()


def _render_round_debrief(rd):
    """Educational debrief — shown ONLY after the team submitted its decision,
    so the 'good' answers are not revealed in advance."""
    points = rd.get("learning_points", []) or []
    if not points:
        return
    with st.expander("🎓 DEBRIEFING — punkty dydaktyczne rundy", expanded=True):
        st.markdown("Czego miała Cię nauczyć ta runda (widoczne dopiero po złożeniu decyzji):")
        for p in points:
            st.markdown(f"- 🧠 {p}")


def _render_scenario_debrief(engine, s_idx):
    """End-of-scenario summary: what should have been done (aggregated learning points)."""
    scenario = get_scenario(engine, s_idx)
    if scenario is None:
        return
    summary = scenario.get("summary") or scenario.get("takeaways") or ""
    rows = []
    for rd in scenario.get("rounds", []):
        pts = rd.get("learning_points", []) or []
        if pts:
            rows.append((rd.get("title", ""), pts))
    if not summary and not rows:
        return
    body = ""
    if summary:
        body += f'<p style="color:#06b6d4;"><strong>{summary}</strong></p>'
    if rows:
        items = ""
        for r_title, pts in rows:
            lis = "".join(f"<li>{p}</li>" for p in pts)
            items += f"<li><strong>{r_title}</strong><ul>{lis}</ul></li>"
        body += "<ul>" + items + "</ul>"
    _html(panel_html(
        f'<h3 style="margin:0 0 0.5rem 0;">{scenario.get("icon", "📋")} '
        f'PODSUMOWANIE SCENARIUSZA {s_idx + 1}: {scenario.get("title", "")}</h3>'
        f'<div style="color:#94a3b8; font-size:0.95rem;">'
        f'Co należało wykonać w tym scenariuszu — zbiorczy debriefing:</div>'
        f'{body}'
    ))


def _render_ranking(engine):
    st.markdown("---")
    st.markdown("### 🏆 Ranking na żywo")
    ranking = calculate_ranking(engine)
    for i, r in enumerate(ranking):
        medal = "🥇" if i == 0 else ("🥈" if i == 1 else ("🥉" if i == 2 else f"#{i+1}"))
        status = ""
        if r["eliminated"]:
            status = " ☠️"
        elif r["eliminated_current"]:
            status = " 💔"
        lives_str = "❤️" * r["lives"] + "💔" * (2 - r["lives"]) if r["lives"] > 0 else "☠️"
        _html(ranking_row_html(medal, r["name"], status, lives_str, r["score"]))


# ============================================================
# ADMIN VIEW
# ============================================================
def admin_view():
    engine = get_global_engine()
    ensure_config(engine)
    cfg = engine["config"]

    st.markdown("### 🔐 Panel Administratora — CyberGra v4")

    if st.sidebar.button("🚪 Wyloguj"):
        st.session_state["role"] = None
        st.rerun()

    if cfg is None:
        st.warning("Brak wczytanej konfiguracji. Wgraj plik YAML lub użyj domyślnego.")
        if os.path.exists(DEFAULT_CONFIG_PATH):
            if st.button("📂 Załaduj domyślną konfigurację (bank_cyber_crisis.yaml)"):
                engine["config"] = load_config_from_path(DEFAULT_CONFIG_PATH)
                st.rerun()
        uploaded = st.file_uploader("Lub wgraj własny plik YAML", type=["yaml", "yml"])
        if uploaded:
            engine["config"] = load_config_from_bytes(uploaded.read())
            st.rerun()
        return

    tabs = st.tabs([
        "📡 STEROWANIE RUNDĄ",
        "👥 ZARZĄDZANIE ZESPOŁAMI",
        "📊 MONITOR ZESPOŁÓW",
        "⚙️ KONFIGURACJA",
    ])

    with tabs[0]:
        _admin_round_control(engine, cfg)
    with tabs[1]:
        _admin_team_management(engine, cfg)
    with tabs[2]:
        _admin_team_monitor(engine, cfg)
    with tabs[3]:
        _admin_config(engine, cfg)


def _admin_round_control(engine, cfg):
    phase = engine["phase"]
    s_idx = engine["current_scenario_idx"]
    r_idx = engine["current_round_idx"]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Faza", phase.upper())
    with col2:
        st.metric("Scenariusz", f"{s_idx+1}/{total_scenarios(engine)}")
    with col3:
        st.metric("Runda", f"{r_idx+1}/{total_rounds_in_scenario(engine, s_idx)}")
    with col4:
        st.metric("Zespoły", f"{len(get_active_teams(engine))}/{len(engine['teams'])}")

    st.divider()

    scenario = get_scenario(engine, s_idx)
    rd = get_round_data(engine, s_idx, r_idx)

    if scenario and rd:
        _html(scenario_header_html(
            "", f"{scenario.get('icon','')} {scenario['title']}", rd.get("title", ""),
        ))

    # Lives status
    st.markdown("#### 💓 Status Żyć Zespołów")
    for tid, t in engine["teams"].items():
        lh = lives_html(t["lives"])
        status_txt = (
            "🟢 Aktywny" if not t["is_eliminated_current"] and not t["is_permanently_eliminated"]
            else ("☠️ Permanentnie wyeliminowany" if t["is_permanently_eliminated"]
                  else "💔 Wyeliminowany (scenariusz)")
        )
        _html(team_status_row_html(t["name"], lh, status_txt))

    st.divider()

    if phase == "playing":
        st.markdown("#### 📋 Status Decyzji")
        active_teams = get_active_teams(engine)
        decided = 0
        playable = 0
        for tid, t in active_teams.items():
            if t["is_eliminated_current"]:
                continue
            playable += 1
            key = f"{s_idx}_{r_idx}_{tid}"
            if key in engine["decisions"]:
                decided += 1
                st.markdown(f"✅ **{t['name']}** — decyzja złożona")
            else:
                st.markdown(f"⏳ **{t['name']}** — czeka")

        st.progress(decided / max(playable, 1), text=f"{decided}/{playable} decyzji")
        st.divider()

        col_eval, col_skip = st.columns(2)
        with col_eval:
            if st.button("⚡ EWALUUJ RUNDĘ I PRZEJDŹ DALEJ", use_container_width=True, type="primary"):
                evaluate_round_and_advance(engine)
                advance_to_next_round(engine)
                st.rerun()
        with col_skip:
            if st.button("⏭️ Pomiń (bez ewaluacji)", use_container_width=True):
                advance_to_next_round(engine)
                st.rerun()

    elif phase == "lobby":
        st.info("Gra nie została jeszcze rozpoczęta.")
        if not engine["teams"]:
            st.warning("Brak zarejestrowanych zespołów. Dodaj zespoły w zakładce 'Zarządzanie Zespołami'.")
        if st.button("🚀 ROZPOCZNIJ GRĘ", use_container_width=True, type="primary"):
            if engine["teams"]:
                engine["phase"] = "playing"
                engine["current_scenario_idx"] = 0
                engine["current_round_idx"] = 0
                bump_version(engine)
                st.rerun()
            else:
                st.error("Dodaj przynajmniej jeden zespół!")

    elif phase == "intermission":
        next_s = get_scenario(engine, s_idx + 1)
        extra = ""
        if next_s:
            extra = (f"<p><strong>Następny:</strong> {next_s.get('icon','')} {next_s['title']}</p>"
                     f"<p><em>{next_s.get('description','')}</em></p>")
        _html(banner_html(f"<h2>🔄 PRZERWA MIĘDZY SCENARIUSZAMI</h2>{extra}"))
        _render_scenario_debrief(engine, s_idx)

        if st.button("▶️ ROZPOCZNIJ NASTĘPNY SCENARIUSZ", use_container_width=True, type="primary"):
            start_next_scenario(engine)
            st.rerun()

    elif phase == "finished":
        _html(banner_html("<h2>🏆 GRA ZAKOŃCZONA</h2>"))
        _render_scenario_debrief(engine, s_idx)
        _render_ranking(engine)

        if st.button("🔄 RESETUJ GRĘ (UWAGA: kasuje wszystko)", use_container_width=True):
            engine["phase"] = "lobby"
            engine["current_scenario_idx"] = 0
            engine["current_round_idx"] = 0
            engine["decisions"] = {}
            engine["round_evaluated"] = False
            engine["history"] = []
            for tid, t in engine["teams"].items():
                for m_def in cfg["metrics"]:
                    t["metrics"][m_def["id"]] = m_def["initial"]
                t["stock_price"] = cfg.get("initial_stock_price", 100.0)
                t["stock_history"] = [cfg.get("initial_stock_price", 100.0)]
                t["lives"] = 2
                t["is_eliminated_current"] = False
                t["is_permanently_eliminated"] = False
                t["eliminated_history"] = []
                t["total_score"] = 0
                t["scenario_scores"] = []
            bump_version(engine)
            st.rerun()


def _admin_team_management(engine, cfg):
    st.markdown("#### ➕ Zarejestruj Nowy Zespół")
    with st.form("add_team_form"):
        c1, c2 = st.columns(2)
        with c1:
            new_name = st.text_input("Nazwa zespołu", placeholder="np. CyberWolves")
        with c2:
            new_pin = st.text_input("PIN (4 cyfry)", placeholder="1234", max_chars=4)
        submitted = st.form_submit_button("➕ Zarejestruj", use_container_width=True)
        if submitted:
            if not new_name or not new_pin:
                st.error("Podaj nazwę i PIN.")
            elif len(new_pin) != 4 or not new_pin.isdigit():
                st.error("PIN musi mieć dokładnie 4 cyfry.")
            else:
                tid = hashlib.md5(new_name.lower().encode()).hexdigest()[:8]
                if tid in engine["teams"]:
                    st.warning(f"Zespół '{new_name}' już istnieje.")
                else:
                    engine["teams"][tid] = new_team_record(new_name, new_pin, cfg)
                    st.success(f"✅ Zespół '{new_name}' zarejestrowany! (ID: {tid})")
                    st.rerun()

    st.divider()
    st.markdown("#### 📋 Zarejestrowane Zespoły")
    if not engine["teams"]:
        st.info("Brak zarejestrowanych zespołów.")
    else:
        for tid, t in list(engine["teams"].items()):
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            with c1:
                st.markdown(f"**{t['name']}** `({tid})`")
            with c2:
                _html(lives_html(t["lives"]))
            with c3:
                st.markdown(f"PIN: `{t['pin']}`")
            with c4:
                if st.button("🗑️", key=f"del_{tid}", help=f"Usuń {t['name']}"):
                    del engine["teams"][tid]
                    st.rerun()


def _admin_team_monitor(engine, cfg):
    st.markdown("#### 📊 Monitor Zespołów")
    if not engine["teams"]:
        st.info("Brak zespołów do monitorowania.")
        return

    for tid, t in engine["teams"].items():
        icon = "☠️" if t["is_permanently_eliminated"] else ("💔" if t["is_eliminated_current"] else "🟢")
        with st.expander(f"{icon} {t['name']} — Żyć: {t['lives']} | Punkty: {t['total_score']}", expanded=False):
            metric_defs = cfg.get("metrics", [])
            mc = st.columns(len(metric_defs) + 1)
            for i, m_def in enumerate(metric_defs):
                with mc[i]:
                    st.metric(m_def["name"], t["metrics"].get(m_def["id"], 0))
            with mc[-1]:
                st.metric("Akcje", f"{t['stock_price']:.2f}")

            if len(t["stock_history"]) > 1:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    y=t["stock_history"], mode="lines+markers",
                    line=dict(color="#06b6d4", width=2), marker=dict(size=6),
                ))
                fig.update_layout(
                    height=200, margin=dict(l=20, r=20, t=20, b=20),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(17,24,39,0.5)",
                    yaxis_title="Kurs (PLN)", xaxis_title="Runda",
                    font=dict(color="#94a3b8"),
                )
                st.plotly_chart(fig, use_container_width=True, key=f"stock_chart_{tid}")

            if t["eliminated_history"]:
                st.markdown("**Historia eliminacji:**")
                for eh in t["eliminated_history"]:
                    st.markdown(f"- 📌 **{eh['scenario']}** / {eh['round']}: {eh['reason']}")

            cr, cm = st.columns(2)
            with cr:
                if st.button("➕ PRZYWRÓĆ ŻYCIE", key=f"restore_{tid}", use_container_width=True):
                    if t["lives"] < 2:
                        t["lives"] += 1
                        if t["is_permanently_eliminated"] and t["lives"] > 0:
                            t["is_permanently_eliminated"] = False
                        t["is_eliminated_current"] = False
                        bump_version(engine)
                        st.success(f"✅ Przywrócono życie dla {t['name']}. Żyć: {t['lives']}")
                        st.rerun()
                    else:
                        st.info("Zespół ma już maksymalną liczbę żyć (2).")
            with cm:
                if st.button("🔄 Reset wskaźników", key=f"reset_{tid}", use_container_width=True):
                    for m_def in cfg["metrics"]:
                        t["metrics"][m_def["id"]] = m_def["initial"]
                    scenario = get_scenario(engine)
                    t["stock_price"] = (scenario.get("initial_stock_price", cfg.get("initial_stock_price", 100.0))
                                        if scenario else cfg.get("initial_stock_price", 100.0))
                    t["total_score"] = compute_score(t, cfg)
                    bump_version(engine)
                    st.success(f"✅ Wskaźniki zresetowane dla {t['name']}.")
                    st.rerun()


def _admin_config(engine, cfg):
    st.markdown("#### ⚙️ Konfiguracja Gry")
    st.markdown(f"**Tytuł gry:** {cfg.get('game_title', 'N/A')}")
    st.markdown(f"**Scenariusze:** {total_scenarios(engine)}")
    total_r = sum(total_rounds_in_scenario(engine, i) for i in range(total_scenarios(engine)))
    st.markdown(f"**Łączna liczba rund:** {total_r}")

    st.divider()
    st.markdown("#### 📋 Przegląd Scenariuszy")
    for i, s in enumerate(cfg.get("scenarios", [])):
        st.markdown(f"**{i+1}. {s.get('icon','')} {s['title']}** — {len(s.get('rounds',[]))} rund")
        st.caption(s.get("subtitle", ""))

    st.divider()
    st.markdown("#### ⚖️ Balans rozgrywki (koszty bazowe / klamp)")
    st.markdown(f"**Klamp metryk (max):** `{cfg.get('metric_max', 100)}`")
    upkeep_disp = cfg.get("upkeep", cfg.get("round_upkeep", -2))
    st.markdown(f"**Koszty bazowe metryk / rundę:** `{upkeep_disp}`")
    st.markdown(f"**Koszt bazowy kursu / rundę:** `{cfg.get('upkeep_stock_delta', -1.0)}`")
    st.caption("Domyślnie: metryki max 100, upkeep -2/metrykę i -1.0 kursu na rundę — "
               "bufor bezpieczeństwa nie rośnie w nieskończoność i napięcie trwa do S5. "
               "Nadpiszesz w YAML: `metric_max`, `round_upkeep`, `upkeep: {metryka: wartość}`, `upkeep_stock_delta`.")

    st.divider()
    st.markdown("#### ✅ Kontrola spójności (liczba opcji / debriefing)")
    from collections import Counter
    counts = Counter()
    per_scenario = []
    for i, s in enumerate(cfg.get("scenarios", [])):
        s_counts = Counter()
        for r in s.get("rounds", []):
            for role_key in ("ciso_question", "ceo_question"):
                n = len(r.get(role_key, {}).get("options", []))
                counts[n] += 1
                s_counts[n] += 1
        per_scenario.append((i + 1, s.get("title", ""), dict(s_counts)))
    if counts:
        modal_n, _ = counts.most_common(1)[0]
        if len(counts) == 1:
            st.success(f"Spójna konfiguracja: wszystkie pytania mają po **{modal_n}** opcji.")
        else:
            st.warning(f"Niespójna liczba opcji: {dict(counts)}. Moda: **{modal_n}** — "
                       "wyrównaj pytania w YAML (dodaj/usuń opcje), żeby wszystkie rundy były porównywalne:")
            for s_no, s_title, sc in per_scenario:
                if len(sc) > 1 or modal_n not in sc:
                    st.markdown(f"- **S{s_no} {s_title}**: {sc}")
    missing_lp = sum(
        1 for s in cfg.get("scenarios", []) for r in s.get("rounds", [])
        if not r.get("learning_points")
    )
    if missing_lp:
        st.warning(f"{missing_lp} rund nie ma zdefiniowanych `learning_points` — debriefing po decyzji nie będzie dla nich dostępny.")
    else:
        st.success("Wszystkie rundy mają `learning_points` — debriefing działa w pełni.")

    st.divider()
    st.markdown("#### 📁 Wgraj Nową Konfigurację")
    uploaded = st.file_uploader("Plik YAML", type=["yaml", "yml"], key="config_upload")
    if uploaded:
        try:
            engine["config"] = load_config_from_bytes(uploaded.read())
            st.success("✅ Nowa konfiguracja załadowana!")
            st.rerun()
        except Exception as e:
            st.error(f"Błąd wczytywania YAML: {e}")

    st.divider()
    st.markdown("#### 🔐 Zmień PIN Administratora")
    with st.form("change_pin_form"):
        new_admin_pin = st.text_input("Nowy PIN", type="password")
        if st.form_submit_button("Zmień PIN"):
            if new_admin_pin and len(new_admin_pin) >= 4:
                engine["admin_pin"] = new_admin_pin
                st.success("✅ PIN zmieniony!")
            else:
                st.error("PIN musi mieć min. 4 znaki.")


# ============================================================
# MAIN
# ============================================================
def main():
    engine = get_global_engine()
    ensure_config(engine)

    # auto-refresh watcher in sidebar
    _auto_refresh_watcher()

    role = st.session_state.get("role")
    if role is None:
        login_page()
    elif role == "admin":
        admin_view()
    elif role == "team":
        team_view()
    else:
        login_page()


if __name__ == "__main__":
    main()
