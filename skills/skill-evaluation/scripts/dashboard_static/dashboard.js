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
  app.innerHTML = `
    <section class="page-heading">
      <div>
        <h1>Evaluation campaigns</h1>
        <p>Completed evaluator artifacts remain authoritative. Live work arrives in the next foundation slice.</p>
      </div>
    </section>
    <section class="metrics">
      ${metric("Registered campaigns", formatNumber(data.campaigns.length, 0), "Local corpus registrations")}
      ${metric("Available", formatNumber(available, 0), "Corpus identity verified")}
      ${metric("Live sessions", "Unavailable", "Not part of this slice")}
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
                    <span>${escapeHtml(campaign.target_skills.join(", ") || "No target skills")} | ${escapeHtml(campaign.availability)}</span>
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

function renderCampaign(data) {
  const totalSpend = observedTotal(data.populations, "observed_credits");
  const premium = observedTotal(
    data.populations,
    "observed_premium_requests",
  );
  const passes = data.attempts.filter(
    (attempt) => attempt.correctness === "PASS",
  ).length;
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
      ${metric("Observed credits", formatNumber(totalSpend.value, 4), totalSpend.value === null ? observedDetail(totalSpend, "credit") : `${formatNumber(totalSpend.value, 4)} cents by user convention | ${observedDetail(totalSpend, "credit")}`)}
      ${metric("Premium requests", formatNumber(premium.value, 4), `Separate evaluator-native unit | ${observedDetail(premium, "premium request")}`)}
    </section>
    <section class="panel">
      <div class="panel-header">
        <div><h2>Task status</h2><p>Outcomes stay distinct. Unknown and not-run states are never zero.</p></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Task</th><th>Skill</th><th>Type</th><th>Status</th><th>Authority</th></tr></thead>
          <tbody>
            ${data.cases
              .map(
                (item) => `
                  <tr>
                    <td><strong>${escapeHtml(item.case_id)}</strong></td>
                    <td>${escapeHtml(item.target_skill)}</td>
                    <td>${escapeHtml(item.case_type)}</td>
                    <td>${escapeHtml(outcomeSummary(item.outcomes))}</td>
                    <td><span class="identity">${escapeHtml(item.source.id)}</span></td>
                  </tr>`,
              )
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

async function start() {
  if (!capability) {
    throw new Error("Missing browser capability. Run the dashboard open command again.");
  }
  const match = window.location.pathname.match(/^\/campaign\/([0-9a-f]{32})$/);
  const data = await loadJson(
    match ? `/api/campaign/${match[1]}` : "/api/index",
  );
  serviceState.textContent = "Read only";
  serviceState.classList.add("available");
  if (match) renderCampaign(data);
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
