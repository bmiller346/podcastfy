const settingsForm = document.querySelector("#settings-form");
const settingsStatus = document.querySelector("#settings-status");
const taskForm = document.querySelector("#task-form");
const taskSelect = document.querySelector("#task-select");
const taskOutput = document.querySelector("#task-output");
const taskPreview = document.querySelector("#task-preview");
const library = document.querySelector("#library");
const runTaskButton = document.querySelector("#run-task");
const refreshButton = document.querySelector("#refresh");

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
}

function renderLibrary(data) {
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
    taskOutput.textContent = JSON.stringify(job, null, 2);
    if (job.status === "succeeded" || job.status === "failed") {
      return job;
    }
    await new Promise((resolve) => {
      window.setTimeout(resolve, 1200);
    });
  }
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

refreshAll().catch((error) => {
  taskOutput.textContent = error.message;
});

updateTaskPreview();
