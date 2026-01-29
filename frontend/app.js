// ========================
// 基础配置
// ========================

// 同域部署时：API_BASE 留空即可
// 例如：前端文件和 FastAPI 在同一个域名 / 同一个 Railway 服务
// 如果前后端分开部署，需要填写后端服务地址
// 示例：const API_BASE = "https://xxx.up.railway.app"
const API_BASE = "";


// ========================
// Token / UID 本地存储
// ========================

// 保存登录 token
function setToken(t) {
  localStorage.setItem("dreams_token", t);
}

// 读取登录 token
function getToken() {
  return localStorage.getItem("dreams_token");
}

// 清除登录状态
function clearToken() {
  localStorage.removeItem("dreams_token");
  localStorage.removeItem("dreams_uid");
}

// 保存当前用户 UID
function setUid(uid) {
  localStorage.setItem("dreams_uid", String(uid));
}

// 读取当前用户 UID
function getUid() {
  return localStorage.getItem("dreams_uid");
}


// ========================
// HTTP 请求封装
// ========================

// GET 请求封装
async function apiGet(path) {
  const r = await fetch(API_BASE + path, {
    method: "GET",
  });
  return r.json();
}

// POST 请求封装
async function apiPost(path, body) {
  const r = await fetch(API_BASE + path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body || {}),
  });
  return r.json();
}


// ========================
// 当前用户信息
// ========================

// 获取当前登录用户信息
// 内部逻辑：
// - 从 localStorage 取 token
// - 请求 /api/me
// - 如果 token 无效，返回 null
async function apiMe() {
  const token = getToken();
  if (!token) return null;

  const d = await apiGet(`/api/me?token=${encodeURIComponent(token)}`);
  if (d && !d.error) return d;

  return null;
}


// ========================
// URL 参数工具
// ========================

// 从当前 URL 中读取指定 query 参数
// 示例：?conversation_id=12
function getQueryParam(name) {
  const url = new URL(window.location.href);
  return url.searchParams.get(name);
}


// ========================
// 文件工具（头像上传）
// ========================

// 将 File 对象转换为 base64 字符串
// 用于头像上传
// 返回格式：data:image/png;base64,...
function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = () => {
      resolve(reader.result);
    };

    reader.onerror = reject;

    reader.readAsDataURL(file);
  });
}


// ========================
// 安全工具
// ========================

// HTML 转义
// 防止聊天内容直接插入 innerHTML 导致 XSS
function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => {
    const m = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    };
    return m[c];
  });
}


// ========================
// 全局导出
// ========================

// 统一挂载到 window，供 HTML 页面直接调用
window.Dreams = {
  API_BASE,

  setToken,
  getToken,
  clearToken,

  setUid,
  getUid,

  apiGet,
  apiPost,
  apiMe,

  getQueryParam,
  fileToBase64,
  escapeHtml,
};
