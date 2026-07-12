"""Tests for provision.py. Mocks VastClient — no network needed."""

import shlex
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Config, VastConfig  # noqa: E402
from provision import (  # noqa: E402
    ProvisionError,
    build_onstart_script,
    extract_host_port,
    pick_offer,
    provision,
    wait_until_running,
)
from vast_client import Instance, Offer  # noqa: E402


def make_config(**overrides) -> Config:
    defaults = dict(
        vast=VastConfig(gpu="RTX_4090", max_price=0.5, disk_gb=40),
        model="qwen2.5-coder",
        ollama_port=11434,
        api_key="key",
    )
    defaults.update(overrides)
    return Config(**defaults)


class PickOfferTests(unittest.TestCase):
    def test_picks_cheapest_first_offer(self):
        client = MagicMock()
        client.search_offers.return_value = [
            Offer(1, "RTX_4090", 0.3, 100),
            Offer(2, "RTX_4090", 0.4, 100),
        ]
        offer = pick_offer(client, make_config())
        self.assertEqual(offer.id, 1)

    def test_no_offers_raises_clear_error(self):
        client = MagicMock()
        client.search_offers.return_value = []
        with self.assertRaises(ProvisionError) as cm:
            pick_offer(client, make_config())
        self.assertIn("no rentable offer", str(cm.exception))


class ExtractHostPortTests(unittest.TestCase):
    def test_returns_host_and_port(self):
        inst = Instance(
            1, "running", {"11434/tcp": [{"HostIp": "0.0.0.0", "HostPort": "40001"}]}, "1.2.3.4"
        )
        self.assertEqual(extract_host_port(inst, 11434), ("1.2.3.4", 40001))

    def test_falls_back_to_binding_host_ip(self):
        inst = Instance(1, "running", {"11434/tcp": [{"HostIp": "5.6.7.8", "HostPort": "1"}]}, None)
        self.assertEqual(extract_host_port(inst, 11434), ("5.6.7.8", 1))

    def test_returns_none_when_port_not_mapped_yet(self):
        inst = Instance(1, "loading", {}, None)
        self.assertIsNone(extract_host_port(inst, 11434))


class WaitUntilRunningTests(unittest.TestCase):
    def test_returns_once_running_and_mapped(self):
        client = MagicMock()
        client.get_instance.side_effect = [
            Instance(1, "loading", {}, None),
            Instance(1, "running", {"11434/tcp": [{"HostIp": "1.2.3.4", "HostPort": "1"}]}, "1.2.3.4"),
        ]
        fake_time = [0.0]
        inst = wait_until_running(
            client,
            1,
            11434,
            timeout_seconds=60,
            poll_interval=1,
            sleep=lambda s: fake_time.__setitem__(0, fake_time[0] + s),
            now=lambda: fake_time[0],
        )
        self.assertEqual(inst.status, "running")
        self.assertEqual(client.get_instance.call_count, 2)

    def test_times_out(self):
        client = MagicMock()
        client.get_instance.return_value = Instance(1, "loading", {}, None)
        fake_time = [0.0]
        with self.assertRaises(ProvisionError) as cm:
            wait_until_running(
                client,
                1,
                11434,
                timeout_seconds=10,
                poll_interval=3,
                sleep=lambda s: fake_time.__setitem__(0, fake_time[0] + s),
                now=lambda: fake_time[0],
            )
        self.assertIn("did not become reachable", str(cm.exception))

    def test_instance_disappearing_raises(self):
        client = MagicMock()
        client.get_instance.return_value = None
        with self.assertRaises(ProvisionError):
            wait_until_running(
                client, 1, 11434, timeout_seconds=10, poll_interval=1, sleep=lambda s: None
            )


class BuildOnstartScriptTests(unittest.TestCase):
    def test_serves_waits_then_pulls_model(self):
        script = build_onstart_script("qwen2.5-coder")
        self.assertIn("ollama serve &", script)
        self.assertIn("ollama pull qwen2.5-coder", script)
        # pull must come after the wait-for-ready loop, not race against boot.
        self.assertLess(script.index("until ollama list"), script.index("ollama pull"))
        self.assertTrue(script.rstrip().endswith("wait"))

    def test_shell_metacharacters_in_model_are_quoted(self):
        script = build_onstart_script("model; rm -rf /")
        self.assertIn(shlex.quote("model; rm -rf /"), script)
        self.assertNotIn("pull model; rm -rf /;", script)


class ProvisionEndToEndTests(unittest.TestCase):
    def test_onstart_includes_serve_and_pull_for_configured_model(self):
        client = MagicMock()
        client.search_offers.return_value = [Offer(1, "RTX_4090", 0.3, 100)]
        client.create_instance.return_value = 555
        client.get_instance.return_value = Instance(
            555, "running", {"11434/tcp": [{"HostIp": "0.0.0.0", "HostPort": "1"}]}, "1.2.3.4"
        )

        with patch("provision.VastClient", return_value=client):
            provision(make_config(model="qwen2.5-coder"), timeout_seconds=5)

        client.create_instance.assert_called_once()
        onstart = client.create_instance.call_args.kwargs["onstart"]
        self.assertIn("ollama serve", onstart)
        self.assertIn("ollama pull qwen2.5-coder", onstart)


if __name__ == "__main__":
    unittest.main()
