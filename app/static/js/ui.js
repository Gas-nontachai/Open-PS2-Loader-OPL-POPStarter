import { ART_TYPES, BUSY_STATES, PROGRESS_BY_STATE, STATES, TRANSITIONS } from "./constants.js";
import { controllableElements, dom } from "./dom.js";
import { store } from "./store.js";

export function switchTab(tabName) {
  const isImport = tabName === "import";
  if (dom.tabImportPanel && dom.tabArtPanel) {
    dom.tabImportPanel.hidden = !isImport;
    dom.tabArtPanel.hidden = isImport;
  }
  if (dom.tabImportBtn && dom.tabArtBtn) {
    dom.tabImportBtn.classList.toggle("is-active", isImport);
    dom.tabArtBtn.classList.toggle("is-active", !isImport);
    dom.tabImportBtn.setAttribute("aria-selected", String(isImport));
    dom.tabArtBtn.setAttribute("aria-selected", String(!isImport));
  }
}

export function defaultMessageForState(state) {
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

export function appendLog(kind, message, details = null) {
  const li = document.createElement("li");
  const ts = new Date().toLocaleTimeString();
  li.innerHTML = `<span class="uppercase tracking-wide text-[10px] text-slate-400">${kind}</span> <span class="ml-2">${ts} - ${message}</span>`;

  if (details && Object.keys(details).length > 0) {
    const pre = document.createElement("pre");
    pre.className = "mt-2 overflow-auto text-[11px] text-cyan-200";
    pre.textContent = JSON.stringify(details, null, 2);
    li.appendChild(pre);
  }

  dom.eventLog.prepend(li);
}

export function updateControlAvailability() {
  const stateBusy = BUSY_STATES.has(store.currentState);
  const busy = stateBusy || store.isLoading;
  controllableElements.forEach((element) => {
    if (element) {
      element.disabled = busy;
    }
  });
  dom.cancelBtn.disabled = !(stateBusy && store.activeController);
}

export function setState(nextState, message = "") {
  const allowed = TRANSITIONS[store.currentState] || [];
  if (store.currentState !== nextState && !allowed.includes(nextState)) {
    appendLog("error", `การเปลี่ยนสถานะไม่ถูกต้อง: ${store.currentState} -> ${nextState}`);
    store.currentState = STATES.FAILED;
  } else {
    store.currentState = nextState;
  }

  dom.statePill.textContent = store.currentState;
  dom.statusMessage.textContent = message || defaultMessageForState(store.currentState);
  dom.progressBar.style.width = `${PROGRESS_BY_STATE[store.currentState] || 0}%`;
  updateControlAvailability();
}

export function setLoading(loading, text = "กำลังดำเนินการ...") {
  store.isLoading = loading;
  dom.loadingOverlay.classList.toggle("hidden", !loading);
  dom.loadingOverlay.classList.toggle("flex", loading);
  dom.loadingOverlay.classList.toggle("pointer-events-none", !loading);
  dom.loadingText.textContent = text;
  updateControlAvailability();
}

export function startOperation(loadingMessage) {
  setLoading(true, loadingMessage);
}

export function endOperation() {
  setLoading(false);
}

export function shouldBlockTabClose() {
  return store.isLoading || BUSY_STATES.has(store.currentState);
}

export function readApiState(apiState) {
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

export function renderSteps(steps = []) {
  steps.forEach((step) => {
    appendLog(step.status || "info", `${step.state}: ${step.message}`, step.details || null);
  });
}

export function setGeneratedGameId(value) {
  dom.generatedGameIdEl.textContent = value || "-";
}

export function normalizeArtSourceChoices(values) {
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

export function updateArtSourceChoices(values, preferred = "") {
  store.artSourceChoices = normalizeArtSourceChoices(values);
  if (!dom.artSourceSelect) {
    if (preferred) {
      dom.artSourceFilenameInput.value = preferred;
    }
    return;
  }

  const previous = dom.artSourceSelect.value;
  dom.artSourceSelect.innerHTML = '<option value="">-- เลือกจากไฟล์ที่ import/อัปโหลด --</option>';
  store.artSourceChoices.forEach((filename) => {
    const option = document.createElement("option");
    option.value = filename;
    option.textContent = filename;
    dom.artSourceSelect.appendChild(option);
  });

  const selectedValue = preferred || previous || dom.artSourceFilenameInput.value.trim() || store.artSourceChoices[0] || "";
  if (selectedValue) {
    dom.artSourceSelect.value = selectedValue;
    dom.artSourceFilenameInput.value = selectedValue;
  }
}

export function renderAutoCandidates(candidates) {
  dom.autoArtResults.innerHTML = "";
  if (!candidates.length) {
    dom.autoArtResults.innerHTML = '<p class="text-sm text-slate-400">ไม่พบภาพตัวอย่างที่ค้นหาได้</p>';
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
    dom.autoArtResults.appendChild(card);
  });
}
