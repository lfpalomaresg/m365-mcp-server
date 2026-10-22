import assert from "node:assert/strict";
import test from "node:test";
import {
  FULL_SCOPES,
  MINIMAL_SCOPES,
  PolicyError,
  assertToolAllowed,
  isWriteCall,
  openCommand,
  resolveScopes,
} from "../dist/policy.js";

test("sin flag se piden los scopes historicos (no se rompe una sesion ya concedida)", () => {
  assert.deepEqual(resolveScopes({}), FULL_SCOPES);
  assert.deepEqual(resolveScopes({ M365_MINIMAL_SCOPES: "0" }), FULL_SCOPES);
});

test("M365_MINIMAL_SCOPES=1 pide solo los scopes que el servidor usa", () => {
  assert.deepEqual(resolveScopes({ M365_MINIMAL_SCOPES: "1" }), MINIMAL_SCOPES);
  for (const scope of ["Files.ReadWrite.All", "Mail.Send", "Tasks.ReadWrite", "offline_access"]) {
    assert.ok(MINIMAL_SCOPES.includes(scope), `falta ${scope}`);
  }
  for (const scope of ["Mail.ReadWrite", "Sites.ReadWrite.All", "Chat.ReadWrite"]) {
    assert.ok(!MINIMAL_SCOPES.includes(scope), `${scope} no se usa y no debe pedirse`);
  }
});

test("las lecturas no cuentan como escritura", () => {
  for (const name of ["search_onedrive_files", "get_latest_emails", "list_onedrive_folder"]) {
    assert.equal(isWriteCall(name), false, name);
  }
});

test("una herramienta de varias acciones se clasifica por su accion", () => {
  assert.equal(isWriteCall("manage_todo_tasks", { action: "list_lists" }), false);
  assert.equal(isWriteCall("manage_todo_tasks", { action: "list_tasks" }), false);
  assert.equal(isWriteCall("manage_todo_tasks", { action: "create_task" }), true);
  assert.equal(isWriteCall("manage_todo_tasks", { action: "complete_task" }), true);
  assert.equal(isWriteCall("sync_calendar_events", { action: "list" }), false);
  assert.equal(isWriteCall("update_excel_sheet", { action: "read" }), false);
  assert.equal(isWriteCall("update_excel_sheet", { action: "write" }), true);
});

test("fail-closed: una herramienta desconocida o sin accion se trata como escritura", () => {
  assert.equal(isWriteCall("herramienta_nueva"), true);
  assert.equal(isWriteCall("manage_todo_tasks", {}), true);
});

test("M365_READ_ONLY=1 bloquea escrituras y deja pasar lecturas", () => {
  const env = { M365_READ_ONLY: "1" };
  assert.doesNotThrow(() => assertToolAllowed("get_latest_emails", {}, env));
  assert.doesNotThrow(() => assertToolAllowed("manage_todo_tasks", { action: "list_tasks" }, env));
  assert.throws(() => assertToolAllowed("send_outlook_email", {}, env), PolicyError);
});

test("M365_CONFIRM_WRITES=1 exige confirm: true", () => {
  const env = { M365_CONFIRM_WRITES: "1" };
  assert.throws(() => assertToolAllowed("send_outlook_email", {}, env), /confirm/);
  assert.doesNotThrow(() => assertToolAllowed("send_outlook_email", { confirm: true }, env));
  assert.doesNotThrow(() => assertToolAllowed("get_latest_emails", {}, env));
});

test("abrir el navegador no pasa por una shell", () => {
  assert.deepEqual(openCommand("http://localhost:3000/x", "darwin"), ["open", "http://localhost:3000/x"]);
  assert.deepEqual(openCommand("http://localhost:3000/x", "linux"), ["xdg-open", "http://localhost:3000/x"]);
  // rundll32 recibe la URL como un solo argumento: cmd /c start la corta en el primer "&".
  assert.deepEqual(openCommand("http://localhost:3000/x?a=1&b=2", "win32"),
    ["rundll32", "url.dll,FileProtocolHandler", "http://localhost:3000/x?a=1&b=2"]);
});
