/* NEON CORTEX — App shell, login, navigation, UI helpers (v2.1 — simplified login) */
"use strict";

/* ── App state ── */
const App = {
  state: { guild: null, channels: {}, members: {} },
  tab: "dashboard",

  getChannels(g) { return App.state.channels[g]; },

  async task(fn, opts = {}) {
    const p = typeof fn === "function" ? fn() : fn;
    const r = await (opts.long ? withLongTimeout(p) : p);
    UI.toast("success", r.message || "تمت العملية بنجاح");
    return r;
  },

  async selectGuild(id) {
    App.state.guild = String(id);
    const sel = $("guildSelect");
    if (sel) sel.value = String(id);
    const opt = sel && sel.selectedOptions[0] ? sel.selectedOptions[0].textContent : id;
    UI.toast("info", `🌐 السيرفر المحدد: ${opt}`);
    render(App.tab);
  },

  showLogin() {
    $("loginOverlay").classList.remove("hidden");
    $("app").classList.add("hidden");
  },

  showApp() {
    $("loginOverlay").classList.add("hidden");
    $("app").classList.remove("hidden");
  },
};

function withLongTimeout(promise, ms = 600000) {
  return Promise.race([
    promise,
    new Promise((_, rej) => setTimeout(() => rej(new Error("انتهت مهلة العملية الطويلة")), ms)),
  ]);
}

/* ── UI helpers ── */
const UI = {
  toast(type, msg) {
    const wrap = $("toastWrap");
    const icons = { success: "✅", error: "❌", info: "💡", warn: "⚠️" };
    const t = document.createElement("div");
    t.className = `toast ${type}`;
    t.innerHTML = `<span>${icons[type] || "ℹ️"}</span><span>${esc(msg)}</span>`;
    wrap.appendChild(t);
    setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 320); }, 4500);
  },

  modal(config) {
    const box = $("modalBox");
    box.innerHTML = `
      <h3>${config.title}<button class="modal-close" onclick="UI.closeModal()">✕</button></h3>
      <div>${config.body || ""}</div>`;
    if (config.actions) {
      const wrap = document.createElement("div");
      wrap.className = "modal-actions";
      wrap.innerHTML = config.actions;
      box.appendChild(wrap);
    }
    $("modalWrap").classList.remove("hidden");
  },

  closeModal() {
    $("modalWrap").classList.add("hidden");
    $("modalBox").innerHTML = "";
  },

  confirm(title, text, cb) {
    UI.modal({
      title,
      body: `<div style="color:var(--text-dim);font-size:14px;line-height:1.8">${esc(text)}</div>`,
      actions: `
        <button class="btn btn-ghost" onclick="UI.closeModal()">إلغاء</button>
        <button class="btn btn-danger" onclick="(async()=>{UI.closeModal(); try{await cb_confirm()}catch(e){UI.toast('error',e.message)}})()">تأكيد</button>`,
    });
    window.cb_confirm = cb;
  },

  prompt(title, text) {
    return new Promise(resolve => {
      window._promptResolve = resolve;
      UI.modal({
        title,
        body: `
          <label>${esc(text)}</label>
          <input id="promptInput" class="input" style="direction:ltr;text-align:left" autofocus />`,
        actions: `
          <button class="btn btn-ghost" onclick="UI.closeModal();if(_promptResolve)_promptResolve(null)">إلغاء</button>
          <button class="btn btn-primary" onclick="const v=$('promptInput').value.trim();UI.closeModal();if(_promptResolve)_promptResolve(v)">حفظ</button>`,
      });
      setTimeout(() => { if ($("promptInput")) $("promptInput").focus(); }, 60);
    });
  },
};

/* ── Theme Toggle ── */
const THEMES = ["dark", "light", "neon", "cyberpunk"];
const THEME_ICONS = { dark: "🌙", light: "☀️", neon: "💚", cyberpunk: "💜" };

function initTheme() {
  const saved = localStorage.getItem("nc_theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
  updateThemeIcon(saved);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme");
  const idx = THEMES.indexOf(current);
  const next = THEMES[(idx + 1) % THEMES.length];
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("nc_theme", next);
  updateThemeIcon(next);
}

function updateThemeIcon(theme) {
  const btn = $("themeToggle");
  if (btn) btn.textContent = THEME_ICONS[theme] || "🌙";
}

/* ── Background particles ── */
(function initParticles() {
  const canvas = $("particles");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let W, H, parts = [];
  const COLORS = ["rgba(88,101,242,.55)", "rgba(34,211,238,.5)", "rgba(232,121,249,.45)"];

  function resize() {
    W = canvas.width = innerWidth;
    H = canvas.height = innerHeight;
  }
  resize();
  addEventListener("resize", resize);

  const COUNT = 90;
  for (let i = 0; i < COUNT; i++) {
    parts.push({
      x: Math.random() * W, y: Math.random() * H,
      r: Math.random() * 2.2 + 0.6,
      c: COLORS[Math.floor(Math.random() * COLORS.length)],
      vx: (Math.random() - 0.5) * 0.35,
      vy: (Math.random() - 0.5) * 0.35,
      tw: Math.random() * Math.PI * 2,
    });
  }

  function frame() {
    ctx.clearRect(0, 0, W, H);
    for (const p of parts) {
      p.x += p.vx; p.y += p.vy; p.tw += 0.03;
      if (p.x < 0) p.x = W; if (p.x > W) p.x = 0;
      if (p.y < 0) p.y = H; if (p.y > H) p.y = 0;
      const a = 0.35 + Math.sin(p.tw) * 0.3;
      ctx.globalAlpha = Math.max(0.05, a);
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = p.c;
      ctx.fill();
    }
    ctx.globalAlpha = 0.08;
    ctx.strokeStyle = "#5865f2";
    ctx.lineWidth = 0.6;
    for (let i = 0; i < parts.length; i++) {
      for (let j = i + 1; j < parts.length; j++) {
        const dx = parts[i].x - parts[j].x, dy = parts[i].y - parts[j].y;
        const d = Math.hypot(dx, dy);
        if (d < 120) {
          ctx.globalAlpha = 0.10 * (1 - d / 120);
          ctx.beginPath();
          ctx.moveTo(parts[i].x, parts[i].y);
          ctx.lineTo(parts[j].x, parts[j].y);
          ctx.stroke();
        }
      }
    }
    ctx.globalAlpha = 1;
    requestAnimationFrame(frame);
  }
  frame();
})();

/* ── Auth Flow (مبسّط — توكن فقط) ── */
async function doConnect() {
  const token = $("tokenInput").value.trim();
  if (!token) { UI.toast("warn", "أدخل توكن البوت"); return; }
  if (token.length < 50) { UI.toast("warn", "التوكن يبدو غير صحيح — تحقق من نسخه بالكامل"); return; }
  const btn = $("connectBtn");
  btn.disabled = true;
  $("connectSpinner").classList.remove("hidden");
  $("connectBtnText").textContent = "جارٍ الاتصال...";
  $("loginError").classList.add("hidden");
  try {
    const r = await API.connect(token);
    UI.toast("success", r.message);
    await enterApp();
  } catch (e) {
    $("loginError").textContent = "❌ خطأ: " + e.message;
    $("loginError").classList.remove("hidden");
    UI.toast("error", e.message);
  } finally {
    btn.disabled = false;
    $("connectSpinner").classList.add("hidden");
    $("connectBtnText").textContent = "🔌 تشغيل البوت";
  }
}

async function enterApp() {
  App.showApp();
  await refreshGuilds();
  render("dashboard");
  updateBotPill();
  startPolling();
}

async function refreshGuilds() {
  try {
    const data = await API.guilds();
    const sel = $("guildSelect");
    sel.innerHTML = data.guilds.map(g => `<option value="${g.id}">${esc(g.name)} (${g.member_count})</option>`).join("");
    if (data.guilds.length && !App.state.guild) {
      App.state.guild = String(data.guilds[0].id);
      sel.value = App.state.guild;
    }
    updateBotPill();
  } catch (e) {
    UI.toast("error", e.message);
  }
}

function updateBotPill() {
  API.status().then(st => {
    $("botName").textContent = st.ready ? st.user : "غير متصل";
    ["headDot", "sideDot"].forEach(id => {
      $(id).classList.toggle("online", st.ready);
    });
    $("sideStatus").textContent = st.ready ? `متصل · ${st.guilds} سيرفر` : "غير متصل";
  }).catch(() => {});
}

async function doDisconnect() {
  UI.confirm("⏻ قطع الاتصال", "هل تريد قطع الاتصال بالبوت؟", async () => {
    try {
      await API.disconnect();
      API.clearSession();
      UI.toast("info", "تم قطع الاتصال");
      location.reload();
    } catch (e) { UI.toast("error", e.message); }
  });
}

/* ── Polling ── */
let pollTimer = null;
function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      const st = await API.status();
      if (!st.ready) {
        clearInterval(pollTimer); pollTimer = null;
        UI.toast("warn", "⚠️ انقطع اتصال البوت");
        $("loginOverlay").classList.remove("hidden");
        $("app").classList.add("hidden");
        return;
      }
      if (App.tab === "dashboard") loadActivity();
    } catch (e) { /* offline-api */ }
  }, 5000);
}

/* ── Navigation ── */
const TITLES = {
  dashboard: "لوحة التحكم",
  messages: "الرسائل",
  channels: "القنوات",
  members: "الأعضاء",
  music: "الموسيقى",
  roles: "الأدوار",
  automod: "الإشراف الآلي",
  welcome: "الترحيب",
  tickets: "التذاكر",
  polls: "الاستطلاعات",
  automation: "الأتمتة",
  emojis: "الرموز التعبيرية",
  soundboard: "لوحة الصوت",
  structure: "الهيكل والنسخ",
  dmail: "الإرسال الجماعي",
  search: "بحث الموحد",
  audit: "سجل التغييرات",
  tools: "الأدوات",
  protection: "حماية السيرفر",
  stats: "الإحصائيات المباشرة",
  welcomeCard: "بطاقة الترحيب",
  embedBuilder: "منشئ Embed",
  login: "تسجيل الدخول",
  antinuke: "Anti-Nuke",
  verification: "نظام التحقق",
  reactionRoles: "رولات بالتفاعل",
  giveaways: "السحب والجوائز",
  levels: "المستويات",
  customCommands: "أوامر مخصصة",
  birthdays: "أعياد الميلاد",
  afk: "الغياب",
  suggestions: "الاقتراحات",
  webhooks: "Webhooks",
  emojiManager: "إدارة الرموز",
  roleHierarchy: "شجرة الأدوار",
  invites: "تتبع الدعوات",
  voiceConnected: "الصوت المتصل",
  botStatus: "حالة البوت",
  cmdStats: "إحصائيات الأوامر",
  errors: "الأخطاء",
  performance: "الأداء",
  scheduled: "رسائل مجدولة",
};

function render(tab) {
  App.tab = tab;
  $("pageTitle").textContent = TITLES[tab] || "لوحة التحكم";
  document.querySelectorAll(".nav-item").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
  const fn = window.Views[tab];
  if (fn) fn().catch(e => UI.toast("error", e.message));
  if (window.innerWidth <= 900) document.querySelector(".sidebar").classList.remove("open");
}

/* ── Wire events ── */
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  $("themeToggle").addEventListener("click", toggleTheme);
  $("connectBtn").addEventListener("click", doConnect);
  $("toggleToken").addEventListener("click", () => {
    const i = $("tokenInput");
    i.type = i.type === "password" ? "text" : "password";
  });
  $("disconnectBtn").addEventListener("click", doDisconnect);
  $("refreshBtn").addEventListener("click", async () => { await refreshGuilds(); render(App.tab); UI.toast("info", "تم التحديث"); });
  $("hamburger").addEventListener("click", () => document.querySelector(".sidebar").classList.toggle("open"));

  document.querySelectorAll(".nav-item").forEach(b => {
    b.addEventListener("click", () => render(b.dataset.tab));
  });

  $("guildSelect").addEventListener("change", () => {
    App.state.guild = $("guildSelect").value || null;
    render(App.tab);
  });

  $("modalWrap").addEventListener("click", e => {
    if (e.target === e.currentTarget && !window._modalLocked) UI.closeModal();
  });

  $("tokenInput").addEventListener("keydown", e => {
    if (e.key === "Enter") doConnect();
  });

  API.status().then(st => {
    if (st.ready) {
      enterApp();
    }
  }).catch(() => {});
});
