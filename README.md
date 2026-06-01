# Hockey Analytics Dashboard - Structured Taxonomy v3 + Trend

Streamlit Cloud:
- Main file path: app.py
- Python version: 3.11

Included:
- data/taxonomy_editor.xlsx = structured v3 taxonomy
- Exact mapping only: DataColumnExact or Aliases
- Long-format report support with Metric Label rows
- Date parsing from filenames like Sun_Mar_01_2026
- Match Date column
- Chronological sorting
- Trend tab for Lag/Match
- Trend line chart uses raw metric values over time


Patch: fixed StreamlitDuplicateElementKey by generating unique widget keys for metric checkboxes.


Patch: added Trend-specific team/entity selector so only selected team(s) are shown in line chart.


Patch: persistent metric selection across search. Selected metrics remain active while searching for additional metrics.


Patch: Added 17 duplicate Overall rows (Lag | Match / Overall / Overall / Overall) while preserving original taxonomy placements.


Patch: uploaded files are now stored globally in session_state and remain when switching analysis mode/pages.


Update: added player position metrics from Position_Metrics_for_ (2).csv under analysis mode Spelare.


Patch: selected metrics now persist globally per analysis mode and remain in spiderchart/trend when switching block, underblock or undercategory.


Patch: selected metrics now persist globally across all analysis modes. Selected rows are read from full taxonomy catalog.
