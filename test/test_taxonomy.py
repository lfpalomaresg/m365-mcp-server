"""Offline regression checks for generic defaults and local-rule precedence."""
import json
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import telegram_bot as bot


class TestTaxonomyConfiguration(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.path = os.path.join(self.directory, "taxonomy.json")
        for name, value in (
            ("TAXONOMY_FILE", self.path),
            ("TAXONOMY", []),
            ("_taxonomy_mtime", 0),
            ("_keyword_index", {}),
        ):
            self.stack.enter_context(mock.patch.object(bot, name, value))
        self.stack.enter_context(mock.patch.object(bot, "log"))

    def test_local_rules_replace_default_destinations_and_keep_conditions(self):
        with open(self.path, "w", encoding="utf-8") as stream:
            json.dump({"rules": [{
                "folder": "Review/Invoices",
                "keywords": ["FACTURA"],
                "if_sender": "SENDER@EXAMPLE.COM",
            }]}, stream)

        bot.load_taxonomy()

        self.assertEqual(bot.TAXONOMY, [{
            "folder": "Review/Invoices",
            "keywords": ["factura"],
            "if_sender": "sender@example.com",
        }])
        # A conditional local rule must not enter the unconditional fast path.
        self.assertNotIn("factura", bot._keyword_index)
        self.assertNotIn("pedido", bot._keyword_index)

    def test_invalid_json_restores_generic_defaults_after_local_configuration(self):
        with open(self.path, "w", encoding="utf-8") as stream:
            stream.write("{not valid json")
        bot.TAXONOMY = [{"folder": "Old/Destination", "keywords": ["obsolete"]}]
        bot._keyword_index = {"obsolete": "Old/Destination"}

        bot.load_taxonomy()

        self.assertNotIn("obsolete", bot._keyword_index)
        invoice_folder = bot._keyword_index["factura"]
        self.assertTrue(any(rule["folder"] == invoice_folder for rule in bot.TAXONOMY))
        self.assertTrue(bot._kw_in("factura", "nueva factura mensual"))
        self.assertFalse(bot._kw_in("factura", "prefacturacion"))
        self.assertEqual(bot._taxonomy_mtime, 0)
