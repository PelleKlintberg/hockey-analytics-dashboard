import streamlit as st

st.set_page_config(
    page_title="Hockey Analytics Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🏒 Hockey Analytics Dashboard")
st.caption("Webbversion med lätt startup. Analysverktyget laddas först när du startar det.")

if "dashboard_started" not in st.session_state:
    st.session_state["dashboard_started"] = False

if not st.session_state["dashboard_started"]:
    st.info("Klicka på knappen nedan för att ladda hela hockeyanalys-appen.")
    if st.button("Starta analysverktyget", type="primary"):
        st.session_state["dashboard_started"] = True
        st.rerun()
    st.stop()

with st.spinner("Laddar analysverktyget..."):
    import dashboard_app
