"""Standalone OpenTelemetry Observability Dashboard Server.
Runs on internal port 5200 (bridged to external port 5209).
Provides interactive Web UI for Traces, Metrics, and Structured Logs.
"""

from __future__ import annotations

import json
import time
import os
import http.server
import socketserver
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = 5200
LOGS_DIR = Path("/home/student/pond_panning/logs")
if not LOGS_DIR.exists():
    LOGS_DIR = Path(__file__).resolve().parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
SPANS_FILE = LOGS_DIR / "otel_spans.jsonl"
LOGS_FILE = LOGS_DIR / "telemetry.log"

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OpenTelemetry Observability Dashboard | Village Pond Planning</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" />
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #0f172a;
      --border: rgba(255, 255, 255, 0.1);
      --primary: #38bdf8;
      --accent: #06b6d4;
      --success: #22c55e;
      --warning: #f59e0b;
      --danger: #ef4444;
      --text: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', sans-serif;
      background: var(--bg);
      color: var(--text);
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
    }
    header {
      background: var(--card-bg);
      border-bottom: 1px solid var(--border);
      padding: 14px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      z-index: 10;
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand i { font-size: 24px; color: var(--primary); }
    .brand h1 { font-size: 18px; font-weight: 700; letter-spacing: -0.5px; }
    .brand .badge {
      font-size: 11px;
      padding: 3px 8px;
      background: rgba(56, 189, 248, 0.15);
      color: var(--primary);
      border-radius: 999px;
      border: 1px solid rgba(56, 189, 248, 0.3);
    }
    .nav-tabs { display: flex; gap: 6px; }
    .tab-btn {
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-muted);
      padding: 8px 16px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s;
    }
    .tab-btn.active, .tab-btn:hover {
      background: rgba(255, 255, 255, 0.06);
      color: var(--text);
      border-color: var(--border);
    }
    .tab-btn.active { color: var(--primary); border-color: rgba(56, 189, 248, 0.4); }
    .main { flex: 1; overflow-y: auto; padding: 24px; }
    .tab-content { display: none; }
    .tab-content.active { display: block; }

    /* Cards */
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 20px;
      margin-bottom: 20px;
    }
    .card-title {
      font-size: 14px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    /* Metrics Grid */
    .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
    .metric-card {
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
    }
    .metric-label { font-size: 12px; color: var(--text-muted); margin-bottom: 6px; }
    .metric-val { font-size: 26px; font-weight: 700; color: #fff; font-family: 'JetBrains Mono', monospace; }
    .metric-unit { font-size: 13px; color: var(--primary); margin-left: 4px; font-weight: 500; }

    /* Trace Waterfall */
    .trace-item {
      border: 1px solid var(--border);
      border-radius: 8px;
      margin-bottom: 12px;
      background: rgba(255, 255, 255, 0.02);
      overflow: hidden;
    }
    .trace-header {
      padding: 14px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      background: rgba(255, 255, 255, 0.03);
    }
    .trace-header:hover { background: rgba(56, 189, 248, 0.05); }
    .trace-id {
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      color: var(--primary);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .span-bar-row {
      display: flex;
      align-items: center;
      padding: 8px 18px;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
      font-size: 12px;
    }
    .span-name { width: 220px; font-weight: 600; font-family: 'JetBrains Mono', monospace; }
    .span-bar-container { flex: 1; height: 18px; background: rgba(255, 255, 255, 0.05); border-radius: 4px; position: relative; margin: 0 16px; }
    .span-bar { height: 100%; border-radius: 4px; position: absolute; background: linear-gradient(90deg, var(--accent), var(--primary)); }
    .span-duration { width: 90px; text-align: right; font-family: 'JetBrains Mono', monospace; color: var(--text-muted); }
    .span-details { padding: 12px 18px; background: rgba(0, 0, 0, 0.4); border-top: 1px solid rgba(255, 255, 255, 0.05); }
    .attr-table { width: 100%; font-size: 12px; font-family: 'JetBrains Mono', monospace; }
    .attr-table td { padding: 4px 8px; border-bottom: 1px solid rgba(255, 255, 255, 0.03); }
    .attr-key { color: var(--primary); width: 240px; }
    .attr-val { color: var(--text); word-break: break-all; }

    /* Logs view */
    .log-terminal {
      background: #020617;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      height: 520px;
      overflow-y: auto;
      line-height: 1.6;
    }
    .log-line { margin-bottom: 4px; white-space: pre-wrap; }
    .log-line .trace { color: var(--accent); }
    .log-line .info { color: var(--success); }
    .log-line .warn { color: var(--warning); }
    .log-line .error { color: var(--danger); }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <i class="fa-solid fa-chart-line"></i>
      <h1>OpenTelemetry Observability</h1>
      <span class="badge">Live Monitoring (stu3_sys1)</span>
    </div>
    <div class="nav-tabs">
      <button class="tab-btn active" onclick="switchTab('traces')"><i class="fa-solid fa-network-wired"></i> Traces & Spans</button>
      <button class="tab-btn" onclick="switchTab('metrics')"><i class="fa-solid fa-gauge-high"></i> Metrics (Prometheus)</button>
      <button class="tab-btn" onclick="switchTab('logs')"><i class="fa-solid fa-terminal"></i> Correlated Logs</button>
      <a href="http://10.1.75.51:16686" target="_blank" class="tab-btn" style="text-decoration:none;"><i class="fa-solid fa-arrow-up-right-from-square"></i> Open Jaeger UI</a>
    </div>
  </header>

  <div class="main">
    <!-- TRACES TAB -->
    <div id="traces" class="tab-content active">
      <div class="card">
        <div class="card-title">
          <span><i class="fa-solid fa-water"></i> Distributed Trace Waterfall</span>
          <button class="tab-btn" style="padding:4px 10px; font-size:11px;" onclick="loadTraces()"><i class="fa-solid fa-rotate-right"></i> Refresh</button>
        </div>
        <div id="traceList">Loading traces...</div>
      </div>
    </div>

    <!-- METRICS TAB -->
    <div id="metrics" class="tab-content">
      <div class="card">
        <div class="card-title">
          <span><i class="fa-solid fa-chart-simple"></i> Hydrological & Service Metrics</span>
          <button class="tab-btn" style="padding:4px 10px; font-size:11px;" onclick="loadMetrics()"><i class="fa-solid fa-rotate-right"></i> Refresh</button>
        </div>
        <div class="metric-grid" id="metricsGrid">
          <div class="metric-card"><div class="metric-label">Total Requests</div><div class="metric-val" id="mRequests">--</div></div>
          <div class="metric-card"><div class="metric-label">Last Duration</div><div class="metric-val" id="mDuration">--<span class="metric-unit">sec</span></div></div>
          <div class="metric-card"><div class="metric-label">Catchment Area</div><div class="metric-val" id="mArea">--<span class="metric-unit">m²</span></div></div>
          <div class="metric-card"><div class="metric-label">Expected Volume</div><div class="metric-val" id="mVolume">--<span class="metric-unit">m³</span></div></div>
          <div class="metric-card"><div class="metric-label">Contour Lines</div><div class="metric-val" id="mContours">--</div></div>
          <div class="metric-card"><div class="metric-label">DEM Grid Cells</div><div class="metric-val" id="mCells">--</div></div>
          <div class="metric-card"><div class="metric-label">Topographic Relief</div><div class="metric-val" id="mRelief">--<span class="metric-unit">m</span></div></div>
          <div class="metric-card"><div class="metric-label">Recommended Depth</div><div class="metric-val" id="mDepth">--<span class="metric-unit">m</span></div></div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">Raw Prometheus Exporter Output (/metrics)</div>
        <pre style="background:#020617; padding:14px; border-radius:8px; font-family:'JetBrains Mono'; font-size:11px; max-height:280px; overflow-y:auto; color:var(--text-muted);" id="rawMetrics">Loading...</pre>
      </div>
    </div>

    <!-- LOGS TAB -->
    <div id="logs" class="tab-content">
      <div class="card">
        <div class="card-title">
          <span><i class="fa-solid fa-file-lines"></i> OpenTelemetry Correlated Structured Logs (Trace-Correlated)</span>
          <button class="tab-btn" style="padding:4px 10px; font-size:11px;" onclick="loadLogs()"><i class="fa-solid fa-rotate-right"></i> Refresh</button>
        </div>
        <div class="log-terminal" id="logTerminal">Loading logs...</div>
      </div>
    </div>
  </div>

  <script>
    function switchTab(tabId) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      event.currentTarget.classList.add('active');
      document.getElementById(tabId).classList.add('active');
      if (tabId === 'traces') loadTraces();
      if (tabId === 'metrics') loadMetrics();
      if (tabId === 'logs') loadLogs();
    }

    async function loadTraces() {
      try {
        const res = await fetch('/api/spans');
        const data = await res.json();
        const list = document.getElementById('traceList');
        if (!data.spans || data.spans.length === 0) {
          list.innerHTML = '<div style="color:var(--text-muted); font-size:13px; padding:20px 0;">No traces recorded yet. Run an analysis on the frontend or curl /analyzeContour to generate traces!</div>';
          return;
        }

        // Group spans by trace_id
        const traces = {};
        data.spans.forEach(s => {
          if (!traces[s.trace_id]) traces[s.trace_id] = [];
          traces[s.trace_id].push(s);
        });

        let html = '';
        for (const [tid, spans] of Object.entries(traces)) {
          const rootSpan = spans.find(s => !s.parent_span_id) || spans[0];
          const totalDuration = rootSpan.duration_ms || spans.reduce((m, s) => Math.max(m, s.duration_ms || 0), 0);
          const startTime = rootSpan.start_time_ns;

          html += `
            <div class="trace-item">
              <div class="trace-header" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none'">
                <div class="trace-id">
                  <i class="fa-solid fa-fingerprint"></i>
                  <span>Trace: ${tid.substring(0, 16)}...</span>
                  <span style="color:#fff; font-weight:600; margin-left:12px;">${rootSpan.name}</span>
                </div>
                <div style="font-family:'JetBrains Mono'; font-size:12px; color:var(--primary); font-weight:600;">
                  ${totalDuration} ms &bull; ${spans.length} spans
                </div>
              </div>
              <div class="trace-body">`;

          spans.forEach(s => {
            const startOffset = Math.max(0, ((s.start_time_ns - startTime) / 1e6));
            const leftPct = Math.min(95, (startOffset / (totalDuration || 1)) * 100);
            const widthPct = Math.max(3, Math.min(100 - leftPct, ((s.duration_ms || 1) / (totalDuration || 1)) * 100));

            html += `
              <div class="span-bar-row">
                <div class="span-name">${s.name}</div>
                <div class="span-bar-container">
                  <div class="span-bar" style="left:${leftPct}%; width:${widthPct}%;"></div>
                </div>
                <div class="span-duration">${s.duration_ms || '<0.1'} ms</div>
              </div>
              <div class="span-details">
                <table class="attr-table">`;
            for (const [k, v] of Object.entries(s.attributes || {})) {
              html += `<tr><td class="attr-key">${k}</td><td class="attr-val">${v}</td></tr>`;
            }
            html += `</table></div>`;
          });

          html += `</div></div>`;
        }
        list.innerHTML = html;
      } catch (e) {
        document.getElementById('traceList').innerText = 'Error loading traces: ' + e;
      }
    }

    async function loadMetrics() {
      try {
        const res = await fetch('/api/metrics');
        const text = await res.text();
        document.getElementById('rawMetrics').innerText = text;

        function extractVal(metricName) {
          const match = text.match(new RegExp(`^${metricName}(\\{[^}]*\\})?\\s+([0-9.]+)`, 'm'));
          return match ? parseFloat(match[2]) : null;
        }

        const reqs = extractVal('pond_analysis_requests_total');
        const area = extractVal('pond_catchment_area_square_meters');
        const vol = extractVal('pond_expected_water_volume_cubic_meters');
        const lines = extractVal('pond_contour_lines_count');
        const cells = extractVal('pond_dem_grid_cells_total');
        const relief = extractVal('pond_topographic_relief_meters');
        const depth = extractVal('pond_recommended_depth_meters');

        if (reqs !== null) document.getElementById('mRequests').innerText = reqs;
        if (area !== null) document.getElementById('mArea').innerText = area.toLocaleString();
        if (vol !== null) document.getElementById('mVolume').innerText = vol.toLocaleString();
        if (lines !== null) document.getElementById('mContours').innerText = lines.toLocaleString();
        if (cells !== null) document.getElementById('mCells').innerText = cells.toLocaleString();
        if (relief !== null) document.getElementById('mRelief').innerText = relief.toFixed(1);
        if (depth !== null) document.getElementById('mDepth').innerText = depth.toFixed(1);
      } catch (e) {
        console.error(e);
      }
    }

    async function loadLogs() {
      try {
        const res = await fetch('/api/logs');
        const text = await res.text();
        const terminal = document.getElementById('logTerminal');
        const lines = text.trim().split('\\n');
        let html = '';
        lines.forEach(l => {
          let cls = 'info';
          if (l.includes('[ERROR]')) cls = 'error';
          if (l.includes('[WARN]')) cls = 'warn';
          html += `<div class="log-line ${cls}">${escapeHtml(l)}</div>`;
        });
        terminal.innerHTML = html || 'No logs yet.';
        terminal.scrollTop = terminal.scrollHeight;
      } catch (e) {
        document.getElementById('logTerminal').innerText = 'Error loading logs: ' + e;
      }
    }

    function escapeHtml(str) {
      return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // Auto-refresh traces initially
    loadTraces();
  </script>
</body>
</html>
"""

class TelemetryHandler(http.server.BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/" or parsed.path == "/index.html":
            content = HTML_DASHBOARD.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        elif parsed.path == "/api/spans":
            spans = []
            if SPANS_FILE.exists():
                try:
                    with open(SPANS_FILE, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                spans.append(json.loads(line))
                except Exception:
                    pass
            body = json.dumps({"spans": spans[-100:], "count": len(spans)}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif parsed.path == "/api/metrics":
            # Proxy from FastAPI :3000/metrics
            try:
                req = urllib.request.urlopen("http://127.0.0.1:3000/metrics", timeout=2)
                body = req.read()
            except Exception as exc:
                body = f"# Error fetching metrics from :3000: {exc}".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif parsed.path == "/api/logs":
            logs = ""
            if LOGS_FILE.exists():
                try:
                    with open(LOGS_FILE, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        logs = "".join(lines[-150:])
                except Exception:
                    pass
            body = logs.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_response(404)
            self.end_headers()


def run():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), TelemetryHandler) as httpd:
        print(f"[*] OpenTelemetry Dashboard serving at http://0.0.0.0:{PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    run()
