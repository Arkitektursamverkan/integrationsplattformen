#!/usr/bin/env node
/**
 * Integration Platform MCP Server
 *
 * Exposes the Integration Platform's full API as MCP tools for AI agents.
 * Communicates with the running API at http://localhost:8100 via HTTP.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const API_BASE = process.env.INTEGRATION_PLATFORM_URL || "http://localhost:8100/api/v1";
const ADMIN_KEY = process.env.INTEGRATION_PLATFORM_ADMIN_KEY || "dev-admin-key";

// ── HTTP helpers ─────────────────────────────────────────────────────────────

async function api(method, path, body = null) {
  const url = `${API_BASE}${path}`;
  const opts = {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Api-Key": ADMIN_KEY,
    },
  };
  if (body) opts.body = JSON.stringify(body);

  const resp = await fetch(url, opts);
  if (resp.status === 204) return { success: true };
  const text = await resp.text();
  try {
    return JSON.parse(text);
  } catch {
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${text}`);
    return { raw: text };
  }
}

function result(data) {
  return { content: [{ type: "text", text: typeof data === "string" ? data : JSON.stringify(data, null, 2) }] };
}

// ── Templates ────────────────────────────────────────────────────────────────

const TEMPLATES = {
  "2c8-processes-to-ea": {
    name: "2C8 Processes → EA Application",
    description: "Import process models from 2C8 and serve them for the EA Application",
    connection: {
      name: "2C8",
      connector_type: "2c8",
      config: { mode: "mock" },
      auth_type: "none",
    },
    flow: {
      name: "2C8 Processes",
      description: "Fetch and transform 2C8 process models for EA import",
      steps: [
        {
          step_order: 0,
          step_type: "transform",
          config: {
            mappings: [
              { source_field: "external_id", target_field: "external_id" },
              { source_field: "name", target_field: "name" },
              { source_field: "description", target_field: "description" },
              { source_field: "attributes.ägare", target_field: "owner" },
              { source_field: "attributes.kategori", target_field: "category" },
            ],
            computed_fields: [{ field: "node_type", value: "Process" }],
          },
        },
      ],
    },
  },
  "sharepoint-applications-to-ea": {
    name: "SharePoint Applications → EA Application",
    description: "Import application data from SharePoint and serve it for the EA Application",
    connection: {
      name: "SharePoint",
      connector_type: "sharepoint",
      config: { mode: "mock" },
      auth_type: "none",
    },
    flow: {
      name: "SharePoint Applications",
      description: "Fetch and transform SharePoint application records for EA import",
      steps: [
        {
          step_order: 0,
          step_type: "transform",
          config: {
            mappings: [
              { source_field: "external_id", target_field: "external_id" },
              { source_field: "name", target_field: "name" },
              { source_field: "description", target_field: "description" },
              { source_field: "attributes.leverantör", target_field: "vendor" },
              { source_field: "attributes.kategori", target_field: "category" },
              { source_field: "attributes.avdelning", target_field: "department" },
            ],
            computed_fields: [{ field: "node_type", value: "Application" }],
          },
        },
      ],
    },
  },
  "2c8-api-processes": {
    name: "2C8 Live API → Processes",
    description: "Connect to a live 2C8 server and import process models via the MT Backend REST API",
    connection: {
      name: "2C8 Production",
      connector_type: "2c8",
      config: { mode: "api", base_url: "REPLACE_ME", repository_id: "REPLACE_ME", resource_type: "models" },
      auth_type: "api_key",
    },
    flow: {
      name: "2C8 Live Processes",
      description: "Fetch process models from 2C8 production server",
      steps: [
        {
          step_order: 0,
          step_type: "transform",
          config: {
            mappings: [
              { source_field: "external_id", target_field: "external_id" },
              { source_field: "name", target_field: "name" },
              { source_field: "description", target_field: "description" },
              { source_field: "attributes.type", target_field: "process_type" },
              { source_field: "attributes.variant", target_field: "notation" },
            ],
            computed_fields: [{ field: "node_type", value: "Process" }, { field: "source", value: "2c8" }],
          },
        },
      ],
    },
  },
};

// ── MCP Server ───────────────────────────────────────────────────────────────

const server = new McpServer({
  name: "integration-platform",
  version: "1.0.0",
});

// ── Discovery tools ──────────────────────────────────────────────────────────

server.tool(
  "list_connector_types",
  "List all available connector types with their configuration schemas. Use this first to understand what integrations are possible.",
  {},
  async () => {
    const types = await api("GET", "/connections/types");
    const schemas = {};
    for (const t of types.connector_types || []) {
      schemas[t] = { type: t, note: "Use get_connector_schema for full config details" };
    }
    return result({ connector_types: types.connector_types, hint: "Use get_connector_schema with a type name to see required config fields and examples" });
  }
);

server.tool(
  "get_connector_schema",
  "Get the full configuration schema for a connector type, including required fields, types, and descriptions. Essential for building valid connection configs.",
  { connector_type: z.string().describe("The connector type: sharepoint, 2c8, or generic_rest") },
  async ({ connector_type }) => {
    // Return built-in schemas since the API doesn't expose them yet
    const schemas = {
      sharepoint: {
        connector_type: "sharepoint",
        config_fields: {
          mode: { type: "string", enum: ["mock", "api"], default: "mock", description: "mock = seed data, api = live Graph API" },
          site_id: { type: "string", description: "SharePoint site ID (required for API mode)" },
          list_id: { type: "string", description: "SharePoint list ID (required for API mode)" },
        },
        credential_fields: {
          access_token: { type: "string", description: "OAuth2 bearer token from Azure AD" },
        },
        example: {
          name: "SharePoint Production",
          connector_type: "sharepoint",
          config: { mode: "api", site_id: "your-site-id", list_id: "your-list-id" },
          credentials: { access_token: "your-token" },
          auth_type: "oauth2",
        },
      },
      "2c8": {
        connector_type: "2c8",
        config_fields: {
          mode: { type: "string", enum: ["mock", "api"], default: "mock", description: "mock = seed data, api = live 2C8 MT Backend API" },
          base_url: { type: "string", description: "2C8 server URL (required for API mode)" },
          repository_id: { type: "uuid", description: "UUID of the 2C8 repository (required for API mode)" },
          resource_type: { type: "string", enum: ["models", "symbols", "lists"], default: "models", description: "What to fetch" },
          list_id: { type: "uuid", description: "List UUID (required when resource_type=lists)" },
          language_id: { type: "uuid", description: "Language UUID for multi-language repos (optional)" },
          columns: { type: "string[]", description: "Column names for list results (optional)" },
        },
        credential_fields: {
          api_key: { type: "string", description: "2C8 API key (Bearer token)" },
        },
        example: {
          name: "2C8 Production",
          connector_type: "2c8",
          config: { mode: "api", base_url: "https://your-2c8-server.com", repository_id: "uuid-here", resource_type: "models" },
          credentials: { api_key: "your-api-key" },
          auth_type: "api_key",
        },
      },
      generic_rest: {
        connector_type: "generic_rest",
        config_fields: {
          url: { type: "string", required: true, description: "API endpoint URL" },
          method: { type: "string", enum: ["GET", "POST"], default: "GET" },
          headers: { type: "object", description: "Custom HTTP headers" },
          params: { type: "object", description: "Query parameters" },
          body: { type: "object", description: "Request body (for POST)" },
          auth_type: { type: "string", enum: ["none", "bearer", "api_key"], default: "none" },
          api_key_header: { type: "string", default: "X-Api-Key", description: "Header name for API key auth" },
          data_path: { type: "string", description: "Dot-separated path to records array in response (e.g. 'data.items')" },
        },
        credential_fields: {
          token: { type: "string", description: "Bearer token (when auth_type=bearer)" },
          api_key: { type: "string", description: "API key (when auth_type=api_key)" },
        },
        example: {
          name: "My REST API",
          connector_type: "generic_rest",
          config: { url: "https://api.example.com/data", auth_type: "bearer", data_path: "results" },
          credentials: { token: "your-bearer-token" },
          auth_type: "bearer",
        },
      },
    };
    return result(schemas[connector_type] || { error: `Unknown type: ${connector_type}. Available: sharepoint, 2c8, generic_rest` });
  }
);

// ── Connection tools ─────────────────────────────────────────────────────────

server.tool(
  "list_connections",
  "List all configured external system connections.",
  {},
  async () => result(await api("GET", "/connections"))
);

server.tool(
  "create_connection",
  "Create a new external system connection. Use get_connector_schema first to see required fields.",
  {
    name: z.string().describe("Human-readable name for the connection"),
    connector_type: z.string().describe("Connector type: sharepoint, 2c8, or generic_rest"),
    config: z.record(z.any()).describe("Connector-specific configuration object"),
    credentials: z.record(z.any()).optional().describe("Credentials object (encrypted at rest)"),
    auth_type: z.string().optional().default("none").describe("Auth type: none, oauth2, api_key, basic"),
    description: z.string().optional().describe("Optional description"),
  },
  async (args) => result(await api("POST", "/connections", args))
);

server.tool(
  "test_connection",
  "Test an existing connection to verify connectivity and credentials.",
  { connection_id: z.string().uuid().describe("UUID of the connection to test") },
  async ({ connection_id }) => result(await api("POST", `/connections/${connection_id}/test`))
);

server.tool(
  "delete_connection",
  "Delete a connection and all its associated flows and data.",
  { connection_id: z.string().uuid().describe("UUID of the connection to delete") },
  async ({ connection_id }) => result(await api("DELETE", `/connections/${connection_id}`))
);

// ── Flow tools ───────────────────────────────────────────────────────────────

server.tool(
  "list_flows",
  "List all integration flows.",
  {},
  async () => result(await api("GET", "/flows"))
);

server.tool(
  "get_flow",
  "Get detailed information about a specific flow, including its transform steps.",
  { flow_id: z.string().uuid().describe("UUID of the flow") },
  async ({ flow_id }) => result(await api("GET", `/flows/${flow_id}`))
);

server.tool(
  "create_flow",
  "Create a new integration flow with transform steps. Requires an existing connection_id.",
  {
    name: z.string().describe("Flow name"),
    connection_id: z.string().uuid().describe("UUID of the source connection"),
    description: z.string().optional().describe("Optional description"),
    steps: z.array(z.object({
      step_order: z.number().describe("Execution order (0-based)"),
      step_type: z.string().describe("Step type: 'transform' or 'filter'"),
      config: z.record(z.any()).describe("Step config with mappings, filters, computed_fields"),
    })).optional().describe("Transform/filter steps"),
  },
  async (args) => result(await api("POST", "/flows", args))
);

server.tool(
  "update_flow",
  "Update an existing flow's name, description, enabled status, or steps.",
  {
    flow_id: z.string().uuid().describe("UUID of the flow to update"),
    name: z.string().optional().describe("New name"),
    description: z.string().optional().describe("New description"),
    enabled: z.boolean().optional().describe("Enable or disable the flow"),
    steps: z.array(z.object({
      step_order: z.number(),
      step_type: z.string(),
      config: z.record(z.any()),
    })).optional().describe("Replace all steps with these new steps"),
  },
  async ({ flow_id, ...body }) => result(await api("PUT", `/flows/${flow_id}`, body))
);

server.tool(
  "delete_flow",
  "Delete a flow and all its stored data records.",
  { flow_id: z.string().uuid().describe("UUID of the flow to delete") },
  async ({ flow_id }) => result(await api("DELETE", `/flows/${flow_id}`))
);

server.tool(
  "execute_flow",
  "Execute a flow now — fetches data from the source, applies transforms, and stores results.",
  { flow_id: z.string().uuid().describe("UUID of the flow to execute") },
  async ({ flow_id }) => result(await api("POST", `/flows/${flow_id}/execute`))
);

// ── Data tools ───────────────────────────────────────────────────────────────

server.tool(
  "list_data_sources",
  "List all available data sources (flows that have stored records) with record counts and last sync times.",
  {},
  async () => result(await api("GET", "/data/sources"))
);

server.tool(
  "get_data_records",
  "Get stored data records for a flow. Returns paginated results with the transformed data.",
  {
    flow_id: z.string().uuid().describe("UUID of the flow"),
    page: z.number().optional().default(1).describe("Page number"),
    page_size: z.number().optional().default(20).describe("Records per page"),
  },
  async ({ flow_id, page, page_size }) => result(await api("GET", `/data/${flow_id}/records?page=${page}&page_size=${page_size}`))
);

server.tool(
  "get_data_summary",
  "Get a quick summary for a flow: record count, last sync, status.",
  { flow_id: z.string().uuid().describe("UUID of the flow") },
  async ({ flow_id }) => result(await api("GET", `/data/${flow_id}/summary`))
);

// ── Execution log tools ──────────────────────────────────────────────────────

server.tool(
  "list_executions",
  "List flow execution history. Optionally filter by flow_id or status.",
  {
    flow_id: z.string().uuid().optional().describe("Filter by flow UUID"),
    status: z.string().optional().describe("Filter by status: success, error, running"),
    page: z.number().optional().default(1).describe("Page number"),
  },
  async ({ flow_id, status, page }) => {
    const params = new URLSearchParams();
    if (flow_id) params.set("flow_id", flow_id);
    if (status) params.set("status", status);
    params.set("page", String(page || 1));
    return result(await api("GET", `/executions?${params}`));
  }
);

// ── API key tools ────────────────────────────────────────────────────────────

server.tool(
  "list_api_keys",
  "List all consumer API keys (without showing the actual key values).",
  {},
  async () => result(await api("GET", "/api-keys"))
);

server.tool(
  "create_api_key",
  "Create a new consumer API key. Returns the key value ONCE — it cannot be retrieved again.",
  {
    name: z.string().describe("Name for the API key, e.g. 'EA Application'"),
    scopes: z.array(z.string()).optional().default(["data:read"]).describe("Permission scopes"),
  },
  async (args) => result(await api("POST", "/api-keys", args))
);

server.tool(
  "delete_api_key",
  "Revoke and delete a consumer API key.",
  { key_id: z.string().uuid().describe("UUID of the API key to delete") },
  async ({ key_id }) => result(await api("DELETE", `/api-keys/${key_id}`))
);

// ── Schedule tools ───────────────────────────────────────────────────────────

server.tool(
  "list_schedules",
  "List all flow schedules.",
  {},
  async () => result(await api("GET", "/schedules"))
);

server.tool(
  "create_schedule",
  "Create a cron schedule for a flow to run automatically.",
  {
    flow_id: z.string().uuid().describe("UUID of the flow to schedule"),
    cron_expression: z.string().describe("Cron expression, e.g. '0 */6 * * *' for every 6 hours"),
    timezone: z.string().optional().default("UTC").describe("Timezone, e.g. 'Europe/Stockholm'"),
    enabled: z.boolean().optional().default(true),
  },
  async (args) => result(await api("POST", "/schedules", args))
);

server.tool(
  "delete_schedule",
  "Delete a flow schedule.",
  { schedule_id: z.string().uuid().describe("UUID of the schedule to delete") },
  async ({ schedule_id }) => result(await api("DELETE", `/schedules/${schedule_id}`))
);

// ── Template tools ───────────────────────────────────────────────────────────

server.tool(
  "list_templates",
  "List available integration templates — pre-built configs for common integrations that can be deployed with one call.",
  {},
  async () => {
    const summaries = Object.entries(TEMPLATES).map(([id, t]) => ({
      template_id: id,
      name: t.name,
      description: t.description,
      connector_type: t.connection.connector_type,
    }));
    return result(summaries);
  }
);

server.tool(
  "get_template",
  "Get full details of a template including connection config, flow steps, and what will be created.",
  { template_id: z.string().describe("Template ID from list_templates") },
  async ({ template_id }) => {
    const tpl = TEMPLATES[template_id];
    if (!tpl) return result({ error: `Unknown template: ${template_id}. Use list_templates to see available templates.` });
    return result(tpl);
  }
);

server.tool(
  "deploy_template",
  "Deploy an integration template — creates the connection and flow, optionally executes it immediately. For live API templates, provide overrides for base_url, repository_id, and credentials.",
  {
    template_id: z.string().describe("Template ID from list_templates"),
    connection_overrides: z.record(z.any()).optional().describe("Override connection config fields (e.g. base_url, repository_id)"),
    credential_overrides: z.record(z.any()).optional().describe("Override credentials (e.g. api_key)"),
    execute_now: z.boolean().optional().default(false).describe("Execute the flow immediately after creation"),
  },
  async ({ template_id, connection_overrides, credential_overrides, execute_now }) => {
    const tpl = TEMPLATES[template_id];
    if (!tpl) return result({ error: `Unknown template: ${template_id}` });

    // Create connection with overrides
    const connBody = {
      ...tpl.connection,
      config: { ...tpl.connection.config, ...(connection_overrides || {}) },
    };
    if (credential_overrides) connBody.credentials = credential_overrides;

    const conn = await api("POST", "/connections", connBody);
    if (!conn.id) return result({ error: "Failed to create connection", details: conn });

    // Create flow
    const flowBody = {
      ...tpl.flow,
      connection_id: conn.id,
    };
    const flow = await api("POST", "/flows", flowBody);
    if (!flow.id) return result({ error: "Failed to create flow", details: flow });

    const response = {
      template: template_id,
      connection: { id: conn.id, name: conn.name },
      flow: { id: flow.id, name: flow.name },
    };

    // Execute if requested
    if (execute_now) {
      const exec = await api("POST", `/flows/${flow.id}/execute`);
      response.execution = exec;
    }

    return result(response);
  }
);

// ── Health tool ──────────────────────────────────────────────────────────────

server.tool(
  "platform_status",
  "Check the Integration Platform's health and show a summary: service status, connection count, flow count, recent executions.",
  {},
  async () => {
    try {
      const [health, connections, flows, executions] = await Promise.all([
        api("GET", "/health"),
        api("GET", "/connections"),
        api("GET", "/flows"),
        api("GET", "/executions?page_size=5"),
      ]);
      return result({
        status: health.status,
        connections: (connections || []).length,
        flows: (flows || []).length,
        recent_executions: (executions.executions || []).map((e) => ({
          flow_id: e.flow_id,
          status: e.status,
          trigger: e.trigger_type,
          records: e.records_processed,
          at: e.started_at,
        })),
      });
    } catch (e) {
      return result({ status: "error", message: `Cannot reach platform API at ${API_BASE}: ${e.message}` });
    }
  }
);

// ── Start ────────────────────────────────────────────────────────────────────

const transport = new StdioServerTransport();
await server.connect(transport);
