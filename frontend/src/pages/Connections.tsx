import { useState } from "react";
import {
  Accordion, AccordionDetails, AccordionSummary,
  Alert, Box, Button, Card, CardContent, Checkbox, Chip,
  Dialog, DialogActions, DialogContent, DialogTitle,
  Divider, FormControl, FormControlLabel, FormHelperText, IconButton, InputLabel, Link, MenuItem, Select,
  Step, StepContent, StepLabel, Stepper,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  TextField, Typography,
} from "@mui/material";
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  Edit as EditIcon,
  PlayArrow as PlayArrowIcon,
  ExpandMore as ExpandMoreIcon,
  HelpOutlineOutlined as HelpOutlineIcon,
} from "@mui/icons-material";
import { useConnections, useCreateConnection, useUpdateConnection, useDeleteConnection, useTestConnection, type Connection, type ConnectionCreate } from "@/api/connections";
import StatusChip from "@/components/common/StatusChip";
import { useSnackbar } from "notistack";
import client from "@/api/client";

// ── Help panel component ─────────────────────────────────────────────────────

function HelpPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Accordion sx={{ bgcolor: "primary.50", "&::before": { display: "none" }, border: "1px solid", borderColor: "primary.100", borderRadius: 1 }} disableGutters>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <HelpOutlineIcon sx={{ mr: 1, color: "primary.main", fontSize: 20 }} />
        <Typography variant="body2" sx={{ color: "primary.main", fontWeight: 600 }}>{title}</Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Typography variant="body2" component="div" sx={{ "& p": { mt: 0, mb: 1 }, "& code": { bgcolor: "grey.100", px: 0.5, borderRadius: 0.5, fontSize: 12 }, "& ol, & ul": { pl: 2, mt: 0, mb: 1 } }}>
          {children}
        </Typography>
      </AccordionDetails>
    </Accordion>
  );
}

// ── Connector definitions ────────────────────────────────────────────────────

type ConnectorType = "2c8" | "sharepoint" | "excel_sharepoint" | "generic_rest" | "csv";

const CONNECTOR_INFO: Record<ConnectorType, { label: string; description: string }> = {
  "2c8": { label: "2C8", description: "Connect to 2C8 Modeling Tool to import process models, symbols, or run predefined lists." },
  sharepoint: { label: "SharePoint", description: "Connect to Microsoft 365 SharePoint to import list data via the Microsoft Graph API." },
  excel_sharepoint: { label: "Excel in SharePoint", description: "Read a sheet or table in an Excel file (.xlsx) stored in SharePoint or OneDrive, via the Microsoft Graph API. Each row becomes a record." },
  generic_rest: { label: "Generic REST API", description: "Connect to any REST API by specifying the URL, authentication, and response format." },
  csv: { label: "CSV File", description: "Upload a CSV, TSV, or TXT file as a data source. The data is stored and available via the Data API." },
};

// Connectors with a demo/mock mode next to the live one.
const hasMode = (t: ConnectorType) => t === "2c8" || t === "sharepoint" || t === "csv";

// ── Component ────────────────────────────────────────────────────────────────

export default function Connections() {
  const { data: connections, isLoading } = useConnections();
  const createMutation = useCreateConnection();
  const updateMutation = useUpdateConnection();
  const deleteMutation = useDeleteConnection();
  const testMutation = useTestConnection();
  const { enqueueSnackbar } = useSnackbar();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [activeStep, setActiveStep] = useState(0);

  // Edit dialog state
  const [editConn, setEditConn] = useState<Connection | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editConfigFields, setEditConfigFields] = useState<Record<string, string>>({});
  const [editCredFields, setEditCredFields] = useState<Record<string, string>>({});

  const openEdit = (conn: Connection) => {
    setEditConn(conn);
    setEditName(conn.name);
    setEditDescription(conn.description || "");
    // Flatten config into string fields
    const cf: Record<string, string> = {};
    for (const [k, v] of Object.entries(conn.config || {})) {
      cf[k] = typeof v === "object" ? JSON.stringify(v) : String(v ?? "");
    }
    setEditConfigFields(cf);
    setEditCredFields({});
  };

  const setEditConfig2 = (key: string, value: string) => setEditConfigFields((p) => ({ ...p, [key]: value }));
  const setEditCred = (key: string, value: string) => setEditCredFields((p) => ({ ...p, [key]: value }));

  const handleUpdate = async () => {
    if (!editConn) return;
    const config: Record<string, unknown> = { ...editConfigFields };
    // Fält som var objekt (t.ex. headers) visas som JSON – tillbaka till objekt,
    // så att de inte sparas som text. Dolda värden (••••••) skickas oförändrade:
    // plattformen behåller då det sparade värdet.
    for (const [k, v] of Object.entries(editConn.config || {})) {
      if (v && typeof v === "object" && typeof config[k] === "string") {
        try {
          config[k] = JSON.parse(config[k] as string);
        } catch {
          /* ogiltig JSON: sparas som den skrevs */
        }
      }
    }
    if (editConn.connector_type === "2c8" && editConfigFields.mode === "api") {
      config.verify_ssl = editConfigFields.verify_ssl !== "false";
    }

    // Only include credentials if user actually filled in at least one field
    const filledCreds: Record<string, string> = {};
    for (const [k, v] of Object.entries(editCredFields)) {
      if (v && v.trim()) filledCreds[k] = v.trim();
    }
    const hasNewCredentials = Object.keys(filledCreds).length > 0;

    const updateData: Record<string, unknown> = {
      name: editName,
      description: editDescription || undefined,
      config,
    };
    // Only send credentials key if user explicitly provided new values
    if (hasNewCredentials) {
      updateData.credentials = filledCreds;
    }

    try {
      const updated: Connection = await updateMutation.mutateAsync({
        id: editConn.id,
        data: updateData,
      });
      if (updated.credentials_cleared) {
        // The platform does not send stored credentials to a new host.
        enqueueSnackbar(
          "Connection updated. The address or the TLS check changed, so the stored credentials were removed – edit the connection and enter them again.",
          { variant: "warning", autoHideDuration: 10000 },
        );
      } else {
        enqueueSnackbar("Connection updated", { variant: "success" });
      }
      setEditConn(null);
    } catch {
      enqueueSnackbar("Failed to update connection", { variant: "error" });
    }
  };

  // Form state
  const [connectorType, setConnectorType] = useState<ConnectorType>("2c8");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [mode, setMode] = useState("mock");
  const [configFields, setConfigFields] = useState<Record<string, string>>({});
  const [credentialFields, setCredentialFields] = useState<Record<string, string>>({});
  const [resourceType, setResourceType] = useState("models");
  const [restAuthType, setRestAuthType] = useState("none");
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvDelimiter, setCsvDelimiter] = useState("auto");

  const isApiMode = mode === "api";

  const resetForm = () => {
    setActiveStep(0); setConnectorType("2c8"); setName(""); setDescription("");
    setMode("mock"); setConfigFields({}); setCredentialFields({}); setResourceType("models"); setRestAuthType("none");
    setCsvFile(null); setCsvDelimiter("auto");
  };

  const setConfig = (key: string, value: string) => setConfigFields((p) => ({ ...p, [key]: value }));
  const setCred = (key: string, value: string) => setCredentialFields((p) => ({ ...p, [key]: value }));

  const handleCreate = async () => {
    // CSV upload: use the dedicated endpoint
    if (connectorType === "csv") {
      if (!csvFile) return;
      const formData = new FormData();
      formData.append("file", csvFile);
      formData.append("name", name);
      formData.append("description", description);
      formData.append("delimiter", csvDelimiter);
      try {
        const resp = await client.post("/csv/upload", formData, { headers: { "Content-Type": "multipart/form-data" } });
        enqueueSnackbar(`CSV uploaded: ${resp.data.total_records} records imported`, { variant: "success" });
        setDialogOpen(false);
        resetForm();
      } catch (err: any) {
        enqueueSnackbar(err.response?.data?.detail || "CSV upload failed", { variant: "error" });
      }
      return;
    }

    const config: Record<string, unknown> = { ...configFields };
    if (hasMode(connectorType)) config.mode = mode;
    if (connectorType === "2c8" && isApiMode) {
      config.resource_type = resourceType;
      config.verify_ssl = configFields.verify_ssl !== "false";
    }
    if (connectorType === "generic_rest") config.auth_type = restAuthType;

    const credentials: Record<string, string> = {};
    for (const [k, v] of Object.entries(credentialFields)) {
      if (v) credentials[k] = v;
    }

    const body: ConnectionCreate = {
      name,
      connector_type: connectorType,
      description: description || undefined,
      config,
      credentials: Object.keys(credentials).length > 0 ? credentials : undefined,
      auth_type: (connectorType === "sharepoint" && isApiMode) || connectorType === "excel_sharepoint" ? "oauth2"
        : connectorType === "generic_rest" ? restAuthType
        : isApiMode ? "api_key" : "none",
    };

    try {
      await createMutation.mutateAsync(body);
      enqueueSnackbar("Connection created! Click the play button to test it.", { variant: "success" });
      setDialogOpen(false);
      resetForm();
    } catch {
      enqueueSnackbar("Failed to create connection", { variant: "error" });
    }
  };

  const handleTest = async (id: string) => {
    const r = await testMutation.mutateAsync(id);
    enqueueSnackbar(r.success ? "Connection OK" : `Test failed: ${r.error || "unknown"}`, {
      variant: r.success ? "success" : "error",
    });
  };

  // ── Step 1: Choose connector ────────────────────────────────────────

  const renderStep0 = () => (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <FormControl fullWidth>
        <InputLabel>Connector Type</InputLabel>
        <Select value={connectorType} label="Connector Type"
          onChange={(e) => { setConnectorType(e.target.value as ConnectorType); setConfigFields({}); setCredentialFields({}); setMode("mock"); setRestAuthType("none"); }}
        >
          {Object.entries(CONNECTOR_INFO).map(([key, c]) => (
            <MenuItem key={key} value={key}>{c.label}</MenuItem>
          ))}
        </Select>
      </FormControl>
      <Alert severity="info">{CONNECTOR_INFO[connectorType].description}</Alert>
      <TextField label="Connection Name" required fullWidth value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder={`e.g. ${CONNECTOR_INFO[connectorType].label} Production`}
        helperText="A name to identify this connection"
      />
      <TextField label="Description (optional)" fullWidth multiline rows={2} value={description}
        onChange={(e) => setDescription(e.target.value)} placeholder="What is this connection used for?"
      />
    </Box>
  );

  // ── Step 2: Configure source ────────────────────────────────────────

  const renderStep1 = () => {
    if (connectorType === "csv") return renderCsvConfig();
    if (connectorType === "generic_rest") return renderGenericRestConfig();
    if (connectorType === "sharepoint") return renderSharePointConfig();
    if (connectorType === "excel_sharepoint") return renderExcelConfig();
    return render2C8Config();
  };

  const renderCsvConfig = () => (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Box
        sx={{
          border: "2px dashed", borderColor: csvFile ? "success.main" : "grey.300",
          borderRadius: 2, p: 3, textAlign: "center", cursor: "pointer",
          "&:hover": { borderColor: "primary.main", bgcolor: "action.hover" },
        }}
        onClick={() => {
          const input = document.createElement("input");
          input.type = "file";
          input.accept = ".csv,.tsv,.txt";
          input.onchange = (e) => {
            const f = (e.target as HTMLInputElement).files?.[0];
            if (f) {
              setCsvFile(f);
              if (!name) setName(f.name.replace(/\.(csv|tsv|txt)$/i, ""));
            }
          };
          input.click();
        }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const f = e.dataTransfer.files[0];
          if (f) {
            setCsvFile(f);
            if (!name) setName(f.name.replace(/\.(csv|tsv|txt)$/i, ""));
          }
        }}
      >
        {csvFile ? (
          <Typography sx={{ color: "success.main", fontWeight: 600 }}>
            {csvFile.name} ({(csvFile.size / 1024).toFixed(1)} KB)
          </Typography>
        ) : (
          <>
            <Typography>Click or drag a CSV file here</Typography>
            <Typography variant="caption" sx={{ color: "text.secondary" }}>Supports .csv, .tsv, .txt</Typography>
          </>
        )}
      </Box>
      <TextField label="Delimiter" select value={csvDelimiter} onChange={(e) => setCsvDelimiter(e.target.value)} sx={{ maxWidth: 200 }}>
        <MenuItem value="auto">Auto-detect</MenuItem>
        <MenuItem value=",">Comma (,)</MenuItem>
        <MenuItem value=";">Semicolon (;)</MenuItem>
        <MenuItem value={"\t"}>Tab</MenuItem>
      </TextField>
    </Box>
  );

  const render2C8Config = () => (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <FormControl fullWidth>
        <InputLabel>Mode</InputLabel>
        <Select value={mode} label="Mode" onChange={(e) => { setMode(e.target.value); setConfigFields({}); setCredentialFields({}); }}>
          <MenuItem value="mock">Demo / Mock data</MenuItem>
          <MenuItem value="api">Live 2C8 server</MenuItem>
        </Select>
        <FormHelperText>{mode === "mock" ? "Uses built-in sample process data — no server needed" : "Connect to a real 2C8 MT Backend server"}</FormHelperText>
      </FormControl>

      {!isApiMode && (
        <Alert severity="success">Mock mode uses 10 sample Swedish process records. Great for testing the platform without a 2C8 server.</Alert>
      )}

      {isApiMode && (
        <>
          <TextField label="Server URL" required fullWidth value={configFields.base_url || ""}
            onChange={(e) => setConfig("base_url", e.target.value)}
            placeholder="https://your-2c8-server.com"
            helperText="The base URL of your 2C8 server"
          />
          <TextField label="Repository ID" required fullWidth value={configFields.repository_id || ""}
            onChange={(e) => setConfig("repository_id", e.target.value)}
            placeholder="00000000-0000-0000-0000-000000000000"
            helperText="UUID of the 2C8 repository to fetch from"
          />

          <HelpPanel title="How do I find the Repository ID?">
            <ol>
              <li>Open the 2C8 admin panel or use the API</li>
              <li>Call <code>GET /mt-backend/api/v1/repositories</code> with your API key in the <code>X-API-Key</code> header</li>
              <li>The response lists all repositories with their UUIDs</li>
            </ol>
            <p>Example:</p>
            <code>curl https://your-server.com/mt-backend/api/v1/repositories -H "X-API-Key: YOUR_KEY"</code>
          </HelpPanel>

          <Divider />

          <FormControl fullWidth>
            <InputLabel>What to fetch</InputLabel>
            <Select value={resourceType} label="What to fetch" onChange={(e) => setResourceType(e.target.value)}>
              <MenuItem value="models">Models (process diagrams)</MenuItem>
              <MenuItem value="symbols">Symbols (objects)</MenuItem>
              <MenuItem value="lists">Lists (predefined queries)</MenuItem>
            </Select>
            <FormHelperText>
              {resourceType === "models" && "Fetches all process diagrams — the most common choice for EA integration"}
              {resourceType === "symbols" && "Fetches reusable objects like activities, roles, and systems"}
              {resourceType === "lists" && "Executes a predefined 2C8 list/report"}
            </FormHelperText>
          </FormControl>

          {resourceType === "lists" && (
            <TextField label="List ID" required fullWidth value={configFields.list_id || ""}
              onChange={(e) => setConfig("list_id", e.target.value)}
              placeholder="UUID of the 2C8 list"
              helperText="The UUID of the predefined list to execute — find it in the 2C8 admin panel"
            />
          )}

          <FormControlLabel
            control={
              <Checkbox
                checked={configFields.verify_ssl !== "false"}
                onChange={(e) => setConfig("verify_ssl", e.target.checked ? "true" : "false")}
              />
            }
            label="Verify TLS certificate"
          />
          <FormHelperText sx={{ mt: -1.5 }}>
            Uncheck only for internal AD-issued self-signed certificates.
          </FormHelperText>
        </>
      )}
    </Box>
  );

  const renderSharePointConfig = () => (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <FormControl fullWidth>
        <InputLabel>Mode</InputLabel>
        <Select value={mode} label="Mode" onChange={(e) => { setMode(e.target.value); setConfigFields({}); setCredentialFields({}); }}>
          <MenuItem value="mock">Demo / Mock data</MenuItem>
          <MenuItem value="api">Live SharePoint</MenuItem>
        </Select>
        <FormHelperText>{mode === "mock" ? "Uses built-in sample application data — no SharePoint needed" : "Connect to a real SharePoint site via Microsoft Graph API"}</FormHelperText>
      </FormControl>

      {!isApiMode && (
        <Alert severity="success">Mock mode uses 10 sample application records (SAP, Workday, ServiceNow, etc.). Great for testing.</Alert>
      )}

      {isApiMode && (
        <>
          <TextField label="Site ID" required fullWidth value={configFields.site_id || ""}
            onChange={(e) => setConfig("site_id", e.target.value)}
            placeholder="contoso.sharepoint.com,11111111-xxxx-xxxx,22222222-xxxx-xxxx"
            helperText="Format: hostname,site-collection-id,web-id"
          />

          <HelpPanel title="How do I find the Site ID?">
            <p>The Site ID is a combination of three values. You find them from your SharePoint site:</p>
            <ol>
              <li>
                <strong>Site Collection ID</strong> — Go to:<br />
                <code>https://YOUR-TENANT.sharepoint.com/sites/YOUR-SITE/_api/site/id</code><br />
                Copy the GUID shown on the page.
              </li>
              <li>
                <strong>Web ID</strong> — Go to:<br />
                <code>https://YOUR-TENANT.sharepoint.com/sites/YOUR-SITE/_api/web/id</code><br />
                Copy the GUID shown on the page.
              </li>
              <li>
                <strong>Combine them</strong> as:<br />
                <code>YOUR-TENANT.sharepoint.com,SITE-COLLECTION-ID,WEB-ID</code>
              </li>
            </ol>
            <p>Example:<br /><code>contoso.sharepoint.com,11111111-1111-1111-1111-111111111111,22222222-2222-2222-2222-222222222222</code></p>
          </HelpPanel>

          <TextField label="List ID" required fullWidth value={configFields.list_id || ""}
            onChange={(e) => setConfig("list_id", e.target.value)}
            placeholder="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
            helperText="The GUID of the SharePoint list to import"
          />

          <HelpPanel title="How do I find the List ID?">
            <ol>
              <li>Open the SharePoint list in your browser</li>
              <li>Click the <strong>gear icon</strong> (top right) → <strong>List settings</strong></li>
              <li>Look at the URL — it contains <code>List=%7B...%7D</code></li>
              <li>The GUID between <code>%7B</code> and <code>%7D</code> is your List ID</li>
            </ol>
            <p>Example URL:<br /><code>/_layouts/15/listedit.aspx?List=%7Baaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee%7D</code></p>
            <p>List ID: <code>aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee</code></p>
          </HelpPanel>
        </>
      )}
    </Box>
  );

  const renderExcelConfig = () => (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <TextField label="File address" required fullWidth value={configFields.file_url || ""}
        onChange={(e) => setConfig("file_url", e.target.value)}
        placeholder="https://contoso.sharepoint.com/sites/Architecture/Shared%20Documents/Systems.xlsx"
        helperText="The address of the .xlsx file in SharePoint"
      />
      <HelpPanel title="Which address should I use?">
        <p><strong>Recommended – the direct address.</strong> In SharePoint, select the file → <strong>Details</strong> (ⓘ) → <strong>Path</strong> → copy. It looks like <code>https://TENANT.sharepoint.com/sites/SITE/Shared%20Documents/Systems.xlsx</code>. Works with the narrow permission <code>Sites.Selected</code>.</p>
        <p><strong>A sharing link</strong> (<code>…sharepoint.com/:x:/…</code>) or the address of the file open in Excel on the web also work, but require <code>Sites.Read.All</code> or <code>Files.Read.All</code>.</p>
      </HelpPanel>
      <TextField label="Table (optional)" fullWidth value={configFields.table || ""}
        onChange={(e) => setConfig("table", e.target.value)}
        placeholder="Systemlista"
        helperText="Name of an Excel table (Format as Table). Takes precedence over the sheet. In Excel: click in the table → Table Design → Table Name."
      />
      <TextField label="Sheet (optional)" fullWidth value={configFields.sheet || ""}
        onChange={(e) => setConfig("sheet", e.target.value)}
        placeholder="Sheet1"
        helperText="Used when no table is given. Empty = the first sheet. The first non-empty row is the header row."
      />
      <TextField label="ID column (optional)" fullWidth value={configFields.id_column || ""}
        onChange={(e) => setConfig("id_column", e.target.value)}
        placeholder="System-ID"
        helperText="Column with a unique, stable value per row – it is how the EA portal recognises a system between imports. Empty = the first column."
      />
    </Box>
  );

  const renderGenericRestConfig = () => (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <TextField label="API URL" required fullWidth value={configFields.url || ""}
        onChange={(e) => setConfig("url", e.target.value)}
        placeholder="https://api.example.com/data"
        helperText="The full URL of the API endpoint to fetch data from"
      />
      <TextField label="Data Path (optional)" fullWidth value={configFields.data_path || ""}
        onChange={(e) => setConfig("data_path", e.target.value)}
        placeholder="data.items"
        helperText="Dot-separated path to the records array in the response. Leave empty if the response is already an array."
      />

      <HelpPanel title="What is Data Path?">
        <p>If the API returns data nested inside an object, specify the path to the array of records.</p>
        <p>Example: if the API returns <code>{`{"data": {"items": [...]}}`}</code>, set Data Path to <code>data.items</code></p>
        <p>If the API returns a plain array <code>[...]</code>, leave this empty.</p>
      </HelpPanel>

      <Divider />
      <FormControl fullWidth>
        <InputLabel>Authentication</InputLabel>
        <Select value={restAuthType} label="Authentication" onChange={(e) => { setRestAuthType(e.target.value); setCredentialFields({}); }}>
          <MenuItem value="none">No authentication</MenuItem>
          <MenuItem value="bearer">Bearer token</MenuItem>
          <MenuItem value="api_key">API key in header</MenuItem>
        </Select>
        <FormHelperText>How should the platform authenticate with this API?</FormHelperText>
      </FormControl>
    </Box>
  );

  // ── Step 3: Credentials ─────────────────────────────────────────────

  const renderStep2 = () => {
    if (connectorType === "csv") {
      return <Alert severity="info">No credentials needed for CSV files. You can skip this step.</Alert>;
    }
    if (connectorType === "2c8" && !isApiMode) {
      return <Alert severity="info">No credentials needed for mock mode. You can skip this step.</Alert>;
    }
    if (connectorType === "sharepoint" && !isApiMode) {
      return <Alert severity="info">No credentials needed for mock mode. You can skip this step.</Alert>;
    }
    if (connectorType === "generic_rest" && restAuthType === "none") {
      return <Alert severity="info">No authentication configured. You can skip this step.</Alert>;
    }

    if (connectorType === "2c8" && isApiMode) {
      return (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <Alert severity="warning">Credentials are encrypted before storage and never shown in API responses.</Alert>
          <TextField label="API Key" required fullWidth type="password" autoComplete="new-password" value={credentialFields.api_key || ""}
            onChange={(e) => setCred("api_key", e.target.value)}
            helperText="Your 2C8 API key — used as a Bearer token for authentication"
          />
          <HelpPanel title="How do I get a 2C8 API key?">
            <ol>
              <li>Log in to your 2C8 MT Backend admin panel</li>
              <li>Navigate to <strong>API key management</strong></li>
              <li>Click <strong>Create new API key</strong></li>
              <li>Set a name (e.g. "Integration Platform") and an expiration date</li>
              <li>Copy the generated API key value</li>
            </ol>
            <p>The API documentation is available at <code>https://developer.2c8.com/</code></p>
          </HelpPanel>
        </Box>
      );
    }

    if ((connectorType === "sharepoint" && isApiMode) || connectorType === "excel_sharepoint") {
      return (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <Alert severity="warning">Credentials are encrypted before storage and never shown in API responses.</Alert>

          <Typography variant="subtitle2" sx={{ color: "text.secondary" }}>Azure AD App Registration</Typography>

          <TextField label="Tenant ID" required fullWidth autoComplete="off" value={credentialFields.tenant_id || ""}
            onChange={(e) => setCred("tenant_id", e.target.value)}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            helperText="Azure AD Directory (tenant) ID"
          />
          <TextField label="Client ID" required fullWidth autoComplete="off" value={credentialFields.client_id || ""}
            onChange={(e) => setCred("client_id", e.target.value)}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            helperText="Application (client) ID from your app registration"
          />
          <TextField label="Client Secret" required fullWidth type="password" autoComplete="new-password" value={credentialFields.client_secret || ""}
            onChange={(e) => setCred("client_secret", e.target.value)}
            helperText="The secret value from Certificates & secrets"
          />

          <HelpPanel title="How do I set up an Azure AD app for SharePoint?">
            <p><strong>Step 1: Register an app</strong></p>
            <ol>
              <li>Go to <Link href="https://portal.azure.com" target="_blank" rel="noopener">portal.azure.com</Link></li>
              <li>Navigate to <strong>Microsoft Entra ID</strong> → <strong>App registrations</strong> → <strong>New registration</strong></li>
              <li>Name: <code>Integration Platform</code></li>
              <li>Supported account types: <strong>Single tenant</strong></li>
              <li>Click <strong>Register</strong></li>
            </ol>

            <p><strong>Step 2: Add API permissions</strong></p>
            <ol>
              <li>In your app → <strong>API permissions</strong> → <strong>Add a permission</strong></li>
              <li>Choose <strong>Microsoft Graph</strong> → <strong>Application permissions</strong></li>
              {connectorType === "excel_sharepoint" ? (
                <li>Add <code>Sites.Selected</code> (read access to one site only – an admin then grants the app <code>read</code> on that site, e.g. with PnP PowerShell <code>Grant-PnPAzureADAppSitePermission -AppId CLIENT-ID -DisplayName "Integration Platform" -Site https://TENANT.sharepoint.com/sites/SITE -Permissions Read</code>), or the broader <code>Sites.Read.All</code></li>
              ) : (
                <li>Search and add: <code>Sites.Read.All</code></li>
              )}
              <li>Click <strong>Grant admin consent</strong> (requires admin rights in your organization)</li>
            </ol>

            <p><strong>Step 3: Create a client secret</strong></p>
            <ol>
              <li>Go to <strong>Certificates &amp; secrets</strong> → <strong>New client secret</strong></li>
              <li>Add a description and choose an expiry period</li>
              <li>Copy the <strong>Value</strong> immediately — it is only shown once</li>
            </ol>

            <p><strong>Step 4: Copy the IDs</strong></p>
            <p>Go to your app's <strong>Overview</strong> page and copy:</p>
            <ul>
              <li><strong>Application (client) ID</strong> → paste in "Client ID" above</li>
              <li><strong>Directory (tenant) ID</strong> → paste in "Tenant ID" above</li>
            </ul>

            <p>The platform will automatically request access tokens using these credentials — no manual token management needed.</p>
          </HelpPanel>
        </Box>
      );
    }

    // Generic REST
    if (restAuthType === "bearer") {
      return (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <Alert severity="warning">Credentials are encrypted before storage.</Alert>
          <TextField label="Bearer Token" required fullWidth type="password" autoComplete="new-password" value={credentialFields.token || ""}
            onChange={(e) => setCred("token", e.target.value)}
            helperText="The bearer token value — sent as: Authorization: Bearer <token>"
          />
        </Box>
      );
    }

    if (restAuthType === "api_key") {
      return (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <Alert severity="warning">Credentials are encrypted before storage.</Alert>
          <TextField label="API Key" required fullWidth type="password" autoComplete="new-password" value={credentialFields.api_key || ""}
            onChange={(e) => setCred("api_key", e.target.value)}
            helperText="The API key value"
          />
          <TextField label="Header Name (optional)" fullWidth value={configFields.api_key_header || ""}
            onChange={(e) => setConfig("api_key_header", e.target.value)}
            placeholder="X-Api-Key"
            helperText="The HTTP header name to send the key in (default: X-Api-Key)"
          />
        </Box>
      );
    }

    return null;
  };

  // ── Step 4: Review ──────────────────────────────────────────────────

  const renderStep3 = () => {
    const config: Record<string, unknown> = { ...configFields };
    if (hasMode(connectorType)) config.mode = mode;
    if (connectorType === "2c8" && isApiMode) config.resource_type = resourceType;
    if (connectorType === "generic_rest") config.auth_type = restAuthType;
    const hasCreds = (connectorType === "sharepoint" && isApiMode) || connectorType === "excel_sharepoint"
      ? !!(credentialFields.tenant_id && credentialFields.client_id && credentialFields.client_secret)
      : Object.values(credentialFields).some((v) => v);

    return (
      <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <Alert severity="info">Review your settings, then click "Create Connection".</Alert>
        <Card variant="outlined">
          <CardContent sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
            <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
              <Chip label={CONNECTOR_INFO[connectorType].label} color="primary" size="small" />
              {hasMode(connectorType) && <Chip label={mode === "mock" ? "Mock" : "Live API"} variant="outlined" size="small" />}
            </Box>
            <Typography variant="h6">{name}</Typography>
            {description && <Typography variant="body2" sx={{ color: "text.secondary" }}>{description}</Typography>}

            <Divider sx={{ my: 1 }} />

            {Object.entries(config).filter(([, v]) => v).map(([k, v]) => (
              <Box key={k} sx={{ display: "flex", gap: 1 }}>
                <Typography variant="body2" sx={{ color: "text.secondary", minWidth: 120 }}>{k}:</Typography>
                <Typography variant="body2" sx={{ fontFamily: "monospace", wordBreak: "break-all" }}>{String(v)}</Typography>
              </Box>
            ))}

            <Divider sx={{ my: 1 }} />
            <Box sx={{ display: "flex", gap: 1 }}>
              <Typography variant="body2" sx={{ color: "text.secondary", minWidth: 120 }}>Credentials:</Typography>
              <Typography variant="body2">{hasCreds ? "Provided (will be encrypted)" : "None"}</Typography>
            </Box>
          </CardContent>
        </Card>

        <Alert severity="success">
          After creating, click the <strong>play button</strong> in the connections table to test the connection.
        </Alert>
      </Box>
    );
  };

  // ── Step navigation ─────────────────────────────────────────────────

  const steps = [
    { label: "Choose connector", render: renderStep0 },
    { label: "Configure source", render: renderStep1 },
    { label: "Credentials", render: renderStep2 },
    { label: "Review & create", render: renderStep3 },
  ];

  const canProceed = () => {
    if (activeStep === 0) return name.trim().length > 0;
    if (activeStep === 1) {
      if (connectorType === "csv") return !!csvFile;
      if (connectorType === "generic_rest") return !!configFields.url;
      if (connectorType === "excel_sharepoint") return !!configFields.file_url?.trim();
      if (!isApiMode) return true;
      if (connectorType === "sharepoint") return !!(configFields.site_id && configFields.list_id);
      if (connectorType === "2c8") {
        const hasBase = !!(configFields.base_url && configFields.repository_id);
        if (resourceType === "lists") return hasBase && !!configFields.list_id;
        return hasBase;
      }
      return true;
    }
    if (activeStep === 2 && connectorType === "excel_sharepoint") {
      return !!(credentialFields.tenant_id && credentialFields.client_id && credentialFields.client_secret);
    }
    return true;
  };

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Typography variant="h4">Connections</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => { resetForm(); setDialogOpen(true); }}>
          New Connection
        </Button>
      </Box>

      <TableContainer component={Card}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Last Tested</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && <TableRow><TableCell colSpan={5}>Loading...</TableCell></TableRow>}
            {connections?.length === 0 && <TableRow><TableCell colSpan={5}>No connections yet. Click "New Connection" to get started.</TableCell></TableRow>}
            {connections?.map((conn) => {
              const label = CONNECTOR_INFO[conn.connector_type as ConnectorType]?.label || conn.connector_type;
              return (
                <TableRow key={conn.id}>
                  <TableCell>{conn.name}</TableCell>
                  <TableCell>{label}</TableCell>
                  <TableCell><StatusChip status={conn.status} /></TableCell>
                  <TableCell>{conn.last_tested_at ? new Date(conn.last_tested_at).toLocaleString() : "-"}</TableCell>
                  <TableCell align="right">
                    <IconButton size="small" onClick={() => handleTest(conn.id)} title="Test connection"><PlayArrowIcon /></IconButton>
                    <IconButton size="small" onClick={() => openEdit(conn)} title="Edit"><EditIcon /></IconButton>
                    <IconButton size="small" color="error" onClick={() => deleteMutation.mutate(conn.id)} title="Delete"><DeleteIcon /></IconButton>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>New Connection</DialogTitle>
        <DialogContent>
          <Stepper activeStep={activeStep} orientation="vertical" sx={{ mt: 1 }}>
            {steps.map((step, index) => (
              <Step key={step.label}>
                <StepLabel>{step.label}</StepLabel>
                <StepContent>
                  <Box sx={{ mb: 2 }}>{step.render()}</Box>
                  <Box sx={{ display: "flex", gap: 1 }}>
                    {index > 0 && <Button size="small" onClick={() => setActiveStep(index - 1)}>Back</Button>}
                    {index < steps.length - 1 ? (
                      <Button size="small" variant="contained" disabled={!canProceed()} onClick={() => setActiveStep(index + 1)}>
                        Continue
                      </Button>
                    ) : (
                      <Button size="small" variant="contained" color="success" onClick={handleCreate} disabled={createMutation.isPending}>
                        {createMutation.isPending ? "Creating..." : "Create Connection"}
                      </Button>
                    )}
                  </Box>
                </StepContent>
              </Step>
            ))}
          </Stepper>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
        </DialogActions>
      </Dialog>

      {/* ── Edit connection dialog ───────────────────────────────────────── */}
      <Dialog open={!!editConn} onClose={() => setEditConn(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Edit Connection</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
          <Chip label={CONNECTOR_INFO[editConn?.connector_type as ConnectorType]?.label || editConn?.connector_type} color="primary" size="small" sx={{ alignSelf: "flex-start" }} />

          <TextField label="Connection Name" fullWidth value={editName}
            onChange={(e) => setEditName(e.target.value)}
          />
          <TextField label="Description" fullWidth multiline rows={2} value={editDescription}
            onChange={(e) => setEditDescription(e.target.value)}
          />

          <Divider><Typography variant="caption" sx={{ color: "text.secondary" }}>Configuration</Typography></Divider>

          {/* ── SharePoint config fields ── */}
          {editConn?.connector_type === "sharepoint" && (
            <>
              <FormControl fullWidth>
                <InputLabel>Mode</InputLabel>
                <Select value={editConfigFields.mode || "mock"} label="Mode"
                  onChange={(e) => setEditConfig2("mode", e.target.value)}>
                  <MenuItem value="mock">Demo / Mock data</MenuItem>
                  <MenuItem value="api">Live SharePoint</MenuItem>
                </Select>
              </FormControl>
              {editConfigFields.mode === "api" && (
                <>
                  <TextField label="Site ID" fullWidth value={editConfigFields.site_id || ""}
                    onChange={(e) => setEditConfig2("site_id", e.target.value)}
                    placeholder="hostname,site-collection-id,web-id"
                    helperText="Format: tenant.sharepoint.com,site-guid,web-guid"
                  />
                  <TextField label="List ID" fullWidth value={editConfigFields.list_id || ""}
                    onChange={(e) => setEditConfig2("list_id", e.target.value)}
                    placeholder="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
                    helperText="SharePoint list GUID — found in List Settings URL"
                  />
                </>
              )}
            </>
          )}

          {/* ── Excel in SharePoint config fields ── */}
          {editConn?.connector_type === "excel_sharepoint" && (
            <>
              <TextField label="File address" fullWidth value={editConfigFields.file_url || ""}
                onChange={(e) => setEditConfig2("file_url", e.target.value)}
                helperText="The address of the .xlsx file in SharePoint"
              />
              <TextField label="Table (optional)" fullWidth value={editConfigFields.table || ""}
                onChange={(e) => setEditConfig2("table", e.target.value)}
                helperText="Takes precedence over the sheet"
              />
              <TextField label="Sheet (optional)" fullWidth value={editConfigFields.sheet || ""}
                onChange={(e) => setEditConfig2("sheet", e.target.value)}
                helperText="Empty = the first sheet"
              />
              <TextField label="ID column (optional)" fullWidth value={editConfigFields.id_column || ""}
                onChange={(e) => setEditConfig2("id_column", e.target.value)}
                helperText="Unique, stable value per row. Empty = the first column"
              />
            </>
          )}

          {/* ── 2C8 config fields ── */}
          {editConn?.connector_type === "2c8" && (
            <>
              <FormControl fullWidth>
                <InputLabel>Mode</InputLabel>
                <Select value={editConfigFields.mode || "mock"} label="Mode"
                  onChange={(e) => setEditConfig2("mode", e.target.value)}>
                  <MenuItem value="mock">Demo / Mock data</MenuItem>
                  <MenuItem value="api">Live 2C8 server</MenuItem>
                </Select>
              </FormControl>
              {editConfigFields.mode === "api" && (
                <>
                  <TextField label="Server URL" fullWidth value={editConfigFields.base_url || ""}
                    onChange={(e) => setEditConfig2("base_url", e.target.value)}
                    placeholder="https://your-2c8-server.com"
                  />
                  <TextField label="Repository ID" fullWidth value={editConfigFields.repository_id || ""}
                    onChange={(e) => setEditConfig2("repository_id", e.target.value)}
                    placeholder="UUID"
                  />
                  <FormControl fullWidth>
                    <InputLabel>What to fetch</InputLabel>
                    <Select value={editConfigFields.resource_type || "models"} label="What to fetch"
                      onChange={(e) => setEditConfig2("resource_type", e.target.value)}>
                      <MenuItem value="models">Models (process diagrams)</MenuItem>
                      <MenuItem value="symbols">Symbols (objects)</MenuItem>
                      <MenuItem value="lists">Lists (predefined queries)</MenuItem>
                    </Select>
                  </FormControl>
                  {editConfigFields.resource_type === "lists" && (
                    <TextField label="List ID" fullWidth value={editConfigFields.list_id || ""}
                      onChange={(e) => setEditConfig2("list_id", e.target.value)}
                      placeholder="UUID of the 2C8 list"
                    />
                  )}
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={editConfigFields.verify_ssl !== "false"}
                        onChange={(e) => setEditConfig2("verify_ssl", e.target.checked ? "true" : "false")}
                      />
                    }
                    label="Verify TLS certificate"
                  />
                </>
              )}
            </>
          )}

          {/* ── Generic REST config fields ── */}
          {editConn?.connector_type === "generic_rest" && (
            <>
              <TextField label="API URL" fullWidth value={editConfigFields.url || ""}
                onChange={(e) => setEditConfig2("url", e.target.value)}
                placeholder="https://api.example.com/data"
              />
              <TextField label="Data Path" fullWidth value={editConfigFields.data_path || ""}
                onChange={(e) => setEditConfig2("data_path", e.target.value)}
                placeholder="data.items"
                helperText="Dot path to the records array in the response (leave empty if response is already an array)"
              />
              <FormControl fullWidth>
                <InputLabel>Authentication</InputLabel>
                <Select value={editConfigFields.auth_type || "none"} label="Authentication"
                  onChange={(e) => setEditConfig2("auth_type", e.target.value)}>
                  <MenuItem value="none">No authentication</MenuItem>
                  <MenuItem value="bearer">Bearer token</MenuItem>
                  <MenuItem value="api_key">API key in header</MenuItem>
                </Select>
              </FormControl>
              {editConfigFields.auth_type === "api_key" && (
                <TextField label="API Key Header Name" fullWidth value={editConfigFields.api_key_header || ""}
                  onChange={(e) => setEditConfig2("api_key_header", e.target.value)}
                  placeholder="X-Api-Key"
                  helperText="Default: X-Api-Key"
                />
              )}
            </>
          )}

          {/* ── Credentials section ── */}
          {((editConn?.connector_type === "sharepoint" && editConfigFields.mode === "api") ||
            editConn?.connector_type === "excel_sharepoint" ||
            (editConn?.connector_type === "2c8" && editConfigFields.mode === "api") ||
            (editConn?.connector_type === "generic_rest" && editConfigFields.auth_type !== "none")) && (
            <>
              <Divider><Typography variant="caption" sx={{ color: "text.secondary" }}>Credentials</Typography></Divider>
              <Alert severity="info" sx={{ py: 0.5 }}>Leave fields empty to keep existing credentials. Fill in to replace.</Alert>

              {(editConn?.connector_type === "sharepoint" || editConn?.connector_type === "excel_sharepoint") && (
                <>
                  <TextField label="Tenant ID" fullWidth autoComplete="off" value={editCredFields.tenant_id || ""}
                    onChange={(e) => setEditCred("tenant_id", e.target.value)}
                    placeholder="Leave empty to keep current"
                    helperText="Azure AD Directory (tenant) ID"
                  />
                  <TextField label="Client ID" fullWidth autoComplete="off" value={editCredFields.client_id || ""}
                    onChange={(e) => setEditCred("client_id", e.target.value)}
                    placeholder="Leave empty to keep current"
                    helperText="Application (client) ID from Azure app registration"
                  />
                  <TextField label="Client Secret" fullWidth type="password" autoComplete="new-password" value={editCredFields.client_secret || ""}
                    onChange={(e) => setEditCred("client_secret", e.target.value)}
                    placeholder="Leave empty to keep current"
                    helperText="Client secret value"
                  />
                </>
              )}

              {editConn?.connector_type === "2c8" && (
                <TextField label="API Key" fullWidth type="password" autoComplete="new-password" value={editCredFields.api_key || ""}
                  onChange={(e) => setEditCred("api_key", e.target.value)}
                  placeholder="Leave empty to keep current"
                  helperText="2C8 API key — sent in the X-API-Key header"
                />
              )}

              {editConn?.connector_type === "generic_rest" && editConfigFields.auth_type === "bearer" && (
                <TextField label="Bearer Token" fullWidth type="password" autoComplete="new-password" value={editCredFields.token || ""}
                  onChange={(e) => setEditCred("token", e.target.value)}
                  placeholder="Leave empty to keep current"
                />
              )}

              {editConn?.connector_type === "generic_rest" && editConfigFields.auth_type === "api_key" && (
                <TextField label="API Key" fullWidth type="password" autoComplete="new-password" value={editCredFields.api_key || ""}
                  onChange={(e) => setEditCred("api_key", e.target.value)}
                  placeholder="Leave empty to keep current"
                />
              )}
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditConn(null)}>Cancel</Button>
          <Button variant="contained" onClick={handleUpdate} disabled={updateMutation.isPending}>
            {updateMutation.isPending ? "Saving..." : "Save Changes"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
