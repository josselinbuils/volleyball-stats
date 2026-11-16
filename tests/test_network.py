import json

from volleyball_stats import network
from volleyball_stats.network import mirrored_config, named_here
from volleyball_stats.review import same_site


def test_off_by_default_and_switched(tmp_path):
    assert not network.shared(tmp_path) and network.bind(tmp_path) == "127.0.0.1"
    network.share(tmp_path, True)
    assert network.shared(tmp_path) and network.bind(tmp_path) == "0.0.0.0"
    (tmp_path / network.FILE).write_text("not json")
    assert not network.shared(tmp_path)


def test_hosts_taken_with_and_without_the_network():
    assert named_here("127.0.0.1:8765", 8765, False) and named_here("localhost:8765", 8765, False)
    assert not named_here("192.168.1.20:8765", 8765, False)
    assert named_here("192.168.1.20:8765", 8765, True)
    assert named_here("pc-de-josselin.local:8765", 8765, True)
    # A site rebinding its own domain to this machine names that domain; another port is another server.
    assert not named_here("evil.example.com:8765", 8765, True)
    assert not named_here("192.168.1.20:9000", 8765, True)


def test_other_sites_stay_out_on_the_network():
    lan = {"Host": "192.168.1.20:8765", "Origin": "http://192.168.1.20:8765", "Sec-Fetch-Site": "same-origin"}
    assert same_site(lan, 8765, True) and not same_site(lan, 8765, False)
    assert not same_site({**lan, "Origin": "http://evil.example.com"}, 8765, True)
    assert not same_site({**lan, "Sec-Fetch-Site": "cross-site"}, 8765, True)


def test_wslconfig_set_to_mirrored_keeping_the_rest():
    text = "[wsl2]\r\n# 16 GB\r\nmemory=16GB\r\nnetworkingMode=nat\r\n\r\n[experimental]\r\nautoMemoryReclaim=dropCache\r\n"
    out = mirrored_config(text)
    assert out.count("networkingMode") == 1 and "networkingMode=mirrored\r\n" in out and "memory=16GB\r\n" in out
    assert out.index("networkingMode") < out.index("[experimental]")
    assert mirrored_config("") == "[wsl2]\nnetworkingMode=mirrored\n"
    assert mirrored_config("[experimental]\nx=1\n").endswith("[wsl2]\nnetworkingMode=mirrored\n")
    assert mirrored_config(out) == out
    assert mirrored_config("[wsl2]\nmemory=16GB\n\n[experimental]\nx=1\n") == "[wsl2]\nmemory=16GB\nnetworkingMode=mirrored\n\n[experimental]\nx=1\n"


def test_state_names_the_address_only_where_it_is_reachable(tmp_path, monkeypatch):
    monkeypatch.setattr(network, "address", lambda: "192.168.1.20")
    monkeypatch.setattr(network, "wsl_mode", lambda: "nat")
    assert network.state(tmp_path, 8765) == {"lan": False, "url": None, "wsl": "nat"}
    monkeypatch.setattr(network, "wsl_mode", lambda: "mirrored")
    assert network.state(tmp_path, 8765)["url"] == "http://192.168.1.20:8765/"
    monkeypatch.setattr(network, "wsl_mode", lambda: None)
    assert json.loads(json.dumps(network.state(tmp_path, 8765)))["url"] == "http://192.168.1.20:8765/"
