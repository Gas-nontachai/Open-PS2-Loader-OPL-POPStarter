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
const tabImportBtn = document.getElementById("tab-import-btn");
const tabArtBtn = document.getElementById("tab-art-btn");
const tabImportPanel = document.getElementById("tab-import-panel");
const tabArtPanel = document.getElementById("tab-art-panel");

const targetPathInput = document.getElementById("target-path");
const isoFilesInput = document.getElementById("iso-files");
const overwriteInput = document.getElementById("overwrite");
const artGameNameInput = document.getElementById("art-game-name");
const artSourceSelect = document.getElementById("art-source-select");
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
let artSourceChoices = [];
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
  artSourceSelect,
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

function switchTab(tabName) {
  const isImport = tabName === "import";
  if (tabImportPanel && tabArtPanel) {
    tabImportPanel.hidden = !isImport;
    tabArtPanel.hidden = isImport;
  }
  if (tabImportBtn && tabArtBtn) {
    tabImportBtn.classList.toggle("is-active", isImport);
    tabArtBtn.classList.toggle("is-active", !isImport);
    tabImportBtn.setAttribute("aria-selected", String(isImport));
    tabArtBtn.setAttribute("aria-selected", String(!isImport));
  }
}

function setState(nextState, message = "") {
  const allowed = TRANSITIONS[currentState] || [];
  if (currentState !== nextState && !allowed.includes(nextState)) {
    appendLog("error", `การเปลี่ยนสถานะไม่ถูกต้อง: ${currentState} -> ${nextState}`);
    currentState = STATES.FAILED;
  } else {
    currentState = nextState;
  }

  statePill.textContent = currentState;
  statusMessage.textContent = message || defaultMessageForState(currentState);
  progressBar.style.width = `${PROGRESS_BY_STATE[currentState] || 0}%`;
  updateControlAvailability();
}

function setLoading(loading, text = "กำลังดำเนินการ...") {
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
  if (state === STATES.IDLE) return "พร้อมใช้งาน";
  if (state === STATES.VALIDATING) return "กำลังตรวจสอบปลายทาง";
  if (state === STATES.VALIDATED) return "ตรวจสอบปลายทางสำเร็จ";
  if (state === STATES.FORMATTING) return "กำลังฟอร์แมต USB";
  if (state === STATES.ARTING) return "กำลังจัดการ ART";
  if (state === STATES.IMPORTING) return "กำลังนำเข้าไฟล์";
  if (state === STATES.COMPLETED) return "นำเข้าเสร็จสิ้น";
  if (state === STATES.CANCELLED) return "ยกเลิกการทำงานแล้ว";
  return "การทำงานล้มเหลว";
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
    data = { status: "error", state: "failed", message: "รูปแบบข้อมูลตอบกลับไม่ถูกต้อง", details: {} };
  }

  renderSteps(data.steps || []);

  if (!response.ok || data.status !== "success") {
    const msg = data.message || "คำขอล้มเหลว";
    const error = new Error(msg);
    error.payload = data;
    throw error;
  }

  return data;
}

validateBtn.addEventListener("click", async () => {
  const targetPath = targetPathInput.value.trim();
  if (!targetPath) {
    appendLog("error", "ต้องระบุโฟลเดอร์ปลายทาง");
    return;
  }

  activeController = new AbortController();
  startOperation("กำลังตรวจสอบปลายทาง..");
  setState(STATES.VALIDATING, "กำลังตรวจสอบปลายทางและโครงสร้างโฟลเดอร์");

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
      setState(STATES.CANCELLED, "ยกเลิกการตรวจสอบแล้ว");
      appendLog("info", "ผู้ใช้ยกเลิกการตรวจสอบ");
      return;
    }

    setState(STATES.FAILED, err.message || "การตรวจสอบล้มเหลว");
    appendLog("error", err.message || "การตรวจสอบล้มเหลว", err.payload?.details || null);
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
    appendLog("error", "ต้องระบุโฟลเดอร์ปลายทาง");
    return;
  }
  if (!files || files.length === 0) {
    appendLog("error", "ต้องเลือกไฟล์ .iso อย่างน้อย 1 ไฟล์");
    return;
  }

  const invalidFile = Array.from(files).find((f) => !f.name.toLowerCase().endsWith(".iso"));
  if (invalidFile) {
    appendLog("error", `ชนิดไฟล์ไม่ถูกต้อง: ${invalidFile.name}`);
    return;
  }

  const formData = new FormData();
  formData.append("target_path", targetPath);
  formData.append("overwrite", overwriteInput.checked ? "true" : "false");
  Array.from(files).forEach((file) => formData.append("files", file));

  activeController = new AbortController();
  startOperation("กำลังเตรียมนำเข้า...");
  setState(STATES.IMPORTING, "กำลังเตรียมและนำเข้าไฟล์");

  try {
    const result = await callApi("/api/import", {
      method: "POST",
      body: formData,
      signal: activeController.signal,
    });

    setState(readApiState(result.state), result.message);
    appendLog("success", result.message, result.details);
    const importedFiles = (result.details?.imported || [])
      .map((item) => item.file || item.source_filename || "")
      .filter(Boolean);
    if (importedFiles.length > 0) {
      updateArtSourceChoices(importedFiles, importedFiles[0]);
      appendLog("info", `พร้อมจัดการ ART ได้ ${importedFiles.length} เกม (เลือกจากช่อง 'เลือกเกมสำหรับ ART')`);
    }
    await Swal.fire({
      icon: "success",
      title: "นำเข้าสำเร็จ",
      text: result.message || "นำเข้าไฟล์เสร็จสิ้น",
    });
  } catch (err) {
    if (err.name === "AbortError") {
      setState(STATES.CANCELLED, "ยกเลิกการนำเข้าแล้ว");
      appendLog("info", "ผู้ใช้ยกเลิกการนำเข้า");
      await Swal.fire({
        icon: "info",
        title: "ยกเลิกแล้ว",
        text: "การนำเข้าถูกยกเลิก",
      });
      return;
    }

    setState(STATES.FAILED, err.message || "การนำเข้าล้มเหลว");
    appendLog("error", err.message || "การนำเข้าล้มเหลว", err.payload?.details || null);
    await Swal.fire({
      icon: "error",
      title: "นำเข้าไม่สำเร็จ",
      text: err.message || "การนำเข้าล้มเหลว",
      footer: err.payload?.next_action ? `คำแนะนำ: ${err.payload.next_action}` : "",
    });
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
  startOperation("กำลังเปิดหน้าต่างเลือกโฟลเดอร์...");
  try {
    const result = await callApi("/api/pick-target-folder", {
      method: "GET",
    });
    if (result.details?.target) {
      targetPathInput.value = result.details.target;
      appendLog("success", "เลือกโฟลเดอร์ปลายทางแล้ว", { target: result.details.target });
    }
  } catch (err) {
    const state = err.payload?.state;
    if (state === "cancelled") {
      appendLog("info", "ผู้ใช้ยกเลิกการเลือกโฟลเดอร์");
      return;
    }

    appendLog("error", err.message || "เลือกโฟลเดอร์ไม่สำเร็จ", err.payload?.details || null);
    await Swal.fire({
      icon: "error",
      title: "เลือกโฟลเดอร์ไม่สำเร็จ",
      text: err.message || "ไม่สามารถเปิดหน้าต่างเลือกโฟลเดอร์ได้",
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
      title: "ยังไม่ได้ระบุปลายทาง",
      text: "กรุณาระบุโฟลเดอร์ปลายทางก่อน",
    });
    return;
  }

  const confirmResult = await Swal.fire({
    icon: "warning",
    title: "ฟอร์แมต USB ใช่หรือไม่?",
    html: `
      <p class="text-left">การทำงานนี้จะลบข้อมูลทั้งหมดบนอุปกรณ์ปลายทาง</p>
      <p class="text-left mt-2">พิมพ์ <b>FORMAT</b> เพื่อยืนยัน</p>
      <input id="swal-confirm-phrase" class="swal2-input" placeholder="FORMAT" />
    `,
    showCancelButton: true,
    confirmButtonText: "ดำเนินการต่อ",
    confirmButtonColor: "#f59e0b",
    preConfirm: () => {
      const phrase = document.getElementById("swal-confirm-phrase")?.value?.trim() || "";
      if (phrase.toUpperCase() !== "FORMAT") {
        Swal.showValidationMessage("กรุณาพิมพ์ FORMAT ให้ถูกต้อง");
        return false;
      }
      return phrase;
    },
  });

  if (!confirmResult.isConfirmed) {
    return;
  }

  const labelResult = await Swal.fire({
    title: "ชื่อไดรฟ์",
    input: "text",
    inputValue: "PS2USB",
    inputLabel: "ชื่อหลังฟอร์แมต (A-Z, 0-9, _ หรือ -)",
    showCancelButton: true,
    confirmButtonColor: "#f59e0b",
    confirmButtonText: "ฟอร์แมตตอนนี้",
  });

  if (!labelResult.isConfirmed) {
    return;
  }

  const volumeLabel = (labelResult.value || "PS2USB").trim() || "PS2USB";

  activeController = new AbortController();
  startOperation("กำลังฟอร์แมต USB..");
  setState(STATES.FORMATTING, "กำลังฟอร์แมต USB เป็น FAT32 และเตรียมโครงสร้าง");

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
      title: "ฟอร์แมตเสร็จสิ้น",
      text: result.message,
    });
  } catch (err) {
    if (err.name === "AbortError") {
      setState(STATES.CANCELLED, "ยกเลิกการฟอร์แมตแล้ว");
      appendLog("info", "ผู้ใช้ยกเลิกการฟอร์แมต");
      await Swal.fire({
        icon: "info",
        title: "ยกเลิกแล้ว",
        text: "คำสั่งฟอร์แมตถูกยกเลิก",
      });
      return;
    }

    setState(STATES.FAILED, err.message || "ฟอร์แมตล้มเหลว");
    appendLog("error", err.message || "การฟอร์แมตล้มเหลว", err.payload?.details || null);
    await Swal.fire({
      icon: "error",
      title: "ฟอร์แมตไม่สำเร็จ",
      text: err.message || "ฟอร์แมตล้มเหลว",
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
  const uploaded = Array.from(isoFilesInput.files || []).map((file) => file.name);
  if (uploaded.length > 0) {
    updateArtSourceChoices(uploaded, uploaded[0]);
  }
});

if (artSourceSelect) {
  artSourceSelect.addEventListener("change", () => {
    const selected = artSourceSelect.value.trim();
    if (selected) {
      artSourceFilenameInput.value = selected;
    }
  });
}

function ensureArtBasics() {
  const targetPath = targetPathInput.value.trim();
  if (!targetPath) {
    throw new Error("ต้องระบุโฟลเดอร์ปลายทาง");
  }
  return { targetPath };
}

function setGeneratedGameId(value) {
  generatedGameIdEl.textContent = value || "-";
}

function normalizeArtSourceChoices(values) {
  const seen = new Set();
  const normalized = [];
  values.forEach((value) => {
    const filename = (value || "").trim();
    if (!filename || seen.has(filename)) {
      return;
    }
    seen.add(filename);
    normalized.push(filename);
  });
  return normalized;
}

function updateArtSourceChoices(values, preferred = "") {
  artSourceChoices = normalizeArtSourceChoices(values);
  if (!artSourceSelect) {
    if (preferred) {
      artSourceFilenameInput.value = preferred;
    }
    return;
  }

  const previous = artSourceSelect.value;
  artSourceSelect.innerHTML = '<option value="">-- เลือกจากไฟล์ที่ import/อัปโหลด --</option>';
  artSourceChoices.forEach((filename) => {
    const option = document.createElement("option");
    option.value = filename;
    option.textContent = filename;
    artSourceSelect.appendChild(option);
  });

  const selectedValue = preferred || previous || artSourceFilenameInput.value.trim() || artSourceChoices[0] || "";
  if (selectedValue) {
    artSourceSelect.value = selectedValue;
    artSourceFilenameInput.value = selectedValue;
  }
}

function renderAutoCandidates(candidates) {
  autoArtResults.innerHTML = "";
  if (!candidates.length) {
    autoArtResults.innerHTML = '<p class="text-sm text-slate-400">ไม่พบภาพตัวอย่างที่ค้นหาได้</p>';
    return;
  }

  candidates.forEach((candidate, index) => {
    const card = document.createElement("article");
    card.className = "art-card";
    const suggestedType = ART_TYPES[index % ART_TYPES.length];
    const options = ART_TYPES.map((artType) => `<option value="${artType}" ${artType === suggestedType ? "selected" : ""}>${artType}</option>`).join("");
    card.innerHTML = `
      <img src="${candidate.thumbnail_url || candidate.image_url}" alt="${candidate.title || "ตัวเลือกภาพ ART"}" class="art-thumb" />
      <p class="art-title">${candidate.title || "ไม่มีชื่อ"}</p>
      <label class="art-toggle">
        <input type="checkbox" data-candidate-id="${candidate.candidate_id}" class="auto-art-check" checked />
        ใช้รูปนี้
      </label>
      <label class="art-type-label">ประเภท ART
        <select class="art-type-select auto-art-type" data-candidate-id="${candidate.candidate_id}">
          ${options}
        </select>
      </label>
      <a class="art-link" href="${candidate.image_url}" target="_blank" rel="noreferrer">เปิดภาพเต็ม</a>
    `;
    autoArtResults.appendChild(card);
  });
}

uploadManualArtBtn.addEventListener("click", async () => {
  let basics;
  try {
    basics = ensureArtBasics();
  } catch (err) {
    await Swal.fire({ icon: "warning", title: "ข้อมูลไม่ครบ", text: err.message });
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
    await Swal.fire({ icon: "warning", title: "ยังไม่ได้เลือกไฟล์", text: "กรุณาเลือกไฟล์ ART อย่างน้อย 1 ไฟล์" });
    return;
  }

  activeController = new AbortController();
  startOperation("กำลังอัปโหลด ART แบบกำหนดเอง...");
  setState(STATES.ARTING, "กำลังอัปโหลดไฟล์ ART แบบกำหนดเอง");
  try {
    const result = await callApi("/api/art/manual", {
      method: "POST",
      body: formData,
      signal: activeController.signal,
    });
    setGeneratedGameId(result.details?.game_id || "");
    setState(readApiState(result.state), result.message);
    appendLog("success", result.message, result.details);
    await Swal.fire({ icon: "success", title: "อัปโหลด ART สำเร็จ", text: result.message });
  } catch (err) {
    if (err.name === "AbortError") {
      setState(STATES.CANCELLED, "ยกเลิกการอัปโหลด ART แบบกำหนดเองแล้ว");
      return;
    }
    setState(STATES.FAILED, err.message || "การอัปโหลด ART แบบกำหนดเองล้มเหลว");
    await Swal.fire({ icon: "error", title: "อัปโหลดไม่สำเร็จ", text: err.message || "การอัปโหลด ART แบบกำหนดเองล้มเหลว" });
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
    await Swal.fire({ icon: "warning", title: "ข้อมูลไม่ครบ", text: err.message });
    return;
  }

  const payload = {
    target_path: basics.targetPath,
    game_name: artGameNameInput.value.trim() || null,
    source_filename: artSourceFilenameInput.value.trim() || null,
    max_results: 10,
  };

  activeController = new AbortController();
  startOperation("กำลังค้นหา ART...");
  setState(STATES.ARTING, "กำลังค้นหาภาพ ART");
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
      setState(STATES.CANCELLED, "ยกเลิกการค้นหา ART แล้ว");
      return;
    }
    setState(STATES.FAILED, err.message || "การค้นหา ART ล้มเหลว");
    await Swal.fire({ icon: "error", title: "ค้นหาไม่สำเร็จ", text: err.message || "การค้นหา ART ล้มเหลว" });
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
    await Swal.fire({ icon: "warning", title: "ข้อมูลไม่ครบ", text: err.message });
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
    await Swal.fire({ icon: "warning", title: "ยังไม่ได้เลือก", text: "กรุณาเลือกภาพอย่างน้อย 1 รูป" });
    return;
  }

  activeController = new AbortController();
  startOperation("กำลังบันทึก ART ที่เลือก...");
  setState(STATES.ARTING, "กำลังบันทึกไฟล์ ART ที่เลือก");
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
      appendLog("info", `ข้าม ${skippedCount} รายการที่เลือกประเภท ART ซ้ำ`);
    }
    await Swal.fire({ icon: "success", title: "บันทึก ART อัตโนมัติสำเร็จ", text: result.message });
  } catch (err) {
    if (err.name === "AbortError") {
      setState(STATES.CANCELLED, "ยกเลิกการบันทึก ART อัตโนมัติแล้ว");
      return;
    }
    setState(STATES.FAILED, err.message || "การบันทึก ART อัตโนมัติล้มเหลว");
    await Swal.fire({ icon: "error", title: "บันทึกไม่สำเร็จ", text: err.message || "การบันทึก ART อัตโนมัติล้มเหลว" });
  } finally {
    activeController = null;
    endOperation();
  }
});

updateControlAvailability();

if (tabImportBtn && tabArtBtn) {
  tabImportBtn.addEventListener("click", () => switchTab("import"));
  tabArtBtn.addEventListener("click", () => switchTab("art"));
  switchTab("import");
}
