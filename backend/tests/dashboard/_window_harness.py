from __future__ import annotations

import streamlit as st

# Generic window harness for AppTest. The test seeds st.session_state["window"]
# and st.session_state["data"] before calling .run().

window = st.session_state.get("window")
data = st.session_state.get("data")

if window == "home":
    from plutus.dashboard.windows.home import render

    render(data)
elif window == "signals":
    from plutus.dashboard.windows.signals import render as render_signals

    render_signals(data)
elif window == "positions":
    from plutus.dashboard.windows.positions import render as render_positions

    render_positions(data)
elif window == "candidates":
    from plutus.dashboard.windows.candidates import render as render_candidates

    render_candidates(data)
elif window == "tranches":
    from plutus.dashboard.windows.tranches import render as render_tranches

    render_tranches(data)
elif window == "postmortem":
    from plutus.dashboard.windows.postmortem import render as render_postmortem

    render_postmortem(data)
elif window == "calibration":
    from plutus.dashboard.windows.calibration import render as render_calibration

    render_calibration(data)
elif window == "strategy_lab":
    from plutus.dashboard.windows.strategy_lab import render as render_lab

    render_lab(data)
elif window == "user_flow":
    from plutus.dashboard.windows.user_flow import render as render_user_flow

    render_user_flow(data)
elif window == "settings":
    from plutus.dashboard.windows.settings import render as render_settings

    render_settings(data)
elif window == "glossary":
    from plutus.dashboard.windows.glossary import render as render_glossary

    render_glossary(data)
