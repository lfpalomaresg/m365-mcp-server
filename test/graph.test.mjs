import assert from "node:assert/strict";
import test from "node:test";
import { buildGraphClient, shouldRetryMethod } from "../dist/graph.js";

test("el cliente de Graph se construye sin lanzar AmbiguityInInitialization", () => {
  // Regresión: initWithMiddleware con authProvider + middleware lanzaba
  // AmbiguityInInitialization y TODAS las herramientas fallaban en runtime,
  // con la suite en verde porque ningún test instanciaba el cliente.
  assert.doesNotThrow(() => buildGraphClient("token-ficticio"));
});

test("no se reintentan las escrituras no idempotentes", () => {
  assert.equal(shouldRetryMethod("POST"), false);
  assert.equal(shouldRetryMethod("post"), false);
  assert.equal(shouldRetryMethod("GET"), true);
  assert.equal(shouldRetryMethod("PATCH"), true);
  assert.equal(shouldRetryMethod("PUT"), true);
  assert.equal(shouldRetryMethod(undefined), true);
});
