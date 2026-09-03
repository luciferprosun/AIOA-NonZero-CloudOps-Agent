"""Self-contained, dependency-free judge console for the portable Local-2 API."""

import base64
import hashlib
from collections.abc import Mapping
from typing import Final

JUDGE_UI_STYLE: Final = r"""
:root {
  color-scheme: dark;
  --ink: #f4f7f5;
  --muted: #a7b4ae;
  --dim: #728079;
  --canvas: #090d0b;
  --surface: #101613;
  --surface-2: #151d19;
  --line: #27322d;
  --mint: #b9f87d;
  --mint-dark: #16351e;
  --amber: #ffbe58;
  --amber-dark: #3a2811;
  --violet: #bba6ff;
  --red: #ff897d;
  --red-dark: #3b1816;
  --radius: 22px;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--canvas);
  color: var(--ink);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
  background:
    radial-gradient(circle at 8% -10%, #264126 0, transparent 34rem),
    radial-gradient(circle at 96% 6%, #291f45 0, transparent 30rem),
    var(--canvas);
}
button, input { font: inherit; }
button { min-height: 44px; }
button:focus-visible, input:focus-visible, summary:focus-visible {
  outline: 3px solid var(--violet);
  outline-offset: 3px;
}
.skip-link {
  position: fixed;
  left: 12px;
  top: -80px;
  z-index: 50;
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--ink);
  color: var(--canvas);
}
.skip-link:focus { top: 12px; }
.shell { width: min(1240px, calc(100% - 40px)); margin: 0 auto; }
.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  border-bottom: 1px solid #ffffff12;
  background: #090d0bd9;
  backdrop-filter: blur(18px);
}
.topbar-inner {
  min-height: 74px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}
.brand { display: flex; align-items: center; gap: 12px; font-weight: 850; letter-spacing: -.02em; }
.brand-mark {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border: 1px solid #cfff9a66;
  border-radius: 11px;
  background: #b9f87d16;
  color: var(--mint);
  font-size: 18px;
}
.brand-sub { color: var(--muted); font-weight: 520; }
.mode-cluster { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 30px;
  padding: 5px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #111814;
  color: var(--muted);
  font-size: .74rem;
  font-weight: 760;
  letter-spacing: .055em;
  text-transform: uppercase;
}
.pill::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--dim); }
.pill.safe { color: var(--mint); border-color: #88bd5d55; }
.pill.safe::before { background: var(--mint); box-shadow: 0 0 14px #b9f87daa; }
.hero { padding: clamp(54px, 8vw, 102px) 0 44px; }
.kicker { color: var(--mint); font-size: .8rem; font-weight: 850; letter-spacing: .16em; text-transform: uppercase; }
h1 {
  max-width: 900px;
  margin: 16px 0 20px;
  font-size: clamp(2.55rem, 7vw, 6rem);
  line-height: .92;
  letter-spacing: -.065em;
  font-weight: 850;
}
.hero-copy { max-width: 750px; margin: 0; color: var(--muted); font-size: clamp(1rem, 2vw, 1.22rem); line-height: 1.65; }
.truth-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  max-width: 850px;
  margin-top: 32px;
}
.truth {
  padding: 15px 16px;
  border: 1px solid var(--line);
  border-radius: 15px;
  background: #111713bb;
}
.truth strong { display: block; color: var(--mint); font-size: 1.05rem; }
.truth span { color: var(--dim); font-size: .78rem; }
.section { margin: 30px 0 72px; }
.section-heading { display: flex; justify-content: space-between; align-items: end; gap: 20px; margin-bottom: 18px; }
.section-number { color: var(--mint); font: 750 .76rem ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: .1em; }
h2 { margin: 5px 0 0; font-size: clamp(1.45rem, 3vw, 2.2rem); letter-spacing: -.035em; }
.section-note { max-width: 520px; color: var(--muted); line-height: 1.5; text-align: right; }
.scenario-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.scenario {
  position: relative;
  min-height: 250px;
  padding: 25px;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: linear-gradient(145deg, #151d19, #0d120f);
  color: var(--ink);
  text-align: left;
  cursor: pointer;
  transition: transform .18s ease, border-color .18s ease, background .18s ease;
}
.scenario:hover:not(:disabled) { transform: translateY(-3px); border-color: #b9f87d66; background: linear-gradient(145deg, #19241d, #0d120f); }
.scenario:disabled { opacity: .5; cursor: not-allowed; }
.scenario::after {
  content: "→";
  position: absolute;
  right: 22px;
  bottom: 17px;
  color: var(--mint);
  font-size: 2rem;
}
.scenario.deny::after { color: var(--amber); }
.scenario-tag { color: var(--mint); font: 800 .74rem ui-monospace, monospace; letter-spacing: .1em; text-transform: uppercase; }
.scenario.deny .scenario-tag { color: var(--amber); }
.scenario h3 { max-width: 380px; margin: 24px 0 10px; font-size: clamp(1.4rem, 3vw, 2rem); letter-spacing: -.035em; }
.scenario p { max-width: 480px; margin: 0; color: var(--muted); line-height: 1.55; }
.hero-scenario {
  width: 100%;
  min-height: 300px;
  margin-bottom: 14px;
  border-color: #b9f87d66;
  background:
    linear-gradient(115deg, #1c3021 0%, #131b17 54%, #211a35 100%);
}
.hero-scenario h3 { max-width: 760px; font-size: clamp(1.8rem, 4vw, 3.2rem); }
.hero-scenario p { max-width: 760px; font-size: 1.02rem; }
.hero-scenario .scenario-tag { color: var(--mint); }
.secondary-story-label {
  margin: 22px 0 10px;
  color: var(--dim);
  font-size: .74rem;
  font-weight: 800;
  letter-spacing: .09em;
  text-transform: uppercase;
}
.session-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 14px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 15px;
  background: #101613;
}
.session-copy { display: flex; align-items: center; gap: 10px; color: var(--muted); }
.session-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--amber); }
.session-dot.connected { background: var(--mint); box-shadow: 0 0 14px #b9f87d88; }
.quiet-button {
  width: auto;
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
}
.pipeline {
  display: grid;
  grid-template-columns: repeat(8, minmax(0, 1fr));
  gap: 7px;
  margin: 0 0 16px;
  padding: 0;
  list-style: none;
}
.pipeline li {
  position: relative;
  min-height: 73px;
  padding: 12px 10px;
  border: 1px solid var(--line);
  border-radius: 13px;
  background: #0e1411;
  color: var(--dim);
  font-size: .72rem;
  line-height: 1.35;
}
.pipeline li span { display: block; margin-bottom: 5px; font: 750 .68rem ui-monospace, monospace; }
.pipeline li.done { border-color: #6f995144; background: #122017; color: var(--muted); }
.pipeline li.done span { color: var(--mint); }
.pipeline li.current { border-color: #bba6ff88; background: #211b34; color: var(--ink); }
.pipeline li.safe-stop { border-color: #ffbe5866; background: var(--amber-dark); color: #ffe0ac; }
.hero-pipeline { grid-template-columns: repeat(10, minmax(108px, 1fr)); overflow-x: auto; }
.hero-pipeline li { min-width: 108px; }
.workspace-grid { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(300px, .75fr); gap: 14px; }
.hero-workspace-grid { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(330px, .8fr); gap: 14px; }
.stack { display: grid; gap: 14px; align-content: start; }
.panel {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: #101613e8;
  box-shadow: 0 22px 55px #0000002b;
}
.panel-pad { padding: 22px; }
.panel-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 20px; }
.panel h3 { margin: 0; font-size: 1rem; letter-spacing: -.01em; }
.state-badge {
  max-width: 100%;
  padding: 6px 9px;
  overflow: hidden;
  border-radius: 8px;
  background: #202a25;
  color: var(--muted);
  font: 800 .68rem ui-monospace, monospace;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.state-badge.success { background: var(--mint-dark); color: var(--mint); }
.state-badge.denied { background: var(--amber-dark); color: var(--amber); }
.facts { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin: 0; }
.fact { min-width: 0; padding-top: 12px; border-top: 1px solid var(--line); }
.fact.wide { grid-column: 1 / -1; }
.fact dt { margin-bottom: 5px; color: var(--dim); font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; }
.fact dd { margin: 0; overflow-wrap: anywhere; color: var(--ink); font-size: .91rem; line-height: 1.45; }
.hash { color: var(--violet); font: .78rem ui-monospace, SFMono-Regular, Menlo, monospace; }
.authority-callout {
  margin-top: 18px;
  padding: 15px;
  border: 1px solid #ffbe5844;
  border-radius: 14px;
  background: #2b2112;
  color: #ffe4b8;
  line-height: 1.5;
}
.authority-callout strong { display: block; margin-bottom: 5px; color: var(--amber); }
.controls { display: grid; gap: 9px; }
.button {
  width: 100%;
  padding: 12px 15px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: var(--mint);
  color: #10200d;
  font-weight: 850;
  cursor: pointer;
}
.button:hover:not(:disabled) { filter: brightness(1.05); }
.button:disabled { opacity: .38; cursor: not-allowed; }
.button.secondary { border-color: var(--line); background: #1a231f; color: var(--ink); }
.button.deny { border-color: #ffbe5844; background: var(--amber-dark); color: var(--amber); }
.button-row { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
.decision-state { margin: 0 0 14px; color: var(--muted); line-height: 1.5; }
.proof {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 16px;
}
.proof div { padding: 12px; border: 1px solid var(--line); border-radius: 12px; background: #0c110e; }
.proof strong { display: block; color: var(--mint); font-size: 1.2rem; }
.proof span { color: var(--dim); font-size: .72rem; }
.outcome {
  margin-top: 16px;
  padding: 15px;
  border-radius: 14px;
  background: #0c110e;
  color: var(--muted);
  line-height: 1.5;
}
.outcome.success { border: 1px solid #b9f87d55; color: #dbffc0; }
.outcome.denied { border: 1px solid #ffbe5855; color: #ffe1af; }
.resource-diff { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 16px; }
.resource-diff div { min-width: 0; padding: 13px; border: 1px solid var(--line); border-radius: 12px; background: #0b100d; }
.resource-diff span { display: block; margin-bottom: 8px; color: var(--dim); font-size: .72rem; text-transform: uppercase; }
.resource-diff code { overflow-wrap: anywhere; color: var(--muted); font-size: .75rem; white-space: pre-wrap; }
.timeline { margin: 0; padding: 0; list-style: none; }
.timeline li { position: relative; padding: 0 0 20px 27px; }
.timeline li::before { content: ""; position: absolute; left: 4px; top: 5px; width: 9px; height: 9px; border: 2px solid var(--mint); border-radius: 50%; background: var(--surface); }
.timeline li::after { content: ""; position: absolute; left: 9px; top: 18px; bottom: 1px; width: 1px; background: var(--line); }
.timeline li:last-child::after { display: none; }
.timeline strong { display: block; font-size: .87rem; }
.timeline .category { display: inline-block; margin-bottom: 4px; color: var(--mint); font: 750 .62rem ui-monospace, monospace; letter-spacing: .08em; }
.timeline time { display: block; margin: 3px 0; color: var(--dim); font-size: .72rem; }
.timeline code { color: var(--violet); font-size: .68rem; overflow-wrap: anywhere; }
.timeline .pending::before { border-color: var(--dim); }
.timeline .safe-stop::before { border-color: var(--amber); }
.timeline-summary { display: block; margin-top: 4px; color: var(--muted); font-size: .78rem; line-height: 1.45; }
.timeline-source { display: block; margin-top: 4px; color: var(--dim); font: .66rem ui-monospace, monospace; }
.diff-panel {
  max-width: 100%;
  margin: 0;
  padding: 16px;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: 13px;
  background: #060906;
  color: #d8e5dd;
  font: .75rem/1.55 ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: pre;
}
.proof-list { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.proof-list li {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: #0b100d;
  color: var(--muted);
}
.proof-list strong { color: var(--ink); font: .72rem ui-monospace, monospace; }
.proof-list strong.pass { color: var(--mint); }
.approval-warning {
  margin-top: 14px;
  padding: 13px;
  border: 1px solid #ffbe5855;
  border-radius: 12px;
  background: var(--amber-dark);
  color: #ffe1af;
  line-height: 1.45;
}
.stage-truth {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.stage-truth article { padding: 14px; border: 1px solid var(--line); border-radius: 13px; background: #0b100d; }
.stage-truth h4 { margin: 0 0 10px; color: var(--muted); font-size: .76rem; letter-spacing: .08em; text-transform: uppercase; }
.stage-truth p { margin: 0; color: var(--ink); line-height: 1.5; }
.recovery-badge { color: var(--violet); border-color: #bba6ff55; }
.empty { color: var(--dim); line-height: 1.55; }
details.technical { border-top: 1px solid var(--line); }
.technical-wrap { margin-top: 14px; }
details.technical summary { padding: 17px 22px; color: var(--muted); cursor: pointer; }
details.technical pre {
  max-height: 480px;
  margin: 0 16px 16px;
  padding: 15px;
  overflow: auto;
  border-radius: 12px;
  background: #060906;
  color: #b9c7bf;
  font: .73rem/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.connection details { border: 1px solid var(--line); border-radius: 15px; background: #0e1411; }
.connection summary { padding: 14px 16px; color: var(--muted); cursor: pointer; }
.connection-form { display: grid; grid-template-columns: 1fr auto auto; gap: 8px; padding: 0 14px 14px; }
.connection input { min-width: 0; padding: 11px; border: 1px solid var(--line); border-radius: 10px; background: #070a08; color: var(--ink); }
.connection .button { width: auto; }
.notice {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 40;
  width: min(440px, calc(100% - 40px));
  padding: 14px 16px;
  border: 1px solid #b9f87d55;
  border-radius: 14px;
  background: #142019f2;
  box-shadow: 0 18px 55px #0009;
  color: #e6ffd5;
  line-height: 1.45;
}
.notice.error { border-color: #ff897d66; background: #2a1716f2; color: #ffd1cc; }
.footer { padding: 0 0 54px; color: var(--dim); font-size: .78rem; }
[hidden] { display: none !important; }
@media (max-width: 980px) {
  .pipeline { grid-template-columns: repeat(4, 1fr); }
  .workspace-grid, .hero-workspace-grid { grid-template-columns: 1fr; }
  .hero-pipeline { display: flex; grid-template-columns: none; }
  .hero-pipeline li { flex: 0 0 132px; }
}
@media (max-width: 700px) {
  .shell { width: min(100% - 24px, 1240px); }
  .topbar-inner { min-height: 66px; align-items: flex-start; padding: 13px 0; }
  .brand-sub { display: none; }
  .mode-cluster .pill:nth-child(2) { display: none; }
  .hero { padding-top: 48px; }
  .truth-grid, .scenario-grid, .facts, .resource-diff, .stage-truth { grid-template-columns: 1fr; }
  .fact.wide { grid-column: auto; }
  .section-heading { display: block; }
  .section-note { margin: 10px 0 0; text-align: left; }
  .scenario { min-height: 220px; }
  .pipeline { display: flex; overflow-x: auto; padding-bottom: 6px; scroll-snap-type: x mandatory; }
  .pipeline li { flex: 0 0 132px; scroll-snap-align: start; }
  .session-strip { align-items: flex-start; }
  .connection-form { grid-template-columns: 1fr; }
  .connection .button { width: 100%; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after { transition-duration: .001ms !important; }
}
""".strip()

JUDGE_UI_SCRIPT: Final = r"""
(() => {
  'use strict';
  const byId = (id) => document.getElementById(id);
  const ui = {
    connected: false,
    busy: false,
    runId: '',
    heroRunId: '',
    challenge: null,
    view: null,
    heroView: null,
    replayProven: false,
  };
  const labels = {
    RUN_CREATED: 'Run identity created',
    RESOURCE_QUERIED: 'Sandbox resource observed',
    REMEDIATION_PLANNED: 'Bounded remediation proposed',
    APPROVAL_REQUESTED: 'Human approval requested',
    APPROVAL_RECORDED: 'Human decision recorded',
    IDEMPOTENCY_REGISTERED: 'Single-effect intent registered',
    EXECUTION_REQUESTED: 'Approved action sent to sandbox',
    EXECUTION_ACKNOWLEDGED: 'Sandbox receipt persisted',
    VERIFICATION_RECORDED: 'Independent read-back verified',
    POLICY_DENIED: 'Unsafe or stale request rejected',
    MODEL_OUTPUT_REJECTED: 'Untrusted model output rejected',
    NO_ACTION_RECORDED: 'No action required',
    RECOMMENDATION_RECORDED: 'Recommendation only',
  };

  class ApiError extends Error {
    constructor(status, payload) {
      super(String(payload.failure_code || payload.error || 'REQUEST_FAILED'));
      this.status = status;
      this.payload = payload;
    }
  }

  function announce(message, isError = false) {
    const notice = byId('notice');
    notice.textContent = message;
    notice.classList.toggle('error', isError);
    notice.hidden = false;
    window.clearTimeout(announce.timer);
    announce.timer = window.setTimeout(() => { notice.hidden = true; }, 7000);
  }

  function shortHash(value) {
    return typeof value === 'string' && value.length > 18
      ? value.slice(0, 10) + '…' + value.slice(-8)
      : (value || '—');
  }

  function setText(id, value, title = '') {
    const node = byId(id);
    node.textContent = value == null || value === '' ? '—' : String(value);
    node.title = title || (typeof value === 'string' ? value : '');
  }

  function setRunHash() {
    const target = ui.heroRunId
      ? '#hero_run=' + encodeURIComponent(ui.heroRunId)
      : ui.runId
        ? '#run=' + encodeURIComponent(ui.runId)
        : location.pathname;
    history.replaceState(null, '', target);
  }

  async function request(path, options = {}) {
    const method = options.method || 'GET';
    const headers = { Accept: 'application/json' };
    if (options.token) headers.Authorization = 'Bearer ' + options.token;
    if (options.body !== undefined) {
      headers['Content-Type'] = 'application/json';
      headers['X-AIOA-Intent'] = 'judge-console-v1';
    }
    const response = await fetch(path, {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: 'no-store',
      credentials: 'same-origin',
    });
    let payload;
    try { payload = await response.json(); }
    catch (_) { payload = { error: 'INVALID_SERVER_RESPONSE' }; }
    if (!response.ok) throw new ApiError(response.status, payload);
    return Object.prototype.hasOwnProperty.call(payload, 'result') ? payload.result : payload;
  }

  function renderSession() {
    const dot = byId('session-dot');
    dot.classList.toggle('connected', ui.connected);
    setText('session-state', ui.connected ? 'Protected local session connected' : 'Local session required');
    document.querySelectorAll('[data-scenario]').forEach((button) => {
      button.disabled = !ui.connected || ui.busy;
    });
    document.querySelectorAll('[data-workspace-hero]').forEach((button) => {
      button.disabled = !ui.connected || ui.busy;
    });
  }

  function renderRuntime(runtime) {
    if (!runtime) return;
    setText('mode-runtime', runtime.runtime_mode);
    setText('mode-provider', runtime.provider);
    setText('network-count', runtime.process_external_network_calls);
    setText('process-mutations', runtime.process_sandbox_mutations);
    setText('provider-calls', runtime.process_provider_calls);
    setText('model-id', runtime.model_id, runtime.model_id);
  }

  function resourceSummary(resource) {
    if (!resource) return 'Absent (expected for a released address)';
    const summary = {
      type: resource.resource_type,
      id: resource.resource_id,
      region: resource.region,
    };
    if (Object.prototype.hasOwnProperty.call(resource, 'association_id')) summary.association_id = resource.association_id;
    if (Array.isArray(resource.inbound_rules)) summary.inbound_rules = resource.inbound_rules.length;
    if (resource.state) summary.state = resource.state;
    return JSON.stringify(summary, null, 2);
  }

  function renderAudit(events) {
    const list = byId('timeline');
    list.replaceChildren();
    if (!Array.isArray(events) || events.length === 0) {
      const empty = document.createElement('li');
      empty.className = 'empty';
      empty.textContent = 'The immutable timeline appears after a scenario starts.';
      list.append(empty);
      return;
    }
    events.forEach((event) => {
      const item = document.createElement('li');
      const category = document.createElement('span');
      const title = document.createElement('strong');
      const time = document.createElement('time');
      const digest = document.createElement('code');
      category.className = 'category';
      category.textContent = event.category || 'FACT';
      title.textContent = event.summary || labels[event.type] || event.type;
      time.textContent = new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      time.dateTime = event.timestamp;
      digest.textContent = shortHash(event.redacted_payload_hash);
      digest.title = event.redacted_payload_hash;
      item.append(category, title, time, digest);
      list.append(item);
    });
  }

  function replaceTextList(id, values) {
    const list = byId(id);
    list.replaceChildren();
    (Array.isArray(values) ? values : []).forEach((value) => {
      const item = document.createElement('li');
      item.textContent = String(value);
      list.append(item);
    });
  }

  function setHeroProof(id, value) {
    setText(id, value);
    const normalized = String(value || 'PENDING');
    byId(id).classList.toggle('pass', !['PENDING', 'FAIL'].includes(normalized));
  }

  function renderHeroTimeline(items) {
    const list = byId('hero-timeline');
    list.replaceChildren();
    (Array.isArray(items) ? items : []).forEach((event) => {
      const item = document.createElement('li');
      const category = document.createElement('span');
      const title = document.createElement('strong');
      const summary = document.createElement('span');
      const source = document.createElement('span');
      const digest = document.createElement('code');
      item.classList.toggle('pending', event.status === 'PENDING');
      item.classList.toggle('safe-stop', event.status === 'SAFE_STOP');
      category.className = 'category';
      category.textContent = event.category || 'FACT';
      title.textContent = event.title || event.stage;
      summary.className = 'timeline-summary';
      summary.textContent = event.summary || '—';
      source.className = 'timeline-source';
      source.textContent = (event.status || 'PENDING') + ' · ' + (event.authority_source || 'durable truth');
      digest.textContent = shortHash(event.evidence_fingerprint);
      digest.title = event.evidence_fingerprint || '';
      item.append(category, title, summary, source, digest);
      list.append(item);
    });
  }

  function markHeroPipeline(items) {
    const statusByStage = new Map((Array.isArray(items) ? items : []).map((item) => [item.stage, item.status]));
    document.querySelectorAll('[data-hero-stage]').forEach((stage) => {
      const status = statusByStage.get(stage.dataset.heroStage) || 'PENDING';
      stage.classList.toggle('done', status === 'COMPLETE');
      stage.classList.toggle('current', status === 'CURRENT');
      stage.classList.toggle('safe-stop', status === 'SAFE_STOP');
    });
  }

  function renderHero(view) {
    ui.heroView = view;
    const card = view.approval_card || {};
    const after = view.after || {};
    const verification = view.verification || null;
    const replay = view.replay || null;
    const state = view.state;
    const denied = state === 'DENIED_BY_HUMAN';
    const succeeded = state === 'SUCCESS_WITH_EVIDENCE'
      && view.success_with_evidence === true
      && view.verification_receipt_present === true
      && verification !== null;

    byId('workspace-hero').hidden = false;
    setText('hero-state', state);
    byId('hero-state').className = 'state-badge' + (succeeded ? ' success' : denied ? ' denied' : '');
    setText('hero-run-id', shortHash(view.run_id), view.run_id);
    replaceTextList('hero-incident-facts', view.incident_facts);
    setText('hero-root-cause', view.root_cause);
    setText('hero-alternative', view.alternative_hypothesis);
    setText('hero-card-scenario', card.scenario);
    setText('hero-card-target', card.target);
    setText('hero-card-field', card.field_path);
    setText('hero-card-change', card.proposed_change);
    setText('hero-workspace-hash', shortHash(card.workspace_fingerprint), card.workspace_fingerprint);
    setText('hero-proposal-hash', shortHash(card.proposal_fingerprint), card.proposal_fingerprint);
    setText('hero-patch-hash', shortHash(card.patch_fingerprint), card.patch_fingerprint);
    setText('hero-request-hash', card.request_fingerprint ? shortHash(card.request_fingerprint) : 'Not issued', card.request_fingerprint || '');
    setText('hero-risk', card.risk);
    setText('hero-rollback', card.rollback);
    setText('hero-evidence', Array.isArray(card.evidence) ? card.evidence.join(' · ') : '—');
    setText('hero-expected', Array.isArray(card.expected_verification) ? card.expected_verification.join(' · ') : '—');
    setText('hero-warning', card.warning);
    byId('hero-diff').textContent = view.patch_diff || 'No patch selected.';
    setText('hero-before-contract', view.before?.deployment_start_contract);
    setText('hero-before-error', view.before?.error);
    setHeroProof('hero-after-scope', after.patch_scope);
    setHeroProof('hero-after-hash', after.target_hash);
    setHeroProof('hero-after-startup', after.startup_executable);
    setHeroProof('hero-after-token', after.token_mode);
    setHeroProof('hero-after-env', after.bootstrap_secret_in_child_env);
    setHeroProof('hero-after-health', after.health);
    setHeroProof('hero-after-ready', after.ready);
    setHeroProof('hero-after-network', String(after.external_egress) + ' / ' + String(after.aws_calls));
    setText('hero-proof-status', succeeded ? 'VERIFIED' : denied ? 'SAFE STOP' : 'PENDING');
    byId('hero-proof-status').className = 'state-badge' + (succeeded ? ' success' : denied ? ' denied' : '');
    setText('hero-mutation-count', view.workspace_mutation_count);
    setText('hero-human-decision', view.human_decision);
    setText('hero-receipt-present', view.verification_receipt_present ? 'YES' : 'NO');
    setText('hero-profile', verification?.profile_id || 'Not run');
    setText('hero-checks', verification ? verification.checks_passed + ' / ' + verification.checks_total : '0 / 0');
    setText('hero-proof-origin', verification?.proof_origin);
    setText('hero-report-hash', verification ? shortHash(verification.report_fingerprint) : '—', verification?.report_fingerprint || '');
    setText('hero-verification-hash', verification ? shortHash(verification.receipt_fingerprint) : '—', verification?.receipt_fingerprint || '');
    setText('hero-recovery-badge', view.recovery_badge);
    setText('hero-replay-state', replay?.status || 'Not available');
    renderHeroTimeline(view.timeline);
    markHeroPipeline(view.timeline);

    const hasRequest = typeof card.request_fingerprint === 'string';
    byId('hero-review').disabled = ui.busy || !ui.connected || state !== 'PATCH_PROPOSED';
    byId('hero-approve').disabled = ui.busy || !ui.connected || state !== 'AWAITING_APPROVAL' || !hasRequest;
    byId('hero-deny').disabled = ui.busy || !ui.connected || state !== 'AWAITING_APPROVAL' || !hasRequest;
    byId('hero-execute').disabled = ui.busy || !ui.connected || state !== 'APPROVED';
    byId('hero-verify').disabled = ui.busy || !ui.connected || !['PATCH_APPLIED_UNVERIFIED', 'RECONCILIATION_REQUIRED', 'VERIFICATION_FAILED', 'DEPENDENCY_UNAVAILABLE'].includes(state);
    byId('hero-replay').disabled = ui.busy || !ui.connected || !succeeded || replay?.status !== 'AVAILABLE';

    const decisionCopy = denied
      ? 'DENIED_BY_HUMAN is a successful safety stop. No patch effect or verification receipt exists.'
      : succeeded
        ? 'Independent disk read-back and the fixed startup profile created the only success-authorizing receipt.'
        : state === 'PATCH_APPLIED_UNVERIFIED'
          ? 'The exact patch was applied once, but this is not success. Independent verification is still required.'
          : state === 'APPROVED'
            ? 'Approval is durable, but it is not success and it has not executed anything. A separate gesture is required.'
            : state === 'AWAITING_APPROVAL'
              ? 'Review the exact workspace, base-state, proposal, patch and request fingerprints before deciding.'
              : 'The proposal is inert. Open one exact durable approval request.';
    setText('hero-decision-copy', decisionCopy);

    const outcome = byId('hero-outcome');
    outcome.className = 'outcome' + (succeeded ? ' success' : denied ? ' denied' : '');
    if (succeeded) {
      outcome.textContent = replay?.status === 'REPLAY_REJECTED_RECONCILED'
        ? 'REPLAY_REJECTED_RECONCILED: the consumed approval produced zero additional mutations and zero profile executions.'
        : 'SUCCESS_WITH_EVIDENCE: one exact mutation is backed by a persisted independent verification receipt.';
    } else if (denied) {
      outcome.textContent = 'DENIED_BY_HUMAN: workspace mutation count is zero; execution and verification were safely skipped.';
    } else {
      outcome.textContent = decisionCopy;
    }
    byId('hero-raw-output').textContent = JSON.stringify(view, null, 2);
  }

  function markPipeline(view) {
    const checkpoint = view.checkpoint || {};
    const evidence = checkpoint.resource_evidence;
    const proposal = checkpoint.remediation_proposal;
    const approval = checkpoint.approval;
    const receipt = checkpoint.execution_receipt;
    const verification = checkpoint.verification;
    const denied = view.run.state === 'DENIED_BY_HUMAN';
    const flags = {
      observe: Boolean(evidence),
      evidence: Boolean(evidence),
      proposal: Boolean(proposal),
      policy: Boolean(proposal),
      approval: Boolean(approval),
      execution: Boolean(receipt) || denied,
      verification: Boolean(verification) || denied,
      receipt: Boolean(verification) || denied,
    };
    let foundCurrent = false;
    document.querySelectorAll('[data-stage]').forEach((stage) => {
      const complete = flags[stage.dataset.stage];
      stage.classList.toggle('done', complete);
      stage.classList.toggle('safe-stop', denied && complete && ['execution', 'verification', 'receipt'].includes(stage.dataset.stage));
      const current = !complete && !foundCurrent;
      stage.classList.toggle('current', current);
      if (current) foundCurrent = true;
    });
  }

  function renderView(view) {
    ui.view = view;
    const checkpoint = view.checkpoint || {};
    const evidence = checkpoint.resource_evidence || {};
    const proposal = checkpoint.remediation_proposal || {};
    const requestView = checkpoint.approval_request || {};
    const approval = checkpoint.approval || {};
    const receipt = checkpoint.execution_receipt || null;
    const verification = checkpoint.verification || null;
    const state = view.run.state;
    const denied = state === 'DENIED_BY_HUMAN';
    const succeeded = state === 'SUCCESS_WITH_EVIDENCE';

    byId('workspace').hidden = false;
    setText('run-state', state);
    byId('run-state').className = 'state-badge' + (succeeded ? ' success' : denied ? ' denied' : '');
    setText('run-id', shortHash(view.run.run_id), view.run.run_id);
    setText('trace-id', shortHash(view.run.trace_id), view.run.trace_id);
    setText('snapshot-hash', shortHash(view.evidence_snapshot_sha256), view.evidence_snapshot_sha256);
    setText('target', proposal.target_resource_id || evidence.resource?.resource_id);
    setText('resource-type', proposal.target_resource_type || evidence.resource?.resource_type);
    setText('finding', Array.isArray(evidence.findings) ? evidence.findings.join(', ') : '—');
    setText('observed-at', evidence.observed_at ? new Date(evidence.observed_at).toLocaleString() : '—', evidence.observed_at);
    setText('evidence-hash', shortHash(evidence.evidence_hash), evidence.evidence_hash);
    setText('operation', proposal.operation_type || 'No executable proposal');
    setText('impact', proposal.risk_summary || 'The policy engine found no bounded mutation to propose.');
    setText('authority', proposal.authority_class || 'NOT_REQUIRED');
    setText('proposal-hash', shortHash(proposal.proposal_hash), proposal.proposal_hash);
    setText('fingerprint', shortHash(proposal.evidence_fingerprint), proposal.evidence_fingerprint);
    setText('request-hash', shortHash(requestView.request_hash), requestView.request_hash);
    setText('decision-hash', shortHash(approval.decision_hash), approval.decision_hash);
    setText('receipt-hash', shortHash(receipt?.receipt_hash), receipt?.receipt_hash);
    setText('verification-hash', shortHash(verification?.verification_hash), verification?.verification_hash);
    setText('run-mutations', view.run_sandbox_mutations);
    renderRuntime(view.runtime);
    renderAudit(view.audit_events);
    markPipeline(view);

    const decisionCopy = succeeded
      ? 'The approved action executed once. Independent read-back closed the run with evidence.'
      : !proposal.proposal_id
      ? 'No human decision is needed for this evidence.'
      : !requestView.request_id
        ? 'The proposal is inert. Open its exact evidence-bound decision request.'
        : !approval.decision
          ? (ui.challenge ? 'Review the target, operation and hashes. Your decision is the authority boundary.' : 'The page was refreshed or another tab changed the challenge. Reload the exact request before deciding.')
          : approval.decision === 'APPROVED'
            ? 'APPROVED is durable, but execution is still a separate explicit gesture.'
            : 'DENIED_BY_HUMAN is a successful safety outcome. No action receipt exists.';
    setText('decision-copy', decisionCopy);

    byId('review').disabled = ui.busy || !ui.connected || !proposal.proposal_id || Boolean(approval.decision) || state !== 'AWAITING_APPROVAL';
    byId('approve').disabled = ui.busy || !ui.connected || !ui.challenge || Boolean(approval.decision);
    byId('deny').disabled = ui.busy || !ui.connected || !ui.challenge || Boolean(approval.decision);
    byId('execute').disabled = ui.busy || !ui.connected || !['APPROVED', 'SUCCESS_WITH_EVIDENCE'].includes(state);
    setText('execute-label', succeeded ? 'Test replay protection' : 'Execute approved action');

    const outcome = byId('outcome');
    outcome.className = 'outcome' + (succeeded ? ' success' : denied ? ' denied' : '');
    if (succeeded) {
      outcome.textContent = ui.replayProven
        ? 'Replay-safe: the completed receipt was reconciled and no second sandbox mutation occurred.'
        : 'SUCCESS_WITH_EVIDENCE: one bounded sandbox mutation was independently verified. You can now test replay protection.';
    } else if (denied) {
      outcome.textContent = 'DENIED_BY_HUMAN: the resource stayed unchanged and no execution or verification receipt was created.';
    } else {
      outcome.textContent = 'No model output can mutate this sandbox. Policy, exact human authority and a separate execution gesture are required.';
    }
    setText('before-state', resourceSummary(receipt?.before_resource));
    setText('after-state', receipt ? resourceSummary(receipt.after_resource) : 'No mutation receipt');
    byId('raw-output').textContent = JSON.stringify(view, null, 2);
  }

  async function refresh(silent = false) {
    if (!ui.runId) return;
    try {
      const view = await request('/api/runs/' + encodeURIComponent(ui.runId));
      ui.connected = true;
      renderSession();
      renderView(view);
      if (!silent) announce('Durable state refreshed.');
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        ui.connected = false;
        renderSession();
        announce('Reconnect the protected local session to resume this run.', true);
        return;
      }
      throw error;
    }
  }

  async function refreshHero(silent = false) {
    if (!ui.heroRunId) return;
    try {
      const view = await request('/api/workspace-demo/runs/' + encodeURIComponent(ui.heroRunId));
      ui.connected = true;
      renderSession();
      renderHero(view);
      if (!silent) announce('Authoritative hero state restored from durable receipts.');
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        ui.connected = false;
        renderSession();
        announce('Reconnect the protected local session to resume this hero run.', true);
        return;
      }
      throw error;
    }
  }

  async function refreshActive(silent = false) {
    if (ui.heroRunId) return refreshHero(silent);
    return refresh(silent);
  }

  async function guarded(action) {
    if (ui.busy) return;
    ui.busy = true;
    renderSession();
    if (ui.view) renderView(ui.view);
    if (ui.heroView) renderHero(ui.heroView);
    try { await action(); }
    catch (error) {
      const stale = error instanceof ApiError && [403, 409].includes(error.status);
      if (stale && (ui.runId || ui.heroRunId)) {
        ui.challenge = null;
        await refreshActive(true).catch(() => {});
        announce('A stale or conflicting action was rejected. Durable truth has been reloaded.', true);
      } else {
        announce(error instanceof ApiError ? error.message : 'Local request failed safely.', true);
      }
    } finally {
      ui.busy = false;
      renderSession();
      if (ui.view) renderView(ui.view);
      if (ui.heroView) renderHero(ui.heroView);
    }
  }

  async function connect(token) {
    await request('/api/session', { method: 'POST', body: {}, token });
    ui.connected = true;
    renderSession();
  }

  async function startWorkspaceHero() {
    await guarded(async () => {
      const result = await request('/api/workspace-demo/runs', {
        method: 'POST',
        body: { scenario_id: 'FAILED_RENDER_DEPLOYMENT_VERIFIED_FIX_V1' },
      });
      ui.heroRunId = result.run_id;
      ui.heroView = result;
      ui.runId = '';
      ui.view = null;
      ui.challenge = null;
      byId('workspace').hidden = true;
      setRunHash();
      renderHero(result);
      byId('workspace-hero').scrollIntoView({ behavior: 'smooth', block: 'start' });
      announce('Sealed evidence inspected. One exact non-applying patch is ready for review.');
    });
  }

  async function reviewWorkspaceHero() {
    await guarded(async () => {
      ui.heroView = await request('/api/workspace-demo/runs/' + encodeURIComponent(ui.heroRunId) + '/approval-request', { method: 'POST', body: {} });
      renderHero(ui.heroView);
      announce('Exact durable request loaded. Approval remains bound to every displayed fingerprint.');
    });
  }

  async function decideWorkspaceHero(decision) {
    await guarded(async () => {
      const requestFingerprint = ui.heroView?.approval_card?.request_fingerprint;
      if (!requestFingerprint) throw new Error('Reload the exact approval request first.');
      ui.heroView = await request('/api/workspace-demo/runs/' + encodeURIComponent(ui.heroRunId) + '/decision', {
        method: 'POST',
        body: { decision, request_fingerprint: requestFingerprint },
      });
      renderHero(ui.heroView);
      announce(decision === 'APPROVED'
        ? 'Exact approval recorded. Nothing has executed; use the separate effect control.'
        : 'Human denial recorded. The durable mutation count remains zero.');
    });
  }

  async function executeWorkspaceHero() {
    await guarded(async () => {
      ui.heroView = await request('/api/workspace-demo/runs/' + encodeURIComponent(ui.heroRunId) + '/resume', {
        method: 'POST',
        body: { confirm_execution: true },
      });
      renderHero(ui.heroView);
      announce('Exact patch applied once. State is PATCH_APPLIED_UNVERIFIED, not success.');
    });
  }

  async function verifyWorkspaceHero() {
    await guarded(async () => {
      ui.heroView = await request('/api/workspace-demo/runs/' + encodeURIComponent(ui.heroRunId) + '/verify-or-reconcile', { method: 'POST', body: {} });
      renderHero(ui.heroView);
      announce(ui.heroView.success_with_evidence === true
        ? 'Independent verification persisted. SUCCESS_WITH_EVIDENCE is now proven.'
        : 'Verification stopped safely without claiming success.', ui.heroView.success_with_evidence !== true);
    });
  }

  async function replayWorkspaceHero() {
    await guarded(async () => {
      const before = ui.heroView?.workspace_mutation_count;
      ui.heroView = await request('/api/workspace-demo/runs/' + encodeURIComponent(ui.heroRunId) + '/resume', {
        method: 'POST',
        body: { confirm_execution: true },
      });
      renderHero(ui.heroView);
      const zeroDelta = ui.heroView.workspace_mutation_count === before
        && ui.heroView.replay?.additional_mutation_delta === 0
        && ui.heroView.replay?.additional_profile_executions === 0;
      announce(zeroDelta
        ? 'Replay rejected and reconciled: zero new mutations, zero profile reruns.'
        : 'Replay proof did not satisfy its fail-closed invariants.', !zeroDelta);
    });
  }

  async function startScenario(button) {
    await guarded(async () => {
      const result = await request('/api/runs', {
        method: 'POST',
        body: {
          resource_type: button.dataset.resourceType,
          resource_id: button.dataset.resourceId,
        },
      });
      ui.runId = result.run_id;
      ui.heroRunId = '';
      ui.heroView = null;
      ui.challenge = null;
      ui.replayProven = false;
      byId('workspace-hero').hidden = true;
      setRunHash();
      await refresh(true);
      byId('workspace').scrollIntoView({ behavior: 'smooth', block: 'start' });
      announce('Evidence captured. The proposal is paused at human authority.');
    });
  }

  async function reviewProposal() {
    await guarded(async () => {
      ui.challenge = await request('/api/runs/' + encodeURIComponent(ui.runId) + '/approval-request', { method: 'POST', body: {} });
      await refresh(true);
      announce('Exact request loaded. Approve or deny only the displayed bound action.');
    });
  }

  async function decide(decision) {
    await guarded(async () => {
      if (!ui.challenge) throw new Error('Reload the exact approval request first.');
      const approvalRequest = ui.challenge.request;
      await request('/api/runs/' + encodeURIComponent(ui.runId) + '/decision', {
        method: 'POST',
        body: {
          request_id: approvalRequest.request_id,
          run_id: approvalRequest.run_id,
          proposal_id: approvalRequest.proposal_id,
          request_hash: approvalRequest.request_hash,
          proposal_hash: approvalRequest.proposal_hash,
          evidence_hash: approvalRequest.evidence_hash,
          proposal_version: approvalRequest.proposal_version,
          decision,
          decision_nonce: ui.challenge.decision_nonce,
        },
      });
      ui.challenge = null;
      await refresh(true);
      announce(decision === 'APPROVED' ? 'Approval recorded. No execution has happened yet.' : 'Human denial recorded. Zero mutation for this run.');
    });
  }

  async function executeOrReplay() {
    await guarded(async () => {
      const before = ui.view?.run_sandbox_mutations || 0;
      const result = await request('/api/runs/' + encodeURIComponent(ui.runId) + '/resume', { method: 'POST', body: { confirm_execution: true } });
      await refresh(true);
      if (result.reconciled === true && ui.view.run_sandbox_mutations === before) ui.replayProven = true;
      announce(result.reconciled === true ? 'Existing receipt reconciled. No duplicate mutation.' : 'Approved sandbox action executed and independently verified.');
    });
  }

  async function boot() {
    const fragment = new URLSearchParams(location.hash.slice(1));
    const bootstrapToken = fragment.get('access_token') || '';
    ui.heroRunId = fragment.get('hero_run') || '';
    ui.runId = ui.heroRunId ? '' : (fragment.get('run') || '');
    setRunHash();
    try {
      const ready = await request('/ready');
      renderRuntime(ready.runtime);
      if (bootstrapToken) await connect(bootstrapToken);
      else {
        await request('/api/session');
        ui.connected = true;
      }
      renderSession();
      if (ui.heroRunId || ui.runId) await refreshActive(true);
    } catch (_) {
      ui.connected = false;
      renderSession();
      if (ui.heroRunId || ui.runId) announce('Run identity restored. Connect the local session to resume.', true);
    }
  }

  byId('workspace-hero-start').addEventListener('click', startWorkspaceHero);
  byId('hero-review').addEventListener('click', reviewWorkspaceHero);
  byId('hero-approve').addEventListener('click', () => decideWorkspaceHero('APPROVED'));
  byId('hero-deny').addEventListener('click', () => decideWorkspaceHero('DENIED'));
  byId('hero-execute').addEventListener('click', executeWorkspaceHero);
  byId('hero-verify').addEventListener('click', verifyWorkspaceHero);
  byId('hero-replay').addEventListener('click', replayWorkspaceHero);
  document.querySelectorAll('[data-scenario]').forEach((button) => button.addEventListener('click', () => startScenario(button)));
  byId('review').addEventListener('click', reviewProposal);
  byId('approve').addEventListener('click', () => decide('APPROVED'));
  byId('deny').addEventListener('click', () => decide('DENIED'));
  byId('execute').addEventListener('click', executeOrReplay);
  byId('refresh').addEventListener('click', () => guarded(() => refreshActive(true)));
  byId('connect-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const input = byId('token');
    const token = input.value;
    input.value = '';
    guarded(async () => {
      await connect(token);
      if (ui.heroRunId || ui.runId) await refreshActive(true);
      announce('Protected browser session established.');
    });
  });
  byId('disconnect').addEventListener('click', () => guarded(async () => {
    await request('/api/session', { method: 'DELETE' });
    ui.connected = false;
    ui.challenge = null;
    renderSession();
    announce('Browser session cleared. Durable run evidence was preserved.');
  }));
  renderSession();
  boot();
})();
""".strip()

_STYLE_HASH = base64.b64encode(
    hashlib.sha256(JUDGE_UI_STYLE.encode("utf-8")).digest()
).decode("ascii")
_SCRIPT_HASH = base64.b64encode(
    hashlib.sha256(JUDGE_UI_SCRIPT.encode("utf-8")).digest()
).decode("ascii")


def judge_ui_headers(base_headers: Mapping[str, str]) -> dict[str, str]:
    """Bind the exact inline assets into a strict no-network CSP."""

    return {
        **base_headers,
        "content-security-policy": (
            "default-src 'none';base-uri 'none';connect-src 'self';frame-ancestors 'none';"
            "form-action 'self';"
            f"style-src 'sha256-{_STYLE_HASH}';script-src 'sha256-{_SCRIPT_HASH}'"
        ),
        "content-type": "text/html; charset=utf-8",
    }


JUDGE_UI_BODY: Final = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>AIOA — Agents for Humans</title>
  <style>{JUDGE_UI_STYLE}</style>
</head>
<body>
  <a class="skip-link" href="#scenarios">Skip to demo</a>
  <header class="topbar">
    <div class="shell topbar-inner">
      <div class="brand"><span class="brand-mark" aria-hidden="true">A</span><span>AIOA <span class="brand-sub">/ Agents for Humans</span></span></div>
      <div class="mode-cluster" aria-label="Runtime truth">
        <span class="pill safe">Demo sandbox</span>
        <span class="pill safe">Portable / <span id="mode-provider">mock</span></span>
        <span class="pill">Strands</span>
      </div>
    </div>
  </header>

  <main id="main" class="shell">
    <section class="hero" aria-labelledby="hero-title">
      <div class="kicker">Non-Zero control plane · human authority preserved</div>
      <h1 id="hero-title">The model proposes.<br>The human authorizes.<br>Evidence decides.</h1>
      <p class="hero-copy">AIOA turns a failed deployment into one exact human-approved fix, executes it once, and independently proves the service can start. Evidence first: model output never becomes authority.</p>
      <div class="truth-grid" aria-label="Safety facts">
        <div class="truth"><strong>0 real cloud writes</strong><span>Bounded local state only</span></div>
        <div class="truth"><strong><span id="network-count">0</span> network calls</strong><span>No hidden service dependency</span></div>
        <div class="truth"><strong>Exact hash binding</strong><span>Approval cannot drift to another action</span></div>
      </div>
    </section>

    <section id="scenarios" class="section" aria-labelledby="scenario-title">
      <div class="section-heading">
        <div><div class="section-number">01 / CHOOSE A STORY</div><h2 id="scenario-title">Start with one safe click</h2></div>
        <p class="section-note">Both scenarios use deterministic AWS-shaped fixtures. Nothing here is live AWS.</p>
      </div>
      <div class="session-strip">
        <div class="session-copy"><span id="session-dot" class="session-dot" aria-hidden="true"></span><span id="session-state">Local session required</span></div>
        <button id="refresh" class="quiet-button" type="button">Refresh durable state</button>
      </div>
      <button id="workspace-hero-start" class="scenario hero-scenario" type="button" data-workspace-hero disabled>
        <span class="scenario-tag">Featured judge journey · fixed scenario</span>
        <h3>Fix a Failed Deployment Safely</h3>
        <p>Trace one failed Render start from observed evidence to an exact patch, human authority, one atomic effect, independent verification and replay-safe receipts.</p>
        <span class="mode-cluster" aria-label="Scenario guarantees">
          <span class="pill safe">Demo sandbox</span>
          <span class="pill safe">Portable / mock</span>
          <span class="pill">Strands</span>
          <span class="pill">Human authority required</span>
          <span class="pill">No live AWS writes</span>
          <span class="pill">No external egress</span>
        </span>
      </button>
      <div class="secondary-story-label">Secondary CloudOps regression stories</div>
      <div class="scenario-grid">
        <button class="scenario" type="button" data-scenario data-resource-type="AWS::EC2::EIP" data-resource-id="eipalloc-0123456789abcdef0">
          <span class="scenario-tag">Primary · approval path</span>
          <h3>Release an unattached Elastic IP</h3>
          <p>Observe waste, inspect bound evidence, approve one exact remediation, then verify one sandbox mutation.</p>
        </button>
        <button class="scenario deny" type="button" data-scenario data-resource-type="AWS::EC2::SecurityGroup" data-resource-id="sg-0123456789abcdef0">
          <span class="scenario-tag">Safety proof · denial path</span>
          <h3>Deny a public-ingress change</h3>
          <p>Reach the same human boundary, deny the proposal, and prove the resource stayed unchanged.</p>
        </button>
      </div>
    </section>

    <section id="workspace-hero" class="section" aria-labelledby="workspace-hero-title" hidden>
      <div class="section-heading">
        <div><div class="section-number">02 / FIX + PROVE</div><h2 id="workspace-hero-title">Failed deployment → verified fix</h2></div>
        <span id="hero-state" class="state-badge">PATCH_PROPOSED</span>
      </div>
      <ol class="pipeline hero-pipeline" aria-label="Fixed workspace remediation stages">
        <li data-hero-stage="OBSERVE"><span>01</span>Observe</li>
        <li data-hero-stage="EVIDENCE"><span>02</span>Evidence</li>
        <li data-hero-stage="ROOT_CAUSE"><span>03</span>Root cause</li>
        <li data-hero-stage="PATCH_PROPOSAL"><span>04</span>Exact patch</li>
        <li data-hero-stage="POLICY"><span>05</span>Policy</li>
        <li data-hero-stage="HUMAN_DECISION"><span>06</span>Human</li>
        <li data-hero-stage="PATCH_EFFECT"><span>07</span>Apply once</li>
        <li data-hero-stage="VERIFICATION"><span>08</span>Verify</li>
        <li data-hero-stage="RECEIPT"><span>09</span>Receipt</li>
        <li data-hero-stage="RECOVERY_REPLAY"><span>10</span>Replay</li>
      </ol>

      <div class="hero-workspace-grid">
        <div class="stack">
          <article class="panel panel-pad">
            <div class="panel-head"><h3>Observed incident + bounded inference</h3><span class="state-badge">W1 · READ ONLY</span></div>
            <ul id="hero-incident-facts" class="proof-list"><li>Loading sealed evidence…</li></ul>
            <dl class="facts">
              <div class="fact wide"><dt>Root cause</dt><dd id="hero-root-cause">—</dd></div>
              <div class="fact wide"><dt>Alternative considered</dt><dd id="hero-alternative">—</dd></div>
            </dl>
          </article>

          <article class="panel panel-pad">
            <div class="panel-head"><h3>Exact non-applying patch proposal</h3><span class="state-badge">W2 · INERT</span></div>
            <pre id="hero-diff" class="diff-panel" aria-label="Exact unified patch diff">No patch selected.</pre>
          </article>

          <article class="panel panel-pad">
            <div class="panel-head"><h3>Before → independently verified after</h3><span id="hero-proof-status" class="state-badge">PENDING</span></div>
            <div class="stage-truth">
              <article><h4>Before</h4><p><strong id="hero-before-contract">FAIL</strong><br><span id="hero-before-error">File name too long / exit 127</span></p></article>
              <article><h4>After</h4><ul class="proof-list">
                <li><span>Exact patch scope</span><strong id="hero-after-scope">PENDING</strong></li>
                <li><span>Target hash</span><strong id="hero-after-hash">PENDING</strong></li>
                <li><span>Startup executable</span><strong id="hero-after-startup">PENDING</strong></li>
                <li><span>Token file mode</span><strong id="hero-after-token">PENDING</strong></li>
                <li><span>Bootstrap secret in child env</span><strong id="hero-after-env">PENDING</strong></li>
                <li><span>/health</span><strong id="hero-after-health">PENDING</strong></li>
                <li><span>/ready</span><strong id="hero-after-ready">PENDING</strong></li>
                <li><span>External egress / AWS calls</span><strong id="hero-after-network">0 / 0</strong></li>
              </ul></article>
            </div>
          </article>
        </div>

        <aside class="stack">
          <section class="panel panel-pad" aria-labelledby="hero-authority-title">
            <div class="panel-head"><h3 id="hero-authority-title">Exact human approval card</h3><span class="state-badge">W3</span></div>
            <dl class="facts">
              <div class="fact wide"><dt>Scenario</dt><dd id="hero-card-scenario">—</dd></div>
              <div class="fact"><dt>Target</dt><dd id="hero-card-target">—</dd></div>
              <div class="fact"><dt>Field</dt><dd id="hero-card-field">—</dd></div>
              <div class="fact wide"><dt>Proposed change</dt><dd id="hero-card-change">—</dd></div>
              <div class="fact"><dt>Workspace fingerprint</dt><dd id="hero-workspace-hash" class="hash">—</dd></div>
              <div class="fact"><dt>Proposal fingerprint</dt><dd id="hero-proposal-hash" class="hash">—</dd></div>
              <div class="fact"><dt>Patch fingerprint</dt><dd id="hero-patch-hash" class="hash">—</dd></div>
              <div class="fact"><dt>Request fingerprint</dt><dd id="hero-request-hash" class="hash">Not issued</dd></div>
              <div class="fact"><dt>Risk</dt><dd id="hero-risk">—</dd></div>
              <div class="fact wide"><dt>Rollback</dt><dd id="hero-rollback">—</dd></div>
            </dl>
            <div class="authority-callout"><strong>Bound evidence</strong><span id="hero-evidence">—</span></div>
            <div class="authority-callout"><strong>Expected verification</strong><span id="hero-expected">—</span></div>
            <div id="hero-warning" class="approval-warning">This approval is valid only for this exact proposal, workspace, base state and patch.</div>
            <p id="hero-decision-copy" class="decision-state">Review the durable request before deciding.</p>
            <div class="controls">
              <button id="hero-review" class="button secondary" type="button" disabled>Review exact request</button>
              <div class="button-row"><button id="hero-approve" class="button" type="button" disabled>Approve exact change</button><button id="hero-deny" class="button deny" type="button" disabled>Deny</button></div>
              <button id="hero-execute" class="button secondary" type="button" disabled>Execute approved patch once</button>
              <button id="hero-verify" class="button secondary" type="button" disabled>Independently verify</button>
              <button id="hero-replay" class="button secondary" type="button" disabled>Prove replay rejection</button>
            </div>
            <div class="proof"><div><strong id="hero-mutation-count">0</strong><span>workspace mutations</span></div><div><strong id="hero-human-decision">PENDING</strong><span>human decision</span></div><div><strong id="hero-receipt-present">NO</strong><span>verification receipt</span></div><div><strong>0</strong><span>live AWS writes</span></div></div>
            <div id="hero-outcome" class="outcome">The proposal is inert. Human approval is not success, and applying the patch is not success.</div>
          </section>

          <section class="panel panel-pad" aria-labelledby="hero-receipt-title">
            <div class="panel-head"><h3 id="hero-receipt-title">Independent verification receipt</h3><span class="state-badge">W4</span></div>
            <dl class="facts">
              <div class="fact wide"><dt>Profile</dt><dd id="hero-profile">Not run</dd></div>
              <div class="fact"><dt>Checks</dt><dd id="hero-checks">0 / 0</dd></div>
              <div class="fact"><dt>Origin</dt><dd id="hero-proof-origin">—</dd></div>
              <div class="fact"><dt>Report fingerprint</dt><dd id="hero-report-hash" class="hash">—</dd></div>
              <div class="fact"><dt>Receipt fingerprint</dt><dd id="hero-verification-hash" class="hash">—</dd></div>
            </dl>
            <div id="hero-recovery-badge" class="state-badge recovery-badge">W4 RECOVERY / RECONCILIATION CERTIFIED</div>
          </section>

          <section class="panel panel-pad" aria-labelledby="hero-timeline-title">
            <div class="panel-head"><h3 id="hero-timeline-title">Evidence and authority timeline</h3></div>
            <ol id="hero-timeline" class="timeline"><li class="empty">The durable timeline appears after the fixed scenario starts.</li></ol>
          </section>

          <section class="panel panel-pad">
            <div class="panel-head"><h3>Hero run identity</h3></div>
            <dl class="facts"><div class="fact wide"><dt>Run ID</dt><dd id="hero-run-id" class="hash">—</dd></div><div class="fact wide"><dt>Replay</dt><dd id="hero-replay-state">Not available</dd></div></dl>
          </section>
        </aside>
      </div>

      <div class="panel technical-wrap">
        <details class="technical"><summary>Inspect sanitized hero projection</summary><pre id="hero-raw-output">No hero run selected.</pre></details>
      </div>
    </section>

    <section id="workspace" class="section" aria-labelledby="workspace-title" hidden>
      <div class="section-heading">
        <div><div class="section-number">03 / CLOUDOPS REGRESSION</div><h2 id="workspace-title">The complete authority path</h2></div>
        <span id="run-state" class="state-badge">READY</span>
      </div>
      <ol class="pipeline" aria-label="Workflow stages">
        <li data-stage="observe"><span>01</span>Observe</li>
        <li data-stage="evidence"><span>02</span>Evidence</li>
        <li data-stage="proposal"><span>03</span>Proposal</li>
        <li data-stage="policy"><span>04</span>Policy</li>
        <li data-stage="approval"><span>05</span>Human</li>
        <li data-stage="execution"><span>06</span>Execute</li>
        <li data-stage="verification"><span>07</span>Verify</li>
        <li data-stage="receipt"><span>08</span>Receipt</li>
      </ol>

      <div class="workspace-grid">
        <div class="stack">
          <article class="panel panel-pad">
            <div class="panel-head"><h3>Observed evidence</h3><span class="state-badge">READ ONLY</span></div>
            <dl class="facts">
              <div class="fact"><dt>Target</dt><dd id="target">—</dd></div>
              <div class="fact"><dt>Resource type</dt><dd id="resource-type">—</dd></div>
              <div class="fact wide"><dt>Finding</dt><dd id="finding">—</dd></div>
              <div class="fact"><dt>Observed</dt><dd id="observed-at">—</dd></div>
              <div class="fact"><dt>Evidence hash</dt><dd id="evidence-hash" class="hash">—</dd></div>
            </dl>
          </article>

          <article class="panel panel-pad">
            <div class="panel-head"><h3>Inert remediation proposal</h3><span class="state-badge">CANNOT EXECUTE</span></div>
            <dl class="facts">
              <div class="fact"><dt>Operation</dt><dd id="operation">—</dd></div>
              <div class="fact"><dt>Required authority</dt><dd id="authority">—</dd></div>
              <div class="fact wide"><dt>Impact / reason</dt><dd id="impact">—</dd></div>
              <div class="fact"><dt>Proposal hash</dt><dd id="proposal-hash" class="hash">—</dd></div>
              <div class="fact"><dt>Evidence fingerprint</dt><dd id="fingerprint" class="hash">—</dd></div>
            </dl>
            <div class="authority-callout"><strong>Why approval is required</strong>The proposal describes an exact change but carries <code>authorizes_execution: false</code>. Only a matching, unexpired human decision can establish authority.</div>
          </article>

          <article class="panel panel-pad">
            <div class="panel-head"><h3>Execution + independent verification</h3><span class="state-badge">SANDBOX ONLY</span></div>
            <dl class="facts">
              <div class="fact"><dt>Request binding</dt><dd id="request-hash" class="hash">—</dd></div>
              <div class="fact"><dt>Decision binding</dt><dd id="decision-hash" class="hash">—</dd></div>
              <div class="fact"><dt>Execution receipt</dt><dd id="receipt-hash" class="hash">—</dd></div>
              <div class="fact"><dt>Verification proof</dt><dd id="verification-hash" class="hash">—</dd></div>
            </dl>
            <div class="resource-diff"><div><span>Before</span><code id="before-state">No mutation receipt</code></div><div><span>After / read-back</span><code id="after-state">No mutation receipt</code></div></div>
          </article>
        </div>

        <aside class="stack">
          <section class="panel panel-pad" aria-labelledby="authority-title">
            <div class="panel-head"><h3 id="authority-title">Human authority</h3></div>
            <p id="decision-copy" class="decision-state">Start a scenario to reach the decision boundary.</p>
            <div class="controls">
              <button id="review" class="button secondary" type="button" disabled>Review exact request</button>
              <div class="button-row"><button id="approve" class="button" type="button" disabled>Approve</button><button id="deny" class="button deny" type="button" disabled>Deny</button></div>
              <button id="execute" class="button secondary" type="button" disabled><span id="execute-label">Execute approved action</span></button>
            </div>
            <div class="proof"><div><strong id="run-mutations">0</strong><span>mutations this run</span></div><div><strong id="process-mutations">0</strong><span>process sandbox mutations</span></div><div><strong id="provider-calls">0</strong><span>deterministic model calls</span></div><div><strong>0</strong><span>real AWS mutations</span></div></div>
            <div id="outcome" class="outcome">No model output can mutate this sandbox.</div>
          </section>

          <section class="panel panel-pad" aria-labelledby="audit-title">
            <div class="panel-head"><h3 id="audit-title">Durable evidence timeline</h3></div>
            <ol id="timeline" class="timeline"><li class="empty">The immutable timeline appears after a scenario starts.</li></ol>
          </section>

          <section class="panel panel-pad">
            <div class="panel-head"><h3>Run identity</h3></div>
            <dl class="facts">
              <div class="fact wide"><dt>Run ID</dt><dd id="run-id" class="hash">—</dd></div>
              <div class="fact wide"><dt>Trace ID</dt><dd id="trace-id" class="hash">—</dd></div>
              <div class="fact wide"><dt>Integrity-verified snapshot</dt><dd id="snapshot-hash" class="hash">—</dd></div>
              <div class="fact wide"><dt>Runtime / model</dt><dd><span id="mode-runtime">portable</span> · <span id="model-id">aioa.mock.deterministic-v1</span></dd></div>
            </dl>
          </section>
        </aside>
      </div>

      <div class="panel technical-wrap">
        <details class="technical"><summary>Inspect sanitized machine-readable evidence</summary><pre id="raw-output">No run selected.</pre></details>
      </div>
    </section>

    <section class="section connection" aria-labelledby="connection-title">
      <details>
        <summary id="connection-title">Manual local-session fallback</summary>
        <form id="connect-form" class="connection-form">
          <input id="token" type="password" autocomplete="off" spellcheck="false" aria-label="Local bearer token" placeholder="Paste owner-only local token">
          <button class="button secondary" type="submit">Connect</button>
          <button id="disconnect" class="button deny" type="button">Disconnect</button>
        </form>
      </details>
    </section>
  </main>
  <footer class="shell footer">AIOA portable judge experience · deterministic model · protected local sandbox · no AWS credentials required</footer>
  <div id="notice" class="notice" role="status" aria-live="polite" hidden></div>
  <script>{JUDGE_UI_SCRIPT}</script>
</body>
</html>"""
