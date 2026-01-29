// ========= 基础配置 =========
// 同域部署：API_BASE 留空即可（推荐）
// 如果你前端和后端分开部署，填后端域名，例如：const API_BASE="https://xxx.up.railway.app"
const API_BASE = "";

// ========= 存取 token =========
function setToken(t) {
  localStorage.setItem("dreams_token", t);
}
function getToken() {
  return localStorage.getItem("dreams_token");
}
function clearToken() {
  localStorage.removeItem("dreams_token");
  localStorage.removeItem("dreams_uid");
}
function setUid(uid) {
  localStorage.setItem("dreams_uid", String(uid));
}
function getUid() {
  return localStorage.getItem("dreams_uid");
}

// ========= HTTP 请求封装 =========
async function apiGet(path) {
  const r = await fetch(API_BASE + path, { method: "GET" });
  return r.json();
}

async function apiPost(path, body) {
  const r = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return r.json();
}

// ========= 用户信息 =========
async function apiMe() {
  const token = getToken();
  if (!token) return null;
  const d = await apiGet(`/api/me?token=${encodeURIComponent(token)}`);
  if (d && !d.error) return d;
  return null;
}

// ========= 工具：读取 URL 参数 =========
function getQueryParam(name) {
  const url = new URL(window.location.href);
  return url.searchParams.get(name);
}

// ========= 工具：文件转 base64（头像） =========
function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result); // data:image/...base64,...
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// ========= 工具：HTML 转义 =========
function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => {
    const m = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
    return m[c];
  });
}

// ========= 导出（给 HTML 调用） =========
window.Dreams = {
  API_BASE,
  setToken, getToken, clearToken,
  setUid, getUid,
  apiGet, apiPost, apiMe,
  getQueryParam,
  fileToBase64,
  escapeHtml,
};
