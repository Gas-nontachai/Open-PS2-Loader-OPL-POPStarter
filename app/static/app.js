const STATES = {
  IDLE: "idle",
  VALIDATING: "validating_target",
  VALIDATED: "validated",
  FORMATTING: "formatting",
  ARTING: "managing_art",
  IMPORTING: "importing",
  COMPLETED: "completed",
  FAILED: "failed",
  CANCELLED: "cancelled",
};

const TRANSITIONS = {
  [STATES.IDLE]: [STATES.VALIDATING, STATES.FORMATTING, STATES.ARTING, STATES.IMPORTING],
  [STATES.VALIDATING]: [STATES.VALIDATED, STATES.FAILED, STATES.CANCELLED, STATES.IDLE],
  [STATES.VALIDATED]: [STATES.VALIDATING, STATES.FORMATTING, STATES.ARTING, STATES.IMPORTING, STATES.IDLE],
  [STATES.FORMATTING]: [STATES.COMPLETED, STATES.FAILED, STATES.CANCELLED],
  [STATES.ARTING]: [STATES.COMPLETED, STATES.FAILED, STATES.CANCELLED],
  [STATES.IMPORTING]: [STATES.COMPLETED, STATES.FAILED, STATES.CANCELLED],
  [STATES.COMPLETED]: [STATES.IDLE, STATES.VALIDATING, STATES.FORMATTING, STATES.ARTING, STATES.IMPORTING],
  [STATES.FAILED]: [STATES.IDLE, STATES.VALIDATING, STATES.FORMATTING, STATES.ARTING, STATES.IMPORTING],
  [STATES.CANCELLED]: [STATES.IDLE, STATES.VALIDATING, STATES.FORMATTING, STATES.ARTING, STATES.IMPORTING],
};

const PROGRESS_BY_STATE = {
  [STATES.IDLE]: 0,
  [STATES.VALIDATING]: 15,
  [STATES.VALIDATED]: 30,
  [STATES.FORMATTING]: 55,
  [STATES.ARTING]: 60,
  [STATES.IMPORTING]: 70,
  [STATES.COMPLETED]: 100,
  [STATES.FAILED]: 100,
  [STATES.CANCELLED]: 100,
};

const statePill = document.getElementById("state-pill");
const statusMessage = document.getElementById("status-message");
const eventLog = document.getElementById("event-log");
const progressBar = document.getElementById("progress-bar");

const form = document.getElementById("import-form");
const validateBtn = document.getElementById("validate-btn");
const importBtn = document.getElementById("import-btn");
const formatBtn = document.getElementById("format-btn");
const cancelBtn = document.getElementById("cancel-btn");
const pickFolderBtn = document.getElementById("pick-folder-btn");
const artModeSelect = document.getElementById("art-mode");
const manualArtBlock = document.getElementById("manual-art-block");
const autoArtBlock = document.getElementById("auto-art-block");
const uploadManualArtBtn = document.getElementById("upload-manual-art-btn");
const searchAutoArtBtn = document.getElementById("search-auto-art-btn");
const saveAutoArtBtn = document.getElementById("save-auto-art-btn");
const autoArtResults = document.getElementById("auto-art-results");
const loadingOverlay = document.getElementById("loading-overlay");
const loadingText = document.getElementById("loading-text");
const generatedGameIdEl = document.getElementById("generated-game-id");

const targetPathInput = document.getElementById("target-path");
const isoFilesInput = document.getElementById("iso-files");
const overwriteInput = document.getElementById("overwrite");
const artGameNameInput = document.getElementById("art-game-name");
const artSourceFilenameInput = document.getElementById("art-source-filename");
const artCovInput = document.getElementById("art-cov");
const artCov2Input = document.getElementById("art-cov2");
const artBgInput = document.getElementById("art-bg");
const artScrInput = document.getElementById("art-scr");
const artScr2Input = document.getElementById("art-scr2");
const artLgoInput = document.getElementById("art-lgo");
const artIcoInput = document.getElementById("art-ico");
const artLabInput = document.getElementById("art-lab");

let currentState = STATES.IDLE;
let activeController = null;
let isLoading = false;
const ART_TYPES = ["COV", "COV2", "BG", "SCR", "SCR2", "LGO", "ICO", "LAB"];
let autoCandidates = [];
const BUSY_STATES = new Set([STATES.VALIDATING, STATES.FORMATTING, STATES.ARTING, STATES.IMPORTING]);

const controllableElements = [
  validateBtn,
  importBtn,
  formatBtn,
  pickFolderBtn,
  uploadManualArtBtn,
  searchAutoArtBtn,
  saveAutoArtBtn,
  artModeSelect,
  targetPathInput,
  isoFilesInput,
  overwriteInput,
  artGameNameInput,
  artSourceFilenameInput,
  artCovInput,
  artCov2Input,
  artBgInput,
  artScrInput,
  artScr2Input,
  artLgoInput,
  artIcoInput,
  artLabInput,
];

function setState(nextState, message = "") {
  const allowed = TRANSITIONS[currentState] || [];
  if (currentState !== nextState && !allowed.includes(nextState)) {
    appendLog("error", `invalid transition: ${currentState} -> ${nextState}`);
    currentState = STATES.FAILED;
  } else {
    currentState = nextState;
  }

  statePill.textContent = currentState;
  statusMessage.textContent = message || defaultMessageForState(currentState);
  progressBar.style.width = `${PROGRESS_BY_STATE[currentState] || 0}%`;
  updateControlAvailability();
}

function setLoading(loading, text = "Working...") {
  isLoading = loading;
  loadingOverlay.classList.toggle("hidden", !loading);
  loadingOverlay.classList.toggle("flex", loading);
  loadingOverlay.classList.toggle("pointer-events-none", !loading);
  loadingText.textContent = text;
  updateControlAvailability();
}

function updateControlAvailability() {
  const stateBusy = BUSY_STATES.has(currentState);
  const busy = stateBusy || isLoading;
  controllableElements.forEach((element) => {
    if (element) {
      element.disabled = busy;
    }
  });
  cancelBtn.disabled = !(stateBusy && activeController);
}

function shouldBlockTabClose() {
  return isLoading || BUSY_STATES.has(currentState);
}

window.addEventListener("beforeunload", (event) => {
  if (!shouldBlockTabClose()) {
    return;
  }
  event.preventDefault();
  event.returnValue = "";
});

function startOperation(loadingMessage) {
  setLoading(true, loadingMessage);
}

function endOperation() {
  setLoading(false);
}

function defaultMessageForState(state) {
  if (state === STATES.IDLE) return "Ready.";
  if (state === STATES.VALIDATING) return "Validating target.";
  if (state === STATES.VALIDATED) return "Target validated.";
  if (state === STATES.FORMATTING) return "Formatting USB.";
  if (state === STATES.ARTING) return "Managing ART.";
  if (state === STATES.IMPORTING) return "Importing files.";
  if (state === STATES.COMPLETED) return "Import completed.";
  if (state === STATES.CANCELLED) return "Operation cancelled.";
  return "Operation failed.";
}

function appendLog(kind, message, details = null) {
  const li = document.createElement("li");
  const ts = new Date().toLocaleTimeString();
  li.innerHTML = `<span class="uppercase tracking-wide text-[10px] text-slate-400">${kind}</span> <span class="ml-2">${ts} - ${message}</span>`;

  if (details && Object.keys(details).length > 0) {
    const pre = document.createElement("pre");
    pre.className = "mt-2 overflow-auto text-[11px] text-cyan-200";
    pre.textContent = JSON.stringify(details, null, 2);
    li.appendChild(pre);
  }

  eventLog.prepend(li);
}

function readApiState(apiState) {
  if (["validated", "validating_target", "formatting", "managing_art", "searching_art", "failed", "completed", "importing"].includes(apiState)) {
    if (apiState === "validated") return STATES.VALIDATED;
    if (apiState === "validating_target") return STATES.VALIDATING;
    if (apiState === "formatting") return STATES.FORMATTING;
    if (apiState === "managing_art") return STATES.ARTING;
    if (apiState === "searching_art") return STATES.VALIDATED;
    if (apiState === "importing") return STATES.IMPORTING;
    if (apiState === "completed") return STATES.COMPLETED;
    return STATES.FAILED;
  }
  return STATES.IDLE;
}

function renderSteps(steps = []) {
  steps.forEach((step) => {
    appendLog(step.status || "info", `${step.state}: ${step.message}`, step.details || null);
  });
}

async function callApi(url, options) {
  const response = await fetch(url, options);
  let data = {};
  try {
    data = await response.json();
  } catch (_err) {
    data = { status: "error", state: "failed", message: "non-json response", details: {} };
  }

  renderSteps(data.steps || []);

  if (!response.ok || data.status !== "success") {
    const msg = data.message || "request failed";
    const error = new Error(msg);
    error.payload = data;
    throw error;
  }

  return data;
}

validateBtn.addEventListener("click", async () => {
  const targetPath = targetPathInput.value.trim();
  if (!targetPath) {
    appendLog("error", "target path is required");
    return;
  }

  activeController = new AbortController();
  startOperation("Validating target...");
  setState(STATES.VALIDATING, "Validating target path and structure.");

  try {
    const payload = { target_path: targetPath, ensure_folders: true };
    const result = await callApi("/api/validate-target", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: activeController.signal,
    });

    setState(readApiState(result.state), result.message);
    appendLog("success", result.message, result.details);
  } catch (err) {
    if (err.name === "AbortError") {
      setState(STATES.CANCELLED, "Validation cancelled.");
      appendLog("info", "validation cancelled by user");
      return;
    }

    setState(STATES.FAILED, err.message || "Validation failed.");
    appendLog("error", err.message || "validation failed", err.payload?.details || null);
  } finally {
    activeController = null;
    endOperation();
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const targetPath = targetPathInput.value.trim();
  const files = isoFilesInput.files;

  if (!targetPath) {
    appendLog("error", "target path is required");
    return;
  }
  if (!files || files.length === 0) {
    appendLog("error", "at least one .iso file is required");
    return;
  }

  const invalidFile = Array.from(files).find((f) => !f.name.toLowerCase().endsWith(".iso"));
  if (invalidFile) {
    appendLog("error", `invalid file type: ${invalidFile.name}`);
    return;
  }

  const formData = new FormData();
  formData.append("target_path", targetPath);
  formData.append("overwrite", overwriteInput.checked ? "true" : "false");
  Array.from(files).forEach((file) => formData.append("files", file));

  activeController = new AbortController();
  startOperation("Preparing import...");
  setState(STATES.IMPORTING, "Preparing and importing files.");

  try {
    const result = await callApi("/api/import", {
      method: "POST",
      body: formData,
      signal: activeController.signal,
    });

    setState(readApiState(result.state), result.message);
    appendLog("success", result.message, result.details);
  } catch (err) {
    if (err.name === "AbortError") {
      setState(STATES.CANCELLED, "Import cancelled.");
      appendLog("info", "import cancelled by user");
      return;
    }

    setState(STATES.FAILED, err.message || "Import failed.");
    appendLog("error", err.message || "import failed", err.payload?.details || null);
  } finally {
    activeController = null;
    endOperation();
  }
});

cancelBtn.addEventListener("click", () => {
  if (!activeController) {
    return;
  }
  activeController.abort();
});

pickFolderBtn.addEventListener("click", async () => {
  startOperation("Opening folder picker...");
  try {
    const result = await callApi("/api/pick-target-folder", {
      method: "GET",
    });
    if (result.details?.target) {
      targetPathInput.value = result.details.target;
      appendLog("success", "target folder selected", { target: result.details.target });
    }
  } catch (err) {
    const state = err.payload?.state;
    if (state === "cancelled") {
      appendLog("info", "folder selection cancelled");
      return;
    }

    appendLog("error", err.message || "failed to select folder", err.payload?.details || null);
    await Swal.fire({
      icon: "error",
      title: "Select Folder Failed",
      text: err.message || "Could not open folder picker.",
    });
  } finally {
    endOperation();
  }
});

formatBtn.addEventListener("click", async () => {
  const targetPath = targetPathInput.value.trim();
  if (!targetPath) {
    await Swal.fire({
      icon: "warning",
      title: "Missing target path",
      text: "Please provide target parent folder first.",
    });
    return;
  }

  const confirmResult = await Swal.fire({
    icon: "warning",
    title: "Format USB?",
    html: `
      <p class="text-left">This will erase all data on the target device.</p>
      <p class="text-left mt-2">Type <b>FORMAT</b> to confirm.</p>
      <input id="swal-confirm-phrase" class="swal2-input" placeholder="FORMAT" />
    `,
    showCancelButton: true,
    confirmButtonText: "Continue",
    confirmButtonColor: "#f59e0b",
    preConfirm: () => {
      const phrase = document.getElementById("swal-confirm-phrase")?.value?.trim() || "";
      if (phrase.toUpperCase() !== "FORMAT") {
        Swal.showValidationMessage("Please type FORMAT exactly.");
        return false;
      }
      return phrase;
    },
  });

  if (!confirmResult.isConfirmed) {
    return;
  }

  const labelResult = await Swal.fire({
    title: "Volume Label",
    input: "text",
    inputValue: "PS2USB",
    inputLabel: "Label after format (A-Z, 0-9, _ or -)",
    showCancelButton: true,
    confirmButtonColor: "#f59e0b",
    confirmButtonText: "Format now",
  });

  if (!labelResult.isConfirmed) {
    return;
  }

  const volumeLabel = (labelResult.value || "PS2USB").trim() || "PS2USB";

  activeController = new AbortController();
  startOperation("Formatting USB...");
  setState(STATES.FORMATTING, "Formatting target USB as FAT32 and preparing structure.");

  try {
    const result = await callApi("/api/format-target", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_path: targetPath,
        confirm_phrase: "FORMAT",
        volume_label: volumeLabel,
      }),
      signal: activeController.signal,
    });

    if (result.details?.target) {
      targetPathInput.value = result.details.target;
    }

    setState(readApiState(result.state), result.message);
    appendLog("success", result.message, result.details);
    await Swal.fire({
      icon: "success",
      title: "Format Completed",
      text: result.message,
    });
  } catch (err) {
    if (err.name === "AbortError") {
      setState(STATES.CANCELLED, "Format cancelled.");
      appendLog("info", "format cancelled by user");
      await Swal.fire({
        icon: "info",
        title: "Cancelled",
        text: "Format request was cancelled.",
      });
      return;
    }

    setState(STATES.FAILED, err.message || "Format failed.");
    appendLog("error", err.message || "format failed", err.payload?.details || null);
    await Swal.fire({
      icon: "error",
      title: "Format Failed",
      text: err.message || "Format failed.",
    });
  } finally {
    activeController = null;
    endOperation();
  }
});

artModeSelect.addEventListener("change", () => {
  const mode = artModeSelect.value;
  manualArtBlock.classList.toggle("hidden", mode !== "manual");
  autoArtBlock.classList.toggle("hidden", mode !== "auto");
});

isoFilesInput.addEventListener("change", () => {
  if (!artSourceFilenameInput.value && isoFilesInput.files?.length > 0) {
    artSourceFilenameInput.value = isoFilesInput.files[0].name;
  }
});

function ensureArtBasics() {
  const targetPath = targetPathInput.value.trim();
  if (!targetPath) {
    throw new Error("target path is required");
  }
  return { targetPath };
}

function setGeneratedGameId(value) {
  generatedGameIdEl.textContent = value || "-";
}

function renderAutoCandidates(candidates) {
  autoArtResults.innerHTML = "";
  if (!candidates.length) {
    autoArtResults.innerHTML = '<p class="text-sm text-slate-400">No preview candidates found.</p>';
    return;
  }

  candidates.forEach((candidate, index) => {
    const card = document.createElement("article");
    card.className = "rounded-lg border border-slate-700 bg-slate-950/60 p-3";
    const suggestedType = ART_TYPES[index % ART_TYPES.length];
    const options = ART_TYPES.map((artType) => `<option value="${artType}" ${artType === suggestedType ? "selected" : ""}>${artType}</option>`).join("");
    card.innerHTML = `
      <img src="${candidate.thumbnail_url || candidate.image_url}" alt="${candidate.title || "art candidate"}" class="h-36 w-full rounded-md object-cover" />
      <p class="mt-2 line-clamp-2 text-xs text-slate-300">${candidate.title || "Untitled"}</p>
      <label class="mt-2 flex items-center gap-2 text-xs text-slate-200">
        <input type="checkbox" data-candidate-id="${candidate.candidate_id}" class="auto-art-check" checked />
        Use this image
      </label>
      <label class="mt-2 block text-xs text-slate-300">Art Type
        <select class="mt-1 w-full rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-100 auto-art-type" data-candidate-id="${candidate.candidate_id}">
          ${options}
        </select>
      </label>
      <a class="mt-2 inline-block text-xs text-cyan-300 underline" href="${candidate.image_url}" target="_blank" rel="noreferrer">Open full image</a>
    `;
    autoArtResults.appendChild(card);
  });
}

uploadManualArtBtn.addEventListener("click", async () => {
  let basics;
  try {
    basics = ensureArtBasics();
  } catch (err) {
    await Swal.fire({ icon: "warning", title: "Missing required info", text: err.message });
    return;
  }

  const formData = new FormData();
  formData.append("target_path", basics.targetPath);
  formData.append("game_name", artGameNameInput.value.trim() || "");
  formData.append("source_filename", artSourceFilenameInput.value.trim() || "");
  const fileMap = [
    ["cov", artCovInput],
    ["cov2", artCov2Input],
    ["bg", artBgInput],
    ["scr", artScrInput],
    ["scr2", artScr2Input],
    ["lgo", artLgoInput],
    ["ico", artIcoInput],
    ["lab", artLabInput],
  ];

  let count = 0;
  fileMap.forEach(([field, input]) => {
    if (input.files?.[0]) {
      formData.append(field, input.files[0]);
      count += 1;
    }
  });
  if (!count) {
    await Swal.fire({ icon: "warning", title: "No files selected", text: "Select at least one ART file." });
    return;
  }

  activeController = new AbortController();
  startOperation("Uploading manual ART...");
  setState(STATES.ARTING, "Uploading manual ART files.");
  try {
    const result = await callApi("/api/art/manual", {
      method: "POST",
      body: formData,
      signal: activeController.signal,
    });
    setGeneratedGameId(result.details?.game_id || "");
    setState(readApiState(result.state), result.message);
    appendLog("success", result.message, result.details);
    await Swal.fire({ icon: "success", title: "Manual ART uploaded", text: result.message });
  } catch (err) {
    if (err.name === "AbortError") {
      setState(STATES.CANCELLED, "Manual ART upload cancelled.");
      return;
    }
    setState(STATES.FAILED, err.message || "Manual ART upload failed.");
    await Swal.fire({ icon: "error", title: "Upload failed", text: err.message || "Manual ART upload failed." });
  } finally {
    activeController = null;
    endOperation();
  }
});

searchAutoArtBtn.addEventListener("click", async () => {
  let basics;
  try {
    basics = ensureArtBasics();
  } catch (err) {
    await Swal.fire({ icon: "warning", title: "Missing required info", text: err.message });
    return;
  }

  const payload = {
    target_path: basics.targetPath,
    game_name: artGameNameInput.value.trim() || null,
    source_filename: artSourceFilenameInput.value.trim() || null,
    max_results: 10,
  };

  activeController = new AbortController();
  startOperation("Searching ART...");
  setState(STATES.ARTING, "Searching ART candidates.");
  try {
    const result = await callApi("/api/art/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: activeController.signal,
    });
    setGeneratedGameId(result.details?.game_id || "");
    autoCandidates = result.details?.candidates || [];
    renderAutoCandidates(autoCandidates);
    setState(readApiState(result.state), result.message);
    appendLog("success", result.message, { count: autoCandidates.length, provider: result.details?.provider_used, cache_hit: result.details?.cache_hit });
  } catch (err) {
    if (err.name === "AbortError") {
      setState(STATES.CANCELLED, "ART search cancelled.");
      return;
    }
    setState(STATES.FAILED, err.message || "ART search failed.");
    await Swal.fire({ icon: "error", title: "Search failed", text: err.message || "ART search failed." });
  } finally {
    activeController = null;
    endOperation();
  }
});

saveAutoArtBtn.addEventListener("click", async () => {
  let basics;
  try {
    basics = ensureArtBasics();
  } catch (err) {
    await Swal.fire({ icon: "warning", title: "Missing required info", text: err.message });
    return;
  }

  const checks = Array.from(document.querySelectorAll(".auto-art-check"));
  const types = Array.from(document.querySelectorAll(".auto-art-type"));
  const selections = [];
  checks.forEach((checkEl) => {
    if (!checkEl.checked) return;
    const candidateId = Number(checkEl.dataset.candidateId);
    const candidate = autoCandidates.find((c) => c.candidate_id === candidateId);
    const typeSelect = types.find((x) => Number(x.dataset.candidateId) === candidateId);
    if (!candidate || !typeSelect) return;
    selections.push({
      art_type: typeSelect.value,
      image_url: candidate.image_url,
    });
  });

  if (!selections.length) {
    await Swal.fire({ icon: "warning", title: "No selection", text: "Select at least one preview image." });
    return;
  }

  activeController = new AbortController();
  startOperation("Saving selected ART...");
  setState(STATES.ARTING, "Saving selected ART files.");
  try {
    const result = await callApi("/api/art/save-auto", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_path: basics.targetPath,
        game_name: artGameNameInput.value.trim() || null,
        source_filename: artSourceFilenameInput.value.trim() || null,
        selections,
      }),
      signal: activeController.signal,
    });
    setGeneratedGameId(result.details?.game_id || "");
    setState(readApiState(result.state), result.message);
    appendLog("success", result.message, result.details);
    const skippedCount = (result.details?.skipped_duplicates || []).length;
    if (skippedCount > 0) {
      appendLog("info", `Skipped ${skippedCount} duplicate art type selections.`);
    }
    await Swal.fire({ icon: "success", title: "Auto ART saved", text: result.message });
  } catch (err) {
    if (err.name === "AbortError") {
      setState(STATES.CANCELLED, "Auto ART save cancelled.");
      return;
    }
    setState(STATES.FAILED, err.message || "Auto ART save failed.");
    await Swal.fire({ icon: "error", title: "Save failed", text: err.message || "Auto ART save failed." });
  } finally {
    activeController = null;
    endOperation();
  }
});

updateControlAvailability();
