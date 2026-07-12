"""Tests for state.py."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import state  # noqa: E402


class StateTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkstemp(suffix=".json")[1])
        self.path.unlink()  # start with no file, like a fresh checkout

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_load_returns_none_when_missing(self):
        self.assertIsNone(state.load(path=self.path))

    def test_save_then_load_roundtrips(self):
        saved = state.InstanceState(instance_id=42, host="1.2.3.4", port=11434)
        state.save(saved, path=self.path)
        self.assertEqual(state.load(path=self.path), saved)

    def test_clear_removes_file(self):
        state.save(state.InstanceState(1, "h", 1), path=self.path)
        state.clear(path=self.path)
        self.assertIsNone(state.load(path=self.path))

    def test_clear_is_safe_when_nothing_to_clear(self):
        state.clear(path=self.path)  # must not raise


if __name__ == "__main__":
    unittest.main()
