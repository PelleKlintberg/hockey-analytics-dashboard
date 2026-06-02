
from io import BytesIO
from pathlib import Path
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(page_title="Trendcenter", layout="wide", initial_sidebar_state="expanded")

st.title("📈 Trendcenter")
st.caption("Separat trendmodul: ladda upp matchfiler, bygg trenddatabas och analysera råvärden över tid.")


# ==================================================
# Helpers
# ==================================================

def normalize_column_name(value):
    return re.sub(r"\s+", " ", str(value).strip().replace('"', ""))


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


def read_uploaded_file(name, content):
    bio = BytesIO(content)
    if name.lower().endswith(".xlsx"):
        # Prefer Games sheet if it exists; otherwise first sheet.
        try:
            xls = pd.ExcelFile(bio)
            sheet = "Games" if "Games" in xls.sheet_names else xls.sheet_names[0]
            return pd.read_excel(BytesIO(content), sheet_name=sheet)
        except Exception:
            return pd.read_excel(BytesIO(content))

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


def infer_date_from_filename(name):
    """
    Safe date parser for file names like:
    Sun_Mar_01_2026_Post-Game_Report.csv
    Wed_Mar_04_2026_Post-Game_Report.csv
    2026-03-04_Report.csv
    04-03-2026_Report.csv
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

    stem = re.sub(r"\.(csv|xlsx)$", "", text, flags=re.IGNORECASE)
    parts = re.split(r"[_\-\s]+", stem)
    parts_clean = [p for p in parts if p]

    # Pattern: Mar 04 2026
    for i in range(len(parts_clean) - 2):
        month_raw = parts_clean[i].lower()
        if month_raw in month_map:
            try:
                day = int(parts_clean[i + 1])
                year = int(parts_clean[i + 2])
                return pd.Timestamp(year=year, month=month_map[month_raw], day=day)
            except Exception:
                pass

    # Pattern: Wed Mar 04 2026
    for i in range(len(parts_clean) - 3):
        month_raw = parts_clean[i + 1].lower()
        if month_raw in month_map:
            try:
                day = int(parts_clean[i + 2])
                year = int(parts_clean[i + 3])
                return pd.Timestamp(year=year, month=month_map[month_raw], day=day)
            except Exception:
                pass

    # Pattern: YYYY MM DD
    for i in range(len(parts_clean) - 2):
        try:
            a, b, c = int(parts_clean[i]), int(parts_clean[i + 1]), int(parts_clean[i + 2])
            if 1900 <= a <= 2100 and 1 <= b <= 12 and 1 <= c <= 31:
                return pd.Timestamp(year=a, month=b, day=c)
        except Exception:
            pass

    # Pattern: DD MM YYYY
    for i in range(len(parts_clean) - 2):
        try:
            a, b, c = int(parts_clean[i]), int(parts_clean[i + 1]), int(parts_clean[i + 2])
            if 1 <= a <= 31 and 1 <= b <= 12 and 1900 <= c <= 2100:
                return pd.Timestamp(year=c, month=b, day=a)
        except Exception:
            pass

    return pd.NaT


def infer_match_label(name):
    return re.sub(r"\.(csv|xlsx)$", "", str(name), flags=re.IGNORECASE).replace("_", " ").strip()


def detect_metric_label_column(df):
    candidates = ["Metric Label", "Metric", "Metric Name", "Parameter", "Parameter Label", "Stat", "Stat Label"]
    for col in candidates:
        if col in df.columns:
            return col
    return None


def numeric_value_columns_for_long_report(df, metric_col):
    excluded_keywords = ["rank", "player", "players", "name", "label", "source", "match", "file"]
    value_cols = []
    for col in df.columns:
        if col == metric_col:
            continue
        low = str(col).lower()
        if any(x in low for x in excluded_keywords):
            continue
        if parse_numeric_series(df[col]).notna().sum() > 0:
            value_cols.append(col)
    return value_cols


def convert_single_match_long_report(df, source_name):
    metric_col = detect_metric_label_column(df)
    if metric_col is None:
        return None

    value_cols = numeric_value_columns_for_long_report(df, metric_col)
    if not value_cols:
        return None

    metric_names = df[metric_col].astype(str).map(normalize_column_name)
    rows = []

    for value_col in value_cols:
        row = {
            "Entity": normalize_column_name(value_col),
            "Source File": source_name,
            "Match Label": infer_match_label(source_name),
            "Match Date": infer_date_from_filename(source_name),
            "Data Format": "Long match report",
        }
        values = parse_numeric_series(df[value_col])
        for metric, value in zip(metric_names, values):
            if metric and metric.lower() != "nan":
                row[metric] = value
        rows.append(row)

    return pd.DataFrame(rows)


def normalize_wide_report(df, source_name):
    df = df.copy()
    df.columns = [normalize_column_name(c) for c in df.columns]

    # Existing trend database / Games style
    date_col = next((c for c in ["Date", "Datum", "Match Date", "Game Date"] if c in df.columns), None)
    team_col = next((c for c in ["Team", "Lag", "Entity", "Name"] if c in df.columns), None)
    opponent_col = next((c for c in ["Opponent", "Motståndare", "Opp"] if c in df.columns), None)
    match_col = next((c for c in ["Match", "Game", "Match Label"] if c in df.columns), None)

    if "Entity" not in df.columns:
        df["Entity"] = df[team_col].astype(str) if team_col else "Uploaded"

    if "Source File" not in df.columns:
        df["Source File"] = source_name

    if "Match Label" not in df.columns:
        if match_col:
            df["Match Label"] = df[match_col].astype(str)
        elif opponent_col:
            df["Match Label"] = df["Entity"].astype(str) + " vs " + df[opponent_col].astype(str)
        else:
            df["Match Label"] = infer_match_label(source_name)

    if "Match Date" not in df.columns:
        if date_col:
            df["Match Date"] = pd.to_datetime(df[date_col], errors="coerce")
        else:
            df["Match Date"] = infer_date_from_filename(source_name)

    df["Data Format"] = "Wide/Games trend report"
    return df


def normalize_uploaded_trend_file(name, content):
    raw = read_uploaded_file(name, content)
    raw = raw.copy()
    raw.columns = [normalize_column_name(c) for c in raw.columns]

    long_df = convert_single_match_long_report(raw, name)
    if long_df is not None:
        return long_df

    return normalize_wide_report(raw, name)


def trend_db_key():
    return "trendcenter_database_rows_v1"


def stored_trend_db():
    return st.session_state.get(trend_db_key(), pd.DataFrame())


def set_trend_db(df):
    st.session_state[trend_db_key()] = df.copy()


def dedupe_trend_db(df):
    if df.empty:
        return df
    key_cols = [c for c in ["Match Date", "Entity", "Match Label", "Source File"] if c in df.columns]
    if key_cols:
        return df.drop_duplicates(subset=key_cols, keep="last").reset_index(drop=True)
    return df.drop_duplicates().reset_index(drop=True)


def merge_into_trend_db(new_df):
    old = stored_trend_db()
    combined = pd.concat([old, new_df], ignore_index=True, sort=False)
    if "Match Date" in combined.columns:
        combined["Match Date"] = pd.to_datetime(combined["Match Date"], errors="coerce")
    combined = dedupe_trend_db(combined)
    if "Match Date" in combined.columns:
        combined = combined.sort_values(["Match Date", "Entity", "Match Label"], na_position="last").reset_index(drop=True)
    set_trend_db(combined)
    return combined


def get_numeric_metric_columns(df):
    excluded = {
        "Entity", "Source File", "Match Label", "Match Date", "Data Format",
        "Date", "Datum", "Team", "Lag", "Opponent", "Motståndare", "Game", "Match"
    }
    metrics = []
    for col in df.columns:
        if str(col) in excluded:
            continue
        if parse_numeric_series(df[col]).notna().sum() > 0:
            metrics.append(col)
    return metrics


def export_excel_bytes(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="TrendDatabase", index=False)
    output.seek(0)
    return output.getvalue()


# ==================================================
# Sidebar upload / database
# ==================================================

st.sidebar.header("1. Trenddatabas")
st.sidebar.caption("Tips: matchfiler kan laddas upp under matchfiler. Om du råkar lägga en matchfil som trenddatabas försöker appen ändå lägga till den.")

uploaded_db = st.sidebar.file_uploader(
    "Ladda upp sparad trenddatabas",
    type=["xlsx", "csv"],
    accept_multiple_files=False,
    key="trendcenter_saved_db_upload",
)

if uploaded_db is not None:
    try:
        db_df = normalize_uploaded_trend_file(uploaded_db.name, uploaded_db.getvalue())
        # Accept both saved trend databases and normal match reports here.
        # If it looks like a single-match report, merge it instead of replacing the database.
        if "Data Format" in db_df.columns and db_df["Data Format"].astype(str).str.contains("Long match report", na=False).any():
            merge_into_trend_db(db_df)
            st.sidebar.success("Matchfil upptäckt och lades till i trenddatabasen.")
        else:
            set_trend_db(dedupe_trend_db(db_df))
            st.sidebar.success("Trenddatabas laddad.")
    except Exception as e:
        st.sidebar.error(f"Kunde inte läsa filen: {e}")

uploaded_match_files = st.sidebar.file_uploader(
    "Ladda upp matchfiler",
    type=["xlsx", "csv"],
    accept_multiple_files=True,
    key="trendcenter_match_uploads",
)

if uploaded_match_files:
    parsed_frames = []
    for file in uploaded_match_files:
        try:
            parsed_frames.append(normalize_uploaded_trend_file(file.name, file.getvalue()))
        except Exception as e:
            st.sidebar.error(f"Kunde inte läsa {file.name}: {e}")
    if parsed_frames:
        new_df = pd.concat(parsed_frames, ignore_index=True, sort=False)
        merge_into_trend_db(new_df)
        st.sidebar.success(f"{len(parsed_frames)} fil(er) lades till i trenddatabasen.")

with st.sidebar.expander("Rensa trendcenter", expanded=False):
    if st.button("Rensa trenddatabas från session", key="trendcenter_clear_db"):
        set_trend_db(pd.DataFrame())
        st.rerun()


db = stored_trend_db()

if db.empty:
    st.info("Ladda upp en sparad trenddatabas eller en/flera matchfiler för att börja.")
    st.stop()

if "Match Date" in db.columns:
    db["Match Date"] = pd.to_datetime(db["Match Date"], errors="coerce")
    db = db.sort_values(["Match Date", "Entity", "Match Label"], na_position="last").reset_index(drop=True)
    set_trend_db(db)


# ==================================================
# Main UI
# ==================================================

tab_database, tab_trend, tab_history = st.tabs(["🗂️ Trenddatabas", "📈 Trender", "📋 Matchhistorik"])

with tab_database:
    st.subheader("🗂️ Trenddatabas")
    c1, c2, c3 = st.columns(3)
    c1.metric("Rader", len(db))
    c2.metric("Matcher", db["Match Label"].nunique() if "Match Label" in db.columns else 0)
    c3.metric("Metrics", len(get_numeric_metric_columns(db)))

    st.dataframe(db, use_container_width=True)

    st.download_button(
        "Ladda ner uppdaterad trenddatabas (.xlsx)",
        data=export_excel_bytes(db),
        file_name="trenddatabase_updated.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

with tab_trend:
    st.subheader("📈 Trender")

    entities = sorted(db["Entity"].dropna().astype(str).unique().tolist()) if "Entity" in db.columns else []
    selected_entities = st.multiselect("Välj lag/enhet", options=entities, default=entities[:1])

    date_min = db["Match Date"].min() if "Match Date" in db.columns and db["Match Date"].notna().any() else None
    date_max = db["Match Date"].max() if "Match Date" in db.columns and db["Match Date"].notna().any() else None

    date_scope = st.radio("Tidsurval", ["Alla", "Senaste 3", "Senaste 5", "Senaste 10", "Eget datumintervall"], horizontal=True)

    trend_df = db.copy()
    if selected_entities:
        trend_df = trend_df[trend_df["Entity"].astype(str).isin(selected_entities)]

    if "Match Date" in trend_df.columns:
        trend_df = trend_df.sort_values("Match Date")

    if date_scope.startswith("Senaste"):
        n = int(date_scope.split()[-1])
        trend_df = trend_df.groupby("Entity", group_keys=False).tail(n) if "Entity" in trend_df.columns else trend_df.tail(n)
    elif date_scope == "Eget datumintervall" and date_min is not None and date_max is not None:
        start, end = st.date_input("Datumintervall", value=(date_min.date(), date_max.date()))
        trend_df = trend_df[
            (trend_df["Match Date"] >= pd.to_datetime(start))
            & (trend_df["Match Date"] <= pd.to_datetime(end))
        ]

    metric_options = get_numeric_metric_columns(trend_df)
    selected_metrics = st.multiselect("Välj metrics", options=metric_options, default=metric_options[:min(3, len(metric_options))])

    if not selected_metrics:
        st.warning("Välj minst en metric.")
    elif trend_df.empty:
        st.warning("Inga rader matchar filtren.")
    else:
        fig = go.Figure()

        for entity in trend_df["Entity"].dropna().astype(str).unique():
            entity_df = trend_df[trend_df["Entity"].astype(str) == entity].copy()
            entity_df = entity_df.sort_values("Match Date") if "Match Date" in entity_df.columns else entity_df

            x_values = entity_df["Match Date"] if "Match Date" in entity_df.columns else entity_df.index

            for metric in selected_metrics:
                fig.add_trace(
                    go.Scatter(
                        x=x_values,
                        y=parse_numeric_series(entity_df[metric]),
                        mode="lines+markers",
                        name=f"{entity} | {metric}",
                        customdata=entity_df["Match Label"] if "Match Label" in entity_df.columns else None,
                        hovertemplate="%{x|%Y-%m-%d}<br>%{customdata}<br>%{y}<extra></extra>",
                    )
                )

        fig.update_layout(
            height=700,
            xaxis_title="Datum / matchordning",
            yaxis_title="Råvärde",
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(trend_df[["Match Date", "Entity", "Match Label"] + selected_metrics], use_container_width=True)

with tab_history:
    st.subheader("📋 Matchhistorik")
    cols = [c for c in ["Match Date", "Entity", "Match Label", "Source File", "Data Format"] if c in db.columns]
    st.dataframe(db[cols].drop_duplicates().sort_values(cols[0] if cols else db.columns[0]), use_container_width=True)
