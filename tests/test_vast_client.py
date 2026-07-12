"""Tests for vast_client.VastClient. Mocks HTTP — no network or real API key needed."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vast_client import Instance, Offer, VastAPIError, VastClient  # noqa: E402


def fake_response(json_body, status_code=200, ok=True):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = ok
    resp.json.return_value = json_body
    resp.text = str(json_body)
    return resp


class VastClientInitTests(unittest.TestCase):
    def test_rejects_empty_api_key(self):
        with self.assertRaises(ValueError):
            VastClient("")


class SearchOffersTests(unittest.TestCase):
    def test_returns_offers(self):
        session = MagicMock()
        session.request.return_value = fake_response(
            {
                "offers": [
                    {"id": 1, "gpu_name": "RTX_4090", "dph_total": 0.3, "disk_space": 100},
                    {"id": 2, "gpu_name": "RTX_4090", "dph_total": 0.4, "disk_space": 200},
                ]
            }
        )
        client = VastClient("key", session=session)
        offers = client.search_offers(gpu_name="RTX_4090", max_price=0.5, min_disk_gb=40)

        self.assertEqual(offers, [Offer(1, "RTX_4090", 0.3, 100), Offer(2, "RTX_4090", 0.4, 200)])
        called_url = session.request.call_args.args[1]
        self.assertIn("/bundles/", called_url)
        sent_body = session.request.call_args.kwargs["json"]
        self.assertEqual(sent_body["gpu_name"], {"eq": "RTX_4090"})
        self.assertEqual(sent_body["dph_total"], {"lte": 0.5})

    def test_no_offers_returns_empty_list(self):
        session = MagicMock()
        session.request.return_value = fake_response({"offers": []})
        client = VastClient("key", session=session)
        self.assertEqual(client.search_offers(gpu_name="X", max_price=1, min_disk_gb=1), [])


class CreateInstanceTests(unittest.TestCase):
    def test_returns_new_contract_id(self):
        session = MagicMock()
        session.request.return_value = fake_response({"success": True, "new_contract": 555})
        client = VastClient("key", session=session)

        instance_id = client.create_instance(
            42, image="ollama/ollama:latest", disk_gb=40, port=11434
        )

        self.assertEqual(instance_id, 555)
        method, url = session.request.call_args.args[:2]
        self.assertEqual(method, "PUT")
        self.assertIn("/asks/42/", url)
        body = session.request.call_args.kwargs["json"]
        self.assertEqual(body["image"], "ollama/ollama:latest")
        self.assertEqual(body["env"], "-p 11434:11434")

    def test_missing_new_contract_raises(self):
        session = MagicMock()
        session.request.return_value = fake_response({"success": True})
        client = VastClient("key", session=session)
        with self.assertRaises(VastAPIError):
            client.create_instance(1, image="img", disk_gb=1, port=1)


class ShowInstancesTests(unittest.TestCase):
    def test_parses_instances(self):
        session = MagicMock()
        session.request.return_value = fake_response(
            {
                "success": True,
                "instances": [
                    {
                        "id": 1,
                        "actual_status": "running",
                        "public_ipaddr": "1.2.3.4",
                        "ports": {"11434/tcp": [{"HostIp": "0.0.0.0", "HostPort": "40001"}]},
                    }
                ],
            }
        )
        client = VastClient("key", session=session)
        instances = client.show_instances()
        self.assertEqual(
            instances,
            [Instance(1, "running", {"11434/tcp": [{"HostIp": "0.0.0.0", "HostPort": "40001"}]}, "1.2.3.4")],
        )

    def test_get_instance_finds_by_id(self):
        session = MagicMock()
        session.request.return_value = fake_response(
            {
                "success": True,
                "instances": [
                    {"id": 1, "actual_status": "running", "ports": {}, "public_ipaddr": None},
                    {"id": 2, "actual_status": "loading", "ports": {}, "public_ipaddr": None},
                ],
            }
        )
        client = VastClient("key", session=session)
        self.assertEqual(client.get_instance(2).status, "loading")
        self.assertIsNone(client.get_instance(99))


class DestroyInstanceTests(unittest.TestCase):
    def test_sends_delete(self):
        session = MagicMock()
        session.request.return_value = fake_response({"success": True})
        client = VastClient("key", session=session)
        client.destroy_instance(7)
        method, url = session.request.call_args.args[:2]
        self.assertEqual(method, "DELETE")
        self.assertIn("/instances/7/", url)


class ErrorHandlingTests(unittest.TestCase):
    def test_api_error_raises(self):
        session = MagicMock()
        session.request.return_value = fake_response(
            {"success": False, "msg": "invalid instance_id"}, status_code=400, ok=False
        )
        client = VastClient("key", session=session)
        with self.assertRaises(VastAPIError) as cm:
            client.destroy_instance(999)
        self.assertIn("invalid instance_id", str(cm.exception))

    def test_non_json_response_raises(self):
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 500
        resp.ok = False
        resp.json.side_effect = ValueError("no json")
        resp.text = "<html>error</html>"
        session.request.return_value = resp
        client = VastClient("key", session=session)
        with self.assertRaises(VastAPIError):
            client.show_instances()

    def test_network_error_raises(self):
        import requests as real_requests

        session = MagicMock()
        session.request.side_effect = real_requests.RequestException("boom")
        client = VastClient("key", session=session)
        with self.assertRaises(VastAPIError):
            client.show_instances()


if __name__ == "__main__":
    unittest.main()
