import ipaddress
import unittest

from ipcalc.core import (
    InputError,
    classify,
    format_count,
    host_info,
    ipv6_slash64,
    parse_input,
    parse_network_lines,
)
from ipcalc.dns import (
    ptr_records,
    reverse_pointer,
    rfc2317_snippets,
    zone_for_network,
)
from ipcalc.generators import cloud_rows, suggested_host
from ipcalc.ipv6_extras import (
    nat64_extract,
    nat64_map,
    parse_mac,
    slaac_from_mac,
    solicited_node,
)
from ipcalc.netmath import (
    covering_supernet,
    intersect_networks,
    range_to_networks,
    subtract_networks,
    summarize_networks,
    union_networks,
)
from ipcalc.planner import (
    Requirement,
    free_space,
    ipam_segments,
    prefix_for_hosts,
    split_by_count,
    split_by_hosts,
    split_by_prefix,
    vlsm_plan,
)


class ParsingTests(unittest.TestCase):
    def test_all_documented_forms(self):
        cases = {
            "10.0.0.5/24": "10.0.0.0/24",
            "10.0.0.5 255.255.255.0": "10.0.0.0/24",
            "10.0.0.5 0.0.0.255": "10.0.0.0/24",
            "10.0.0.5/255.255.255.0": "10.0.0.0/24",
            "2001:db8::1/64": "2001:db8::/64",
            "10.0.0.5": "10.0.0.5/32",
            "2001:db8::1": "2001:db8::1/128",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_input(text).normalized, expected)

    def test_host_bits_flag(self):
        self.assertTrue(parse_input("10.0.0.5/24").host_bits_set)
        self.assertFalse(parse_input("10.0.0.0/24").host_bits_set)
        self.assertFalse(parse_input("10.0.0.5/32").host_bits_set)

    def test_non_contiguous_mask(self):
        with self.assertRaises(InputError):
            parse_input("10.0.0.5 255.0.255.0")

    def test_ambiguous_wildcard_heuristics(self):
        self.assertEqual(parse_input("10.0.0.5 0.0.0.0").prefixlen, 32)
        self.assertEqual(parse_input("10.0.0.5 255.255.255.255").prefixlen, 32)

    def test_invalid_prefix_range(self):
        with self.assertRaises(InputError):
            parse_input("10.0.0.1/33")
        with self.assertRaises(InputError):
            parse_input("2001:db8::1/129")

    def test_ipv6_with_dotted_mask_rejected(self):
        with self.assertRaises(InputError):
            parse_input("2001:db8::1 255.255.255.0")

    def test_comments_and_errors_in_line_parser(self):
        networks, errors, warnings = parse_network_lines(
            "10.0.0.5/24\n# comment\n\nbad input\n2001:db8::/32\n"
        )
        self.assertEqual([str(n) for n in networks], ["10.0.0.0/24", "2001:db8::/32"])
        self.assertEqual(len(errors), 1)
        self.assertEqual(len(warnings), 1)


class HostCountTests(unittest.TestCase):
    def test_ipv4_corner_cases(self):
        self.assertEqual(host_info(ipaddress.ip_network("10.0.0.0/31")).usable, 2)
        self.assertEqual(host_info(ipaddress.ip_network("10.0.0.1/32")).usable, 1)
        self.assertEqual(host_info(ipaddress.ip_network("10.0.0.0/30")).usable, 2)
        self.assertEqual(host_info(ipaddress.ip_network("0.0.0.0/0")).usable, 2**32 - 2)

    def test_broadcast_is_empty_for_31_and_32(self):
        from ipcalc.core import format_network_row

        self.assertEqual(format_network_row(ipaddress.ip_network("10.0.0.0/31"))["broadcast"], "")
        self.assertEqual(format_network_row(ipaddress.ip_network("10.0.0.1/32"))["broadcast"], "")
        self.assertEqual(
            format_network_row(ipaddress.ip_network("10.0.0.0/30"))["broadcast"],
            "10.0.0.3",
        )

    def test_ipv6_corner_cases(self):
        self.assertEqual(host_info(ipaddress.ip_network("2001:db8::/127")).usable, 2)
        self.assertEqual(host_info(ipaddress.ip_network("2001:db8::1/128")).usable, 1)
        self.assertEqual(host_info(ipaddress.ip_network("2001:db8::/64")).usable, 2**64)

    def test_number_formatting(self):
        self.assertEqual(format_count(2**64), "2^64 = 18,446,744,073,709,551,616")
        self.assertEqual(format_count(254), "254")
        self.assertIn("2^16", ipv6_slash64(48)[1])
        self.assertIn("of a /64", ipv6_slash64(65)[1])

    def test_matches_ipaddress_for_every_ipv4_prefix(self):
        for prefix in range(33):
            network = ipaddress.ip_network((ipaddress.IPv4Address(0), prefix))
            info = host_info(network)
            self.assertEqual(info.total, network.num_addresses)
            if prefix <= 30:
                self.assertEqual(info.usable, network.num_addresses - 2)


class SplitterTests(unittest.TestCase):
    def test_split_by_prefix(self):
        networks = split_by_prefix(ipaddress.ip_network("10.0.0.0/24"), 26)
        self.assertEqual(len(networks), 4)
        self.assertEqual(str(networks[-1]), "10.0.0.192/26")

    def test_split_by_count_rounds_up(self):
        result = split_by_count(ipaddress.ip_network("10.0.0.0/24"), 3)
        self.assertEqual(len(result.networks), 4)
        self.assertIn("rounded up", result.note)

    def test_split_by_hosts_uses_rfc3021_for_two(self):
        result = split_by_hosts(ipaddress.ip_network("10.0.0.0/24"), 2)
        self.assertEqual(result.new_prefix, 31)
        self.assertEqual(len(result.networks), 128)

    def test_prefix_for_hosts(self):
        self.assertEqual(prefix_for_hosts(1, 4)[0], 32)
        self.assertEqual(prefix_for_hosts(2, 4)[0], 31)
        self.assertEqual(prefix_for_hosts(3, 4)[0], 29)
        self.assertEqual(prefix_for_hosts(254, 4)[0], 24)
        self.assertEqual(prefix_for_hosts(1, 6)[0], 128)

    def test_v6_split(self):
        networks = split_by_prefix(ipaddress.ip_network("2001:db8::/48"), 56)
        self.assertEqual(len(networks), 256)
        self.assertEqual(str(networks[1]), "2001:db8:0:100::/56")


class VLSMTests(unittest.TestCase):
    def test_largest_first_packing(self):
        plan = vlsm_plan(
            ipaddress.ip_network("10.0.0.0/24"),
            [
                Requirement("small", 2),
                Requirement("large", 100),
                Requirement("medium", 50),
                Requirement("tiny", 20),
            ],
        )
        allocated = [str(item.network) for item in plan.allocations]
        self.assertEqual(
            allocated,
            ["10.0.0.0/25", "10.0.0.128/26", "10.0.0.192/27", "10.0.0.224/31"],
        )
        self.assertGreater(plan.free_coverage, 0)

    def test_unallocated_when_no_space(self):
        plan = vlsm_plan(
            ipaddress.ip_network("10.0.0.0/24"),
            [Requirement("too big", 200), Requirement("also big", 200)],
        )
        self.assertEqual(len(plan.allocations), 1)
        self.assertEqual(len(plan.unallocated), 1)

    def test_ipv6_vlsm(self):
        plan = vlsm_plan(
            ipaddress.ip_network("2001:db8::/48"),
            [Requirement("site", 2**64)],
        )
        self.assertEqual(str(plan.allocations[0].network), "2001:db8::/64")


class NetmathTests(unittest.TestCase):
    def test_summarize_exact(self):
        networks = [
            ipaddress.ip_network("10.0.0.0/25"),
            ipaddress.ip_network("10.0.0.128/25"),
        ]
        summary = summarize_networks(networks)
        self.assertEqual([str(n) for n in summary["networks"]], ["10.0.0.0/24"])
        self.assertEqual(summary["extra_count"], 0)

    def test_supernet_extra_space_detected(self):
        networks = [
            ipaddress.ip_network("10.0.0.0/24"),
            ipaddress.ip_network("10.0.2.0/24"),
        ]
        supernet = covering_supernet(networks)
        self.assertEqual(str(supernet), "10.0.0.0/22")
        extra = subtract_networks([supernet], networks)
        self.assertEqual(sum(n.num_addresses for n in extra), 512)

    def test_union_intersect_subtract(self):
        left = [ipaddress.ip_network("10.0.0.0/24"), ipaddress.ip_network("10.0.1.0/24")]
        right = [ipaddress.ip_network("10.0.0.128/25"), ipaddress.ip_network("10.0.2.0/24")]
        union = union_networks(left, right)
        self.assertEqual(
            [str(n) for n in union],
            ["10.0.0.0/23", "10.0.2.0/24"],
        )
        intersection = intersect_networks(left, right)
        self.assertEqual([str(n) for n in intersection], ["10.0.0.128/25"])
        remainder = subtract_networks(left, right)
        self.assertEqual(
            [str(n) for n in remainder],
            ["10.0.0.0/25", "10.0.1.0/24"],
        )

    def test_range_to_cidrs(self):
        networks = range_to_networks(
            ipaddress.IPv4Address("10.0.0.5"),
            ipaddress.IPv4Address("10.0.3.200"),
        )
        self.assertEqual(networks[0], ipaddress.ip_network("10.0.0.5/32"))
        self.assertEqual(networks[-1], ipaddress.ip_network("10.0.3.200/32"))
        self.assertEqual(
            sum(network.num_addresses for network in networks),
            int(ipaddress.IPv4Address("10.0.3.200")) - int(ipaddress.IPv4Address("10.0.0.5")) + 1,
        )

    def test_free_space_and_ipam(self):
        parent = ipaddress.ip_network("10.0.0.0/24")
        gaps, warnings = free_space(
            parent,
            [
                ipaddress.ip_network("10.0.0.0/26"),
                ipaddress.ip_network("10.0.0.64/26"),
            ],
        )
        self.assertEqual([str(n) for n in gaps], ["10.0.0.128/25"])
        self.assertEqual(warnings, [])
        segments, _ = ipam_segments(
            parent,
            [("a", ipaddress.ip_network("10.0.0.0/26")), ("b", ipaddress.ip_network("10.0.0.64/26"))],
        )
        allocated = sum(segment.width_pct for segment in segments if segment.kind == "allocated")
        self.assertAlmostEqual(allocated, 50.0, places=6)


class ClassificationTests(unittest.TestCase):
    def test_ipv4_classes(self):
        self.assertEqual(classify(ipaddress.ip_address("10.1.2.3"))[0].label, "RFC 1918 private")
        self.assertEqual(classify(ipaddress.ip_address("100.64.0.1"))[0].label, "CGNAT")
        self.assertEqual(classify(ipaddress.ip_address("127.0.0.1"))[0].label, "Loopback")
        self.assertEqual(classify(ipaddress.ip_address("169.254.1.1"))[0].label, "Link-local")
        self.assertEqual(classify(ipaddress.ip_address("192.0.2.1"))[0].label, "Documentation")
        self.assertEqual(classify(ipaddress.ip_address("233.252.0.1"))[0].label, "Documentation multicast")

    def test_ipv6_classes(self):
        self.assertEqual(classify(ipaddress.ip_address("2001:db8::1"))[0].label, "Documentation")
        self.assertEqual(classify(ipaddress.ip_address("fc00::1"))[0].label, "ULA")
        self.assertEqual(classify(ipaddress.ip_address("fe80::1"))[0].label, "Link-local")
        self.assertEqual(classify(ipaddress.ip_address("ff02::1"))[0].label, "Multicast")
        self.assertEqual(classify(ipaddress.ip_address("::ffff:192.0.2.1"))[0].label, "IPv4-mapped")
        self.assertEqual(classify(ipaddress.ip_address("2606:4700::1111"))[0].label, "GUA")


class DNSTests(unittest.TestCase):
    def test_ipv4_pointer(self):
        self.assertEqual(
            reverse_pointer(ipaddress.ip_address("192.0.2.1")),
            "1.2.0.192.in-addr.arpa",
        )

    def test_ipv6_pointer(self):
        self.assertEqual(
            reverse_pointer(ipaddress.ip_address("2001:db8::1")),
            "1.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa",
        )

    def test_octet_aligned_zone(self):
        info = zone_for_network(ipaddress.ip_network("192.0.2.0/24"))
        self.assertEqual(info.zone, "2.0.192.in-addr.arpa")
        self.assertTrue(info.aligned)

    def test_rfc2317_zone_and_records(self):
        info = zone_for_network(ipaddress.ip_network("192.0.2.0/25"))
        self.assertEqual(info.zone, "0/25.2.0.192.in-addr.arpa")
        self.assertTrue(info.rfc2317)
        parent, child = rfc2317_snippets(ipaddress.ip_network("192.0.2.0/25"))
        self.assertIn("$GENERATE 0-127", parent)
        self.assertIn("$ORIGIN 0/25.2.0.192.in-addr.arpa.", child)
        self.assertIn("PTR", child)

    def test_ipv6_nibble_zone(self):
        info = zone_for_network(ipaddress.ip_network("2001:db8::/32"))
        self.assertEqual(
            info.zone,
            "8.b.d.0.1.0.0.2.ip6.arpa",
        )
        self.assertTrue(info.aligned)

    def test_ptr_records(self):
        records = ptr_records(ipaddress.ip_network("192.0.2.0/30"), "example.com")
        self.assertEqual(len(records), 4)
        self.assertEqual(records[0]["pointer"], "0.2.0.192.in-addr.arpa")
        self.assertTrue(records[0]["target"].endswith(".example.com."))


class GeneratorTests(unittest.TestCase):
    def test_suggested_host(self):
        self.assertEqual(suggested_host(parse_input("10.0.0.0/24")), "10.0.0.1")
        self.assertEqual(suggested_host(parse_input("10.0.0.0/31")), "10.0.0.0")
        self.assertEqual(suggested_host(parse_input("2001:db8::/64")), "2001:db8::1")

    def test_cloud_rules(self):
        rows = cloud_rows(parse_input("10.0.0.0/24"))
        providers = {row["provider"]: row for row in rows}
        self.assertEqual(providers["AWS"]["first_usable"], "10.0.0.4")
        self.assertEqual(providers["GCP"]["first_usable"], "10.0.0.2")
        self.assertEqual(providers["GCP"]["last_usable"], "10.0.0.253")

    def test_cloud_rules_reject_tiny_subnet(self):
        rows = cloud_rows(parse_input("10.0.0.0/30"))
        self.assertTrue(all(row["supported"] == "No" for row in rows))


class IPv6ExtraTests(unittest.TestCase):
    def test_eui64_and_slaac(self):
        mac = parse_mac("00:1a:2b:3c:4d:5e")
        result = slaac_from_mac(ipaddress.ip_network("2001:db8:1234:5678::/64"), mac)
        self.assertEqual(result.interface_id, "021a:2bff:fe3c:4d5e")
        self.assertEqual(
            str(result.address), "2001:db8:1234:5678:21a:2bff:fe3c:4d5e"
        )
        self.assertEqual(str(result.link_local), "fe80::21a:2bff:fe3c:4d5e")

    def test_solicited_node(self):
        multicast = solicited_node(ipaddress.IPv6Address("2001:db8::1"))
        self.assertEqual(str(multicast), "ff02::1:ff00:1")

    def test_nat64_round_trip(self):
        prefix = ipaddress.ip_network("64:ff9b::/96")
        mapped = nat64_map(ipaddress.IPv4Address("192.0.2.33"), prefix)
        self.assertEqual(str(mapped), "64:ff9b::c000:221")
        self.assertEqual(str(nat64_extract(mapped, prefix)), "192.0.2.33")


if __name__ == "__main__":
    unittest.main()


class BulkAndPlanTests(unittest.TestCase):
    def test_bulk_rows(self):
        from ipcalc.core import bulk_rows

        rows, errors = bulk_rows("10.0.0.5/24\nnot-an-ip\n2001:db8::1/64\n")
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(errors), 1)
        self.assertEqual(rows[0]["status"], "normalized")
        self.assertEqual(rows[1]["status"], "error")
        self.assertEqual(rows[2]["family"], "IPv6")

    def test_plan_json_round_trip(self):
        from ipcalc.planner import (
            Requirement,
            parse_plan_payload,
            plan_payload,
            vlsm_plan,
        )

        parent = ipaddress.ip_network("10.0.0.0/24")
        requirements = [Requirement("core", 100), Requirement("access", 50)]
        plan = vlsm_plan(parent, requirements)
        payload = plan_payload(parent, requirements, plan)
        parsed_parent, parsed_requirements = parse_plan_payload(payload)
        self.assertEqual(parsed_parent, "10.0.0.0/24")
        self.assertEqual(parsed_requirements, [("core", 100), ("access", 50)])

    def test_site_plan(self):
        from ipcalc.planner import site_plan

        parent = ipaddress.ip_network("2001:db8:1000::/48")
        plan = site_plan(parent, [("HQ", ipaddress.ip_network("2001:db8:1000::/56"))])
        self.assertEqual(plan["total_sites"], 256)
        self.assertEqual(plan["used_sites"], 1)
        self.assertEqual(plan["free_sites"], 255)
        self.assertEqual(plan["total_slash64"], 65536)

    def test_ipam_overlap_clipping(self):
        parent = ipaddress.ip_network("10.0.0.0/24")
        segments, warnings = ipam_segments(
            parent,
            [
                ("a", ipaddress.ip_network("10.0.0.0/25")),
                ("b", ipaddress.ip_network("10.0.0.64/26")),
            ],
        )
        self.assertTrue(any("overlaps" in warning for warning in warnings))
        allocated = sum(segment.width_pct for segment in segments if segment.kind == "allocated")
        self.assertAlmostEqual(allocated, 50.0, places=6)


class IPv6VectorTests(unittest.TestCase):
    def test_ipv6_known_vectors(self):
        vectors = {
            "::/0": 2**128,
            "2001:db8::/32": 2**96,
            "2001:db8::/64": 2**64,
            "2001:db8::/127": 2,
            "2001:db8::1/128": 1,
        }
        for cidr, expected in vectors.items():
            with self.subTest(cidr=cidr):
                network = ipaddress.ip_network(cidr)
                self.assertEqual(network.num_addresses, expected)
                self.assertEqual(host_info(network).total, expected)
                self.assertEqual(host_info(network).usable, expected)

    def test_ipv6_range_round_trip(self):
        start = ipaddress.IPv6Address("2001:db8::1")
        end = ipaddress.IPv6Address("2001:db8::ffff")
        networks = range_to_networks(start, end)
        self.assertEqual(networks[0], ipaddress.ip_network("2001:db8::1/128"))
        self.assertEqual(networks[-1], ipaddress.ip_network("2001:db8::8000/113"))
        self.assertEqual(
            sum(network.num_addresses for network in networks),
            int(end) - int(start) + 1,
        )

    def test_ipv6_zone_at_64(self):
        info = zone_for_network(ipaddress.ip_network("2001:db8:1234:5678::/64"))
        self.assertTrue(info.aligned)
        self.assertEqual(
            info.zone,
            "8.7.6.5.4.3.2.1.8.b.d.0.1.0.0.2.ip6.arpa",
        )

    def test_pointer_round_trip(self):
        from ipcalc.dns import address_from_pointer

        for address in (
            ipaddress.ip_address("192.0.2.1"),
            ipaddress.ip_address("2001:db8::1"),
        ):
            self.assertEqual(address_from_pointer(reverse_pointer(address)), address)
