import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Alert, Box, Button, Card, CardContent, Checkbox, Chip, Dialog, DialogActions,
  DialogContent, DialogTitle, Divider, FormControlLabel, IconButton, MenuItem,
  Pagination, Paper, Switch, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, TableSortLabel, TextField, Tooltip, Typography,
} from "@mui/material";
import {
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon,
  Search as SearchIcon,
  ViewColumn as ViewColumnIcon,
  Fullscreen as FullscreenIcon,
} from "@mui/icons-material";
import { useDataSources, useDataRecords } from "@/api/data";

export default function DataExplorer() {
  const [searchParams] = useSearchParams();
  const { data: sources } = useDataSources();
  const [selectedFlow, setSelectedFlow] = useState(searchParams.get("flow") || "");
  const [page, setPage] = useState(1);
  const { data: recordData, isLoading } = useDataRecords(selectedFlow, page, 100);

  // Auto-select flow from URL param
  useEffect(() => {
    const flowParam = searchParams.get("flow");
    if (flowParam && flowParam !== selectedFlow) {
      setSelectedFlow(flowParam);
      setPage(1);
    }
  }, [searchParams]);

  // Column visibility and order
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(new Set(["external_id", "Created", "Modified"]));
  const [columnOrder, setColumnOrder] = useState<string[]>([]);
  const [columnDialogOpen, setColumnDialogOpen] = useState(false);
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  // Search
  const [searchText, setSearchText] = useState("");

  // Sort
  const [sortField, setSortField] = useState("");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  // Detail view
  const [detailRecord, setDetailRecord] = useState<Record<string, unknown> | null>(null);

  // Discover all columns from the data
  const allColumns = useMemo(() => {
    if (!recordData?.records.length) return [];
    const colSet = new Set<string>();
    for (const rec of recordData.records) {
      for (const key of Object.keys(rec.data)) {
        colSet.add(key);
      }
    }
    // Put common fields first, then alphabetical
    const priority = ["external_id", "Title", "name", "Name"];
    const cols = Array.from(colSet);
    cols.sort((a, b) => {
      const ai = priority.indexOf(a);
      const bi = priority.indexOf(b);
      if (ai !== -1 && bi !== -1) return ai - bi;
      if (ai !== -1) return -1;
      if (bi !== -1) return 1;
      return a.localeCompare(b);
    });
    return cols;
  }, [recordData]);

  // When allColumns changes (new data source), reset column order
  useEffect(() => {
    if (allColumns.length > 0 && columnOrder.length === 0) {
      setColumnOrder(allColumns);
    }
  }, [allColumns]);

  // Ordered visible columns: follow custom order, include any new columns at the end
  const visibleColumns = useMemo(() => {
    if (columnOrder.length === 0) return allColumns.filter((c) => !hiddenColumns.has(c));
    const ordered = columnOrder.filter((c) => allColumns.includes(c) && !hiddenColumns.has(c));
    // Add any new columns not yet in the order
    for (const c of allColumns) {
      if (!hiddenColumns.has(c) && !ordered.includes(c)) ordered.push(c);
    }
    return ordered;
  }, [columnOrder, allColumns, hiddenColumns]);

  // Filter and sort records
  const processedRecords = useMemo(() => {
    if (!recordData?.records) return [];
    let rows: Record<string, unknown>[] = recordData.records.map((r) => ({ ...r.data, _id: r.id, _version: r.version, _updated: r.updated_at }));

    // Search filter
    if (searchText) {
      const lower = searchText.toLowerCase();
      rows = rows.filter((row) =>
        Object.values(row).some((v) => String(v ?? "").toLowerCase().includes(lower))
      );
    }

    // Sort
    if (sortField) {
      rows.sort((a, b) => {
        const av = a[sortField] ?? "";
        const bv = b[sortField] ?? "";
        const cmp = String(av).localeCompare(String(bv), undefined, { numeric: true });
        return sortDir === "asc" ? cmp : -cmp;
      });
    }

    return rows;
  }, [recordData, searchText, sortField, sortDir]);

  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDir("asc");
    }
  };

  const toggleColumn = (col: string) => {
    setHiddenColumns((prev) => {
      const next = new Set(prev);
      if (next.has(col)) next.delete(col);
      else next.add(col);
      return next;
    });
  };

  const formatCellValue = (value: unknown): string => {
    if (value === null || value === undefined) return "";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  };

  const selectedSource = sources?.find((s) => s.flow_id === selectedFlow);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <Typography variant="h4" gutterBottom>Data Explorer</Typography>

      {/* Source selector */}
      <Box sx={{ mb: 3, display: "flex", gap: 2, alignItems: "center", flexWrap: "wrap" }}>
        <TextField
          select label="Data Source" sx={{ minWidth: 350 }}
          value={selectedFlow}
          onChange={(e) => { setSelectedFlow(e.target.value); setPage(1); setSearchText(""); setSortField(""); setColumnOrder([]); }}
        >
          <MenuItem value="">Select a source...</MenuItem>
          {sources?.map((s) => (
            <MenuItem key={s.flow_id} value={s.flow_id}>
              {s.flow_name} ({s.connector_type}) — {s.record_count} records
            </MenuItem>
          ))}
        </TextField>

        {selectedFlow && (
          <>
            <TextField
              size="small" placeholder="Search all fields..."
              value={searchText} onChange={(e) => setSearchText(e.target.value)}
              InputProps={{ startAdornment: <SearchIcon sx={{ mr: 0.5, color: "text.secondary" }} /> }}
              sx={{ minWidth: 250 }}
            />
            <Button
              size="small" variant="outlined" startIcon={<ViewColumnIcon />}
              onClick={() => setColumnDialogOpen(true)}
            >
              Columns ({visibleColumns.length}/{allColumns.length})
            </Button>
          </>
        )}
      </Box>

      {/* Summary chips */}
      {selectedSource && (
        <Box sx={{ display: "flex", gap: 1, mb: 2, flexWrap: "wrap" }}>
          <Chip label={`${selectedSource.record_count} records`} size="small" />
          <Chip label={selectedSource.connector_type} size="small" variant="outlined" />
          {selectedSource.last_sync && (
            <Chip label={`Last sync: ${new Date(selectedSource.last_sync).toLocaleString()}`} size="small" variant="outlined" />
          )}
          <Chip label={`${visibleColumns.length} columns visible`} size="small" variant="outlined" />
          {searchText && <Chip label={`${processedRecords.length} matches`} size="small" color="primary" />}
        </Box>
      )}

      {/* Empty state */}
      {!selectedFlow && (
        <Card>
          <CardContent>
            <Typography color="text.secondary" gutterBottom>Select a data source to browse records.</Typography>
            {sources && sources.length > 0 && (
              <Box sx={{ mt: 2 }}>
                {sources.map((s) => (
                  <Box key={s.flow_id} sx={{ py: 0.5, display: "flex", gap: 2, alignItems: "center" }}>
                    <Chip label={s.connector_type} size="small" variant="outlined" />
                    <Typography variant="body2" sx={{ cursor: "pointer", color: "primary.main", "&:hover": { textDecoration: "underline" } }}
                      onClick={() => { setSelectedFlow(s.flow_id); setPage(1); }}
                    >
                      {s.flow_name} — {s.record_count} records
                    </Typography>
                  </Box>
                ))}
              </Box>
            )}
          </CardContent>
        </Card>
      )}

      {/* Data table */}
      {selectedFlow && recordData && (() => {
        // Find the first "title-like" column to pin it
        const titleColIndex = visibleColumns.findIndex((c) =>
          c === "Title" || c === "name" || c === "Name" || c === "title"
        );
        const ROW_NUM_W = 44;
        const TITLE_W = 200;
        const hasPinnedTitle = titleColIndex >= 0;

        // Sticky cell styles
        const stickyRowNum = {
          position: "sticky" as const, left: 0, zIndex: 3,
          bgcolor: "grey.100", width: ROW_NUM_W, minWidth: ROW_NUM_W,
        };
        const stickyTitle = {
          position: "sticky" as const, left: ROW_NUM_W, zIndex: 3,
          bgcolor: "grey.100", minWidth: TITLE_W, maxWidth: TITLE_W,
          borderRight: "2px solid #ccc",
        };
        const stickyRowNumBody = {
          position: "sticky" as const, left: 0, zIndex: 1,
          bgcolor: "background.paper", width: ROW_NUM_W, minWidth: ROW_NUM_W,
        };
        const stickyTitleBody = {
          position: "sticky" as const, left: ROW_NUM_W, zIndex: 1,
          bgcolor: "background.paper", minWidth: TITLE_W, maxWidth: TITLE_W,
          borderRight: "2px solid #e0e0e0", fontWeight: 500,
        };
        // Header cells need highest z-index for corner overlap
        const stickyRowNumHead = { ...stickyRowNum, zIndex: 4 };
        const stickyTitleHead = { ...stickyTitle, zIndex: 4 };

        return (
        <>
          {isLoading && <Typography>Loading...</Typography>}
          <TableContainer component={Paper} sx={{
            flex: 1, minHeight: 0,
            overflow: "auto",
          }}>
            <Table size="small" stickyHeader sx={{ minWidth: Math.max(800, visibleColumns.length * 180) }}>
              <TableHead>
                <TableRow>
                  <TableCell sx={stickyRowNumHead}>#</TableCell>
                  {visibleColumns.map((col, ci) => {
                    const isPinned = hasPinnedTitle && ci === titleColIndex;
                    return (
                      <TableCell key={col} sx={{
                        bgcolor: "grey.100", fontWeight: 600, whiteSpace: "nowrap",
                        ...(isPinned ? stickyTitleHead : {}),
                      }}>
                        <TableSortLabel
                          active={sortField === col}
                          direction={sortField === col ? sortDir : "asc"}
                          onClick={() => handleSort(col)}
                        >
                          {col}
                        </TableSortLabel>
                      </TableCell>
                    );
                  })}
                  <TableCell sx={{ width: 40, bgcolor: "grey.100" }} />
                </TableRow>
              </TableHead>
              <TableBody>
                {processedRecords.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={visibleColumns.length + 2}>
                      <Typography color="text.secondary" align="center">
                        {searchText ? "No records match your search." : "No records."}
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
                {processedRecords.map((row, i) => (
                  <TableRow key={row._id as string} hover>
                    <TableCell sx={{ ...stickyRowNumBody, color: "text.secondary", fontSize: 12 }}>{(page - 1) * 100 + i + 1}</TableCell>
                    {visibleColumns.map((col, ci) => {
                      const val = formatCellValue(row[col]);
                      const isLong = val.length > 80;
                      const isPinned = hasPinnedTitle && ci === titleColIndex;
                      return (
                        <TableCell key={col} sx={{
                          maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis",
                          whiteSpace: "nowrap", fontSize: 13,
                          ...(isPinned ? stickyTitleBody : {}),
                        }}>
                          {isLong ? (
                            <Tooltip title={val} placement="bottom-start">
                              <span>{val.slice(0, 80)}...</span>
                            </Tooltip>
                          ) : val}
                        </TableCell>
                      );
                    })}
                    <TableCell>
                      <IconButton size="small" onClick={() => setDetailRecord(row)} title="View full record">
                        <FullscreenIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {recordData.total > recordData.page_size && (
            <Box sx={{ display: "flex", justifyContent: "center", py: 1, flexShrink: 0 }}>
              <Pagination
                count={Math.ceil(recordData.total / recordData.page_size)}
                page={page}
                onChange={(_, p) => setPage(p)}
              />
            </Box>
          )}
        </>
        );
      })()}

      {/* Column visibility + order dialog */}
      <Dialog open={columnDialogOpen} onClose={() => setColumnDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Columns</DialogTitle>
        <DialogContent>
          <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
            <Button size="small" onClick={() => setHiddenColumns(new Set())}>Show all</Button>
            <Button size="small" onClick={() => setHiddenColumns(new Set(allColumns))}>Hide all</Button>
          </Box>
          <Divider sx={{ mb: 1 }} />
          {(() => {
            const orderedCols = columnOrder.length > 0 ? columnOrder.filter((c) => allColumns.includes(c)) : allColumns;
            const moveColumn = (from: number, to: number) => {
              const order = [...orderedCols];
              const [moved] = order.splice(from, 1);
              order.splice(to, 0, moved);
              setColumnOrder(order);
            };
            return orderedCols.map((col, i) => (
              <Box key={col} sx={{ display: "flex", alignItems: "center", gap: 0.5, py: 0.25, px: 0.5, borderRadius: 1, "&:hover": { bgcolor: "action.hover" } }}>
                <Box sx={{ display: "flex", flexDirection: "column", mr: 0.5 }}>
                  <IconButton size="small" disabled={i === 0} onClick={() => moveColumn(i, i - 1)}
                    sx={{ p: 0, fontSize: 14, lineHeight: 1 }}>▲</IconButton>
                  <IconButton size="small" disabled={i === orderedCols.length - 1} onClick={() => moveColumn(i, i + 1)}
                    sx={{ p: 0, fontSize: 14, lineHeight: 1 }}>▼</IconButton>
                </Box>
                <Checkbox size="small" checked={!hiddenColumns.has(col)} onChange={() => toggleColumn(col)} />
                <Typography variant="body2" sx={{ flexGrow: 1 }}>{col}</Typography>
                <Typography variant="caption" color="text.disabled">{i + 1}</Typography>
              </Box>
            ));
          })()}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setColumnDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Record detail dialog */}
      <Dialog open={!!detailRecord} onClose={() => setDetailRecord(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Record Detail</DialogTitle>
        <DialogContent>
          {detailRecord && (
            <Table size="small">
              <TableBody>
                {Object.entries(detailRecord)
                  .filter(([k]) => !k.startsWith("_"))
                  .map(([key, value]) => (
                    <TableRow key={key}>
                      <TableCell sx={{ fontWeight: 600, whiteSpace: "nowrap", width: 150, verticalAlign: "top" }}>{key}</TableCell>
                      <TableCell sx={{ wordBreak: "break-word" }}>
                        {typeof value === "object" ? (
                          <Typography component="pre" sx={{ fontSize: 12, m: 0 }}>{JSON.stringify(value, null, 2)}</Typography>
                        ) : (
                          String(value ?? "")
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailRecord(null)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
