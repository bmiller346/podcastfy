const settingsForm = document.querySelector("#settings-form");
const settingsStatus = document.querySelector("#settings-status");
const taskForm = document.querySelector("#task-form");
const taskSelect = document.querySelector("#task-select");
const taskOutput = document.querySelector("#task-output");
const taskPreview = document.querySelector("#task-preview");
const diagnosticsSummary = document.querySelector("#diagnostics-summary");
const diagnosticsOutput = document.querySelector("#diagnostics-output");
const refreshDiagnosticsButton = document.querySelector("#refresh-diagnostics");
const copyDiagnosticsButton = document.querySelector("#copy-diagnostics");
const library = document.querySelector("#library");
const runTaskButton = document.querySelector("#run-task");
const refreshButton = document.querySelector("#refresh");

let latestSettings = null;
let latestTasks = null;
let latestLibrary = null;
let latestJob = null;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `Request failed: ${response.status}`);
  }
  return data;
}

function renderSettings(data) {
  latestSettings = data;
  const defaults = data.defaults || {};
  for (const [key, value] of Object.entries(defaults)) {
    const field = settingsForm.elements[key];
    if (field) field.value = value || "";
  }

  const providers = Object.entries(data.api_keys || {});
  settingsStatus.innerHTML = providers
    .map(([provider, info]) => {
      const source = info.env && info.file ? "file + env" : info.env ? "env" : info.file ? "file" : "unset";
      return `<div class="status-item"><strong>${provider}</strong>: ${source}</div>`;
    })
    .join("");
}

function renderTasks(data) {
  latestTasks = data;
  const tasks = data.tasks || [];
  taskSelect.innerHTML = tasks
    .map((task) => `<option value="${escapeHtml(task.path)}">${escapeHtml(task.name)}</option>`)
    .join("");
  if (!tasks.length) {
    taskSelect.innerHTML = `<option value="">No usage/litrpg*.json tasks found</option>`;
  }
}

function updateTaskPreview() {
  if (!taskForm || !taskPreview) return;
  taskPreview.textContent = JSON.stringify(buildTaskPayload(), null, 2);
  updateDiagnostics();
}

function renderLibrary(data) {
  latestLibrary = data;
  const series = data.library || [];
  if (!series.length) {
    library.innerHTML = `<p class="muted">No saved episodes found under data/litrpg.</p>`;
    return;
  }
  library.innerHTML = series
    .map((item) => {
      const episodes = (item.episodes || []).map(renderEpisode).join("");
      const count = `${item.episode_count || 0} episode${item.episode_count === 1 ? "" : "s"}`;
      const incomplete = item.incomplete_count
        ? `<span class="library-count warning">${item.incomplete_count} needs attention</span>`
        : "";
      return `<article class="series-block">
        <div class="series-header">
          <h3 class="series-title">${escapeHtml(item.title || item.series_id)}</h3>
          <div class="series-meta">
            <span class="library-count">${escapeHtml(count)}</span>
            ${incomplete}
          </div>
        </div>
        ${episodes || `<p class="muted">No episodes saved for this series yet.</p>`}
      </article>`;
    })
    .join("");
}

function renderEpisode(episode) {
  const number = episode.episode_number ? `Episode ${episode.episode_number}` : episode.episode_id;
  const prompt = episode.prompt ? `<div class="episode-prompt">${escapeHtml(episode.prompt)}</div>` : "";
  const qa = episode.qa || {};
  const qaText = qa.status && qa.status !== "unknown" ? qa.status : "not reviewed";
  const parts = episode.regenerable_parts || [];
  const audio = episode.audio
    ? `<audio controls preload="none" src="${escapeHtml(episode.audio.url)}"></audio>
       <div class="audio-meta">
         <span>${escapeHtml(episode.audio.format || "audio")}</span>
         <span>${formatBytes(episode.audio.bytes)}</span>
         <span>${escapeHtml(episode.audio.path)}</span>
       </div>`
    : `<div class="muted">No audio file saved for this episode.</div>`;
  return `<section class="episode">
    <div class="episode-heading">
      <div class="episode-title">${escapeHtml(number)}</div>
      <div class="badges">
        <span class="badge status-${escapeClass(episode.status || "unknown")}">${escapeHtml(episode.status || "unknown")}</span>
        <span class="badge">${escapeHtml(qaText)}</span>
      </div>
    </div>
    ${prompt}
    <div class="episode-path">${escapeHtml(episode.path || "")}</div>
    ${audio}
    <div class="muted">${parts.length} saved script part${parts.length === 1 ? "" : "s"}</div>
  </section>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeClass(value) {
  return String(value).replace(/[^a-z0-9_-]/gi, "-").toLowerCase();
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (!bytes) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function cleanValue(value) {
  return String(value || "").trim();
}

function maybeAssign(target, key, value) {
  if (value) {
    target[key] = value;
  }
}

function buildTaskPayload() {
  const formData = new FormData(taskForm);
  const mode = cleanValue(formData.get("mode")) || "episode";
  const task = {
    mode,
    series_id: cleanValue(formData.get("series_id")) || "local-series",
    premise: cleanValue(formData.get("premise")),
    render_audio: formData.get("render_audio") === "on",
    storage_dir: cleanValue(formData.get("storage_dir")) || "../data/litrpg",
  };

  maybeAssign(task, "result_path", cleanValue(formData.get("result_path")));
  maybeAssign(task, "checkpoint_dir", cleanValue(formData.get("checkpoint_dir")));

  const generation = {};
  maybeAssign(generation, "provider", cleanValue(formData.get("generation_provider")));
  maybeAssign(generation, "model", cleanValue(formData.get("generation_model")));
  if (Object.keys(generation).length) {
    task.generation = generation;
  }

  const tts = {};
  maybeAssign(tts, "provider", cleanValue(formData.get("tts_provider")));
  maybeAssign(tts, "model", cleanValue(formData.get("tts_model")));
  maybeAssign(tts, "format", cleanValue(formData.get("tts_format")));
  if (Object.keys(tts).length) {
    task.tts = tts;
  }

  return task;
}

async function pollJob(jobId) {
  while (true) {
    const data = await api(`/api/jobs/${jobId}`);
    const job = data.job || {};
    latestJob = job;
    updateDiagnostics();
    taskOutput.textContent = JSON.stringify(job, null, 2);
    if (job.status === "succeeded" || job.status === "failed") {
      return job;
    }
    await new Promise((resolve) => {
      window.setTimeout(resolve, 1200);
    });
  }
}

function buildDiagnosticsReport() {
  const task = buildTaskPayload();
  const premise = task.premise || "";
  const premiseAnalysis = analyzePremise(premise);
  const settings = summarizeSettings(latestSettings);
  const librarySummary = summarizeLibrary(latestLibrary);
  const job = latestJob ? summarizeJob(latestJob) : null;
  const recommendations = diagnosticRecommendations({
    task,
    premiseAnalysis,
    settings,
    librarySummary,
    job,
  });

  return {
    generated_at: new Date().toISOString(),
    task,
    premise_analysis: premiseAnalysis,
    settings,
    latest_job: job,
    library: librarySummary,
    recommendations,
  };
}

function updateDiagnostics() {
  if (!diagnosticsOutput || !diagnosticsSummary || !taskForm) return;
  const report = buildDiagnosticsReport();
  diagnosticsOutput.textContent = JSON.stringify(report, null, 2);
  diagnosticsSummary.innerHTML = renderDiagnosticsSummary(report);
}

function renderDiagnosticsSummary(report) {
  const readiness = report.recommendations.length ? "needs review" : "ready to test";
  const configured = Object.values(report.settings.api_keys || {}).filter(Boolean).length;
  const hooks = Object.entries(report.premise_analysis.hooks || {})
    .filter(([, present]) => present)
    .length;
  const audio = report.task.render_audio ? "audio on" : "audio off";
  return [
    diagnosticsItem("Readiness", readiness),
    diagnosticsItem("Premise hooks", `${hooks}/7`),
    diagnosticsItem("Configured keys", String(configured)),
    diagnosticsItem("Mode", report.task.mode || "episode"),
    diagnosticsItem("Audio", audio),
    diagnosticsItem("Library episodes", String(report.library.episode_count || 0)),
  ].join("");
}

function diagnosticsItem(label, value) {
  return `<div class="diagnostic-item"><strong>${escapeHtml(label)}</strong><span>${escapeHtml(value)}</span></div>`;
}

function analyzePremise(premise) {
  const lower = premise.toLowerCase();
  const words = premise.trim() ? premise.trim().split(/\s+/).length : 0;
  const hooks = {
    reluctant_protagonist: /\b(retired|leave me alone|alone|reluctant|exhausted|wants? .{0,20} alone|stop having tasks)\b/i.test(premise),
    chaos_partner: /\b(chaos|volatile|all-in|risk|odds|gambl|bet|wildcard)\b/i.test(premise),
    nonhuman_cast: /\b(macaw|familiar|pet|animal|bird|parrot|pedro)\b/i.test(premise),
    home_base: /\b(catamaran|boat|ship|home base|base|hull|rigging)\b/i.test(premise),
    mechanics: /\b(class|system|quest|xp|floor boss|stat|familiar|dungeon)\b/i.test(premise),
    setting_flavor: /\b(atlantic city|south jersey|pine barrens|philadelphia|union|boardwalk|marina|west berlin)\b/i.test(premise),
    problem_solving: /\b(carpentry|structural|repair|improvise|load-bearing|rigger|assessor|code)\b/i.test(premise),
  };
  const sensitive_terms = [];
  if (lower.includes("bipolar")) sensitive_terms.push("bipolar portrayal");
  if (lower.includes("mental")) sensitive_terms.push("mental health portrayal");
  const missing_hooks = Object.entries(hooks)
    .filter(([, present]) => !present)
    .map(([name]) => name);
  return {
    characters: findCharacterNames(premise),
    word_count: words,
    hooks,
    missing_hooks,
    sensitive_terms,
    strength: scorePremiseStrength(hooks, words),
  };
}

function findCharacterNames(premise) {
  const names = [];
  for (const name of ["Edward", "Kelli", "Pedro"]) {
    if (new RegExp(`\\b${name}\\b`, "i").test(premise)) {
      names.push(name);
    }
  }
  return names;
}

function scorePremiseStrength(hooks, words) {
  const hookCount = Object.values(hooks).filter(Boolean).length;
  if (hookCount >= 6 && words >= 80) return "strong";
  if (hookCount >= 4 && words >= 40) return "workable";
  return "thin";
}

function summarizeSettings(settings) {
  const apiKeys = {};
  for (const [provider, info] of Object.entries((settings && settings.api_keys) || {})) {
    apiKeys[provider] = Boolean(info.configured);
  }
  return {
    settings_path: settings ? settings.settings_path : "",
    api_keys: apiKeys,
    defaults: (settings && settings.defaults) || {},
  };
}

function summarizeLibrary(data) {
  const series = (data && data.library) || [];
  const episodeCount = series.reduce((total, item) => total + ((item.episodes || []).length), 0);
  const replayReady = series.reduce(
    (total, item) => total + (item.episodes || []).filter((episode) => episode.replay && episode.replay.available).length,
    0,
  );
  return {
    series_count: series.length,
    episode_count: episodeCount,
    replay_ready_count: replayReady,
  };
}

function summarizeJob(job) {
  return {
    job_id: job.job_id,
    status: job.status,
    phase: job.phase,
    task_summary: job.task_summary,
    result: job.result,
    error: job.error,
    checkpoint_paths: job.checkpoint_paths || [],
  };
}

function diagnosticRecommendations({ task, premiseAnalysis, settings, job }) {
  const recommendations = [];
  if (!task.premise) {
    recommendations.push("Add a premise before queueing generation.");
  }
  if (premiseAnalysis.strength === "thin") {
    recommendations.push("Premise looks thin; add character tension, mechanics, setting flavor, or a concrete first boss problem.");
  }
  if (premiseAnalysis.missing_hooks.length) {
    recommendations.push(`Missing premise hooks: ${premiseAnalysis.missing_hooks.join(", ")}.`);
  }
  if (premiseAnalysis.sensitive_terms.length) {
    recommendations.push(`Sensitive material detected (${premiseAnalysis.sensitive_terms.join(", ")}); keep the character specific, agentic, and non-caricatured.`);
  }
  const generationProvider = (task.generation && task.generation.provider) || settings.defaults.default_generation_provider || "openai";
  if (generationProvider === "openai" && !settings.api_keys.openai) {
    recommendations.push("OpenAI generation is selected but no OpenAI API key is configured.");
  }
  const ttsProvider = (task.tts && task.tts.provider) || settings.defaults.default_tts_provider || "";
  if (task.render_audio && ttsProvider && !settings.api_keys[ttsProvider]) {
    recommendations.push(`${ttsProvider} TTS is selected but no ${ttsProvider} API key is configured.`);
  }
  if (task.render_audio) {
    recommendations.push("For first story tests, consider turning audio off until QA/checkpoints look good.");
  }
  if (job && job.error) {
    recommendations.push(`Latest job failed: ${job.error}`);
  }
  return recommendations;
}

async function copyDiagnostics() {
  const text = diagnosticsOutput ? diagnosticsOutput.textContent : "";
  if (!text) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(text);
    taskOutput.textContent = "Diagnostics copied.";
    return;
  }
  taskOutput.textContent = text;
}

async function refreshAll() {
  const [settings, tasks, episodes] = await Promise.all([
    api("/api/settings"),
    api("/api/tasks"),
    api("/api/library"),
  ]);
  renderSettings(settings);
  renderTasks(tasks);
  renderLibrary(episodes);
}

settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(settingsForm);
  const payload = Object.fromEntries(formData.entries());
  try {
    renderSettings(await api("/api/settings", { method: "POST", body: JSON.stringify(payload) }));
    taskOutput.textContent = "Settings saved.";
    for (const field of settingsForm.querySelectorAll('input[type="password"]')) field.value = "";
  } catch (error) {
    taskOutput.textContent = error.message;
  }
});

taskForm.addEventListener("input", () => {
  updateTaskPreview();
});

taskForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = buildTaskPayload();
  const submitButton = document.querySelector("#submit-task");
  submitButton.disabled = true;
  taskOutput.textContent = "Queueing generation...";
  try {
    const response = await api("/api/jobs", {
      method: "POST",
      body: JSON.stringify({ task: payload }),
    });
    const job = await pollJob(response.job.job_id);
    latestJob = job;
    updateDiagnostics();
    taskOutput.textContent = JSON.stringify(job, null, 2);
    await refreshAll();
  } catch (error) {
    taskOutput.textContent = error.message;
  } finally {
    submitButton.disabled = false;
  }
});

runTaskButton.addEventListener("click", async () => {
  const path = taskSelect.value;
  if (!path) return;
  runTaskButton.disabled = true;
  taskOutput.textContent = "Running task...";
  try {
    const result = await api("/api/run-task", { method: "POST", body: JSON.stringify({ path }) });
    taskOutput.textContent = JSON.stringify(result.result, null, 2);
    await refreshAll();
  } catch (error) {
    taskOutput.textContent = error.message;
  } finally {
    runTaskButton.disabled = false;
  }
});

refreshButton.addEventListener("click", () => {
  refreshAll().catch((error) => {
    taskOutput.textContent = error.message;
  });
});

refreshDiagnosticsButton.addEventListener("click", () => {
  updateDiagnostics();
});

copyDiagnosticsButton.addEventListener("click", () => {
  copyDiagnostics().catch((error) => {
    taskOutput.textContent = error.message;
  });
});

refreshAll().catch((error) => {
  taskOutput.textContent = error.message;
});

updateTaskPreview();
updateDiagnostics();
