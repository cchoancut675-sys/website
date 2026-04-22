// ============================================================
// api.js — Giao tiếp với Cloudflare Worker để gọi Gemini Vision
// ============================================================

const WORKER_URL = "https://your-worker.your-subdomain.workers.dev"; // 👈 thay URL worker của bạn

/**
 * Gửi ảnh + prompt lên Worker → Gemini Vision trả lời
 * @param {string} prompt - Câu hỏi / mô tả task
 * @param {Array}  images - Mảng { data: base64, mimeType: "image/png" }
 * @returns {Promise<string>} - Câu trả lời từ AI
 */
export async function askGemini(prompt, images = []) {
  const res = await fetch(WORKER_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, images })
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || "Worker error");
  }

  const data = await res.json();
  return data.answer || "";
}

/**
 * Convert HTMLImageElement hoặc URL ảnh sang base64
 * @param {string} imgUrl
 * @returns {Promise<{data: string, mimeType: string}>}
 */
export async function imageUrlToBase64(imgUrl) {
  const res = await fetch(imgUrl);
  const blob = await res.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const base64 = reader.result.split(",")[1];
      resolve({ data: base64, mimeType: blob.type || "image/png" });
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

/**
 * Giải hCaptcha image selection challenge
 * @param {string} taskText  - Ví dụ: "Please click each image containing a bicycle"
 * @param {string[]} imgUrls - Mảng URL của các ô ảnh trong challenge
 * @returns {Promise<number[]>} - Mảng index các ảnh cần click (0-based)
 */
export async function solveImageChallenge(taskText, imgUrls) {
  // Convert tất cả ảnh sang base64
  const images = await Promise.all(imgUrls.map(url => imageUrlToBase64(url)));

  const prompt = `You are solving an hCaptcha image selection challenge.
Task: "${taskText}"
There are ${imgUrls.length} images provided (in order, starting from index 0).
Look at ALL images carefully and identify which ones match the task description.
Reply ONLY with a JSON array of 0-based indexes of matching images.
Example reply: [0, 2, 5]
If none match, reply: []`;

  const answer = await askGemini(prompt, images);

  // Parse JSON array từ response
  try {
    const match = answer.match(/\[[\d,\s]*\]/);
    if (match) return JSON.parse(match[0]);
  } catch (_) {}
  return [];
}
