
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

        # Include row if exact mode is listed, or generic/multi-mode includes it.
        if modes and analysis_mode not in modes:
            continue

        datacol, match_type = match_metric_to_data_column(row, data_columns)

        rows.append({
            "MetricID": row.get("MetricID", ""),
            "Metric": row.get("Metric", ""),
            "Analysläge": row.get("Analysläge", ""),
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

    frames = []

    if uploaded_files:
        for file in uploaded_files:
            try:
                temp = read_uploaded_file_cached(file.name, file.getvalue())
                temp = temp.copy()
                temp.columns = [normalize_column_name(c) for c in temp.columns]
                temp["Source File"] = file.name
                temp["Match Label"] = infer_match_from_filename(file.name)
                temp["Match Date"] = infer_match_date_from_filename(file.name)
                frames.append(temp)
            except Exception as e:
                st.sidebar.error(f"Kunde inte läsa {file.name}: {e}")

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
        selected_teams = st.sidebar.multiselect("Filtrera lag", options=teams, default=teams, key=f"teams_{analysis_mode}")
        df = df[df[team_col].astype(str).isin(selected_teams)]

    if match_col:
        matches = sorted(df[match_col].dropna().astype(str).unique().tolist())
        selected_matches = st.sidebar.multiselect("Filtrera matcher/källor", options=matches, default=matches, key=f"matches_{analysis_mode}")
        df = df[df[match_col].astype(str).isin(selected_matches)]

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

    catalog_df = build_metric_catalog_for_mode(taxonomy_df, analysis_mode, df.columns)

    if catalog_df.empty:
        st.error(f"Inga taxonomy-rader finns för analysläge {analysis_mode}. Kontrollera taxonomy_editor.xlsx.")
        st.stop()

    # Selection hierarchy
    st.sidebar.header("4. Välj analysblock")

    normalization_default = "Soft"

    # Preserve the order from taxonomy_editor.xlsx while keeping preferred main blocks first.
    blocks = catalog_df["Analysblock"].dropna().astype(str).drop_duplicates().tolist()
    preferred_blocks = ["Overall", "Generell", "Defensivt", "Offensivt", "WOI", "Målvakt", "Specialteam", "Faceoff", "Playmaking", "NZ"]
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

    if search:
        block_df = block_df[
            block_df["Metric"].astype(str).str.lower().str.contains(search, na=False)
            | block_df["DataColumnExact"].astype(str).str.lower().str.contains(search, na=False)
            | block_df["Aliases"].astype(str).str.lower().str.contains(search, na=False)
        ]

    if block_df.empty:
        st.warning("Inga metrics matchar urvalet.")
        st.stop()

    # Metric selection mode
    available_metrics = block_df[block_df["Finns i data"] == True]["Metric"].dropna().unique().tolist()
    all_metrics = block_df["Metric"].dropna().unique().tolist()

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

    selected_metrics = []

    for _, row in block_df.iterrows():
        metric = row["Metric"]
        exists = bool(row["Finns i data"])
        prefix = "✅" if exists else "⚪"
        label = f"{prefix} {metric}"

        checked = st.sidebar.checkbox(
            label,
            value=metric in default_set,
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
            selected_metrics.append(metric)

        st.sidebar.caption(
            f"{row['MetricTyp']} | {row['FörEmot']} | "
            f"{'Data: ' + str(row['Datakolumn']) if exists else 'Saknas i data'}"
        )

    if not selected_metrics:
        st.warning("Välj minst en metric.")
        st.stop()

    selected_rows = block_df[block_df["Metric"].isin(selected_metrics)].copy()
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
    selected_entities = st.sidebar.multiselect(
        "5. Välj vilka som visas",
        options=entities,
        default=entities[:min(5, len(entities))],
        key=f"entities_{analysis_mode}",
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
        tab_spider, tab_trend, tab_profile, tab_mapping, tab_browser, tab_data = st.tabs(
            ["📊 Spiderchart", "📈 Trend", "🧾 Profilkort", "🔐 Mappingkontroll", "🔎 Metric Browser", "📘 Data"]
        )
    else:
        tab_spider, tab_profile, tab_mapping, tab_browser, tab_data = st.tabs(
            ["📊 Spiderchart", "🧾 Profilkort", "🔐 Mappingkontroll", "🔎 Metric Browser", "📘 Data"]
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
