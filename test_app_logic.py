"""Run: python -m unittest discover -p 'test_*.py' -v
All tests are offline: no Apple, Gmail, or Twilio requests are made.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock
import json
import tempfile
import unittest

import monitor
import notifications
import stock_core as core
import watchlist


class CatalogTests(unittest.TestCase):
    def test_catalog_variants(self):
        sample = (
            'prefix '
            '"partNumber":"AB123VC/A","price":{"fullPrice":1799.00},'
            '"category":"iphone","name":"iPhone 18 Pro Max 256GB Glacier" '
            '"partNumber":"ZX098VC/A","price":{"fullPrice":2999.00},'
            '"category":"iphone","name":"iPhone Duo 512GB Night Sky"'
        )
        variants = core.parse_catalog_html(sample)
        self.assertEqual(len(variants), 2)
        self.assertEqual(variants[0], {
            "part": "AB123VC/A", "model": "iPhone 18 Pro Max",
            "storage": "256GB", "color": "Glacier",
        })
        self.assertEqual(variants[1]["color"], "Night Sky")

    def test_model_and_storage_filters_prevent_wrong_colour(self):
        catalog = [
            {"model": "iPhone 18 Pro", "storage": "256GB", "color": "Amber", "part": "AAA1VC/A"},
            {"model": "iPhone 18 Pro", "storage": "512GB", "color": "Sage", "part": "AAA2VC/A"},
            {"model": "iPhone Duo", "storage": "256GB", "color": "Sky", "part": "BBB1VC/A"},
        ]
        duo = core.variants_for_model(catalog, "iPhone Duo", "256GB")
        self.assertEqual([v["color"] for v in duo], ["Sky"])
        self.assertEqual(duo[0]["part"], "BBB1VC/A")
        self.assertNotIn("Amber", [v["color"] for v in duo])
        self.assertEqual(core.family_for_model("iPhone Duo"), "iphone-duo")
        self.assertEqual(core.family_for_model("iPhone 18 Pro"), "iphone-18-pro")

    def test_storage_sort(self):
        self.assertEqual(sorted(["1TB", "512GB", "256GB", "2TB"], key=core.storage_sort_key),
                         ["256GB", "512GB", "1TB", "2TB"])

    def test_status_unknown_is_not_sold_out(self):
        self.assertEqual(core.classify_pickup("available"), "Available")
        self.assertEqual(core.classify_pickup("unavailable"), "Unavailable")
        self.assertEqual(core.classify_pickup(None), "Unknown")
        self.assertEqual(core.classify_pickup("restricted"), "Unknown")

    def test_apple_links_only(self):
        self.assertEqual(core.secure_apple_link("http://www.apple.com/ca/shop"),
                         "https://www.apple.com/ca/shop")
        self.assertIsNone(core.secure_apple_link("https://apple.com.bad.example/"))

    def test_pickup_response(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "body": {"stores": [
                {"storeName": "Apple Eaton Centre", "city": "Toronto", "storeNumber": "R001",
                 "partsAvailability": {"ABC123VC/A": {"pickupDisplay": "available",
                      "messageTypes": {"regular": {"storePickupQuote": "<b>Today</b>"}}}}},
                {"storeName": "Apple Yorkdale", "city": "Toronto", "storeNumber": "R002",
                 "partsAvailability": {"ABC123VC/A": {"pickupDisplay": "restricted"}}},
            ]}
        }
        session = MagicMock()
        session.get.side_effect = [MagicMock(), response]
        with patch.object(core, "new_session", return_value=session):
            stores, checked = core.check_pickup("ABC123VC/A", "Toronto", "iphone-18-pro")
        self.assertEqual([r["Status"] for r in stores], ["Available", "Unknown"])
        self.assertEqual(stores[0]["Store ID"], "R001")
        self.assertEqual(stores[0]["Pickup details"], "Today")
        self.assertIn("UTC", checked)

    def test_bad_pickup_response_fails_closed(self):
        session = MagicMock()
        response = MagicMock(status_code=200)
        response.json.return_value = {"body": {}}
        session.get.side_effect = [MagicMock(), response]
        with patch.object(core, "new_session", return_value=session):
            with self.assertRaises(RuntimeError):
                core.check_pickup("ABC123VC/A", "Toronto", "iphone-18-pro")

    def test_no_legacy_endpoint(self):
        self.assertNotIn("/fulfillment-messages", Path(core.__file__).read_text(encoding="utf-8"))


class NotificationsTests(unittest.TestCase):
    def test_recipient_validation(self):
        self.assertTrue(notifications.email_valid("test@example.com"))
        self.assertFalse(notifications.email_valid("bad@example.com\nBcc:another@example.com"))
        self.assertTrue(notifications.phone_valid("+14165550123"))
        self.assertFalse(notifications.phone_valid("4165550123"))

    def test_send_sms_payload(self):
        with patch.dict("os.environ", {"TWILIO_ACCOUNT_SID": "AC" + "1" * 32,
                                        "TWILIO_AUTH_TOKEN": "fake-token",
                                        "TWILIO_FROM": "+14165550100"}):
            with patch.object(notifications.requests, "post") as post:
                post.return_value.status_code = 201
                notifications.send_sms("+14165550123", "test message")
        self.assertEqual(post.call_args.kwargs["data"]["To"], "+14165550123")
        self.assertEqual(post.call_args.kwargs["data"]["Body"], "test message")
        self.assertEqual(post.call_args.kwargs["auth"][1], "fake-token")


class WatchlistTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.p1 = patch.object(watchlist, "DATA_DIR", self.root)
        self.p2 = patch.object(watchlist, "WATCHLIST_PATH", self.root / "watchlist.json")
        self.p1.start(); self.p2.start()
        self.addCleanup(self.p1.stop); self.addCleanup(self.p2.stop)

    def add(self):
        return watchlist.create_watch(
            part="ABC123VC/A", model="iPhone 18 Pro", storage="256GB", color="White",
            location="Toronto", family="iphone-18-pro", target_stores=[], email="hello@example.com",
        )

    def test_watch_persists_and_removes(self):
        w = self.add()
        self.assertEqual(watchlist.load_watches()[0]["id"], w["id"])
        watchlist.update_watch_state(w["id"], {"email": ["R1"], "sms": []}, "now", "")
        self.assertEqual(watchlist.load_watches()[0]["notified"]["email"], ["R1"])
        watchlist.delete_watch(w["id"])
        self.assertEqual(watchlist.load_watches(), [])

    def test_duplicate_watch_is_rejected(self):
        self.add()
        with self.assertRaises(ValueError):
            self.add()

    def test_sold_out_rearms_unknown_preserves_state(self):
        notified = {"email": ["R1", "R2"], "sms": ["R1"]}
        rows = [{"Store ID": "R1", "Status": "Unavailable"},
                {"Store ID": "R2", "Status": "Unknown"}]
        self.assertEqual(watchlist.clear_sold_out(notified, rows),
                         {"email": ["R2"], "sms": []})

    def test_pending_only_new_available(self):
        notified = {"email": ["R1"], "sms": []}
        rows = [{"Store ID": "R1", "Status": "Available"},
                {"Store ID": "R2", "Status": "Available"},
                {"Store ID": "R3", "Status": "Unknown"}]
        self.assertEqual([r["Store ID"] for r in watchlist.pending_for_channel("email", notified, rows)], ["R2"])

    def test_monitor_sends_once_then_rearms(self):
        watch = self.add()
        available = [{"Store ID": "R1", "Store": "Eaton", "City": "Toronto", "Status": "Available"}]
        unavailable = [{**available[0], "Status": "Unavailable"}]
        with patch.object(monitor, "check_pickup", side_effect=[
            (available, "first"), (available, "second"), (unavailable, "third"), (available, "fourth")
        ]), patch.object(monitor, "send_email") as send:
            for expected in [1, 0, 0, 1]:
                w = watchlist.load_watches()[0]
                count, messages = monitor.check_watch(w)
                self.assertEqual(count, expected, messages)
        self.assertEqual(send.call_count, 2)

    def test_failed_email_retries_without_duplicate_other_channel(self):
        watchlist.create_watch(part="ABC123VC/A", model="iPhone Duo", storage="", color="",
            location="Toronto", family="iphone-duo", target_stores=[],
            email="hello@example.com", sms="+14165550123")
        row = {"Store ID": "R1", "Store": "Eaton", "City": "Toronto", "Status": "Available"}
        with patch.object(monitor, "check_pickup", return_value=([row], "now")), \
             patch.object(monitor, "send_email", side_effect=[OSError("smtp down"), None]) as send_mail, \
             patch.object(monitor, "send_sms") as send_text:
            count1, _ = monitor.check_watch(watchlist.load_watches()[0])
            count2, _ = monitor.check_watch(watchlist.load_watches()[0])
        self.assertEqual([count1, count2], [1, 1])
        self.assertEqual(send_mail.call_count, 2)
        self.assertEqual(send_text.call_count, 1)

    def test_unknown_does_not_trigger_reset_after_accepted_alert(self):
        w = self.add()
        row = {"Store ID": "R1", "Store": "Eaton", "City": "Toronto"}
        with patch.object(monitor, "check_pickup", side_effect=[
            ([{**row, "Status": "Available"}], "now"),
            ([{**row, "Status": "Unknown"}], "later"),
            ([{**row, "Status": "Available"}], "later2"),
        ]), patch.object(monitor, "send_email") as send:
            for _ in range(3):
                monitor.check_watch(watchlist.load_watches()[0])
        self.assertEqual(send.call_count, 1)


if __name__ == "__main__":
    unittest.main()
