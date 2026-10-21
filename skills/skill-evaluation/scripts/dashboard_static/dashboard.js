"use strict";

const app = document.querySelector("#app");
const serviceState = document.querySelector("#service-state");
const fragment = new URLSearchParams(window.location.hash.slice(1));
const fragmentCapability = fragment.get("cap");
const projectRoute = window.location.pathname.match(
  /^\/project\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})/,
);
const routeScope = projectRoute
  ? `project:${projectRoute[1]}`
  : window.location.pathname === "/unassigned" ||
      window.location.pathname.startsWith("/campaign/")
    ? "unassigned"
    : "project_index";
let capability = fragmentCapability;
let capabilityStorageKey = null;
if (capability) {
  const generation = capability.split(".", 1)[0];
  if (generation) {
    capabilityStorageKey = `skill-eval-cap:${generation}:${routeScope}`;
    try {
      sessionStorage.setItem(capabilityStorageKey, capability);
    } catch {
      capabilityStorageKey = null;
    }
  }
} else {
  try {
    const matches = [];
    for (let index = 0; index < sessionStorage.length; index += 1) {
      const key = sessionStorage.key(index);
      if (key?.startsWith("skill-eval-cap:") && key.endsWith(`:${routeScope}`)) {
        matches.push([key, sessionStorage.getItem(key)]);
      }
    }
    if (matches.length === 1) {
      [capabilityStorageKey, capability] = matches[0];
    }
  } catch {
    capability = null;
  }
}
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
    if ([401, 403].includes(response.status) && capabilityStorageKey) {
      try {
        sessionStorage.removeItem(capabilityStorageKey);
      } catch {
        capabilityStorageKey = null;
      }
    }
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

async function openProject(projectId) {
  const response = await fetch(
    `/api/projects/${encodeURIComponent(projectId)}/capability`,
    {
      method: "POST",
      headers: { Authorization: "Bearer " + capability },
      cache: "no-store",
    },
  );
  const value = await response.json();
  if (!response.ok) {
    throw new Error(value.error || `Request failed: ${response.status}`);
  }
  window.location.assign(
    `${value.route}#cap=${encodeURIComponent(value.capability)}`,
  );
}

function renderIndex(data) {
  app.innerHTML = `
    <section class="page-heading">
      <div>
        <h1>Skill improvement projects</h1>
        <p>Each scorecard uses one exact current revision. Results from different revisions are never pooled.</p>
      </div>
    </section>
    <section class="metrics">
      ${metric("Projects", formatNumber(data.projects.length, 0), "Explicit corpus-local declarations")}
      ${metric("Active local runs", formatNumber(data.projects.reduce((sum, project) => sum + project.active_runs, 0), 0), "Supported evaluator launchers")}
    </section>
    ${
      data.projects.length
        ? `<section class="campaign-grid">
            ${data.projects
              .map(
                (project) => `
                  <button class="campaign-link project-open" data-project-id="${escapeHtml(project.project_id)}">
                    <strong>${escapeHtml(project.title)}</strong>
                    <span>${escapeHtml(project.goal)}</span>
                    <small>${escapeHtml(project.target_skills.join(", "))} | ${escapeHtml(project.task_counts.passing)} passing | ${escapeHtml(project.active_runs)} active runs</small>
                  </button>`,
              )
              .join("")}
          </section>`
        : `<section class="empty-state"><h1>No projects registered</h1><p>Add a valid evaluation-project.json to a corpus and register it.</p></section>`
    }`;
  document.querySelectorAll(".project-open").forEach((button) => {
    button.addEventListener("click", () => {
      openProject(button.dataset.projectId).catch((error) => {
        app.innerHTML = `<section class="error-state"><h1>Project unavailable</h1><p>${escapeHtml(error.message)}</p></section>`;
      });
    });
  });
}

function renderUnassigned(data) {
  app.innerHTML = `
    <section class="page-heading simple-heading">
      <div>
        <h1>Unassigned evaluations</h1>
        <p>Legacy corpora remain readable here until they explicitly declare a project.</p>
      </div>
    </section>
    ${
      data.campaigns.length
        ? `<section class="campaign-grid">${data.campaigns
            .map(
              (campaign) => `
                <a class="campaign-link" href="/campaign/${escapeHtml(campaign.campaign_id)}">
                  <strong>${escapeHtml(campaign.corpus_name)}</strong>
                  <span>${escapeHtml(campaign.target_skills.join(", ") || "No target skills")}</span>
                </a>`,
            )
            .join("")}</section>`
        : '<section class="empty-state"><h2>No unassigned evaluations</h2></section>'
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
                    <a class="attention-item" href="/campaign/${escapeHtml(data.campaign.campaign_id)}/task/${escapeHtml(item.case_id)}">
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

const joinedValues = (items, empty = "Unavailable") =>
  items?.length ? items.join(", ") : empty;

function selectionLabel(selection) {
  if (!selection) return "pending";
  if (selection.status === "selected") {
    return `selected: ${selection.selected_treatment_id}`;
  }
  return selection.status.replaceAll("_", " ");
}

function renderExperimentAttention(experiments) {
  return `
          <section class="panel experiment-attention">
            <div class="panel-header">
              <div><h2>Experiment attention</h2><p>Missing activity, incomplete stages, conflicts, judge disagreement, and accounting gaps.</p></div>
              <span class="badge ${experiments.attention.length ? "state-blocked" : "available"}">${escapeHtml(experiments.attention.length)}</span>
            </div>
            ${
              experiments.attention.length
                ? `<div class="experiment-attention-list">
                    ${experiments.attention
                      .map(
                        (item) => `
                          <div class="experiment-attention-item">
                            <strong>${escapeHtml(item.kind.replaceAll("_", " "))}</strong>
                            <span>${escapeHtml(item.case_id || item.experiment_id)}</span>
                            <p>${escapeHtml(item.summary)}</p>
                          </div>`,
                      )
                      .join("")}
                  </div>`
                : '<div class="panel-empty">No admitted experiment record currently needs attention.</div>'
            }
    </section>`;
}

function experimentActivityRows(items) {
  return items
    .map(
      (item) => `
              <tr>
                <td><a class="task-link" href="/campaign/${escapeHtml(item.campaign_id || "")}/task/${escapeHtml(item.case_id)}">${escapeHtml(item.case_id)}</a><span class="identity mono">${escapeHtml(shortId(item.case_revision))}</span></td>
                <td>${escapeHtml(item.treatment_id)}<span class="identity">repetition ${escapeHtml(item.repetition)}</span></td>
                <td>${escapeHtml(item.model)}<span class="identity">${escapeHtml(item.platform)} | ${escapeHtml(item.route)}</span></td>
                <td>${stateBadge(item.state)}</td>
                <td>${escapeHtml(joinedValues(item.transport_statuses))}<span class="identity">${escapeHtml(joinedValues(item.transport_conclusions, "No conclusion"))}</span></td>
                <td>${escapeHtml(item.stage_status || "Unavailable")}</td>
                <td class="${item.evaluator_result ? `outcome-${escapeHtml(item.evaluator_result)}` : ""}">${escapeHtml(item.evaluator_result || "Unavailable")}</td>
                <td><span class="identity mono">${escapeHtml(shortId(item.first_outcome_id))}</span></td>
                <td>${escapeHtml(item.recovery_source_id || "None")}<span class="identity mono">${escapeHtml(shortId(item.effective_result_id))}</span></td>
                <td>${escapeHtml(item.observed_as_of || "Not observed")}<span class="identity">${item.non_atomic ? "non-atomic snapshot" : "atomic or unavailable"}</span></td>
                <td>${item.cost.complete ? escapeHtml(costLabel(item.cost)) : "Incomplete"}<span class="identity">${escapeHtml(joinedValues(item.source_ids, "No safe source ID"))}</span></td>
              </tr>`,
          )
    .join("");
}

function renderExperiments(data) {
  const experiments = data.experiments;
  if (!experiments || experiments.status !== "available") {
    return `
            <section class="panel">
              <div class="panel-header">
                <div><h2>Experiments</h2><p>No admitted distributed experiment records are available.</p></div>
                <span class="badge unavailable">unavailable</span>
              </div>
      </section>`;
  }
  return `
          <section class="panel experiment-overview">
            <div class="panel-header">
              <div><h2>Experiments</h2><p>Predeclared treatments, exact distributed identity, and non-authoritative selection.</p></div>
              <span class="badge available">${escapeHtml(experiments.items.length)} experiments</span>
            </div>
            <div class="experiment-summary-strip">
              <div><strong>${escapeHtml(experiments.counts.planned)}</strong><span>planned attempts</span></div>
              <div><strong>${escapeHtml(experiments.counts.cloud_nonterminal)}</strong><span>cloud nonterminal</span></div>
              <div><strong>${escapeHtml(experiments.counts.distributed_pending)}</strong><span>distributed pending</span></div>
              <div><strong>${escapeHtml(experiments.counts.terminal)}</strong><span>terminal results</span></div>
              <div><strong>${escapeHtml(experiments.counts.invalid_or_conflicted)}</strong><span>invalid or conflicted</span></div>
            </div>
            ${experiments.items
              .map(
                (item) => `
                  <article class="experiment-block">
                    <header class="experiment-heading">
                      <div>
                        <h3>${escapeHtml(item.title)}</h3>
                        <p>${escapeHtml(item.summary)}</p>
                      </div>
                      <div class="experiment-meta">
                        <span class="badge state-${escapeHtml(item.selection.status === "selected" ? "active" : item.selection.status === "conflicted" ? "conflicted" : "idle")}">${escapeHtml(selectionLabel(item.selection))}</span>
                        <span>${escapeHtml(item.candidate_model)} | ${escapeHtml(item.platform)}</span>
                        <span>${escapeHtml(item.observed_as_of ? `observed as of ${item.observed_as_of}` : "cloud not observed")}${item.non_atomic ? " | non-atomic" : ""}</span>
                      </div>
                    </header>
                    <div class="treatment-grid">
                      ${item.treatments
                        .map(
                          (treatment) => `
                            <div class="treatment-card selection-${escapeHtml(treatment.selection_state)}">
                              <div class="treatment-card-heading">
                                <div><strong>${escapeHtml(treatment.treatment_id)}</strong><span>${escapeHtml(treatment.role)}</span></div>
                                <span class="badge state-${escapeHtml(treatment.selection_state === "selected" ? "active" : treatment.selection_state === "conflicted" ? "conflicted" : "idle")}">${escapeHtml(treatment.selection_state.replaceAll("_", " "))}</span>
                              </div>
                              <p>${escapeHtml(treatment.hypothesis)}</p>
                              <dl>
                                <div><dt>Repetitions</dt><dd>${escapeHtml(treatment.terminal_repetitions)} terminal / ${escapeHtml(treatment.planned_repetitions)} planned</dd></div>
                                <div><dt>Outcomes</dt><dd>${escapeHtml(`PASS ${treatment.outcomes.PASS}, FAIL ${treatment.outcomes.FAIL}`)}</dd></div>
                                <div><dt>Cost</dt><dd>${treatment.cost.complete ? escapeHtml(costLabel(treatment.cost)) : `Incomplete: ${treatment.cost.known_attempts} of ${treatment.cost.total_attempts}`}</dd></div>
                              </dl>
                            </div>`,
                        )
                        .join("")}
                    </div>
                  </article>`,
              )
              .join("")}
          </section>
          ${renderExperimentAttention(experiments)}
          <section class="panel">
            <div class="panel-header">
              <div><h2>Distributed activity</h2><p>Transport, stage, evaluator, first outcome, recovery, and effective result remain separate.</p></div>
            </div>
            <div class="table-wrap">
              <table class="distributed-table">
                <thead><tr><th>Task</th><th>Treatment</th><th>Execution</th><th>State</th><th>Transport</th><th>Stage</th><th>Evaluator</th><th>First outcome</th><th>Recovery / effective</th><th>Observation</th><th>Cost / source</th></tr></thead>
                <tbody>${experimentActivityRows(experiments.activity) || '<tr><td colspan="11">No distributed attempts have been admitted.</td></tr>'}</tbody>
              </table>
            </div>
    </section>`;
}

function liveSessionRows(data) {
  return data.sessions
    .map(
      (item) => `
        <tr>
          <td><a href="/campaign/${escapeHtml(data.campaign.campaign_id)}/session/${escapeHtml(item.session_id)}"><span class="identity mono">${escapeHtml(item.session_id)}</span></a></td>
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

const plural = (count, singular, pluralValue = `${singular}s`) =>
  `${count} ${count === 1 ? singular : pluralValue}`;

const agrees = (count, singular, pluralValue) =>
  count === 1 ? singular : pluralValue;

const sentenceCase = (value) => {
  const words = String(value || "")
    .replaceAll(/[-_.]+/g, " ")
    .replaceAll(/\s+/g, " ")
    .trim();
  return words ? words[0].toUpperCase() + words.slice(1) : "Untitled task";
};

const conciseTimestamp = (value) => {
  if (!value) {
    return "Start time unavailable";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
};

const conciseDuration = (seconds) => {
  if (!Number.isFinite(seconds)) return null;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(seconds < 36000 ? 1 : 0)}h`;
  return `${(seconds / 86400).toFixed(seconds < 864000 ? 1 : 0)}d`;
};

const taskEffortSummary = (task) => {
  const effort = task.effort;
  if (effort.runs === 0 && effort.attempts === 0) {
    return "No evaluation run yet.";
  }
  const timing = task.timing;
  const duration = conciseDuration(timing.elapsed_seconds);
  const lead = timing.first_qualified_pass_at
    ? `First qualified${duration ? ` in ${duration}` : ""}`
    : timing.first_run_at
      ? `Started ${conciseTimestamp(timing.first_run_at)}`
      : "No qualified attempt evidence yet";
  const attempts = `${plural(effort.runs, "run")}, ${plural(effort.attempts, "attempt")}`;
  const infrastructure = effort.infrastructure_failures
    ? `, ${plural(effort.infrastructure_failures, "infrastructure failure")}`
    : "";
  const cost = effort.total_cost;
  const costValue = cost.complete ? cost.credits : cost.observed_credits;
  const costLabel = Number.isFinite(costValue)
    ? ` · ${formatNumber(costValue)} ${costValue === 1 ? "credit" : "credits"}${cost.complete ? "" : " observed (partial)"}`
    : "";
  return `${lead} · ${attempts}${infrastructure}${costLabel}`;
};

const taskProgressSummary = (task) => {
  const progress = task.safe_progress;
  if (!progress || progress.status !== "available") return "";
  return `<p class="task-progress-copy">${escapeHtml(`${progress.passed} of ${progress.total} named checks passing`)}</p>`;
};

const runAttemptSummary = (run) => {
  const summary = `${run.planned_attempts} planned attempts; ${run.started_attempts} started`;
  if (run.completed_attempts === undefined) {
    return summary;
  }
  const counts = [
    run.passing_attempts,
    run.failing_attempts,
    run.unavailable_attempts,
  ];
  if (!counts.every(Number.isInteger)) {
    return `${summary}; ${run.completed_attempts} completed; outcome counts unavailable`;
  }
  return `${summary}; ${run.completed_attempts} completed, ${run.passing_attempts} passing, ${run.failing_attempts} failing, ${run.unavailable_attempts} unavailable`;
};

const taskRuns = (task, runs) =>
  runs.filter(
    (run) => Array.isArray(run.task_ids) && run.task_ids.includes(task.task_id),
  );

function renderTaskRuns(task, runs) {
  const matching = taskRuns(task, runs);
  if (!matching.length) return "";
  return `
    <div class="task-run-list">
      ${matching
        .map(
          (run) => `
            <div class="task-run-row">
              <time>${escapeHtml(conciseTimestamp(run.started_at))}</time>
              <strong>${escapeHtml(run.run_goal)}</strong>
              <span class="plain-status status-${escapeHtml(run.state === "completed" ? "passed" : run.state === "active" ? "running" : "failed")}">${escapeHtml(sentenceCase(run.state))}</span>
              <span>${escapeHtml(runAttemptSummary(run))}</span>
            </div>`,
        )
        .join("")}
    </div>`;
}

const isActive = (item) => ["active", "blocked"].includes(item.state);
const needsUpdate = (item) => ["stale", "conflicted"].includes(item.state);

function taskView(item, detail) {
  const sessions = detail?.sessions || [];
  const attempts = detail?.live_attempts || [];
  const live = [...sessions, ...attempts];
  const outcome = detail?.outcome;
  let state = "waiting";
  let label = "Not started";
  if (outcome === "PASS") {
    state = "passed";
    label = "Passed";
  } else if (outcome) {
    state = "failed";
    label = outcome === "FAIL" ? "Did not pass" : sentenceCase(outcome);
  }

  const definingLive =
    live.find((entry) => entry.state === "conflicted") ||
    live.find((entry) => entry.state === "blocked") ||
    live.find((entry) => entry.state === "active") ||
    live.find((entry) => entry.state === "stale");
  const activityState = definingLive?.state || null;
  const activityLabel = {
    active: "Running",
    blocked: "Blocked",
    stale: "Needs update",
    conflicted: "Conflicted",
  }[activityState] || null;
  const progress = detail?.progress;
  const definingSession = sessions
    .filter((entry) => entry.state === activityState && entry.summary)
    .sort((left, right) => left.age_seconds - right.age_seconds)[0];
  let summary = "No run has reported progress for this task yet.";
  if (progress?.status === "conflicted") {
    summary = "Progress records conflict and need review.";
  } else if (definingSession?.summary) {
    summary = definingSession.summary;
  } else if (progress?.status === "available") {
    summary = progress.summary;
  } else if (state === "passed") {
    summary = "This task has a passing evaluator result.";
  } else if (state === "failed") {
    summary = "The latest evaluator result did not pass.";
  }
  if (activityState) {
    state = activityState === "active" ? "running" : activityState;
    label = activityLabel;
  }
  return {
    caseId: item.case_id,
    title: sentenceCase(item.case_id),
    targetSkill: item.target_skill,
    state,
    label,
    activityState,
    activityLabel: null,
    summary,
  };
}

function renderRunCards(data, taskViews) {
  if (data.availability.live_sessions !== "available") {
    return `
      <section class="simple-section">
        <h2>Running now</h2>
        <p class="quiet-message">Live run status is not available for this campaign.</p>
      </section>`;
  }
  const trackedSessions = data.sessions.filter((session) => session.last_event_id);
  const activeSessions = trackedSessions.filter(isActive);
  const activeAttempts = data.live_attempts.filter(isActive);
  const staleCount = [...trackedSessions, ...data.live_attempts].filter(
    needsUpdate,
  ).length;
  if (!activeSessions.length && !activeAttempts.length) {
    return `
      <section class="simple-section">
        <h2>Running now</h2>
        <p class="quiet-message">Nothing is running right now.${staleCount ? ` ${escapeHtml(plural(staleCount, "previous run"))} ${escapeHtml(agrees(staleCount, "needs", "need"))} an update.` : ""}</p>
      </section>`;
  }
  const tasks = new Map(taskViews.map((item) => [item.caseId, item]));
  const cards = [
    ...activeSessions.map((session) => ({
      state: session.state,
      caseId: session.case_id,
      summary: session.summary,
      ageSeconds: session.age_seconds,
      href: `/campaign/${escapeHtml(data.campaign.campaign_id)}/session/${escapeHtml(session.session_id)}`,
    })),
    ...activeAttempts.map((attempt) => ({
      state: attempt.state,
      caseId: attempt.case_id,
      summary: null,
      ageSeconds: null,
      href: `/campaign/${escapeHtml(data.campaign.campaign_id)}/task/${escapeHtml(attempt.case_id)}`,
    })),
  ];
  return `
    <section class="simple-section">
      <div class="simple-section-heading">
        <h2>Running now</h2>
        <span>${escapeHtml(plural(cards.length, "run"))}</span>
      </div>
      <div class="run-list">
        ${cards
          .map((run) => {
            const task = tasks.get(run.caseId);
            const goal =
              run.summary ||
              (task
                ? `Test whether the current skill can complete ${task.title.toLowerCase()}.`
                : "Continue the current evaluation work.");
            return `
              <a class="run-card" href="${run.href}">
                <div>
                  <span class="plain-status status-${escapeHtml(run.state)}">${escapeHtml(sentenceCase(run.state))}</span>
                  <h3>${escapeHtml(task?.title || sentenceCase(run.caseId || "Unassigned work"))}</h3>
                  <p>${escapeHtml(goal)}</p>
                </div>
                ${run.ageSeconds === null ? "" : `<span class="run-age">Updated ${escapeHtml(formatNumber(run.ageSeconds, 0))}s ago</span>`}
              </a>`;
          })
          .join("")}
      </div>
    </section>`;
}

function renderSimpleExperiments(data) {
  const experiments = data.experiments;
  if (!experiments || experiments.status !== "available") {
    return "";
  }
  if (!experiments.items.length) {
    return experiments.attention.length
      ? `<section class="simple-section quiet-warning"><h2>Experiment records need attention</h2><p>${escapeHtml(experiments.attention.map((item) => item.summary).join(" "))}</p></section>`
      : "";
  }
  return `
    <section class="simple-section">
      <h2>Experiments</h2>
      <div class="experiment-list-simple">
        ${experiments.items
          .map(
            (experiment) => `
              <article>
                <div class="simple-section-heading">
                  <h3>${escapeHtml(experiment.title)}</h3>
                  <span>${escapeHtml(selectionLabel(experiment.selection))}</span>
                </div>
                <p>${escapeHtml(experiment.summary)}</p>
                <div class="experiment-goals">
                  ${experiment.treatments
                    .map(
                      (treatment) => `
                        <div>
                          <strong>${escapeHtml(sentenceCase(treatment.role || treatment.treatment_id))}</strong>
                          <span>${escapeHtml(treatment.hypothesis)}</span>
                          <small>${escapeHtml(`${treatment.terminal_repetitions} of ${treatment.planned_repetitions} runs complete; ${treatment.outcomes.PASS} passed, ${treatment.outcomes.FAIL} did not pass`)}</small>
                        </div>`,
                    )
                    .join("")}
                </div>
              </article>`,
          )
          .join("")}
      </div>
      ${
        experiments.attention.length
          ? `<p class="quiet-warning">${escapeHtml(plural(experiments.attention.length, "experiment issue"))} need review.</p>`
          : ""
      }
    </section>`;
}

function renderCampaign(data) {
  if (data.campaign.availability !== "available") {
    app.innerHTML = `
      <section class="page-heading simple-heading">
        <div>
          <h1>${escapeHtml(data.campaign.corpus_name)}</h1>
          <p>This campaign cannot be read right now.</p>
        </div>
        <a href="/unassigned">Unassigned evaluations</a>
      </section>
      <section class="error-state">
        <h2>Campaign data unavailable</h2>
        <p>${escapeHtml(sentenceCase(data.campaign.unavailable_reason || "The registered corpus could not be read"))}.</p>
      </section>`;
    return;
  }
  const totalSpend = observedTotal(data.populations, "observed_credits");
  const details = new Map(
    data.task_details.map((item) => [item.case_id, item]),
  );
  const tasks = data.cases.map((item) =>
    taskView(item, details.get(item.case_id)),
  );
  const passed = tasks.filter((item) => item.state === "passed").length;
  const active = tasks.filter((item) =>
    ["active", "blocked"].includes(item.activityState),
  ).length;
  const stale = tasks.filter((item) =>
    ["stale", "conflicted"].includes(item.activityState),
  ).length;
  const needsWork = tasks.length - passed;
  const skills = data.campaign.target_skills.join(", ");
  const activeText = [
    active ? `${plural(active, "task")} currently active.` : "Nothing is running right now.",
    stale ? `${plural(stale, "task")} ${agrees(stale, "needs", "need")} an update.` : "",
  ].filter(Boolean).join(" ");
  const resultText = passed
    ? `${plural(passed, "task")} passed so far.`
    : "No tasks have passed yet.";
  app.innerHTML = `
    <section class="page-heading simple-heading">
      <div>
        <h1>${escapeHtml(data.campaign.corpus_name)}</h1>
        <p>Standalone corpus testing <strong>${escapeHtml(skills || "the current skill set")}</strong> across ${escapeHtml(plural(tasks.length, "task"))}. Related retries and treatments are not grouped because this corpus has no project declaration.</p>
      </div>
      <a href="/unassigned">Unassigned evaluations</a>
    </section>
    <section class="campaign-brief">
      <div>
        <span class="brief-label">Goal</span>
        <h2>Get a passing evaluator result for every task.</h2>
        <p>Each task checks a real behavior. A task counts as passed only after the evaluator records a passing result.</p>
      </div>
      <div class="status-sentence">
        <strong>${escapeHtml(resultText)}</strong>
        <span>${escapeHtml(activeText)} ${escapeHtml(plural(needsWork, "task"))} still ${escapeHtml(agrees(needsWork, "needs", "need"))} a passing result.</span>
      </div>
    </section>
    <section class="simple-counts" aria-label="Campaign status">
      <div><strong>${escapeHtml(passed)}</strong><span>Passed</span></div>
      <div><strong>${escapeHtml(active)}</strong><span>Active or blocked</span></div>
      ${stale ? `<div><strong>${escapeHtml(stale)}</strong><span>Need an update</span></div>` : ""}
      <div><strong>${escapeHtml(needsWork)}</strong><span>Still need to pass</span></div>
      ${
        totalSpend.value === null
          ? ""
          : `<div><strong>${escapeHtml(formatNumber(totalSpend.value, 4))}</strong><span>Observed credits, shown as cents${totalSpend.known === totalSpend.total ? "" : `; partial ${totalSpend.known} of ${totalSpend.total}`}</span></div>`
      }
    </section>
    ${renderRunCards(data, tasks)}
    <section class="simple-section">
      <div class="simple-section-heading">
        <div>
          <h2>What is being tested</h2>
          <p>${escapeHtml(plural(tasks.length, "task"))} for ${escapeHtml(skills || "the current skill set")}. Open a task for its latest evidence.</p>
        </div>
        <span>${escapeHtml(`${passed} passed`)}</span>
      </div>
      <div class="task-list-simple">
        ${tasks
          .sort((left, right) => {
            const order = { blocked: 0, running: 1, stale: 2, failed: 3, waiting: 4, passed: 5 };
            return order[left.state] - order[right.state] || left.title.localeCompare(right.title);
          })
          .map(
            (task) => `
              <a href="/campaign/${escapeHtml(data.campaign.campaign_id)}/task/${escapeHtml(task.caseId)}">
                <span class="task-statuses">
                  <span class="plain-status status-${escapeHtml(task.state)}">${escapeHtml(task.label)}</span>
                  ${task.activityLabel ? `<span class="activity-status status-${escapeHtml(task.activityState)}">${escapeHtml(task.activityLabel)}</span>` : ""}
                </span>
                <div>
                  <h3>${escapeHtml(task.title)}</h3>
                  <p>${escapeHtml(task.summary)}</p>
                </div>
                <span class="task-skill">${escapeHtml(task.targetSkill)}</span>
              </a>`,
          )
          .join("")}
      </div>
    </section>
    ${renderSimpleExperiments(data)}
    `;
}

function renderProject(data) {
  const passing = data.tasks.filter((task) => task.result === "passing").length;
  const regressed = data.tasks.filter((task) => task.result === "regressed").length;
  const active = data.runs.filter((run) => run.state === "active").length;
  const hasRuns = data.runs.length > 0;
  const hasRevision = Boolean(data.selected_revision.snapshot_id);
  const hasConflicts = Object.values(data.conflicts).some(
    (items) => Array.isArray(items) ? items.length : Boolean(items),
  );
  app.innerHTML = `
    <section class="page-heading simple-heading">
      <div>
        <h1>${escapeHtml(data.project.title)}</h1>
        <p>${escapeHtml(data.project.goal)}</p>
      </div>
    </section>
    <section class="campaign-brief">
      <div>
        <span class="brief-label">${hasRevision ? "Current skill revision" : "Project status"}</span>
        <h2>${escapeHtml(hasRevision ? shortId(data.selected_revision.snapshot_id) : "Ready for first evaluation")}</h2>
        <p>${escapeHtml(hasRevision ? `Improving ${data.project.target_skills.join(", ")}. Results shown here use this exact revision.` : `Improving ${data.project.target_skills.join(", ")}. The exact revision appears when the first evaluation starts.`)}</p>
      </div>
      <div class="status-sentence">
        <strong>${escapeHtml(`${passing} of ${data.tasks.length} tasks passed`)}</strong>
        <span>${escapeHtml(hasRuns ? `${active} active runs${regressed ? `, ${regressed} regressed` : ""}` : "No evaluation runs yet")}</span>
      </div>
    </section>
    ${
      hasConflicts
        ? '<section class="quiet-warning">Conflicting project or ablation evidence is visible and excluded from totals.</section>'
        : ""
    }
    <section class="simple-section">
      <div class="simple-section-heading">
        <div><h2>Tasks</h2><p>What must pass, what is happening now, and the effort spent to get there.</p></div>
      </div>
      <div class="task-list-simple">
        ${data.tasks
          .map((task) => {
            const matchingRuns = taskRuns(task, data.runs);
            const hasTaskRuns = matchingRuns.length > 0;
            const resultState = task.result === "passing"
              ? "passed"
              : ["not_passing", "regressed"].includes(task.result)
                ? "failed"
                : "waiting";
            const resultLabel = hasTaskRuns
              ? sentenceCase(task.result)
              : "Not started";
            const phaseLabel = hasTaskRuns
              ? sentenceCase(task.phase.phase || task.phase.status)
              : null;
            return `
              <article>
                <span class="task-statuses">
                  <span class="plain-status status-${escapeHtml(resultState)}">${escapeHtml(resultLabel)}</span>
                  ${phaseLabel ? `<span class="activity-status status-${escapeHtml(task.phase.status === "conflicted" ? "conflicted" : task.phase.phase ? "active" : "waiting")}">${escapeHtml(phaseLabel)}</span>` : ""}
                </span>
                <div>
                  <h3>${escapeHtml(task.title)}</h3>
                  <p>${escapeHtml(task.summary)}</p>
                  ${taskProgressSummary(task)}
                  <p class="task-effort-copy">${escapeHtml(taskEffortSummary(task))}</p>
                  ${renderTaskAblation(task.ablation)}
                </div>
                <span class="task-skill">${escapeHtml(hasTaskRuns ? `${task.bindings.filter((binding) => binding.qualified).length}/${task.bindings.length} passed` : "Not evaluated")}</span>
                ${renderTaskRuns(task, matchingRuns)}
              </article>`;
          })
          .join("") || '<div class="panel-empty">Task totals are unavailable while project identity conflicts.</div>'}
      </div>
    </section>
    ${
      data.holdouts.length
        ? `<section class="simple-section">
            <div class="simple-section-heading"><div><h2>Generalization</h2><p>Authenticated aggregate holdout evidence only. Private cases and outputs never enter this page.</p></div></div>
            <div class="task-list-simple">
              ${data.holdouts.map((holdout) => `
                <article>
                  <span class="plain-status status-${escapeHtml(holdout.status === "completed" && holdout.qualification ? "passed" : holdout.status === "active" ? "running" : holdout.status === "invalid" ? "failed" : "waiting")}">${escapeHtml(sentenceCase(holdout.status))}</span>
                  <div><h3>${escapeHtml(holdout.summary)}</h3><p>${escapeHtml(holdout.status === "completed" ? `${holdout.aggregate.passed_cases} of ${holdout.aggregate.total_cases} aggregate checks passed` : holdout.status === "active" ? "Independent validation is running." : holdout.status === "invalid" ? "Holdout evidence failed closed." : "No authenticated holdout result yet.")}</p></div>
                  <span class="task-skill">${escapeHtml(holdout.qualification === true ? "Qualified" : holdout.qualification === false ? "Not qualified" : holdout.infrastructure_state)}</span>
                </article>`).join("")}
            </div>
          </section>`
        : ""
    }
    ${renderWholeSkillAblation(data.whole_skill_ablation)}
    ${
      data.pre_project_history.length
        ? `<section class="simple-section"><div class="simple-section-heading"><div><h2>Pre-project history</h2><p>Readable legacy attempts excluded from all project totals.</p></div></div><div class="panel-empty">${escapeHtml(plural(data.pre_project_history.length, "legacy attempt"))}</div></section>`
        : ""
    }`;
}

function snapshotSize(size) {
  return `${formatNumber(size.bytes, 0)} bytes · ${formatNumber(size.lines, 0)} lines · ${plural(size.files, "file")}`;
}

function reductionCopy(reduction) {
  if (!reduction) return "Qualification is still in progress.";
  const direction = reduction.bytes >= 0 ? "smaller" : "larger";
  return `${formatNumber(Math.abs(reduction.bytes), 0)} bytes (${formatNumber(Math.abs(reduction.percent), 1)}%) ${direction}`;
}

function renderTaskAblation(ablation) {
  if (!ablation) return "";
  const finalCopy = ablation.final
    ? `<p><strong>Final qualified:</strong> ${escapeHtml(snapshotSize(ablation.final))} · ${escapeHtml(reductionCopy(ablation.reduction.final))}</p>`
    : "";
  const restored = ablation.instruction_changes.restored
    .map((item) => `<li><strong>${escapeHtml(item.instruction_id)}</strong>: ${escapeHtml(item.reason)}</li>`)
    .join("");
  return `
    <div class="ablation-summary">
      <span class="brief-label">Delta ablation · ${escapeHtml(sentenceCase(ablation.status))}</span>
      <p><strong>Passing size:</strong> ${escapeHtml(snapshotSize(ablation.exploratory))}</p>
      <p><strong>Current candidate:</strong> ${escapeHtml(snapshotSize(ablation.current))} · ${escapeHtml(reductionCopy(ablation.reduction.current))}</p>
      ${finalCopy}
      <p><strong>Maintained wins:</strong> ${escapeHtml(`${ablation.maintained_wins.passed} passed · ${ablation.maintained_wins.failed} failed · ${ablation.maintained_wins.unavailable} unavailable`)}</p>
      <p>${escapeHtml(`${ablation.instruction_changes.removed} removed · ${ablation.instruction_changes.retained} retained · ${ablation.instruction_changes.restored.length} restored`)}</p>
      ${restored ? `<details><summary>Why rules were restored</summary><ul>${restored}</ul></details>` : ""}
    </div>`;
}

function renderWholeSkillAblation(ablation) {
  if (!ablation) return "";
  return `
    <section class="simple-section">
      <div class="simple-section-heading">
        <div><h2>Whole-skill ablation</h2><p>Shown only because a neutral, lean, and full comparison was explicitly declared.</p></div>
        <span>${escapeHtml(sentenceCase(ablation.status))}</span>
      </div>
      <div class="task-list-simple">
        ${ablation.arms.map((arm) => `
          <article>
            <span class="plain-status status-${escapeHtml(arm.selection_state === "selected" ? "passed" : arm.maintained_wins.failed ? "failed" : "waiting")}">${escapeHtml(sentenceCase(arm.arm))}</span>
            <div>
              <h3>${escapeHtml(snapshotSize(arm.size))}</h3>
              <p>${escapeHtml(`${arm.maintained_wins.passed} of ${arm.maintained_wins.total} maintained tasks passed${arm.retry_dependent ? " · retry dependent" : ""}`)}</p>
            </div>
            <span class="task-skill">${escapeHtml(arm.holdout_qualification === true ? "Holdout qualified" : arm.holdout_qualification === false ? "Holdout not qualified" : "Holdout unavailable")}</span>
          </article>`).join("")}
      </div>
    </section>`;
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
      <a href="/campaign/${escapeHtml(data.campaign.campaign_id)}">Campaign</a>
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
        <div><h2>Experiment attempts</h2><p>Only attempts for this exact frozen case revision are shown.</p></div>
        <span class="badge ${detail.experiment_attempts.length ? "available" : "unavailable"}">${escapeHtml(detail.experiment_attempts.length)}</span>
      </div>
      <div class="table-wrap">
        <table class="distributed-table">
          <thead><tr><th>Treatment</th><th>Execution</th><th>State</th><th>Transport</th><th>Stage</th><th>Evaluator</th><th>First outcome</th><th>Recovery / effective</th><th>Observation</th><th>Cost / source</th></tr></thead>
          <tbody>
            ${detail.experiment_attempts
              .map(
                (item) => `
                  <tr>
                    <td>${escapeHtml(item.treatment_id)}<span class="identity">repetition ${escapeHtml(item.repetition)}</span></td>
                    <td>${escapeHtml(item.model)}<span class="identity">${escapeHtml(item.platform)} | ${escapeHtml(item.route)}</span></td>
                    <td>${stateBadge(item.state)}</td>
                    <td>${escapeHtml(joinedValues(item.transport_statuses))}<span class="identity">${escapeHtml(joinedValues(item.transport_conclusions, "No conclusion"))}</span></td>
                    <td>${escapeHtml(item.stage_status || "Unavailable")}</td>
                    <td class="${item.evaluator_result ? `outcome-${escapeHtml(item.evaluator_result)}` : ""}">${escapeHtml(item.evaluator_result || "Unavailable")}</td>
                    <td><span class="identity mono">${escapeHtml(shortId(item.first_outcome_id))}</span></td>
                    <td>${escapeHtml(item.recovery_source_id || "None")}<span class="identity mono">${escapeHtml(shortId(item.effective_result_id))}</span></td>
                    <td>${escapeHtml(item.observed_as_of || "Not observed")}<span class="identity">${item.non_atomic ? "non-atomic snapshot" : "atomic or unavailable"}</span></td>
                    <td>${item.cost.complete ? escapeHtml(costLabel(item.cost)) : "Incomplete"}<span class="identity">${escapeHtml(joinedValues(item.source_ids, "No safe source ID"))}</span></td>
                  </tr>`,
              )
              .join("") || '<tr><td colspan="10">No experiment attempt matches this exact case revision.</td></tr>'}
          </tbody>
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
      <a href="/campaign/${escapeHtml(data.campaign.campaign_id)}">Campaign</a>
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

const REFRESH_INTERVAL_MS = 5000;
let refreshTimer = null;
let refreshInFlight = false;
let lastProjection = null;

function currentRoute() {
  const projectMatch = window.location.pathname.match(
    /^\/project\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})$/,
  );
  const sessionMatch = window.location.pathname.match(
    /^\/campaign\/([0-9a-f]{32})\/session\/([0-9a-f-]{36})$/,
  );
  const taskMatch = window.location.pathname.match(
    /^\/campaign\/([0-9a-f]{32})\/task\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})$/,
  );
  const match = window.location.pathname.match(/^\/campaign\/([0-9a-f]{32})$/);
  return {
    projectMatch,
    sessionMatch,
    taskMatch,
    match,
    path: projectMatch
      ? `/api/project/${projectMatch[1]}`
      : window.location.pathname === "/unassigned"
        ? "/api/unassigned"
      : sessionMatch
      ? `/api/campaign/${sessionMatch[1]}/session/${sessionMatch[2]}`
      : taskMatch
        ? `/api/campaign/${taskMatch[1]}`
      : match
        ? `/api/campaign/${match[1]}`
        : "/api/projects",
  };
}

function renderRoute(route, data) {
  if (route.projectMatch) renderProject(data);
  else if (window.location.pathname === "/unassigned") renderUnassigned(data);
  else if (route.sessionMatch) renderSession(data);
  else if (route.taskMatch) renderTask(data, route.taskMatch[2]);
  else if (route.match) renderCampaign(data);
  else renderIndex(data);
}

function scheduleRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = null;
  if (!document.hidden) {
    refreshTimer = setTimeout(() => refreshDashboard(false), REFRESH_INTERVAL_MS);
  }
}

async function refreshDashboard(initial) {
  if (refreshInFlight || document.hidden) {
    scheduleRefresh();
    return;
  }
  refreshInFlight = true;
  try {
    const route = currentRoute();
    const data = await loadJson(route.path);
    const projection = JSON.stringify(data);
    if (projection !== lastProjection) {
      renderRoute(route, data);
      lastProjection = projection;
    }
    serviceState.textContent = "Read only";
    serviceState.classList.remove("unavailable");
    serviceState.classList.add("available");
  } catch (error) {
    serviceState.textContent = "Update failed";
    serviceState.classList.remove("available");
    serviceState.classList.add("unavailable");
    if (initial) throw error;
  } finally {
    refreshInFlight = false;
    scheduleRefresh();
  }
}

async function start() {
  if (!capability) {
    throw new Error("Missing browser capability. Run the dashboard open command again.");
  }
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      clearTimeout(refreshTimer);
      refreshTimer = null;
    } else {
      refreshDashboard(false);
    }
  });
  await refreshDashboard(true);
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
