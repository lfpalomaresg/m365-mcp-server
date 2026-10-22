"""Troceo de mensajes largos para Telegram (límite duro de 4096 caracteres).

Sin red: solo la función pura del bot.
"""
import unittest

import telegram_bot


class TrocearMensajeTest(unittest.TestCase):
    def test_texto_corto_vuelve_en_un_trozo(self):
        self.assertEqual(telegram_bot.trocear_mensaje("hola"), ["hola"])

    def test_texto_vacio_no_produce_trozos(self):
        self.assertEqual(telegram_bot.trocear_mensaje(""), [])

    def test_ningun_trozo_supera_el_limite(self):
        texto = "palabra " * 3000
        trozos = telegram_bot.trocear_mensaje(texto)
        self.assertTrue(all(len(t) <= telegram_bot.LIMITE_TELEGRAM for t in trozos))

    def test_prefiere_cortar_por_salto_de_linea_antes_que_por_caracter(self):
        texto = ("parrafo de prueba\n" * 1000).strip()
        trozos = telegram_bot.trocear_mensaje(texto)
        # Todos salvo el último acaban exactamente en un salto de línea.
        for trozo in trozos[:-1]:
            self.assertTrue(trozo.endswith("\n"), trozo[-10:])

    def test_corta_por_salto_de_linea(self):
        texto = "linea\n" * 2000
        trozos = telegram_bot.trocear_mensaje(texto)
        self.assertTrue(all(t.rstrip("\n").endswith("linea") for t in trozos))
        self.assertTrue(all(len(t) <= telegram_bot.LIMITE_TELEGRAM for t in trozos))

    def test_sin_espacios_corta_por_caracter(self):
        trozos = telegram_bot.trocear_mensaje("x" * 5000, limite=4096)
        self.assertEqual([len(t) for t in trozos], [4096, 904])

    def test_emoji_no_desborda_el_limite_real_de_telegram(self):
        # 3000 emojis = 6000 unidades UTF-16 (Telegram), 3000 code points.
        texto = "📧" * 3000
        trozos = telegram_bot.trocear_mensaje(texto)
        self.assertGreater(len(trozos), 1)
        for trozo in trozos:
            self.assertLessEqual(telegram_bot._unidades_utf16(trozo), telegram_bot.LIMITE_TELEGRAM)
            self.assertLessEqual(telegram_bot._unidades_utf16(trozo), telegram_bot.MARGEN_TELEGRAM)

    def test_un_trozo_no_entregado_se_registra(self):
        registros = []

        def falso_make_request(url, method=None, body=None, **kwargs):
            return {"_error": "http_400"}

        original_req, original_log = telegram_bot.make_request, telegram_bot.log
        telegram_bot.make_request = falso_make_request
        telegram_bot.log = registros.append
        try:
            telegram_bot.send_telegram(1, "hola")
        finally:
            telegram_bot.make_request, telegram_bot.log = original_req, original_log

        self.assertTrue(any("no entregado" in r for r in registros))

    def test_limite_personalizado(self):
        trozos = telegram_bot.trocear_mensaje("abc def ghi", limite=8)
        self.assertTrue(all(len(t) <= 8 for t in trozos))

    def test_no_se_pierde_contenido(self):
        texto = ("palabra " * 1000).strip()
        trozos = telegram_bot.trocear_mensaje(texto)
        self.assertEqual("".join(trozos), texto)

    def test_enviar_usa_trozos_y_el_teclado_va_en_el_ultimo(self):
        llamadas = []

        def falso_make_request(url, method=None, body=None, **kwargs):
            llamadas.append(body)
            return {"ok": True}

        original = telegram_bot.make_request
        telegram_bot.make_request = falso_make_request
        try:
            telegram_bot.send_telegram(123, "z" * 5000, reply_markup={"inline_keyboard": []})
        finally:
            telegram_bot.make_request = original

        self.assertEqual(len(llamadas), 2)
        self.assertNotIn("reply_markup", llamadas[0])
        self.assertIn("reply_markup", llamadas[1])


if __name__ == "__main__":
    unittest.main()


class RotacionLogTest(unittest.TestCase):
    def test_rota_el_log_por_encima_del_limite(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            original = telegram_bot.LOG_FILE
            telegram_bot.LOG_FILE = os.path.join(tmp, "bot.log")
            try:
                with open(telegram_bot.LOG_FILE, "w", encoding="utf-8") as f:
                    f.write("x" * 100)
                telegram_bot._rotar_log(si_supera=50)
                self.assertTrue(os.path.exists(telegram_bot.LOG_FILE + ".1"))
                self.assertFalse(os.path.exists(telegram_bot.LOG_FILE))
            finally:
                telegram_bot.LOG_FILE = original
