"""Minimal Streamlit shell for the resource-allocation API."""

import streamlit as st

from api_client import ApiClient, ApiError, ApiUnreachable
from components.app_picker import render_app_picker
from components.compare_chart import render_compare_chart
from components.prediction_gauges import render_prediction_gauges

st.set_page_config(
    page_title="AI Resource Allocation Engine",
    layout="wide",
)

st.title("AI Resource Allocation Engine")

client = ApiClient()
with st.sidebar:
    st.header("API status")
    try:
        health = client.health()
    except (ApiError, ApiUnreachable) as error:
        st.error(f"API unavailable: {error}")
    else:
        if health.get("status") == "ok":
            st.success("API is online")
        else:
            st.error(f"API status: {health.get('status', 'unknown')}")
        st.write(f"Predictor: **{health.get('predictor', 'unknown')}**")

render_app_picker(client)

prediction = st.session_state.get("prediction")
if prediction:
    st.subheader(f"Prediction: {prediction['app_name']}")
    result = prediction["result"]
    render_prediction_gauges(result.get("predicted", result))
    with st.expander("Raw response"):
        st.json(result)

comparison = st.session_state.get("comparison")
if comparison:
    st.subheader(f"Run comparison: {comparison['app_name']}")
    render_compare_chart(comparison["result"])
    with st.expander("Raw comparison response"):
        st.json(comparison["result"])

history = st.session_state.get("comparison_history", [])
if history:
    with st.expander("Comparison history"):
        st.dataframe(history, hide_index=True, width="stretch")
