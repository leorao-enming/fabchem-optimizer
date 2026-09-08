"""fabchem-optimizer Streamlit dashboard entry point.

P0 stub. This file must stay thin: it only calls simulate()/optimize() from
fabchem's service layer (src/fabchem/) and renders results. No Pyomo model
construction, no NRTL parameters, no cost formulas here — ever.
"""

import streamlit as st

st.set_page_config(page_title="fabchem-optimizer", layout="wide")
st.title("fabchem-optimizer")
st.caption("P0 skeleton — property model, flowsheet, and optimization land in Gates C1-C4.")

st.warning(
    "This is a placeholder page. No thermodynamic model, flowsheet, or "
    "optimization has been implemented yet. Nothing shown here is a real result."
)
