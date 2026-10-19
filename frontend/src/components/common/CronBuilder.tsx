import { useState, useEffect } from "react";
import {
  Box, Chip, FormControl, InputLabel, MenuItem, Select, Stack,
  TextField, Typography,
} from "@mui/material";

// ── Preset schedules ────────────────────────────────────────────────────────

interface Preset {
  label: string;
  cron: string;
  description: string;
}

const PRESETS: Preset[] = [
  { label: "Every 5 minutes",  cron: "*/5 * * * *",  description: "Runs every 5 minutes" },
  { label: "Every 15 minutes", cron: "*/15 * * * *", description: "Runs every 15 minutes" },
  { label: "Every 30 minutes", cron: "*/30 * * * *", description: "Runs every 30 minutes" },
  { label: "Every hour",       cron: "0 * * * *",    description: "Runs at the start of every hour" },
  { label: "Every 2 hours",    cron: "0 */2 * * *",  description: "Runs every 2 hours" },
  { label: "Every 6 hours",    cron: "0 */6 * * *",  description: "Runs at 00:00, 06:00, 12:00, 18:00" },
  { label: "Daily at 06:00",   cron: "0 6 * * *",    description: "Runs once a day at 06:00" },
  { label: "Daily at 08:00",   cron: "0 8 * * *",    description: "Runs once a day at 08:00" },
  { label: "Daily at midnight", cron: "0 0 * * *",   description: "Runs once a day at 00:00" },
  { label: "Weekdays at 07:00", cron: "0 7 * * 1-5", description: "Mon–Fri at 07:00" },
  { label: "Weekly (Monday 06:00)", cron: "0 6 * * 1", description: "Every Monday at 06:00" },
  { label: "Monthly (1st at 06:00)", cron: "0 6 1 * *", description: "First day of every month at 06:00" },
];

// ── Custom builder options ──────────────────────────────────────────────────

const MINUTE_OPTIONS = [
  { value: "*",    label: "Every minute" },
  { value: "*/5",  label: "Every 5 min" },
  { value: "*/10", label: "Every 10 min" },
  { value: "*/15", label: "Every 15 min" },
  { value: "*/30", label: "Every 30 min" },
  { value: "0",    label: ":00 (on the hour)" },
  { value: "15",   label: ":15" },
  { value: "30",   label: ":30" },
  { value: "45",   label: ":45" },
];

const HOUR_OPTIONS = [
  { value: "*",    label: "Every hour" },
  { value: "*/2",  label: "Every 2 hours" },
  { value: "*/3",  label: "Every 3 hours" },
  { value: "*/4",  label: "Every 4 hours" },
  { value: "*/6",  label: "Every 6 hours" },
  { value: "*/12", label: "Every 12 hours" },
  ...Array.from({ length: 24 }, (_, i) => ({
    value: String(i),
    label: `${String(i).padStart(2, "0")}:xx`,
  })),
];

const DAY_OPTIONS = [
  { value: "*", label: "Every day" },
  { value: "1", label: "1st" },
  { value: "15", label: "15th" },
  { value: "1,15", label: "1st & 15th" },
];

const MONTH_OPTIONS = [
  { value: "*", label: "Every month" },
];

const DOW_OPTIONS = [
  { value: "*",   label: "Any day" },
  { value: "1-5", label: "Weekdays (Mon–Fri)" },
  { value: "0,6", label: "Weekends (Sat–Sun)" },
  { value: "1",   label: "Monday" },
  { value: "2",   label: "Tuesday" },
  { value: "3",   label: "Wednesday" },
  { value: "4",   label: "Thursday" },
  { value: "5",   label: "Friday" },
];

// ── Human-readable description ──────────────────────────────────────────────

function describeCron(cron: string): string {
  const preset = PRESETS.find((p) => p.cron === cron);
  if (preset) return preset.description;

  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return "";

  const [min, hour, day, , dow] = parts;
  const pieces: string[] = [];

  // Frequency
  if (min.startsWith("*/")) pieces.push(`Every ${min.slice(2)} minutes`);
  else if (hour.startsWith("*/")) pieces.push(`Every ${hour.slice(2)} hours at :${min.padStart(2, "0")}`);
  else if (hour !== "*" && min !== "*") pieces.push(`At ${hour.padStart(2, "0")}:${min.padStart(2, "0")}`);
  else if (hour !== "*") pieces.push(`Every minute during hour ${hour}`);
  else if (min !== "*") pieces.push(`At :${min.padStart(2, "0")} every hour`);
  else pieces.push("Every minute");

  // Day of month
  if (day !== "*") pieces.push(`on day ${day}`);

  // Day of week
  if (dow === "1-5") pieces.push("weekdays only");
  else if (dow === "0,6") pieces.push("weekends only");
  else if (dow !== "*") {
    const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const dayNames = dow.split(",").map((d) => days[parseInt(d)] || d).join(", ");
    pieces.push(`on ${dayNames}`);
  }

  return pieces.join(", ");
}

// ── Component ───────────────────────────────────────────────────────────────

type Mode = "preset" | "custom";

interface CronBuilderProps {
  value: string;
  onChange: (cron: string) => void;
}

export default function CronBuilder({ value, onChange }: CronBuilderProps) {
  const [mode, setMode] = useState<Mode>("preset");

  // Parse current value into parts for custom mode
  const parts = value.trim().split(/\s+/);
  const [minute, setMinute] = useState(parts[0] || "0");
  const [hour, setHour] = useState(parts[1] || "*");
  const [day, setDay] = useState(parts[2] || "*");
  const [month, setMonth] = useState(parts[3] || "*");
  const [dow, setDow] = useState(parts[4] || "*");

  // Sync custom fields when value changes externally
  useEffect(() => {
    const p = value.trim().split(/\s+/);
    if (p.length === 5) {
      setMinute(p[0]);
      setHour(p[1]);
      setDay(p[2]);
      setMonth(p[3]);
      setDow(p[4]);
    }
  }, [value]);

  // Update cron from custom fields
  const updateCustom = (min: string, hr: string, d: string, mo: string, dw: string) => {
    setMinute(min); setHour(hr); setDay(d); setMonth(mo); setDow(dw);
    onChange(`${min} ${hr} ${d} ${mo} ${dw}`);
  };

  const description = describeCron(value);
  const isPreset = PRESETS.some((p) => p.cron === value);

  return (
    <Box>
      {/* Mode toggle */}
      <Stack direction="row" spacing={1} mb={2}>
        <Chip
          label="Quick select"
          variant={mode === "preset" ? "filled" : "outlined"}
          color={mode === "preset" ? "primary" : "default"}
          onClick={() => setMode("preset")}
          sx={{ cursor: "pointer" }}
        />
        <Chip
          label="Custom"
          variant={mode === "custom" ? "filled" : "outlined"}
          color={mode === "custom" ? "primary" : "default"}
          onClick={() => setMode("custom")}
          sx={{ cursor: "pointer" }}
        />
      </Stack>

      {mode === "preset" && (
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
          {PRESETS.map((p) => (
            <Chip
              key={p.cron}
              label={p.label}
              variant={value === p.cron ? "filled" : "outlined"}
              color={value === p.cron ? "success" : "default"}
              onClick={() => onChange(p.cron)}
              sx={{ cursor: "pointer" }}
            />
          ))}
        </Box>
      )}

      {mode === "custom" && (
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Minute</InputLabel>
            <Select value={MINUTE_OPTIONS.some((o) => o.value === minute) ? minute : minute} label="Minute"
              onChange={(e) => updateCustom(e.target.value, hour, day, month, dow)}>
              {MINUTE_OPTIONS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Hour</InputLabel>
            <Select value={hour} label="Hour"
              onChange={(e) => updateCustom(minute, e.target.value, day, month, dow)}>
              {HOUR_OPTIONS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 130 }}>
            <InputLabel>Day</InputLabel>
            <Select value={DAY_OPTIONS.some((o) => o.value === day) ? day : "*"} label="Day"
              onChange={(e) => updateCustom(minute, hour, e.target.value, month, dow)}>
              {DAY_OPTIONS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 130 }}>
            <InputLabel>Weekday</InputLabel>
            <Select value={DOW_OPTIONS.some((o) => o.value === dow) ? dow : "*"} label="Weekday"
              onChange={(e) => updateCustom(minute, hour, day, month, e.target.value)}>
              {DOW_OPTIONS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
            </Select>
          </FormControl>
        </Stack>
      )}

      {/* Description + raw value */}
      {value && (
        <Box sx={{ mt: 1.5, display: "flex", alignItems: "center", gap: 2 }}>
          <Typography variant="body2" color="success.main" fontWeight={500}>
            {description || "Custom schedule"}
          </Typography>
          <Typography variant="caption" fontFamily="monospace" color="text.secondary">
            ({value})
          </Typography>
        </Box>
      )}
    </Box>
  );
}

export { describeCron };
