import { STATES } from "../constants.js";
import { dom } from "../dom.js";
import { store } from "../store.js";
import { callApi } from "../api.js";
import { appendLog, endOperation, readApiState, setState, startOperation, updateArtSourceChoices } from "../ui.js";

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderGamesTable(games = []) {
  if (!dom.gamesTableBody) return;

  if (!games.length) {
    dom.gamesTableBody.innerHTML = `
      <tr>
        <td colspan="7" class="games-empty">ไม่พบเกมใน CD/DVD</td>
      </tr>
    `;
    return;
  }

  dom.gamesTableBody.innerHTML = games
    .map((game) => {
      const safeId = game.game_id || "-";
      const safeName = game.game_name || "-";
      const safeFile = game.destination_filename || "-";
      const safeFolder = game.target_folder || "-";
      const safeSize = game.size_human || "-";
      const artNames = (game.art_files || []).join(", ");
      const canDelete = Boolean(game.game_id);
      return `
        <tr>
          <td><span class="game-id-chip">${escapeHtml(safeId)}</span></td>
          <td>${escapeHtml(safeName)}</td>
          <td>${escapeHtml(safeFile)}</td>
          <td>${escapeHtml(safeFolder)}</td>
          <td>${escapeHtml(safeSize)}</td>
          <td title="${escapeHtml(artNames)}">${game.art_count || 0}</td>
          <td>
            <button
              type="button"
              class="btn btn-rose btn-sm delete-game-btn"
              data-game-id="${escapeHtml(game.game_id || "")}"
              data-destination-filename="${escapeHtml(safeFile)}"
              ${canDelete ? "" : "disabled"}
            >
              ลบเกม
            </button>
          </td>
        </tr>
      `;
    })
    .join("");
}

function formatPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) return "0.00%";
  return `${numeric.toFixed(2)}%`;
}

function renderStorageSummary(games = [], storage = null) {
  if (!dom.storageSummary) return;

  const gameCount = games.length;
  const gamesBytes = games.reduce((total, game) => total + Number(game.size_bytes || 0), 0);
  const fallbackGamesSize = `${(gamesBytes / (1024 ** 3)).toFixed(2)} GB`;
  const safeStorage = storage || {};

  const gamesSizeText = safeStorage.games_human || fallbackGamesSize;
  const usedSizeText = safeStorage.used_human || "-";
  const freeSizeText = safeStorage.free_human || "-";
  const totalSizeText = safeStorage.total_human || "-";
  const usagePercentText = formatPercent(safeStorage.used_percent || 0);
  const usageBarPercent = Math.min(Math.max(Number(safeStorage.used_percent || 0), 0), 100);

  dom.summaryGameCount.textContent = String(gameCount);
  dom.summaryGamesSize.textContent = gamesSizeText;
  dom.summaryUsedSize.textContent = usedSizeText;
  dom.summaryFreeSize.textContent = freeSizeText;
  dom.storageMeterBar.style.width = `${usageBarPercent}%`;
  dom.summaryUsageText.textContent = usedSizeText === "-" ? "ยังไม่สแกน" : `${usedSizeText} / ${totalSizeText} (${usagePercentText})`;
}

async function scanGames({ silent = false } = {}) {
  const targetPath = dom.targetPathInput.value.trim();
  if (!targetPath) {
    if (!silent) {
      appendLog("error", "ต้องระบุโฟลเดอร์ปลายทางก่อนสแกน");
    }
    return [];
  }

  store.activeController = new AbortController();
  startOperation("กำลังสแกนเกมในไดรฟ์...");
  setState(STATES.VALIDATING, "กำลังสแกนเกมในโฟลเดอร์ CD/DVD");
  try {
    const result = await callApi("/api/games/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_path: targetPath }),
      signal: store.activeController.signal,
    });
    const games = result.details?.games || [];
    const storage = result.details?.storage || null;
    store.scannedGames = games;
    store.storageSummary = storage;
    renderGamesTable(games);
    renderStorageSummary(games, storage);
    setState(readApiState(result.state), `สแกนเกมเสร็จแล้ว (${games.length} เกม)`);
    appendLog("success", `สแกนเกมเสร็จแล้ว (${games.length} เกม)`, { target: targetPath });
    const sourceChoices = games.map((game) => game.destination_filename).filter(Boolean);
    if (sourceChoices.length > 0) {
      updateArtSourceChoices(sourceChoices, sourceChoices[0]);
    }
    return games;
  } catch (err) {
    if (err.name === "AbortError") {
      setState(STATES.CANCELLED, "ยกเลิกการสแกนเกมแล้ว");
      appendLog("info", "ผู้ใช้ยกเลิกการสแกนเกม");
      return [];
    }
    setState(STATES.FAILED, err.message || "การสแกนเกมล้มเหลว");
    appendLog("error", err.message || "การสแกนเกมล้มเหลว", err.payload?.details || null);
    if (!silent) {
      await Swal.fire({
        icon: "error",
        title: "สแกนเกมไม่สำเร็จ",
        text: err.message || "การสแกนเกมล้มเหลว",
      });
    }
    return [];
  } finally {
    store.activeController = null;
    endOperation();
  }
}

export function bindImportHandlers() {
  dom.scanGamesBtn?.addEventListener("click", async () => {
    await scanGames();
  });

  dom.gamesTableBody?.addEventListener("click", async (event) => {
    const target = event.target.closest(".delete-game-btn");
    if (!target) return;

    const gameId = target.dataset.gameId || "";
    const destinationFilename = target.dataset.destinationFilename || "";
    if (!gameId) {
      await Swal.fire({
        icon: "warning",
        title: "ลบไม่ได้",
        text: "ไม่พบ Game ID ในชื่อไฟล์เกมนี้",
      });
      return;
    }

    const confirm = await Swal.fire({
      icon: "warning",
      title: "ยืนยันลบเกม?",
      html: `
        <p>Game ID: <b>${gameId}</b></p>
        <p>ไฟล์: <b>${destinationFilename}</b></p>
        <p>ระบบจะลบไฟล์เกมและ ART ที่ผูกกับ ID นี้ทั้งหมด</p>
      `,
      showCancelButton: true,
      confirmButtonText: "ลบเลย",
      confirmButtonColor: "#e11d48",
      cancelButtonText: "ยกเลิก",
    });
    if (!confirm.isConfirmed) return;

    const targetPath = dom.targetPathInput.value.trim();
    if (!targetPath) {
      appendLog("error", "ต้องระบุโฟลเดอร์ปลายทาง");
      return;
    }

    store.activeController = new AbortController();
    startOperation("กำลังลบเกม...");
    setState(STATES.IMPORTING, `กำลังลบเกม ${gameId}`);
    try {
      const result = await callApi("/api/games/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_path: targetPath,
          game_id: gameId,
          destination_filename: destinationFilename,
        }),
        signal: store.activeController.signal,
      });
      appendLog("success", result.message, result.details);
      setState(readApiState(result.state), `ลบเกม ${gameId} สำเร็จ`);
      await Swal.fire({
        icon: "success",
        title: "ลบเกมสำเร็จ",
        text: `ลบ ${gameId} เรียบร้อยแล้ว`,
      });
      await scanGames({ silent: true });
    } catch (err) {
      if (err.name === "AbortError") {
        setState(STATES.CANCELLED, "ยกเลิกการลบเกมแล้ว");
        return;
      }
      setState(STATES.FAILED, err.message || "ลบเกมไม่สำเร็จ");
      appendLog("error", err.message || "ลบเกมไม่สำเร็จ", err.payload?.details || null);
      await Swal.fire({
        icon: "error",
        title: "ลบไม่สำเร็จ",
        text: err.message || "ลบเกมไม่สำเร็จ",
      });
    } finally {
      store.activeController = null;
      endOperation();
    }
  });

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
      await scanGames({ silent: true });
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
      await scanGames({ silent: true });
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
