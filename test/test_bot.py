"""Tests for the Telegram bot pure functions (no network).

Run with: python -m unittest test.test_bot
or:        python -m pytest test/test_bot.py
"""
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import telegram_bot as bot  # noqa: E402


class TestStripHtml(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(bot.strip_html("<p>Hola</p>"), "Hola")

    def test_line_breaks(self):
        self.assertEqual(bot.strip_html("<p>a</p><p>b</p>"), "a\nb")

    def test_br(self):
        self.assertEqual(bot.strip_html("uno<br>dos"), "uno\ndos")

    def test_entities(self):
        self.assertEqual(bot.strip_html("caf&eacute;"), "café")

    def test_empty(self):
        self.assertEqual(bot.strip_html(""), "")

    def test_none(self):
        self.assertEqual(bot.strip_html(None), "")

    def test_removes_tags(self):
        self.assertEqual(bot.strip_html("<b>negrita</b> normal"), "negrita normal")


class TestLocalMidnight(unittest.TestCase):
    def test_returns_timezone_aware(self):
        result = bot.local_midnight_utc()
        self.assertIsNotNone(result.tzinfo)

    def test_is_utc(self):
        result = bot.local_midnight_utc()
        self.assertEqual(result.utcoffset().total_seconds(), 0)


class TestKeyboards(unittest.TestCase):
    def test_main_keyboard_structure(self):
        kb = bot.main_keyboard()
        self.assertIn("inline_keyboard", kb)
        self.assertTrue(len(kb["inline_keyboard"]) > 0)

    def test_main_keyboard_has_callbacks(self):
        kb = bot.main_keyboard()
        callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
        for expected in ["hoy", "clasifica", "buscar", "enviar", "calendario", "tareas"]:
            self.assertIn(expected, callbacks)

    def test_confirm_keyboard(self):
        kb = bot.confirm_keyboard("confirm_send")
        self.assertIn("confirm_send", [b["callback_data"] for row in kb["inline_keyboard"] for b in row])
        self.assertIn("cancel", [b["callback_data"] for row in kb["inline_keyboard"] for b in row])

    def test_email_actions_keyboard(self):
        kb = bot.email_actions_keyboard("5")
        callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
        self.assertIn("leido:5", callbacks)
        self.assertIn("archivar:5", callbacks)
        self.assertIn("eliminar:5", callbacks)
        self.assertIn("responder:5", callbacks)


class TestFormatEmailList(unittest.TestCase):
    def sample_email(self, **overrides):
        email = {
            "from": {"emailAddress": {"name": "Juan", "address": "juan@x.com"}},
            "subject": "Asunto de prueba",
            "receivedDateTime": "2026-09-12T10:30:00Z",
            "id": "AAA123",
        }
        email.update(overrides)
        return email

    def test_shows_sender(self):
        text = bot.format_email_list([self.sample_email()])
        self.assertIn("Juan", text)

    def test_shows_numbered_ids(self):
        text = bot.format_email_list([self.sample_email(), self.sample_email(subject="Otro")])
        self.assertIn("1.", text)
        self.assertIn("2.", text)

    def test_empty(self):
        self.assertEqual(bot.format_email_list([]), "Sin resultados.")


class TestRegisterResults(unittest.TestCase):
    def tearDown(self):
        bot.last_results.clear()

    def test_maps_short_ids(self):
        emails = [
            {"id": "ID1", "subject": "a"},
            {"id": "ID2", "subject": "b"},
            {"id": "ID3", "subject": "c"},
        ]
        mapping = bot.register_results(123, emails)
        self.assertEqual(mapping["1"], "ID1")
        self.assertEqual(mapping["3"], "ID3")

    def test_skips_missing_ids(self):
        emails = [{"subject": "sin id"}, {"id": "IDX", "subject": "con id"}]
        mapping = bot.register_results(456, emails)
        self.assertNotIn("1", mapping)  # first has no id
        self.assertEqual(mapping.get("2"), "IDX")


class TestEnvConfig(unittest.TestCase):
    def test_allowed_user_is_int(self):
        self.assertIsInstance(bot.ALLOWED_USER_ID, int)

    def test_token_configured(self):
        self.assertTrue(bot.BOT_TOKEN)


class TestGraphErrors(unittest.TestCase):
    def test_no_token_message(self):
        msg = bot.graph_error_text({"_error": "no_token"})
        self.assertIn("auth", msg.lower())

    def test_401_message(self):
        msg = bot.graph_error_text({"_error": "http_401"})
        self.assertIn("caducado", msg.lower())

    def test_429_message(self):
        msg = bot.graph_error_text({"_error": "http_429"})
        self.assertIn("limita", msg.lower())

    def test_unknown_error(self):
        msg = bot.graph_error_text({"_error": "http_500"})
        self.assertIn("Error", msg)

    def test_no_error_returns_none(self):
        self.assertIsNone(bot.graph_error_text({}))
        self.assertIsNone(bot.graph_error_text({"value": []}))


class TestThrottle(unittest.TestCase):
    def test_throttle_exists(self):
        # Verifies the throttle infrastructure is callable without error
        bot.MIN_GRAPH_INTERVAL = 0
        bot._throttle_graph()
        self.assertTrue(True)


class TestSanitizeUrl(unittest.TestCase):
    def test_strips_query_params(self):
        url = "https://graph.microsoft.com/v1.0/me/messages?$filter=isRead eq false&$top=5"
        clean = bot.sanitize_url(url)
        self.assertNotIn("$filter", clean)
        self.assertTrue(clean.endswith("/me/messages"))

    def test_masks_long_ids(self):
        url = "https://graph.microsoft.com/v1.0/me/messages/AQMkADAwATM0MDAAMS1kMTEANS1jYjVkLTAwAi0wMAoALgAA"
        clean = bot.sanitize_url(url)
        self.assertIn("/<id>", clean)

    def test_clean_url_passes_through(self):
        clean = bot.sanitize_url("https://graph.microsoft.com/v1.0/me")
        self.assertEqual(clean, "https://graph.microsoft.com/v1.0/me")


if __name__ == "__main__":
    unittest.main()
