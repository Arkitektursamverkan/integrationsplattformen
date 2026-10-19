import { useState, useEffect, useMemo, lazy, Suspense } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Alert, Box, Button, Card, CardContent, Checkbox, Chip, Divider, FormControl,
  FormControlLabel, IconButton, InputLabel, MenuItem, Select, Table, TableBody,
  TableCell, TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import SaveIcon from "@mui/icons-material/Save";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import ScheduleIcon from "@mui/icons-material/Schedule";
import CronBuilder, { describeCron } from "@/components/common/CronBuilder";
import WebhookIcon from "@mui/icons-material/Webhook";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import ViewListIcon from "@mui/icons-material/ViewList";
import AccountTreeIcon from "@mui/icons-material/AccountTree";

const FlowBuilderCanvas = lazy(() => import("@/components/flow-builder/FlowBuilder"));
import { useFlow, useExecuteFlow, useUpdateFlow } from "@/api/flows";
import { useExecutions } from "@/api/executions";
import { useConnections } from "@/api/connections";
import { useDataRecords } from "@/api/data";
import { useSchedules, useCreateSchedule, useDeleteSchedule, useUpdateSchedule, type Schedule } from "@/api/schedules";
import { useWebhooks, useCreateWebhook, useDeleteWebhook, type Webhook } from "@/api/webhooks";
import StatusChip from "@/components/common/StatusChip";
import { useSnackbar } from "notistack";
import { copyToClipboard } from "@/utils/clipboard";

// ── Operation definitions ────────────────────────────────────────────────────

const OPERATION_TYPES = [
  { type: "transform", label: "Field Mapping", icon: "🔀", color: "#e65100", description: "Map, rename, and transform fields" },
  { type: "add_column", label: "Add Column", icon: "➕", color: "#1565c0", description: "Create new columns from expressions or templates" },
  { type: "remove", label: "Remove Fields", icon: "🗑", color: "#c62828", description: "Remove unwanted fields" },
  { type: "rename", label: "Rename Fields", icon: "✏️", color: "#6a1b9a", description: "Rename fields" },
  { type: "filter", label: "Filter Rows", icon: "🔍", color: "#2e7d32", description: "Keep only matching records" },
  { type: "replace", label: "Find & Replace", icon: "🔄", color: "#0277bd", description: "Replace text in field values" },
  { type: "substring", label: "Extract Text", icon: "✂️", color: "#ad1457", description: "Extract part of a text field" },
  { type: "split_column", label: "Split Column", icon: "↔️", color: "#f57f17", description: "Split a field by delimiter" },
  { type: "math", label: "Math", icon: "🔢", color: "#283593", description: "Arithmetic on numeric fields" },
  { type: "combine", label: "Combine Fields", icon: "🔗", color: "#00695c", description: "Merge fields into one" },
  { type: "lookup", label: "Value Lookup", icon: "📋", color: "#4e342e", description: "Map values using a lookup table" },
  { type: "sort", label: "Sort", icon: "↕️", color: "#37474f", description: "Sort records" },
  { type: "trim", label: "Trim Whitespace", icon: "🧽", color: "#795548", description: "Remove leading/trailing spaces from values" },
  { type: "deduplicate", label: "Deduplicate", icon: "🧹", color: "#546e7a", description: "Remove duplicate records" },
];

const TRANSFORMS = [
  { value: "", label: "None" }, { value: "to_string", label: "To text" }, { value: "to_int", label: "To integer" },
  { value: "to_float", label: "To decimal" }, { value: "to_lower", label: "Lowercase" }, { value: "to_upper", label: "Uppercase" },
  { value: "trim", label: "Trim" }, { value: "strip_html", label: "Remove HTML" }, { value: "date_parse", label: "Parse date" },
];

const FILTER_OPS = [
  { value: "eq", label: "equals" }, { value: "neq", label: "not equals" }, { value: "contains", label: "contains" },
  { value: "not_contains", label: "not contains" }, { value: "starts_with", label: "starts with" },
  { value: "gt", label: ">" }, { value: "lt", label: "<" }, { value: "gte", label: ">=" }, { value: "lte", label: "<=" },
  { value: "exists", label: "exists" }, { value: "not_exists", label: "is empty" },
];

const MATH_OPS = [
  { value: "add", label: "Add (+)" }, { value: "subtract", label: "Subtract (-)" },
  { value: "multiply", label: "Multiply (×)" }, { value: "divide", label: "Divide (÷)" },
  { value: "round", label: "Round" }, { value: "abs", label: "Absolute" },
  { value: "percent", label: "Percentage (%)" },
];

// ── Types ────────────────────────────────────────────────────────────────────

interface PipelineStage {
  step_type: string;
  config: Record<string, unknown>;
}

// ── Stage config editors ─────────────────────────────────────────────────────

// ── Field picker — dropdown with available field names ────────────────────────

function FieldPicker({ label, value, onChange, fields, required, helperText }: {
  label: string; value: string; onChange: (v: string) => void; fields: string[];
  required?: boolean; helperText?: string;
}) {
  if (fields.length === 0) {
    // Fallback to text field if no fields available
    return <TextField size="small" label={label} value={value} onChange={(e) => onChange(e.target.value)} fullWidth required={required} helperText={helperText} />;
  }
  return (
    <FormControl fullWidth size="small" required={required}>
      <InputLabel>{label}</InputLabel>
      <Select value={fields.includes(value) ? value : ""} label={label} onChange={(e) => onChange(e.target.value)} displayEmpty>
        {value && !fields.includes(value) && <MenuItem value={value}>{value}</MenuItem>}
        {fields.map((f) => <MenuItem key={f} value={f}>{f}</MenuItem>)}
      </Select>
      {helperText && <Typography variant="caption" color="text.secondary" sx={{ ml: 1.5, mt: 0.5 }}>{helperText}</Typography>}
    </FormControl>
  );
}

function MultiFieldPicker({ label, value, onChange, fields, helperText }: {
  label: string; value: string[]; onChange: (v: string[]) => void; fields: string[];
  helperText?: string;
}) {
  if (fields.length === 0) {
    return <TextField size="small" label={label} value={(value || []).join(", ")} onChange={(e) => onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} fullWidth helperText={helperText} />;
  }
  return (
    <FormControl fullWidth size="small">
      <InputLabel>{label}</InputLabel>
      <Select multiple value={value || []} label={label} onChange={(e) => onChange(e.target.value as string[])}
        renderValue={(selected) => (
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
            {(selected as string[]).map((v) => <Chip key={v} label={v} size="small" />)}
          </Box>
        )}
      >
        {fields.map((f) => <MenuItem key={f} value={f}>{f}</MenuItem>)}
      </Select>
      {helperText && <Typography variant="caption" color="text.secondary" sx={{ ml: 1.5, mt: 0.5 }}>{helperText}</Typography>}
    </FormControl>
  );
}

function StageEditor({ stage, onChange, fields }: { stage: PipelineStage; onChange: (config: Record<string, unknown>) => void; fields: string[] }) {
  const c = stage.config;
  const set = (key: string, value: unknown) => onChange({ ...c, [key]: value });

  // Helper for list-in-config editing
  const getList = (key: string): Record<string, unknown>[] => (c[key] as Record<string, unknown>[]) || [];
  const setList = (key: string, list: Record<string, unknown>[]) => set(key, list);
  const addToList = (key: string, item: Record<string, unknown>) => setList(key, [...getList(key), item]);
  const updateInList = (key: string, i: number, field: string, value: unknown) => {
    const list = [...getList(key)]; list[i] = { ...list[i], [field]: value }; setList(key, list);
  };
  const removeFromList = (key: string, i: number) => setList(key, getList(key).filter((_, j) => j !== i));

  switch (stage.step_type) {
    case "transform":
      return (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <Typography variant="subtitle2">Field Mappings</Typography>
            <Button size="small" onClick={() => addToList("mappings", { source_field: "", target_field: "", transform: "" })}>+ Add mapping</Button>
          </Box>
          {getList("mappings").map((m, i) => (
            <Box key={i} sx={{ display: "flex", gap: 1, alignItems: "center" }}>
              <Box sx={{ flex: 1 }}><FieldPicker label="Source" value={String(m.source_field || "")} onChange={(v) => { updateInList("mappings", i, "source_field", v); if (!m.target_field) updateInList("mappings", i, "target_field", v); }} fields={fields} /></Box>
              <TextField size="small" label="Target" value={m.target_field || ""} onChange={(e) => updateInList("mappings", i, "target_field", e.target.value)} sx={{ flex: 1 }} />
              <TextField size="small" label="Transform" select value={m.transform || ""} onChange={(e) => updateInList("mappings", i, "transform", e.target.value)} sx={{ width: 130 }}>
                {TRANSFORMS.map((t) => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
              </TextField>
              <IconButton size="small" onClick={() => removeFromList("mappings", i)}><DeleteIcon fontSize="small" /></IconButton>
            </Box>
          ))}
          <Divider />
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <Typography variant="subtitle2">Computed Fields</Typography>
            <Button size="small" onClick={() => addToList("computed_fields", { field: "", value: "" })}>+ Add</Button>
          </Box>
          {getList("computed_fields").map((cf, i) => (
            <Box key={i} sx={{ display: "flex", gap: 1, alignItems: "center" }}>
              <TextField size="small" label="Field name" value={cf.field || ""} onChange={(e) => updateInList("computed_fields", i, "field", e.target.value)} sx={{ flex: 1 }} />
              <TextField size="small" label="Value" value={cf.value || ""} onChange={(e) => updateInList("computed_fields", i, "value", e.target.value)} sx={{ flex: 1 }} />
              <IconButton size="small" onClick={() => removeFromList("computed_fields", i)}><DeleteIcon fontSize="small" /></IconButton>
            </Box>
          ))}
        </Box>
      );

    case "add_column":
      return (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
          <TextField size="small" label="New column name" value={c.column || ""} onChange={(e) => set("column", e.target.value)} fullWidth />
          <TextField size="small" label="Mode" select value={c.mode || "static"} onChange={(e) => set("mode", e.target.value)} fullWidth>
            <MenuItem value="static">Static value</MenuItem>
            <MenuItem value="template">Template (use {`{field_name}`} placeholders)</MenuItem>
            <MenuItem value="concat">Concatenate fields</MenuItem>
            <MenuItem value="copy">Copy from another field</MenuItem>
            <MenuItem value="conditional">Conditional (if/else)</MenuItem>
          </TextField>
          {c.mode === "static" && <TextField size="small" label="Value" value={c.value || ""} onChange={(e) => set("value", e.target.value)} fullWidth />}
          {c.mode === "template" && <TextField size="small" label="Template" value={c.template || ""} onChange={(e) => set("template", e.target.value)} fullWidth placeholder="{Fråga} - {Bedömning}" helperText="Use {field_name} to insert field values" />}
          {c.mode === "concat" && (
            <>
              <MultiFieldPicker label="Fields to concatenate" value={c.fields as string[] || []} onChange={(v) => set("fields", v)} fields={fields} />
              <TextField size="small" label="Separator" value={c.separator ?? " "} onChange={(e) => set("separator", e.target.value)} sx={{ width: 150 }} />
            </>
          )}
          {c.mode === "copy" && <FieldPicker label="Source field" value={String(c.source_field || "")} onChange={(v) => set("source_field", v)} fields={fields} />}
          {c.mode === "conditional" && (
            <>
              <Box sx={{ display: "flex", gap: 1 }}>
                <Box sx={{ flex: 1 }}><FieldPicker label="If field" value={String(c.condition_field || "")} onChange={(v) => set("condition_field", v)} fields={fields} /></Box>
                <TextField size="small" label="Condition" select value={c.condition_op || "exists"} onChange={(e) => set("condition_op", e.target.value)} sx={{ width: 130 }}>
                  {FILTER_OPS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
                </TextField>
                <TextField size="small" label="Value" value={c.condition_value || ""} onChange={(e) => set("condition_value", e.target.value)} sx={{ flex: 1 }} />
              </Box>
              <Box sx={{ display: "flex", gap: 1 }}>
                <TextField size="small" label="Then value" value={c.true_value || ""} onChange={(e) => set("true_value", e.target.value)} sx={{ flex: 1 }} />
                <TextField size="small" label="Else value" value={c.false_value || ""} onChange={(e) => set("false_value", e.target.value)} sx={{ flex: 1 }} />
              </Box>
            </>
          )}
        </Box>
      );

    case "remove":
      return <MultiFieldPicker label="Fields to remove" value={c.fields as string[] || []} onChange={(v) => set("fields", v)} fields={fields} />;

    case "rename":
      return (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
            <Button size="small" onClick={() => set("renames", [...(c.renames as unknown[] || []), { from: "", to: "" }])}>+ Add</Button>
          </Box>
          {((c.renames as Array<{ from: string; to: string }>) || []).map((r, i) => (
            <Box key={i} sx={{ display: "flex", gap: 1, alignItems: "center" }}>
              <Box sx={{ flex: 1 }}><FieldPicker label="From" value={r.from} onChange={(v) => { const list = [...(c.renames as Array<{ from: string; to: string }>)]; list[i] = { ...list[i], from: v }; set("renames", list); }} fields={fields} /></Box>
              <Typography>→</Typography>
              <TextField size="small" label="To" value={r.to} onChange={(e) => { const list = [...(c.renames as Array<{ from: string; to: string }>)]; list[i] = { ...list[i], to: e.target.value }; set("renames", list); }} sx={{ flex: 1 }} />
              <IconButton size="small" onClick={() => set("renames", (c.renames as unknown[]).filter((_, j) => j !== i))}><DeleteIcon fontSize="small" /></IconButton>
            </Box>
          ))}
        </Box>
      );

    case "filter":
      return (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
            <Button size="small" onClick={() => addToList("filters", { field: "", operator: "eq", value: "" })}>+ Add condition</Button>
          </Box>
          {getList("filters").map((f, i) => (
            <Box key={i} sx={{ display: "flex", gap: 1, alignItems: "center" }}>
              <Box sx={{ flex: 1 }}><FieldPicker label="Field" value={String(f.field || "")} onChange={(v) => updateInList("filters", i, "field", v)} fields={fields} /></Box>
              <TextField size="small" label="Op" select value={f.operator || "eq"} onChange={(e) => updateInList("filters", i, "operator", e.target.value)} sx={{ width: 130 }}>
                {FILTER_OPS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
              </TextField>
              <TextField size="small" label="Value" value={f.value || ""} onChange={(e) => updateInList("filters", i, "value", e.target.value)} sx={{ flex: 1 }} disabled={f.operator === "exists" || f.operator === "not_exists"} />
              <IconButton size="small" onClick={() => removeFromList("filters", i)}><DeleteIcon fontSize="small" /></IconButton>
            </Box>
          ))}
        </Box>
      );

    case "replace":
      return (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
          <FieldPicker label="Field" value={String(c.field || "")} onChange={(v) => set("field", v)} fields={fields} />
          <TextField size="small" label="Find" value={c.find || ""} onChange={(e) => set("find", e.target.value)} fullWidth />
          <TextField size="small" label="Replace with" value={c.replace_with || ""} onChange={(e) => set("replace_with", e.target.value)} fullWidth />
        </Box>
      );

    case "substring":
      return (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
          <FieldPicker label="Source field" value={String(c.field || "")} onChange={(v) => set("field", v)} fields={fields} />
          <FieldPicker label="Target field (optional)" value={String(c.target_field || "")} onChange={(v) => set("target_field", v)} fields={fields} helperText="Leave empty to overwrite the source field" />
          <TextField size="small" label="Regex pattern (with capture group)" value={c.regex || ""} onChange={(e) => set("regex", e.target.value)} fullWidth placeholder="e.g. (\d{4})-\d{2}-\d{2} to extract year" helperText="Or use start/end positions below" />
          <Box sx={{ display: "flex", gap: 1 }}>
            <TextField size="small" label="Start position" type="number" value={c.start ?? ""} onChange={(e) => set("start", e.target.value ? parseInt(e.target.value) : undefined)} sx={{ flex: 1 }} />
            <TextField size="small" label="End position" type="number" value={c.end ?? ""} onChange={(e) => set("end", e.target.value ? parseInt(e.target.value) : undefined)} sx={{ flex: 1 }} />
          </Box>
        </Box>
      );

    case "split_column":
      return (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
          <FieldPicker label="Source field" value={String(c.source_field || "")} onChange={(v) => set("source_field", v)} fields={fields} />
          <TextField size="small" label="Delimiter" value={c.delimiter ?? ","} onChange={(e) => set("delimiter", e.target.value)} sx={{ width: 150 }} />
          <TextField size="small" label="Target fields (comma-separated)" fullWidth placeholder="part1, part2, part3"
            defaultValue={(c.target_fields as string[] || []).join(", ")}
            onBlur={(e) => set("target_fields", e.target.value.split(",").map((s: string) => s.trim()).filter(Boolean))}
          />
          <FormControlLabel
            control={<Checkbox size="small" checked={c.keep_source === false ? false : true} onChange={(e) => set("keep_source", e.target.checked)} />}
            label={<Typography variant="body2">Keep original column after split</Typography>}
          />
        </Box>
      );

    case "math":
      return (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
          <TextField size="small" label="Result field" value={c.target_field || ""} onChange={(e) => set("target_field", e.target.value)} fullWidth />
          <TextField size="small" label="Operation" select value={c.operation || "add"} onChange={(e) => set("operation", e.target.value)} fullWidth>
            {MATH_OPS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
          </TextField>
          <FieldPicker label="Field A" value={String(c.field_a || "")} onChange={(v) => set("field_a", v)} fields={fields} />
          <FieldPicker label="Field B (or leave empty and set constant)" value={String(c.field_b || "")} onChange={(v) => set("field_b", v)} fields={fields} />
          <TextField size="small" label="Constant value" type="number" value={c.value ?? ""} onChange={(e) => set("value", e.target.value ? parseFloat(e.target.value) : undefined)} fullWidth helperText="Used when Field B is empty" />
        </Box>
      );

    case "combine":
      return (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
          <TextField size="small" label="Target field" value={c.target_field || ""} onChange={(e) => set("target_field", e.target.value)} fullWidth />
          <MultiFieldPicker label="Fields to combine" value={c.fields as string[] || []} onChange={(v) => set("fields", v)} fields={fields} />
          <TextField size="small" label="Separator" value={c.separator ?? " - "} onChange={(e) => set("separator", e.target.value)} sx={{ width: 200 }} />
        </Box>
      );

    case "lookup":
      return (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
          <FieldPicker label="Source field" value={String(c.field || "")} onChange={(v) => set("field", v)} fields={fields} />
          <FieldPicker label="Target field (optional)" value={String(c.target_field || "")} onChange={(v) => set("target_field", v)} fields={fields} helperText="Leave empty to overwrite the source field" />
          <Typography variant="caption" color="text.secondary">Lookup mapping (one per line: value = replacement)</Typography>
          <TextField size="small" multiline rows={4} value={Object.entries((c.mapping as Record<string, string>) || {}).map(([k, v]) => `${k} = ${v}`).join("\n")} fullWidth
            placeholder={"1 = Low\n2 = Medium\n3 = High"}
            onChange={(e) => {
              const mapping: Record<string, string> = {};
              for (const line of e.target.value.split("\n")) {
                const [k, ...rest] = line.split("=");
                if (k?.trim() && rest.length) mapping[k.trim()] = rest.join("=").trim();
              }
              set("mapping", mapping);
            }}
          />
          <TextField size="small" label="Default (if not in mapping)" value={c.default ?? ""} onChange={(e) => set("default", e.target.value || undefined)} fullWidth />
        </Box>
      );

    case "sort":
      return (
        <Box sx={{ display: "flex", gap: 1 }}>
          <Box sx={{ flex: 1 }}><FieldPicker label="Sort by field" value={String(c.field || "")} onChange={(v) => set("field", v)} fields={fields} /></Box>
          <TextField size="small" label="Direction" select value={c.ascending !== false ? "asc" : "desc"} onChange={(e) => set("ascending", e.target.value === "asc")} sx={{ width: 140 }}>
            <MenuItem value="asc">Ascending</MenuItem>
            <MenuItem value="desc">Descending</MenuItem>
          </TextField>
          <TextField size="small" label="Type" select value={c.numeric ? "numeric" : "text"} onChange={(e) => set("numeric", e.target.value === "numeric")} sx={{ width: 130 }}>
            <MenuItem value="text">Text</MenuItem>
            <MenuItem value="numeric">Numeric</MenuItem>
          </TextField>
        </Box>
      );

    case "trim":
      return (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <Alert severity="info" sx={{ py: 0 }}>
            Removes leading and trailing spaces from text values. Leave empty to trim all fields.
          </Alert>
          <MultiFieldPicker label="Fields to trim (leave empty for all)" value={c.fields as string[] || []} onChange={(v) => set("fields", v.length > 0 ? v : undefined)} fields={fields} />
        </Box>
      );

    case "deduplicate":
      return (
        <Box sx={{ display: "flex", gap: 1 }}>
          <Box sx={{ flex: 1 }}><MultiFieldPicker label="Unique fields" value={c.fields as string[] || []} onChange={(v) => set("fields", v)} fields={fields} /></Box>
          <TextField size="small" label="Keep" select value={c.keep || "first"} onChange={(e) => set("keep", e.target.value)} sx={{ width: 120 }}>
            <MenuItem value="first">First</MenuItem>
            <MenuItem value="last">Last</MenuItem>
          </TextField>
        </Box>
      );

    default:
      return <Typography color="text.secondary">Unknown operation type</Typography>;
  }
}

// ── Main component ───────────────────────────────────────────────────────────

export default function FlowDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: flow, isLoading } = useFlow(id || "");
  const { data: connections } = useConnections();
  const { data: executions } = useExecutions({ flow_id: id });
  const { data: recordData } = useDataRecords(id || "", 1, 20);
  const executeMutation = useExecuteFlow();
  const updateMutation = useUpdateFlow();
  const { enqueueSnackbar } = useSnackbar();

  // Schedules & webhooks for this flow
  const { data: allSchedules } = useSchedules();
  const createSchedule = useCreateSchedule();
  const deleteSchedule = useDeleteSchedule();
  const updateScheduleM = useUpdateSchedule();
  const flowSchedules = (allSchedules || []).filter((s: Schedule) => s.flow_id === id);

  const { data: allWebhooks } = useWebhooks();
  const createWebhook = useCreateWebhook();
  const deleteWebhook = useDeleteWebhook();
  const flowWebhooks = (allWebhooks || []).filter((w: Webhook) => w.flow_id === id);

  const [newCron, setNewCron] = useState("");
  const [newCronTz, setNewCronTz] = useState("Europe/Stockholm");
  const [viewMode, setViewMode] = useState<"pipeline" | "visual">("pipeline");
  const [postExecUrl, setPostExecUrl] = useState("");
  const [postExecDirty, setPostExecDirty] = useState(false);

  // Extract base field names from stored data
  const baseFields = useMemo(() => {
    if (!recordData?.records.length) return [];
    const fieldSet = new Set<string>();
    for (const rec of recordData.records) {
      for (const key of Object.keys(rec.data)) {
        fieldSet.add(key);
      }
    }
    return Array.from(fieldSet).sort();
  }, [recordData]);

  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [hasChanges, setHasChanges] = useState(false);
  const [addMenuOpen, setAddMenuOpen] = useState(false);

  // Compute available fields for each stage by simulating what prior stages do
  const fieldsPerStage = useMemo(() => {
    const result: string[][] = [];
    let currentFields = new Set(baseFields);

    for (const stage of stages) {
      // Fields available TO this stage (before it runs)
      result.push(Array.from(currentFields).sort());

      // Simulate what this stage does to the field list
      const c = stage.config;
      switch (stage.step_type) {
        case "add_column":
          if (c.column) currentFields.add(c.column as string);
          break;
        case "split_column":
          if (c.target_fields) {
            for (const f of c.target_fields as string[]) currentFields.add(f);
          }
          if (c.keep_source === false && c.source_field) {
            currentFields.delete(c.source_field as string);
          }
          break;
        case "remove":
          if (c.fields) {
            for (const f of c.fields as string[]) currentFields.delete(f);
          }
          break;
        case "rename":
          if (c.renames) {
            for (const r of c.renames as Array<{ from: string; to: string }>) {
              currentFields.delete(r.from);
              currentFields.add(r.to);
            }
          }
          break;
        case "combine":
          if (c.target_field) currentFields.add(c.target_field as string);
          break;
        case "math":
          if (c.target_field) currentFields.add(c.target_field as string);
          break;
        case "substring":
          if (c.target_field) currentFields.add(c.target_field as string);
          break;
        case "transform":
          if (c.mappings && (c.mappings as unknown[]).length > 0) {
            const newFields = new Set<string>();
            for (const m of c.mappings as Array<{ target_field?: string; source_field?: string }>) {
              newFields.add(m.target_field || m.source_field || "");
            }
            currentFields = newFields;
          }
          if (c.computed_fields) {
            for (const cf of c.computed_fields as Array<{ field: string }>) {
              currentFields.add(cf.field);
            }
          }
          break;
      }
    }

    return result;
  }, [baseFields, stages]);

  useEffect(() => {
    if (!flow) return;
    if (flow.steps) setStages(flow.steps.map((s) => ({ step_type: s.step_type, config: s.config })));
    setPostExecUrl(flow.post_exec_webhook_url || "");
    setPostExecDirty(false);
    setHasChanges(false);
  }, [flow]);

  const addStage = (type: string) => {
    setStages([...stages, { step_type: type, config: {} }]);
    setHasChanges(true);
    setAddMenuOpen(false);
  };

  const updateStageConfig = (i: number, config: Record<string, unknown>) => {
    const updated = [...stages];
    updated[i] = { ...updated[i], config };
    setStages(updated);
    setHasChanges(true);
  };

  const removeStage = (i: number) => {
    setStages(stages.filter((_, j) => j !== i));
    setHasChanges(true);
  };

  const moveStage = (from: number, to: number) => {
    if (to < 0 || to >= stages.length) return;
    const updated = [...stages];
    const [moved] = updated.splice(from, 1);
    updated.splice(to, 0, moved);
    setStages(updated);
    setHasChanges(true);
  };

  const handleSave = async () => {
    if (!flow) return;
    const steps = stages.map((s, i) => ({ step_order: i, step_type: s.step_type, config: s.config }));
    try {
      await updateMutation.mutateAsync({ flow_id: flow.id, steps });
      enqueueSnackbar("Pipeline saved", { variant: "success" });
      setHasChanges(false);
    } catch {
      enqueueSnackbar("Failed to save", { variant: "error" });
    }
  };

  const handleExecute = async () => {
    if (!flow) return;
    try {
      const result = await executeMutation.mutateAsync(flow.id);
      enqueueSnackbar(
        result.status === "success"
          ? `Success: ${result.records_processed} records (${result.records_created} new, ${result.records_updated} updated)`
          : `Error: ${result.error_message || "Unknown error"}`,
        { variant: result.status === "success" ? "success" : "error" },
      );
    } catch {
      enqueueSnackbar("Execution failed", { variant: "error" });
    }
  };

  if (isLoading) return <Typography>Loading...</Typography>;
  if (!flow) return <Typography>Flow not found</Typography>;

  const connection = connections?.find((c) => c.id === flow.connection_id);

  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2 }}>
        <Box>
          <Typography variant="h4">{flow.name}</Typography>
          {flow.description && <Typography color="text.secondary">{flow.description}</Typography>}
        </Box>
        <Box sx={{ display: "flex", gap: 1 }}>
          {hasChanges && (
            <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSave} disabled={updateMutation.isPending}>
              Save Pipeline
            </Button>
          )}
          <Button variant="outlined" startIcon={<PlayArrowIcon />} onClick={handleExecute} disabled={executeMutation.isPending}>
            {executeMutation.isPending ? "Running..." : "Execute Now"}
          </Button>
        </Box>
      </Box>

      <Box sx={{ display: "flex", gap: 1, mb: 3, alignItems: "center" }}>
        <Chip label={flow.enabled ? "Enabled" : "Disabled"} color={flow.enabled ? "success" : "default"} size="small" />
        <Chip label={connection?.name || flow.connection_id.slice(0, 8)} variant="outlined" size="small" />
        <Chip label={`${stages.length} stages`} variant="outlined" size="small" />
        <Box sx={{ flexGrow: 1 }} />
        <Chip
          icon={<ViewListIcon />}
          label="Pipeline"
          variant={viewMode === "pipeline" ? "filled" : "outlined"}
          color={viewMode === "pipeline" ? "primary" : "default"}
          onClick={() => setViewMode("pipeline")}
          sx={{ cursor: "pointer" }}
        />
        <Chip
          icon={<AccountTreeIcon />}
          label="Visual"
          variant={viewMode === "visual" ? "filled" : "outlined"}
          color={viewMode === "visual" ? "primary" : "default"}
          onClick={() => setViewMode("visual")}
          sx={{ cursor: "pointer" }}
        />
      </Box>

      {hasChanges && <Alert severity="warning" sx={{ mb: 2 }}>Unsaved changes. Click "Save Pipeline" to apply.</Alert>}

      {/* ── Visual Flow Builder ──────────────────────────────────────────── */}
      {viewMode === "visual" && (
        <Card sx={{ mb: 3, overflow: "hidden" }}>
          <Box sx={{ height: 500 }}>
            <Suspense fallback={<Box display="flex" justifyContent="center" alignItems="center" height="100%"><Typography>Loading...</Typography></Box>}>
              <FlowBuilderCanvas
                flowId={flow.id}
                flowName={flow.name}
                connection={connection}
                steps={flow.steps || []}
                recordCount={recordData?.total}
                onNodeClick={(nodeId, stageIndex) => {
                  if (stageIndex != null) {
                    setViewMode("pipeline");
                  }
                }}
              />
            </Suspense>
          </Box>
        </Card>
      )}

      {/* ── Pipeline (form-based editor) ─────────────────────────────────── */}
      {viewMode === "pipeline" && <>

      {/* Source */}
      <Card sx={{ mb: 1, borderLeft: "4px solid #1565c0" }}>
        <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 }, display: "flex", alignItems: "center", gap: 1 }}>
          <Chip label="SOURCE" size="small" sx={{ bgcolor: "#1565c0", color: "white", fontWeight: 700 }} />
          <Typography variant="body2">{connection?.name} ({connection?.connector_type})</Typography>
        </CardContent>
      </Card>

      {stages.length === 0 && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}>
          <ArrowDownwardIcon color="action" />
        </Box>
      )}

      {/* Stages */}
      {stages.map((stage, i) => {
        const opDef = OPERATION_TYPES.find((o) => o.type === stage.step_type);
        return (
          <Box key={i}>
            <Box sx={{ display: "flex", justifyContent: "center", py: 0.5 }}>
              <ArrowDownwardIcon color="action" fontSize="small" />
            </Box>
            <Card sx={{ mb: 0, borderLeft: `4px solid ${opDef?.color || "#666"}` }}>
              <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    <Typography sx={{ fontSize: 18 }}>{opDef?.icon}</Typography>
                    <Chip label={`STAGE ${i + 1}`} size="small" sx={{ bgcolor: opDef?.color || "#666", color: "white", fontWeight: 700 }} />
                    <Typography variant="subtitle2">{opDef?.label || stage.step_type}</Typography>
                    <Typography variant="caption" color="text.secondary">{opDef?.description}</Typography>
                  </Box>
                  <Box sx={{ display: "flex", gap: 0.5 }}>
                    <IconButton size="small" onClick={() => moveStage(i, i - 1)} disabled={i === 0} title="Move up">▲</IconButton>
                    <IconButton size="small" onClick={() => moveStage(i, i + 1)} disabled={i === stages.length - 1} title="Move down">▼</IconButton>
                    <IconButton size="small" color="error" onClick={() => removeStage(i)} title="Remove"><DeleteIcon fontSize="small" /></IconButton>
                  </Box>
                </Box>
                <StageEditor stage={stage} onChange={(config) => updateStageConfig(i, config)} fields={fieldsPerStage[i] || baseFields} />
              </CardContent>
            </Card>
          </Box>
        );
      })}

      {/* Add stage */}
      <Box sx={{ display: "flex", justifyContent: "center", py: 1 }}>
        <ArrowDownwardIcon color="action" fontSize="small" />
      </Box>

      {!addMenuOpen ? (
        <Box sx={{ display: "flex", justifyContent: "center", mb: 2 }}>
          <Button variant="outlined" startIcon={<AddIcon />} onClick={() => setAddMenuOpen(true)}>
            Add Stage
          </Button>
        </Box>
      ) : (
        <Card sx={{ mb: 2, border: "2px dashed", borderColor: "primary.light" }}>
          <CardContent>
            <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
              <Typography variant="subtitle2">Add a pipeline stage</Typography>
              <Button size="small" onClick={() => setAddMenuOpen(false)}>Cancel</Button>
            </Box>
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
              {OPERATION_TYPES.map((op) => (
                <Chip
                  key={op.type}
                  label={`${op.icon} ${op.label}`}
                  onClick={() => addStage(op.type)}
                  sx={{ cursor: "pointer", borderColor: op.color, "&:hover": { bgcolor: `${op.color}22` } }}
                  variant="outlined"
                />
              ))}
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Store */}
      <Card sx={{ mb: 3, borderLeft: "4px solid #2e7d32" }}>
        <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Chip label="STORE" size="small" sx={{ bgcolor: "#2e7d32", color: "white", fontWeight: 700 }} />
              <Typography variant="body2">Data records → Data API → Consuming applications</Typography>
            </Box>
            <Button size="small" variant="outlined" color="success" onClick={() => navigate(`/data?flow=${flow.id}`)}>
              View Data
            </Button>
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block", fontFamily: "monospace" }}>
            API endpoint: GET /api/v1/data/{flow.id}/records
          </Typography>
        </CardContent>
      </Card>

      </>}

      {/* ── Schedules ────────────────────────────────────────────────────── */}
      <Divider sx={{ my: 3 }} />
      <Typography variant="h5" gutterBottom sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <ScheduleIcon /> Schedules
      </Typography>
      <Card sx={{ mb: 2 }}>
        <CardContent>
          {flowSchedules.length === 0 && (
            <Typography color="text.secondary" sx={{ mb: 2 }}>No schedules configured. Add one to run this flow automatically.</Typography>
          )}
          {flowSchedules.map((s) => (
            <Box key={s.id} sx={{ display: "flex", alignItems: "center", gap: 2, py: 1, borderBottom: "1px solid #eee" }}>
              <Chip
                label={s.enabled ? "Active" : "Paused"}
                size="small"
                color={s.enabled ? "success" : "default"}
                onClick={async () => {
                  try {
                    await updateScheduleM.mutateAsync({ id: s.id, enabled: !s.enabled });
                    enqueueSnackbar(s.enabled ? "Schedule paused" : "Schedule activated", { variant: "success" });
                  } catch { enqueueSnackbar("Failed to update", { variant: "error" }); }
                }}
                sx={{ cursor: "pointer" }}
              />
              <Box sx={{ flexGrow: 1 }}>
                <Typography variant="body2" fontWeight={600}>{describeCron(s.cron_expression) || s.cron_expression}</Typography>
                <Typography variant="caption" color="text.secondary" fontFamily="monospace">{s.cron_expression} ({s.timezone})</Typography>
              </Box>
              {s.last_run_at && (
                <Typography variant="caption" color="text.secondary">
                  Last: {new Date(s.last_run_at).toLocaleString()}
                </Typography>
              )}
              {s.next_run_at && (
                <Typography variant="caption" color="text.secondary">
                  Next: {new Date(s.next_run_at).toLocaleString()}
                </Typography>
              )}
              <IconButton size="small" color="error" onClick={async () => {
                try { await deleteSchedule.mutateAsync(s.id); enqueueSnackbar("Schedule deleted", { variant: "success" }); }
                catch { enqueueSnackbar("Failed to delete", { variant: "error" }); }
              }}><DeleteIcon fontSize="small" /></IconButton>
            </Box>
          ))}

          <Divider sx={{ my: 2 }} />
          <Typography variant="subtitle2" mb={1.5}>Add new schedule</Typography>
          <CronBuilder value={newCron} onChange={setNewCron} />
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", mt: 2 }}>
            <TextField
              size="small" label="Timezone" value={newCronTz}
              onChange={(e) => setNewCronTz(e.target.value)} sx={{ width: 200 }}
            />
            <Button
              variant="contained" size="small" startIcon={<AddIcon />}
              disabled={!newCron.trim() || createSchedule.isPending}
              onClick={async () => {
                try {
                  await createSchedule.mutateAsync({ flow_id: id!, cron_expression: newCron.trim(), timezone: newCronTz });
                  enqueueSnackbar("Schedule created", { variant: "success" });
                  setNewCron("");
                } catch { enqueueSnackbar("Failed to create schedule", { variant: "error" }); }
              }}
            >
              Add Schedule
            </Button>
          </Box>
        </CardContent>
      </Card>

      {/* ── Webhooks ──────────────────────────────────────────────────────── */}
      <Typography variant="h5" gutterBottom sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <WebhookIcon /> Webhooks
      </Typography>
      <Card sx={{ mb: 2 }}>
        <CardContent>
          {flowWebhooks.length === 0 && (
            <Typography color="text.secondary" sx={{ mb: 2 }}>No webhook endpoints. Create one to trigger this flow via HTTP POST.</Typography>
          )}
          {flowWebhooks.map((w) => (
            <Box key={w.id} sx={{ display: "flex", alignItems: "center", gap: 2, py: 1, borderBottom: "1px solid #eee" }}>
              <Chip label={w.enabled ? "Active" : "Disabled"} size="small" color={w.enabled ? "success" : "default"} />
              <Typography variant="body2" fontFamily="monospace" sx={{ flexGrow: 1 }}>
                POST /api/v1/webhooks/receive/{w.path_token}
              </Typography>
              <IconButton size="small" title="Copy URL" onClick={async () => {
                const url = `${window.location.origin}/api/v1/webhooks/receive/${w.path_token}`;
                const ok = await copyToClipboard(url);
                enqueueSnackbar(
                  ok ? "URL copied" : "Could not copy — select the URL and press Ctrl+C",
                  { variant: ok ? "info" : "warning" },
                );
              }}><ContentCopyIcon fontSize="small" /></IconButton>
              <IconButton size="small" color="error" onClick={async () => {
                try { await deleteWebhook.mutateAsync(w.id); enqueueSnackbar("Webhook deleted", { variant: "success" }); }
                catch { enqueueSnackbar("Failed to delete", { variant: "error" }); }
              }}><DeleteIcon fontSize="small" /></IconButton>
            </Box>
          ))}
          <Box sx={{ mt: 2 }}>
            <Button
              variant="contained" size="small" startIcon={<AddIcon />}
              disabled={createWebhook.isPending}
              onClick={async () => {
                try {
                  await createWebhook.mutateAsync({ flow_id: id! });
                  enqueueSnackbar("Webhook created", { variant: "success" });
                } catch { enqueueSnackbar("Failed to create webhook", { variant: "error" }); }
              }}
            >
              Create Webhook Endpoint
            </Button>
          </Box>
        </CardContent>
      </Card>

      {/* ── Post-Execution Webhook ─────────────────────────────────────── */}
      <Divider sx={{ my: 3 }} />
      <Typography variant="h5" gutterBottom sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <ContentCopyIcon /> Post-Execution Webhook
      </Typography>
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Typography variant="body2" color="text.secondary" mb={2}>
            When this flow executes successfully, send a notification to this URL.
            Use this to trigger automatic sync in the EA Application.
          </Typography>
          <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
            <TextField
              size="small"
              label="Webhook URL"
              placeholder="http://localhost:8000/api/v1/sync/webhook"
              value={postExecUrl}
              onChange={(e) => { setPostExecUrl(e.target.value); setPostExecDirty(true); }}
              fullWidth
            />
            <Button
              variant="contained"
              size="small"
              disabled={!postExecDirty || updateMutation.isPending}
              onClick={async () => {
                try {
                  await updateMutation.mutateAsync({
                    flow_id: flow.id,
                    post_exec_webhook_url: postExecUrl || null,
                  } as any);
                  enqueueSnackbar("Webhook URL saved", { variant: "success" });
                  setPostExecDirty(false);
                } catch { enqueueSnackbar("Failed to save", { variant: "error" }); }
              }}
              sx={{ minWidth: 80 }}
            >
              Save
            </Button>
            {postExecUrl && (
              <Button
                variant="outlined"
                size="small"
                color="error"
                onClick={async () => {
                  setPostExecUrl("");
                  try {
                    await updateMutation.mutateAsync({
                      flow_id: flow.id,
                      post_exec_webhook_url: "",
                    } as any);
                    enqueueSnackbar("Webhook URL removed", { variant: "success" });
                    setPostExecDirty(false);
                  } catch { enqueueSnackbar("Failed to save", { variant: "error" }); }
                }}
              >
                Remove
              </Button>
            )}
          </Box>
          {flow.post_exec_webhook_url && (
            <Typography variant="caption" color="success.main" sx={{ mt: 1, display: "block" }}>
              Active: POST {flow.post_exec_webhook_url} will be called after each successful execution
            </Typography>
          )}
        </CardContent>
      </Card>

      {/* ── Execution History ────────────────────────────────────────────── */}
      <Divider sx={{ my: 3 }} />
      <Typography variant="h5" gutterBottom>Execution History</Typography>
      <Card>
        <CardContent>
          {executions?.executions.length === 0 && (
            <Typography color="text.secondary">No executions yet. Click "Execute Now" to run this flow.</Typography>
          )}
          {executions?.executions.map((exec) => (
            <Box key={exec.id} sx={{ display: "flex", alignItems: "center", gap: 2, py: 1, borderBottom: "1px solid #eee" }}>
              <StatusChip status={exec.status} />
              <Typography variant="body2" sx={{ minWidth: 70 }}>{exec.trigger_type}</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ flexGrow: 1 }}>
                {new Date(exec.started_at).toLocaleString()}
              </Typography>
              <Typography variant="body2">
                {exec.records_processed} records ({exec.records_created} new, {exec.records_updated} updated)
              </Typography>
            </Box>
          ))}
        </CardContent>
      </Card>
    </Box>
  );
}
