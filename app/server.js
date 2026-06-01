import express from 'express';
import cors from 'cors';
import { exec } from 'child_process';
import { writeFile, unlink } from 'fs/promises';
import { tmpdir } from 'os';
import { join } from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const app = express();
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// Binary paths — override via env vars for Docker / CI
const CLANG_FORMAT        = process.env.CLANG_FORMAT_BIN  ?? '/usr/bin/clang-format';
const CLANG_FORMAT_CONFIG = process.env.CLANG_FORMAT_CONFIG ?? join(__dirname, '.clang-format');

const RUFF        = process.env.RUFF_BIN    ?? 'ruff';
const RUFF_CONFIG = process.env.RUFF_CONFIG ?? join(__dirname, 'ruff.toml');

app.get('/api/config/clang-format', (_req, res) => {
  res.sendFile(CLANG_FORMAT_CONFIG);
});

app.get('/api/config/ruff', (_req, res) => {
  res.sendFile(RUFF_CONFIG);
});

app.post('/api/format', async (req, res) => {
  const { code, language = 'cpp' } = req.body;
  if (typeof code !== 'string') {
    return res.status(400).json({ error: 'code field required' });
  }

  if (language === 'python') {
    const tmpFile = join(tmpdir(), `fmt_${Date.now()}.py`);
    try {
      await writeFile(tmpFile, code, 'utf8');
      const cmd = `"${RUFF}" format --config "${RUFF_CONFIG}" --quiet "${tmpFile}" && cat "${tmpFile}"`;
      exec(cmd, { maxBuffer: 10 * 1024 * 1024 }, async (err, stdout, stderr) => {
        try { await unlink(tmpFile); } catch (_) {}
        if (err) return res.status(500).json({ error: stderr || err.message });
        res.json({ formatted: stdout });
      });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
    return;
  }

  // default: C++
  const tmpFile = join(tmpdir(), `fmt_${Date.now()}.cpp`);
  try {
    await writeFile(tmpFile, code, 'utf8');
    const cmd = `"${CLANG_FORMAT}" --Wno-error=unknown --style=file:"${CLANG_FORMAT_CONFIG}" "${tmpFile}"`;
    exec(cmd, { maxBuffer: 10 * 1024 * 1024 }, async (err, stdout, stderr) => {
      try { await unlink(tmpFile); } catch (_) {}
      if (err) return res.status(500).json({ error: stderr || err.message });
      res.json({ formatted: stdout });
    });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

// Serve built frontend (production)
const DIST = join(__dirname, 'dist');
app.use(express.static(DIST));
app.use((_req, res) => {
  res.sendFile(join(DIST, 'index.html'));
});

const PORT = process.env.PORT ?? 3000;
app.listen(PORT, () => {
  console.log(`Format server running on http://localhost:${PORT}`);
});
