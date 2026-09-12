import assert from "node:assert/strict";
import test from "node:test";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

test("publishes all OneDrive organization tools through MCP", async () => {
  const transport = new StdioClientTransport({ command: process.execPath, args: ["dist/index.js"] });
  const client = new Client({ name: "contract-test", version: "1.0.0" });
  try {
    await client.connect(transport);
    const response = await client.listTools();
    const names = new Set(response.tools.map((tool) => tool.name));
    for (const name of [
      "list_onedrive_folder",
      "get_onedrive_item_metadata",
      "create_onedrive_folder",
      "move_onedrive_item",
    ]) {
      assert.ok(names.has(name), `missing MCP tool: ${name}`);
    }
  } finally {
    await client.close();
  }
});
