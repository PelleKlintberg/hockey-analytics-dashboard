
import json
import re
from pathlib import Path
from io import BytesIO

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def canonical(value):
    return re.sub(r"[^a-z0-9åäö]+", "", str(value).lower())


def normalize_col_name(col):
    return re.sub(r"\s+", " ", str(col).strip().replace('"', ""))


def contains_any(text, words):
    text = str(text).lower()
    return any(w.lower() in text for w in words)


def parse_numeric_series(series):
    if getattr(series, "dtype", None) is not None and series.dtype.kind in "biufc":
        return pd.to_numeric(series, errors="coerce")
    return pd.to_numeric(
        series.astype(str)
        .str.replace("%", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.replace("−", "-", regex=False)
        .str.strip(),
        errors="coerce",
    )


def safe_row_value(row, metric, default=0):
    try:
        if metric in row.index and pd.notna(row[metric]):
            return float(row[metric])
    except Exception:
        pass
    return default


@st.cache_data(show_spinner=False)
def load_json_file(filename):
    path = Path(__file__).parent / "data" / filename
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


@st.cache_data(show_spinner=False)
def read_uploaded_file_cached(name, content):
    bio = BytesIO(content)
    if name.lower().endswith(".xlsx"):
        return pd.read_excel(bio)

    attempts = [
        {"sep": ",", "encoding": "utf-8-sig"},
        {"sep": ";", "encoding": "utf-8-sig", "decimal": ","},
        {"sep": None, "engine": "python", "encoding": "utf-8-sig"},
    ]
    last_error = None
    for kwargs in attempts:
        try:
            bio.seek(0)
            return pd.read_csv(bio, **kwargs)
        except Exception as e:
            last_error = e
    raise last_error


BLOCKS_BY_MODE = {
    "Lag": ["Overall", "Defensivt", "Offensivt", "Specialteam", "Faceoff", "Playmaking", "NZ", "Alla hittade metrics", "Saknade metrics", "Alla taxonomy metrics"],
    "Match": ["Overall", "Defensivt", "Offensivt", "Specialteam", "Faceoff", "Playmaking", "NZ", "Alla hittade metrics", "Saknade metrics", "Alla taxonomy metrics"],
    "Spelare": ["Overall", "Generell", "Offensivt", "Defensivt", "WOI", "Specialteam", "Faceoff", "Playmaking", "NZ", "Alla hittade metrics", "Saknade metrics", "Alla taxonomy metrics"],
    "Målvakt": ["Overall", "Målvakt", "Specialteam", "Alla hittade metrics", "Saknade metrics", "Alla taxonomy metrics"],
}

DEFAULT_DRILLDOWNS = {
    "Overall": ["Overall preset", "Alla overall metrics"],
    "Generell": ["Alla generella metrics"],
    "Defensivt": ["Alla defensiva", "Exits / Breakouts", "Entry defense / denial", "Shots against", "Slot protection", "Defensive actions"],
    "Offensivt": ["Alla offensiva", "Entries / ingångar", "Skott / shot", "OZ-passningar", "Forecheck / LPR"],
    "Specialteam": ["Båda (PP + PK/SH)", "Powerplay (PP)", "Penalty kill / SH"],
    "Faceoff": ["Alla faceoffs", "DZ faceoffs", "NZ faceoffs", "OZ faceoffs"],
    "Playmaking": ["Alla playmaking", "Passningar", "Successful passing", "Failed passing", "Possession", "Corsi / Fenwick"],
    "NZ": ["Alla NZ", "NZ passing", "NZ defense", "NZ possession"],
    "WOI": ["Alla WOI", "WOI xG", "WOI shots", "WOI goals", "Overall WOI"],
    "Målvakt": ["Alla målvakt", "Shot stopping", "Rebound control", "Traffic / screens", "Puck moving"],
}

TEAM_MATCH_OVERALL_PRESET_METRICS = [
    "Goals", "GF", "GA", "Goals Against", "GAA", "xG", "Expected Goals", "xGA",
    "Expected Goals Against", "XGF%", "XG%", "PP%", "SH%", "PK%", "Save %",
    "SVS%", "Grade A Shot Opportunities", "Grade B Shot Opportunities",
    "Grade C Shot Opportunities", "Points", "Total Goals", "ES XGAP60",
    "ES ACT2XGAP60"
]

PLAYER_OVERALL_PRESET_METRICS = [
    "All shifts", "Games played", "GP", "Time on ice", "TOI", "TOI (min)",
    "TOI (sec)", "Total Games played", "Total TOI/GP (min)",
    "Total TOI/GP (sec)", "+/-", "Plus Minus"
]

GOALIE_OVERALL_PRESET_METRICS = [
    "SVS%", "Save %", "Save%", "Saves %", "Räddnings%", "GA", "Goals Against",
    "GAA", "Retur", "Rebound control", "Traffic", "Trafic", "Screens",
    "Screen", "Goalie SH Save%"
]


def get_overall_preset_list(mode):
    if mode in ["Lag", "Match"]:
        return TEAM_MATCH_OVERALL_PRESET_METRICS
    if mode == "Spelare":
        return PLAYER_OVERALL_PRESET_METRICS
    if mode == "Målvakt":
        return GOALIE_OVERALL_PRESET_METRICS
    return TEAM_MATCH_OVERALL_PRESET_METRICS


def metric_type(metric):
    name = str(metric).lower()
    if "%" in name or "rate" in name or "percentage" in name or "ratio" in name:
        return "Success % / Rate"
    if contains_any(name, ["failed", "lost", "missed", "unsuccessful"]):
        return "Failed / Lost"
    if contains_any(name, ["successful", "won", "save", "on net", "scored", "recovered"]):
        return "Successful / Positive Count"
    if contains_any(name, ["xg", "expected"]):
        return "Expected Value"
    if contains_any(name, ["attempt", "attempts", "total", "shots", "goals", "passes", "entries", "exits"]):
        return "Total Attempts / Count"
    return "Value"


def lower_is_better(metric):
    name = str(metric).lower()
    if contains_any(name, ["denial", "denied", "blocked", "recovery", "recoveries", "save", "saves", "success", "won"]):
        return False
    return contains_any(name, ["against", "gaa", "xga", "failed", "lost", "missed", "giveaway", "turnover", "penalty", "pim"])


def specialteam_state(metric):
    name = f" {str(metric).lower()} "
    compact = str(metric).lower().replace(" ", "")
    if name.strip().startswith("es ") or " es " in name or compact.startswith("es%"):
        return None
    if name.strip().startswith("pp ") or compact.startswith("pp%") or " pp " in name or "power play" in name or "powerplay" in name:
        return "PP"
    if name.strip().startswith("sh ") or compact.startswith("sh%") or name.strip().startswith("pk ") or compact.startswith("pk%") or " sh " in name or " pk " in name or "penalty kill" in name or "short-handed" in name or "shorthanded" in name:
        return "PK_SH"
    return None


def fallback_block(metric):
    name = str(metric).lower()
    state = specialteam_state(metric)
    if state == "PP":
        return "Specialteam", "Powerplay (PP)"
    if state == "PK_SH":
        return "Specialteam", "Penalty kill / SH"
    if "woi" in name:
        return "WOI", "Alla WOI"
    if contains_any(name, ["goalie", "save", "gaa", "gsaxg", "shootout", "svs", "räddning"]):
        return "Målvakt", "Shot stopping"
    if contains_any(name, ["faceoff", "face-off", "faceoffs"]):
        return "Faceoff", "Alla faceoffs"
    if " nz " in f" {name} " or name.startswith("nz"):
        return "NZ", "Alla NZ"
    if contains_any(name, ["entry denial", "denied controlled", "entries against", "controlled entries against"]):
        return "Defensivt", "Entry defense / denial"
    if contains_any(name, ["breakout", "exit", "outlet", "dump out", "carry-out", "pass-out"]):
        return "Defensivt", "Exits / Breakouts"
    if contains_any(name, ["against", "xga", "opposition shot", "shots against", "goals against"]):
        if contains_any(name, ["slot", "screen"]):
            return "Defensivt", "Slot protection"
        return "Defensivt", "Shots against"
    if contains_any(name, ["defensive", "takeaway", "turnover", "denial", "battle", "hit"]):
        return "Defensivt", "Defensive actions"
    if contains_any(name, ["forecheck", "lpr", "loose puck recovery"]):
        return "Offensivt", "Forecheck / LPR"
    if contains_any(name, ["dump-in", "dump in", "chip", "rim dump", "controlled entry", "entries", "entry"]):
        return "Offensivt", "Entries / ingångar"
    if contains_any(name, ["shot", "shots", "goal", "xg", "scoring chance", "slot", "screen", "rebound"]):
        return "Offensivt", "Skott / shot"
    if contains_any(name, ["pass", "passing", "assist", "reception"]):
        return "Playmaking", "Passningar"
    if contains_any(name, ["possession", "corsi", "fenwick", "puck control", "zone time"]):
        return "Playmaking", "Possession"
    return "Overall", "Alla overall metrics"


def derive_subdetail(block, drill, metric):
    name = str(metric).lower()
    if block == "Defensivt" and drill == "Exits / Breakouts":
        if contains_any(name, ["carry-out", "carry out", "stickhandling"]):
            return "Carry out"
        if contains_any(name, ["dump out", "dump-out", "dump-in recovery", "defensive dump-in", "dz dump-in", "rim dump-in", "same-side dump-in", "soft dump-in", "cross-ice dump-in"]):
            return "Dump out / dump-in recovery"
        if contains_any(name, ["pass-out", "pass out", "breakouts via pass"]):
            return "Pass out"
        if contains_any(name, ["outlet", "stretch pass", "stretch passing"]):
            return "Outlet"
        return "Total / overall"
    if block == "Defensivt" and drill in ["Shots against", "Slot protection"]:
        if "slot" in name:
            return "Slot shots against"
        if "screen" in name:
            return "Screened shots against"
        if "rush" in name:
            return "Rush chances against"
        return "Overall shots against"
    if block == "Offensivt" and drill == "Skott / shot":
        if "slot" in name:
            return "Slot shots"
        if "rebound" in name:
            return "Rebounds"
        if "screen" in name:
            return "Screened shots"
        if "rush" in name:
            return "Rush offense"
        return "Overall shots"
    if block == "Offensivt" and drill == "Entries / ingångar":
        if "carry" in name:
            return "Carry entries"
        if contains_any(name, ["dump", "chip", "rim"]):
            return "Dump / chip entries"
        return "Overall entries"
    if block == "Playmaking":
        if "outlet" in name:
            return "Outlet passing"
        if contains_any(name, ["failed", "turnover", "misslyck"]):
            return "Failed passing"
        if contains_any(name, ["successful", "completed", "success rate", "lyckade"]):
            return "Successful passing"
        return "Overall passing"
    if block == "Specialteam":
        state = specialteam_state(metric)
        if state == "PP":
            return "Powerplay"
        if state == "PK_SH":
            return "Penalty kill"
        return "Overall specialteam"
    if block == "WOI":
        if "xg" in name:
            return "WOI xG"
        if "shot" in name:
            return "WOI shots"
        if "goal" in name:
            return "WOI goals"
        return "Overall WOI"
    if block == "Målvakt":
        if "rebound" in name:
            return "Rebound control"
        if "screen" in name or "traffic" in name or "trafic" in name:
            return "Traffic / screens"
        if contains_any(name, ["save", "gaa", "svs"]):
            return "Shot stopping"
        return "Overall goalie"
    return "Overall"


def build_taxonomy_browser(taxonomy_rows, all_metric_names):
    rows = []
    seen = set()
    for r in taxonomy_rows:
        metric = normalize_col_name(r.get("metric", ""))
        if not metric:
            continue
        fallback_b, fallback_d = fallback_block(metric)
        block = r.get("block") or r.get("main") or fallback_b
        drill = r.get("drilldown") or r.get("sub") or fallback_d
        modes = r.get("modes", ["Lag", "Match", "Spelare"])
        direction = r.get("direction") or ("Emot / lägre bättre" if lower_is_better(metric) else "För / högre bättre")
        mtype = r.get("metric_type") or metric_type(metric)
        detail = derive_subdetail(block, drill, metric)
        key = canonical(metric)
        if key and key not in seen:
            seen.add(key)
            rows.append({"Metric": metric, "Block": block, "Drilldown": drill, "Detail": detail, "Modes": ", ".join(modes) if isinstance(modes, list) else str(modes), "Metric Type": mtype, "För/Emot": direction, "Matched taxonomy": True, "Finns i data": False, "Datakolumn": ""})
    for metric in all_metric_names:
        metric = normalize_col_name(metric)
        key = canonical(metric)
        if not key or key in seen:
            continue
        block, drill = fallback_block(metric)
        rows.append({"Metric": metric, "Block": block, "Drilldown": drill, "Detail": derive_subdetail(block, drill, metric), "Modes": "Lag, Match, Spelare, Målvakt", "Metric Type": metric_type(metric), "För/Emot": "Emot / lägre bättre" if lower_is_better(metric) else "För / högre bättre", "Matched taxonomy": True, "Finns i data": False, "Datakolumn": ""})
        seen.add(key)
    return pd.DataFrame(rows)


def build_data_browser(df, entity_col):
    rows = []
    for col in df.columns:
        if col in {entity_col, "Display Name", "Source File", "Match Label", "Report Format"}:
            continue
        if canonical(col) in {"id", "playerid", "teamid", "metricid", "gameid", "matchid"}:
            continue
        if parse_numeric_series(df[col]).notna().sum() == 0:
            continue
        block, drill = fallback_block(col)
        rows.append({"Metric": col, "Block": block, "Drilldown": drill, "Detail": derive_subdetail(block, drill, col), "Modes": "Lag, Match, Spelare, Målvakt", "Metric Type": metric_type(col), "För/Emot": "Emot / lägre bättre" if lower_is_better(col) else "För / högre bättre", "Matched taxonomy": False, "Finns i data": True, "Datakolumn": col})
    return pd.DataFrame(rows)


def combine_taxonomy_and_data(taxonomy_df, data_df):
    if taxonomy_df.empty:
        return data_df.copy()
    data_by_key = {canonical(row["Metric"]): row for _, row in data_df.iterrows() if canonical(row["Metric"])}
    out_rows = []
    for _, row in taxonomy_df.iterrows():
        out = row.to_dict()
        key = canonical(out["Metric"])
        found = data_by_key.get(key)
        if found is None:
            for dkey, drow in data_by_key.items():
                if key and len(key) > 5 and (key in dkey or dkey in key):
                    found = drow
                    break
        if found is not None:
            out["Finns i data"] = True
            out["Datakolumn"] = found["Metric"]
        out_rows.append(out)
    existing = {canonical(r["Metric"]) for r in out_rows}
    for _, row in data_df.iterrows():
        key = canonical(row["Metric"])
        if key and key not in existing:
            out_rows.append(row.to_dict())
    return pd.DataFrame(out_rows)


def infer_match_from_filename(name):
    return re.sub(r"\.(csv|xlsx)$", "", name, flags=re.IGNORECASE).replace("_", " ").strip()


def find_first_existing(df, options):
    for option in options:
        if option in df.columns:
            return option
    return None


def text_like_columns(df):
    return [col for col in df.columns if parse_numeric_series(df[col]).notna().mean() < 0.5]


def auto_entity_column(df, mode):
    if mode == "Lag":
        return find_first_existing(df, ["Team", "Lag", "team"]) or find_first_existing(df, ["Source File", "Match Label"])
    if mode == "Match":
        return "Match Label" if "Match Label" in df.columns else find_first_existing(df, ["Match", "Source File", "Team", "Lag"])
    if mode == "Spelare":
        return find_first_existing(df, ["Player", "Spelare", "Name", "Player Name"]) or find_first_existing(df, ["Team", "Lag"])
    if mode == "Målvakt":
        return find_first_existing(df, ["Goalie", "Player", "Spelare", "Name", "Player Name"]) or find_first_existing(df, ["Team", "Lag"])
    return None


def normalize_series(series, inverse=False, method="Soft"):
    numeric = parse_numeric_series(series)
    if numeric.notna().sum() == 0:
        return pd.Series([0] * len(numeric), index=numeric.index)
    if method == "Percentil":
        return (numeric.rank(pct=True, ascending=inverse) * 100).fillna(0).clip(0, 100)
    min_val, max_val = numeric.min(), numeric.max()
    if min_val == max_val:
        return pd.Series([50] * len(numeric), index=numeric.index)
    if method == "Min/Max":
        return (((max_val - numeric) if inverse else (numeric - min_val)) / (max_val - min_val) * 100).fillna(0).clip(0, 100)
    mid, spread = (min_val + max_val) / 2, max_val - min_val or 1
    return (50 + (((mid - numeric) if inverse else (numeric - mid)) / spread) * 50).fillna(0).clip(0, 100)


def render_analysis_page(analysis_mode):
    st.title(f"🏒 {analysis_mode}")
    st.caption("Taxonomy styr strukturen. Uppladdad data fyller värden.")
    st.markdown("""<style>
    section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label { align-items: flex-start; }
    section[data-testid="stSidebar"] div[data-testid="stCheckbox"] p { white-space: normal !important; line-height: 1.25; font-size: 0.88rem; }
    </style>""", unsafe_allow_html=True)

    taxonomy_rows = load_json_file("taxonomy.json")
    all_metric_names = load_json_file("taxonomy_all_metrics.json")
    taxonomy_df = build_taxonomy_browser(taxonomy_rows, all_metric_names)

    st.sidebar.header("1. Data")
    uploaded_files = st.sidebar.file_uploader("Ladda upp CSV/Excel-filer", type=["csv", "xlsx"], accept_multiple_files=True, key=f"upload_{analysis_mode}")
    frames = []
    if uploaded_files:
        for file in uploaded_files:
            try:
                temp = read_uploaded_file_cached(file.name, file.getvalue())
                temp = temp.copy()
                temp.columns = [normalize_col_name(c) for c in temp.columns]
                temp["Source File"] = file.name
                temp["Match Label"] = infer_match_from_filename(file.name)
                temp["Report Format"] = "Uploaded"
                frames.append(temp)
            except Exception as e:
                st.sidebar.error(f"Kunde inte läsa {file.name}: {e}")
    if frames:
        df = pd.concat(frames, ignore_index=True, sort=False)
    else:
        df = pd.DataFrame({"Team": ["Demo Team"], "Match Label": ["Demo"], "Source File": ["Demo"], "Goals": [3], "xG": [2.4], "Shots": [28], "Save %": [91.2]})
    df.columns = [normalize_col_name(c) for c in df.columns]

    auto_entity = auto_entity_column(df, analysis_mode)
    st.sidebar.header("2. Analys")
    with st.sidebar.expander("Avancerat: jämförelsekolumn", expanded=False):
        entity_options = text_like_columns(df) or list(df.columns)
        if auto_entity not in entity_options and entity_options:
            auto_entity = entity_options[0]
        entity_col = st.selectbox("Jämför på", options=entity_options, index=entity_options.index(auto_entity) if auto_entity in entity_options else 0, key=f"entity_{analysis_mode}")
    st.sidebar.caption(f"Jämför på: **{entity_col}**")

    st.sidebar.header("3. Filter")
    team_col = find_first_existing(df, ["Team", "Lag", "team"])
    match_col = "Match Label" if "Match Label" in df.columns else ("Source File" if "Source File" in df.columns else None)
    if team_col:
        teams = sorted(df[team_col].dropna().astype(str).unique().tolist())
        selected_teams = st.sidebar.multiselect("Filtrera lag", options=teams, default=teams, key=f"teams_{analysis_mode}")
        df = df[df[team_col].astype(str).isin(selected_teams)]
    if match_col:
        matches = sorted(df[match_col].dropna().astype(str).unique().tolist())
        selected_matches = st.sidebar.multiselect("Filtrera matcher/källor", options=matches, default=matches, key=f"matches_{analysis_mode}")
        df = df[df[match_col].astype(str).isin(selected_matches)]

    df[entity_col] = df[entity_col].astype(str).str.strip()
    if analysis_mode == "Match":
        df["Display Name"] = df[entity_col].astype(str)
    elif analysis_mode == "Lag" and match_col:
        df["Display Name"] = df[entity_col].astype(str) + " | " + df[match_col].astype(str)
    elif team_col and match_col:
        df["Display Name"] = df[entity_col].astype(str) + " | " + df[team_col].astype(str) + " | " + df[match_col].astype(str)
    else:
        df["Display Name"] = df[entity_col].astype(str)

    data_browser_df = build_data_browser(df, entity_col)
    browser_df = combine_taxonomy_and_data(taxonomy_df, data_browser_df)

    if browser_df.empty:
        st.error("Inga metrics hittades.")
        st.stop()

    st.sidebar.header("4. Välj analysblock")
    normalization_method = st.sidebar.selectbox("Normalisering", ["Soft", "Min/Max", "Percentil"], index=0, key=f"norm_{analysis_mode}")
    selected_block = st.sidebar.radio("Analysblock", options=BLOCKS_BY_MODE[analysis_mode], index=0, key=f"block_{analysis_mode}")
    if selected_block == "Alla hittade metrics":
        block_df = browser_df[browser_df["Finns i data"] == True].copy()
    elif selected_block == "Saknade metrics":
        block_df = browser_df[browser_df["Finns i data"] == False].copy()
    elif selected_block == "Alla taxonomy metrics":
        block_df = browser_df.copy()
    elif selected_block == "Overall":
        presets = get_overall_preset_list(analysis_mode)
        preset_keys = [canonical(p) for p in presets]
        block_df = browser_df[browser_df["Metric"].map(lambda m: any(k and (k in canonical(m) or canonical(m) in k) for k in preset_keys))].copy()
        if not block_df.empty:
            block_df["Drilldown"] = "Overall preset"
    else:
        block_df = browser_df[browser_df["Block"] == selected_block].copy()
    if block_df.empty:
        st.sidebar.warning("Inga metrics hittades i detta block.")
        st.stop()

    real_drills = sorted(block_df["Drilldown"].dropna().astype(str).unique().tolist())
    if selected_block == "Specialteam":
        drill_options = ["Båda (PP + PK/SH)", "Powerplay (PP)", "Penalty kill / SH"]
    elif selected_block in ["Alla hittade metrics", "Saknade metrics", "Alla taxonomy metrics"]:
        drill_options = [selected_block]
    elif selected_block == "Overall":
        drill_options = ["Overall preset"]
    else:
        base_drills = DEFAULT_DRILLDOWNS.get(selected_block, ["Alla"])
        drill_options = [d for d in base_drills if d in real_drills or d.startswith("Alla")]
        drill_options += [d for d in real_drills if d not in drill_options]
    selected_drill = st.sidebar.selectbox("Underblock", options=drill_options, index=0, key=f"drill_{analysis_mode}")
    if selected_drill in ["Båda (PP + PK/SH)", "Overall preset", "Alla hittade metrics", "Saknade metrics", "Alla taxonomy metrics"] or selected_drill.startswith("Alla"):
        drill_df = block_df.copy()
    elif selected_drill == "Powerplay (PP)":
        drill_df = block_df[block_df["Drilldown"].astype(str).str.contains("Powerplay|PP", case=False, na=False)].copy()
    elif selected_drill == "Penalty kill / SH":
        drill_df = block_df[block_df["Drilldown"].astype(str).str.contains("Penalty kill|PK|SH", case=False, na=False)].copy()
    else:
        drill_df = block_df[block_df["Drilldown"] == selected_drill].copy()

    details = sorted([d for d in drill_df.get("Detail", pd.Series(dtype=str)).dropna().astype(str).unique().tolist() if d and d != "Alla"])
    if details:
        selected_detail = st.sidebar.selectbox("Underkategori", options=["Alla"] + details, index=0, key=f"detail_{analysis_mode}")
        if selected_detail != "Alla":
            drill_df = drill_df[drill_df["Detail"] == selected_detail].copy()
    else:
        selected_detail = "Alla"

    search = st.sidebar.text_input("Sök inom valt block", placeholder="Ex: entry, slot, dump...", key=f"search_block_{analysis_mode}").strip().lower()
    if search:
        drill_df = drill_df[drill_df["Metric"].astype(str).str.lower().str.contains(search, na=False)]
    if drill_df.empty:
        st.warning("Inga metrics matchar urvalet.")
        st.stop()

    available_metrics = drill_df[drill_df["Finns i data"] == True]["Metric"].dropna().unique().tolist()
    metrics = drill_df["Metric"].dropna().unique().tolist()
    select_mode = st.sidebar.radio("Metric-urval", ["Rekommenderade", "Alla som finns i data", "Alla från taxonomy", "Manuellt"], horizontal=False, key=f"metric_mode_{analysis_mode}")
    if select_mode == "Alla som finns i data":
        default_metrics = available_metrics
    elif select_mode == "Alla från taxonomy":
        default_metrics = metrics
    elif select_mode == "Rekommenderade":
        default_metrics = available_metrics if selected_block == "Overall" else available_metrics[:min(12, len(available_metrics))]
    else:
        default_metrics = []
    default_set = set(default_metrics)

    metric_search = st.sidebar.text_input("Sök i metric-listan", placeholder="Ex: slot, pass, exit...", key=f"metric_search_{analysis_mode}").strip().lower()
    visible_df = drill_df.copy()
    if metric_search:
        visible_df = visible_df[visible_df["Metric"].astype(str).str.lower().str.contains(metric_search, na=False)]

    selected_metrics = []
    st.sidebar.markdown("**Metrics**")
    for metric in visible_df["Metric"].dropna().unique().tolist():
        meta = drill_df[drill_df["Metric"] == metric]
        exists = bool(meta.iloc[0]["Finns i data"]) if not meta.empty else False
        prefix = "✅" if exists else "⚪"
        checked = st.sidebar.checkbox(f"{prefix} {metric}", value=metric in default_set, key=f"metric_{analysis_mode}_{canonical(metric)}_{selected_block}_{selected_drill}_{selected_detail}")
        if checked:
            selected_metrics.append(metric)
        if not meta.empty:
            st.sidebar.caption(f"{meta.iloc[0].get('Metric Type','')} | {meta.iloc[0].get('För/Emot','')}")
    if not selected_metrics:
        st.warning("Välj minst en metric.")
        st.stop()

    metric_to_data_col = {}
    for metric in selected_metrics:
        row = browser_df[browser_df["Metric"] == metric]
        if not row.empty and bool(row.iloc[0].get("Finns i data", False)):
            datacol = row.iloc[0].get("Datakolumn", "")
            if datacol and datacol in df.columns:
                metric_to_data_col[metric] = datacol
    available_selected_metrics = list(metric_to_data_col.keys())
    if not available_selected_metrics:
        st.warning("Valda metrics syns i taxonomy men saknar värden i uppladdad data.")
        st.stop()

    df_work = df.copy()
    for metric, datacol in metric_to_data_col.items():
        if metric not in df_work.columns:
            df_work[metric] = df_work[datacol]
    agg = {metric: (lambda s: parse_numeric_series(s).mean()) for metric in available_selected_metrics}
    compare_df = df_work.groupby("Display Name", dropna=False).agg(agg).reset_index()
    entities = compare_df["Display Name"].dropna().astype(str).unique().tolist()
    selected_entities = st.sidebar.multiselect("5. Välj vilka som visas", options=entities, default=entities[:min(5, len(entities))], key=f"entities_{analysis_mode}")
    compare_df = compare_df[compare_df["Display Name"].astype(str).isin(selected_entities)]

    index_df = compare_df[["Display Name"]].copy()
    for metric in available_selected_metrics:
        if metric in compare_df.columns:
            index_df[metric] = normalize_series(compare_df[metric], inverse=lower_is_better(metric), method=normalization_method)
    selected_metrics_for_chart = [m for m in available_selected_metrics if m in index_df.columns]
    if not selected_metrics_for_chart:
        st.warning("Inga metrics kunde ritas.")
        st.stop()

    tab_spider, tab_profile, tab_browser, tab_data = st.tabs(["📊 Spiderchart", "🧾 Profilkort", "🔎 Metric Browser", "📘 Data"])
    with tab_spider:
        st.subheader("📊 Spiderchart")
        st.caption(f"Analysläge: {analysis_mode} | Block: {selected_block} | Underblock: {selected_drill}")
        fig = go.Figure()
        for _, row in index_df.iterrows():
            values = [safe_row_value(row, metric, 0) for metric in selected_metrics_for_chart]
            values = [max(0, min(100, v)) for v in values]
            if len(values) == 1:
                r_values = values + values
                theta = selected_metrics_for_chart + selected_metrics_for_chart
            else:
                r_values = values + [values[0]]
                theta = selected_metrics_for_chart + [selected_metrics_for_chart[0]]
            fig.add_trace(go.Scatterpolar(r=r_values, theta=theta, fill="toself", name=str(row["Display Name"])))
        fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), height=760, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)
    with tab_profile:
        st.subheader("🧾 Profilkort")
        for _, row in index_df.iterrows():
            st.markdown(f"### {row['Display Name']}")
            cols = st.columns(min(4, max(1, len(selected_metrics_for_chart))))
            for i, metric in enumerate(selected_metrics_for_chart):
                value = safe_row_value(row, metric, 0)
                with cols[i % len(cols)]:
                    st.metric(metric, f"{value:.1f}")
                    st.progress(int(max(0, min(100, value))))
            st.divider()
    with tab_browser:
        st.subheader("🔎 Metric Browser")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Taxonomy metrics", len(taxonomy_df))
        c2.metric("Metrics i data", len(data_browser_df))
        c3.metric("Valda metrics", len(selected_metrics_for_chart))
        c4.metric("Analysläge", analysis_mode)
        browser_search = st.text_input("Sök i browser", value=search, key=f"browser_search_{analysis_mode}")
        display_browser = browser_df.copy()
        if browser_search:
            display_browser = display_browser[
                display_browser["Metric"].astype(str).str.lower().str.contains(browser_search.lower(), na=False)
                | display_browser["Block"].astype(str).str.lower().str.contains(browser_search.lower(), na=False)
                | display_browser["Drilldown"].astype(str).str.lower().str.contains(browser_search.lower(), na=False)
                | display_browser["Detail"].astype(str).str.lower().str.contains(browser_search.lower(), na=False)
            ]
        st.dataframe(display_browser.sort_values(["Block", "Drilldown", "Detail", "Metric"]), use_container_width=True)
    with tab_data:
        st.subheader("📘 Rådata")
        st.dataframe(df, use_container_width=True)
        st.subheader("📈 Indexdata")
        st.dataframe(index_df, use_container_width=True)
        st.subheader("Jämförelsedata")
        st.dataframe(compare_df, use_container_width=True)
