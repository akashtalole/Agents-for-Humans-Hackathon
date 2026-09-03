"""GlacierWatch demo UI.

Run with:  streamlit run app_glacierwatch.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

from glacierwatch.config import model_status
from glacierwatch.pipeline import run_watchlist
from glacierwatch.rendering import DISCLAIMER

st.set_page_config(page_title="GlacierWatch", page_icon="🏔️", layout="wide")

st.title("🏔️ GlacierWatch")
st.caption(
    "Combines published, cited Himalayan glacial-hazard assessments with live weather and "
    "seismic data to prioritize monitoring attention this week."
)
st.warning(DISCLAIMER)

with st.sidebar:
    st.subheader("Model")
    status = model_status()
    if status.startswith("No credentials"):
        st.error(status)
        st.caption("Set ANTHROPIC_API_KEY, or configure AWS credentials for Bedrock, then rerun.")
    else:
        st.success(status)

    st.subheader("Reference watchlist")
    st.caption(
        "GlacierWatch runs against a small, cited set of documented Himalayan glacial hazard "
        "sites bundled with this tool - see glacierwatch/data/watchlist.json. It fetches live "
        "weather (Open-Meteo) and seismic (USGS) data for each site at run time."
    )

    run_clicked = st.button("Run GlacierWatch", type="primary", use_container_width=True)

if "result" not in st.session_state:
    st.session_state.result = None

if run_clicked:
    workdir = Path(tempfile.mkdtemp(prefix="glacierwatch_"))
    output_dir = workdir / "output"
    log_container = st.empty()
    log_lines: list[str] = []
    # Strands runs the agent (and every callback_handler invocation) on a
    # background ThreadPoolExecutor thread, which never receives Streamlit's
    # ScriptRunContext. Without re-attaching it, the first st.* call from
    # stream_callback raises NoSessionContext.
    script_ctx = get_script_run_ctx()

    def stream_callback(**kwargs):
        add_script_run_ctx(ctx=script_ctx)
        tool_use = kwargs.get("current_tool_use") or {}
        if tool_use.get("name"):
            line = f"🔧 calling `{tool_use['name']}`"
            if not log_lines or log_lines[-1] != line:
                log_lines.append(line)
                log_container.code("\n".join(log_lines), language=None)

    with st.spinner("GlacierWatch is loading sites, fetching live conditions, and assessing priority..."):
        result = run_watchlist(output_dir=str(output_dir), callback_handler=stream_callback)
    st.session_state.result = result
    st.session_state.output_dir = output_dir

result = st.session_state.result

if result is not None:
    run = result.run
    priority_sites = [b for b in run.briefs if b.priority_level.value == "priority"]

    if run.report is None:
        st.warning("Run did not complete.")
    elif priority_sites:
        st.error(f"🔴 {len(priority_sites)} site(s) at PRIORITY level this week — see below.")
    else:
        st.success("🟢 No sites at priority level this week.")

    tabs = st.tabs(["Weekly Watchlist", "Site Profiles", "Current Conditions", "Agent's Own Summary (unverified)"])
    output_dir: Path = st.session_state.output_dir

    def _read(name: str) -> str:
        path = output_dir / name
        return path.read_text() if path.exists() else "_Not generated._"

    with tabs[0]:
        content = _read("watchlist_report.md")
        st.markdown(content)
        st.download_button("Download watchlist_report.md", content, file_name="watchlist_report.md")
    with tabs[1]:
        for site in run.sites:
            st.markdown(_read(f"site_profile_{site.id}.md"))
            st.divider()
    with tabs[2]:
        active_sites = [s for s in run.sites if s.status == "active_watch"]
        if not active_sites:
            st.info("No active_watch sites in this run.")
        for site in active_sites:
            content = _read(f"site_conditions_{site.id}.md")
            if content != "_Not generated._":
                st.markdown(f"### {site.name}")
                st.markdown(content)
                st.divider()
    with tabs[3]:
        st.caption(
            "This is the orchestrator's own free-text reply, shown for transparency. "
            "It can occasionally misstate specifics even when every generated file above "
            "is correct - treat **Weekly Watchlist** as the source of truth, not this tab."
        )
        st.markdown(result.summary_text)
else:
    st.info("Click **Run GlacierWatch** in the sidebar to generate this week's watchlist.")
