"""BidWright demo UI.

Run with:  streamlit run app_streamlit.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from bidwright.config import model_status
from bidwright.pipeline import run_bid_job

st.set_page_config(page_title="BidWright", page_icon="📋", layout="wide")

EXAMPLES_DIR = Path(__file__).parent / "examples"

st.title("📋 BidWright")
st.caption("An RFP compliance & proposal-drafting agent for small contractors and business owners.")

with st.sidebar:
    st.subheader("Model")
    status = model_status()
    if status.startswith("No credentials"):
        st.error(status)
        st.caption("Set ANTHROPIC_API_KEY, or configure AWS credentials for Bedrock, then rerun.")
    else:
        st.success(status)

    st.subheader("1. RFP document")
    rfp_source = st.radio("Source", ["Use example (Rivertown RFP)", "Upload a file"], key="rfp_source")
    rfp_upload = None
    if rfp_source == "Upload a file":
        rfp_upload = st.file_uploader("RFP file", type=["txt", "md", "pdf", "docx"], key="rfp_upload")

    st.subheader("2. Company profile")
    profile_source = st.radio(
        "Source", ["Use example (GreenPath Grounds)", "Upload a file"], key="profile_source"
    )
    profile_upload = None
    if profile_source == "Upload a file":
        profile_upload = st.file_uploader(
            "Company profile file", type=["txt", "md", "json"], key="profile_upload"
        )

    run_clicked = st.button("Run BidWright", type="primary", use_container_width=True)


def _resolve_input(source_label: str, upload, example_path: Path, workdir: Path) -> str | None:
    if source_label.startswith("Use example"):
        return str(example_path)
    if upload is not None:
        dest = workdir / upload.name
        dest.write_bytes(upload.getvalue())
        return str(dest)
    return None


if "result" not in st.session_state:
    st.session_state.result = None

if run_clicked:
    workdir = Path(tempfile.mkdtemp(prefix="bidwright_"))
    rfp_path = _resolve_input(rfp_source, rfp_upload, EXAMPLES_DIR / "sample_rfp.md", workdir)
    profile_path = _resolve_input(
        profile_source, profile_upload, EXAMPLES_DIR / "company_profile.json", workdir
    )

    if rfp_path is None or profile_path is None:
        st.error("Please provide both an RFP document and a company profile.")
    else:
        output_dir = workdir / "output"
        log_container = st.empty()
        log_lines: list[str] = []

        def stream_callback(**kwargs):
            tool_use = kwargs.get("current_tool_use") or {}
            if tool_use.get("name"):
                line = f"🔧 calling `{tool_use['name']}`"
                if not log_lines or log_lines[-1] != line:
                    log_lines.append(line)
                    log_container.code("\n".join(log_lines), language=None)

        with st.spinner("BidWright is analyzing the RFP, checking compliance, and drafting the proposal..."):
            result = run_bid_job(
                rfp_path=rfp_path,
                profile_path=profile_path,
                output_dir=str(output_dir),
                callback_handler=stream_callback,
            )
        st.session_state.result = result
        st.session_state.output_dir = output_dir

result = st.session_state.result

if result is not None:
    job = result.job
    blocking = [g for g in (job.compliance.gaps if job.compliance else []) if g.severity.value == "blocking"]

    if job.compliance is None:
        st.warning("Run did not complete compliance checking.")
    elif blocking:
        st.error(f"⚠️ {len(blocking)} blocking gap(s) found — this bid is NOT ready to submit yet.")
    else:
        st.success("✅ No blocking gaps found — this bid is ready for final human review.")

    tabs = st.tabs(["Decisions Needed", "Requirements", "Compliance Report", "Proposal Draft", "Agent Summary"])
    output_dir: Path = st.session_state.output_dir

    def _read(name: str) -> str:
        path = output_dir / name
        return path.read_text() if path.exists() else "_Not generated._"

    with tabs[0]:
        st.markdown(_read("decisions_needed.md"))
        ics_path = output_dir / "submission_deadline.ics"
        if ics_path.exists():
            st.download_button(
                "Download deadline reminder (.ics)",
                data=ics_path.read_bytes(),
                file_name="submission_deadline.ics",
                mime="text/calendar",
            )
    with tabs[1]:
        content = _read("requirements.md")
        st.markdown(content)
        st.download_button("Download requirements.md", content, file_name="requirements.md")
    with tabs[2]:
        content = _read("compliance_report.md")
        st.markdown(content)
        st.download_button("Download compliance_report.md", content, file_name="compliance_report.md")
    with tabs[3]:
        content = _read("proposal_draft.md")
        st.markdown(content)
        st.download_button("Download proposal_draft.md", content, file_name="proposal_draft.md")
    with tabs[4]:
        st.markdown(result.summary_text)
else:
    st.info("Configure an RFP and company profile in the sidebar, then click **Run BidWright**.")
