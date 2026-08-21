from datetime import datetime, timedelta

from django.test import TestCase
from django.utils import timezone

from guild.models import ApiKey, RaidEvent


class RaidApiTests(TestCase):
    def test_create_raid_creates_event_with_api_key_permission(self):
        api_key, raw_key = ApiKey.issue(
            name="Raid Creator",
            permissions=["raids:create", "raids:read"],
        )

        start_at = timezone.now() + timedelta(days=1)
        payload = {
            "title": "Moonlit Raid",
            "zone": "Temple of Veeshan",
            "start_at": start_at.isoformat(),
            "end_at": (start_at + timedelta(hours=2)).isoformat(),
            "description": "Test raid creation",
            "public": True,
        }

        response = self.client.post(
            "/api/v1/raids/create",
            data=payload,
            content_type="application/json",
            HTTP_X_API_KEY=raw_key,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(RaidEvent.objects.count(), 1)
        self.assertEqual(RaidEvent.objects.get().title, "Moonlit Raid")
