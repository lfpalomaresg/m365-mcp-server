"""M365_READ_ONLY en el bot: leer sí, escribir no.

Sin red: se sustituye `call_graph` por un contador y se comprueba que en modo
solo lectura no se llama nunca, y que al desactivarlo vuelve a llamarse.
"""
import os
import unittest
from unittest import mock

import telegram_bot


class SoloLecturaTest(unittest.TestCase):
    def test_valores_que_activan(self):
        self.assertTrue(telegram_bot.solo_lectura_activo("1"))
        self.assertTrue(telegram_bot.solo_lectura_activo(" 1 "))

    def test_valores_que_no_activan(self):
        for valor in ("", "0", "true", "sí", None):
            self.assertFalse(telegram_bot.solo_lectura_activo(valor), repr(valor))

    def test_aviso_nombra_la_variable(self):
        self.assertIn("M365_READ_ONLY", telegram_bot.aviso_solo_lectura("enviar"))

    def _sin_red(self):
        llamadas = []
        original = telegram_bot.call_graph

        def falso(*args, **kwargs):
            llamadas.append((args, kwargs))
            return {"value": []}

        telegram_bot.call_graph = falso
        self.addCleanup(setattr, telegram_bot, "call_graph", original)
        return llamadas

    def test_en_solo_lectura_no_se_escribe_nada(self):
        llamadas = self._sin_red()
        with mock.patch.dict(os.environ, {"M365_READ_ONLY": "1"}):
            self.assertFalse(telegram_bot.mark_read("id"))
            self.assertFalse(telegram_bot.archive_message("id"))
            self.assertFalse(telegram_bot.delete_message("id"))
            self.assertFalse(telegram_bot.reply_message("id", "hola"))
            self.assertFalse(telegram_bot.send_email_via_graph("a@b.c", "asunto", "cuerpo"))
            self.assertIn("solo lectura", telegram_bot.apply_plan([]))
        self.assertEqual(llamadas, [])

    def test_sin_solo_lectura_las_funciones_siguen_llamando(self):
        llamadas = self._sin_red()
        with mock.patch.dict(os.environ, {"M365_READ_ONLY": "0"}):
            self.assertTrue(telegram_bot.mark_read("id"))
        self.assertEqual(len(llamadas), 1)


if __name__ == "__main__":
    unittest.main()
