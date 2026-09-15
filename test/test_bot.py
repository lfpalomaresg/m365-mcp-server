"""Tests for the Telegram bot pure functions (no network).

Run with: python -m unittest test.test_bot
or:        python -m pytest test/test_bot.py
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

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


class TestTokenRedaction(unittest.TestCase):
    """2026-09-16: el token del bot salía en claro en dist/bot.log (68 líneas del 13 al 15/09)."""

    def test_sanitize_url_masks_telegram_token(self):
        url = "https://api.telegram.org/bot123456789:AAHfake_Token-abcdefghijklmnopqrstu/getUpdates?offset=1"
        clean = bot.sanitize_url(url)
        self.assertNotIn("AAHfake_Token", clean)
        self.assertNotIn("123456789:", clean)

    def test_log_never_writes_bot_token(self):
        with tempfile.TemporaryDirectory() as d:
            old_dir, old_file = bot.DIST_DIR, bot.LOG_FILE
            bot.DIST_DIR, bot.LOG_FILE = d, os.path.join(d, "bot.log")
            try:
                with mock.patch("builtins.print"):
                    bot.log(f"HTTP error on {bot.TELEGRAM_API_URL}/getUpdates: boom")
                with open(bot.LOG_FILE, encoding="utf-8") as f:
                    content = f.read()
            finally:
                bot.DIST_DIR, bot.LOG_FILE = old_dir, old_file
        self.assertNotIn(bot.BOT_TOKEN, content)
        self.assertIn("getUpdates", content)


class TestNaturalLanguageReply(unittest.TestCase):
    """Una respuesta interpretada por el LLM no puede enviarse sin confirmación ni volcarse al log."""

    CHAT = 999

    def setUp(self):
        bot.user_state.pop(self.CHAT, None)
        bot.last_results[str(self.CHAT)] = {"2": "MSGID2"}
        self.patches = {n: mock.patch.object(bot, n) for n in
                        ("send_telegram", "save_state", "reply_message", "log", "answer_callback")}
        self.m = {n: p.start() for n, p in self.patches.items()}
        self.m["reply_message"].return_value = True

    def tearDown(self):
        for p in self.patches.values():
            p.stop()
        bot.user_state.pop(self.CHAT, None)
        bot.last_results.pop(str(self.CHAT), None)

    def _nl(self, text="contesta al 2 que vale, mañana"):
        nl = {"action": "responder", "params": {"num": "2", "text": "vale, mañana"}}
        with mock.patch.object(bot, "interpret_nl", return_value=nl), mock.patch.object(bot, "LLM_ENABLED", True):
            bot.handle_message(self.CHAT, text)

    def test_nl_reply_asks_confirmation_instead_of_sending(self):
        self._nl()
        self.m["reply_message"].assert_not_called()
        st = bot.user_state.get(self.CHAT, {})
        self.assertEqual(st.get("state"), "waiting_confirm_reply")
        self.assertEqual(st.get("reply_to"), "MSGID2")

    def test_confirm_reply_callback_sends(self):
        self._nl()
        bot.handle_callback(self.CHAT, "confirm_reply", "cb1")
        self.m["reply_message"].assert_called_once_with("MSGID2", "vale, mañana")
        self.assertNotIn(self.CHAT, bot.user_state)

    def test_nl_does_not_log_user_text(self):
        self._nl()
        logged = " ".join(str(c.args[0]) for c in self.m["log"].call_args_list if c.args)
        self.assertNotIn("vale, mañana", logged)
        self.assertNotIn("contesta al 2", logged)


class TestAlertRegistration(unittest.TestCase):
    """Un aviso de correo importante no puede machacar la última lista (/hoy, /buscar)."""

    def tearDown(self):
        bot.last_results.clear()

    def test_alert_does_not_clobber_last_list(self):
        bot.last_results["42"] = {"1": "LISTA1", "2": "LISTA2"}
        with mock.patch.object(bot, "save_state"):
            short = bot.register_alert(42, "ALERTA")
        self.assertEqual(bot.last_results["42"]["1"], "LISTA1")
        self.assertEqual(bot.last_results["42"][short], "ALERTA")
        self.assertNotIn(short, ("1", "2"))


class TestTokenCache(unittest.TestCase):
    """Sin un access token de Mail en la caché no se debe devolver otro cualquiera."""

    def test_no_fallback_to_unrelated_token(self):
        cache = {"AccessToken": {"k": {"target": "Files.Read", "secret": "OTRO", "expires_on": "9999999999"}}}
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "cache.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(cache, f)
            with mock.patch.object(bot, "TOKEN_CACHE_PATH", p):
                self.assertEqual(bot._read_token_from_cache(), (None, None))


if __name__ == "__main__":
    unittest.main()
