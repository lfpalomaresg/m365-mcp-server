import assert from "node:assert/strict";
import test from "node:test";

import {
  createOneDriveFolder,
  getOneDriveItemMetadata,
  listOneDriveFolder,
  moveOneDriveItem,
} from "../dist/onedrive.js";

function mockClient(response = {}) {
  const calls = [];
  const request = {
    select(value) { calls.push(["select", value]); return this; },
    top(value) { calls.push(["top", value]); return this; },
    header(name, value) { calls.push(["header", name, value]); return this; },
    get() { calls.push(["get"]); return response; },
    post(body) { calls.push(["post", body]); return response; },
    patch(body) { calls.push(["patch", body]); return response; },
  };
  return { calls, api(endpoint) { calls.push(["api", endpoint]); return request; } };
}

function pagedClient(pages) {
  const calls = [];
  let page = 0;
  const request = {
    select(value) { calls.push(["select", value]); return this; },
    top(value) { calls.push(["top", value]); return this; },
    header(name, value) { calls.push(["header", name, value]); return this; },
    async get() { calls.push(["get"]); return pages[page++]; },
  };
  return { calls, api(endpoint) { calls.push(["api", endpoint]); return request; } };
}

test("lists root children with a bounded page size", async () => {
  const client = mockClient({ value: [{ id: "1", name: "Docs", folder: { childCount: 2 } }] });
  const result = await listOneDriveFolder(client, { top: 5000 });
  assert.deepEqual(client.calls[0], ["api", "/me/drive/root/children"]);
  assert.ok(client.calls.some(([method, value]) => method === "top" && value === 200));
  assert.equal(result.items[0].type, "folder");
});

test("lists children by item id", async () => {
  const client = mockClient({ value: [] });
  await listOneDriveFolder(client, { folder_id: "folder-id" });
  assert.deepEqual(client.calls[0], ["api", "/me/drive/items/folder-id/children"]);
});

test("follows Graph pagination without silently omitting children", async () => {
  const client = pagedClient([
    { value: [{ id: "1", name: "One", file: {} }], "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/drive/root/children?$skiptoken=next" },
    { value: [{ id: "2", name: "Two", file: {} }] },
  ]);
  const result = await listOneDriveFolder(client, { top: 500 });
  assert.deepEqual(result.items.map((item) => item.id), ["1", "2"]);
  assert.ok(client.calls.some(([method, value]) => method === "api" && value.includes("$skiptoken=next")));
});

test("continues a large inventory from a validated Graph page URL", async () => {
  const nextPageUrl = "https://graph.microsoft.com/v1.0/me/drive/root/children?$skiptoken=x";
  const client = pagedClient([{ value: [{ id: "3", name: "Three", file: {} }] }]);
  const result = await listOneDriveFolder(client, { next_page_url: nextPageUrl, top: 100 });
  assert.deepEqual(client.calls[0], ["api", nextPageUrl]);
  assert.equal(result.items[0].id, "3");
});

test("rejects pagination URLs outside Microsoft Graph", async () => {
  const client = pagedClient([]);
  await assert.rejects(
    () => listOneDriveFolder(client, { next_page_url: "https://example.com/steal", top: 100 }),
    /invalid pagination URL/i,
  );
  assert.equal(client.calls.length, 0);
});

test("gets a safe metadata projection", async () => {
  const client = mockClient({ id: "1", name: "a.txt", parentReference: { id: "p" }, file: { mimeType: "text/plain" } });
  const result = await getOneDriveItemMetadata(client, { item_id: "1" });
  assert.equal(result.parentId, "p");
  assert.equal(result.mimeType, "text/plain");
});

test("creates a folder with fail conflict behavior", async () => {
  const client = mockClient({ id: "new", name: "Reports", folder: {} });
  await createOneDriveFolder(client, { name: "Reports", parent_id: "parent" });
  assert.deepEqual(client.calls[0], ["api", "/me/drive/items/parent/children"]);
  assert.deepEqual(client.calls.at(-1), ["post", { name: "Reports", folder: {}, "@microsoft.graph.conflictBehavior": "fail" }]);
});

test("rejects invalid folder names before calling Graph", async () => {
  const client = mockClient();
  await assert.rejects(() => createOneDriveFolder(client, { name: "../escape" }), /invalid/i);
  assert.equal(client.calls.length, 0);
});

test("rejects trailing dots, trailing spaces, and reserved folder names", async () => {
  for (const name of ["Reports.", "Reports ", "CON", "desktop.ini"]) {
    const client = mockClient();
    await assert.rejects(() => createOneDriveFolder(client, { name }), /invalid/i);
    assert.equal(client.calls.length, 0);
  }
});

test("moves an item only by stable ids and returns its new parent", async () => {
  const calls = [];
  const client = {
    calls,
    api(endpoint) {
      calls.push(["api", endpoint]);
      return {
        select(value) { calls.push(["select", value]); return this; },
        async get() {
          calls.push(["get"]);
          return endpoint.endsWith("/target")
            ? { id: "target", name: "Target", folder: {} }
            : { id: "item", name: "a.txt", parentReference: { id: "source" }, eTag: "etag-1", file: {} };
        },
        header(name, value) { calls.push(["header", name, value]); return this; },
        async patch(body) {
          calls.push(["patch", body]);
          return { id: "item", name: "a.txt", parentReference: { id: "target" }, file: {} };
        },
      };
    },
  };
  const result = await moveOneDriveItem(client, {
    item_id: "item",
    destination_folder_id: "target",
    expected_parent_id: "source",
    expected_name: "a.txt",
  });
  assert.deepEqual(client.calls[0], ["api", "/me/drive/items/item"]);
  assert.deepEqual(client.calls.at(-1), ["patch", {
    parentReference: { id: "target" },
    "@microsoft.graph.conflictBehavior": "fail",
  }]);
  assert.ok(client.calls.some((call) => call[0] === "header" && call[1] === "If-Match" && call[2] === "etag-1"));
  assert.equal(result.parentId, "target");
});

test("aborts a stale move before patching", async () => {
  const client = mockClient({ id: "item", name: "renamed.txt", parentReference: { id: "source" }, eTag: "etag-2", file: {} });
  await assert.rejects(() => moveOneDriveItem(client, {
    item_id: "item",
    destination_folder_id: "target",
    expected_parent_id: "source",
    expected_name: "old.txt",
  }), /changed/i);
  assert.ok(!client.calls.some(([method]) => method === "patch"));
});

test("rejects moving an item into itself", async () => {
  const client = mockClient();
  await assert.rejects(() => moveOneDriveItem(client, { item_id: "same", destination_folder_id: "same" }), /itself/i);
  assert.equal(client.calls.length, 0);
});
