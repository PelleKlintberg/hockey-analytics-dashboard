# Hockey Analytics Dashboard - Exact Mapping + Long Report Support

Streamlit Cloud:
- Main file path: app.py
- Python version: 3.11

Important:
- Appen läser data/taxonomy_editor.xlsx som master.
- Ingen fuzzy matching används.
- Mapping görs endast via DataColumnExact eller Aliases.
- Appen stödjer både:
  1. bred data där metrics är kolumner
  2. lång data där metrics ligger i 'Metric Label'-rader
