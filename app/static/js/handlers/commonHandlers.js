import { STATES } from "../constants.js";
import { dom } from "../dom.js";
import { store } from "../store.js";
import { callApi } from "../api.js";
import {
  appendLog,
  endOperation,
  readApiState,
  setState,
  shouldBlockTabClose,
  startOperation,
  switchTab,
  updateArtSourceChoices,
} from "../ui.js";

export function bindCommonHandlers() {
  window.addEventListener("beforeunload", (event) => {
    if (!shouldBlockTabClose()) {
      return;
    }
    event.preventDefault();
    event.returnValue = "";
  });

  dom.cancelBtn.addEventListener("click", () => {
    if (!store.activeController) {
      return;
    }
    store.activeController.abort();
  });

  dom.pickFolderBtn.addEventListener("click", async () => {
    startOperation("กำลังเปิดหน้าต่างเลือกโฟลเดอร์...");
    try {
      const result = await callApi("/api/pick-target-folder", { method: "GET" });
      if (result.details?.target) {
        dom.targetPathInput.value = result.details.target;
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

  dom.formatBtn.addEventListener("click", async () => {
    const targetPath = dom.targetPathInput.value.trim();
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

    store.activeController = new AbortController();
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
        signal: store.activeController.signal,
      });

      if (result.details?.target) {
        dom.targetPathInput.value = result.details.target;
      }

      setState(readApiState(result.state), result.message);
      appendLog("success", result.message, result.details);
      await Swal.fire({ icon: "success", title: "ฟอร์แมตเสร็จสิ้น", text: result.message });
    } catch (err) {
      if (err.name === "AbortError") {
        setState(STATES.CANCELLED, "ยกเลิกการฟอร์แมตแล้ว");
        appendLog("info", "ผู้ใช้ยกเลิกการฟอร์แมต");
        await Swal.fire({ icon: "info", title: "ยกเลิกแล้ว", text: "คำสั่งฟอร์แมตถูกยกเลิก" });
        return;
      }

      setState(STATES.FAILED, err.message || "ฟอร์แมตล้มเหลว");
      appendLog("error", err.message || "การฟอร์แมตล้มเหลว", err.payload?.details || null);
      await Swal.fire({ icon: "error", title: "ฟอร์แมตไม่สำเร็จ", text: err.message || "ฟอร์แมตล้มเหลว" });
    } finally {
      store.activeController = null;
      endOperation();
    }
  });

  dom.artModeSelect.addEventListener("change", () => {
    const mode = dom.artModeSelect.value;
    dom.manualArtBlock.classList.toggle("hidden", mode !== "manual");
    dom.autoArtBlock.classList.toggle("hidden", mode !== "auto");
  });

  dom.isoFilesInput.addEventListener("change", () => {
    const uploaded = Array.from(dom.isoFilesInput.files || []).map((file) => file.name);
    if (uploaded.length > 0) {
      updateArtSourceChoices(uploaded, uploaded[0]);
    }
  });

  if (dom.artSourceSelect) {
    dom.artSourceSelect.addEventListener("change", () => {
      const selected = dom.artSourceSelect.value.trim();
      if (selected) {
        dom.artSourceFilenameInput.value = selected;
      }
    });
  }

  if (dom.tabImportBtn && dom.tabArtBtn) {
    dom.tabImportBtn.addEventListener("click", () => switchTab("import"));
    dom.tabArtBtn.addEventListener("click", () => switchTab("art"));
    switchTab("import");
  }
}
