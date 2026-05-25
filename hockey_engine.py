
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

    required = [
        "MetricID",
        "Active",
        "Analysläge",
        "Analysblock",
        "Underblock",
        "Underkategori",
        "Metric",
        "DataColumnExact",
        "Aliases",
        "MetricTyp",
        "FörEmot",
        "Normalisering",
        "DefaultIChart",
        "Matchningsregel",
        "Kommentar",
        "Status",
    ]

    for col in required:
        if col not in df.columns:
            df[col] = ""

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

    if analysis_mode == "Match":
        return df[entity_col].astype(str)

    if analysis_mode == "Lag" and match_col and entity_col != match_col:
        return df[entity_col].astype(str) + " | " + df[match_col].astype(str)

    if team_col and match_col and entity_col not in [team_col, match_col]:
        return df[entity_col].astype(str) + " | " + df[team_col].astype(str) + " | " + df[match_col].astype(str)

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
                frames.append(temp)
            except Exception as e:
                st.sidebar.error(f"Kunde inte läsa {file.name}: {e}")

    if frames:
        df = pd.concat(frames, ignore_index=True, sort=False)
    else:
        df = pd.DataFrame({
            "Team": ["Demo Team"],
            "Match Label": ["Demo"],
            "Source File": ["Demo"],
            "Goals": [3],
            "xG": [2.4],
            "Shots": [28],
            "Save %": [91.2],
        })

    df.columns = [normalize_column_name(c) for c in df.columns]

    st.sidebar.header("2. Analys")

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

    df["Display Name"] = make_display_name(df, entity_col, analysis_mode)

    catalog_df = build_metric_catalog_for_mode(taxonomy_df, analysis_mode, df.columns)

    if catalog_df.empty:
        st.error(f"Inga taxonomy-rader finns för analysläge {analysis_mode}. Kontrollera taxonomy_editor.xlsx.")
        st.stop()

    # Selection hierarchy
    st.sidebar.header("4. Välj analysblock")

    normalization_default = "Soft"

    blocks = sorted(catalog_df["Analysblock"].dropna().astype(str).unique().tolist())
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
            key=f"metric_{analysis_mode}_{row['MetricID']}_{selected_block}_{selected_underblock}_{selected_subcat}",
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
    compare_df = df_work.groupby("Display Name", dropna=False).agg(agg).reset_index()

    entities = compare_df["Display Name"].dropna().astype(str).unique().tolist()
    selected_entities = st.sidebar.multiselect(
        "5. Välj vilka som visas",
        options=entities,
        default=entities[:min(5, len(entities))],
        key=f"entities_{analysis_mode}",
    )

    compare_df = compare_df[compare_df["Display Name"].astype(str).isin(selected_entities)]

    index_df = compare_df[["Display Name"]].copy()

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
