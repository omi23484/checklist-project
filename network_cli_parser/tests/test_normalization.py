import pytest
from utils.normalization import (
    normalize_command, detect_platform,
    extract_hostname, extract_collection_time, denormalize_command,
)


class TestNormalizeCommand:
    def test_basic(self):
        assert normalize_command("show ip bgp summary") == "show_ip_bgp_summary"

    def test_pipe_include(self):
        assert normalize_command("show ip bgp summary | include 65001") == "show_ip_bgp_summary_include"

    def test_pipe_exclude(self):
        assert normalize_command("show ip route | exclude Connected") == "show_ip_route_exclude"

    def test_pipe_begin(self):
        assert normalize_command("show ip route | begin 10.0.0") == "show_ip_route_begin"

    def test_hyphen_preserved(self):
        assert normalize_command("show port-channel summary") == "show_port-channel_summary"

    def test_extra_whitespace_collapsed(self):
        assert normalize_command("show  ip   bgp") == "show_ip_bgp"

    def test_uppercase_lowercased(self):
        assert normalize_command("SHOW VERSION") == "show_version"

    def test_no_pipe(self):
        assert normalize_command("show version") == "show_version"


class TestDetectPlatform:
    # --- Tier 1: filename prefix ---
    def test_n9k_prefix(self):
        assert detect_platform("N9K-CORE-1_01-Jan-26.txt", "", warn=False) == "cisco_nxos"

    def test_n7k_prefix(self):
        assert detect_platform("N7K-AGG-2.txt", "", warn=False) == "cisco_nxos"

    def test_n3k_prefix(self):
        assert detect_platform("N3K-SW.txt", "", warn=False) == "cisco_nxos"

    def test_csr_prefix(self):
        assert detect_platform("CSR1000V_01-Jan-26.txt", "", warn=False) == "cisco_iosxe"

    def test_isr_prefix(self):
        assert detect_platform("ISR4451_edge.txt", "", warn=False) == "cisco_iosxe"

    def test_asr_prefix(self):
        assert detect_platform("ASR9001-core.txt", "", warn=False) == "cisco_iosxe"

    # --- Tier 2: content keywords ---
    def test_nxos_keyword_cisco_nxos(self):
        assert detect_platform("unknown.txt", "Cisco NX-OS Software, Version 9.3(7)", warn=False) == "cisco_nxos"

    def test_nxos_keyword_nxos_software(self):
        assert detect_platform("unknown.txt", "NX-OS Software, Version 9.3(3)", warn=False) == "cisco_nxos"

    def test_iosxe_keyword_ios_xe_software(self):
        assert detect_platform("unknown.txt", "Cisco IOS XE Software, Version 17.3.2", warn=False) == "cisco_iosxe"

    def test_iosxe_keyword_ios_xe_space(self):
        assert detect_platform("unknown.txt", "IOS XE Software, Version 16.9.5", warn=False) == "cisco_iosxe"

    def test_ios_keyword(self):
        assert detect_platform("unknown.txt", "Cisco IOS Software, Version 15.4(3)M", warn=False) == "cisco_ios"

    def test_prefix_wins_over_content(self):
        # N9K prefix → cisco_nxos even if content says IOS XE
        result = detect_platform("N9K-SW.txt", "IOS XE Software", warn=False)
        assert result == "cisco_nxos"

    # --- Tier 3: prompt heuristic ---
    def test_ios_gt_prompt_heuristic(self):
        content = "Router> show version\nCisco"
        assert detect_platform("unknown.txt", content, warn=False) == "cisco_ios"

    # --- Tier 4: fallback ---
    def test_fallback_returns_cisco_ios(self):
        result = detect_platform("unknown.txt", "no useful content", warn=False)
        assert result == "cisco_ios"

    def test_fallback_prints_warning(self, capsys):
        detect_platform("mystery.txt", "", warn=True)
        captured = capsys.readouterr()
        assert "[WARN]" in captured.out
        assert "mystery.txt" in captured.out

    def test_no_warning_when_suppressed(self, capsys):
        detect_platform("mystery.txt", "", warn=False)
        captured = capsys.readouterr()
        assert "[WARN]" not in captured.out


class TestExtractHostname:
    def test_standard_filename(self):
        assert extract_hostname("N9K-CAMA-WAN-1_03-May-26.txt") == "N9K-CAMA-WAN-1"

    def test_no_timestamp(self):
        assert extract_hostname("hostname.txt") == "hostname"

    def test_with_path(self):
        assert extract_hostname("/data/raw/N9K-CORE_01-Jan-26.txt") == "N9K-CORE"

    def test_multiple_underscores_splits_on_last(self):
        assert extract_hostname("DC1_N9K_CORE_03-May-26.txt") == "DC1_N9K_CORE"


class TestExtractCollectionTime:
    def test_standard_filename(self):
        assert extract_collection_time("N9K-CAMA-WAN-1_03-May-26.txt") == "03-May-26"

    def test_no_timestamp_returns_empty(self):
        assert extract_collection_time("hostname.txt") == ""

    def test_with_path(self):
        assert extract_collection_time("/data/N9K-CORE_01-Jan-26.txt") == "01-Jan-26"


class TestDenormalizeCommand:
    def test_basic(self):
        assert denormalize_command("show_ip_bgp_summary") == "show ip bgp summary"

    def test_hyphen_preserved(self):
        assert denormalize_command("show_port-channel_summary") == "show port-channel summary"

    def test_single_word(self):
        assert denormalize_command("show_version") == "show version"
