import { Chip, type ChipProps } from "@mui/material";

const STATUS_COLORS: Record<string, ChipProps["color"]> = {
  success: "success",
  active: "success",
  running: "info",
  error: "error",
  disabled: "default",
  empty: "warning",
  pending: "warning",
};

export default function StatusChip({ status }: { status: string }) {
  return (
    <Chip
      label={status}
      size="small"
      color={STATUS_COLORS[status] || "default"}
      variant="outlined"
    />
  );
}
