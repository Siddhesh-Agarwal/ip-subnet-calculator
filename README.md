# IP Subnet Calculator

A Streamlit workspace for network engineers: fast subnet maths, VLSM planning, VLSM/IPAM exports, reverse DNS, and the IPv6 extras that are usually scattered across tabs and blog posts.

All address maths uses Python's standard-library `ipaddress` module, so IPv6 is real 128-bit arithmetic rather than a 32-bit workaround.

## Run

```bash
uv sync
uv run streamlit run main.py
```

Then open <http://localhost:8501>.

## Tests

```bash
uv run python -m unittest discover -s tests -v
```

The tests cover the documented input forms, `/0`, `/31`, `/32`, `/127`, `/128`, prefix splitting, VLSM packing, set operations, free space, RFC 2317, EUI-64, NAT64, and comparison against `ipaddress` vectors.

## What is included

**Analyze**

- One input box with automatic detection: CIDR, dotted netmask, wildcard mask, bare IPv4/IPv6, and host-bit warnings.
- IPv4 result panel with network, broadcast, usable host range, counts, netmask, wildcard, and normalized CIDR.
- IPv6 result panel with RFC 5952 compressed/expanded forms, network start/end, `/64` count, and address classification.
- Binary view with the network/host boundary highlighted.
- RFC 1918, CGNAT, loopback, link-local, documentation, multicast, reserved, GUA, ULA, and IPv4-mapped classification.
- Click-to-copy on every result field, plus copy/download as JSON and CSV.
- Bulk mode for hundreds of pasted lines with filters and a sortable table.
- Prefix cheat sheet in the app and as a dedicated page.

**Plan**

- Subnet splitter by new prefix, subnet count, or minimum usable hosts.
- VLSM planner with largest-first packing, free-space reporting, IPAM bar, JSON/CSV export, and JSON/CSV import.
- Free-space finder that highlights the largest available block.
- IPAM map with proportional allocated/free segments.
- IPv6 site planner for `/48 → /56 → /64`.

**Operate**

- Network summarization (exact minimal set or single supernet with over-coverage warnings).
- Range ↔ CIDR conversion in both directions.
- IP membership and list-overlap checker.
- Union, intersection, and subtraction on prefix lists.
- Cisco, Juniper, Linux, ACL, and AWS/Azure/GCP cloud snippets.
- Reverse DNS with `in-addr.arpa`, `ip6.arpa`, and RFC 2317 classless delegation.
- IPv6 EUI-64/SLAAC, solicited-node multicast, and NAT64 mapping.

## Implementation notes

- `ipcalc/core.py` — parsing, host semantics, number formatting, classification.
- `ipcalc/netmath.py` — interval and prefix-list maths (union, subtract, intersect, summaries).
- `ipcalc/planner.py` — splitter, VLSM, free space, IPAM segments, plan JSON.
- `ipcalc/dns.py`, `ipcalc/generators.py`, `ipcalc/ipv6_extras.py` — the specialized helpers.
- `ipcalc/components.py` — small Custom Components v2 pieces for click-to-copy, binary bits, and the IPAM bar.
- `app_pages/` — one direct script per page, wired through `st.navigation` in `main.py`.

The calculator input is bound to the `q` query parameter, so `?q=10.0.0.0/22` is shareable.
