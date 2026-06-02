
from pathlib import Path
from io import BytesIO
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ==================================================
# BASIC HELPERS
# ==================================================

def normalize_text(value):
    return str(value).strip()


def normalize_column_name(value):
    return re.sub(r"\s+", " ", str(value).strip().replace('"', ""))


def parse_aliases(value):
    if pd.isna(value) or str(value).strip() == "":
        return []
    raw = str(value)
    parts = []
    for chunk in raw.replace("|", ";").split(";"):
        chunk = chunk.strip()
        if chunk:
            parts.append(chunk)
    return parts


def parse_modes(value):
    if pd.isna(value) or str(value).strip() == "":
        return []
    return [x.strip() for x in str(value).replace(",", "|").split("|") if x.strip()]


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



def make_widget_key(*parts):
    """
    Create unique Streamlit widget keys.
    Avoids duplicate keys when taxonomy contains duplicated MetricID/Metric names.
    """
    raw = "__".join([str(p) for p in parts if p is not None])
    raw = re.sub(r"[^A-Za-z0-9_åäöÅÄÖ]+", "_", raw)
    return raw[:240]


def safe_float(value, default=0):
    try:
        if pd.notna(value):
            return float(value)
    except Exception:
        pass
    return default


def lower_is_better(direction):
    return "lägre" in str(direction).lower() or "emot" in str(direction).lower()


def infer_match_from_filename(name):
    return re.sub(r"\.(csv|xlsx)$", "", str(name), flags=re.IGNORECASE).replace("_", " ").strip()


def infer_match_date_from_filename(name):
    """
    Läser datum från filnamn som:
    Sun_Mar_01_2026_Post-Game_Report_All_Periods.csv
    Wed_Mar_04_2026_Post-Game_Report_All_Periods.csv
    Fri_Mar_06_2026_Post-Game_Report_All_Periods.csv

    Returnerar pandas Timestamp eller NaT.
    """
    text = str(name)

    month_map = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }

    # Pattern: Sun_Mar_01_2026 or Mar_01_2026
    m = re.search(
        r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?_?([A-Za-z]{3,9})[_\- ](\d{1,2})[_\- ](\d{4})",
        text,
        flags=re.IGNORECASE,
    )

    if m:
        month_raw = m.group(1).lower()
        day = int(m.group(2))
        year = int(m.group(3))
        month = month_map.get(month_raw)

        if month:
            return pd.Timestamp(year=year, month=month, day=day)

    # Pattern fallback: 2026-03-04, 2026_03_04
    m = re.search(r"(\d{4})[_\- ](\d{1,2})[_\- ](\d{1,2})", text)

    if m:
        return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=int(m.group(3)))

    return pd.NaT


def format_match_label_with_date(match_label, match_date):
    if pd.isna(match_date):
        return str(match_label)

    return f"{pd.to_datetime(match_date).strftime('%Y-%m-%d')} | {match_label}"


def find_first_existing(df, options):
    for option in options:
        if option in df.columns:
            return option
    return None


def text_like_columns(df):
    out = []
    for col in df.columns:
        numeric_ratio = parse_numeric_series(df[col]).notna().mean()
        if numeric_ratio < 0.5:
            out.append(col)
    return out


# ==================================================
# LOADERS
# ==================================================

@st.cache_data(show_spinner=False)
def load_taxonomy_master():
    path = Path(__file__).parent / "data" / "taxonomy_editor.xlsx"

    if not path.exists():
        return pd.DataFrame()

    df = pd.read_excel(path, sheet_name="Taxonomy_Master")
    df.columns = [normalize_column_name(c) for c in df.columns]

    # Flexible schema mapping for updated taxonomy naming.
    column_aliases = {
        "MetricID": ["MetricID", "Metric ID", "ID"],
        "Active": ["Active", "Aktiv"],
        "Analysläge": ["Analysläge", "AnalysisMode", "Analysis Mode", "Mode"],
        "Analysblock": ["Analysblock", "AnalysisBlock", "Analysis Block", "Block"],
        "Underblock": ["Underblock", "SubBlock", "Sub Block"],
        "Underkategori": ["Underkategori", "SubCategory", "Sub Category"],
        "Metric": ["Metric", "Parameter", "Metric Label"],
        "DataColumnExact": ["DataColumnExact", "Data Column Exact", "Datakolumn", "Datakolumn exakt"],
        "Aliases": ["Aliases", "Alias", "Alternativa namn"],
        "MetricTyp": ["MetricTyp", "Metric Type", "Value", "Typ", "Värdetyp"],
        "FörEmot": ["FörEmot", "För/Emot", "ForEmot", "Direction", "Riktning"],
        "Normalisering": ["Normalisering", "Normalization"],
        "DefaultIChart": ["DefaultIChart", "Default", "Default i chart"],
        "Matchningsregel": ["Matchningsregel", "Matching Rule", "Matchning"],
        "Kommentar": ["Kommentar", "Comment"],
        "Status": ["Status"],
    }

    for target, aliases in column_aliases.items():
        if target not in df.columns:
            matched = next((a for a in aliases if a in df.columns), None)
            df[target] = df[matched] if matched else ""

    df = df[df["Active"].astype(str).str.lower().isin(["yes", "ja", "true", "1"])]
    df["Metric"] = df["Metric"].astype(str).map(normalize_column_name)
    df["DataColumnExact"] = df["DataColumnExact"].fillna("").astype(str).map(normalize_column_name)
    df["Aliases"] = df["Aliases"].fillna("").astype(str)
    df["Analysläge"] = df["Analysläge"].fillna("").astype(str)
    df["Analysblock"] = df["Analysblock"].fillna("Overall").astype(str)
    df["Underblock"] = df["Underblock"].fillna("Overall").astype(str)
    df["Underkategori"] = df["Underkategori"].fillna("Overall").astype(str)
    df["FörEmot"] = df["FörEmot"].fillna("För / högre bättre").astype(str)
    df["MetricTyp"] = df["MetricTyp"].fillna("Value").astype(str)
    df["DefaultIChart"] = df["DefaultIChart"].fillna("No").astype(str)
    df["Matchningsregel"] = df["Matchningsregel"].fillna("ExactOnly").astype(str)

    return df


@st.cache_data(show_spinner=False)
def read_uploaded_file_cached(name, content):
    bio = BytesIO(content)

    if name.lower().endswith(".xlsx"):
        return read_xlsx_smart(name, content)

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



# ==================================================
# GLOBAL UPLOAD STATE
# ==================================================

def store_uploaded_files(uploaded_files):
    """
    Stores uploaded files globally across Streamlit pages.
    Without this, each multipage page has its own uploader state and files disappear
    when switching between Lag/Match/Spelare/Målvakt.
    """
    if "global_uploaded_files" not in st.session_state:
        st.session_state["global_uploaded_files"] = []

    if not uploaded_files:
        return

    existing_keys = {
        (item["name"], item["size"])
        for item in st.session_state["global_uploaded_files"]
    }

    for file in uploaded_files:
        content = file.getvalue()
        key = (file.name, len(content))

        if key not in existing_keys:
            st.session_state["global_uploaded_files"].append(
                {
                    "name": file.name,
                    "content": content,
                    "size": len(content),
                }
            )
            existing_keys.add(key)


def get_stored_uploaded_files():
    return st.session_state.get("global_uploaded_files", [])


def clear_stored_uploaded_files():
    st.session_state["global_uploaded_files"] = []



# ==================================================
# EXACT MATCHING ENGINE
# ==================================================

def build_column_lookup(data_columns):
    """
    Case/space-normalized lookup, but still exact by full column name.
    This prevents xGA from matching Breakout%, because only full names are compared.
    """
    lookup = {}
    for col in data_columns:
        exact = normalize_column_name(col)
        lookup[exact] = col
        lookup[exact.lower()] = col
    return lookup


def match_metric_to_data_column(row, data_columns):
    """
    Deterministic matching only.

    Allowed:
    1. DataColumnExact full-name match
    2. Alias full-name match

    Not allowed:
    - fuzzy matching
    - contains matching
    - token matching
    - regex guessing
    """
    lookup = build_column_lookup(data_columns)

    candidates = []

    exact = normalize_column_name(row.get("DataColumnExact", ""))
    if exact:
        candidates.append(("DataColumnExact", exact))

    for alias in parse_aliases(row.get("Aliases", "")):
        candidates.append(("Alias", normalize_column_name(alias)))

    for match_type, candidate in candidates:
        if candidate in lookup:
            return lookup[candidate], match_type
        if candidate.lower() in lookup:
            return lookup[candidate.lower()], match_type

    return None, "Missing"


def build_metric_catalog_for_mode(taxonomy_df, analysis_mode, data_columns):
    rows = []

    for _, row in taxonomy_df.iterrows():
        modes = parse_modes(row.get("Analysläge", ""))

        datacol, match_type = match_metric_to_data_column(row, data_columns)

        # Include row if exact mode is listed, or generic/multi-mode includes it.
        # __ALL__ is used internally so selected metrics can persist across analysis modes.
        #
        # Special rule for Spelare:
        # if a player/career file contains a metric that currently belongs to Lag/Match
        # in taxonomy, still show it in Spelare mode because the uploaded player file proves
        # the metric exists for player-season analysis.
        include_from_other_mode_for_player = (
            analysis_mode == "Spelare"
            and datacol is not None
        )

        if (
            analysis_mode != "__ALL__"
            and modes
            and analysis_mode not in modes
            and not include_from_other_mode_for_player
        ):
            continue

        display_mode = row.get("Analysläge", "")
        if include_from_other_mode_for_player and "Spelare" not in modes:
            display_mode = f"Spelare (från {display_mode})"

        rows.append({
            "MetricID": row.get("MetricID", ""),
            "Metric": row.get("Metric", ""),
            "Analysläge": display_mode if "display_mode" in locals() else row.get("Analysläge", ""),
            "Analysblock": row.get("Analysblock", "Overall"),
            "Underblock": row.get("Underblock", "Overall"),
            "Underkategori": row.get("Underkategori", "Overall"),
            "MetricTyp": row.get("MetricTyp", "Value"),
            "FörEmot": row.get("FörEmot", "För / högre bättre"),
            "Normalisering": row.get("Normalisering", "Soft"),
            "DefaultIChart": row.get("DefaultIChart", "No"),
            "Matchningsregel": row.get("Matchningsregel", "ExactOnly"),
            "Status": row.get("Status", ""),
            "DataColumnExact": row.get("DataColumnExact", ""),
            "Aliases": row.get("Aliases", ""),
            "Finns i data": datacol is not None,
            "Datakolumn": datacol or "",
            "Matchningstyp": match_type,
        })

    return pd.DataFrame(rows)


# ==================================================
# NORMALIZATION / DISPLAY
# ==================================================

def normalize_series(series, inverse=False, method="Soft"):
    numeric = parse_numeric_series(series)

    if numeric.notna().sum() == 0:
        return pd.Series([0] * len(numeric), index=numeric.index)

    method = str(method or "Soft")

    if method == "None":
        return numeric.fillna(0)

    if method == "Percentil":
        return (numeric.rank(pct=True, ascending=inverse) * 100).fillna(0).clip(0, 100)

    min_val = numeric.min()
    max_val = numeric.max()

    if min_val == max_val:
        return pd.Series([50] * len(numeric), index=numeric.index)

    if method == "Min/Max":
        if inverse:
            out = ((max_val - numeric) / (max_val - min_val)) * 100
        else:
            out = ((numeric - min_val) / (max_val - min_val)) * 100
        return out.fillna(0).clip(0, 100)

    mid = (min_val + max_val) / 2
    spread = max_val - min_val or 1

    if inverse:
        out = 50 + ((mid - numeric) / spread) * 50
    else:
        out = 50 + ((numeric - mid) / spread) * 50

    return out.fillna(0).clip(0, 100)


def make_display_name(df, entity_col, analysis_mode):
    team_col = find_first_existing(df, ["Team", "Lag", "team"])
    match_col = "Match Label" if "Match Label" in df.columns else ("Source File" if "Source File" in df.columns else None)

    if "Match Date" in df.columns and match_col:
        dated_match = [
            format_match_label_with_date(label, date)
            for label, date in zip(df[match_col], df["Match Date"])
        ]
        dated_match = pd.Series(dated_match, index=df.index)
    elif match_col:
        dated_match = df[match_col].astype(str)
    else:
        dated_match = pd.Series([""] * len(df), index=df.index)

    if analysis_mode == "Match":
        if match_col:
            return dated_match
        return df[entity_col].astype(str)

    if analysis_mode == "Lag" and match_col and entity_col != match_col:
        return df[entity_col].astype(str) + " | " + dated_match.astype(str)

    if team_col and match_col and entity_col not in [team_col, match_col]:
        return df[entity_col].astype(str) + " | " + df[team_col].astype(str) + " | " + dated_match.astype(str)

    return df[entity_col].astype(str)


def auto_entity_column(df, analysis_mode):
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
# LONG / WIDE DATA FORMAT SUPPORT
# ==================================================

def detect_metric_label_column(df):
    """
    Detects reports where metrics are stored as rows, e.g.
    Metric Label | Mora IK | League Median | League Leader Value
    """
    candidates = [
        "Metric Label",
        "Metric",
        "Metric Name",
        "Metric label",
        "Parameter",
        "Parameter Label",
        "Stat",
        "Stat Label",
    ]

    for col in candidates:
        if col in df.columns:
            return col

    return None


def is_long_metric_report(df):
    metric_col = detect_metric_label_column(df)

    if metric_col is None:
        return False

    # Long metric reports have many rows where the metric column is text.
    if len(df) < 5:
        return False

    text_count = df[metric_col].dropna().astype(str).str.strip().ne("").sum()

    return text_count >= 5


def numeric_value_columns_for_long_report(df, metric_col):
    """
    Pick columns that can behave as values/entities in a long metric report.
    Excludes obvious metadata columns.
    """
    excluded_keywords = [
        "rank",
        "team",
        "player",
        "players",
        "name",
        "label",
        "source",
        "match",
        "file",
    ]

    value_cols = []

    for col in df.columns:
        if col == metric_col:
            continue

        low = str(col).lower()

        if any(x in low for x in excluded_keywords):
            continue

        numeric = parse_numeric_series(df[col])

        if numeric.notna().sum() > 0:
            value_cols.append(col)

    return value_cols


def convert_long_metric_report_to_wide(df, source_name="", match_date=pd.NaT):
    """
    Converts:
        Metric Label | Mora IK | League Median
        xG           | 123     | 100
        xGA          | 80      | 90

    Into:
        Display Name     | xG  | xGA
        Mora IK          | 123 | 80
        League Median    | 100 | 90

    This allows exact taxonomy mapping against metric names without fuzzy matching.
    """
    metric_col = detect_metric_label_column(df)

    if metric_col is None:
        return df.copy(), False

    value_cols = numeric_value_columns_for_long_report(df, metric_col)

    if not value_cols:
        return df.copy(), False

    rows = []

    metric_names = df[metric_col].astype(str).map(normalize_column_name)

    for value_col in value_cols:
        out = {
            "Display Name": normalize_column_name(value_col),
            "Source File": source_name,
            "Match Label": source_name,
            "Match Date": match_date,
            "Report Format": "Long metric report",
        }

        values = parse_numeric_series(df[value_col])

        for metric_name, value in zip(metric_names, values):
            if metric_name and metric_name.lower() != "nan":
                out[metric_name] = value

        rows.append(out)

    wide = pd.DataFrame(rows)

    return wide, True


def normalize_uploaded_frames(frames):
    """
    Supports both:
    1. Wide reports: metrics are columns.
    2. Long reports: metrics are rows under Metric Label.
    """
    normalized = []
    converted_any = False

    for frame in frames:
        source_name = frame["Source File"].iloc[0] if "Source File" in frame.columns and len(frame) else ""

        if is_long_metric_report(frame):
            match_date = frame["Match Date"].iloc[0] if "Match Date" in frame.columns and len(frame) else pd.NaT
            wide, converted = convert_long_metric_report_to_wide(frame, source_name=source_name, match_date=match_date)
            normalized.append(wide)
            converted_any = converted_any or converted
        else:
            normalized.append(frame)

    if not normalized:
        return pd.DataFrame(), False

    return pd.concat(normalized, ignore_index=True, sort=False), converted_any



# ==================================================
# CAREER / PLAYER SEASON SUPPORT + HYBRID METRICS
# ==================================================

def infer_player_name_from_filename(name):
    text = str(name)
    stem = re.sub(r"\.(csv|xlsx)$", "", text, flags=re.IGNORECASE)
    m = re.search(r"Career\s*-\s*(.*?)(?:,\s*\d{1,2}[-_ ][A-Za-z]{3,9}[-_ ]\d{4}|$)", stem, flags=re.IGNORECASE)
    if m:
        return normalize_column_name(m.group(1))
    return normalize_column_name(stem)


def detect_season_column(df):
    for col in ["Career", "Season", "Säsong", "Sasong", "Year", "Years"]:
        if col in df.columns:
            return col
    return None


def normalize_season_value(value):
    return str(value).strip().replace("/", "-")


def add_career_metadata(df, source_name):
    df = df.copy()
    if "Player" not in df.columns or df["Player"].isna().all():
        df["Player"] = infer_player_name_from_filename(source_name)
    season_col = detect_season_column(df)
    if season_col is not None:
        df["Season"] = df[season_col].map(normalize_season_value)
        df["Report Format"] = "Career / player season report"
    elif "Season" not in df.columns:
        df["Season"] = ""
    return df


def metric_type_from_name(metric):
    name = str(metric).lower()
    if "%" in str(metric) or "rate" in name or "percentage" in name or "ratio" in name:
        return "Success % / Rate"
    if "xg" in name or "expected" in name or "act2x" in name:
        return "Expected Value"
    if any(x in name for x in ["failed", "lost", "missed", "unsuccessful"]):
        return "Failed / Lost"
    if any(x in name for x in ["successful", "won", "wins", "save", "recovered", "scored"]):
        return "Successful / Positive Count"
    if any(x in name for x in ["attempt", "total", "shot", "goal", "pass", "entry", "exit", "toi", "games"]):
        return "Total Attempts / Count"
    return "Value"


def direction_from_name(metric):
    name = str(metric).lower()
    if any(x in name for x in ["toi", "games played", "gp", "career", "season"]):
        return "Neutral"
    if any(x in name for x in ["xga", "against", "gaa", "isa", "failed", "lost", "turnover", "penalty"]):
        return "Emot / lägre bättre"
    return "För / högre bättre"


def classify_detected_metric(metric, analysis_mode):
    name = str(metric).lower()
    if analysis_mode == "Spelare":
        if "f/o" in name or "faceoff" in name or "face-off" in name:
            if "oz" in name:
                return "Faceoff", "OZ faceoffs", "Faceoff %"
            if "dz" in name:
                return "Faceoff", "DZ faceoffs", "Faceoff %"
            return "Faceoff", "Alla faceoffs", "Faceoff attempts"
        if "woi" in name or "corsi" in name or "xgf %" in name:
            if "xg" in name or "xgf" in name:
                return "WOI", "WOI xG / chances", "WOI xG / chances"
            if "shot" in name or "isf" in name or "isa" in name:
                return "WOI", "WOI shots", "WOI shots"
            return "WOI", "WOI possession", "WOI possession"
        if "ozstart" in name or "toi" in name or "games" in name:
            return "Generell", "Usage / deployment", "Zone starts"
        if "xg" in name or "shot" in name or "soo" in name or "sot" in name:
            return "Offensivt", "Skott / shot", "xG / chances"
    return "Alla hittade metrics", "Alla hittade metrics", "Uppladdad fil"


def build_detected_metrics_catalog(df, taxonomy_df, analysis_mode):
    excluded = {
        "Display Name", "Source File", "Match Label", "Match Date", "Report Format",
        "Player", "Team", "Lag", "Position", "Season", "Career", "Name", "Player Name",
    }
    existing_metric_names = set(taxonomy_df["Metric"].dropna().astype(str).str.strip().str.lower().tolist())
    rows = []
    excluded_lower = {x.lower() for x in excluded}
    for col in df.columns:
        if str(col).strip().lower() in excluded_lower:
            continue
        if parse_numeric_series(df[col]).notna().sum() == 0:
            continue
        if str(col).strip().lower() in existing_metric_names:
            continue
        block, under, subcat = classify_detected_metric(col, analysis_mode)
        rows.append({
            "MetricID": f"DETECTED_{len(rows)+1:04d}_{re.sub(r'[^A-Za-z0-9]+', '_', str(col))[:40]}",
            "Active": "Yes",
            "Analysläge": analysis_mode,
            "Analysblock": block,
            "Underblock": under,
            "Underkategori": subcat,
            "Metric": str(col),
            "DataColumnExact": str(col),
            "Aliases": "",
            "MetricTyp": metric_type_from_name(col),
            "FörEmot": direction_from_name(col),
            "Normalisering": "Soft",
            "DefaultIChart": "No",
            "Matchningsregel": "ExactOnly",
            "Kommentar": "Automatiskt hittad metric från uppladdad fil. Lägg till i taxonomy om den ska få fast placering.",
            "Status": "Detected",
        })
    if not rows:
        return taxonomy_df
    return pd.concat([taxonomy_df, pd.DataFrame(rows)], ignore_index=True, sort=False)



# ==================================================
# GLOBAL PERSISTENT FILTER STATE
# ==================================================

def persistent_multiselect(label, options, store_key, default=None, sidebar=True, help=None):
    """
    Global multiselect that preserves selected values even when changing page/analysis mode.
    Selections are only removed manually by the user or when the selected value no longer exists in options.
    """
    options = [str(x) for x in options if str(x) != "nan"]
    option_set = set(options)

    if default is None:
        default = options

    if store_key not in st.session_state:
        st.session_state[store_key] = [str(x) for x in default if str(x) in option_set]
    else:
        # Keep existing values that still exist. Do not auto-reset to all/new defaults.
        st.session_state[store_key] = [
            str(x) for x in st.session_state.get(store_key, [])
            if str(x) in option_set
        ]

    widget_key = make_widget_key("widget", store_key)

    target = st.sidebar if sidebar else st

    selected = target.multiselect(
        label,
        options=options,
        default=st.session_state[store_key],
        key=widget_key,
        help=help,
    )

    st.session_state[store_key] = selected
    return selected


def reset_global_filters_button():
    with st.sidebar.expander("Rensa sparade val", expanded=False):
        st.caption("Rensar filter och val som sparats mellan analyslägen.")
        if st.button("Rensa alla sparade val", key="clear_all_global_saved_values"):
            keys_to_clear = [
                key for key in list(st.session_state.keys())
                if key.startswith("global_filter_")
                or key.startswith("global_entities_")
                or key == "selected_metrics_store_global_all_modes"
            ]
            for key in keys_to_clear:
                del st.session_state[key]
            st.rerun()




# ==================================================
# SMART TREND TEMPLATE SUPPORT
# ==================================================

def read_xlsx_smart(name, content):
    """
    Reads normal Excel files and trend-template Excel files like Mora.xlsx.

    Trend template support:
    - Looks for a sheet named 'Games' or a sheet with a row containing 'Game'.
    - Uses the row containing 'Game' as column headers.
    - Uses the row above as group/category headers when available.
    - Produces a clean wide dataframe with one row per game and metric columns.
    """
    bio = BytesIO(content)

    try:
        sheets = pd.read_excel(bio, sheet_name=None, header=None)
    except Exception:
        bio.seek(0)
        return pd.read_excel(bio)

    def parse_games_sheet(raw_df):
        header_idx = None
        max_scan = min(15, len(raw_df))
        for i in range(max_scan):
            row_vals = raw_df.iloc[i].astype(str).str.strip().str.lower().tolist()
            if "game" in row_vals:
                header_idx = i
                break
        if header_idx is None:
            return None

        group_idx = max(0, header_idx - 1)
        groups = raw_df.iloc[group_idx].copy() if group_idx != header_idx else pd.Series([""] * raw_df.shape[1])
        groups = groups.ffill()

        headers = []
        used = {}
        for col_idx in range(raw_df.shape[1]):
            sub = normalize_column_name(raw_df.iloc[header_idx, col_idx])
            group = normalize_column_name(groups.iloc[col_idx]) if col_idx < len(groups) else ""

            if not sub or sub.lower() in ["nan", "none"]:
                headers.append(None)
                continue

            if sub.lower() == "game":
                name_out = "Game"
            else:
                if group and group.lower() not in ["nan", "none", sub.lower()]:
                    name_out = f"{group} - {sub}"
                else:
                    name_out = sub

            if name_out in used:
                used[name_out] += 1
                name_out = f"{name_out} ({used[name_out]})"
            else:
                used[name_out] = 1

            headers.append(name_out)

        data = raw_df.iloc[header_idx + 1:].copy()
        keep_cols = [i for i, h in enumerate(headers) if h]
        data = data.iloc[:, keep_cols]
        data.columns = [headers[i] for i in keep_cols]

        if "Game" in data.columns:
            data = data[pd.to_numeric(data["Game"], errors="coerce").notna()].copy()
            data["Game"] = pd.to_numeric(data["Game"], errors="coerce")

        # Remove entirely empty columns and rows
        data = data.dropna(axis=1, how="all").dropna(axis=0, how="all")

        if data.empty:
            return None

        data["Report Format"] = "Trend template / Games"
        return data.reset_index(drop=True)

    # Prefer a Games sheet, otherwise scan all sheets.
    ordered_items = []
    if "Games" in sheets:
        ordered_items.append(("Games", sheets["Games"]))
    ordered_items.extend([(k, v) for k, v in sheets.items() if k != "Games"])

    for sheet_name, raw in ordered_items:
        parsed = parse_games_sheet(raw)
        if parsed is not None:
            parsed["Trend Source Sheet"] = sheet_name
            return parsed

    # Fallback normal first sheet with normal headers.
    bio.seek(0)
    return pd.read_excel(bio)


def trend_numeric_metric_columns(df):
    excluded = {
        "Display Name", "Source File", "Match Label", "Match Date", "Report Format",
        "Player", "Team", "Lag", "Position", "Season", "Career", "Name", "Player Name",
        "Trend Source Sheet",
    }
    cols = []
    for col in df.columns:
        if str(col) in excluded:
            continue
        if parse_numeric_series(df[col]).notna().sum() > 0:
            cols.append(col)
    return cols


def natural_sort_trend_df(df, x_col):
    out = df.copy()
    if x_col == "__row__":
        out["_trend_x"] = range(1, len(out) + 1)
        return out.sort_values("_trend_x"), "_trend_x", "Rad"

    if x_col not in out.columns:
        out["_trend_x"] = range(1, len(out) + 1)
        return out.sort_values("_trend_x"), "_trend_x", "Rad"

    if "date" in x_col.lower() or "datum" in x_col.lower():
        out["_trend_x"] = pd.to_datetime(out[x_col], errors="coerce")
        return out.sort_values("_trend_x", na_position="last"), "_trend_x", x_col

    # Season like 2020-2021: sort by first year
    if str(x_col).lower() in ["season", "career", "säsong", "sasong"]:
        out["_trend_x_sort"] = out[x_col].astype(str).str.extract(r"(\d{4})")[0].astype(float)
        out["_trend_x"] = out[x_col].astype(str)
        return out.sort_values("_trend_x_sort", na_position="last"), "_trend_x", x_col

    numeric = pd.to_numeric(out[x_col], errors="coerce")
    if numeric.notna().sum() > 0:
        out["_trend_x"] = numeric
        return out.sort_values("_trend_x", na_position="last"), "_trend_x", x_col

    out["_trend_x"] = out[x_col].astype(str)
    return out.sort_values("_trend_x"), "_trend_x", x_col


def render_persistent_trend_tab(raw_df, selected_metrics=None):
    st.subheader("📈 Trendmall / råvärden över tid")
    st.caption("Den här fliken ligger kvar oavsett analysläge. Appen hittar själv möjlig x-axel, enhet och numeriska metrics från uppladdad fil.")

    if raw_df is None or raw_df.empty:
        st.info("Ladda upp en fil för att visa trend.")
        return

    trend_df = raw_df.copy()

    metric_options = trend_numeric_metric_columns(trend_df)
    if not metric_options:
        st.warning("Inga numeriska metric-kolumner hittades i uppladdad fil.")
        return

    possible_x = []
    for candidate in ["Match Date", "Game", "Season", "Career"]:
        if candidate in trend_df.columns:
            possible_x.append(candidate)
    possible_x.append("__row__")

    default_x = possible_x[0]
    x_col = st.selectbox(
        "X-axel",
        options=possible_x,
        index=possible_x.index(default_x),
        format_func=lambda x: "Radnummer" if x == "__row__" else x,
        key="global_trend_x_axis",
    )

    entity_options = [c for c in ["Display Name", "Team", "Lag", "Player", "Source File", "Match Label", "Position"] if c in trend_df.columns]
    if not entity_options:
        trend_df["Trend Entity"] = "Uppladdad fil"
        entity_options = ["Trend Entity"]

    entity_col = st.selectbox(
        "Linjegruppering",
        options=entity_options,
        index=0,
        key="global_trend_entity_col",
    )

    selected_present = [m for m in (selected_metrics or []) if m in metric_options]
    default_metrics = selected_present[:min(6, len(selected_present))] if selected_present else metric_options[:min(6, len(metric_options))]

    trend_metrics = persistent_multiselect(
        "Välj metrics för trendmall",
        options=metric_options,
        store_key="global_trend_template_metrics",
        default=default_metrics,
        sidebar=False,
    )

    if not trend_metrics:
        st.warning("Välj minst en metric.")
        return

    entity_values = sorted([str(x) for x in trend_df[entity_col].dropna().unique().tolist()])
    selected_entities = persistent_multiselect(
        "Välj linjer/enheter",
        options=entity_values,
        store_key="global_trend_template_entities",
        default=entity_values[:min(6, len(entity_values))],
        sidebar=False,
    )

    if selected_entities:
        trend_df = trend_df[trend_df[entity_col].astype(str).isin(selected_entities)].copy()

    trend_df, actual_x, x_title = natural_sort_trend_df(trend_df, x_col)

    fig = go.Figure()

    for entity in trend_df[entity_col].dropna().astype(str).unique():
        entity_df = trend_df[trend_df[entity_col].astype(str) == entity].copy()

        for metric in trend_metrics:
            if metric not in entity_df.columns:
                continue

            y = parse_numeric_series(entity_df[metric])
            if y.notna().sum() == 0:
                continue

            fig.add_trace(
                go.Scatter(
                    x=entity_df[actual_x],
                    y=y,
                    mode="lines+markers",
                    name=f"{entity} | {metric}",
                    hovertemplate="%{x}<br>%{y}<extra></extra>",
                )
            )

    fig.update_layout(
        height=700,
        xaxis_title=x_title,
        yaxis_title="Råvärde",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="left", x=0),
        margin=dict(l=20, r=20, t=50, b=140),
    )

    st.plotly_chart(fig, use_container_width=True)

    show_cols = [entity_col, actual_x] + [m for m in trend_metrics if m in trend_df.columns]
    show_cols = list(dict.fromkeys(show_cols))
    st.dataframe(trend_df[show_cols], use_container_width=True)

    with st.expander("Kolumner som appen hittade i trendfilen", expanded=False):
        st.write(metric_options)


# ==================================================
# MAIN RENDERER
# ==================================================

def render_analysis_page(analysis_mode):
    st.title(f"🏒 {analysis_mode}")
    st.caption("Exakt mapping: DataColumnExact/Aliases → Metric. Ingen fuzzy matching.")

    st.markdown("""
    <style>
    section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label { align-items: flex-start; }
    section[data-testid="stSidebar"] div[data-testid="stCheckbox"] p {
        white-space: normal !important;
        line-height: 1.25;
        font-size: 0.88rem;
    }
    </style>
    """, unsafe_allow_html=True)

    taxonomy_df = load_taxonomy_master()

    if taxonomy_df.empty:
        st.error("Kunde inte läsa data/taxonomy_editor.xlsx.")
        st.stop()

    st.sidebar.header("1. Data")

    uploaded_files = st.sidebar.file_uploader(
        "Ladda upp CSV/Excel-filer",
        type=["csv", "xlsx"],
        accept_multiple_files=True,
        key=f"upload_{analysis_mode}",
    )

    # Store uploads globally so they remain when switching between multipage analysis modes.
    store_uploaded_files(uploaded_files)

    stored_files = get_stored_uploaded_files()

    if stored_files:
        with st.sidebar.expander(f"Uppladdade filer ({len(stored_files)})", expanded=False):
            for item in stored_files:
                st.write(f"• {item['name']}")
            if st.button("Rensa uppladdade filer", key=make_widget_key("clear_uploads", analysis_mode)):
                clear_stored_uploaded_files()
                st.rerun()

    frames = []

    if stored_files:
        for file_item in stored_files:
            try:
                temp = read_uploaded_file_cached(file_item["name"], file_item["content"])
                temp = temp.copy()
                temp.columns = [normalize_column_name(c) for c in temp.columns]
                temp["Source File"] = file_item["name"]
                temp["Match Label"] = infer_match_from_filename(file_item["name"])
                temp["Match Date"] = infer_match_date_from_filename(file_item["name"])
                temp = add_career_metadata(temp, file_item["name"])
                frames.append(temp)
            except Exception as e:
                st.sidebar.error(f"Kunde inte läsa {file_item['name']}: {e}")

    if frames:
        df, converted_long_format = normalize_uploaded_frames(frames)
        if converted_long_format:
            st.sidebar.success("Lång rapportstruktur upptäckt: Metric Label-rader har konverterats till metric-kolumner.")
    else:
        df = pd.DataFrame({
            "Team": ["Demo Team"],
            "Match Label": ["Demo"],
            "Source File": ["Demo"],
            "Match Date": [pd.Timestamp.today().normalize()],
            "Goals": [3],
            "xG": [2.4],
            "Shots": [28],
            "Save %": [91.2],
        })
        converted_long_format = False

    df.columns = [normalize_column_name(c) for c in df.columns]
    df = add_career_metadata(df, df["Source File"].iloc[0] if "Source File" in df.columns and len(df) else "")

    # Hybrid metric system:
    # taxonomy remains structure/facit, but all numeric metrics in uploaded files are also selectable.
    taxonomy_df = build_detected_metrics_catalog(df, taxonomy_df, analysis_mode)

    st.sidebar.header("2. Analys")

    # För long-format rapporter skapas Display Name automatiskt från värdekolumnerna,
    # t.ex. Mora IK, League Median, League Leader Value.
    if converted_long_format and "Display Name" in df.columns:
        auto_entity = "Display Name"
    else:
        auto_entity = auto_entity_column(df, analysis_mode)
    entity_options = text_like_columns(df) or list(df.columns)

    if auto_entity not in entity_options and entity_options:
        auto_entity = entity_options[0]

    with st.sidebar.expander("Avancerat: jämförelsekolumn", expanded=False):
        entity_col = st.selectbox(
            "Jämför på",
            options=entity_options,
            index=entity_options.index(auto_entity) if auto_entity in entity_options else 0,
            key=f"entity_{analysis_mode}",
        )

    st.sidebar.caption(f"Jämför på: **{entity_col}**")

    # Filters
    st.sidebar.header("3. Filter")

    team_col = find_first_existing(df, ["Team", "Lag", "team"])
    match_col = "Match Label" if "Match Label" in df.columns else ("Source File" if "Source File" in df.columns else None)

    if team_col:
        teams = sorted(df[team_col].dropna().astype(str).unique().tolist())
        selected_teams = persistent_multiselect(
            "Filtrera lag",
            options=teams,
            store_key="global_filter_teams",
            default=teams,
            sidebar=True,
        )
        df = df[df[team_col].astype(str).isin(selected_teams)]

    if match_col:
        matches = sorted(df[match_col].dropna().astype(str).unique().tolist())
        selected_matches = persistent_multiselect(
            "Filtrera matcher/källor",
            options=matches,
            store_key="global_filter_matches",
            default=matches,
            sidebar=True,
        )
        df = df[df[match_col].astype(str).isin(selected_matches)]

    # Career/player-season filters.
    if "Player" in df.columns:
        players = sorted([x for x in df["Player"].dropna().astype(str).unique().tolist() if x and x.lower() != "nan"])
        if players:
            selected_players = persistent_multiselect(
                "Filtrera spelare",
                options=players,
                store_key="global_filter_players",
                default=players,
                sidebar=True,
            )
            df = df[df["Player"].astype(str).isin(selected_players)]

    if "Season" in df.columns:
        seasons = sorted(
            [x for x in df["Season"].dropna().astype(str).unique().tolist() if x and x.lower() != "nan" and x != ""],
            reverse=True,
        )
        if seasons:
            selected_seasons = persistent_multiselect(
                "Filtrera säsonger",
                options=seasons,
                store_key="global_filter_seasons",
                default=seasons,
                sidebar=True,
            )
            df = df[df["Season"].astype(str).isin(selected_seasons)]


    if converted_long_format and entity_col == "Display Name":
        if analysis_mode in ["Lag", "Match"] and "Match Date" in df.columns and "Match Label" in df.columns:
            df["Display Name"] = df["Display Name"].astype(str) + " | " + pd.Series(
                [format_match_label_with_date(label, date) for label, date in zip(df["Match Label"], df["Match Date"])],
                index=df.index,
            )
        else:
            df["Display Name"] = df["Display Name"].astype(str)
    else:
        df["Display Name"] = make_display_name(df, entity_col, analysis_mode)

    # If this is a player/career report, show player-season combinations.
    if analysis_mode == "Spelare" and "Player" in df.columns and "Season" in df.columns:
        df["Display Name"] = df["Player"].astype(str) + " | " + df["Season"].astype(str)

    catalog_df = build_metric_catalog_for_mode(taxonomy_df, analysis_mode, df.columns)
    full_catalog_df = build_metric_catalog_for_mode(taxonomy_df, "__ALL__", df.columns)

    if catalog_df.empty:
        st.error(f"Inga taxonomy-rader finns för analysläge {analysis_mode}. Kontrollera taxonomy_editor.xlsx.")
        st.stop()

    # Selection hierarchy
    st.sidebar.header("4. Välj analysblock")

    normalization_default = "Soft"

    # Preserve the order from taxonomy_editor.xlsx while keeping preferred main blocks first.
    blocks = catalog_df["Analysblock"].dropna().astype(str).drop_duplicates().tolist()
    preferred_blocks = ["Overall", "Generell", "Defensivt", "Offensivt", "WOI", "Målvakt", "Specialteam", "Faceoff", "Playmaking", "NZ", "Alla hittade metrics"]
    block_options = [b for b in preferred_blocks if b in blocks] + [b for b in blocks if b not in preferred_blocks]

    selected_block = st.sidebar.radio("Analysblock", options=block_options, index=0, key=f"block_{analysis_mode}")
    block_df = catalog_df[catalog_df["Analysblock"] == selected_block].copy()

    underblocks = sorted(block_df["Underblock"].dropna().astype(str).unique().tolist())
    selected_underblock = st.sidebar.selectbox("Underblock", options=["Alla"] + underblocks, index=0, key=f"underblock_{analysis_mode}")

    if selected_underblock != "Alla":
        block_df = block_df[block_df["Underblock"] == selected_underblock].copy()

    subcats = sorted(block_df["Underkategori"].dropna().astype(str).unique().tolist())
    selected_subcat = st.sidebar.selectbox("Underkategori", options=["Alla"] + subcats, index=0, key=f"subcat_{analysis_mode}")

    if selected_subcat != "Alla":
        block_df = block_df[block_df["Underkategori"] == selected_subcat].copy()

    search = st.sidebar.text_input("Sök metrics", placeholder="Ex: xGA, breakout, save...", key=f"metric_search_{analysis_mode}").strip().lower()

    # Scope before search. Search controls visible checkboxes only.
    # Previously selected metrics remain selected even when search text changes.
    selection_scope_df = block_df.copy()

    if search:
        block_df = block_df[
            block_df["Metric"].astype(str).str.lower().str.contains(search, na=False)
            | block_df["DataColumnExact"].astype(str).str.lower().str.contains(search, na=False)
            | block_df["Aliases"].astype(str).str.lower().str.contains(search, na=False)
        ]

    if block_df.empty:
        st.info("Inga metrics matchar sökningen, men tidigare valda metrics ligger kvar.")

    # Metric selection mode
    available_metrics = selection_scope_df[selection_scope_df["Finns i data"] == True]["Metric"].dropna().unique().tolist()
    all_metrics = selection_scope_df["Metric"].dropna().unique().tolist()

    select_mode = st.sidebar.radio(
        "Metric-urval",
        ["Rekommenderade", "Alla som finns i data", "Alla från taxonomy", "Manuellt"],
        key=f"select_mode_{analysis_mode}",
    )

    if select_mode == "Alla som finns i data":
        default_metrics = available_metrics
    elif select_mode == "Alla från taxonomy":
        default_metrics = all_metrics
    elif select_mode == "Rekommenderade":
        default_rows = block_df[
            (block_df["DefaultIChart"].astype(str).str.lower().isin(["yes", "ja", "true", "1"]))
            & (block_df["Finns i data"] == True)
        ]
        if default_rows.empty:
            default_metrics = available_metrics[:min(12, len(available_metrics))]
        else:
            default_metrics = default_rows["Metric"].dropna().unique().tolist()
    else:
        default_metrics = []

    default_set = set(default_metrics)

    st.sidebar.markdown("**Metrics**")

    # Persistent metric selection:
    # Select one metric, search another, select it, and keep all previous selections.
    # Fully global metric selection:
    # selected metrics remain in chart even when changing analysis mode,
    # analysis block, underblock or undercategory.
    selection_key = "selected_metrics_store_global_all_modes"

    if selection_key not in st.session_state:
        # Start with defaults for the first opened view only.
        st.session_state[selection_key] = list(default_set)

    selected_metrics_store = set(st.session_state.get(selection_key, []))

    c_sel1, c_sel2 = st.sidebar.columns(2)

    with c_sel1:
        if st.button(
            "Lägg till synliga",
            key=make_widget_key("add_visible_metrics", analysis_mode, selected_block, selected_underblock, selected_subcat, search),
        ):
            selected_metrics_store.update(block_df["Metric"].dropna().astype(str).tolist())
            st.session_state[selection_key] = sorted(selected_metrics_store)
            st.rerun()

    with c_sel2:
        if st.button(
            "Rensa val",
            key=make_widget_key("clear_metrics", analysis_mode, selected_block, selected_underblock, selected_subcat),
        ):
            st.session_state[selection_key] = []
            selected_metrics_store = set()
            st.rerun()

    for _, row in block_df.iterrows():
        metric = str(row["Metric"])
        exists = bool(row["Finns i data"])
        prefix = "✅" if exists else "⚪"
        label = f"{prefix} {metric}"

        checked = st.sidebar.checkbox(
            label,
            value=metric in selected_metrics_store,
            key=make_widget_key(
                "metric",
                analysis_mode,
                selected_block,
                selected_underblock,
                selected_subcat,
                row.name,
                row.get("MetricID", ""),
                metric,
                row.get("Datakolumn", ""),
            ),
        )

        if checked:
            selected_metrics_store.add(metric)
        else:
            selected_metrics_store.discard(metric)

        st.sidebar.caption(
            f"{row['MetricTyp']} | {row['FörEmot']} | "
            f"{'Data: ' + str(row['Datakolumn']) if exists else 'Saknas i data'}"
        )

    st.session_state[selection_key] = sorted(selected_metrics_store)
    selected_metrics = sorted(selected_metrics_store)

    if selected_metrics:
        with st.sidebar.expander(f"Valda metrics i chart ({len(selected_metrics)})", expanded=False):
            selected_preview = full_catalog_df[full_catalog_df["Metric"].isin(selected_metrics)][
                ["Metric", "Analysläge", "Analysblock", "Underblock", "Underkategori"]
            ].drop_duplicates()
            for _, selected_row in selected_preview.iterrows():
                st.write(
                    f"• {selected_row['Metric']} "
                    f"({selected_row.get('Analysläge', '')} → {selected_row['Analysblock']} → {selected_row['Underblock']})"
                )

    if not selected_metrics:
        st.warning("Välj minst en metric.")
        st.stop()

    # Use full catalog so metrics selected from other blocks AND analysis modes remain active in chart.
    selected_rows = full_catalog_df[full_catalog_df["Metric"].isin(selected_metrics)].copy()
    selected_available_rows = selected_rows[selected_rows["Finns i data"] == True].copy()

    if selected_available_rows.empty:
        st.warning("Valda metrics finns i taxonomy men saknar matchande datakolumner i uppladdad data.")
        st.stop()

    # Build working dataframe
    df_work = df.copy()

    # Kronologisk sortering för Lag/Match.
    if "Match Date" in df_work.columns:
        df_work["Match Date"] = pd.to_datetime(df_work["Match Date"], errors="coerce")

    metrics_for_chart = []

    for _, row in selected_available_rows.iterrows():
        metric = row["Metric"]
        datacol = row["Datakolumn"]

        if datacol in df_work.columns:
            df_work[metric] = df_work[datacol]
            metrics_for_chart.append(metric)

    metrics_for_chart = list(dict.fromkeys(metrics_for_chart))

    if not metrics_for_chart:
        st.warning("Inga valda metrics kunde kopplas till datakolumner.")
        st.stop()

    agg = {metric: (lambda s: parse_numeric_series(s).mean()) for metric in metrics_for_chart}

    if analysis_mode in ["Lag", "Match"] and "Match Date" in df_work.columns:
        agg_with_date = dict(agg)
        agg_with_date["Match Date"] = "min"
        compare_df = df_work.groupby("Display Name", dropna=False).agg(agg_with_date).reset_index()
        compare_df = compare_df.sort_values(["Match Date", "Display Name"], na_position="last").reset_index(drop=True)
    else:
        compare_df = df_work.groupby("Display Name", dropna=False).agg(agg).reset_index()

    entities = compare_df["Display Name"].dropna().astype(str).unique().tolist()
    selected_entities = persistent_multiselect(
        "5. Välj vilka som visas",
        options=entities,
        store_key="global_entities_display",
        default=entities[:min(5, len(entities))],
        sidebar=True,
    )

    compare_df = compare_df[compare_df["Display Name"].astype(str).isin(selected_entities)]

    index_columns = ["Display Name"]
    if "Match Date" in compare_df.columns:
        index_columns.append("Match Date")
    index_df = compare_df[index_columns].copy()

    for _, row in selected_available_rows.iterrows():
        metric = row["Metric"]
        if metric not in compare_df.columns:
            continue
        method = row["Normalisering"] or normalization_default
        inverse = lower_is_better(row["FörEmot"])
        index_df[metric] = normalize_series(compare_df[metric], inverse=inverse, method=method)

    metrics_for_chart = [m for m in metrics_for_chart if m in index_df.columns]

    if not metrics_for_chart:
        st.warning("Inga metrics kunde normaliseras för graf.")
        st.stop()

    # Main tabs
    if analysis_mode in ["Lag", "Match"]:
        tab_spider, tab_trend, tab_template_trend, tab_profile, tab_mapping, tab_browser, tab_data = st.tabs(
            ["📊 Spiderchart", "📈 Trend", "📈 Trendmall", "🧾 Profilkort", "🔐 Mappingkontroll", "🔎 Metric Browser", "📘 Data"]
        )
    else:
        tab_spider, tab_template_trend, tab_profile, tab_mapping, tab_browser, tab_data = st.tabs(
            ["📊 Spiderchart", "📈 Trendmall", "🧾 Profilkort", "🔐 Mappingkontroll", "🔎 Metric Browser", "📘 Data"]
        )

    with tab_spider:
        st.subheader("📊 Spiderchart")
        st.caption(f"{analysis_mode} → {selected_block} → {selected_underblock} → {selected_subcat}")

        fig = go.Figure()

        for _, row in index_df.iterrows():
            values = [safe_float(row.get(metric, 0), 0) for metric in metrics_for_chart]
            values = [max(0, min(100, value)) for value in values]

            if len(values) == 1:
                r_values = values + values
                theta = metrics_for_chart + metrics_for_chart
            else:
                r_values = values + [values[0]]
                theta = metrics_for_chart + [metrics_for_chart[0]]

            fig.add_trace(
                go.Scatterpolar(
                    r=r_values,
                    theta=theta,
                    fill="toself",
                    name=str(row["Display Name"]),
                )
            )

        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            height=760,
            showlegend=True,
        )

        st.plotly_chart(fig, use_container_width=True)

    if analysis_mode in ["Lag", "Match"]:
        with tab_trend:
            st.subheader("📈 Trend över matcher")
            st.caption("Matcher sorteras kronologiskt via datum i filnamnet, t.ex. Sun_Mar_01_2026.")

            if "Match Date" not in compare_df.columns or compare_df["Match Date"].isna().all():
                st.warning("Inget matchdatum kunde läsas från filnamnen. Kontrollera att filnamnen innehåller datum.")
            else:
                trend_metric_options = [m for m in metrics_for_chart if m in compare_df.columns]

                trend_metrics = st.multiselect(
                    "Välj metric för trend",
                    options=trend_metric_options,
                    default=trend_metric_options[:min(3, len(trend_metric_options))],
                    key=make_widget_key("trend_metrics", analysis_mode, selected_block, selected_underblock, selected_subcat),
                )

                if trend_metrics:
                    trend_df = compare_df.copy()
                    trend_df["Match Date"] = pd.to_datetime(trend_df["Match Date"], errors="coerce")
                    trend_df = trend_df.sort_values(["Match Date", "Display Name"])

                    # Trend-specific team/entity filter.
                    # This solves the issue where all teams/entities appear in the trend chart at once.
                    trend_entities = trend_df["Display Name"].dropna().astype(str).unique().tolist()

                    if trend_entities:
                        default_trend_entities = trend_entities[:1]
                    else:
                        default_trend_entities = []

                    selected_trend_entities = persistent_multiselect(
                        "Välj lag/enhet för trend",
                        options=trend_entities,
                        store_key="global_entities_trend",
                        default=default_trend_entities,
                        sidebar=False,
                    )

                    if selected_trend_entities:
                        trend_df = trend_df[trend_df["Display Name"].astype(str).isin(selected_trend_entities)].copy()
                    else:
                        st.warning("Välj minst ett lag/enhet för trendgrafen.")
                        st.stop()

                    fig_trend = go.Figure()

                    for entity in trend_df["Display Name"].dropna().astype(str).unique():
                        entity_df = trend_df[trend_df["Display Name"].astype(str) == entity].copy()

                        for metric in trend_metrics:
                            fig_trend.add_trace(
                                go.Scatter(
                                    x=entity_df["Match Date"],
                                    y=parse_numeric_series(entity_df[metric]),
                                    mode="lines+markers",
                                    name=f"{entity} | {metric}",
                                    hovertemplate="%{x|%Y-%m-%d}<br>%{y}<extra></extra>",
                                )
                            )

                    fig_trend.update_layout(
                        height=620,
                        xaxis_title="Datum",
                        yaxis_title="Råvärde",
                        hovermode="x unified",
                    )

                    st.plotly_chart(fig_trend, use_container_width=True)

                    st.dataframe(
                        trend_df[["Match Date", "Display Name"] + trend_metrics],
                        use_container_width=True,
                    )
                else:
                    st.info("Välj minst en metric för trendgrafen.")


    with tab_template_trend:
        render_persistent_trend_tab(df, selected_metrics=selected_metrics)


    with tab_profile:
        st.subheader("🧾 Profilkort")

        for _, row in index_df.iterrows():
            st.markdown(f"### {row['Display Name']}")
            cols = st.columns(min(4, max(1, len(metrics_for_chart))))

            for i, metric in enumerate(metrics_for_chart):
                value = safe_float(row.get(metric, 0), 0)
                with cols[i % len(cols)]:
                    st.metric(metric, f"{value:.1f}")
                    st.progress(int(max(0, min(100, value))))

            st.divider()

    with tab_mapping:
        st.subheader("🔐 Mappingkontroll")
        st.caption("Här ser du exakt vilken uppladdad datakolumn som kopplats till vilken metric. Ingen fuzzy matching används.")

        mapping_cols = [
            "MetricID",
            "Metric",
            "DataColumnExact",
            "Aliases",
            "Finns i data",
            "Datakolumn",
            "Matchningstyp",
            "Analysblock",
            "Underblock",
            "Underkategori",
        ]

        st.dataframe(block_df[mapping_cols], use_container_width=True)

        missing = block_df[block_df["Finns i data"] == False]
        if not missing.empty:
            st.warning(f"{len(missing)} metrics i detta urval saknar matchande datakolumn.")

        detected = catalog_df[catalog_df["Status"].astype(str).str.lower().eq("detected")] if "Status" in catalog_df.columns else pd.DataFrame()
        if not detected.empty:
            st.info(f"{len(detected)} metrics har hittats i uppladdad fil men finns inte permanent i taxonomy ännu.")
            with st.expander("Visa detected metrics som bör läggas in i taxonomy", expanded=False):
                export_cols = [
                    "MetricID", "Active", "Analysläge", "Analysblock", "Underblock",
                    "Underkategori", "Metric", "DataColumnExact", "Aliases", "MetricTyp",
                    "FörEmot", "Normalisering", "DefaultIChart", "Matchningsregel",
                    "Kommentar", "Status"
                ]
                available_export_cols = [c for c in export_cols if c in detected.columns]
                st.dataframe(detected[available_export_cols], use_container_width=True)

    with tab_browser:
        st.subheader("🔎 Metric Browser")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Taxonomy-rader", len(catalog_df))
        c2.metric("Metrics i valt urval", len(block_df))
        c3.metric("Finns i data", int(block_df["Finns i data"].sum()))
        c4.metric("Valda metrics", len(metrics_for_chart))

        st.dataframe(
            catalog_df.sort_values(["Analysblock", "Underblock", "Underkategori", "Metric"]),
            use_container_width=True,
        )

    with tab_data:
        st.subheader("📘 Rådata")
        st.dataframe(df, use_container_width=True)

        st.subheader("📈 Indexdata")
        st.dataframe(index_df, use_container_width=True)

        st.subheader("Jämförelsedata")
        st.dataframe(compare_df, use_container_width=True)

        st.subheader("Uppladdade kolumner")
        st.write(list(df.columns))

        if converted_long_format:
            st.info("Den uppladdade filen var i lång rapportstruktur. Appen har konverterat Metric Label-rader till bred metric-data innan mapping.")
