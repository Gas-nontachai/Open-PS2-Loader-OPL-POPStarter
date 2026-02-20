const STATES = {
  IDLE: "idle",
  VALIDATING: "validating_target",
  VALIDATED: "validated",
  FORMATTING: "formatting",
  IMPORTING: "importing",
  COMPLETED: "completed",
  FAILED: "failed",
  CANCELLED: "cancelled",
};

const TRANSITIONS = {
  [STATES.IDLE]: [STATES.VALIDATING, STATES.FORMATTING, STATES.IMPORTING],
  [STATES.VALIDATING]: [STATES.VALIDATED, STATES.FAILED, STATES.CANCELLED, STATES.IDLE],
  [STATES.VALIDATED]: [STATES.VALIDATING, STATES.FORMATTING, STATES.IMPORTING, STATES.IDLE],
  [STATES.FORMATTING]: [STATES.COMPLETED, STATES.FAILED, STATES.CANCELLED],
  [STATES.IMPORTING]: [STATES.COMPLETED, STATES.FAILED, STATES.CANCELLED],
  [STATES.COMPLETED]: [STATES.IDLE, STATES.VALIDATING, STATES.FORMATTING, STATES.IMPORTING],
  [STATES.FAILED]: [STATES.IDLE, STATES.VALIDATING, STATES.FORMATTING, STATES.IMPORTING],
  [STATES.CANCELLED]: [STATES.IDLE, STATES.VALIDATING, STATES.FORMATTING, STATES.IMPORTING],
};

const PROGRESS_BY_STATE = {
  [STATES.IDLE]: 0,
  [STATES.VALIDATING]: 15,
  [STATES.VALIDATED]: 30,
  [STATES.FORMATTING]: 55,
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

const targetPathInput = document.getElementById("target-path");
const isoFilesInput = document.getElementById("iso-files");
const overwriteInput = document.getElementById("overwrite");

let currentState = STATES.IDLE;
let activeController = null;

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

  const busy = currentState === STATES.VALIDATING || currentState === STATES.FORMATTING || currentState === STATES.IMPORTING;
  validateBtn.disabled = busy;
  importBtn.disabled = busy;
  formatBtn.disabled = busy;
  cancelBtn.disabled = !busy;
}

function defaultMessageForState(state) {
  if (state === STATES.IDLE) return "Ready.";
  if (state === STATES.VALIDATING) return "Validating target.";
  if (state === STATES.VALIDATED) return "Target validated.";
  if (state === STATES.FORMATTING) return "Formatting USB.";
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
  if (["validated", "validating_target", "formatting", "failed", "completed", "importing"].includes(apiState)) {
    if (apiState === "validated") return STATES.VALIDATED;
    if (apiState === "validating_target") return STATES.VALIDATING;
    if (apiState === "formatting") return STATES.FORMATTING;
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
  }
});

cancelBtn.addEventListener("click", () => {
  if (!activeController) {
    return;
  }
  activeController.abort();
});

pickFolderBtn.addEventListener("click", async () => {
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
  }
});
