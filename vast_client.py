"""Thin client for the vast.ai REST API.

Only wraps the calls this project needs: searching offers, creating an
instance, listing instances (to read status/port mappings), and destroying
an instance. See https://docs.vast.ai/api-reference for the full API.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

BASE_URL = "https://console.vast.ai/api/v0"
INSTANCES_V1_URL = "https://console.vast.ai/api/v1/instances/"
DEFAULT_TIMEOUT = 30


class VastAPIError(Exception):
    """Raised when the vast.ai API returns an error or an unexpected response."""


@dataclass(frozen=True)
class Offer:
    id: int
    gpu_name: str
    dph_total: float
    disk_space: float


@dataclass(frozen=True)
class Instance:
    id: int
    status: str
    ports: dict
    public_ipaddr: str | None


class VastClient:
    """Minimal REST client for vast.ai, authenticated with a bearer API key."""

    def __init__(self, api_key: str, *, session: requests.Session | None = None):
        if not api_key:
            raise ValueError("api_key must be non-empty")
        self._api_key = api_key
        self._session = session or requests.Session()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._api_key}"}

    def _request(self, method: str, url: str, **kwargs) -> dict:
        try:
            resp = self._session.request(
                method, url, headers=self._headers(), timeout=DEFAULT_TIMEOUT, **kwargs
            )
        except requests.RequestException as exc:
            raise VastAPIError(f"request to vast.ai failed: {exc}") from exc

        try:
            data = resp.json()
        except ValueError as exc:
            raise VastAPIError(
                f"vast.ai returned non-JSON response (status {resp.status_code})"
            ) from exc

        if not resp.ok or data.get("success") is False:
            msg = data.get("msg") or data.get("error") or resp.text
            raise VastAPIError(f"vast.ai API error (status {resp.status_code}): {msg}")

        return data

    def search_offers(
        self, *, gpu_name: str, max_price: float, min_disk_gb: int, limit: int = 50
    ) -> list[Offer]:
        """Search rentable on-demand offers matching the given filters, cheapest first."""
        body = {
            "limit": limit,
            "type": "ondemand",
            "gpu_name": {"eq": gpu_name},
            "dph_total": {"lte": max_price},
            "disk_space": {"gte": min_disk_gb},
            "rentable": {"eq": True},
            "order": [["dph_total", "asc"]],
        }
        data = self._request("POST", f"{BASE_URL}/bundles/", json=body)
        offers_raw = data.get("offers", [])
        return [
            Offer(
                id=o["id"],
                gpu_name=o["gpu_name"],
                dph_total=o["dph_total"],
                disk_space=o["disk_space"],
            )
            for o in offers_raw
        ]

    def create_instance(
        self, offer_id: int, *, image: str, disk_gb: int, port: int, onstart: str = ""
    ) -> int:
        """Rent the given offer. Returns the new instance (contract) id."""
        body = {
            "image": image,
            "disk": disk_gb,
            "env": f"-p {port}:{port}",
            "runtype": "ssh",
        }
        if onstart:
            body["onstart"] = onstart
        data = self._request("PUT", f"{BASE_URL}/asks/{offer_id}/", json=body)
        instance_id = data.get("new_contract")
        if instance_id is None:
            raise VastAPIError(f"create_instance response missing 'new_contract': {data}")
        return instance_id

    def show_instances(self) -> list[Instance]:
        """List all instances on the account."""
        data = self._request("GET", INSTANCES_V1_URL)
        return [
            Instance(
                id=i["id"],
                status=i.get("actual_status", "unknown"),
                ports=i.get("ports") or {},
                public_ipaddr=i.get("public_ipaddr"),
            )
            for i in data.get("instances", [])
        ]

    def get_instance(self, instance_id: int) -> Instance | None:
        """Look up a single instance by id (via the instance list)."""
        for inst in self.show_instances():
            if inst.id == instance_id:
                return inst
        return None

    def destroy_instance(self, instance_id: int) -> None:
        """Destroy (terminate) an instance. Irreversible — stops billing for it."""
        self._request("DELETE", f"{BASE_URL}/instances/{instance_id}/")
