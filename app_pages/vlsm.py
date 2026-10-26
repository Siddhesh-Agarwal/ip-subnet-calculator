import io

import pandas as pd
import streamlit as st

from ipcalc import ui
from ipcalc.core import InputError, format_count_compact
from ipcalc.planner import (
    Requirement,
    allocation_rows,
    ipam_segments,
    parse_plan_payload,
    plan_payload,
    vlsm_plan,
)

ui.page_header(
    "VLSM planner",
    "Largest-first allocation inside a parent block, with free space and a plan you can reload.",
    icon=":material/account_tree:",
)

PENDING = "vlsm-pending-import"
VERSION = "vlsm-ui-version"

pending = st.session_state.pop(PENDING, None)
ui_version = int(st.session_state.get(VERSION, 0))
if pending:
    ui_version += 1
    st.session_state[VERSION] = ui_version

# A new key on import makes the text input and data editor reinitialize from
# the imported values instead of keeping their previous browser-side state.
PARENT = f"vlsm-parent-{ui_version}"
EDITOR = f"vlsm-editor-{ui_version}"

default_parent = "10.0.0.0/16"
default_rows = ui.requirements_frame()
if pending:
    default_parent = str(pending["parent"])
    default_rows = ui.requirements_frame(pending["requirements"])


def _queue_import(payload: dict) -> None:
    parent, requirements = parse_plan_payload(payload)
    st.session_state[PENDING] = {
        "parent": parent,
        "requirements": requirements,
    }


def _handle_upload(uploaded) -> None:
    fingerprint = getattr(uploaded, "file_id", None) or f"{uploaded.name}:{uploaded.size}"
    marker = "vlsm-import-marker"
    if st.session_state.get(marker) == fingerprint:
        return
    try:
        if uploaded.name.lower().endswith(".json"):
            _queue_import(ui.read_uploaded_json(uploaded))
        else:
            frame = pd.read_csv(io.BytesIO(uploaded.getvalue()))
            columns = {str(column).lower(): column for column in frame.columns}
            name_col = columns.get("name")
            hosts_col = (
                columns.get("hosts")
                or columns.get("host_count")
                or columns.get("requested")
                or columns.get("requested_hosts")
            )
            if hosts_col is None:
                raise InputError(
                    "CSV needs a 'name' column and a 'hosts' or 'host_count' column."
                )
            parent_value = st.session_state.get(PARENT, default_parent)
            parent_col = columns.get("parent")
            if parent_col is not None and len(frame):
                candidate = str(frame[parent_col].iloc[0]).strip()
                if candidate and candidate.lower() != "nan":
                    parent_value = candidate
            requirements = []
            for index, row in frame.iterrows():
                name = str(row[name_col]) if name_col is not None else f"Requirement {index + 1}"
                hosts = ui.safe_int(row[hosts_col], default=0)
                if hosts > 0:
                    requirements.append((name, hosts))
            if not requirements:
                raise InputError("No positive host counts found in the CSV.")
            _queue_import({"parent": parent_value, "requirements": [
                {"name": name, "hosts": hosts} for name, hosts in requirements
            ]})
    except InputError as exc:
        ui.input_error(exc)
        return
    st.session_state[marker] = fingerprint
    st.rerun()


with st.expander("Import a saved plan", icon=":material/upload_file:", expanded=False):
    uploaded = st.file_uploader(
        "Plan JSON or requirements CSV",
        type=["json", "csv"],
        key="vlsm-import",
        help=(
            "JSON round-trips the whole plan. CSV needs parent (optional), name, "
            "and hosts columns."
        ),
    )
    if uploaded is not None:
        _handle_upload(uploaded)

parent_text = st.text_input(
    "Parent block",
    value=default_parent,
    key=PARENT,
    icon=":material/hub:",
    help="The block that all requirements are allocated from.",
)
parsed_parent = ui.parse_one(parent_text)
if parsed_parent is None:
    st.stop()
if parsed_parent.host_bits_set:
    st.warning(
        f"Host bits set in the parent; using {parsed_parent.normalized}.",
        icon=":material/warning:",
    )
parent = parsed_parent.network

st.caption(
    "Add one row per requirement. Allocation is largest-first and next-fit; "
    "the remaining gaps are shown below the table."
)
edited = st.data_editor(
    default_rows,
    num_rows="dynamic",
    hide_index=True,
    width="stretch",
    key=EDITOR,
    column_config={
        "Name": st.column_config.TextColumn("Name", width="medium"),
        "Hosts": st.column_config.NumberColumn(
            "Hosts",
            min_value=1,
            step=1,
            format="%d",
            help="Minimum usable hosts required.",
        ),
    },
    alt="VLSM requirements editor",
)

requirements: list[Requirement] = []
for index, row in edited.iterrows():
    hosts = ui.safe_int(row.get("Hosts"), default=0)
    if hosts <= 0:
        continue
    name = str(row.get("Name") or "").strip() or f"Requirement {index + 1}"
    requirements.append(Requirement(name, hosts))

if not requirements:
    st.info("Add at least one requirement with a positive host count.", icon=":material/info:")
    st.stop()

plan = vlsm_plan(parent, requirements)

with st.container(horizontal=True):
    st.metric("Parent", str(parent), border=True)
    st.metric("Allocated", format_count_compact(plan.allocated_coverage), border=True)
    st.metric("Free", format_count_compact(plan.free_coverage), border=True)
    st.metric("Utilization", f"{plan.utilization:.1%}", border=True)

if plan.unallocated:
    st.error(
        f"{len(plan.unallocated)} requirement(s) could not be placed.",
        icon=":material/error:",
    )
    unallocated_rows = [
        {
            "name": item.name,
            "requested": format_count_compact(item.requested_hosts),
            "reason": item.note,
        }
        for item in plan.unallocated
    ]
    st.dataframe(
        ui.display_rows(unallocated_rows),
        hide_index=True,
        width="stretch",
        alt="Unallocated requirements",
    )

st.subheader("Allocations")
rows = allocation_rows(plan)
if rows:
    st.dataframe(
        ui.display_rows(rows),
        hide_index=True,
        width="stretch",
        height=min(520, 60 + len(rows) * 35),
        key="vlsm-allocations",
        alt="VLSM allocation table",
    )
else:
    st.info("Nothing was allocated.", icon=":material/info:")

st.subheader("IPAM view")
allocated = [
    (allocation.name, allocation.network)
    for allocation in plan.allocations
    if allocation.network is not None
]
segments, segment_warnings = ipam_segments(parent, allocated)
for warning in segment_warnings:
    st.warning(warning, icon=":material/warning:")
ui.render_ipam(
    segments,
    parent=parent,
    allocated_pct=plan.utilization,
    key="vlsm-ipam",
)

st.subheader("Free space")
if plan.free:
    ui.network_table(
        plan.free,
        key="vlsm-free",
        height=min(360, 60 + len(plan.free) * 35),
        alt="Free space left in the VLSM parent",
    )
else:
    st.success("No free space remains in the parent block.", icon=":material/check_circle:")

payload = plan_payload(parent, requirements, plan)
requirement_rows = [
    {"parent": str(parent), "name": requirement.name, "hosts": requirement.hosts}
    for requirement in requirements
]

export_rows = [
    {
        "parent": str(parent),
        "hosts": allocation.requested_hosts,
        **row,
    }
    for allocation, row in zip(plan.allocations, rows)
]
st.space("small")
ui.copy_and_download(
    payload=payload,
    rows=export_rows,
    key_prefix="vlsm",
    filename="vlsm-plan",
)
with st.container(horizontal=True):
    ui.download_csv(
        requirement_rows,
        "vlsm-requirements.csv",
        key="vlsm-download-requirements",
        label="Download requirements CSV",
    )
    st.caption("JSON stores the full plan; CSV stores requirements and allocations.")
