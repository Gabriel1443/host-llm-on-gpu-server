"""Tests for config loading/validation. Run: python3 -m unittest discover -s tests"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (  # noqa: E402
    DEFAULT_OLLAMA_PORT,
    Config,
    ConfigError,
    load_config,
)

VALID = {
    "vast": {"gpu": "RTX 4090", "max_price": 0.5, "disk_gb": 40},
    "model": "qwen2.5-coder",
    "ollama_port": 11434,
}
ENV = {"VAST_API_KEY": "test-key"}


def write_config(data) -> str:
    """Write ``data`` (dict → JSON, or raw str) to a temp file, return its path."""
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        f.write(data if isinstance(data, str) else json.dumps(data))
    return path


class LoadConfigTests(unittest.TestCase):
    def setUp(self):
        self._paths = []

    def tearDown(self):
        for p in self._paths:
            os.unlink(p)

    def _write(self, data):
        p = write_config(data)
        self._paths.append(p)
        return p

    def test_valid_config(self):
        cfg = load_config(self._write(VALID), env=ENV)
        self.assertIsInstance(cfg, Config)
        self.assertEqual(cfg.vast.gpu, "RTX 4090")
        self.assertEqual(cfg.vast.max_price, 0.5)
        self.assertEqual(cfg.vast.disk_gb, 40)
        self.assertEqual(cfg.model, "qwen2.5-coder")
        self.assertEqual(cfg.ollama_port, 11434)
        self.assertEqual(cfg.api_key, "test-key")

    def test_ollama_port_defaults(self):
        data = {k: v for k, v in VALID.items() if k != "ollama_port"}
        cfg = load_config(self._write(data), env=ENV)
        self.assertEqual(cfg.ollama_port, DEFAULT_OLLAMA_PORT)

    def test_verified_defaults_true_when_omitted(self):
        cfg = load_config(self._write(VALID), env=ENV)
        self.assertTrue(cfg.vast.verified)

    def test_verified_can_be_set_false(self):
        data = json.loads(json.dumps(VALID))
        data["vast"]["verified"] = False
        cfg = load_config(self._write(data), env=ENV)
        self.assertFalse(cfg.vast.verified)

    def test_verified_wrong_type_rejected(self):
        data = json.loads(json.dumps(VALID))
        data["vast"]["verified"] = "yes"
        with self.assertRaises(ConfigError):
            load_config(self._write(data), env=ENV)

    def test_min_cpu_cores_defaults_none_when_omitted(self):
        cfg = load_config(self._write(VALID), env=ENV)
        self.assertIsNone(cfg.vast.min_cpu_cores)

    def test_min_cpu_cores_can_be_set(self):
        data = json.loads(json.dumps(VALID))
        data["vast"]["min_cpu_cores"] = 2
        cfg = load_config(self._write(data), env=ENV)
        self.assertEqual(cfg.vast.min_cpu_cores, 2.0)

    def test_min_cpu_cores_non_positive_rejected(self):
        data = json.loads(json.dumps(VALID))
        data["vast"]["min_cpu_cores"] = 0
        with self.assertRaises(ConfigError):
            load_config(self._write(data), env=ENV)

    def test_missing_file(self):
        with self.assertRaises(ConfigError) as cm:
            load_config("/no/such/config.json", env=ENV)
        self.assertIn("not found", str(cm.exception))

    def test_invalid_json(self):
        with self.assertRaises(ConfigError) as cm:
            load_config(self._write("{ not json"), env=ENV)
        self.assertIn("invalid JSON", str(cm.exception))

    def test_missing_api_key(self):
        with self.assertRaises(ConfigError) as cm:
            load_config(self._write(VALID), env={})
        self.assertIn("VAST_API_KEY", str(cm.exception))

    def test_api_key_not_read_from_file(self):
        # A key placed in the file must be ignored; env is the only source.
        data = dict(VALID, api_key="should-be-ignored")
        cfg = load_config(self._write(data), env=ENV)
        self.assertEqual(cfg.api_key, "test-key")

    def test_missing_required_field(self):
        data = {k: v for k, v in VALID.items() if k != "model"}
        with self.assertRaises(ConfigError) as cm:
            load_config(self._write(data), env=ENV)
        self.assertIn("model", str(cm.exception))

    def test_missing_nested_field(self):
        data = {"vast": {"gpu": "RTX 4090", "max_price": 0.5}, "model": "m"}
        with self.assertRaises(ConfigError) as cm:
            load_config(self._write(data), env=ENV)
        self.assertIn("vast.disk_gb", str(cm.exception))

    def test_wrong_type_rejected(self):
        data = json.loads(json.dumps(VALID))
        data["ollama_port"] = "11434"  # string, not int
        with self.assertRaises(ConfigError) as cm:
            load_config(self._write(data), env=ENV)
        self.assertIn("ollama_port", str(cm.exception))

    def test_bool_rejected_for_number(self):
        data = json.loads(json.dumps(VALID))
        data["vast"]["disk_gb"] = True  # bool must not pass as int
        with self.assertRaises(ConfigError):
            load_config(self._write(data), env=ENV)

    def test_empty_model_rejected(self):
        data = dict(VALID, model="   ")
        with self.assertRaises(ConfigError):
            load_config(self._write(data), env=ENV)

    def test_out_of_range_port(self):
        data = dict(VALID, ollama_port=70000)
        with self.assertRaises(ConfigError):
            load_config(self._write(data), env=ENV)

    def test_non_positive_price(self):
        data = json.loads(json.dumps(VALID))
        data["vast"]["max_price"] = 0
        with self.assertRaises(ConfigError):
            load_config(self._write(data), env=ENV)

    def test_example_config_is_valid(self):
        # config.json.example must always load (with a key in env).
        example = Path(__file__).resolve().parent.parent / "config.json.example"
        cfg = load_config(example, env=ENV)
        self.assertEqual(cfg.model, "qwen2.5-coder")


if __name__ == "__main__":
    unittest.main()
