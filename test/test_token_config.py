"""Regresiones de caché local con datos inventados; sin servicios externos."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import telegram_bot as bot


class TestTokenCacheLocation(unittest.TestCase):
    def test_relative_cache_is_read_from_project_not_current_directory(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as elsewhere:
            cache_path = os.path.join(root, "private", "cache.json")
            os.makedirs(os.path.dirname(cache_path))
            with open(cache_path, "w", encoding="utf-8") as stream:
                json.dump({"AccessToken": {"fixture": {
                    "target": "Mail.Read offline_access",
                    "secret": "synthetic-test-value",
                    "expires_on": "1",
                }}}, stream)
            original_cwd = os.getcwd()
            try:
                os.chdir(elsewhere)
                resolved = bot.resolve_token_cache_path("private/cache.json", root)
                with mock.patch.object(bot, "TOKEN_CACHE_PATH", resolved):
                    self.assertEqual(bot._read_token_from_cache(), ("synthetic-test-value", "1"))
                self.assertEqual(os.listdir(elsewhere), [])
            finally:
                os.chdir(original_cwd)

    def test_absolute_cache_location_is_preserved(self):
        configured = os.path.join(tempfile.gettempdir(), "m365-existing", "cache.json")
        self.assertEqual(bot.resolve_token_cache_path(configured), configured)

    def test_quoted_dotenv_path_is_resolved_like_node_dotenv(self):
        with tempfile.TemporaryDirectory() as root:
            for quote in ['"', "'"]:
                self.assertEqual(
                    bot.resolve_token_cache_path(quote + "private/cache.json" + quote, root),
                    os.path.join(root, "private", "cache.json"),
                )

    def test_absent_or_blank_configuration_uses_legacy_home_cache(self):
        with tempfile.TemporaryDirectory() as home:
            for configured in [None, "", "   "]:
                self.assertEqual(
                    bot.resolve_token_cache_path(configured, home_dir=home),
                    os.path.join(home, ".m365-mcp", ".token_cache.json"),
                )
