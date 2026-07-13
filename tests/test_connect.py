"""Tests for connect.py. Mocks HTTP and VastClient — no network needed."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Config, VastConfig  # noqa: E402
from connect import (  # noqa: E402
    ConnectError,
    check_generate,
    check_tags,
    model_is_pulled,
    resolve_target,
    run_check,
    wait_for_model,
)
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


def fake_http_response(json_body, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.raise_for_status.return_value = None
    return resp


class ResolveTargetTests(unittest.TestCase):
    def test_single_running_instance_with_port(self):
        client = MagicMock()
        client.show_instances.return_value = [
            Instance(1, "running", {"11434/tcp": [{"HostIp": "0.0.0.0", "HostPort": "40001"}]}, "1.2.3.4"),
            Instance(2, "loading", {}, None),
        ]
        self.assertEqual(resolve_target(client, 11434), ("1.2.3.4", 40001))

    def test_no_running_instance_raises(self):
        client = MagicMock()
        client.show_instances.return_value = [Instance(1, "loading", {}, None)]
        with self.assertRaises(ConnectError) as cm:
            resolve_target(client, 11434)
        self.assertIn("no running instance", str(cm.exception))

    def test_multiple_matches_raises_with_ids(self):
        client = MagicMock()
        client.show_instances.return_value = [
            Instance(1, "running", {"11434/tcp": [{"HostIp": "1.1.1.1", "HostPort": "1"}]}, "1.1.1.1"),
            Instance(2, "running", {"11434/tcp": [{"HostIp": "2.2.2.2", "HostPort": "2"}]}, "2.2.2.2"),
        ]
        with self.assertRaises(ConnectError) as cm:
            resolve_target(client, 11434)
        self.assertIn("1, 2", str(cm.exception))

    def test_explicit_instance_id_used_directly(self):
        client = MagicMock()
        client.get_instance.return_value = Instance(
            7, "running", {"11434/tcp": [{"HostIp": "9.9.9.9", "HostPort": "9"}]}, "9.9.9.9"
        )
        self.assertEqual(resolve_target(client, 11434, instance_id=7), ("9.9.9.9", 9))
        client.get_instance.assert_called_once_with(7)

    def test_unknown_instance_id_raises(self):
        client = MagicMock()
        client.get_instance.return_value = None
        with self.assertRaises(ConnectError):
            resolve_target(client, 11434, instance_id=999)


class ModelIsPulledTests(unittest.TestCase):
    def test_matches_tag_qualified_name(self):
        # Ollama's /api/tags always returns "name:tag"; config.json's model
        # name usually omits the tag (e.g. "qwen2.5-coder" pulls :latest).
        self.assertTrue(model_is_pulled("qwen2.5-coder", ["qwen2.5-coder:latest"]))

    def test_matches_exact_name(self):
        self.assertTrue(model_is_pulled("qwen2.5-coder:latest", ["qwen2.5-coder:latest"]))

    def test_no_match(self):
        self.assertFalse(model_is_pulled("qwen2.5-coder", ["llama3:latest"]))

    def test_no_match_on_empty_list(self):
        self.assertFalse(model_is_pulled("qwen2.5-coder", []))


class CheckTagsTests(unittest.TestCase):
    @patch("connect.requests.get")
    def test_returns_model_names(self, mock_get):
        mock_get.return_value = fake_http_response({"models": [{"name": "qwen2.5-coder"}]})
        names = check_tags("1.2.3.4", 11434)
        self.assertEqual(names, ["qwen2.5-coder"])
        mock_get.assert_called_once_with("http://1.2.3.4:11434/api/tags", timeout=10)

    @patch("connect.requests.get")
    def test_network_error_raises_connect_error(self, mock_get):
        import requests as real_requests

        mock_get.side_effect = real_requests.RequestException("refused")
        with self.assertRaises(ConnectError):
            check_tags("1.2.3.4", 11434)


class WaitForModelTests(unittest.TestCase):
    @patch("connect.check_tags")
    def test_returns_once_model_appears(self, mock_check_tags):
        mock_check_tags.side_effect = [[], ["qwen2.5-coder:latest"]]
        fake_time = [0.0]
        models = wait_for_model(
            "1.2.3.4",
            11434,
            "qwen2.5-coder",
            timeout_seconds=60,
            poll_interval=30,
            sleep=lambda s: fake_time.__setitem__(0, fake_time[0] + s),
            now=lambda: fake_time[0],
        )
        self.assertEqual(models, ["qwen2.5-coder:latest"])
        self.assertEqual(mock_check_tags.call_count, 2)

    @patch("connect.check_tags")
    def test_returns_immediately_if_already_present(self, mock_check_tags):
        mock_check_tags.return_value = ["qwen2.5-coder:latest"]
        models = wait_for_model(
            "1.2.3.4", 11434, "qwen2.5-coder", sleep=lambda s: self.fail("should not sleep")
        )
        self.assertEqual(models, ["qwen2.5-coder:latest"])

    @patch("connect.check_tags")
    def test_times_out_with_clear_error(self, mock_check_tags):
        mock_check_tags.return_value = []
        fake_time = [0.0]
        with self.assertRaises(ConnectError) as cm:
            wait_for_model(
                "1.2.3.4",
                11434,
                "qwen2.5-coder",
                timeout_seconds=10,
                poll_interval=3,
                sleep=lambda s: fake_time.__setitem__(0, fake_time[0] + s),
                now=lambda: fake_time[0],
            )
        self.assertIn("did not appear within 10s", str(cm.exception))


class CheckGenerateTests(unittest.TestCase):
    @patch("connect.requests.post")
    def test_returns_response_text(self, mock_post):
        mock_post.return_value = fake_http_response({"response": "OK"})
        text = check_generate("1.2.3.4", 11434, "qwen2.5-coder", "hi")
        self.assertEqual(text, "OK")
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["model"], "qwen2.5-coder")
        self.assertEqual(body["stream"], False)

    @patch("connect.requests.post")
    def test_missing_response_field_raises(self, mock_post):
        mock_post.return_value = fake_http_response({"unexpected": "shape"})
        with self.assertRaises(ConnectError):
            check_generate("1.2.3.4", 11434, "m", "p")


class RunCheckTests(unittest.TestCase):
    @patch("connect.check_generate")
    @patch("connect.check_tags")
    def test_uses_explicit_host_without_vast_lookup(self, mock_tags, mock_generate):
        mock_tags.return_value = ["qwen2.5-coder"]
        mock_generate.return_value = "OK"
        with patch("connect.VastClient") as mock_client_cls:
            run_check(make_config(), instance_id=None, host="5.5.5.5", port=9999)
            mock_client_cls.assert_not_called()
        mock_tags.assert_called_once_with("5.5.5.5", 9999)
        mock_generate.assert_called_once()

    @patch("connect.check_generate")
    @patch("connect.check_tags")
    def test_falls_back_to_config_port_when_host_given_without_port(self, mock_tags, mock_generate):
        mock_tags.return_value = []
        mock_generate.return_value = "OK"
        run_check(make_config(ollama_port=11434), instance_id=None, host="5.5.5.5", port=None)
        mock_tags.assert_called_once_with("5.5.5.5", 11434)

    @patch("connect.check_generate")
    @patch("connect.check_tags")
    def test_custom_prompt_is_passed_to_generate(self, mock_tags, mock_generate):
        mock_tags.return_value = []
        mock_generate.return_value = "OK"
        run_check(make_config(), instance_id=None, host="5.5.5.5", port=9999, prompt="custom prompt")
        mock_generate.assert_called_once_with("5.5.5.5", 9999, "qwen2.5-coder", "custom prompt")

    @patch("connect.check_generate")
    @patch("connect.check_tags")
    def test_no_false_warning_when_model_pulled_with_tag(self, mock_tags, mock_generate):
        # config.json's "qwen2.5-coder" vs. Ollama's tag-qualified
        # "qwen2.5-coder:latest" must not trigger the "not pulled yet" warning.
        mock_tags.return_value = ["qwen2.5-coder:latest"]
        mock_generate.return_value = "OK"
        with patch("builtins.print") as mock_print:
            run_check(make_config(), instance_id=None, host="5.5.5.5", port=9999)
        warnings = [c for c in mock_print.call_args_list if "not in server's model list" in str(c)]
        self.assertEqual(warnings, [])

    @patch("connect.check_generate")
    @patch("connect.wait_for_model")
    def test_watch_uses_wait_for_model_instead_of_single_check(self, mock_wait, mock_generate):
        mock_wait.return_value = ["qwen2.5-coder:latest"]
        mock_generate.return_value = "OK"
        run_check(
            make_config(),
            instance_id=None,
            host="5.5.5.5",
            port=9999,
            watch=True,
            poll_interval=5,
            watch_timeout=20,
        )
        mock_wait.assert_called_once_with(
            "5.5.5.5", 9999, "qwen2.5-coder", poll_interval=5, timeout_seconds=20
        )

    @patch("connect.check_generate")
    @patch("connect.check_tags")
    def test_default_behavior_unchanged_without_watch(self, mock_tags, mock_generate):
        mock_tags.return_value = ["qwen2.5-coder:latest"]
        mock_generate.return_value = "OK"
        with patch("connect.wait_for_model") as mock_wait:
            run_check(make_config(), instance_id=None, host="5.5.5.5", port=9999)
            mock_wait.assert_not_called()
        mock_tags.assert_called_once_with("5.5.5.5", 9999)


if __name__ == "__main__":
    unittest.main()
