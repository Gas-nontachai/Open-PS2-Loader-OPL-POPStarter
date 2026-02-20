import { STATES } from "../constants.js";
import { dom } from "../dom.js";
import { store } from "../store.js";
import { callApi } from "../api.js";
import { appendLog, endOperation, readApiState, setState, startOperation, updateArtSourceChoices } from "../ui.js";

export function bindImportHandlers() {
  dom.validateBtn.addEventListener("click", async () => {
    const targetPath = dom.targetPathInput.value.trim();
    if (!targetPath) {
      appendLog("error", "ต้องระบุโฟลเดอร์ปลายทาง");
      return;
    }

    store.activeController = new AbortController();
    startOperation("กำลังตรวจสอบปลายทาง..");
    setState(STATES.VALIDATING, "กำลังตรวจสอบปลายทางและโครงสร้างโฟลเดอร์");

    try {
      const payload = { target_path: targetPath, ensure_folders: true };
      const result = await callApi("/api/validate-target", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: store.activeController.signal,
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
      store.activeController = null;
      endOperation();
    }
  });

  dom.form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const targetPath = dom.targetPathInput.value.trim();
    const files = dom.isoFilesInput.files;

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
    formData.append("overwrite", dom.overwriteInput.checked ? "true" : "false");
    Array.from(files).forEach((file) => formData.append("files", file));

    store.activeController = new AbortController();
    startOperation("กำลังเตรียมนำเข้า...");
    setState(STATES.IMPORTING, "กำลังเตรียมและนำเข้าไฟล์");

    try {
      const result = await callApi("/api/import", {
        method: "POST",
        body: formData,
        signal: store.activeController.signal,
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
      store.activeController = null;
      endOperation();
    }
  });
}
