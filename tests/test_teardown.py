"""Tests for teardown.py. Mocks VastClient and state — no network needed."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import state  # noqa: E402
from config import Config, VastConfig  # noqa: E402
from teardown import TeardownError, resolve_instance_id, teardown  # noqa: E402
from vast_client import Instance  # noqa: E402


def make_config(**overrides) -> Config:
    defaults = dict(
        vast=VastConfig(gpu="RTX_4090", max_price=0.5, disk_gb=40),
        model="qwen2.5-coder",
        ollama_port=11434,
        api_key="key",
    )
    defaults.update(overrides)
    return Config(**defaults)


class ResolveInstanceIdTests(unittest.TestCase):
    @patch("teardown.state.load")
    def test_explicit_instance_id_wins(self, mock_load):
        client = MagicMock()
        result = resolve_instance_id(client, instance_id=99)
        self.assertEqual(result, 99)
        mock_load.assert_not_called()

    @patch("teardown.state.load")
    def test_falls_back_to_saved_state(self, mock_load):
        mock_load.return_value = state.InstanceState(instance_id=7, host="h", port=1)
        client = MagicMock()
        self.assertEqual(resolve_instance_id(client, instance_id=None), 7)

    @patch("teardown.state.load")
    def test_falls_back_to_sole_running_instance(self, mock_load):
        mock_load.return_value = None
        client = MagicMock()
        client.show_instances.return_value = [
            Instance(1, "running", {}, "1.1.1.1"),
            Instance(2, "loading", {}, None),
        ]
        self.assertEqual(resolve_instance_id(client, instance_id=None), 1)

    @patch("teardown.state.load")
    def test_none_when_nothing_found(self, mock_load):
        mock_load.return_value = None
        client = MagicMock()
        client.show_instances.return_value = []
        self.assertIsNone(resolve_instance_id(client, instance_id=None))

    @patch("teardown.state.load")
    def test_multiple_running_without_state_raises(self, mock_load):
        mock_load.return_value = None
        client = MagicMock()
        client.show_instances.return_value = [
            Instance(1, "running", {}, "1.1.1.1"),
            Instance(2, "running", {}, "2.2.2.2"),
        ]
        with self.assertRaises(TeardownError):
            resolve_instance_id(client, instance_id=None)


class TeardownTests(unittest.TestCase):
    @patch("teardown.state.clear")
    @patch("teardown.state.load")
    def test_destroys_after_confirmation(self, mock_load, mock_clear):
        mock_load.return_value = state.InstanceState(instance_id=7, host="h", port=1)
        client = MagicMock()
        with patch("teardown.VastClient", return_value=client):
            teardown(make_config(), instance_id=None, confirm=True, ask=lambda _: "y")
        client.destroy_instance.assert_called_once_with(7)
        mock_clear.assert_called_once()

    @patch("teardown.state.clear")
    @patch("teardown.state.load")
    def test_aborts_without_confirmation(self, mock_load, mock_clear):
        mock_load.return_value = state.InstanceState(instance_id=7, host="h", port=1)
        client = MagicMock()
        with patch("teardown.VastClient", return_value=client):
            teardown(make_config(), instance_id=None, confirm=True, ask=lambda _: "n")
        client.destroy_instance.assert_not_called()
        mock_clear.assert_not_called()

    @patch("teardown.state.load")
    def test_skips_prompt_when_confirm_false(self, mock_load):
        mock_load.return_value = state.InstanceState(instance_id=7, host="h", port=1)
        client = MagicMock()
        with patch("teardown.VastClient", return_value=client):
            teardown(
                make_config(),
                instance_id=None,
                confirm=False,
                ask=lambda _: (_ for _ in ()).throw(AssertionError("should not prompt")),
            )
        client.destroy_instance.assert_called_once_with(7)

    @patch("teardown.state.load")
    def test_nothing_to_destroy_is_a_no_op(self, mock_load):
        mock_load.return_value = None
        client = MagicMock()
        client.show_instances.return_value = []
        with patch("teardown.VastClient", return_value=client):
            teardown(make_config(), instance_id=None, confirm=True, ask=lambda _: "y")
        client.destroy_instance.assert_not_called()


if __name__ == "__main__":
    unittest.main()
