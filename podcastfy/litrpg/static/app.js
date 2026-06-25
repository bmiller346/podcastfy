const settingsForm = document.querySelector("#settings-form");
const settingsStatus = document.querySelector("#settings-status");
const taskSelect = document.querySelector("#task-select");
const taskOutput = document.querySelector("#task-output");
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

function renderLibrary(data) {
  const series = data.library || [];
  if (!series.length) {
    library.innerHTML = `<p class="muted">No saved episodes found under data/litrpg.</p>`;
    return;
  }
  library.innerHTML = series
    .map((item) => {
      const episodes = (item.episodes || []).map(renderEpisode).join("");
      return `<article><h3 class="series-title">${escapeHtml(item.series_id)}</h3>${episodes}</article>`;
    })
    .join("");
}

function renderEpisode(episode) {
  const number = episode.episode_number ? `Episode ${episode.episode_number}` : episode.episode_id;
  const prompt = episode.prompt ? `<div class="episode-prompt">${escapeHtml(episode.prompt)}</div>` : "";
  const audio = episode.audio
    ? `<audio controls preload="none" src="${episode.audio.url}"></audio><div class="muted">${escapeHtml(episode.audio.path)}</div>`
    : `<div class="muted">No audio file saved for this episode.</div>`;
  return `<section class="episode"><div class="episode-title">${escapeHtml(number)}</div>${prompt}${audio}</section>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
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
