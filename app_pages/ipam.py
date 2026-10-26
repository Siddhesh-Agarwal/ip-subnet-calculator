import io
import json

import pandas as pd
import streamlit as st

from ipcalc import ui
from ipcalc.core import InputError, format_count
from ipcalc.netmath import coverage
from ipcalc.planner import (
    allocation_rows,
    ipam_segments,
    parse_plan_payload,
    plan_allocation_rows,
)

ui.page_header(
    "IPAM map",
    "A proportional map of how a parent block is divided, plus the free gaps.",
    icon=":material/bar_chart:",
)

PENDING = "ipam-pending-import"
PARENT = "ipam-parent"
EDITOR = "ipam-editor"

pending = st.session_state.pop(PENDING, None)
default_parent = "10.0.0.0/16"
default_rows = ui.allocations_frame()
if pending:
    default_parent = str(pending["parent"])
    default_rows = ui.allocations_frame(pending["allocations"])
    st.session_state.pop(PARENT, None)
    st.session_state.pop(EDITOR, None)


def _queue_import(payload: dict) -> None:
    parent, _requirements = parse_plan_payload(payload)
    rows = plan_allocation_rows(payload)
    allocations = [
        (row["name"] or row["cidr"], row["cidr"])
        for row in rows
        if row.get("cidr")
    ]
    st.session_state[PENDING] = {"parent": parent, "allocations": allocations}


def _handle_upload(uploaded) -> None:
    fingerprint = getattr(uploaded, "file_id", None) or f"{uploaded.name}:{uploaded.size}"
    marker = "ipam-import-marker"
    if st.session_state.get(marker) == fingerprint:
        return
    try:
        if uploaded.name.lower().endswith(".json"):
            _queue_import(ui.read_uploaded_json(uploaded))
        else:
            frame = pd.read_csv(io.BytesIO(uploaded.getvalue()))
            columns = {str(column).lower(): column for column in frame.columns}
            cidr_col = columns.get("cidr")
            if cidr_col is None:
                raise InputError("CSV needs a 'cidr' column (and optionally 'name').")
            name_col = columns.get("name")
            parent_col = columns.get("parent")
            parent_value = default_parent
            if parent_col is not None and len(frame):
                candidate = str(frame[parent_col].iloc[0]).strip()
                if candidate and candidate.lower() != "nan":
                    parent_value = candidate
            allocations = []
            for index, row in frame.iterrows():
                cidr = str(row[cidr_col]).strip()
                if not cidr or cidr.lower() == "nan":
                    continue
                name = str(row[name_col]).strip() if name_col is not None else ""
                allocations.append((name or cidr, cidr))
            if not allocations:
                raise InputError("No CIDR rows found in the CSV.")
            st.session_state[PENDING] = {
                "parent": parent_value,
                "allocations": allocations,
            }
    except InputError as exc:
        ui.input_error(exc)
        return
    st.session_state[marker] = fingerprint
    st.rerun()


with st.expander("Import a saved plan", icon=":material/upload_file:", expanded=False):
    uploaded = st.file_uploader(
        "Plan JSON or allocations CSV",
        type=["json", "csv"],
        key="ipam-import",
        help="JSON plans from the VLSM planner can be loaded directly.",
    )
    if uploaded is not None:
        _handle_upload(uploaded)

parent_text = st.text_input(
    "Parent block",
    value=default_parent,
    key=PARENT,
    icon=":material/hub:",
)
parsed = ui.parse_one(parent_text)
if parsed is None:
    st.stop()
parent = parsed.network

edited = st.data_editor(
    default_rows,
    num_rows="dynamic",
    hide_index=True,
    width="stretch",
    key=EDITOR,
    column_config={
        "Name": st.column_config.TextColumn("Name", width="medium"),
        "CIDR": st.column_config.TextColumn("CIDR", width="medium"),
    },
    alt="IPAM allocation editor",
)

allocations: list[tuple[str, object]] = []
for index, row in edited.iterrows():
    cidr = str(row.get("CIDR") or "").strip()
    if not cidr or cidr.lower() == "nan":
        continue
    name = str(row.get("Name") or "").strip()
    try:
        network = ui.parse_one(cidr)
    except Exception:  # ui.parse_one already reports the error
        continue
    if network is None:
        continue
    allocations.append((name or str(network.network), network.network))

if not allocations:
    st.info("Add at least one allocation CIDR.", icon=":material/info:")
    st.stop()

segments, warnings = ipam_segments(parent, allocations)
for warning in warnings:
    st.warning(warning, icon=":material/warning:")

allocated_networks = [
    network for _, network in allocations if network.version == parent.version and network.subnet_of(parent)
]
allocated_coverage = coverage(allocated_networks)
utilization = allocated_coverage / parent.num_addresses if parent.num_addresses else 0.0

with st.container(horizontal=True):
    st.metric("Parent", str(parent), border=True)
    st.metric("Allocated", format_count(allocated_coverage), border=True)
    st.metric("Allocations", f"{len(allocations):,}", border=True)
    st.metric("Utilization", f"{utilization:.1%}", border=True)

st.space("small")
ui.render_ipam(segments, parent=parent, allocated_pct=utilization, key="ipam-bar")

rows: list[dict[str, str]] = []
for name, network in allocations:
    rows.append(
        {
            "kind": "Allocated",
            "name": name,
            "cidr": str(network),
            "addresses": format_count(network.num_addresses),
        }
    )
for segment in segments:
    if segment.kind == "free":
        rows.append(
            {
                "kind": "Free",
                "name": "Free",
                "cidr": str(segment.network),
                "addresses": format_count(segment.addresses),
            }
        )

st.subheader("Allocation map")
st.dataframe(
    ui.display_rows(rows),
    hide_index=True,
    width="stretch",
    height=min(520, 60 + len(rows) * 35),
    key="ipam-table",
    alt="IPAM allocation and free-space table",
)

payload = {
    "schema": "ip-subnet-calculator/ipam/v1",
    "parent": str(parent),
    "allocations": [
        {"name": name, "cidr": str(network)} for name, network in allocations
    ],
    "free": [str(segment.network) for segment in segments if segment.kind == "free"],
}
st.space("small")
ui.copy_and_download(
    payload=payload,
    rows=rows,
    key_prefix="ipam",
    filename="ipam-plan",
)
