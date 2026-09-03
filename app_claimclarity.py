"""ClaimClarity demo UI.

Run with:  streamlit run app_claimclarity.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

from claimclarity.config import model_status
from claimclarity.pipeline import run_claim_case

st.set_page_config(page_title="ClaimClarity", page_icon="🩺", layout="wide")

EXAMPLES_DIR = Path(__file__).parent / "examples" / "claimclarity"

st.title("🩺 ClaimClarity")
st.caption(
    "An agent that reads your insurance denial, checks it against real ICD-10 coding rules "
    "and your plan's own terms, and drafts the appeal - or tells you honestly when it's not worth fighting."
)

with st.sidebar:
    st.subheader("Model")
    status = model_status()
    if status.startswith("No credentials"):
        st.error(status)
        st.caption("Set ANTHROPIC_API_KEY, or configure AWS credentials for Bedrock, then rerun.")
    else:
        st.success(status)

    st.subheader("Claim documents")
    source = st.radio(
        "Source",
        ["Use example (Maria Chen / Heartland Mutual)", "Upload files"],
        key="doc_source",
    )
    uploads = None
    if source == "Upload files":
        uploads = st.file_uploader(
            "Denial notice/EOB, and optionally a plan summary of benefits and/or medical record excerpt",
            type=["txt", "md", "pdf", "docx"],
            accept_multiple_files=True,
            key="doc_uploads",
        )

    run_clicked = st.button("Run ClaimClarity", type="primary", use_container_width=True)

if "result" not in st.session_state:
    st.session_state.result = None

if run_clicked:
    workdir = Path(tempfile.mkdtemp(prefix="claimclarity_"))

    if source.startswith("Use example"):
        document_paths = [
            str(EXAMPLES_DIR / "denial_notice.md"),
            str(EXAMPLES_DIR / "plan_summary_of_benefits.md"),
            str(EXAMPLES_DIR / "medical_record_excerpt.md"),
        ]
    elif uploads:
        document_paths = []
        for upload in uploads:
            dest = workdir / upload.name
            dest.write_bytes(upload.getvalue())
            document_paths.append(str(dest))
    else:
        document_paths = []

    if not document_paths:
        st.error("Please upload at least the denial notice/EOB, or use the example.")
    else:
        output_dir = workdir / "output"
        log_container = st.empty()
        log_lines: list[str] = []
        # Strands runs the agent (and every callback_handler invocation) on a
        # background ThreadPoolExecutor thread, which never receives
        # Streamlit's ScriptRunContext. Without re-attaching it, the first
        # st.* call from stream_callback raises NoSessionContext.
        script_ctx = get_script_run_ctx()

        def stream_callback(**kwargs):
            add_script_run_ctx(ctx=script_ctx)
            tool_use = kwargs.get("current_tool_use") or {}
            if tool_use.get("name"):
                line = f"🔧 calling `{tool_use['name']}`"
                if not log_lines or log_lines[-1] != line:
                    log_lines.append(line)
                    log_container.code("\n".join(log_lines), language=None)

        with st.spinner("ClaimClarity is analyzing the claim, checking codes, and investigating the denial..."):
            result = run_claim_case(
                documents_paths=document_paths,
                output_dir=str(output_dir),
                callback_handler=stream_callback,
            )
        st.session_state.result = result
        st.session_state.output_dir = output_dir

result = st.session_state.result

if result is not None:
    case = result.case
    worth_appealing = [f for f in (case.findings.findings if case.findings else []) if f.worth_appealing]

    if case.findings is None:
        st.warning("Run did not complete denial investigation.")
    elif worth_appealing:
        st.success(f"✅ {len(worth_appealing)} item(s) look worth appealing — a draft letter is ready for review.")
    else:
        st.info("Nothing here looks worth appealing — see the explanation for why.")

    tabs = st.tabs(
        [
            "Decisions Needed",
            "Claim Summary",
            "Denial Findings",
            "Appeal Package",
            "External Review & Escalation",
            "Agent's Own Summary (unverified)",
        ]
    )
    output_dir: Path = st.session_state.output_dir

    def _read(name: str) -> str:
        path = output_dir / name
        return path.read_text() if path.exists() else "_Not generated._"

    with tabs[0]:
        st.markdown(_read("decisions_needed.md"))
        ics_path = output_dir / "appeal_deadline.ics"
        if ics_path.exists():
            st.download_button(
                "Download appeal deadline reminder (.ics)",
                data=ics_path.read_bytes(),
                file_name="appeal_deadline.ics",
                mime="text/calendar",
            )
    with tabs[1]:
        content = _read("claim_summary.md")
        st.markdown(content)
        st.download_button("Download claim_summary.md", content, file_name="claim_summary.md")
    with tabs[2]:
        content = _read("denial_findings.md")
        st.markdown(content)
        st.download_button("Download denial_findings.md", content, file_name="denial_findings.md")
    with tabs[3]:
        content = _read("appeal_package.md")
        st.markdown(content)
        st.download_button("Download appeal_package.md", content, file_name="appeal_package.md")
    with tabs[4]:
        content = _read("escalation_package.md")
        st.markdown(content)
        st.download_button("Download escalation_package.md", content, file_name="escalation_package.md")
        review_ics_path = output_dir / "external_review_deadline.ics"
        if review_ics_path.exists():
            st.download_button(
                "Download external review deadline reminder (.ics)",
                data=review_ics_path.read_bytes(),
                file_name="external_review_deadline.ics",
                mime="text/calendar",
            )
    with tabs[5]:
        st.caption(
            "This is the orchestrator's own free-text reply, shown for transparency. "
            "It can occasionally misstate specifics even when every generated file above "
            "is correct - treat **Decisions Needed** and the generated files as the source "
            "of truth, not this tab."
        )
        st.markdown(result.summary_text)
else:
    st.info("Choose claim documents in the sidebar, then click **Run ClaimClarity**.")
