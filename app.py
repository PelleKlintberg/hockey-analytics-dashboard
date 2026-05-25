import streamlit as st

st.set_page_config(
    page_title="Hockey Analytics Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🏒 Hockey Analytics Dashboard")
st.caption("Multipage-webbapp byggd för snabbare start.")

st.markdown('''
### Välj analysdel i sidomenyn

- **Lag**
- **Match**
- **Spelare**
- **Målvakt**

Appen laddar bara den del du öppnar, vilket gör den stabilare på Streamlit Cloud.
''')

st.info("Öppna en analysdel i vänstermenyn för att börja.")
