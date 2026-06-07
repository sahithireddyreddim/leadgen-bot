"""
Simple Flask dashboard for monitoring the B2B Lead Generation Pipeline.
Accessible at http://localhost:5000 (or your deployed URL).
"""

import os
import sys
import threading
import logging
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request, redirect, url_for

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.database import init_db, get_pipeline_stats, get_all_outreach, get_leads_for_outreach
from config.settings import settings

app = Flask(__name__)
app.secret_key = settings.DASHBOARD_SECRET_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>B2B Lead Gen Dashboard</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #0f172a; color: #e2e8f0; min-height: 100vh; }
    header { background: #1e293b; border-bottom: 1px solid #334155;
             padding: 16px 24px; display: flex; align-items: center; gap: 12px; }
    header h1 { font-size: 1.25rem; font-weight: 600; color: #f1f5f9; }
    header span { font-size: 0.75rem; background: #22c55e; color: #fff;
                  padding: 2px 8px; border-radius: 99px; }
    .container { max-width: 1100px; margin: 0 auto; padding: 24px; }
    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
             gap: 16px; margin-bottom: 32px; }
    .stat-card { background: #1e293b; border: 1px solid #334155; border-radius: 12px;
                 padding: 20px; text-align: center; }
    .stat-card .num { font-size: 2rem; font-weight: 700; color: #38bdf8; }
    .stat-card .label { font-size: 0.8rem; color: #94a3b8; margin-top: 4px; }
    .actions { display: flex; gap: 12px; margin-bottom: 32px; flex-wrap: wrap; }
    .btn { padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer;
           font-size: 0.9rem; font-weight: 500; text-decoration: none;
           display: inline-flex; align-items: center; gap: 6px; transition: opacity .2s; }
    .btn:hover { opacity: .85; }
    .btn-primary { background: #3b82f6; color: #fff; }
    .btn-success { background: #22c55e; color: #fff; }
    .btn-warning { background: #f59e0b; color: #fff; }
    .btn-danger  { background: #ef4444; color: #fff; }
    .btn-secondary { background: #334155; color: #e2e8f0; }
    .section { background: #1e293b; border: 1px solid #334155; border-radius: 12px;
               padding: 20px; margin-bottom: 24px; }
    .section h2 { font-size: 1rem; font-weight: 600; color: #f1f5f9; margin-bottom: 16px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    th { text-align: left; padding: 10px 12px; color: #64748b;
         border-bottom: 1px solid #334155; font-weight: 500; }
    td { padding: 10px 12px; border-bottom: 1px solid #1e293b; vertical-align: top; }
    tr:hover td { background: #0f172a; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
             font-size: 0.75rem; font-weight: 500; }
    .badge-sent        { background: #14532d; color: #4ade80; }
    .badge-followed_up { background: #1e3a5f; color: #93c5fd; }
    .badge-pending     { background: #1e293b; color: #94a3b8; }
    .badge-failed      { background: #450a0a; color: #f87171; }
    .badge-rejected    { background: #312e0a; color: #facc15; }
    .badge-replied     { background: #064e3b; color: #34d399; }
    .modal-bg { display:none; position:fixed; inset:0; background:rgba(0,0,0,.7);
                z-index:50; align-items:center; justify-content:center; }
    .modal-bg.open { display:flex; }
    .modal { background:#1e293b; border:1px solid #334155; border-radius:12px;
             padding:24px; max-width:560px; width:90%; max-height:80vh; overflow-y:auto; }
    .modal h3 { margin-bottom:12px; color:#f1f5f9; }
    .modal pre { white-space:pre-wrap; font-size:0.82rem; color:#cbd5e1;
                 background:#0f172a; border-radius:8px; padding:12px; }
    .close-btn { float:right; background:none; border:none; color:#94a3b8;
                 font-size:1.2rem; cursor:pointer; }
    #toast { position:fixed; bottom:24px; right:24px; background:#22c55e; color:#fff;
             padding:12px 20px; border-radius:8px; display:none; font-size:.9rem; z-index:100; }
    #status-bar { background:#0f172a; padding:8px 24px; font-size:0.78rem;
                  color:#64748b; border-top:1px solid #1e293b; }
  </style>
</head>
<body>
  <header>
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#38bdf8"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
      <polyline points="22 4 12 14.01 9 11.01"/>
    </svg>
    <h1>B2B Lead Generation</h1>
    <span>Live</span>
  </header>

  <div class="container">
    <div class="stats" id="stats-grid">
      <div class="stat-card"><div class="num" id="s-discovered">–</div><div class="label">Discovered</div></div>
      <div class="stat-card"><div class="num" id="s-researched">–</div><div class="label">Researched</div></div>
      <div class="stat-card"><div class="num" id="s-rejected">–</div><div class="label">Rejected</div></div>
      <div class="stat-card"><div class="num" id="s-emailed">–</div><div class="label">Emailed</div></div>
      <div class="stat-card"><div class="num" id="s-sent">–</div><div class="label">Emails Sent</div></div>
      <div class="stat-card"><div class="num" id="s-followups">–</div><div class="label">Follow-ups Sent</div></div>
      <div class="stat-card"><div class="num" id="s-replied" style="color:#4ade80">–</div><div class="label">Replied</div></div>
      <div class="stat-card"><div class="num" id="s-failed">–</div><div class="label">Failed</div></div>
    </div>

    <div class="actions">
      <button class="btn btn-primary" onclick="runPipeline('all', false)">▶ Run Full Pipeline</button>
      <button class="btn btn-secondary" onclick="runPipeline('all', true)">🔍 Dry Run</button>
      <button class="btn btn-success"  onclick="runPipeline('find', false)">🔎 Find Leads</button>
      <button class="btn btn-warning"  onclick="runPipeline('research', false)">📋 Research</button>
      <button class="btn btn-danger"   onclick="runPipeline('outreach', false)">✉ Send Emails</button>
      <button class="btn btn-primary"  onclick="runPipeline('followup', false)" style="background:#8b5cf6">↩ Send Follow-ups</button>
      <button class="btn btn-secondary" onclick="loadData()">↻ Refresh</button>
    </div>

    <div class="section">
      <h2>Recent Outreach</h2>
      <table>
        <thead>
          <tr>
            <th>Company</th><th>Industry</th><th>Region</th><th>Email Sent To</th>
            <th>Subject</th><th>Status</th><th>Date</th><th></th>
          </tr>
        </thead>
        <tbody id="outreach-table">
          <tr><td colspan="8" style="text-align:center;color:#64748b">Loading...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <div id="status-bar">Pipeline ready. Use the buttons above to start.</div>
  <div id="toast"></div>

  <div class="modal-bg" id="email-modal">
    <div class="modal">
      <button class="close-btn" onclick="closeModal()">✕</button>
      <h3 id="modal-subject"></h3>
      <p style="color:#94a3b8;font-size:.8rem;margin-bottom:8px">To: <span id="modal-to"></span></p>
      <pre id="modal-body"></pre>
    </div>
  </div>

  <script>
    function toast(msg, color='#22c55e') {
      const el = document.getElementById('toast');
      el.textContent = msg; el.style.background = color;
      el.style.display = 'block';
      setTimeout(() => el.style.display = 'none', 3000);
    }
    function status(msg) {
      document.getElementById('status-bar').textContent = msg;
    }

    async function loadStats() {
      const r = await fetch('/api/stats');
      const d = await r.json();
      document.getElementById('s-discovered').textContent = d.discovered || 0;
      document.getElementById('s-researched').textContent = d.researched || 0;
      document.getElementById('s-rejected').textContent   = d.rejected   || 0;
      document.getElementById('s-emailed').textContent    = d.emailed    || 0;
      document.getElementById('s-sent').textContent       = d.emails_sent || 0;
      document.getElementById('s-followups').textContent  = d.follow_ups_sent || 0;
      document.getElementById('s-replied').textContent    = d.replied    || 0;
      document.getElementById('s-failed').textContent     = d.emails_failed || 0;
    }

    async function loadOutreach() {
      const r = await fetch('/api/outreach');
      const rows = await r.json();
      const tbody = document.getElementById('outreach-table');
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#64748b">No outreach yet. Run the pipeline first.</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(row => {
        const badge = {
          sent:'badge-sent', followed_up:'badge-followed_up',
          replied:'badge-replied', pending:'badge-pending',
          failed:'badge-failed', dry_run:'badge-pending'
        }[row.status] || 'badge-pending';
        const followLabel = row.follow_up_count > 0 ? ` <span style="font-size:.7rem;color:#94a3b8">(+${row.follow_up_count} FU)</span>` : '';
        const date = row.sent_at ? row.sent_at.split('T')[0] : (row.created_at||'').split('T')[0];
        return `<tr>
          <td><strong>${esc(row.company_name)}</strong></td>
          <td>${esc(row.industry||'')}</td>
          <td style="color:#a78bfa">${esc(row.region||row.country||'')}</td>
          <td style="color:#60a5fa">${esc(row.contact_email||'')}</td>
          <td>${esc(row.email_subject||'')}</td>
          <td><span class="badge ${badge}">${row.status}</span>${followLabel}</td>
          <td style="color:#64748b">${date}</td>
          <td><button class="btn btn-secondary" style="padding:4px 10px;font-size:.75rem"
              onclick='showEmail(${JSON.stringify(row.email_subject)},${JSON.stringify(row.contact_email)},${JSON.stringify(row.email_body)})'>View</button></td>
        </tr>`;
      }).join('');
    }

    function esc(str) {
      return String(str||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    function showEmail(subject, to, body) {
      document.getElementById('modal-subject').textContent = subject;
      document.getElementById('modal-to').textContent = to;
      document.getElementById('modal-body').textContent = body;
      document.getElementById('email-modal').classList.add('open');
    }
    function closeModal() {
      document.getElementById('email-modal').classList.remove('open');
    }

    async function runPipeline(stage, dryRun) {
      status(`Running pipeline (stage: ${stage}, dry_run: ${dryRun})...`);
      toast('Pipeline started...', '#3b82f6');
      try {
        const r = await fetch('/api/run', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({stage, dry_run: dryRun})
        });
        const d = await r.json();
        if (d.error) {
          toast('Error: ' + d.error, '#ef4444');
          status('Pipeline error: ' + d.error);
        } else {
          toast(`Done! Sent: ${d.emails_sent || 0}, Found: ${d.new_leads || 0}`, '#22c55e');
          status(`Pipeline complete – ${JSON.stringify(d)}`);
          loadData();
        }
      } catch(e) {
        toast('Pipeline failed: ' + e, '#ef4444');
        status('Error: ' + e);
      }
    }

    function loadData() { loadStats(); loadOutreach(); }
    loadData();
    setInterval(loadData, 30000);
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route("/api/stats")
def api_stats():
    try:
        return jsonify(get_pipeline_stats())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/outreach")
def api_outreach():
    try:
        limit = request.args.get("limit", 50, type=int)
        return jsonify(get_all_outreach(limit=limit))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/run", methods=["POST"])
def api_run():
    """Trigger the pipeline in a background thread."""
    data = request.get_json() or {}
    stage = data.get("stage", "all")
    dry_run = data.get("dry_run", False)
    target = data.get("target", settings.DAILY_TARGET)

    def _run():
        try:
            from main import run_pipeline
            run_pipeline(stage=stage, target=target, dry_run=dry_run)
        except Exception as e:
            logger.error("Pipeline error: %s", e)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({
        "status": "started",
        "stage": stage,
        "dry_run": dry_run,
        "target": target,
    })


@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    init_db()
    port = settings.DASHBOARD_PORT
    logger.info("Dashboard running at http://0.0.0.0:%d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
