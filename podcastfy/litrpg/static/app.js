const settingsForm = document.querySelector("#settings-form");
const settingsStatus = document.querySelector("#settings-status");
const taskForm = document.querySelector("#task-form");
const taskSelect = document.querySelector("#task-select");
const taskOutput = document.querySelector("#task-output");
const taskPreview = document.querySelector("#task-preview");
const activeSeriesInput = document.querySelector("#active-series-id");
const seriesSelect = document.querySelector("#series-select");
const seriesStatus = document.querySelector("#series-status");
const useTaskSeriesButton = document.querySelector("#use-task-series");
const loadActiveSeriesButton = document.querySelector("#load-active-series");
const newSeriesPackageButton = document.querySelector("#new-series-package");
const packageForm = document.querySelector("#package-form");
const packageStatus = document.querySelector("#package-status");
const packageSummary = document.querySelector("#package-summary");
const packageOutput = document.querySelector("#package-output");
const roleList = document.querySelector("#role-list");
const loadPackageButton = document.querySelector("#load-package");
const savePackageButton = document.querySelector("#save-package");
const generatePackageButton = document.querySelector("#generate-package");
const copyPackageButton = document.querySelector("#copy-package");
const addRoleButton = document.querySelector("#add-role");
const rebuildRolesButton = document.querySelector("#rebuild-roles");
const saveRolesButton = document.querySelector("#save-roles");
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
let latestPackage = null;
let activeSeriesId = "";
let lastSyncedPackageSeriesId = "";

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
    taskSelect.innerHTML = `<option value="">No task JSON files found</option>`;
  }
}

function updateTaskPreview({ syncSeries = false } = {}) {
  if (!taskForm || !taskPreview) return;
  syncSeriesFromTask({ force: syncSeries });
  taskPreview.textContent = JSON.stringify(buildTaskPayload(), null, 2);
  renderSeriesWorkspace();
  updateDiagnostics();
}

function syncSeriesFromTask({ force = false } = {}) {
  const seriesId = cleanValue(taskForm.elements.series_id && taskForm.elements.series_id.value) || "local-series";
  if (!activeSeriesId || force || activeSeriesId === "local-series") {
    setActiveSeriesId(seriesId, { syncTask: false, syncPackage: true });
    return;
  }
  syncPackageSeriesId();
}

function syncPackageSeriesId({ force = false } = {}) {
  if (!packageForm || !taskForm) return;
  const packageField = packageForm.elements.package_series_id;
  if (!packageField) return;
  const seriesId = currentSeriesId();
  const current = cleanValue(packageField.value);
  if (!force && current && current !== lastSyncedPackageSeriesId) return;
  packageField.value = seriesId;
  lastSyncedPackageSeriesId = seriesId;
}

function currentSeriesId() {
  return cleanValue(activeSeriesId)
    || cleanValue(activeSeriesInput && activeSeriesInput.value)
    || cleanValue(taskForm.elements.series_id && taskForm.elements.series_id.value)
    || "local-series";
}

function setActiveSeriesId(seriesId, { syncTask = true, syncPackage = true } = {}) {
  const cleanSeries = cleanValue(seriesId) || "local-series";
  activeSeriesId = cleanSeries;
  if (activeSeriesInput) activeSeriesInput.value = cleanSeries;
  if (syncTask && taskForm && taskForm.elements.series_id) {
    taskForm.elements.series_id.value = cleanSeries;
  }
  if (syncPackage) syncPackageSeriesId({ force: true });
  if (seriesSelect && [...seriesSelect.options].some((option) => option.value === cleanSeries)) {
    seriesSelect.value = cleanSeries;
  }
  renderSeriesWorkspace();
}

function renderLibrary(data) {
  latestLibrary = data;
  renderSeriesWorkspace();
  const series = data.library || [];
  if (!series.length) {
    library.innerHTML = `<p class="muted">No saved episodes found in local story storage.</p>`;
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

function renderSeriesWorkspace() {
  if (!seriesStatus) return;
  const librarySeries = (latestLibrary && latestLibrary.library) || [];
  const selectedSeries = currentSeriesId();
  if (seriesSelect) {
    const sortedSeries = [...librarySeries]
      .sort((a, b) => String(a.series_id).localeCompare(String(b.series_id)))
      .filter((item) => cleanValue(item.series_id));
    const knownSeries = new Set(sortedSeries.map((item) => String(item.series_id)));
    const options = sortedSeries
      .map((item) => {
        const id = String(item.series_id || "");
        const title = item.title && item.title !== id ? ` - ${item.title}` : "";
        return `<option value="${escapeHtml(id)}">${escapeHtml(id + title)}</option>`;
      });
    if (!knownSeries.has(selectedSeries)) {
      options.unshift(`<option value="${escapeHtml(selectedSeries)}">${escapeHtml(selectedSeries)} - current draft</option>`);
    }
    seriesSelect.innerHTML = options.join("") || `<option value="${escapeHtml(selectedSeries)}">${escapeHtml(selectedSeries)}</option>`;
    seriesSelect.value = selectedSeries;
  }

  const libraryItem = librarySeries.find((item) => String(item.series_id) === selectedSeries);
  const packageInfo = summarizeSeriesPackage(latestPackage);
  const selectedPackage = latestPackage && latestPackage.series_id === selectedSeries ? packageInfo : null;
  const packageState = selectedPackage && selectedPackage.available ? "ready" : "missing";
  const roleCount = selectedPackage ? selectedPackage.role_count : 0;
  const bestiaryCount = selectedPackage ? selectedPackage.bestiary_count : 0;
  const encounterCount = selectedPackage ? selectedPackage.encounter_count : 0;
  seriesStatus.innerHTML = [
    diagnosticsItem("Active series", selectedSeries),
    diagnosticsItem("Package", packageState),
    diagnosticsItem("Episodes", String((libraryItem && libraryItem.episode_count) || 0)),
    diagnosticsItem("Roles", String(roleCount)),
    diagnosticsItem("Bestiary", String(bestiaryCount)),
    diagnosticsItem("Encounters", String(encounterCount)),
  ].join("");
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

  maybeAssign(task, "genre", cleanValue(formData.get("genre")));
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

function packageSeriesId() {
  if (!packageForm) return currentSeriesId();
  const formData = new FormData(packageForm);
  return cleanValue(formData.get("package_series_id")) || currentSeriesId();
}

function baselinePackageText() {
  if (!packageForm) return "";
  const formData = new FormData(packageForm);
  return cleanValue(formData.get("baseline_text"));
}

function buildPackageDraft() {
  const task = buildTaskPayload();
  const seriesId = packageSeriesId();
  return {
    schema_version: "ui-draft-v1",
    series_id: seriesId,
    metadata: {
      source: "ui",
      genre: task.genre || "",
      updated_at: new Date().toISOString(),
    },
    premise: task.premise || "",
    baseline_text: baselinePackageText(),
    system_announcer: {},
    characters: [],
    familiar: {},
    home_base: {},
    floor_rules: {},
    faction_map: {},
    bestiary: [],
    encounters: [],
  };
}

function renderSeriesPackage(data) {
  latestPackage = data;
  if (!packageStatus || !packageSummary || !packageOutput) return;
  const modules = data.modules || {};
  const packageState = data.available ? data.status || "ready" : data.status || "missing";
  packageStatus.innerHTML = [
    statusItem("Package", packageState),
    statusItem("Storage helpers", modules.packages ? "available" : "fallback"),
    statusItem("Generator", modules.generator ? "available" : "unavailable"),
    statusItem("Path", data.path || ""),
  ].join("");
  packageSummary.textContent = data.summary || "No saved package summary yet.";
  packageOutput.textContent = JSON.stringify(data.package || {}, null, 2);
  renderRoleEditor(data.package || buildPackageDraft());
  updateDiagnostics();
}

function renderRoleEditor(packageValue) {
  if (!roleList) return;
  const roles = roleArrayFromPackage(packageValue);
  if (!roles.length) {
    roleList.innerHTML = `<div class="muted">No roles yet. Add one manually or generate a package from your premise.</div>`;
    return;
  }
  roleList.innerHTML = roles.map((role, index) => renderRoleCard(role, index)).join("");
}

function renderRoleCard(role, index) {
  return `<article class="role-card" data-role-index="${index}">
    <div class="role-card-header">
      <strong>${escapeHtml(role.name || role.role || role.role_id || `Role ${index + 1}`)}</strong>
      <button class="remove-role" type="button" data-role-index="${index}">Remove</button>
    </div>
    <div class="role-grid">
      ${roleField(index, "name", "Name", role.name)}
      ${roleField(index, "role", "Role tag", role.role || role.role_id)}
      ${roleField(index, "character_class", "Class", role.character_class || role.class_candidate)}
      ${roleField(index, "voice", "Voice", roleScalarValue(role.voice || role.voice_profile))}
      ${roleTextarea(index, "personality", "Personality", role.personality)}
      ${roleTextarea(index, "arc", "Arc", role.arc)}
      ${roleTextarea(index, "rules", "Rules", listToText(role.rules || role.avoid || role.portrayal_guardrails))}
      ${roleTextarea(index, "sample_lines", "Sample lines", listToText(role.sample_lines))}
      ${roleTextarea(index, "relationships", "Relationships", listToText(role.relationships))}
      ${roleTextarea(index, "notes", "Notes", listToText(role.notes || role.audio_notes))}
    </div>
  </article>`;
}

function roleField(index, name, label, value) {
  return `<label>
    ${escapeHtml(label)}
    <input data-role-index="${index}" data-role-field="${escapeHtml(name)}" type="text" value="${escapeHtml(value || "")}">
  </label>`;
}

function roleTextarea(index, name, label, value) {
  return `<label class="wide">
    ${escapeHtml(label)}
    <textarea data-role-index="${index}" data-role-field="${escapeHtml(name)}" rows="3">${escapeHtml(value || "")}</textarea>
  </label>`;
}

function roleArrayFromPackage(packageValue) {
  const characters = packageValue && packageValue.characters;
  if (Array.isArray(characters)) {
    return characters.map((item) => ({ ...(item || {}) }));
  }
  if (characters && typeof characters === "object") {
    return Object.entries(characters).map(([key, value]) => {
      const role = value && typeof value === "object" ? { ...value } : {};
      if (!role.name) role.name = key;
      return role;
    });
  }
  return [];
}

function packageFromRoleEditor(basePackage) {
  const packageValue = basePackage && typeof basePackage === "object" ? { ...basePackage } : buildPackageDraft();
  packageValue.series_id = packageSeriesId();
  packageValue.premise = packageValue.premise || buildTaskPayload().premise || "";
  packageValue.baseline_text = baselinePackageText() || packageValue.baseline_text || "";
  packageValue.metadata = {
    ...(packageValue.metadata || {}),
    genre: buildTaskPayload().genre || (packageValue.metadata && packageValue.metadata.genre) || "",
  };
  packageValue.characters = readRolesFromEditor();
  return packageValue;
}

function readRolesFromEditor() {
  if (!roleList) return [];
  const originalRoles = roleArrayFromPackage(currentPackageJson());
  const cards = [...roleList.querySelectorAll(".role-card")];
  return cards
    .map((card, index) => {
      const role = { ...(originalRoles[index] || {}) };
      for (const field of card.querySelectorAll("[data-role-field]")) {
        const name = field.getAttribute("data-role-field");
        const value = cleanValue(field.value);
        if (!value) {
          delete role[name];
          continue;
        }
        if (["rules", "sample_lines", "relationships", "notes"].includes(name)) {
          role[name] = textToList(value);
        } else if (name === "voice" && role.voice && typeof role.voice === "object") {
          role.voice = { ...role.voice, delivery: value };
        } else {
          role[name] = value;
        }
      }
      return role;
    })
    .filter((role) => role.name || role.role);
}

function addRole(initial = {}) {
  const current = packageFromRoleEditor(currentPackageJson()).characters || [];
  current.push({
    role: initial.role || `SUPPORT_${current.length + 1}`,
    name: initial.name || "",
    character_class: initial.character_class || "",
    voice: initial.voice || "",
    personality: initial.personality || "",
    arc: initial.arc || "",
    rules: initial.rules || [],
    sample_lines: initial.sample_lines || [],
    relationships: initial.relationships || [],
    notes: initial.notes || [],
  });
  const packageValue = currentPackageJson() || buildPackageDraft();
  packageValue.characters = current;
  renderRoleEditor(packageValue);
  syncPackageOutputFromRoleEditor();
}

function removeRole(index) {
  const packageValue = packageFromRoleEditor(currentPackageJson());
  packageValue.characters.splice(index, 1);
  renderRoleEditor(packageValue);
  packageOutput.textContent = JSON.stringify(packageValue, null, 2);
  latestPackage = { ...(latestPackage || {}), package: packageValue, available: true };
  updateDiagnostics();
}

function currentPackageJson() {
  const currentText = packageOutput ? cleanValue(packageOutput.textContent) : "";
  if (!currentText || currentText === "{}") return buildPackageDraft();
  try {
    const parsed = JSON.parse(currentText);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
  } catch (_error) {
    return buildPackageDraft();
  }
  return buildPackageDraft();
}

function syncPackageOutputFromRoleEditor() {
  if (!packageOutput) return;
  const packageValue = packageFromRoleEditor(currentPackageJson());
  packageOutput.textContent = JSON.stringify(packageValue, null, 2);
  latestPackage = { ...(latestPackage || {}), package: packageValue, available: true };
  updateDiagnostics();
}

function listToText(value) {
  if (Array.isArray(value)) return value.join("\n");
  return value || "";
}

function roleScalarValue(value) {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (typeof value !== "object") return String(value);
  return [
    value.voice,
    value.archetype,
    value.delivery,
    value.tone,
    value.accent,
    value.pacing,
  ]
    .map((item) => cleanValue(item))
    .filter(Boolean)
    .join("; ");
}

function textToList(value) {
  return cleanValue(value)
    .split(/\r?\n/)
    .map((line) => line.trim().replace(/^[-*]\s*/, ""))
    .filter(Boolean);
}

function statusItem(label, value) {
  return `<div class="status-item"><strong>${escapeHtml(label)}</strong>: ${escapeHtml(value)}</div>`;
}

async function loadSeriesPackage() {
  syncPackageSeriesId({ force: true });
  const seriesId = packageSeriesId();
  const data = await api(`/api/series-package?series_id=${encodeURIComponent(seriesId)}`);
  renderSeriesPackage(data);
  return data;
}

async function saveSeriesPackage() {
  syncPackageSeriesId({ force: true });
  const seriesId = packageSeriesId();
  const packageValue = packageFromRoleEditor(currentPackageJson());
  const data = await api("/api/series-package", {
    method: "POST",
    body: JSON.stringify({
      series_id: seriesId,
      premise: buildTaskPayload().premise || "",
      baseline_text: baselinePackageText(),
      package: packageValue,
    }),
  });
  renderSeriesPackage(data);
  return data;
}

async function generateSeriesPackage() {
  const data = await api("/api/series-package/generate", {
    method: "POST",
    body: JSON.stringify({
      series_id: packageSeriesId(),
      premise: buildTaskPayload().premise || "",
      genre: buildTaskPayload().genre || "",
      baseline_text: baselinePackageText(),
      save: true,
    }),
  });
  renderSeriesPackage(data);
  return data;
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
  const premiseAnalysis = analyzePremise(premise, task.genre || "");
  const settings = summarizeSettings(latestSettings);
  const librarySummary = summarizeLibrary(latestLibrary);
  const seriesPackage = summarizeSeriesPackage(latestPackage);
  const job = latestJob ? summarizeJob(latestJob) : null;
  const recommendations = diagnosticRecommendations({
    task,
    premiseAnalysis,
    settings,
    librarySummary,
    seriesPackage,
    job,
  });

  return {
    generated_at: new Date().toISOString(),
    active_series_id: currentSeriesId(),
    task,
    premise_analysis: premiseAnalysis,
    settings,
    series_package: seriesPackage,
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
  const hookTotal = Object.keys(report.premise_analysis.hooks || {}).length || 0;
  const audio = report.task.render_audio ? "audio on" : "audio off";
  const packageState = report.series_package.available ? "ready" : "missing";
  return [
    diagnosticsItem("Active series", report.active_series_id || "local-series"),
    diagnosticsItem("Readiness", readiness),
    diagnosticsItem("Premise hooks", `${hooks}/${hookTotal}`),
    diagnosticsItem("Series package", packageState),
    diagnosticsItem("Genre", report.series_package.genre || report.task.genre || "unspecified"),
    diagnosticsItem("Role packages", String(report.series_package.role_count || 0)),
    diagnosticsItem("Bestiary", String(report.series_package.bestiary_count || 0)),
    diagnosticsItem("Encounters", String(report.series_package.encounter_count || 0)),
    diagnosticsItem("Configured keys", String(configured)),
    diagnosticsItem("Mode", report.task.mode || "episode"),
    diagnosticsItem("Audio", audio),
    diagnosticsItem("Library episodes", String(report.library.episode_count || 0)),
  ].join("");
}

function diagnosticsItem(label, value) {
  return `<div class="diagnostic-item"><strong>${escapeHtml(label)}</strong><span>${escapeHtml(value)}</span></div>`;
}

function analyzePremise(premise, genre = "") {
  const lower = premise.toLowerCase();
  const genreText = genre.toLowerCase();
  const words = premise.trim() ? premise.trim().split(/\s+/).length : 0;
  const isLitrpg = /\b(litrpg|dungeon|system|xp|quest|stats?)\b/i.test(`${genre} ${premise}`);
  const hooks = isLitrpg
    ? {
        reluctant_protagonist: /\b(retired|leave me alone|alone|reluctant|exhausted|wants? .{0,20} alone|stop having tasks)\b/i.test(premise),
        chaos_partner: /\b(chaos|volatile|all-in|risk|odds|gambl|bet|wildcard)\b/i.test(premise),
        nonhuman_cast: /\b(macaw|familiar|pet|animal|bird|parrot|pedro)\b/i.test(premise),
        home_base: /\b(catamaran|boat|ship|home base|base|hull|rigging)\b/i.test(premise),
        mechanics: /\b(class|system|quest|xp|floor boss|stat|familiar|dungeon)\b/i.test(premise),
        setting_flavor: /\b(atlantic city|south jersey|pine barrens|philadelphia|union|boardwalk|marina|west berlin)\b/i.test(premise),
        problem_solving: /\b(carpentry|structural|repair|improvise|load-bearing|rigger|assessor|code)\b/i.test(premise),
      }
    : {
        clear_protagonist: /\b(who|protagonist|hero|lead|detective|captain|clerk|retired|sold|discovers?)\b/i.test(premise),
        concrete_setting: /\b(city|town|station|ship|marina|office|school|house|island|planet|kingdom|hotel|road)\b/i.test(premise),
        central_conflict: /\b(must|wants?|needs?|against|discovers?|trapped|haunted|missing|murder|war|secret|threat)\b/i.test(premise),
        relationship_pressure: /\b(family|partner|crew|friend|rival|enemy|marriage|kids|team|neighbor)\b/i.test(premise),
        tonal_identity: /\b(comedy|dark|cozy|romantic|grim|absurd|satire|horror|mystery|thriller|hopeful)\b/i.test(`${genre} ${premise}`),
        audio_cast_potential: /\b(announcer|host|narrator|voice|cast|interview|podcast|radio|trial|council|crew)\b/i.test(premise),
        serial_engine: /\b(book|chapter|episode|season|case|floor|mission|arc|quest|investigation|journey)\b/i.test(premise),
      };
  const sensitive_terms = [];
  if (lower.includes("bipolar")) sensitive_terms.push("bipolar portrayal");
  if (lower.includes("mental")) sensitive_terms.push("mental health portrayal");
  const missing_hooks = Object.entries(hooks)
    .filter(([, present]) => !present)
    .map(([name]) => name);
  return {
    characters: findCharacterNames(premise),
    genre: genre || (genreText.includes("litrpg") ? "LitRPG" : ""),
    analysis_mode: isLitrpg ? "litrpg" : "general_story",
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

function summarizeSeriesPackage(data) {
  const modules = (data && data.modules) || {};
  const packageValue = data && data.package && typeof data.package === "object" ? data.package : {};
  const metadata = packageValue.metadata && typeof packageValue.metadata === "object" ? packageValue.metadata : {};
  const roles = roleArrayFromPackage(packageValue).map((role) => ({
    role: role.role || role.role_id || "",
    name: role.name || "",
    class: role.character_class || role.class_candidate || role.class_or_mechanic || "",
    voice: roleScalarValue(role.voice || role.voice_profile),
  }));
  const bestiary = packageArray(packageValue.bestiary || packageValue.world_entities || packageValue.entities || packageValue.monsters || packageValue.mobs)
    .map((entry) => ({
      name: entry.name || "",
      type: entry.entity_type || entry.type || entry.kind || "",
      recurrence: entry.recurrence || "",
      weaknesses: Array.isArray(entry.weaknesses) ? entry.weaknesses : [],
    }));
  const encounters = packageArray(packageValue.encounters || packageValue.encounter_registry || packageValue.bosses)
    .map((entry) => ({
      name: entry.name || "",
      type: entry.encounter_type || entry.type || entry.kind || "",
      status: entry.status || "",
      location: entry.location || entry.arena || "",
    }));
  return {
    series_id: data ? data.series_id : "",
    available: Boolean(data && data.available),
    status: data ? data.status : "unknown",
    path: data ? data.path : "",
    genre: metadata.genre || metadata.style || "",
    role_count: roles.length,
    roles,
    bestiary_count: bestiary.length,
    bestiary,
    encounter_count: encounters.length,
    encounters,
    has_system_announcer: Boolean(packageValue.system_announcer && Object.keys(packageValue.system_announcer).length),
    has_familiar: Boolean(packageValue.familiar && Object.keys(packageValue.familiar).length),
    package_keys: Object.keys(packageValue),
    modules: {
      packages: Boolean(modules.packages),
      generator: Boolean(modules.generator),
    },
    summary: data ? data.summary || "" : "",
  };
}

function packageArray(value) {
  if (Array.isArray(value)) {
    return value.filter((item) => item && typeof item === "object");
  }
  if (value && typeof value === "object") {
    return Object.entries(value).map(([key, item]) => {
      const entry = item && typeof item === "object" ? { ...item } : {};
      if (!entry.name) entry.name = key;
      return entry;
    });
  }
  return [];
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

function diagnosticRecommendations({ task, premiseAnalysis, settings, seriesPackage, job }) {
  const recommendations = [];
  if (!task.premise) {
    recommendations.push("Add a premise before queueing generation.");
  }
  if (premiseAnalysis.strength === "thin") {
    if (premiseAnalysis.analysis_mode === "litrpg") {
      recommendations.push("Premise looks thin; add character tension, mechanics, setting flavor, or a concrete first boss problem.");
    } else {
      recommendations.push("Premise looks thin; add a clear lead, setting, conflict, relationship pressure, and a repeatable story engine.");
    }
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
  if (!seriesPackage.available) {
    recommendations.push("No series package is loaded yet; create or save a package before serious chapter tests.");
  }
  if (seriesPackage.available && !seriesPackage.role_count) {
    recommendations.push("Series package has no editable role packages yet; add cast roles or generate a first draft.");
  }
  if (seriesPackage.available && !seriesPackage.bestiary_count && !seriesPackage.encounter_count) {
    recommendations.push("Series package has no bestiary or encounter entries yet; add reusable threats, suspects, hazards, or setpieces before long-form tests.");
  }
  if (!seriesPackage.modules.generator) {
    recommendations.push("Series package generator is unavailable; save a draft package or wait for the generator lane.");
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

async function copyPackageJson() {
  const text = packageOutput ? packageOutput.textContent : "";
  if (!text) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(text);
    taskOutput.textContent = "Package JSON copied.";
    return;
  }
  taskOutput.textContent = text;
}

async function refreshAll() {
  syncSeriesFromTask({ force: !activeSeriesId });
  const [settings, tasks, episodes] = await Promise.all([
    api("/api/settings"),
    api("/api/tasks"),
    api("/api/library"),
  ]);
  renderSettings(settings);
  renderTasks(tasks);
  renderLibrary(episodes);
  if (packageForm) {
    syncPackageSeriesId({ force: true });
    await loadSeriesPackage().catch((error) => {
      renderSeriesPackage({
        ok: false,
        series_id: currentSeriesId(),
        available: false,
        status: "unavailable",
        error: error.message,
        modules: {},
      });
    });
  }
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

taskForm.addEventListener("input", (event) => {
  updateTaskPreview({ syncSeries: event.target && event.target.name === "series_id" });
});

if (activeSeriesInput) {
  activeSeriesInput.addEventListener("input", () => {
    setActiveSeriesId(activeSeriesInput.value, { syncTask: true, syncPackage: true });
    updateTaskPreview({ syncSeries: false });
  });
}

if (seriesSelect) {
  seriesSelect.addEventListener("change", async () => {
    setActiveSeriesId(seriesSelect.value, { syncTask: true, syncPackage: true });
    taskOutput.textContent = "Loading selected series...";
    try {
      await loadSeriesPackage();
      taskOutput.textContent = "Series loaded.";
    } catch (error) {
      taskOutput.textContent = error.message;
    }
  });
}

if (useTaskSeriesButton) {
  useTaskSeriesButton.addEventListener("click", async () => {
    setActiveSeriesId(buildTaskPayload().series_id, { syncTask: false, syncPackage: true });
    taskOutput.textContent = "Task series selected.";
    await loadSeriesPackage().catch((error) => {
      taskOutput.textContent = error.message;
    });
  });
}

if (loadActiveSeriesButton) {
  loadActiveSeriesButton.addEventListener("click", async () => {
    setActiveSeriesId(currentSeriesId(), { syncTask: true, syncPackage: true });
    taskOutput.textContent = "Loading series...";
    try {
      await loadSeriesPackage();
      taskOutput.textContent = "Series loaded.";
    } catch (error) {
      taskOutput.textContent = error.message;
    }
  });
}

if (newSeriesPackageButton) {
  newSeriesPackageButton.addEventListener("click", () => {
    setActiveSeriesId(currentSeriesId(), { syncTask: true, syncPackage: true });
    const draft = buildPackageDraft();
    latestPackage = {
      ok: true,
      series_id: draft.series_id,
      available: true,
      status: "draft",
      package: draft,
      modules: latestPackage && latestPackage.modules ? latestPackage.modules : {},
      summary: "",
    };
    if (packageOutput) packageOutput.textContent = JSON.stringify(draft, null, 2);
    if (packageSummary) packageSummary.textContent = "Unsaved package draft.";
    renderRoleEditor(draft);
    renderSeriesWorkspace();
    updateDiagnostics();
    taskOutput.textContent = "New package draft created. Save it before generation.";
  });
}

packageForm.addEventListener("input", () => {
  const packageField = packageForm.elements.package_series_id;
  if (packageField && document.activeElement === packageField) {
    setActiveSeriesId(packageField.value, { syncTask: true, syncPackage: false });
    lastSyncedPackageSeriesId = cleanValue(packageField.value);
  }
  syncPackageOutputFromRoleEditor();
  updateDiagnostics();
});

if (roleList) {
  roleList.addEventListener("input", () => {
    syncPackageOutputFromRoleEditor();
  });
  roleList.addEventListener("click", (event) => {
    const target = event.target;
    if (!target || !target.classList || !target.classList.contains("remove-role")) return;
    removeRole(Number(target.getAttribute("data-role-index")));
  });
}

loadPackageButton.addEventListener("click", async () => {
  loadPackageButton.disabled = true;
  taskOutput.textContent = "Loading series package...";
  try {
    await loadSeriesPackage();
    taskOutput.textContent = "Series package loaded.";
  } catch (error) {
    taskOutput.textContent = error.message;
  } finally {
    loadPackageButton.disabled = false;
  }
});

savePackageButton.addEventListener("click", async () => {
  savePackageButton.disabled = true;
  taskOutput.textContent = "Saving series package...";
  try {
    await saveSeriesPackage();
    taskOutput.textContent = "Series package saved.";
  } catch (error) {
    taskOutput.textContent = error.message;
  } finally {
    savePackageButton.disabled = false;
  }
});

generatePackageButton.addEventListener("click", async () => {
  generatePackageButton.disabled = true;
  taskOutput.textContent = "Generating series package...";
  try {
    await generateSeriesPackage();
    taskOutput.textContent = "Series package generated.";
  } catch (error) {
    taskOutput.textContent = error.message;
    await loadSeriesPackage().catch(() => {});
  } finally {
    generatePackageButton.disabled = false;
  }
});

copyPackageButton.addEventListener("click", () => {
  copyPackageJson().catch((error) => {
    taskOutput.textContent = error.message;
  });
});

if (addRoleButton) {
  addRoleButton.addEventListener("click", () => {
    addRole();
  });
}

if (rebuildRolesButton) {
  rebuildRolesButton.addEventListener("click", () => {
    renderRoleEditor(currentPackageJson());
    taskOutput.textContent = "Role editor loaded from package JSON.";
  });
}

if (saveRolesButton) {
  saveRolesButton.addEventListener("click", async () => {
    saveRolesButton.disabled = true;
    taskOutput.textContent = "Saving role package...";
    try {
      await saveSeriesPackage();
      taskOutput.textContent = "Role package saved.";
    } catch (error) {
      taskOutput.textContent = error.message;
    } finally {
      saveRolesButton.disabled = false;
    }
  });
}

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

updateTaskPreview({ syncSeries: true });
updateDiagnostics();
