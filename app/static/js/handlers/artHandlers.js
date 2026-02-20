import { ART_TYPES, STATES } from "../constants.js";
import { dom } from "../dom.js";
import { store } from "../store.js";
import { callApi } from "../api.js";
import { appendLog, endOperation, readApiState, renderAutoCandidates, setGeneratedGameId, setState, startOperation } from "../ui.js";

function ensureArtBasics() {
  const targetPath = dom.targetPathInput.value.trim();
  if (!targetPath) {
    throw new Error("ต้องระบุโฟลเดอร์ปลายทาง");
  }
  return { targetPath };
}

export function bindArtHandlers() {
  dom.uploadManualArtBtn.addEventListener("click", async () => {
    let basics;
    try {
      basics = ensureArtBasics();
    } catch (err) {
      await Swal.fire({ icon: "warning", title: "ข้อมูลไม่ครบ", text: err.message });
      return;
    }

    const formData = new FormData();
    formData.append("target_path", basics.targetPath);
    formData.append("game_name", dom.artGameNameInput.value.trim() || "");
    formData.append("source_filename", dom.artSourceFilenameInput.value.trim() || "");
    const fileMap = [
      ["cov", dom.artCovInput],
      ["cov2", dom.artCov2Input],
      ["bg", dom.artBgInput],
      ["scr", dom.artScrInput],
      ["scr2", dom.artScr2Input],
      ["lgo", dom.artLgoInput],
      ["ico", dom.artIcoInput],
      ["lab", dom.artLabInput],
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

    store.activeController = new AbortController();
    startOperation("กำลังอัปโหลด ART แบบกำหนดเอง...");
    setState(STATES.ARTING, "กำลังอัปโหลดไฟล์ ART แบบกำหนดเอง");
    try {
      const result = await callApi("/api/art/manual", {
        method: "POST",
        body: formData,
        signal: store.activeController.signal,
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
      store.activeController = null;
      endOperation();
    }
  });

  dom.searchAutoArtBtn.addEventListener("click", async () => {
    let basics;
    try {
      basics = ensureArtBasics();
    } catch (err) {
      await Swal.fire({ icon: "warning", title: "ข้อมูลไม่ครบ", text: err.message });
      return;
    }

    const payload = {
      target_path: basics.targetPath,
      game_name: dom.artGameNameInput.value.trim() || null,
      source_filename: dom.artSourceFilenameInput.value.trim() || null,
      max_results: 10,
    };

    store.activeController = new AbortController();
    startOperation("กำลังค้นหา ART...");
    setState(STATES.ARTING, "กำลังค้นหาภาพ ART");
    try {
      const result = await callApi("/api/art/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: store.activeController.signal,
      });
      setGeneratedGameId(result.details?.game_id || "");
      store.autoCandidates = result.details?.candidates || [];
      renderAutoCandidates(store.autoCandidates);
      setState(readApiState(result.state), result.message);
      appendLog("success", result.message, {
        count: store.autoCandidates.length,
        provider: result.details?.provider_used,
        cache_hit: result.details?.cache_hit,
      });
    } catch (err) {
      if (err.name === "AbortError") {
        setState(STATES.CANCELLED, "ยกเลิกการค้นหา ART แล้ว");
        return;
      }
      setState(STATES.FAILED, err.message || "การค้นหา ART ล้มเหลว");
      await Swal.fire({ icon: "error", title: "ค้นหาไม่สำเร็จ", text: err.message || "การค้นหา ART ล้มเหลว" });
    } finally {
      store.activeController = null;
      endOperation();
    }
  });

  dom.saveAutoArtBtn.addEventListener("click", async () => {
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
      const candidate = store.autoCandidates.find((c) => c.candidate_id === candidateId);
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

    store.activeController = new AbortController();
    startOperation("กำลังบันทึก ART ที่เลือก...");
    setState(STATES.ARTING, "กำลังบันทึกไฟล์ ART ที่เลือก");
    try {
      const result = await callApi("/api/art/save-auto", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_path: basics.targetPath,
          game_name: dom.artGameNameInput.value.trim() || null,
          source_filename: dom.artSourceFilenameInput.value.trim() || null,
          selections,
        }),
        signal: store.activeController.signal,
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
      store.activeController = null;
      endOperation();
    }
  });
}
