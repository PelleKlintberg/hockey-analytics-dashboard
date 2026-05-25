import re
import math
import json
from typing import List, Dict, Tuple

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ==================================================
# SAFE VALUE HELPER
# ==================================================

def safe_row_value(row, metric, default=0):
    """
    Säker hämtning av värde från en pandas-rad.
    Hindrar KeyError om taxonomy-metric saknar datakolumn.
    """
    try:
        if metric in row.index and pd.notna(row[metric]):
            return float(row[metric])
    except Exception:
        pass
    return default


# ==================================================
# EMBEDDED FULL TAXONOMY
# ==================================================
def load_taxonomy_file():
    """
    Loads taxonomy from taxonomy.json instead of embedding it in app.py.
    This makes Streamlit Cloud start faster.
    """
    import json
    from pathlib import Path

    path = Path(__file__).parent / "taxonomy.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


EMBEDDED_TAXONOMY_ROWS = load_taxonomy_file()
MASTER_TAXONOMY_ROWS = EMBEDDED_TAXONOMY_ROWS

def load_full_taxonomy_metrics_file():
    import json
    from pathlib import Path

    path = Path(__file__).parent / "taxonomy_all_metrics.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


FULL_TAXONOMY_METRICS = load_full_taxonomy_metrics_file()




# ==================================================
# SAFE TAXONOMY FALLBACK
# ==================================================

# Säkerställ att taxonomy alltid existerar.
# Om taxonomy-filen inte laddats korrekt ska appen fortfarande fungera.
try:
    MASTER_TAXONOMY_ROWS
except NameError:
    MASTER_TAXONOMY_ROWS = []


# ==================================================
# APP SETUP
# ==================================================
st.set_page_config(page_title="Hockey Analytics Dashboard Web Optimized", layout="wide")
st.title("🏒 Hockey Analytics Dashboard Web Optimized")
st.caption("Hybrid: taxonomy styr strukturen. Exits/Breakouts har nu extra nivå: utgångstyp → metrics.")


st.markdown("""
<style>
section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label {
    align-items: flex-start;
}
section[data-testid="stSidebar"] div[data-testid="stCheckbox"] p {
    white-space: normal !important;
    line-height: 1.25;
    font-size: 0.88rem;
}
section[data-testid="stSidebar"] div[data-testid="stCaptionContainer"] {
    margin-top: -0.35rem;
    margin-bottom: 0.35rem;
    color: #6b7280;
}
</style>
""", unsafe_allow_html=True)


# ==================================================
# CONSTANTS
# ==================================================
ANALYSIS_MODES = ["Lag", "Match", "Spelare", "Målvakt"]

BLOCKS_BY_MODE = {
    "Lag": ["Overall", "Defensivt", "Offensivt", "Specialteam", "Faceoff", "Playmaking", "NZ"],
    "Match": ["Overall", "Defensivt", "Offensivt", "Specialteam", "Faceoff", "Playmaking", "NZ"],
    "Spelare": ["Overall", "Generell", "Offensivt", "Defensivt", "WOI", "Specialteam", "Faceoff", "Playmaking", "NZ"],
    "Målvakt": ["Overall", "Målvakt", "Specialteam"],
}

DRILLDOWN_BY_BLOCK = {
    "Overall": ["Alla overall metrics"],
    "Generell": ["Alla generella metrics"],
    "Defensivt": [
        "Alla defensiva",
        "Exits / Breakouts",
        "Entry defense / denial",
        "Shots against",
        "Slot protection",
        "Defensive actions",
    ],
    "Offensivt": [
        "Alla offensiva",
        "Entries / ingångar",
        "Dump-in / chip-in / rim",
        "Carry entries",
        "Pass entries",
        "Skott / shot",
        "Slot shots",
        "Inner slot",
        "Rebound / second chance",
        "Screen / traffic",
        "OZ-passningar",
        "Scoring chances",
        "Forecheck / LPR",
    ],
    "Specialteam": [
        "Båda (PP + PK/SH)",
        "Powerplay (PP)",
        "Penalty kill / SH",
    ],
    "Faceoff": ["Alla faceoffs", "DZ faceoffs", "NZ faceoffs", "OZ faceoffs"],
    "Playmaking": ["Alla playmaking", "Passningar", "Lyckade passningar", "Misslyckade passningar", "Possession", "Corsi / Fenwick"],
    "NZ": ["Alla NZ", "NZ passing", "NZ defense", "NZ possession"],
    "WOI": ["Alla WOI", "WOI xG / chances", "WOI shots", "WOI goals", "WOI possession", "WOI transition"],
    "Målvakt": ["Alla målvakt", "Shot stopping", "Rebound control", "Puck moving", "Shootout", "Short-handed saves"],
}


# ==================================================
# HARD PRESET TAXONOMY PATCHES
# ==================================================
# Dessa ligger alltid i rätt block även om kolumnen saknas i uppladdad data.
# Data matchas sedan mot metricnamnet och markeras som "Finns i data".

HARD_PRESET_ROWS = [
    # Defense / Exits / Breakouts - Overall
    {"metric": "Breakouts", "block": "Defensivt", "drilldown": "Exits / Breakouts"},
    {"metric": "Breakouts via stickhandling", "block": "Defensivt", "drilldown": "Exits / Breakouts"},
    {"metric": "Controlled Exit with Play After Rate", "block": "Defensivt", "drilldown": "Exits / Breakouts"},
    {"metric": "Controlled Exits", "block": "Defensivt", "drilldown": "Exits / Breakouts"},
    {"metric": "Controlled Exits with Play After", "block": "Defensivt", "drilldown": "Exits / Breakouts"},
    {"metric": "ES Breakout Exit Success% (with OZ Possession", "block": "Defensivt", "drilldown": "Exits / Breakouts"},
    {"metric": "ES Breakout Exit Success% (with OZ Possession)", "block": "Defensivt", "drilldown": "Exits / Breakouts"},
    {"metric": "ES Zone Exit Success% (with OZ Possession)", "block": "Defensivt", "drilldown": "Exits / Breakouts"},
    {"metric": "ES% Pressure OZ Dump-Ins Without Opposition Exit on Forecheck", "block": "Defensivt", "drilldown": "Exits / Breakouts"},
    {"metric": "Overall DZ Denial and Exit Percentage", "block": "Defensivt", "drilldown": "Exits / Breakouts"},

    # Carry out
    {"metric": "Carry-Out with Play After Rate", "block": "Defensivt", "drilldown": "Carry out"},
    {"metric": "Carry-Outs with Play After", "block": "Defensivt", "drilldown": "Carry out"},
    {"metric": "Total Carry-Out Attempts", "block": "Defensivt", "drilldown": "Carry out"},

    # Dump out / dump-in recovery exit
    {"metric": "ES Dump-In Attempts Against", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "ES Dump-In Rate Against", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "ES Average Gap on Dump-Ins Against", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "Breakouts via dump out", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "Defensive Dump-In Recovery Exit Rate", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "Dump Out Rate", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "Dump Out Success Rate", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "Dump outs", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "ES% DZ Dump-In Recovery & Exit", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "ES% DZ Cross-Ice Dump-In Recovery & Exit", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "ES% Pressure DZ Dump-In Recoveries with Clean Exit", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "Successful Dump Out Attempts", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "Total Dump Out Attempts", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "ES% DZ Rim Dump-In Recovery & Exit", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "ES% DZ Same-Side Dump-In Recovery & Exit", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "ES% DZ Soft Dump-In Recovery & Exit", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "Total Defensive Dump-In Recoveries", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "ES Pressure DZ Dump-In Recoveries", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "ES Successful Dump-In Recoveries by Opposition", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "ES% DZ Dump-In Recoveries Under Pressure", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "ES% Pressure DZ Dump-In Recoveries with 1st Play Successful", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "Failed Defensive Dump-In Recoveries", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "Successful Defensive Dump-In Recoveries", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},
    {"metric": "ES DZ Dump-In Recoveries", "block": "Defensivt", "drilldown": "Dump out / dump-in recovery exit"},

    # Pass out
    {"metric": "Breakouts via pass", "block": "Defensivt", "drilldown": "Pass out"},
    {"metric": "Pass-Out Success Rate", "block": "Defensivt", "drilldown": "Pass out"},
    {"metric": "Pass-Out with Play After Rate", "block": "Defensivt", "drilldown": "Pass out"},
    {"metric": "Pass-Outs with Play After", "block": "Defensivt", "drilldown": "Pass out"},

    # Outlet
    {"metric": "Outlet Pass Success Rate", "block": "Defensivt", "drilldown": "Outlet"},
    {"metric": "Outlet Passing Tendency", "block": "Defensivt", "drilldown": "Outlet"},
    {"metric": "Stretch Pass Success Rate", "block": "Defensivt", "drilldown": "Outlet"},
    {"metric": "Stretch Passing Tendency", "block": "Defensivt", "drilldown": "Outlet"},
    {"metric": "Total Outlet Pass Attempts", "block": "Defensivt", "drilldown": "Outlet"},
    {"metric": "Total Stretch Pass Attempts", "block": "Defensivt", "drilldown": "Outlet"},
]

TECHNICAL_EXCLUDE_EXACT = {
    "id", "player id", "team id", "metric id", "game id", "match id",
    "age", "height", "jersey", "jersey number", "jerseynumber", "career",
    "section", "section name", "players", "opposing metric label",
}

# Overall är ett preset från din taxonomy. Det behöver inte finnas som kategori i filen.
# Appen försöker hitta dessa metrics bland uppladdade kolumner via exact/fuzzy matchning.
TEAM_MATCH_OVERALL_PRESET_METRICS = [
    "Goals/GF/Mål framåt",
    "Goals",
    "GF",
    "Mål framåt",
    "GA/Mål bakåt",
    "Goals Against",
    "GA",
    "Mål bakåt",
    "GFA/Mål framåt average",
    "GAA/mål bakåt average",
    "GAA",
    "XG/ Expected Goals",
    "xG",
    "Expected Goals",
    "XGA/ Expected Goals Against",
    "xGA",
    "Expected Goals Against",
    "XGF%",
    "XG%",
    "ES Actual to Expected Goals For",
    "ES Actual to Expected Goals against",
    "Actual to Expected Goals",
    "PP%",
    "SH/PK%",
    "SH%",
    "PK%",
    "Saves%",
    "SVS%",
    "Save %",
    "Räddnings%",
    "Grade A Shot Opportunities",
    "Grade B Shot Opportunities",
    "Grade C Shot Opportunities",
    "Grade A Shot",
    "Grade B Shot",
    "Grade C Shot",
    "Error leading to goal",
    "ES Goals Scored",
    "Expected Goals Corsi Ratio",
    "Goals From Slot",
    "Goals Off OZ Play From Slot",
    "Goals Off-the-Cycle From Slot",
    "Goals Off-the-Forecheck From Slot",
    "Points",
    "Total Goals",
    "Total Regular Goals",
    "Total Regular Goals From Inner Slot",
    "Total Regular Goals From Outside Slot",
    "xG (Expected goals)",
    "xG per goal",
    "xG per goal conceded",
    "ES ACT2XGAP60",
    "ES XGAP60",
]

PLAYER_OVERALL_PRESET_METRICS = [
    "All shifts",
    "Games played",
    "GP",
    "Time on ice",
    "TOI",
    "TOI (min)",
    "TOI (sec)",
    "Total Games played",
    "Total Games Played",
    "Total TOI/GP (min)",
    "Total TOI/GP (sec)",
    "+/-",
    "Plus Minus",
]

GOALIE_OVERALL_PRESET_METRICS = [
    "SVS%",
    "Save %",
    "Save%",
    "Saves %",
    "Räddnings%",
    "Räddnings %",
    "GA",
    "Goals Against",
    "GAA",
    "Retur",
    "Rebound control",
    "Rebound Control",
    "Rebounds",
    "Traffic",
    "Trafic",
    "Screens",
    "Screen",
    "Goalie SH Save%",
]


# ==================================================
# DEMO DATA
# ==================================================
sample_data = pd.DataFrame({
    "Player": ["Player A", "Player B", "Goalie C", "Player A", "Player B"],
    "Team": ["Mora IK", "SSK", "Mora IK", "Mora IK", "Nybro"],
    "Position": ["D", "F", "G", "D", "F"],
    "Match": ["Mora vs SSK", "Mora vs SSK", "Mora vs SSK", "Mora vs Nybro", "Mora vs Nybro"],
    "TOI (sec)": [3600, 3300, 3900, 3500, 3200],
    "GP": [1, 1, 1, 1, 1],
    "Goals": [2, 1, 0, 0, 2],
    "Assists": [1, 2, 0, 1, 1],
    "Points": [3, 3, 0, 1, 3],
    "Shots": [7, 4, 0, 3, 8],
    "xGF%": [55.2, 48.1, 0, 49.2, 61.3],
    "Breakouts": [12, 8, 0, 14, 9],
    "Breakouts via pass": [7, 4, 0, 8, 5],
    "Dump outs": [2, 1, 0, 2, 2],
    "ES Shot Attempts From Slot Against": [5, 8, 0, 4, 9],
    "DZ Entry Denial Rate": [48, 39, 0, 52, 35],
    "OZ Pass Attempts": [18, 25, 0, 16, 30],
    "Controlled Entries": [16, 22, 0, 14, 28],
    "PP Expected Goals For": [1.2, 1.1, 0, 1.4, 1.7],
    "Faceoffs won, %": [51, 48, 0, 53, 49],
    "ES XGFP60 (WOI)": [2.4, 1.8, 0, 2.1, 2.9],
    "Save %": [0, 0, 91.8, 0, 0],
    "GAA": [0, 0, 2.14, 0, 0],
})

# ==================================================
# BASIC HELPERS
# ==================================================
def canonical(s: str) -> str:
    return re.sub(r"[^a-z0-9åäö]+", "", str(s).lower())


def get_overall_preset_list(analysis_mode):
    if analysis_mode in ["Lag", "Match"]:
        return TEAM_MATCH_OVERALL_PRESET_METRICS
    if analysis_mode == "Spelare":
        return PLAYER_OVERALL_PRESET_METRICS
    if analysis_mode == "Målvakt":
        return GOALIE_OVERALL_PRESET_METRICS
    return TEAM_MATCH_OVERALL_PRESET_METRICS


def find_overall_preset_metrics(available_metrics, analysis_mode):
    """
    Hittar uppladdade kolumner som motsvarar Overall-paketet för valt analysläge.
    Lag/Match, Spelare och Målvakt har olika Overall-paket.
    """
    preset_metrics = get_overall_preset_list(analysis_mode)

    available = [m for m in list(available_metrics) if m is not None]
    by_key = {canonical(m): m for m in available}
    selected = []

    def add_metric(metric):
        if metric is not None and metric not in selected:
            selected.append(metric)

    for preset in preset_metrics:
        if preset is None:
            continue

        preset_text = str(preset)
        raw_parts = re.split(r"[()/]+", preset_text)
        preset_parts = [str(p).strip() for p in raw_parts if p is not None and str(p).strip()]

        candidate_keys = [canonical(preset_text)] + [canonical(p) for p in preset_parts]
        candidate_keys = [k for k in candidate_keys if k]

        # exact canonical match
        for key in candidate_keys:
            if key in by_key:
                add_metric(by_key[key])

        # relaxed contains match
        for key in candidate_keys:
            if not key or len(key) < 3:
                continue
            for available_key, original in by_key.items():
                if not available_key:
                    continue
                if key == available_key:
                    add_metric(original)
                elif len(key) >= 4 and (key in available_key or available_key in key):
                    add_metric(original)

    return selected


def normalize_col_name(col) -> str:
    return re.sub(r"\s+", " ", str(col).strip().replace('"', ""))


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [normalize_col_name(c) for c in df.columns]
    return df


def parse_numeric_series(s: pd.Series) -> pd.Series:
    if getattr(s, "dtype", None) is not None and s.dtype.kind in "biufc":
        return pd.to_numeric(s, errors="coerce")
    return pd.to_numeric(
        s.astype(str)
        .str.replace("%", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.replace("−", "-", regex=False)
        .str.strip(),
        errors="coerce",
    )


def contains_any(text: str, words: List[str]) -> bool:
    text = str(text).lower()
    return any(w.lower() in text for w in words)


def specialteam_state(metric: str):
    """
    Returnerar PP, PK_SH eller None.
    Viktigt: ES ska aldrig räknas som specialteam.
    Vi använder token-regler så att 'opposition' inte feltolkas som PP.
    """
    name = f" {str(metric).lower()} "
    compact = str(metric).lower().replace(" ", "")

    # Even strength ska inte specialteam-routas.
    if name.strip().startswith("es ") or " es " in name or compact.startswith("es%"):
        return None

    is_pp = (
        name.strip().startswith("pp ")
        or compact.startswith("pp%")
        or " pp " in name
        or " pp%" in name
        or "power play" in name
        or "powerplay" in name
    )

    is_pk_sh = (
        name.strip().startswith("sh ")
        or compact.startswith("sh%")
        or " sh " in name
        or " sh%" in name
        or name.strip().startswith("pk ")
        or compact.startswith("pk%")
        or " pk " in name
        or " pk%" in name
        or "penalty kill" in name
        or "penalty killing" in name
        or "short-handed" in name
        or "shorthanded" in name
    )

    if is_pp:
        return "PP"
    if is_pk_sh:
        return "PK_SH"
    return None


def is_specialteam_metric(metric: str) -> bool:
    return specialteam_state(metric) is not None


def is_excluded_column(col: str) -> bool:
    c = canonical(col)
    if c in {canonical(x) for x in TECHNICAL_EXCLUDE_EXACT}:
        return True
    if c.endswith("id") and len(c) <= 18:
        return True
    return False


def text_like_columns(df: pd.DataFrame) -> List[str]:
    cols = []
    for col in df.columns:
        if parse_numeric_series(df[col]).notna().mean() < 0.5:
            cols.append(col)
    return cols


def find_first_existing(df: pd.DataFrame, candidates: List[str]):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def infer_match_from_filename(filename: str) -> str:
    name = re.sub(r"\.(csv|xlsx)$", "", filename, flags=re.IGNORECASE)
    name = name.replace("_", " ")
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def read_uploaded_file(file) -> pd.DataFrame:
    name = file.name.lower()
    if name.endswith(".xlsx"):
        return pd.read_excel(file)
    attempts = [
        {"sep": ",", "encoding": "utf-8-sig"},
        {"sep": ";", "encoding": "utf-8-sig", "decimal": ","},
        {"sep": None, "engine": "python", "encoding": "utf-8-sig"},
    ]
    last_error = None
    for kwargs in attempts:
        try:
            file.seek(0)
            return pd.read_csv(file, **kwargs)
        except Exception as e:
            last_error = e
    raise last_error

# ==================================================
# LONG-FORM SUPPORT
# ==================================================
def looks_like_long_metric_report(df: pd.DataFrame) -> bool:
    if df.empty:
        return False
    text_cols = text_like_columns(df)
    numeric_cols = [c for c in df.columns if parse_numeric_series(df[c]).notna().sum() > 0]
    if len(text_cols) >= 1 and len(numeric_cols) >= 1 and len(df) > 5:
        first_text = text_cols[0]
        unique_text = df[first_text].dropna().astype(str).nunique()
        return unique_text >= min(5, max(1, len(df) // 4))
    return False


def convert_long_metric_report_to_wide(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    df = clean_dataframe(df)
    text_cols = text_like_columns(df)
    numeric_cols = [c for c in df.columns if parse_numeric_series(df[c]).notna().sum() > 0]
    if not text_cols or not numeric_cols:
        return df

    metric_col = None
    for c in text_cols:
        if any(t in c.lower() for t in ["metric", "parameter", "stat", "label", "name"]):
            metric_col = c
            break
    if metric_col is None:
        metric_col = text_cols[0]

    value_col = None
    for c in numeric_cols:
        if any(t in c.lower() for t in ["value", "värde", "total", "rate", "%", "count"]):
            value_col = c
            break
    if value_col is None:
        value_col = numeric_cols[0]

    wide = {}
    for metric, value in zip(df[metric_col].astype(str), parse_numeric_series(df[value_col])):
        metric = normalize_col_name(metric)
        if not metric or metric.lower() in ["nan", "none"]:
            continue
        if pd.isna(value) or is_excluded_column(metric):
            continue
        if metric not in wide:
            wide[metric] = value

    if not wide:
        return df

    out = pd.DataFrame([wide])
    out["Source File"] = source_name
    out["Match Label"] = infer_match_from_filename(source_name)
    out["Report Format"] = "Long metric report converted to wide"

    for possible in ["Team", "Lag", "Player", "Spelare", "Goalie", "Position", "Opponent"]:
        if possible in df.columns and possible not in out.columns:
            non_empty = df[possible].dropna().astype(str)
            if not non_empty.empty:
                out[possible] = non_empty.iloc[0]

    if not any(c in out.columns for c in ["Team", "Lag", "Player", "Spelare", "Goalie"]):
        out["Team"] = infer_match_from_filename(source_name)
    return out


def prepare_uploaded_dataframe(raw_df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    raw_df = clean_dataframe(raw_df)
    if looks_like_long_metric_report(raw_df):
        return convert_long_metric_report_to_wide(raw_df, source_name)
    raw_df["Source File"] = source_name
    raw_df["Match Label"] = infer_match_from_filename(source_name)
    raw_df["Report Format"] = "Wide report"
    return raw_df

# ==================================================
# REPORT DETECTION
# ==================================================
def score_report_types(df: pd.DataFrame) -> Dict[str, int]:
    cols = [str(c).lower() for c in df.columns]
    joined = " ".join(cols)
    scores = {mode: 0 for mode in ANALYSIS_MODES}
    if any(c in df.columns for c in ["Team", "Lag", "team"]):
        scores["Lag"] += 5
    if "Match Label" in df.columns or "Source File" in df.columns or any("match" in c for c in cols):
        scores["Match"] += 3
    if any(c in df.columns for c in ["Player", "Spelare", "Name", "Player Name"]):
        scores["Spelare"] += 6
    if "Position" in df.columns:
        scores["Spelare"] += 2
    if any(term in joined for term in ["goalie", "save", "saves", "save %", "save%", "gaa", "gsaxg", "svs", "räddning"]):
        scores["Målvakt"] += 8
    if "Team" in df.columns and "Player" in df.columns and df["Player"].dropna().astype(str).nunique() > 1:
        scores["Spelare"] += 4
    if "Match Label" in df.columns and df["Match Label"].dropna().astype(str).nunique() > 1:
        scores["Match"] += 3
    return scores


def suggested_analysis_mode(df: pd.DataFrame) -> str:
    scores = score_report_types(df)
    return max(scores, key=scores.get)


def auto_entity_column(df: pd.DataFrame, analysis_mode: str):
    if analysis_mode == "Lag":
        return find_first_existing(df, ["Team", "Lag", "team"]) or find_first_existing(df, ["Source File", "Match Label"])
    if analysis_mode == "Match":
        return "Match Label" if "Match Label" in df.columns else find_first_existing(df, ["Match", "Source File", "Team", "Lag"])
    if analysis_mode == "Spelare":
        return find_first_existing(df, ["Player", "Spelare", "Name", "Player Name"]) or find_first_existing(df, ["Team", "Lag"])
    if analysis_mode == "Målvakt":
        return find_first_existing(df, ["Goalie", "Player", "Spelare", "Name", "Player Name"]) or find_first_existing(df, ["Team", "Lag"])
    return None

# ==================================================
# CLASSIFICATION
# ==================================================
def fallback_block(metric: str) -> Tuple[str, str]:
    name = str(metric).lower()
    state = specialteam_state(metric)

    # 1. Specialteam måste vara hårdast: bara PP / SH / PK.
    if state == "PP":
        return "Specialteam", "Powerplay (PP)"
    if state == "PK_SH":
        return "Specialteam", "Penalty kill / SH"

    # 2. WOI
    if "woi" in name:
        return "WOI", "Alla WOI"

    # 3. Målvakt
    if contains_any(name, ["goalie", "save", "gaa", "gsaxg", "shootout", "svs", "räddning"]):
        return "Målvakt", "Shot stopping"

    # 4. Faceoff
    if contains_any(name, ["faceoff", "face-off", "faceoffs"]):
        if "dz" in name:
            return "Faceoff", "DZ faceoffs"
        if "nz" in name:
            return "Faceoff", "NZ faceoffs"
        if "oz" in name:
            return "Faceoff", "OZ faceoffs"
        return "Faceoff", "Alla faceoffs"

    # 5. NZ
    if " nz " in f" {name} " or name.startswith("nz"):
        if "pass" in name:
            return "NZ", "NZ passing"
        if contains_any(name, ["defense", "defensive", "takeaway", "denial"]):
            return "NZ", "NZ defense"
        return "NZ", "Alla NZ"

    # 6. Defensivt
    if contains_any(name, ["entry denial", "denied controlled", "entries against", "controlled entries against", "gap on entries", "entry attempts against"]):
        return "Defensivt", "Entry defense / denial"

    if contains_any(name, ["breakout", "exit", "outlet", "dump out", "carry-out", "pass-out"]):
        return "Defensivt", "Exits / Breakouts"

    # Opposition-shot metrics är defensiva även om ordet "Against" saknas.
    if contains_any(name, [
        "against",
        "xga",
        "goals against",
        "shot attempts against",
        "shots on net against",
        "opposition shot attempts",
        "opposition shots",
        "opposition oz possession",
        "opposition possession",
    ]):
        if contains_any(name, ["slot", "inner slot", "screen"]):
            return "Defensivt", "Slot protection"
        return "Defensivt", "Shots against"

    if contains_any(name, ["defensive", "takeaway", "turnover", "denial", "battle", "hit"]):
        return "Defensivt", "Defensive actions"

    # 7. Offensivt
    if contains_any(name, ["forecheck", "lpr", "loose puck recovery", "oz rebound", "oz shot attempts recovered"]):
        return "Offensivt", "Forecheck / LPR"

    if contains_any(name, ["dump-in", "dump in", "chip", "rim dump", "same-side", "cross-ice"]):
        return "Offensivt", "Dump-in / chip-in / rim"

    if contains_any(name, ["controlled entry", "entries", "entry"]):
        return "Offensivt", "Entries / ingångar"

    if contains_any(name, ["shot", "shots", "goal", "xg", "scoring chance", "slot", "screen", "rebound", "deflect"]):
        if "inner slot" in name:
            return "Offensivt", "Inner slot"
        if "slot" in name:
            return "Offensivt", "Slot shots"
        if "screen" in name:
            return "Offensivt", "Screen / traffic"
        if "rebound" in name or "2nd chance" in name:
            return "Offensivt", "Rebound / second chance"
        return "Offensivt", "Skott / shot"

    if contains_any(name, ["oz pass", "pass to slot", "passes to the slot", "assist", "east-west", "off-the-rush pass"]):
        return "Offensivt", "OZ-passningar"

    # 8. Playmaking
    if contains_any(name, ["pass", "passing", "assist", "reception"]):
        if contains_any(name, ["failed", "misslyck"]):
            return "Playmaking", "Misslyckade passningar"
        if contains_any(name, ["successful", "accurate", "lyckade"]):
            return "Playmaking", "Lyckade passningar"
        return "Playmaking", "Passningar"

    if contains_any(name, ["possession", "corsi", "fenwick", "puck control", "zone time"]):
        if contains_any(name, ["corsi", "fenwick"]):
            return "Playmaking", "Corsi / Fenwick"
        return "Playmaking", "Possession"

    return "Overall", "Alla overall metrics"


def classify_metric(metric: str) -> Tuple[str, str]:
    block, drill = fallback_block(metric)
    return block, drill


def metric_type(metric: str) -> str:
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


def lower_is_better(metric: str) -> bool:
    name = str(metric).lower()
    if any(w in name for w in ["denial", "denied", "blocked", "recovery", "recoveries", "recovered", "takeaway", "save", "saves", "success", "win%", "won"]):
        return False
    return any(w in name for w in ["against", "+against", "gaa", "xga", "failed", "lost", "missed", "giveaway", "turnover", "penalty", "pim"])


def get_numeric_columns(df: pd.DataFrame, entity_col: str) -> List[str]:
    numeric_cols = []
    for col in df.columns:
        if col in {entity_col, "Display Name", "Source File", "Match Label", "Report Format"}:
            continue
        if is_excluded_column(col):
            continue
        if parse_numeric_series(df[col]).notna().sum() > 0:
            numeric_cols.append(col)
    return numeric_cols


def build_metric_browser(numeric_cols: List[str]) -> pd.DataFrame:
    rows = []
    for metric in numeric_cols:
        block, drill = classify_metric(metric)
        rows.append({
            "Metric": metric,
            "Block": block,
            "Drilldown": drill,
            "Metric Type": metric_type(metric),
            "För/Emot": "Emot / lägre bättre" if lower_is_better(metric) else "För / högre bättre",
        })
    return pd.DataFrame(rows)


# Extra säkerhet: skapa tom taxonomy om variabeln saknas.
if "MASTER_TAXONOMY_ROWS" not in globals():
    MASTER_TAXONOMY_ROWS = []

def build_taxonomy_catalog_browser():
    """
    Bygger hela katalogen från inbäddad full taxonomy.
    Detta är grundstrukturen som alltid ska synas även när data saknas.
    """
    rows = []
    seen = set()

    for r in EMBEDDED_TAXONOMY_ROWS:
        metric = r.get("metric")
        if metric is None:
            continue

        metric = normalize_col_name(metric)
        if not metric or is_excluded_column(metric):
            continue

        block = r.get("block", "Overall")
        drill = r.get("drilldown", "Alla overall metrics")
        modes = r.get("modes", ["Lag", "Match", "Spelare"])
        metric_type_value = r.get("metric_type", metric_type(metric))
        direction_value = r.get("direction", "Emot / lägre bättre" if lower_is_better(metric) else "För / högre bättre")

        key = (canonical(metric), block, drill, tuple(modes))
        if not key[0] or key in seen:
            continue
        seen.add(key)

        rows.append({
            "Metric": metric,
            "Block": block,
            "Drilldown": drill,
            "Modes": ", ".join(modes),
            "Metric Type": metric_type_value,
            "För/Emot": direction_value,
            "Matched taxonomy": True,
            "Finns i data": False,
            "Datakolumn": "",
        })

    # Safety net: include every metric found in the raw taxonomy text.
    # If parser failed to place it, it still appears under "Taxonomy / ej mappad".
    existing_keys = {canonical(r["Metric"]) for r in rows if r.get("Metric")}
    for metric in FULL_TAXONOMY_METRICS:
        metric = normalize_col_name(metric)
        key = canonical(metric)
        if not key or key in existing_keys or is_excluded_column(metric):
            continue

        block, drill = fallback_block(metric)
        rows.append({
            "Metric": metric,
            "Block": block if block else "Taxonomy / ej mappad",
            "Drilldown": drill if drill else "Taxonomy / ej mappad",
            "Modes": "Lag, Match, Spelare, Målvakt",
            "Metric Type": metric_type(metric),
            "För/Emot": "Emot / lägre bättre" if lower_is_better(metric) else "För / högre bättre",
            "Matched taxonomy": True,
            "Finns i data": False,
            "Datakolumn": "",
        })
        existing_keys.add(key)

    return pd.DataFrame(rows)




def derive_subdetail(block: str, drill: str, metric: str):
    """
    Generell tredje nivå:
    Block -> Underblock -> Underkategori -> Metrics
    """
    name = str(metric).lower()

    # DEFENSE / EXITS
    if block == "Defensivt" and drill == "Exits / Breakouts":
        if any(x in name for x in ["carry-out", "carry out", "carry-outs", "carry outs", "stickhandling"]):
            return "Carry out"

        if any(x in name for x in [
            "dump out", "dump-out", "dump outs",
            "dump-in recovery", "dump in recovery",
            "defensive dump-in", "dz dump-in", "rim dump-in",
            "same-side dump-in", "soft dump-in", "cross-ice dump-in",
            "dump-in recoveries", "dump-in attempts against", "dump-in rate against"
        ]):
            return "Dump out / dump-in recovery"

        if any(x in name for x in ["pass-out", "pass out", "pass-outs", "pass outs", "breakouts via pass"]):
            return "Pass out"

        if any(x in name for x in ["outlet", "stretch pass", "stretch passing", "stretch pass attempts"]):
            return "Outlet"

        return "Total / overall"

    # DEFENSE / SHOTS AGAINST
    if block == "Defensivt" and drill in ["Shots against", "Slot protection"]:
        if any(x in name for x in ["inner slot", "slot"]):
            return "Slot shots against"
        if "screen" in name:
            return "Screened shots against"
        if "rush" in name:
            return "Rush chances against"
        if "rebound" in name:
            return "Rebounds against"
        return "Overall shots against"

    # OFFENSE / SHOTS
    if block == "Offensivt" and drill == "Skott / shot":
        if any(x in name for x in ["1 timer", "one timer"]):
            return "1-timers"
        if "rebound" in name:
            return "Rebounds"
        if "screen" in name:
            return "Screened shots"
        if any(x in name for x in ["inner slot", "slot"]):
            return "Slot shots"
        if "rush" in name:
            return "Rush offense"
        return "Overall shots"

    # OFFENSE / ENTRIES
    if block == "Offensivt" and drill == "Entries / ingångar":
        if "carry" in name:
            return "Carry entries"
        if any(x in name for x in ["dump", "chip", "rim"]):
            return "Dump / chip entries"
        if "cross-ice" in name:
            return "Cross-ice entries"
        return "Overall entries"

    # PLAYMAKING
    if block == "Playmaking":
        if "outlet" in name:
            return "Outlet passing"
        if any(x in name for x in ["cross-ice", "royal road"]):
            return "Cross-ice passing"
        if any(x in name for x in ["failed", "turnover", "misslyck"]):
            return "Failed passing"
        if any(x in name for x in ["successful", "completed", "success rate", "lyckade"]):
            return "Successful passing"
        return "Overall passing"

    # SPECIALTEAM
    if block == "Specialteam":
        if any(x in name for x in ["pp", "powerplay", "power play"]):
            return "Powerplay"
        if any(x in name for x in ["pk", "sh", "penalty kill", "short-handed"]):
            return "Penalty kill"
        return "Overall specialteam"

    # WOI
    if block == "WOI":
        if "xg" in name:
            return "WOI xG"
        if "shot" in name:
            return "WOI shots"
        if "goal" in name:
            return "WOI goals"
        return "Overall WOI"

    # GOALIE
    if block == "Målvakt":
        if "rebound" in name:
            return "Rebound control"
        if "screen" in name or "traffic" in name or "trafic" in name:
            return "Traffic / screens"
        if any(x in name for x in ["save", "gaa", "svs"]):
            return "Shot stopping"
        return "Overall goalie"

    return "Overall"


def add_detail_groups(browser_df):
    """
    Lägger på en extra detaljnivå. Används främst för:
    Defensivt → Exits / Breakouts → utgångstyp.
    """
    if browser_df.empty:
        return browser_df

    browser_df = browser_df.copy()

    if "Detail" not in browser_df.columns:
        browser_df["Detail"] = "Alla"

    for idx, row in browser_df.iterrows():
        block = str(row.get("Block", ""))
        drill = str(row.get("Drilldown", ""))
        metric = str(row.get("Metric", ""))

        # Normalize old exit drilldowns into one parent drilldown
        if block == "Defensivt" and drill in [
            "Carry out",
            "Dump out / dump-in recovery exit",
            "Pass out",
            "Outlet",
        ]:
            browser_df.at[idx, "Drilldown"] = "Exits / Breakouts"
            drill = "Exits / Breakouts"

        browser_df.at[idx, "Detail"] = derive_subdetail(block, drill, metric)

    return browser_df


def combine_taxonomy_and_data_browsers(taxonomy_df, data_df):
    """
    Slår ihop taxonomy-katalogen med uppladdade metrics.
    - Taxonomy styr vad som alltid visas.
    - Data markerar vad som faktiskt finns som kolumn.
    - Data-metrics som inte finns i taxonomy läggs också till.
    """
    if taxonomy_df.empty and data_df.empty:
        return pd.DataFrame(columns=[
            "Metric", "Block", "Drilldown", "Modes", "Metric Type",
            "För/Emot", "Matched taxonomy", "Finns i data", "Datakolumn"
        ])

    taxonomy_df = taxonomy_df.copy()
    data_df = data_df.copy()

    data_by_key = {}
    for _, row in data_df.iterrows():
        metric = row.get("Metric")
        if metric is None:
            continue
        key = canonical(metric)
        if key:
            data_by_key[key] = row

    combined_rows = []

    # First include all taxonomy metrics.
    for _, trow in taxonomy_df.iterrows():
        metric = trow["Metric"]
        key = canonical(metric)
        out = trow.to_dict()

        if key in data_by_key:
            drow = data_by_key[key]
            out["Finns i data"] = True
            out["Datakolumn"] = drow["Metric"]
            # Keep taxonomy Block/Drilldown, but data confirms availability.
        else:
            # Try relaxed alias match.
            found = None
            for dkey, drow in data_by_key.items():
                if key and len(key) > 5 and (key in dkey or dkey in key):
                    found = drow
                    break
            if found is not None:
                out["Finns i data"] = True
                out["Datakolumn"] = found["Metric"]
            else:
                out["Finns i data"] = False
                out["Datakolumn"] = ""

        combined_rows.append(out)

    # Then add uploaded data metrics that were not represented in taxonomy.
    taxonomy_keys = {canonical(m) for m in taxonomy_df["Metric"].dropna().astype(str).tolist()}
    represented_data_cols = {r.get("Datakolumn") for r in combined_rows if r.get("Datakolumn")}

    for _, drow in data_df.iterrows():
        metric = drow.get("Metric")
        if metric is None:
            continue

        key = canonical(metric)

        if key in taxonomy_keys or metric in represented_data_cols:
            continue

        out = drow.to_dict()
        out["Finns i data"] = True
        out["Datakolumn"] = metric
        combined_rows.append(out)

    combined = pd.DataFrame(combined_rows)

    if combined.empty:
        return combined

    # Remove duplicates but prefer rows where Finns i data=True.
    combined["_sort_exists"] = combined["Finns i data"].astype(int)
    combined = combined.sort_values(["Metric", "_sort_exists"], ascending=[True, False])
    combined = combined.drop_duplicates(subset=["Metric"], keep="first")
    combined = combined.drop(columns=["_sort_exists"], errors="ignore")

    return combined


def get_data_column_for_metric(metric, browser_df):
    """
    Returnerar datakolumnen för vald metric. Om metricen inte finns i data returneras None.
    """
    if browser_df.empty:
        return None

    rows = browser_df[browser_df["Metric"] == metric]
    if rows.empty:
        return None

    datacol = rows.iloc[0].get("Datakolumn", "")
    exists = bool(rows.iloc[0].get("Finns i data", False))

    if exists and datacol:
        return datacol

    # Fallback: metric name may be the actual column.
    if exists:
        return metric

    return None


# ==================================================
# CALC HELPERS
# ==================================================
def find_toi_column(df: pd.DataFrame):
    return find_first_existing(df, ["TOI (sec)", "TOI(sec)", "TOI_sec", "TOI Sec", "TOI", "Time on ice", "Total TOI (sec)", "Total TOI/GP (sec)", "TOI (min)", "Total TOI/GP (min)"])


def toi_to_seconds(series: pd.Series) -> pd.Series:
    if getattr(series, "dtype", None) is not None and series.dtype.kind in "biufc":
        values = pd.to_numeric(series, errors="coerce")
        if values.max(skipna=True) is not None and values.max(skipna=True) < 300:
            return values * 60
        return values
    out = []
    for value in series.astype(str):
        value = value.strip()
        if ":" in value:
            parts = value.split(":")
            try:
                parts = [float(p) for p in parts]
                if len(parts) == 2:
                    out.append(parts[0] * 60 + parts[1])
                elif len(parts) == 3:
                    out.append(parts[0] * 3600 + parts[1] * 60 + parts[2])
                else:
                    out.append(math.nan)
            except Exception:
                out.append(math.nan)
        else:
            try:
                num = float(value.replace(",", "."))
                out.append(num * 60 if num < 300 else num)
            except Exception:
                out.append(math.nan)
    return pd.Series(out, index=series.index)


def create_rate_metrics(df: pd.DataFrame, entity_col: str) -> pd.DataFrame:
    df = df.copy()
    toi_col = find_toi_column(df)
    if toi_col is None:
        return df
    toi_sec = toi_to_seconds(df[toi_col])
    skip_terms = ["%", "/60", "rate", "toi", "time on ice", "games", "game", "position", "team", "player", "source", "match", "age", "height", "career", "jersey", "id"]
    for col in list(df.columns):
        if col == entity_col:
            continue
        lower = col.lower()
        if any(term in lower for term in skip_terms):
            continue
        values = parse_numeric_series(df[col])
        if values.notna().sum() == 0:
            continue
        new_col = f"{col} /60"
        if new_col not in df.columns:
            df[new_col] = (values / toi_sec) * 3600
    return df


def normalize_series(series: pd.Series, inverse=False, method="Soft") -> pd.Series:
    numeric = parse_numeric_series(series)
    if numeric.notna().sum() == 0:
        return pd.Series([0] * len(numeric), index=numeric.index)
    if method == "Percentil":
        return (numeric.rank(pct=True, ascending=inverse) * 100).fillna(0).clip(0, 100)
    min_val, max_val = numeric.min(), numeric.max()
    if min_val == max_val:
        return pd.Series([50] * len(numeric), index=numeric.index)
    if method == "Min/Max":
        out = ((max_val - numeric) / (max_val - min_val)) * 100 if inverse else ((numeric - min_val) / (max_val - min_val)) * 100
        return out.fillna(0).clip(0, 100)
    mid = (min_val + max_val) / 2
    spread = max_val - min_val or 1
    out = 50 + ((mid - numeric) / spread) * 50 if inverse else 50 + ((numeric - mid) / spread) * 50
    return out.fillna(0).clip(0, 100)


def build_display_name(df: pd.DataFrame, entity_col: str, team_col=None, match_col=None, mode="Entity | Match") -> pd.Series:
    entity = df[entity_col].astype(str)
    if mode == "Entity only":
        return entity
    if mode == "Entity | Team" and team_col:
        return entity + " | " + df[team_col].astype(str)
    if mode == "Entity | Match" and match_col:
        return entity + " | " + df[match_col].astype(str)
    if mode == "Entity | Team | Match" and team_col and match_col:
        return entity + " | " + df[team_col].astype(str) + " | " + df[match_col].astype(str)
    return entity


def aggregate_for_compare(df: pd.DataFrame, display_col: str, selected_metrics: List[str]) -> pd.DataFrame:
    agg = {}
    for metric in selected_metrics:
        if metric in df.columns:
            agg[metric] = lambda s: parse_numeric_series(s).mean()
    if not agg:
        return df[[display_col]].drop_duplicates()
    return df.groupby([display_col], dropna=False).agg(agg).reset_index()

# ==================================================
# SIDEBAR: DATA
# ==================================================
st.sidebar.header("1. Data")
uploaded_files = st.sidebar.file_uploader("Ladda upp CSV/Excel-filer", type=["csv", "xlsx"], accept_multiple_files=True)

frames = []
if uploaded_files:
    for file in uploaded_files:
        try:
            raw = read_uploaded_file(file)
            temp = prepare_uploaded_dataframe(raw, file.name)
            frames.append(temp)
        except Exception as e:
            st.sidebar.error(f"Kunde inte läsa {file.name}: {e}")

if frames:
    df = pd.concat(frames, ignore_index=True, sort=False)
else:
    df = sample_data.copy()
    df["Source File"] = "Demo"
    df["Match Label"] = "Demo Match"
    df["Report Format"] = "Demo"

df = clean_dataframe(df)

# ==================================================
# ANALYSIS MODE
# ==================================================
st.sidebar.header("2. Analys")
scores = score_report_types(df)
suggested = suggested_analysis_mode(df)

with st.sidebar.expander("Automatisk rapporttolkning", expanded=False):
    st.write(f"Föreslagen rapporttyp: **{suggested}**")
    st.write(scores)

analysis_mode = st.sidebar.radio("Analysläge", ANALYSIS_MODES, index=ANALYSIS_MODES.index(suggested) if suggested in ANALYSIS_MODES else 0)

auto_entity = auto_entity_column(df, analysis_mode)
with st.sidebar.expander("Avancerat: jämförelsekolumn", expanded=False):
    txt_cols = text_like_columns(df)
    entity_options = txt_cols if txt_cols else list(df.columns)
    if auto_entity not in entity_options and entity_options:
        auto_entity = entity_options[0]
    entity_col = st.selectbox("Jämför på", options=entity_options, index=entity_options.index(auto_entity) if auto_entity in entity_options else 0)

st.sidebar.caption(f"Jämför på: **{entity_col}**")
if analysis_mode == "Lag":
    st.sidebar.caption("Lag = jämför lag över vald data. Flera matcher/filer kan ingå.")
elif analysis_mode == "Match":
    st.sidebar.caption("Match = jämför matcher/källor. Använd filter för att välja lag i matcherna.")

team_col = find_first_existing(df, ["Team", "Lag", "team"])
if team_col not in df.columns:
    team_col = None
match_col = "Match Label" if "Match Label" in df.columns else ("Source File" if "Source File" in df.columns else None)

# ==================================================
# FILTERS
# ==================================================
st.sidebar.header("3. Filter")

if team_col:
    teams = sorted(df[team_col].dropna().astype(str).unique().tolist())
    selected_teams = st.sidebar.multiselect("Filtrera lag", options=teams, default=teams)
    df = df[df[team_col].astype(str).isin(selected_teams)]

if match_col:
    matches = sorted(df[match_col].dropna().astype(str).unique().tolist())
    selected_matches = st.sidebar.multiselect("Filtrera matcher/källor (uppladdade filer)", options=matches, default=matches)
    df = df[df[match_col].astype(str).isin(selected_matches)]

# ==================================================
# PREPARE DATA
# ==================================================
df[entity_col] = df[entity_col].astype(str).str.strip()

if analysis_mode == "Match":
    label_mode = "Entity only"
elif analysis_mode == "Lag":
    label_mode = "Entity | Match" if match_col else "Entity only"
else:
    label_mode = "Entity | Team | Match" if team_col and match_col else "Entity only"

df["Display Name"] = build_display_name(df, entity_col=entity_col, team_col=team_col, match_col=match_col, mode=label_mode)

df = create_rate_metrics(df, entity_col)
numeric_cols = get_numeric_columns(df, entity_col)

if not numeric_cols:
    st.error("Hittar inga numeriska parametrar i vald data.")
    st.stop()

data_browser_df = build_metric_browser(numeric_cols)
taxonomy_browser_df = build_taxonomy_catalog_browser()

# Om taxonomy är tom används data-browsern som fallback.
if taxonomy_browser_df.empty:
    browser_df = data_browser_df.copy()
    browser_df["Finns i data"] = True
    browser_df["Datakolumn"] = browser_df["Metric"]
else:
    browser_df = combine_taxonomy_and_data_browsers(taxonomy_browser_df, data_browser_df)

# Behåll hela taxonomy i browser_df. Analysblocken styr vad som visas.
# Detta gör att metrics aldrig försvinner bara för att parsern satte fel mode.
browser_df = add_detail_groups(browser_df)

mode_blocks = BLOCKS_BY_MODE[analysis_mode]
# Add rescue blocks.
if "Alla hittade metrics" not in mode_blocks:
    mode_blocks = mode_blocks + ["Alla hittade metrics"]
if "Saknade metrics" not in mode_blocks:
    mode_blocks = mode_blocks + ["Saknade metrics"]
if "Alla taxonomy metrics" not in mode_blocks:
    mode_blocks = mode_blocks + ["Alla taxonomy metrics"]

# ==================================================
# PRESET METRIC SELECTION
# ==================================================
st.sidebar.header("4. Välj analysblock")
normalization_method = st.sidebar.selectbox("Normalisering", ["Soft", "Min/Max", "Percentil"], index=0)

selected_block = st.sidebar.radio("Analysblock", options=mode_blocks, index=0)

if selected_block == "Alla hittade metrics":
    block_df = browser_df[browser_df["Finns i data"] == True].copy()
elif selected_block == "Saknade metrics":
    block_df = browser_df[browser_df["Finns i data"] == False].copy()
elif selected_block == "Alla taxonomy metrics":
    block_df = browser_df.copy()
elif selected_block == "Overall":
    overall_found = find_overall_preset_metrics(browser_df["Metric"].tolist(), analysis_mode)
    block_df = browser_df[browser_df["Metric"].isin(overall_found)].copy()
    if not block_df.empty:
        block_df["Drilldown"] = "Overall preset"
else:
    block_df = browser_df[browser_df["Block"] == selected_block].copy()

if block_df.empty:
    st.sidebar.warning("Inga metrics hittades i detta block för uppladdad fil.")
    with st.sidebar.expander("Block som finns i filen", expanded=False):
        st.write(sorted(browser_df["Block"].dropna().unique().tolist()))
    st.stop()

real_drills = sorted(block_df["Drilldown"].dropna().unique().tolist())

if selected_block == "Overall":
    preset_drills = ["Overall preset"]
elif selected_block == "Alla hittade metrics":
    preset_drills = ["Alla hittade metrics"]
elif selected_block == "Saknade metrics":
    preset_drills = ["Saknade metrics"]
elif selected_block == "Alla taxonomy metrics":
    preset_drills = ["Alla taxonomy metrics"]
else:
    preset_drills = DRILLDOWN_BY_BLOCK.get(selected_block, ["Alla"])

if selected_block == "Specialteam":
    drill_options = ["Båda (PP + PK/SH)", "Powerplay (PP)", "Penalty kill / SH"]
elif selected_block == "Alla taxonomy metrics":
    drill_options = ["Alla taxonomy metrics"]
else:
    drill_options = [
        d for d in preset_drills
        if d.startswith("Alla") or d in real_drills or d == "Overall preset"
    ]
    drill_options += [d for d in real_drills if d not in drill_options]

selected_drill = st.sidebar.selectbox("Underblock", options=drill_options, index=0)

if selected_drill.startswith("Alla") or selected_drill == "Overall preset" or selected_drill == "Båda (PP + PK/SH)" or selected_drill == "Saknade metrics" or selected_drill == "Alla taxonomy metrics":
    drill_df = block_df.copy()
elif selected_drill == "Powerplay (PP)":
    drill_df = block_df[block_df["Drilldown"].astype(str).str.contains("Powerplay|PP", case=False, na=False)].copy()
elif selected_drill == "Penalty kill / SH":
    drill_df = block_df[block_df["Drilldown"].astype(str).str.contains("Penalty kill|PK|SH", case=False, na=False)].copy()
else:
    drill_df = block_df[block_df["Drilldown"] == selected_drill].copy()

# Extra tredje nivå: underkategori
selected_detail = "Alla"

if "Detail" in drill_df.columns:
    detail_available = sorted(
        [d for d in drill_df["Detail"].dropna().astype(str).unique().tolist() if d and d != "Alla"]
    )

    if detail_available:
        detail_options = ["Alla"] + detail_available

        selected_detail = st.sidebar.selectbox(
            "Underkategori",
            options=detail_options,
            index=0
        )

        if selected_detail != "Alla":
            drill_df = drill_df[drill_df["Detail"] == selected_detail].copy()

search_query = st.sidebar.text_input("Sök inom valt block", placeholder="Ex: slot, pass, exit...").strip().lower()
if search_query:
    drill_df = drill_df[drill_df["Metric"].astype(str).str.lower().str.contains(search_query, na=False)]

if drill_df.empty:
    st.sidebar.warning("Inga metrics matchar detta val.")
    st.stop()

# Visa metrics som checkbox-lista istället för kapade multiselect-tags.
metrics = drill_df["Metric"].dropna().unique().tolist()
available_metrics = drill_df[drill_df["Finns i data"] == True]["Metric"].dropna().unique().tolist()
missing_count = int((drill_df["Finns i data"] == False).sum()) if "Finns i data" in drill_df.columns else 0

if missing_count > 0:
    st.sidebar.caption(f"{missing_count} metrics i detta block saknas i uppladdad data men visas från taxonomy.")

select_mode = st.sidebar.radio(
    "Metric-urval",
    ["Rekommenderade", "Alla som finns i data", "Alla från taxonomy", "Manuellt"],
    horizontal=False
)

if select_mode == "Alla som finns i data":
    default_metrics = available_metrics
elif select_mode == "Alla från taxonomy":
    default_metrics = metrics
elif select_mode == "Rekommenderade":
    if selected_block == "Overall":
        default_metrics = available_metrics
    else:
        default_metrics = available_metrics[:min(12, len(available_metrics))]
else:
    default_metrics = []

default_set = set(default_metrics)

metric_search = st.sidebar.text_input(
    "Sök i metric-listan",
    placeholder="Ex: entry, slot, dump..."
).strip().lower()

visible_metric_rows = drill_df.copy()

if metric_search:
    visible_metric_rows = visible_metric_rows[
        visible_metric_rows["Metric"].astype(str).str.lower().str.contains(metric_search, na=False)
    ]

visible_metrics = visible_metric_rows["Metric"].dropna().unique().tolist()

selected_metrics = []

st.sidebar.markdown("**Metrics**")

with st.sidebar.container():
    if not visible_metrics:
        st.sidebar.caption("Inga metrics matchar sökningen.")
    else:
        for metric in visible_metrics:
            row_meta = drill_df[drill_df["Metric"] == metric]
            exists = False
            metric_type_label = ""
            direction_label = ""

            if not row_meta.empty:
                exists = bool(row_meta.iloc[0].get("Finns i data", False))
                metric_type_label = str(row_meta.iloc[0].get("Metric Type", ""))
                direction_label = str(row_meta.iloc[0].get("För/Emot", ""))

            prefix = "✅" if exists else "⚪"
            label = f"{prefix} {metric}"

            checked = st.checkbox(
                label,
                value=metric in default_set,
                key=f"metric_checkbox_{canonical(metric)}_{selected_block}_{selected_drill}_{selected_detail}"
            )

            if checked:
                selected_metrics.append(metric)

            if metric_type_label or direction_label:
                st.caption(f"{metric_type_label} | {direction_label}")

if not selected_metrics:
    st.warning("Välj minst en metric.")
    st.stop()

missing_selected = [m for m in selected_metrics if get_data_column_for_metric(m, browser_df) is None]
if missing_selected:
    st.sidebar.warning(f"{len(missing_selected)} valda metrics saknas i uppladdad data och kommer inte kunna ritas.")

with st.sidebar.expander("För / Emot-logik", expanded=False):
    metric_direction = {}
    for metric in selected_metrics:
        inverse = lower_is_better(metric)
        direction = st.radio(metric, ["För / högre är bättre", "Emot / lägre är bättre"], index=1 if inverse else 0, horizontal=True, key=f"direction_{metric}")
        metric_direction[metric] = direction.startswith("Emot")

# ==================================================
# DISPLAY SELECTION
# ==================================================
st.sidebar.header("5. Välj vilka som visas")
# Mappa valda taxonomy-metrics till faktiska datakolumner.
selected_metric_to_data_col = {
    metric: get_data_column_for_metric(metric, browser_df)
    for metric in selected_metrics
}
selected_available_metrics = [
    metric for metric, datacol in selected_metric_to_data_col.items()
    if datacol is not None and datacol in df.columns
]

# Skapa en temporär dataframe där valda taxonomy-namn pekar på rätt datakolumn.
df_for_compare = df.copy()
for metric, datacol in selected_metric_to_data_col.items():
    if datacol is not None and datacol in df_for_compare.columns and metric not in df_for_compare.columns:
        df_for_compare[metric] = df_for_compare[datacol]

if not selected_available_metrics:
    st.warning("De valda metrics finns inte i uppladdad data. De visas i taxonomy, men kan inte ritas förrän rätt datafil laddas upp.")
    st.stop()

compare_df = aggregate_for_compare(df_for_compare, "Display Name", selected_available_metrics)
entity_list = compare_df["Display Name"].dropna().astype(str).unique().tolist()
selected_entities = st.sidebar.multiselect("Lag/spelare/matcher", options=entity_list, default=entity_list[:min(5, len(entity_list))])
compare_df = compare_df[compare_df["Display Name"].astype(str).isin(selected_entities)]

index_df = compare_df[["Display Name"]].copy()
for metric in selected_available_metrics:
    if metric in compare_df.columns:
        index_df[metric] = normalize_series(compare_df[metric], inverse=metric_direction.get(metric, False), method=normalization_method)

# Från denna punkt används bara de metrics som faktiskt finns i index_df.
selected_metrics_for_chart = [
    metric for metric in selected_available_metrics
    if metric in index_df.columns
]

if not selected_metrics_for_chart:
    st.warning("Inga av de valda metrics kunde matchas mot uppladdad data. De syns i taxonomy men saknar värden i filen.")
    st.stop()

# ==================================================
# MAIN TABS
# ==================================================
tab_spider, tab_profile, tab_browser, tab_data = st.tabs(["📊 Spiderchart", "🧾 Profilkort", "🔎 Metric Browser", "📘 Data"])

with tab_spider:
    st.subheader("📊 Spiderchart")
    st.caption(f"Analysläge: {analysis_mode} | Block: {selected_block} | Underblock: {selected_drill}")
    fig = go.Figure()
    for _, row in index_df.iterrows():
        values = []
        for metric in selected_metrics_for_chart:
            try:
                values.append(safe_row_value(row, metric, 0))
            except Exception:
                values.append(0)
        values = [max(0, min(100, v)) for v in values]
        if len(values) == 1:
            r_values = values + values
            theta = selected_metrics_for_chart + selected_metrics_for_chart
        else:
            r_values = values + [values[0]]
            theta = selected_metrics_for_chart + [selected_metrics_for_chart[0]]
        fig.add_trace(go.Scatterpolar(r=r_values, theta=theta, fill="toself", name=str(row["Display Name"])))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100], tickvals=[0, 20, 40, 60, 80, 100])), height=800, showlegend=True)
    st.plotly_chart(fig, use_container_width=True)

with tab_profile:
    st.subheader("🧾 Profilkort")
    if index_df.empty:
        st.warning("Välj minst en rad.")
    else:
        for _, row in index_df.iterrows():
            st.markdown(f"### {row['Display Name']}")
            cols = st.columns(min(4, max(1, len(selected_metrics_for_chart))))
            for i, metric in enumerate(selected_metrics):
                value = safe_row_value(row, metric, 0)
                meta = browser_df[browser_df["Metric"] == metric]
                caption = ""
                if not meta.empty:
                    caption = f"{meta.iloc[0]['Block']} → {meta.iloc[0]['Drilldown']}"
                with cols[i % len(cols)]:
                    st.metric(metric, f"{value:.1f}")
                    st.progress(int(max(0, min(100, value))))
                    st.caption(caption)
            st.divider()

with tab_browser:
    st.subheader("🔎 Metric Browser")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Metrics i data", len(numeric_cols))
    c2.metric("Block", browser_df["Block"].nunique())
    c3.metric("Valda metrics", len(selected_metrics_for_chart))
    c4.metric("Analysläge", analysis_mode)

    browser_search = st.text_input("Sök i Metric Browser", value=search_query, placeholder="Ex: breakout, slot, goalie...").strip().lower()
    display_browser = browser_df.copy()
    if browser_search:
        display_browser = display_browser[
            display_browser["Metric"].astype(str).str.lower().str.contains(browser_search, na=False)
            | display_browser["Block"].astype(str).str.lower().str.contains(browser_search, na=False)
            | display_browser["Drilldown"].astype(str).str.lower().str.contains(browser_search, na=False)
        ]

    st.dataframe(display_browser.sort_values(["Block", "Drilldown", "Detail", "Metric"]), use_container_width=True)

    st.markdown("### Preset-träd")
    for block in [b for b in BLOCKS_BY_MODE[analysis_mode] if b in display_browser["Block"].unique().tolist()]:
        with st.expander(block, expanded=False):
            bdf = display_browser[display_browser["Block"] == block]
            for drill in sorted(bdf["Drilldown"].dropna().unique().tolist()):
                st.markdown(f"#### {drill}")
                ddf = bdf[bdf["Drilldown"] == drill].sort_values("Metric")
                for _, r in ddf.iterrows():
                    st.write(f"- {r['Metric']} — {r['Metric Type']} — {r['För/Emot']}")

with tab_data:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📘 Rådata")
        st.dataframe(df, use_container_width=True)
    with col2:
        st.subheader("📈 Indexdata 0–100")
        st.dataframe(index_df, use_container_width=True)
    st.subheader("Jämförelsedata")
    st.dataframe(compare_df, use_container_width=True)
    st.subheader("Rapporttolkning")
    st.write("Föreslagen rapporttyp:", suggested)
    st.write("Scores:", score_report_types(df))
    st.write("Jämförelsekolumn:", entity_col)
    if "Report Format" in df.columns:
        st.write("Rapportformat:", df["Report Format"].dropna().astype(str).unique().tolist())
    st.subheader("Alla kolumner")
    st.write(list(df.columns))
