"use strict";

const app = document.querySelector("#app");
const serviceState = document.querySelector("#service-state");
const fragment = new URLSearchParams(window.location.hash.slice(1));
const capability = fragment.get("cap");
window.history.replaceState(null, "", window.location.pathname);

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const formatNumber = (value, digits = 2) =>
  value === null || value === undefined
    ? "Unknown"
    : new Intl.NumberFormat(undefined, {
        maximumFractionDigits: digits,
      }).format(value);

const costLabel = (cost) => {
  if (!cost) return "Unknown";
  const credits = cost.credits ?? cost.observed_credits;
  return credits === null || credits === undefined
    ? "Unknown"
    : `${formatNumber(credits, 4)} credits`;
};

const centsLabel = (cost) => {
  if (!cost) return "No credit observation";
  const credits = cost.credits ?? cost.observed_credits;
  return credits === null || credits === undefined
    ? "No credit observation"
    : `${formatNumber(credits, 4)} cents by user convention`;
};

async function loadJson(path) {
  const response = await fetch(path, {
    headers: { Authorization: `Bearer ${capability}` },
    cache: "no-store",
  });
  const value = await response.json();
  if (!response.ok) {
    throw new Error(value.error || `Request failed: ${response.status}`);
  }
  return value;
}

function metric(label, value, detail) {
  return `
    <div class="metric">
      <span class="metric-label">${escapeHtml(label)}</span>
      <strong class="metric-value">${escapeHtml(value)}</strong>
      <span class="metric-detail">${escapeHtml(detail)}</span>
    </div>`;
}

function availabilityRows(availability) {
  return Object.entries(availability)
    .map(([name, status]) => `
      <tr>
        <td>${escapeHtml(name.replaceAll("_", " "))}</td>
        <td><span class="badge ${escapeHtml(status)}">${escapeHtml(status)}</span></td>
      </tr>`)
    .join("");
}

function renderIndex(data) {
  const available = data.campaigns.filter(
    (campaign) => campaign.availability === "available",
  ).length;
  const liveAvailable = data.availability.live_sessions === "available";
  app.innerHTML = `
    <section class="page-heading">
      <div>
        <h1>Evaluation campaigns</h1>
        <p>Completed evaluator artifacts remain authoritative. Live local work is labeled separately.</p>
      </div>
    </section>
    <section class="metrics">
      ${metric("Registered campaigns", formatNumber(data.campaigns.length, 0), "Local corpus registrations")}
      ${metric("Available", formatNumber(available, 0), "Corpus identity verified")}
      ${metric("Live sessions", liveAvailable ? formatNumber(data.session_counts.active + data.session_counts.blocked, 0) : "Unavailable", liveAvailable ? `${data.session_counts.stale} stale | ${data.active_attempts} active attempts` : "No registered corpus has live session state")}
      ${metric("Cloud activity", "Unavailable", "Deferred by design")}
    </section>
    ${
      data.campaigns.length
        ? `<section class="campaign-grid">
            ${data.campaigns
              .map(
                (campaign) => `
                  <a class="campaign-link" href="/campaign/${escapeHtml(campaign.campaign_id)}#cap=${encodeURIComponent(capability)}">
                    <strong>${escapeHtml(campaign.corpus_name)}</strong>
                    <span>${escapeHtml(campaign.target_skills.join(", ") || "No target skills")} | ${escapeHtml(campaign.availability)} | ${escapeHtml(campaign.session_counts.active)} active sessions</span>
                  </a>`,
              )
              .join("")}
          </section>`
        : `<section class="empty-state"><h1>No campaigns registered</h1><p>Run the dashboard ensure command for an evaluation corpus.</p></section>`
    }`;
}

function outcomeSummary(outcomes) {
  if (!outcomes) return "Not run";
  return Object.entries(outcomes)
    .filter(([, count]) => count)
    .map(([outcome, count]) => `${outcome} ${count}`)
    .join(", ");
}

function observedTotal(populations, field) {
  const values = populations
    .map((population) => population.total_spend[field])
    .filter((value) => value !== null && value !== undefined);
  return {
    value: values.length
      ? values.reduce((sum, value) => sum + value, 0)
      : null,
    known: values.length,
    total: populations.length,
  };
}

function observedDetail(summary, unit) {
  if (summary.value === null) return `No observed ${unit} data`;
  if (summary.known === summary.total) return `All ${summary.total} populations observed`;
  return `Partial: ${summary.known} of ${summary.total} populations observed`;
}

function stateBadge(state) {
  return `<span class="badge state-${escapeHtml(state)}">${escapeHtml(state)}</span>`;
}

const shortId = (value) => (value ? value.slice(0, 12) : "Unavailable");

function roleCard(role, value) {
  const status = value?.status || "unavailable";
  return `
    <div class="lineage-role ${escapeHtml(status)}">
      <span class="lineage-role-name">${escapeHtml(role)}</span>
      <strong class="mono">${escapeHtml(shortId(value?.snapshot_id))}</strong>
      <span class="lineage-role-detail">${escapeHtml(status)} | ${escapeHtml(value?.authority || "no authority")}</span>
    </div>`;
}

function renderLineage(data) {
  const lineage = data.lineage;
  if (!lineage || lineage.status !== "available") {
    return `
      <section class="panel">
        <div class="panel-header">
          <div><h2>Skill lineage</h2><p>No admitted lineage snapshots have been published.</p></div>
          <span class="badge unavailable">unavailable</span>
        </div>
      </section>`;
  }
  const roles = [
    "original",
    "published",
    "integrated",
    "experimental",
    "passing",
    "released",
  ];
  return `
    <section class="panel lineage-panel">
      <div class="panel-header">
        <div><h2>Skill lineage</h2><p>Declared roles and evaluator-observed passing stay distinct.</p></div>
        <span class="badge available">${escapeHtml(lineage.snapshots.length)} snapshots</span>
      </div>
      <div class="lineage-strip">
        ${roles.map((role) => roleCard(role, lineage.roles[role])).join("")}
      </div>
      ${
        lineage.invalid.length || lineage.conflicts.length
          ? `<div class="panel-warning">
              ${escapeHtml(lineage.invalid.length)} invalid records and ${escapeHtml(lineage.conflicts.length)} writer conflicts remain excluded.
            </div>`
          : ""
      }
    </section>`;
}

function renderCampaignChange(data) {
  const original = data.lineage?.roles?.original;
  const integrated = data.lineage?.roles?.integrated;
  const comparison =
    original?.status === "available" && integrated?.status === "available"
      ? data.lineage.comparisons.find(
          (item) =>
            item.from_snapshot_id === original.snapshot_id &&
            item.to_snapshot_id === integrated.snapshot_id,
        )
      : null;
  if (!comparison) {
    return `
      <section class="panel">
        <div class="panel-header">
          <div><h2>Original to integrated</h2><p>No unique admitted comparison is available.</p></div>
          <span class="badge unavailable">unavailable</span>
        </div>
      </section>`;
  }
  const summary = comparison.summary;
  return `
    <section class="panel campaign-change">
      <div class="panel-header">
        <div><h2>Original to integrated</h2><p>Exact admitted snapshot comparison across all target skills.</p></div>
        <span class="identity mono">${escapeHtml(shortId(comparison.from_snapshot_id))} to ${escapeHtml(shortId(comparison.to_snapshot_id))}</span>
      </div>
      <div class="change-strip">
        <div><strong>${escapeHtml(summary.added_files + summary.removed_files + summary.modified_files)}</strong><span>files changed</span></div>
        <div><strong>+${escapeHtml(summary.added_lines)} / -${escapeHtml(summary.removed_lines)}</strong><span>line movement</span></div>
        <div><strong>${escapeHtml(summary.byte_delta)}</strong><span>byte delta</span></div>
        <div><strong>${escapeHtml(summary.binary_changes)}</strong><span>binary changes</span></div>
      </div>
    </section>`;
}

function renderAttention(data) {
  return `
    <section class="panel attention-panel">
      <div class="panel-header">
        <div><h2>Needs attention</h2><p>Blocked, conflicted, failing, stale, or missing-progress work only.</p></div>
        <span class="badge ${data.attention.length ? "state-blocked" : "available"}">${escapeHtml(data.attention.length)}</span>
      </div>
      ${
        data.attention.length
          ? `<div class="attention-list">
              ${data.attention
                .map(
                  (item) => `
                    <a class="attention-item" href="/campaign/${escapeHtml(data.campaign.campaign_id)}/task/${escapeHtml(item.case_id)}#cap=${encodeURIComponent(capability)}">
                      <span class="attention-kind">${escapeHtml(item.kind.replaceAll("_", " "))}</span>
                      <strong>${escapeHtml(item.case_id)}</strong>
                      <span>${escapeHtml(item.summary)}</span>
                    </a>`,
                )
                .join("")}
            </div>`
          : `<div class="panel-empty">No task currently meets the attention criteria.</div>`
      }
    </section>`;
}

function liveSessionRows(data) {
  return data.sessions
    .map(
      (item) => `
        <tr>
          <td><a href="/campaign/${escapeHtml(data.campaign.campaign_id)}/session/${escapeHtml(item.session_id)}#cap=${encodeURIComponent(capability)}"><span class="identity mono">${escapeHtml(item.session_id)}</span></a></td>
          <td>${stateBadge(item.state)}</td>
          <td>${escapeHtml(item.case_id || "Unassigned")}</td>
          <td><span class="identity mono">${escapeHtml(item.skill_identity || "Unknown")}</span></td>
          <td>${escapeHtml(item.summary || "No current summary")}</td>
          <td>${escapeHtml(formatNumber(item.age_seconds, 0))}s ago</td>
          <td><span class="identity">${escapeHtml(item.source)}</span></td>
        </tr>`,
    )
    .join("");
}

function liveAttemptRows(items) {
  return items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.case_id)}</td>
          <td>${stateBadge(item.state)}</td>
          <td>${escapeHtml(item.model)}</td>
          <td>${escapeHtml(item.effort)}</td>
          <td>${escapeHtml(item.arm)}</td>
          <td><span class="identity mono">${escapeHtml(item.treatment_identity)}</span></td>
          <td><span class="identity mono">${escapeHtml(item.skill_identity || "Unknown")}</span></td>
          <td>${escapeHtml(item.location)} / ${escapeHtml(item.platform)}</td>
          <td><span class="identity">${escapeHtml(item.run_path)}</span></td>
          <td>${escapeHtml(item.authority)}</td>
        </tr>`,
    )
    .join("");
}

function renderCampaign(data) {
  const totalSpend = observedTotal(data.populations, "observed_credits");
  const premium = observedTotal(
    data.populations,
    "observed_premium_requests",
  );
  const passes = data.attempts.filter(
    (attempt) => attempt.correctness === "PASS",
  ).length;
  const details = new Map(
    data.task_details.map((item) => [item.case_id, item]),
  );
  app.innerHTML = `
    <section class="page-heading">
      <div>
        <h1>${escapeHtml(data.campaign.corpus_name)}</h1>
        <p>${escapeHtml(data.campaign.target_skills.join(", ") || "No target skills")} | Completed history grouped by exact observed identity.</p>
      </div>
      <a href="/#cap=${encodeURIComponent(capability)}">All campaigns</a>
    </section>
    <section class="metrics">
      ${metric("Corpus tasks", formatNumber(data.cases.length, 0), "Every indexed case")}
      ${metric("Completed attempts", formatNumber(data.attempts.length, 0), `${passes} executable passes`)}
      ${metric("Active sessions", formatNumber(data.sessions.filter((item) => ["active", "blocked"].includes(item.state)).length, 0), `${data.sessions.filter((item) => item.state === "stale").length} stale`)}
      ${metric("Active attempts", formatNumber(data.live_attempts.filter((item) => item.state === "active").length, 0), "Live events never upgrade results")}
    </section>
    <section class="metrics secondary-metrics">
      ${metric("Observed credits", formatNumber(totalSpend.value, 4), totalSpend.value === null ? observedDetail(totalSpend, "credit") : `${formatNumber(totalSpend.value, 4)} cents by user convention | ${observedDetail(totalSpend, "credit")}`)}
      ${metric("Premium requests", formatNumber(premium.value, 4), `Separate evaluator-native unit | ${observedDetail(premium, "premium request")}`)}
    </section>
    ${renderLineage(data)}
    ${renderCampaignChange(data)}
    ${renderAttention(data)}
    <section class="panel">
      <div class="panel-header">
        <div><h2>Local sessions</h2><p>Session-owned heartbeats and assignments; stale is never completed.</p></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Session</th><th>State</th><th>Task</th><th>Skill identity</th><th>Current work</th><th>Freshness</th><th>Authority</th></tr></thead>
          <tbody>${liveSessionRows(data) || '<tr><td colspan="7">Live session registration unavailable or not started.</td></tr>'}</tbody>
        </table>
      </div>
    </section>
    <section class="panel">
      <div class="panel-header">
        <div><h2>Local attempts</h2><p>Immutable artifacts supersede matching live attempts.</p></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Task</th><th>State</th><th>Model</th><th>Effort</th><th>Arm</th><th>Treatment</th><th>Skill</th><th>Location</th><th>Run</th><th>Authority</th></tr></thead>
          <tbody>${liveAttemptRows(data.live_attempts) || '<tr><td colspan="10">No local attempt events yet.</td></tr>'}</tbody>
        </table>
      </div>
    </section>
    <section class="panel">
      <div class="panel-header">
        <div><h2>Task status</h2><p>Outcomes stay distinct. Unknown and not-run states are never zero.</p></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Task</th><th>Skill</th><th>Type</th><th>Outcome</th><th>Progress</th><th>Authority</th></tr></thead>
          <tbody>
            ${data.cases
              .map((item) => {
                const progress = details.get(item.case_id)?.progress;
                const progressLabel =
                  progress?.status === "available"
                    ? `${progress.frontier} | ${progress.movement}`
                    : progress?.status || "unavailable";
                return `
                  <tr>
                    <td><a class="task-link" href="/campaign/${escapeHtml(data.campaign.campaign_id)}/task/${escapeHtml(item.case_id)}#cap=${encodeURIComponent(capability)}"><strong>${escapeHtml(item.case_id)}</strong></a></td>
                    <td>${escapeHtml(item.target_skill)}</td>
                    <td>${escapeHtml(item.case_type)}</td>
                    <td>${escapeHtml(outcomeSummary(item.outcomes))}</td>
                    <td>${escapeHtml(progressLabel)}</td>
                    <td><span class="identity">${escapeHtml(item.source.id)}</span></td>
                  </tr>`;
              })
              .join("")}
          </tbody>
        </table>
      </div>
    </section>
    <section class="panel">
      <div class="panel-header">
        <div><h2>Matched populations</h2><p>Metrics compare only complete identity tuples.</p></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Case</th><th>Skill identity</th><th>Model</th><th>Pass at 1</th><th>Coverage</th><th>Total spend</th><th>Premium</th></tr></thead>
          <tbody>
            ${data.populations
              .map(
                (item) => `
                  <tr>
                    <td>${escapeHtml(item.population.case_id)}</td>
                    <td><span class="identity mono">${escapeHtml(item.population.skill_identity || "Unknown")}</span></td>
                    <td>${escapeHtml(item.population.model || "Unknown")}</td>
                    <td class="mono">${escapeHtml(formatNumber(item.pass_at_1))}</td>
                    <td class="mono">${escapeHtml(formatNumber(item.execution_coverage))}</td>
                    <td><strong>${escapeHtml(costLabel(item.total_spend))}</strong><span class="identity">${escapeHtml(centsLabel(item.total_spend))}</span></td>
                    <td class="mono">${escapeHtml(formatNumber(item.total_spend.observed_premium_requests, 4))}</td>
                  </tr>`,
              )
              .join("") || '<tr><td colspan="7">No completed populations yet.</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
    <section class="panel">
      <div class="panel-header">
        <div><h2>Attempts</h2><p>Immutable artifacts supersede all future live metadata.</p></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Source</th><th>Result</th><th>Behavioral</th><th>Attempt</th><th>Timing</th><th>Accounting</th></tr></thead>
          <tbody>
            ${data.attempts
              .map(
                (item) => `
                  <tr>
                    <td><span class="identity">${escapeHtml(item.source.id)}</span></td>
                    <td class="outcome-${escapeHtml(item.correctness)}"><strong>${escapeHtml(item.correctness)}</strong></td>
                    <td>${escapeHtml(item.behavioral_verdict || "Unavailable")}</td>
                    <td class="mono">${escapeHtml(item.attempt)}</td>
                    <td class="mono">${escapeHtml(formatNumber(item.elapsed_seconds))}</td>
                    <td>${escapeHtml(costLabel(item.total_spend))}</td>
                  </tr>`,
              )
              .join("") || '<tr><td colspan="6">No completed attempts yet.</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
    <section class="panel">
      <div class="panel-header"><div><h2>Availability</h2><p>Unsupported surfaces are explicit.</p></div></div>
      <div class="table-wrap"><table><tbody>${availabilityRows(data.availability)}</tbody></table></div>
    </section>
    <section class="notice"><strong>Accounting note:</strong> ${escapeHtml(data.interpretation)}</section>`;
}

function progressBadge(progress) {
  if (!progress || progress.status !== "available") {
    return `<span class="badge state-${escapeHtml(progress?.status || "unavailable")}">${escapeHtml(progress?.status || "unavailable")}</span>`;
  }
  return `<span class="badge progress-evidence">workflow evidence</span>`;
}

function comparisonView(comparison) {
  if (!comparison) {
    return `<div class="panel-empty">No relevant admitted comparison is available for this task.</div>`;
  }
  const summary = comparison.summary;
  return `
    <div class="comparison-summary">
      ${metric("Files changed", formatNumber(summary.added_files + summary.removed_files + summary.modified_files, 0), `${summary.added_files} added | ${summary.removed_files} removed | ${summary.modified_files} modified`)}
      ${metric("Line movement", `+${formatNumber(summary.added_lines, 0)} / -${formatNumber(summary.removed_lines, 0)}`, `${summary.binary_changes} binary changes`)}
      ${metric("Byte delta", formatNumber(summary.byte_delta, 0), `${shortId(comparison.from_snapshot_id)} to ${shortId(comparison.to_snapshot_id)}`)}
    </div>
    <div class="diff-list">
      ${comparison.files
        .map(
          (file) => `
            <details class="diff-file" ${comparison.files.length === 1 ? "open" : ""}>
              <summary>
                <span><strong>${escapeHtml(file.skill)}/${escapeHtml(file.path)}</strong></span>
                <span class="badge state-${file.status === "modified" ? "blocked" : "active"}">${escapeHtml(file.status)}</span>
              </summary>
              ${
                file.binary
                  ? `<div class="binary-change">Binary content changed. Only hashes, modes, and byte counts are available.</div>`
                  : `<pre class="diff-code"><code>${escapeHtml(file.diff || "No textual change")}</code></pre>`
              }
            </details>`,
        )
        .join("") || '<div class="panel-empty">The admitted snapshots have no file changes.</div>'}
    </div>`;
}

function taskAttemptRows(items) {
  return items
    .map(
      (item) => `
        <tr>
          <td><span class="identity">${escapeHtml(item.source.id)}</span></td>
          <td class="outcome-${escapeHtml(item.correctness)}"><strong>${escapeHtml(item.correctness)}</strong></td>
          <td>${escapeHtml(item.behavioral_verdict || "Unavailable")}</td>
          <td>${escapeHtml(item.population.model || "Unknown")}</td>
          <td class="mono">${escapeHtml(formatNumber(item.elapsed_seconds))}</td>
        </tr>`,
    )
    .join("");
}

function renderTask(data, caseId) {
  const detail = data.task_details.find((item) => item.case_id === caseId);
  const summary = data.cases.find((item) => item.case_id === caseId);
  if (!detail || !summary) {
    throw new Error(`Task unavailable: ${caseId}`);
  }
  const progress = detail.progress;
  const progressAvailable = progress.status === "available";
  const progressMetric =
    progress.status === "conflicted" ? "Conflicted" : "Unavailable";
  const progressMetricDetail =
    progress.status === "conflicted"
      ? "Incompatible current workflow records"
      : "No current workflow record";
  app.innerHTML = `
    <section class="page-heading task-heading">
      <div>
        <h1>${escapeHtml(caseId)}</h1>
        <p>${escapeHtml(summary.target_skill)} | Exact case revision <span class="mono">${escapeHtml(shortId(detail.case_revision))}</span></p>
      </div>
      <a href="/campaign/${escapeHtml(data.campaign.campaign_id)}#cap=${encodeURIComponent(capability)}">Campaign</a>
    </section>
    <section class="metrics">
      ${metric("Outcome", detail.outcome || "Not run", "Immutable evaluator authority")}
      ${metric("Failure frontier", progressAvailable ? progress.frontier : progressMetric, progressAvailable ? progress.classification.replaceAll("_", " ") : progressMetricDetail)}
      ${metric("Product movement", progressAvailable ? progress.movement : progressMetric, progressAvailable ? "Workflow evidence, not correctness" : progressMetricDetail)}
      ${metric("Associated snapshot", shortId(detail.associated_snapshot_id), detail.associated_snapshot_id || "No unique integrated or released tip")}
    </section>
    <section class="panel">
      <div class="panel-header">
        <div><h2>Current progress</h2><p>Bound to the exact case revision and associated skill snapshot.</p></div>
        ${progressBadge(progress)}
      </div>
      ${
        progressAvailable
          ? `<div class="progress-layout">
              <div class="progress-summary">
                <h3>${escapeHtml(progress.summary)}</h3>
                <dl>
                  <div><dt>Classification</dt><dd>${escapeHtml(progress.classification.replaceAll("_", " "))}</dd></div>
                  <div><dt>Blocker</dt><dd>${escapeHtml(progress.blocker || "None recorded")}</dd></div>
                  <div><dt>Next action</dt><dd>${escapeHtml(progress.next_action || "None recorded")}</dd></div>
                  <div><dt>Observed</dt><dd>${escapeHtml(progress.observed_at)}</dd></div>
                  <div><dt>Sources</dt><dd>${progress.sources.length ? progress.sources.map((item) => `<span class="source-label">${escapeHtml(item.kind)}:${escapeHtml(item.id)}</span>`).join("") : "None recorded"}</dd></div>
                </dl>
              </div>
              <div class="uptake-list">
                <h3>Instruction uptake</h3>
                ${
                  progress.uptake.length
                    ? progress.uptake
                        .map(
                          (item) => `
                            <div class="uptake-item">
                              <div><strong>${escapeHtml(item.rule_id)}</strong><span class="badge uptake-${escapeHtml(item.status.toLowerCase())}">${escapeHtml(item.status)}</span></div>
                              <p>${escapeHtml(item.summary)}</p>
                            </div>`,
                        )
                        .join("")
                    : '<div class="panel-empty">No instruction-uptake rows recorded.</div>'
                }
              </div>
            </div>`
          : `<div class="panel-empty">Progress is ${escapeHtml(progress.status)} for the current task and skill snapshot.</div>`
      }
    </section>
    <section class="panel">
      <div class="panel-header">
        <div><h2>Relevant skill change</h2><p>Exact admitted bytes. Stored source files are never directly served.</p></div>
      </div>
      ${comparisonView(detail.comparison)}
    </section>
    <section class="panel">
      <div class="panel-header">
        <div><h2>Immutable attempts</h2><p>Only attempts for this exact frozen case revision are shown.</p></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Source</th><th>Result</th><th>Behavioral</th><th>Model</th><th>Seconds</th></tr></thead>
          <tbody>${taskAttemptRows(detail.attempts) || '<tr><td colspan="5">No completed attempts for this revision.</td></tr>'}</tbody>
        </table>
      </div>
    </section>
    <section class="panel">
      <div class="panel-header">
        <div><h2>Local activity</h2><p>Live activity is non-final and cannot change the outcome above.</p></div>
      </div>
      <div class="activity-grid">
        <div><strong>${escapeHtml(detail.sessions.length)}</strong><span>sessions</span></div>
        <div><strong>${escapeHtml(detail.live_attempts.length)}</strong><span>live attempts</span></div>
        <div><strong>${escapeHtml(progressAvailable ? progress.sources.length : 0)}</strong><span>safe source identifiers</span></div>
      </div>
    </section>`;
}

function renderSession(data) {
  const item = data.session;
  app.innerHTML = `
    <section class="page-heading">
      <div>
        <h1>Session ${escapeHtml(item.session_id.slice(0, 8))}</h1>
        <p>${escapeHtml(data.campaign.corpus_name)} | ${escapeHtml(item.summary || "No current assignment")}</p>
      </div>
      <a href="/campaign/${escapeHtml(data.campaign.campaign_id)}#cap=${encodeURIComponent(capability)}">Campaign</a>
    </section>
    <section class="metrics">
      ${metric("State", item.state, `Reported ${item.reported_state}`)}
      ${metric("Current task", item.case_id || "Unassigned", item.case_revision || "No active revision")}
      ${metric("Skill identity", item.skill_identity || "Unknown", "Exact when supplied by the session")}
      ${metric("Heartbeat", `${formatNumber(item.age_seconds, 0)}s ago`, item.source)}
    </section>
    <section class="panel">
      <div class="panel-header"><div><h2>Assignment timeline</h2><p>Non-final session events, newest recorded last.</p></div></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Recorded</th><th>Event</th><th>Task</th><th>State</th><th>Summary</th><th>Source</th></tr></thead>
          <tbody>
            ${data.assignments
              .map(
                (event) => `
                  <tr>
                    <td>${escapeHtml(event.recorded_at)}</td>
                    <td>${escapeHtml(event.event_type)}</td>
                    <td>${escapeHtml(event.entity.case_id)}</td>
                    <td>${stateBadge(event.payload.state)}</td>
                    <td>${escapeHtml(event.payload.summary)}</td>
                    <td>${escapeHtml(event.source)}</td>
                  </tr>`,
              )
              .join("") || '<tr><td colspan="6">No assignment events yet.</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
    <section class="panel">
      <div class="panel-header"><div><h2>Related local attempts</h2><p>Shown only for the current exact task.</p></div></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Task</th><th>State</th><th>Model</th><th>Effort</th><th>Arm</th><th>Treatment</th><th>Skill</th><th>Location</th><th>Run</th><th>Authority</th></tr></thead>
          <tbody>${liveAttemptRows(data.attempts) || '<tr><td colspan="10">No related local attempts.</td></tr>'}</tbody>
        </table>
      </div>
    </section>`;
}

async function start() {
  if (!capability) {
    throw new Error("Missing browser capability. Run the dashboard open command again.");
  }
  const sessionMatch = window.location.pathname.match(
    /^\/campaign\/([0-9a-f]{32})\/session\/([0-9a-f-]{36})$/,
  );
  const taskMatch = window.location.pathname.match(
    /^\/campaign\/([0-9a-f]{32})\/task\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})$/,
  );
  const match = window.location.pathname.match(/^\/campaign\/([0-9a-f]{32})$/);
  const data = await loadJson(
    sessionMatch
      ? `/api/campaign/${sessionMatch[1]}/session/${sessionMatch[2]}`
      : taskMatch
        ? `/api/campaign/${taskMatch[1]}`
      : match
        ? `/api/campaign/${match[1]}`
        : "/api/index",
  );
  serviceState.textContent = "Read only";
  serviceState.classList.add("available");
  if (sessionMatch) renderSession(data);
  else if (taskMatch) renderTask(data, taskMatch[2]);
  else if (match) renderCampaign(data);
  else renderIndex(data);
}

start().catch((error) => {
  serviceState.textContent = "Unavailable";
  serviceState.classList.add("unavailable");
  app.innerHTML = `
    <section class="error-state">
      <h1>Dashboard unavailable</h1>
      <p>${escapeHtml(error.message)}</p>
      <p>Run <span class="mono">dashboard open</span> again if the service was replaced.</p>
    </section>`;
});
