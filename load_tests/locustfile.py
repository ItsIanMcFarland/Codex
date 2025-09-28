"""Locust load test for the Social Discovery Service API."""

from __future__ import annotations

import os
from typing import List

from locust import FastHttpUser, between, task

API_KEY = os.getenv("SOCIAL_DISCOVERY_API_KEY", "test-key")
BATCH_ENDPOINT = os.getenv("SOCIAL_DISCOVERY_ENDPOINT", "http://localhost:8000/api/jobs/batch")
DOMAINS: List[str] = [
    "example-hotel.com",
    "grandstay.test",
    "luxuryresort.local",
]


class SubmitterUser(FastHttpUser):
    wait_time = between(1, 5)

    @task
    def submit_batch(self) -> None:
        payload = {
            "batch_name": "load-test",
            "hotel_domains": DOMAINS,
            "metadata": {"source": "locust"},
        }
        headers = {"X-API-Key": API_KEY}
        self.client.post(BATCH_ENDPOINT, json=payload, headers=headers)
