import streamlit as st

st.set_page_config(
    page_title="Hockey Analytics Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🏒 Hockey Analytics Dashboard")
st.caption("Version med exakt datamatchning via taxonomy_editor.xlsx")

st.markdown("""
### Välj analysdel i sidomenyn

- **Lag**
- **Match**
- **Spelare**
- **Målvakt**

Den här versionen använder `taxonomy_editor.xlsx` som master/facit.

**Viktig regel:**  
Appen matchar aldrig fuzzy. En uppladdad kolumn får endast kopplas till en metric om den matchar:

1. `DataColumnExact`
2. eller ett godkänt namn i `Aliases`

Om ingen exakt/alias-match finns visas metricen som saknad.
""")


st.markdown("### 📈 Trendcenter\nVälj **Trendcenter** i sidomenyn för separat trenddatabas, trendgraf och matchhistorik.")
