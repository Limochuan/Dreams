// ========================
// 基础配置
// ========================
const API_BASE = ""; // 如果是前后端分离部署，这里填后端地址，例如 "http://127.0.0.1:8000"

const Dreams = {
  // ========================
  // 1. Token / 用户信息管理
  // ========================
  setToken: (t) => localStorage.setItem("dreams_token", t),
  getToken: () => localStorage.getItem("dreams_token"),
  
  setUid: (uid) => localStorage.setItem("dreams_uid", String(uid)),
  getUid: () => localStorage.getItem("dreams_uid"),

  // 登出：清除数据并跳回登录页
  logout: () => {
    localStorage.removeItem("dreams_token");
    localStorage.removeItem("dreams_uid");
    // 只有当前不在登录页时才跳转，防止死循环
    if (!location.pathname.includes("login.html")) {
        location.href = "./login.html";
    }
  },

  // ========================
  // 2. HTTP 请求封装 (自动带 Token)
  // ========================
  
  // GET 请求：自动在 URL 后追加 ?token=xxx
  async apiGet(path) {
    const token = Dreams.getToken();
    let url = API_BASE + path;

    // 如果有 token，拼接到 URL 参数中
    if (token) {
      // 判断 URL 里是否已经有 ? 了
      const separator = url.includes("?") ? "&" : "?";
      url += `${separator}token=${encodeURIComponent(token)}`;
    }

    try {
      const r = await fetch(url, { method: "GET" });
      if (r.status === 401 || r.status === 403) {
        // 如果后端返回 401/403，说明 Token 过期或非法
        Dreams.logout();
        return { error: "登录已过期，请重新登录" };
      }
      return await r.json();
    } catch (e) {
      console.error(e);
      return { error: "网络连接失败" };
    }
  },

  // POST 请求：自动在 JSON Body 里追加 { token: xxx }
  async apiPost(path, body = {}) {
    const token = Dreams.getToken();
    
    // 自动注入 token 到 body
    if (token) {
        body.token = token;
    }

    try {
      const r = await fetch(API_BASE + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      
      // 注意：登录接口本身可能会报 400 错误（密码错），不应该自动登出
      // 只有非登录页面的 401 才需要登出
      if (r.status === 401 && !path.includes("/login")) {
          Dreams.logout();
      }
      
      return await r.json();
    } catch (e) {
      console.error(e);
      return { error: "网络连接失败" };
    }
  },

  // 获取当前用户信息
  async apiMe() {
    // 复用上面的 apiGet，它会自动带上 token
    const d = await Dreams.apiGet("/api/me");
    if (d && !d.error) return d;
    return null;
  },

  // ========================
  // 3. WebSocket 封装 (核心)
  // ========================
  
  /**
   * 连接 WebSocket
   * @param {number} conversationId - 会话ID
   * @param {function} onMessage - 接收到消息时的回调函数
   * @returns WebSocket 对象
   */
  connectChat: (conversationId, onMessage) => {
    const token = Dreams.getToken();
    if (!token) return null;

    // 自动判断协议：如果是 https 页面则用 wss，否则用 ws
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const host = location.host; // 例如 127.0.0.1:8000

    // ⚠️ 关键：Token 必须放在 URL 参数里，适配后端 main.py
    const wsUrl = `${protocol}//${host}/ws/${conversationId}?token=${encodeURIComponent(token)}`;
    
    console.log("Connecting WS:", wsUrl);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log(`Connected to room ${conversationId}`);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data); // 把解析好的 JSON 数据传给回调
      } catch (e) {
        console.error("WS Message Parse Error", e);
      }
    };

    ws.onclose = (e) => {
      console.log("WS Closed", e.code, e.reason);
      // 如果后端因为 Token 无效拒绝连接 (code 1008)，则登出
      if (e.code === 1008) {
          alert("连接验证失败，请重新登录");
          Dreams.logout();
      }
    };

    return ws;
  },

  // ========================
  // 4. 工具函数
  // ========================
  
  getQueryParam: (name) => {
    const url = new URL(window.location.href);
    return url.searchParams.get(name);
  },

  fileToBase64: (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
    });
  },

  escapeHtml: (s) => {
    return (s || "").replace(/[&<>"']/g, (c) => {
      const m = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
      return m[c];
    });
  }
};

// 挂载到 window
window.Dreams = Dreams;
