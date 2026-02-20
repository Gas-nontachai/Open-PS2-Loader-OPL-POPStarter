import { renderSteps } from "./ui.js";

export async function callApi(url, options) {
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
