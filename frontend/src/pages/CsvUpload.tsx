import { useState, useRef } from "react";
import {
  Alert, Box, Button, Card, CardContent, Chip, Divider,
  MenuItem, Paper, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import {
  UploadFile as UploadFileIcon,
  CloudUpload as CloudUploadIcon,
  CheckCircle as CheckCircleIcon,
} from "@mui/icons-material";
import { useSnackbar } from "notistack";
import client from "@/api/client";

interface PreviewResult {
  total_rows: number;
  columns: Array<{ name: string; sample: string }>;
  preview: Record<string, unknown>[];
}

interface UploadResult {
  connection_id: string;
  flow_id: string;
  name: string;
  filename: string;
  total_records: number;
  columns: string[];
}

export default function CsvUpload() {
  const { enqueueSnackbar } = useSnackbar();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [delimiter, setDelimiter] = useState("auto");
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);

  const handleFileSelect = async (selectedFile: File) => {
    setFile(selectedFile);
    setResult(null);

    // Auto-fill name from filename
    if (!name) {
      const baseName = selectedFile.name.replace(/\.(csv|tsv|txt)$/i, "");
      setName(baseName);
    }

    // Preview
    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("delimiter", delimiter);
    try {
      const resp = await client.post("/csv/preview", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPreview(resp.data);
    } catch (err: any) {
      enqueueSnackbar(err.response?.data?.detail || "Failed to parse CSV", { variant: "error" });
      setPreview(null);
    }
  };

  const handleUpload = async () => {
    if (!file || !name) return;
    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("name", name);
    formData.append("description", description);
    formData.append("delimiter", delimiter);
    try {
      const resp = await client.post("/csv/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(resp.data);
      enqueueSnackbar(`Uploaded ${resp.data.total_records} records`, { variant: "success" });
    } catch (err: any) {
      enqueueSnackbar(err.response?.data?.detail || "Upload failed", { variant: "error" });
    } finally {
      setUploading(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setName("");
    setDescription("");
    setPreview(null);
    setResult(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>CSV Import</Typography>
      <Typography variant="body2" gutterBottom sx={{ color: "text.secondary" }}>
        Upload a CSV file to create a new data source. The data becomes available in the Data Explorer and Data API.
      </Typography>

      {/* File selection */}
      {!result && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <Box
                sx={{
                  border: "2px dashed",
                  borderColor: file ? "success.main" : "grey.300",
                  borderRadius: 2,
                  p: 4,
                  textAlign: "center",
                  cursor: "pointer",
                  "&:hover": { borderColor: "primary.main", bgcolor: "action.hover" },
                }}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const f = e.dataTransfer.files[0];
                  if (f) handleFileSelect(f);
                }}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,.tsv,.txt"
                  hidden
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleFileSelect(f);
                  }}
                />
                <UploadFileIcon sx={{ fontSize: 48, color: file ? "success.main" : "grey.400", mb: 1 }} />
                {file ? (
                  <Typography>{file.name} ({(file.size / 1024).toFixed(1)} KB)</Typography>
                ) : (
                  <>
                    <Typography>Click or drag a CSV file here</Typography>
                    <Typography variant="caption" sx={{ color: "text.secondary" }}>Supports .csv, .tsv, .txt</Typography>
                  </>
                )}
              </Box>

              <Box sx={{ display: "flex", gap: 2 }}>
                <TextField
                  label="Data Source Name" required fullWidth
                  value={name} onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Employee List"
                  helperText="Name for this data source in the platform"
                />
                <TextField
                  label="Delimiter" select sx={{ minWidth: 150 }}
                  value={delimiter}
                  onChange={(e) => setDelimiter(e.target.value)}
                >
                  <MenuItem value="auto">Auto-detect</MenuItem>
                  <MenuItem value=",">Comma (,)</MenuItem>
                  <MenuItem value=";">Semicolon (;)</MenuItem>
                  <MenuItem value={"\t"}>Tab</MenuItem>
                </TextField>
              </Box>

              <TextField
                label="Description (optional)" fullWidth
                value={description} onChange={(e) => setDescription(e.target.value)}
                placeholder="What does this data contain?"
              />
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Preview */}
      {preview && !result && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
              <Box>
                <Typography variant="h6">Preview</Typography>
                <Box sx={{ display: "flex", gap: 1, mt: 0.5 }}>
                  <Chip label={`${preview.total_rows} rows`} size="small" />
                  <Chip label={`${preview.columns.length} columns`} size="small" variant="outlined" />
                </Box>
              </Box>
              <Button
                variant="contained" startIcon={<CloudUploadIcon />}
                onClick={handleUpload} disabled={uploading || !name}
              >
                {uploading ? "Uploading..." : `Upload ${preview.total_rows} rows`}
              </Button>
            </Box>

            <Typography variant="subtitle2" gutterBottom sx={{ color: "text.secondary" }}>
              Columns: {preview.columns.map((c) => c.name).join(", ")}
            </Typography>

            <TableContainer component={Paper} sx={{ maxHeight: 400, overflow: "auto" }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ bgcolor: "grey.100", fontWeight: 600 }}>#</TableCell>
                    {preview.columns.map((col) => (
                      <TableCell key={col.name} sx={{ bgcolor: "grey.100", fontWeight: 600, whiteSpace: "nowrap" }}>
                        {col.name}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {preview.preview.map((row, i) => (
                    <TableRow key={i}>
                      <TableCell sx={{ color: "text.secondary", fontSize: 12 }}>{i + 1}</TableCell>
                      {preview.columns.map((col) => (
                        <TableCell key={col.name} sx={{ fontSize: 13, maxWidth: 250, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {String(row[col.name] ?? "")}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            {preview.total_rows > 10 && (
              <Typography variant="caption" sx={{ color: "text.secondary", mt: 1, display: "block" }}>
                Showing first 10 of {preview.total_rows} rows
              </Typography>
            )}
          </CardContent>
        </Card>
      )}

      {/* Result */}
      {result && (
        <Card>
          <CardContent>
            <Alert severity="success" icon={<CheckCircleIcon />} sx={{ mb: 2 }}>
              Successfully imported {result.total_records} records
            </Alert>
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1, mb: 2 }}>
              <Typography variant="body2"><strong>Name:</strong> {result.name}</Typography>
              <Typography variant="body2"><strong>File:</strong> {result.filename}</Typography>
              <Typography variant="body2"><strong>Records:</strong> {result.total_records}</Typography>
              <Typography variant="body2"><strong>Columns:</strong> {result.columns.join(", ")}</Typography>
              <Typography variant="body2" sx={{ fontFamily: "monospace", fontSize: 12 }}>
                <strong>Flow ID:</strong> {result.flow_id}
              </Typography>
              <Typography variant="body2" sx={{ fontFamily: "monospace", fontSize: 12 }}>
                <strong>API:</strong> GET /api/v1/data/{result.flow_id}/records
              </Typography>
            </Box>
            <Divider sx={{ my: 2 }} />
            <Box sx={{ display: "flex", gap: 1 }}>
              <Button variant="outlined" onClick={handleReset}>Upload another file</Button>
              <Button variant="contained" onClick={() => window.location.href = `/data?flow=${result.flow_id}`}>
                View in Data Explorer
              </Button>
            </Box>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}
