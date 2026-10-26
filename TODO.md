# Feature List

- [ ] Single input box that auto-detects the format: 10.0.0.5/24, 10.0.0.5 255.255.255.0, 10.0.0.5 0.0.0.255, 2001:db8::1/64, or a bare IP
- [ ] Result panel for IPv4: network, broadcast, first and last usable host, usable and total counts, mask, wildcard, and the normalized CIDR. Handle /31 (RFC 3021) and /32 correctly
- [ ] Result panel for IPv6: compressed and expanded forms (RFC 5952), network start and end, number of /64s, and address type (GUA, ULA, link-local, multicast, IPv4-mapped)
- [ ] Binary view with the network/host boundary highlighted
- [ ] Address classification: RFC 1918, CGNAT, loopback, link-local, documentation, multicast, reserved
- [ ] Click-to-copy on every field, plus a "copy as JSON/CSV" button
- [ ] Clear validation errors, such as non-contiguous masks, and a warning when host bits are set in the input Core engineer tools
- [ ] Subnet splitter: split by prefix, by number of subnets, or by minimum hosts, with a table of results that can be exported
- [ ] VLSM planner: enter a parent block and a list of requirements (name, host count) and get a packed allocation, largest first, with remaining free space shown. Support both v4 and v6
- [ ] Summarization: aggregate a list of networks into the minimal covering set, and flag when a summary covers extra space
- [ ] Range ↔ CIDR conversion: 10.0.0.5–10.0.3.200 to the minimal CIDR list, and the reverse
- [ ] Contains/overlap checker: is IP X in network Y, and do these lists overlap? This is a common firewall-audit task
- [ ] Bulk mode: paste hundreds of lines and get a sortable, filterable table
- [ ] Set operations on prefix lists: union, subtract, and intersect, for building allowlists and finding what's left of a block
- [ ] Free-space finder: parent block plus used subnets gives the available gaps, with the largest free block highlighted
- [ ] IPAM-style visual map: a bar or tree showing how a parent block is divided, with colors for allocated and free space
- [ ] Config generators: Cisco/Juniper/Linux (ip addr) snippets, ACL wildcard entries, and cloud formats (AWS/Azure/GCP VPC subnet reserved-address rules)
- [ ] Reverse DNS helper: in-addr.arpa and ip6.arpa zone and PTR names, including RFC 2317 classless delegation
- [ ] IPv6 extras: EUI-64 from MAC, solicited-node multicast address, NAT64 (64:ff9b::/96) mapping, and a /48 → /56 → /64 site planner
- [ ] Planner export and import: save a plan as JSON or CSV, and reload it later

UX details that matter to this audience

- [ ] Shareable URLs (?q=10.0.0.0/22) so engineers can paste results into tickets and chat
- [ ] Prefix cheat sheet (prefix → mask → hosts, and v6 prefix sizes) in a collapsible panel

Correctness

- [ ] Use a proper library for IPv6 (128-bit) math, since plain numbers will break
- [ ] Test against known vectors, including /0, /31, /32, /127, /128, and compare outputs with Python's ipaddress and ipcalc
- [ ] Make the number-format rules explicit: usable hosts for /31 and /32, and whether a v6 /64 count is shown as a power of two rather than a huge integer Architecture note
