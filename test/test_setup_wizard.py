"""Tests de scripts/setup.py (asistente de alta de un cliente).

Fallos encontrados al revisar el asistente que añadió opencode (17/09/2026):
  1. Sobrescribía un .env existente sin avisar (se perdía la config de Telegram).
  2. Pedía el Tenant ID y no lo guardaba: el .env se quedaba en `common`.
  3. Verificaba contra http://localhost, pero la app usa http://localhost:3000
     (src/auth.ts): con la App Registration real, la verificación fallaba.
  4. Verificaba con 7 permisos, no con los 16 que pide `npm run auth`.

Sin red ni navegador: se prueba la parte determinista del asistente.
"""
import importlib.util
import os
import re
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cargar_setup():
    spec = importlib.util.spec_from_file_location("asistente_setup", os.path.join(RAIZ, "scripts", "setup.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def leer_auth_ts():
    with open(os.path.join(RAIZ, "src", "auth.ts"), encoding="utf-8") as f:
        src = f.read()
    redirect = re.search(r'const REDIRECT_URI = "([^"]+)"', src)
    bloque = re.search(r"const GRAPH_SCOPES = \[(.*?)\];", src, re.S)
    if not redirect or not bloque:
        raise AssertionError("No se reconoce REDIRECT_URI/GRAPH_SCOPES en src/auth.ts: el test no sabe leerlo.")
    return redirect.group(1), re.findall(r'"([^"]+)"', bloque.group(1))


class TestCoherenciaConAuthTs(unittest.TestCase):
    def test_redirect_uri_igual_que_auth_ts(self):
        setup = cargar_setup()
        redirect, _ = leer_auth_ts()
        self.assertEqual(setup.REDIRECT_URI, redirect)

    def test_permisos_iguales_que_auth_ts(self):
        setup = cargar_setup()
        _, scopes = leer_auth_ts()
        self.assertEqual(sorted(setup.SCOPES), sorted(scopes))


class TestCreateEnv(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.setup = cargar_setup()
        self.setup.APP_DIR = self.tmp.name
        self.setup.ENV_FILE = os.path.join(self.tmp.name, ".env")
        self.setup.ENV_EXAMPLE = os.path.join(RAIZ, ".env.example")
        self.setup.TOKEN_CACHE_DIR = os.path.join(self.tmp.name, "cache")

    def tearDown(self):
        self.tmp.cleanup()

    def leer_env(self):
        with open(self.setup.ENV_FILE, encoding="utf-8") as f:
            return f.read()

    def test_guarda_el_tenant_indicado(self):
        self.assertTrue(self.setup.create_env("11111111-2222-3333-4444-555555555555", "contoso.onmicrosoft.com"))
        env = self.leer_env()
        self.assertIn("CLIENT_ID=11111111-2222-3333-4444-555555555555", env)
        self.assertRegex(env, r"(?m)^TENANT_ID=contoso\.onmicrosoft\.com$")
        self.assertNotRegex(env, r"(?m)^TENANT_ID=common$")

    def test_no_sobrescribe_un_env_existente_por_defecto(self):
        with open(self.setup.ENV_FILE, "w", encoding="utf-8") as f:
            f.write("TELEGRAM_BOT_TOKEN=config-real\n")
        self.assertFalse(self.setup.create_env("11111111-2222-3333-4444-555555555555", "common"))
        self.assertEqual(self.leer_env(), "TELEGRAM_BOT_TOKEN=config-real\n")

    def test_si_se_confirma_sobrescribir_guarda_copia_bak(self):
        with open(self.setup.ENV_FILE, "w", encoding="utf-8") as f:
            f.write("TELEGRAM_BOT_TOKEN=config-real\n")
        self.assertTrue(self.setup.create_env("11111111-2222-3333-4444-555555555555", "common", overwrite=True))
        copias = [n for n in os.listdir(self.tmp.name) if n.startswith(".env.bak.")]
        self.assertEqual(len(copias), 1, copias)
        with open(os.path.join(self.tmp.name, copias[0]), encoding="utf-8") as f:
            self.assertEqual(f.read(), "TELEGRAM_BOT_TOKEN=config-real\n")
        self.assertIn("CLIENT_ID=11111111-2222-3333-4444-555555555555", self.leer_env())



# ─── Careo ronda 1 (17/09/2026, Codex) ──────────────────────────────────────
import stat
import subprocess
from urllib.parse import parse_qs, urlparse


class TestCareoRonda1(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.setup = cargar_setup()
        self.setup.APP_DIR = self.tmp.name
        self.setup.ENV_FILE = os.path.join(self.tmp.name, ".env")
        self.setup.ENV_EXAMPLE = os.path.join(RAIZ, ".env.example")
        self.setup.TOKEN_CACHE_DIR = os.path.join(self.tmp.name, "cache")

    def tearDown(self):
        self.tmp.cleanup()

    # IMPORTANTE 2: inyección de líneas en el .env
    def test_rechaza_tenant_con_salto_de_linea_y_no_escribe_nada(self):
        ok = self.setup.create_env("11111111-2222-3333-4444-555555555555", "common\nTELEGRAM_BOT_TOKEN=robado")
        self.assertFalse(ok)
        self.assertFalse(os.path.exists(self.setup.ENV_FILE))

    def test_rechaza_client_id_que_no_es_guid(self):
        self.assertFalse(self.setup.create_env("abc\nX=1", "common"))
        self.assertFalse(os.path.exists(self.setup.ENV_FILE))

    def test_formatos_de_tenant(self):
        validos = ["common", "organizations", "consumers", "contoso.onmicrosoft.com",
                   "11111111-2222-3333-4444-555555555555"]
        invalidos = ["", "common\nX=1", "con espacio", "a;b", "common\r",
                     "contoso.com\nTELEGRAM_BOT_TOKEN=robado", "contoso.com X", "contoso.com\r"]
        for t in validos:
            self.assertTrue(self.setup.tenant_valido(t), t)
        for t in invalidos:
            self.assertFalse(self.setup.tenant_valido(t), repr(t))

    # IMPORTANTE 1 + MENOR 5: copia con fecha, ignorada por git y con permisos 0600
    def test_copia_con_fecha_ignorada_por_git_y_permisos_restringidos(self):
        with open(self.setup.ENV_FILE, "w", encoding="utf-8") as f:
            f.write("TELEGRAM_BOT_TOKEN=config-real\n")
        self.assertTrue(self.setup.create_env("11111111-2222-3333-4444-555555555555", "common", overwrite=True))
        copias = [n for n in os.listdir(self.tmp.name) if n.startswith(".env.bak")]
        self.assertEqual(len(copias), 1, copias)
        self.assertRegex(copias[0], r"^\.env\.bak\.\d{8}-\d{6}$")
        r = subprocess.run(["git", "check-ignore", "-q", copias[0]], cwd=RAIZ)
        self.assertEqual(r.returncode, 0, f"{copias[0]} NO está ignorado por .gitignore")
        for nombre in (".env", copias[0]):
            modo = stat.S_IMODE(os.stat(os.path.join(self.tmp.name, nombre)).st_mode)
            self.assertEqual(modo, 0o600, f"{nombre}: {oct(modo)}")

    # IMPORTANTE 3: lo que se ENVÍA a Microsoft usa el redirect y los permisos de auth.ts
    def test_url_de_autorizacion_usa_redirect_y_permisos_de_auth_ts(self):
        redirect, scopes = leer_auth_ts()
        url = self.setup.build_auth_url("cid", "common", "estado", "reto")
        qs = parse_qs(urlparse(url).query)
        self.assertEqual(qs["redirect_uri"], [redirect])
        self.assertEqual(sorted(qs["scope"][0].split(" ")), sorted(scopes))

    def test_peticion_de_token_usa_redirect_y_permisos_de_auth_ts(self):
        redirect, scopes = leer_auth_ts()
        cuerpo = parse_qs(self.setup.build_token_body("cid", "codigo", "verificador").decode())
        self.assertEqual(cuerpo["redirect_uri"], [redirect])
        self.assertEqual(sorted(cuerpo["scope"][0].split(" ")), sorted(scopes))


# ─── Careo ronda 2 (17/09/2026, Codex) ──────────────────────────────────────
import io
import json as _json
from unittest import mock


class TestFlujoReal(unittest.TestCase):
    """Lo que `verify_client_id` y `main` hacen DE VERDAD (red, navegador y
    teclado simulados), no solo las funciones que construyen URL y cuerpo."""

    def setUp(self):
        self.setup = cargar_setup()

    def test_verify_client_id_abre_y_envia_lo_de_auth_ts(self):
        redirect, scopes = leer_auth_ts()
        abierto = {}
        enviado = {}

        def abrir(url):
            abierto["url"] = url
            return True

        def teclear(_prompt):
            state = parse_qs(urlparse(abierto["url"]).query)["state"][0]
            return f"{redirect}/?code=codigo-123&state={state}"

        def urlopen(req):
            enviado["url"] = req.full_url
            enviado["cuerpo"] = parse_qs(req.data.decode())
            return io.BytesIO(_json.dumps({"access_token": "tok"}).encode())

        with mock.patch.object(self.setup.webbrowser, "open", side_effect=abrir), \
             mock.patch("builtins.input", side_effect=teclear), \
             mock.patch.object(self.setup.urllib.request, "urlopen", side_effect=urlopen), \
             mock.patch("builtins.print"):
            self.assertTrue(self.setup.verify_client_id("cid", "contoso.onmicrosoft.com"))

        u = urlparse(abierto["url"])
        self.assertEqual((u.scheme, u.netloc, u.path),
                         ("https", "login.microsoftonline.com", "/contoso.onmicrosoft.com/oauth2/v2.0/authorize"))
        qs = parse_qs(u.query)
        self.assertEqual(qs["redirect_uri"], [redirect])
        self.assertEqual(sorted(qs["scope"][0].split(" ")), sorted(scopes))
        self.assertEqual(enviado["url"], "https://login.microsoftonline.com/contoso.onmicrosoft.com/oauth2/v2.0/token")
        self.assertEqual(enviado["cuerpo"]["redirect_uri"], [redirect])
        self.assertEqual(enviado["cuerpo"]["code"], ["codigo-123"])
        self.assertEqual(sorted(enviado["cuerpo"]["scope"][0].split(" ")), sorted(scopes))
        self.assertTrue(enviado["cuerpo"]["code_verifier"][0])

    def _main(self, env_existe, respuesta_sobrescribir="n"):
        orden = []
        preguntas = []
        eventos = []  # preguntas de sobrescribir y login en UN solo orden

        def ask(prompt, default=None):
            preguntas.append((prompt, default))
            if "Sobrescribir" in prompt:
                eventos.append("pregunta-sobrescribir")
            if prompt.startswith("Azure App Registration CLIENT_ID"):
                return "11111111-2222-3333-4444-555555555555"
            if prompt == "Tenant ID":
                return "common"
            return respuesta_sobrescribir

        def verify(*_a):
            orden.append("verify")
            eventos.append("login")
            return True

        def create(*_a, **kw):
            orden.append(("create", kw.get("overwrite")))
            return True

        real_exists = os.path.exists
        with mock.patch.object(self.setup, "ask", side_effect=ask), \
             mock.patch.object(self.setup, "verify_client_id", side_effect=verify), \
             mock.patch.object(self.setup, "create_env", side_effect=create), \
             mock.patch.object(self.setup.os.path, "exists",
                               side_effect=lambda p: env_existe if p == self.setup.ENV_FILE else real_exists(p)), \
             mock.patch("builtins.print"):
            try:
                self.setup.main()
                codigo = 0
            except SystemExit as e:
                codigo = e.code or 0
        return orden, preguntas, codigo, eventos

    def test_main_sin_env_verifica_y_luego_crea(self):
        orden, _, codigo, _ev = self._main(env_existe=False)
        self.assertEqual(orden, ["verify", ("create", False)])
        self.assertEqual(codigo, 0)

    def test_main_con_env_y_no_sobrescribir_no_hace_login(self):
        orden, _, codigo, _ev = self._main(env_existe=True, respuesta_sobrescribir="n")
        self.assertEqual(orden, [])
        self.assertEqual(codigo, 0)

    def test_main_con_env_y_sobrescribir_pregunta_antes_del_login(self):
        orden, preguntas, _, eventos = self._main(env_existe=True, respuesta_sobrescribir="s")
        self.assertEqual(orden, ["verify", ("create", True)])
        self.assertEqual(eventos, ["pregunta-sobrescribir", "login"])
        prompt_sobrescribir = [p for p, _d in preguntas if "Sobrescribir" in p]
        self.assertEqual(len(prompt_sobrescribir), 1)
        self.assertNotIn("(s/n)", prompt_sobrescribir[0], "el valor por defecto ya lo muestra ask()")


class TestCopiasYDominios(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.setup = cargar_setup()
        self.setup.APP_DIR = self.tmp.name
        self.setup.ENV_FILE = os.path.join(self.tmp.name, ".env")
        self.setup.ENV_EXAMPLE = os.path.join(RAIZ, ".env.example")
        self.setup.TOKEN_CACHE_DIR = os.path.join(self.tmp.name, "cache")

    def tearDown(self):
        self.tmp.cleanup()

    def test_dos_sobrescrituras_en_el_mismo_segundo_no_machacan_la_copia(self):
        guid = "11111111-2222-3333-4444-555555555555"
        with open(self.setup.ENV_FILE, "w", encoding="utf-8") as f:
            f.write("VERSION=1\n")
        with mock.patch.object(self.setup.time, "strftime", return_value="20260917-120000"), \
             mock.patch("builtins.print"):
            self.assertTrue(self.setup.create_env(guid, "common", overwrite=True))
            with open(self.setup.ENV_FILE, "a", encoding="utf-8") as f:
                f.write("VERSION=2\n")
            self.assertTrue(self.setup.create_env(guid, "common", overwrite=True))
        copias = sorted(n for n in os.listdir(self.tmp.name) if n.startswith(".env.bak."))
        self.assertEqual(len(copias), 2, copias)
        for c in copias:
            r = subprocess.run(["git", "check-ignore", "-q", c], cwd=RAIZ)
            self.assertEqual(r.returncode, 0, f"{c} no está ignorado")

    def test_dominios_mal_formados_se_rechazan(self):
        for t in ["-.-", "a.-b", "a-.b", ".contoso.com", "contoso..com", "contoso.com."]:
            self.assertFalse(self.setup.tenant_valido(t), repr(t))
        for t in ["contoso.com", "my-tenant.onmicrosoft.com", "a1.b2.c3"]:
            self.assertTrue(self.setup.tenant_valido(t), repr(t))


if __name__ == "__main__":
    unittest.main()
