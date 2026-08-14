/* NEON CORTEX — All page views */
"use strict";

/* Shared helpers ---------------------------------------------------- */
function $(id) { return document.getElementById(id); }

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function curGuild() { return App.state.guild; }

function requireGuild() {
  const g = curGuild();
  if (!g) { UI.toast("warn", "⚠️ اختر سيرفراً أولاً من القائمة العلوية"); return null; }
  return g;
}

function avatarHtml(m) {
  if (m.avatar) return `<img class="avatar" src="${esc(m.avatar)}" alt="" />`;
  const letter = (m.display_name || "?").trim()[0] || "?";
  return `<div class="avatar placeholder">${esc(letter)}</div>`;
}

async function channelOptions(filter) {
  const g = requireGuild();
  if (!g) return "";
  let list = App.getChannels(g);
  if (!list) {
    try { list = (await API.guildChannels(g)).channels; App.state.channels[g] = list; }
    catch (e) { UI.toast("error", e.message); return ""; }
  }
  if (filter) list = list.filter(c => c.type === filter);
  return list.map(c => {
    const cat = c.category ? ` (${esc(c.category)})` : "";
    return `<option value="${c.id}">${c.icon} ${esc(c.name)}${cat}</option>`;
  }).join("");
}

function channelName(g, id) {
  const list = App.getChannels(g) || [];
  const c = list.find(x => x.id === id);
  return c ? `${c.icon} ${c.name}` : String(id);
}

/* ── Dashboard ─────────────────────────────────────────────────── */
async function viewDashboard() {
  const view = $("view");
  view.innerHTML = `
    <div id="dashHero" class="card glass neon-frame">
      <div class="loading"><div class="loader"></div><span>تجميع البيانات الحية...</span></div>
    </div>
    <div id="dashBody"></div>`;
  await loadDashHero();
  await loadDashGuilds();
}

async function loadDashHero() {
  const el = $("dashHero");
  if (!el) return;
  try {
    const st = await API.status();
    const g = curGuild();
    let statsRows = "";
    let guildTile = "";
    if (g) {
      try {
        const s = (await API.guildStats(g)).stats;
        statsRows = `
          <div class="stat-tile"><div class="s-icon">👥</div><div class="s-value">${s.members}</div><div class="s-label">الأعضاء</div></div>
          <div class="stat-tile tile-cyan"><div class="s-icon">💬</div><div class="s-value">${s.text_channels}</div><div class="s-label">قنوات نصية</div></div>
          <div class="stat-tile tile-magenta"><div class="s-icon">🔊</div><div class="s-value">${s.voice_channels}</div><div class="s-label">قنوات صوتية</div></div>
          <div class="stat-tile tile-amber"><div class="s-icon">🎭</div><div class="s-value">${s.roles}</div><div class="s-label">الرولات</div></div>
          <div class="stat-tile tile-green"><div class="s-icon">😀</div><div class="s-value">${s.emojis}</div><div class="s-label">الرموز</div></div>
          <div class="stat-tile"><div class="s-icon">🚀</div><div class="s-value">${s.boost_level}</div><div class="s-label">Boost Level (${s.boosts})</div></div>`;
        guildTile = `<span class="chip">${esc(s.name)}</span>`;
      } catch (e) { /* ignore */ }
    }
    el.innerHTML = `
      <div class="card" style="display:flex;align-items:center;gap:18px;flex-wrap:wrap;box-shadow:none;border:none;background:transparent;padding:0;">
        <div class="logo-ring"><span>⚡</span></div>
        <div style="flex:1;min-width:180px">
          <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
            <h1 class="hero-stat gradient-text">${st.ready ? esc(st.user || "البوت") : "غير متصل"}</h1>
            ${st.ready ? '<span class="chip green">● متصل</span>' : '<span class="chip red">○ غير متصل</span>'}
            ${guildTile}
          </div>
          <div style="color:var(--text-dim);font-size:14px;margin-top:6px">
            ${st.ready ? `${st.guilds} سيرفر · بينج ${st.latency}ms` : "قم بتفعيل البوت من شاشة الدخول"}
          </div>
        </div>
      </div>
      ${statsRows ? `<div class="grid grid-4" style="margin-top:18px">${statsRows}</div>` : ""}`;
  } catch (e) {
    el.innerHTML = `<div class="empty"><div class="e-icon">⚠️</div><div>تعذر جلب الحالة: ${esc(e.message)}</div></div>`;
  }
}

async function loadDashGuilds() {
  const el = $("dashBody");
  if (!el) return;
  try {
    const data = await API.guilds();
    if (!data.guilds.length) {
      el.innerHTML = `<div class="card glass"><div class="empty"><div class="e-icon">🌐</div><div>لا توجد سيرفرات — أضف البوت إلى سيرفر ثم حدّث</div></div></div>`;
      return;
    }
    el.innerHTML = `
      <div class="section-title">🌐 سيرفراتك (${data.guilds.length}) — انقر سيرفراً للتحكم الكامل</div>
      <div class="grid grid-3">
        ${data.guilds.map(g => `
          <div class="server-card" onclick="App.selectGuild('${g.id}')">
            <div class="sc-banner">
              ${g.banner || g.icon ? `<img src="${esc(g.banner || g.icon)}" alt="" />` : `<div class="sc-empty"></div>`}
            </div>
            <div class="sc-icon">
              ${g.icon ? `<img src="${esc(g.icon)}" alt="" />` : `<div class="ph">${esc(g.name.charAt(0) || "?")}</div>`}
            </div>
            <div class="sc-body">
              <div class="sc-name">${esc(g.name)}</div>
              <div class="sc-meta">
                <span>👥 ${g.member_count}</span>
                <span>💬 ${g.text_channels}</span>
                <span>🔊 ${g.voice_channels}</span>
                <span>🚀 L${g.boost_tier}</span>
              </div>
              <div class="sc-chips">
                ${g.verified ? '<span class="chip green">✓ موثّق</span>' : ""}
                <span class="chip">${g.id.slice(0, 6)}…</span>
              </div>
              <button class="btn btn-primary w-full">🎯 التحكم بهذا السيرفر</button>
            </div>
          </div>`).join("")}
      </div>
      <div class="section-title">📡 النشاط المباشر</div>
      <div class="card glass"><div id="activityFeed" class="activity-list"></div></div>`;
    await loadActivity();
  } catch (e) {
    el.innerHTML = `<div class="card glass"><div class="empty"><div class="e-icon">⚠️</div><div>${esc(e.message)}</div></div></div>`;
  }
}

async function loadActivity() {
  const feed = $("activityFeed");
  if (!feed) return;
  try {
    const data = await API.activity();
    feed.innerHTML = data.entries.length
      ? data.entries.map(en => {
          const m = en.match(/^\[(.*?)\]\s?(.*)$/);
          const ts = m ? m[1] : "";
          const msg = m ? m[2] : en;
          return `<div class="activity-entry"><span class="ts">${ts}</span>${esc(msg)}</div>`;
        }).join("")
      : `<div class="empty"><div class="e-icon">📡</div><div>لا نشاط بعد</div></div>`;
  } catch (e) {
    feed.innerHTML = `<div class="empty"><div>${esc(e.message)}</div></div>`;
  }
}

/* ── Messages ─────────────────────────────────────────────────── */
async function viewMessages() {
  if (!requireGuild()) return;
  const view = $("view");
  view.innerHTML = `
    <div class="card glass">
      <h3>💬 الرسائل <span class="sub">إرسال مباشر</span></h3>
      <div class="field"><label>القناة المستهدفة</label><select id="msgChannel" class="input"></select></div>
      <div class="field"><label>نص الرسالة</label><textarea id="msgContent" class="input" rows="4" placeholder="اكتب الرسالة هنا..."></textarea></div>
      <button class="btn btn-primary" onclick="sendOne()">🚀 إرسال</button>
    </div>

    <div class="grid grid-2">
      <div class="card glass">
        <h3>⚡ إرسال جماعي متسلسل</h3>
        <div class="field"><label>القناة</label><select id="bulkChannel" class="input"></select></div>
        <div class="field"><label>الرسائل (كل سطر = رسالة)</label><textarea id="bulkContent" class="input" rows="6" placeholder="رسالة 1&#10;رسالة 2&#10;رسالة 3"></textarea></div>
        <div class="field-row">
          <div class="field"><label>التأخير (ثوانٍ)</label><input id="bulkDelay" type="number" class="input" value="1" min="0" step="0.5" /></div>
        </div>
        <button class="btn btn-cyan w-full" onclick="sendBulk()">⛓️ تشغيل الحزمة</button>
      </div>
      <div class="card glass">
        <h3>🗑️ مسح الرسائل</h3>
        <div class="field"><label>القناة</label><select id="purgeChannel" class="input"></select></div>
        <div class="field"><label>العدد</label><input id="purgeLimit" type="number" class="input" value="100" min="1" max="1000" /></div>
        <button class="btn btn-danger w-full" onclick="doPurge()">🧨 مسح</button>
      </div>
    </div>

    <div class="card glass">
      <h3>🖼️ منشئ الـ Embed الفخم</h3>
      <div class="field"><label>القناة</label><select id="embedChannel" class="input"></select></div>
      <div class="field-row">
        <div class="field"><label>العنوان</label><input id="ebTitle" class="input" /></div>
        <div class="field"><label>اللون</label><input id="ebColor" type="color" class="input" value="#5865f2" style="height:44px;padding:4px" /></div>
      </div>
      <div class="field"><label>الوصف</label><textarea id="ebDesc" class="input" rows="3"></textarea></div>
      <div class="field-row">
        <div class="field"><label>المؤلف (Author)</label><input id="ebAuthor" class="input" /></div>
        <div class="field"><label>أيقونة المؤلف</label><input id="ebAuthorIcon" class="input" placeholder="https://..." /></div>
      </div>
      <div class="field-row">
        <div class="field"><label>الفوتر (Footer)</label><input id="ebFooter" class="input" /></div>
        <div class="field"><label>الصورة الرمزية</label><input id="ebThumb" class="input" placeholder="https://..." /></div>
      </div>
      <div class="field-row">
        <div class="field"><label>صورة كبيرة</label><input id="ebImage" class="input" placeholder="https://..." /></div>
        <div class="field" style="display:flex;align-items:flex-end;justify-content:space-between;gap:10px">
          <label style="margin:0"><input type="checkbox" id="ebTimestamp" /> وقت تلقائي</label>
        </div>
      </div>
      <div class="field"><label>الحقول (مفاتيح عشوائية — الاسم: القيمة)</label><textarea id="ebFields" class="input" rows="3" placeholder="الرابط: https://...&#10;الحالة: مفعلة"></textarea></div>
      <div class="field"><label>الأزرار (الاسم: الرابط)</label><textarea id="ebButtons" class="input" rows="2" placeholder="زر رائع: https://..."></textarea></div>
      <button class="btn btn-magenta" style="background:linear-gradient(135deg,var(--magenta),#a21caf)" onclick="sendEmbed()">✨ إرسال Embed</button>
    </div>`;

  const opts = await channelOptions("text");
  ["msgChannel", "bulkChannel", "purgeChannel", "embedChannel"].forEach(id => $(id).innerHTML = opts);
}

async function sendOne() {
  const ch = $("msgChannel").value, content = $("msgContent").value.trim();
  if (!ch || !content) return UI.toast("warn", "أكمل القناة والنص");
  try { await App.task(API.sendMessage(ch, content)); } catch (e) { UI.toast("error", e.message); }
}

async function sendBulk() {
  const ch = $("bulkChannel").value;
  const lines = $("bulkContent").value.split("\n").filter(x => x.trim());
  const delay = parseFloat($("bulkDelay").value) || 1;
  if (!ch || !lines.length) return UI.toast("warn", "أكمل القناة والرسائل");
  UI.toast("info", `⛓️ بدء إرسال ${lines.length} رسالة...`);
  try { await App.task(API.bulkSend(ch, lines, delay)); } catch (e) { UI.toast("error", e.message); }
}

async function doPurge() {
  const ch = $("purgeChannel").value, limit = parseInt($("purgeLimit").value) || 100;
  if (!ch) return UI.toast("warn", "اختر قناة");
  UI.confirm("🧨 مسح الرسائل", `تأكيد مسح آخر ${limit} رسالة من القناة؟`, async () => {
    try { await App.task(API.purge(ch, limit)); } catch (e) { UI.toast("error", e.message); }
  });
}

async function sendEmbed() {
  const ch = $("embedChannel").value;
  if (!ch) return UI.toast("warn", "اختر قناة");
  const embed = {
    title: $("ebTitle").value.trim(),
    description: $("ebDesc").value.trim(),
    color: $("ebColor").value,
    author: $("ebAuthor").value.trim(),
    author_icon: $("ebAuthorIcon").value.trim(),
    footer: $("ebFooter").value.trim(),
    thumbnail: $("ebThumb").value.trim(),
    image: $("ebImage").value.trim(),
    timestamp: $("ebTimestamp").checked,
    fields: [],
    buttons: [],
  };
  $("ebFields").value.split("\n").forEach(l => {
    const idx = l.indexOf(":");
    if (idx > 0) embed.fields.push({ name: l.slice(0, idx).trim(), value: l.slice(idx + 1).trim(), inline: true });
  });
  $("ebButtons").value.split("\n").forEach(l => {
    const idx = l.indexOf(":");
    if (idx > 0) embed.buttons.push({ label: l.slice(0, idx).trim(), url: l.slice(idx + 1).trim() });
  });
  try { await App.task(API.sendEmbed(ch, embed)); } catch (e) { UI.toast("error", e.message); }
}

/* ── Channels ─────────────────────────────────────────────────── */
async function viewChannels() {
  if (!requireGuild()) return;
  const view = $("view");
  view.innerHTML = `
    <div class="card glass">
      <h3>📁 القنوات</h3>
      <div class="grid grid-2">
        <div>
          <div class="field-row">
            <div class="field"><label>الاسم</label><input id="chName" class="input" /></div>
            <div class="field"><label>النوع</label><select id="chType" class="input">
              <option value="text">💬 نصية</option><option value="voice">🔊 صوتية</option></select></div>
          </div>
          <div class="field"><label>الفئة (اختياري)</label><select id="chCat" class="input"><option value="">بدون فئة</option></select></div>
          <button class="btn btn-success" onclick="createChannel()">➕ إنشاء القناة</button>
        </div>
        <div>
          <div class="field"><label>بحث</label><input id="chSearch" class="input" placeholder="تصفية حسب الاسم..." oninput="renderChannelList()" /></div>
          <div id="channelList" class="list" style="max-height:420px"></div>
        </div>
      </div>
    </div>`;

  try {
    const data = await API.guildChannels(curGuild());
    App.state.channels[curGuild()] = data.channels;
    const cats = data.channels.filter(c => c.type === "category");
    $("chCat").innerHTML = `<option value="">بدون فئة</option>` + cats.map(c => `<option value="${c.id}">📁 ${esc(c.name)}</option>`).join("");
    renderChannelList();
  } catch (e) { UI.toast("error", e.message); }
}

function renderChannelList() {
  const list = (App.getChannels(curGuild()) || []).filter(c => c.type !== "category");
  const q = ($("chSearch") ? $("chSearch").value : "").toLowerCase();
  const filtered = q ? list.filter(c => c.name.toLowerCase().includes(q)) : list;
  const box = $("channelList");
  if (!box) return;
  if (!filtered.length) { box.innerHTML = `<div class="empty"><div class="e-icon">📂</div><div>لا قنوات</div></div>`; return; }
  box.innerHTML = filtered.map(c => `
    <div class="list-item">
      <div class="li-info">
        <div class="li-title">${c.icon} ${esc(c.name)}</div>
        <div class="li-sub">ID: ${c.id}${c.category ? " · " + esc(c.category) : ""}${c.slowmode ? " · ⏳" + c.slowmode + "s" : ""}</div>
      </div>
      <div class="li-actions">
        <button class="btn btn-ghost btn-sm" onclick="copyText('${c.id}')" title="نسخ ID">📋</button>
        <button class="btn btn-danger btn-sm" onclick="delChannel('${c.id}')">🗑</button>
      </div>
    </div>`).join("");
}

async function createChannel() {
  const g = curGuild();
  const name = $("chName").value.trim();
  const type = $("chType").value;
  const cat = $("chCat").value || null;
  if (!name) return UI.toast("warn", "اكتب اسم القناة");
  try {
    await App.task(API.createChannel(g, name, type, cat));
    $("chName").value = "";
    const data = await API.guildChannels(g);
    App.state.channels[g] = data.channels;
    renderChannelList();
  } catch (e) { UI.toast("error", e.message); }
}

function delChannel(id) {
  UI.confirm("🗑️ حذف قناة", "هل تريد حذف هذه القناة نهائياً؟", async () => {
    try {
      await App.task(API.deleteChannel(id));
      const data = await API.guildChannels(curGuild());
      App.state.channels[curGuild()] = data.channels;
      renderChannelList();
    } catch (e) { UI.toast("error", e.message); }
  });
}

/* ── Members ─────────────────────────────────────────────────── */
async function viewMembers() {
  if (!requireGuild()) return;
  const view = $("view");
  view.innerHTML = `
    <div class="card glass">
      <h3>👥 الأعضاء والتعديلات الإدارية</h3>
      <div class="field-row" style="align-items:end">
        <div class="field"><label>بحث</label><input id="mbSearch" class="input" placeholder="اسم العضو..." oninput="renderMemberList()" /></div>
        <div class="field" style="flex:0 0 auto"><label>إدخال ID مباشر</label><input id="rawId" class="input" placeholder="مثال: 123456789" /></div>
      </div>
      <div id="memberList" class="list" style="max-height:500px"></div>
    </div>`;
  await loadMembers();
}

async function loadMembers() {
  const g = curGuild();
  try {
    const data = await API.guildMembers(g);
    App.state.members[g] = data.members;
    renderMemberList();
  } catch (e) { UI.toast("error", e.message); }
}

function renderMemberList() {
  const g = curGuild();
  const members = App.state.members[g] || [];
  const q = ($("mbSearch") ? $("mbSearch").value : "").toLowerCase();
  const filtered = q ? members.filter(m => (m.display_name + m.name).toLowerCase().includes(q)) : members;
  const box = $("memberList");
  if (!box) return;
  if (!filtered.length) { box.innerHTML = `<div class="empty"><div class="e-icon">👤</div><div>لا أعضاء</div></div>`; return; }
  box.innerHTML = filtered.map(m => `
    <div class="list-item">
      ${avatarHtml(m)}
      <div class="li-info">
        <div class="li-title">${esc(m.display_name)} ${m.bot ? '<span class="chip cyan">بوت</span>' : ""}</div>
        <div class="li-sub">${esc(m.name)} · ${esc(m.top_role)}</div>
      </div>
      <div class="li-actions">
        <button class="btn btn-ghost btn-sm" onclick="showWarnsModal('${m.id}')" title="التحديث/التحذيرات">⚠️</button>
        <button class="btn btn-sm" style="background:rgba(251,191,36,.15);color:var(--amber);border:1px solid rgba(251,191,36,.3)" onclick="doTimeout('${m.id}')">⏱</button>
        <button class="btn btn-danger btn-sm" onclick="doKick('${m.id}')">👢</button>
        <button class="btn btn-danger btn-sm" onclick="doBan('${m.id}')">⛔</button>
      </div>
    </div>`).join("");
}

function memberName(id) {
  const g = curGuild();
  const m = (App.state.members[g] || []).find(x => x.id === id);
  return m ? m.display_name : String(id);
}

async function doKick(id) {
  const reason = await UI.prompt("👢 طرد عضو", `سبب طرد ${memberName(id)}:`);
  if (reason === null) return;
  try { await App.task(API.kick(curGuild(), id, reason)); } catch (e) { UI.toast("error", e.message); }
}

async function doBan(id) {
  const reason = await UI.prompt("⛔ حظر عضو", `سبب حظر ${memberName(id)}:`);
  if (reason === null) return;
  try { await App.task(API.ban(curGuild(), id, reason)); } catch (e) { UI.toast("error", e.message); }
}

async function doTimeout(id) {
  const minutes = await UI.prompt("⏱️ تايم أوت", `عدد الدقائق لـ ${memberName(id)}:`);
  if (!minutes || isNaN(minutes)) return;
  const reason = await UI.prompt("⏱️ السبب (اختياري)", "");
  try { await App.task(API.timeout(curGuild(), id, parseInt(minutes), reason || "")); } catch (e) { UI.toast("error", e.message); }
}

async function warnMember(id) {
  const reason = await UI.prompt("⚠️ تحذير عضو", `سبب تحذير ${memberName(id)} (3 تحذيرات = حظر تلقائي):`);
  if (!reason) return;
  try { await App.task(API.warn(curGuild(), id, reason)); } catch (e) { UI.toast("error", e.message); }
}

async function showWarnsModal(id) {
  try {
    const data = await API.getWarns(curGuild(), id);
    const warns = data.warns || [];
    UI.modal({
      title: `⚠️ تحذيرات ${esc(memberName(id))}`,
      body: `
        ${warns.length ? warns.map((w, i) => `
          <div class="activity-entry" style="margin-bottom:8px">
            <b>#${i + 1}</b> ${esc(w.reason)}
            <div class="li-sub">${esc(w.date)} · بواسطة ${esc(w.moderator)}</div>
          </div>`).join("")
        : `<div class="empty"><div class="e-icon">🛡️</div><div>لا تحذيرات لهذا العضو</div></div>`}
        <div style="display:flex;gap:10px;margin-top:14px">
          <button class="btn" style="background:rgba(251,191,36,.15);color:var(--amber);border:1px solid rgba(251,191,36,.4);flex:1" onclick="warnBtn('${id}')">⚠️ تحذير الآن</button>
          <button class="btn btn-danger" style="flex:1" onclick="clearBtn('${id}')">🧹 مسح التحذيرات</button>
        </div>`,
    });
  } catch (e) { UI.toast("error", e.message); }
}

async function warnBtn(id) {
  UI.closeModal();
  const reason = await UI.prompt("⚠️ تحذير", "السبب:");
  if (!reason) return;
  try { await App.task(API.warn(curGuild(), id, reason)); } catch (e) { UI.toast("error", e.message); }
}

async function clearBtn(id) {
  try { await App.task(API.clearWarns(curGuild(), id)); } catch (e) { UI.toast("error", e.message); }
  UI.closeModal();
}

async function triggerWarn(id) {
  const reason = await UI.prompt("⚠️ تحذير", "السبب:");
  if (!reason) return;
  try { await App.task(API.warn(curGuild(), id, reason)); } catch (e) { UI.toast("error", e.message); }
}

async function clearMemberWarns(id) {
  try { await App.task(API.clearWarns(curGuild(), id)); } catch (e) { UI.toast("error", e.message); }
}

/* ── Music ─────────────────────────────────────────────────── */
function fmtDur(d) {
  if (!d) return "0:00";
  const m = Math.floor(d / 60), s = d % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function fmtTime(s) {
  if (!s) return "0:00";
  const m = Math.floor(s / 60), sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

async function viewMusic() {
  if (!requireGuild()) return;
  const view = $("view");
  view.innerHTML = `
    <div class="card glass" id="musicNowPlaying" style="display:none"></div>

    <div class="grid grid-2">
      <div class="card glass">
        <h3>🔌 أجهزة الصوت</h3>
        <div class="field"><label>القناة الصوتية</label><select id="vcChannel" class="input"></select></div>
        <div style="display:flex;gap:10px">
          <button class="btn btn-success" style="flex:1" onclick="joinVoice()">🔌 دخول</button>
          <button class="btn btn-danger" style="flex:1" onclick="leaveVoice()">⏻ خروج</button>
        </div>
        <div style="margin-top:12px">
          <button class="btn btn-cyan w-full" onclick="sendMusicPanel()">📤 إرسال Panel للموسيقى</button>
          <p class="hint" style="margin-top:6px">يظهر Panel تلقائياً في القناة الصوتية لما البوت يدخلها</p>
        </div>
        <div class="section-title">🎶 بحث وتشغيل</div>
        <div class="field"><label>اسم الأغنية أو الرابط</label><input id="ytQuery" class="input" placeholder="اكتب اسم الأغنية..." onkeydown="if(event.key==='Enter')searchMusic()" /></div>
        <div style="display:flex;gap:10px">
          <button class="btn btn-cyan" style="flex:1" onclick="searchMusic()">🔎 بحث</button>
          <button class="btn btn-cyan btn-ghost" style="flex:1" onclick="playNow($('ytQuery').value.trim())">▶️ تشغيل</button>
        </div>
        <div id="musicResults" class="list" style="max-height:260px;margin-top:10px"></div>
        <div class="section-title">🔗 أو بلينك مباشر</div>
        <input id="ytUrl" class="input" placeholder="https://www.youtube.com/watch?v=..." onkeydown="if(event.key==='Enter')playNow($('ytUrl').value.trim())" />
        <button class="btn btn-cyan w-full" onclick="playNow($('ytUrl').value.trim())" style="margin-top:8px">▶️ تشغيل أو إضافة</button>
      </div>
      <div class="card glass">
        <h3>🎛️ التحكم بالموسيقى</h3>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px">
          <button class="btn btn-ghost" id="btnPause" onclick="togglePause()" title="إيقاف/استئناف">⏸</button>
          <button class="btn btn-ghost" onclick="skipTrack()" title="تخطي">⏭️</button>
          <button class="btn btn-ghost" onclick="stopTrack()" title="إيقاف">⏹️</button>
          <button class="btn btn-ghost" onclick="clearQueue()" title="مسح القائمة">🧹</button>
        </div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px">
          <button class="btn btn-ghost btn-sm" id="btnLoop" onclick="toggleLoopBtn()" title="تكرار الأغنية">🔁</button>
          <button class="btn btn-ghost btn-sm" id="btnQueueLoop" onclick="toggleQueueLoopBtn()" title="تكرار القائمة">🔂</button>
          <button class="btn btn-ghost btn-sm" id="btnShuffle" onclick="toggleShuffleBtn()" title="خلط">🔀</button>
        </div>
        <div style="display:flex;gap:10px;align-items:center;margin-bottom:12px">
          <button class="btn btn-ghost btn-sm" id="btnStay" onclick="toggleStayBtn()" title="البقاء في القناة">🏠</button>
          <span style="font-size:12px;color:var(--text-faint)" id="stayLabel">البقاء: معطّل</span>
        </div>
        <div class="section-title">🔊 الصوت — <span class="range-val" id="volVal">100%</span></div>
        <input type="range" id="volRange" min="5" max="200" value="100" oninput="$('volVal').textContent=this.value+'%'" onchange="setVol(this.value)" />
      </div>
    </div>
    <div class="card glass">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <h3 style="margin:0">📃 قائمة التشغيل</h3>
        <button class="btn btn-ghost btn-sm" onclick="loadMusicStatus()">⟳ تحديث</button>
      </div>
      <div id="musicQueue" class="list" style="max-height:280px"></div>
    </div>
    <div class="card glass">
      <h3>💻 كونسول الأوامر</h3>
      <p class="hint">اكتب أمراً مثل <code>!play اسم الأغنية</code> أو <code>!search كلمة</code> وشوف رد البوت مباشرة هنا.</p>
      <div class="field"><label>الأمر</label><input id="cmdInput" class="input" placeholder="!play Imagine Dragons" onkeydown="if(event.key==='Enter')runConsoleCommand()" /></div>
      <button class="btn btn-cyan w-full" onclick="runConsoleCommand()">▶️ تنفيذ الأمر</button>
      <div id="cmdLog" class="cmd-log"></div>
    </div>`;

  const vcOpts = await channelOptions("voice");
  $("vcChannel").innerHTML = vcOpts;
  await loadMusicStatus();
}

let _musicInterval = null;

async function loadMusicStatus() {
  const g = requireGuild(); if (!g) return;
  try {
    const st = await API.musicStatus(g);
    const npBox = $("musicNowPlaying");
    const np = st.now_playing;

    if (np && npBox) {
      npBox.style.display = "block";
      const elapsed = st.elapsed || 0;
      const dur = st.duration || 0;
      const pct = dur > 0 ? Math.min(100, (elapsed / dur) * 100) : 0;
      npBox.innerHTML = `
        <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">
          ${st.thumbnail ? `<img src="${esc(st.thumbnail)}" style="width:100px;height:100px;border-radius:12px;object-fit:cover;border:2px solid var(--cyan);box-shadow:0 0 20px rgba(34,211,238,0.3)" />` : '<div style="width:100px;height:100px;border-radius:12px;background:linear-gradient(135deg,var(--blurple),var(--cyan));display:flex;align-items:center;justify-content:center;font-size:40px">🎵</div>'}
          <div style="flex:1;min-width:200px">
            <div style="font-size:11px;color:var(--cyan);margin-bottom:4px;font-weight:700">🎶 يُعزف الآن</div>
            <div style="font-size:18px;font-weight:800;color:#fff;margin-bottom:4px">${esc(np)}</div>
            <div style="font-size:12px;color:var(--text-dim);margin-bottom:8px">
              ${st.requester ? `بواسطة ${esc(st.requester)}` : ""} ${st.channel ? `في #${esc(st.channel)}` : ""}
            </div>
            <div style="display:flex;align-items:center;gap:8px">
              <span style="font-size:11px;color:var(--text-faint);font-family:monospace">${fmtTime(elapsed)}</span>
              <div style="flex:1;height:4px;border-radius:4px;background:rgba(88,101,242,0.2);overflow:hidden">
                <div style="height:100%;width:${pct}%;background:linear-gradient(90deg,var(--cyan),var(--magenta));border-radius:4px;transition:width 1s"></div>
              </div>
              <span style="font-size:11px;color:var(--text-faint);font-family:monospace">${fmtTime(dur)}</span>
            </div>
          </div>
          <div style="display:flex;gap:6px">
            ${st.loop ? '<span class="chip cyan">🔁</span>' : ""}
            ${st.queue_loop ? '<span class="chip amber">🔂</span>' : ""}
            ${st.shuffle ? '<span class="chip" style="background:rgba(232,121,249,0.15);border-color:rgba(232,121,249,0.3);color:var(--magenta)">🔀</span>' : ""}
          </div>
        </div>`;

      $("btnPause").textContent = st.paused ? "▶️" : "⏸";
    } else if (npBox) {
      npBox.style.display = "none";
    }

    if ($("btnLoop")) {
      $("btnLoop").style.background = st.loop ? "rgba(34,211,238,0.2)" : "";
      $("btnLoop").style.borderColor = st.loop ? "var(--cyan)" : "";
    }
    if ($("btnQueueLoop")) {
      $("btnQueueLoop").style.background = st.queue_loop ? "rgba(251,191,36,0.2)" : "";
      $("btnQueueLoop").style.borderColor = st.queue_loop ? "var(--amber)" : "";
    }
    if ($("btnShuffle")) {
      $("btnShuffle").style.background = st.shuffle ? "rgba(232,121,249,0.2)" : "";
      $("btnShuffle").style.borderColor = st.shuffle ? "var(--magenta)" : "";
    }
    if ($("btnStay")) {
      $("btnStay").style.background = st.stay_in_vc ? "rgba(52,211,153,0.2)" : "";
      $("btnStay").style.borderColor = st.stay_in_vc ? "var(--green)" : "";
      $("stayLabel").textContent = st.stay_in_vc ? "البقاء: مفعّل" : "البقاء: معطّل";
    }

    const qBox = $("musicQueue");
    if (qBox) {
      if (st.queue && st.queue.length) {
        qBox.innerHTML = st.queue.map((t, i) => `
          <div class="list-item" style="padding:8px 12px">
            <div style="width:28px;text-align:center;font-size:13px;color:var(--cyan);font-weight:800;flex-shrink:0">${i + 1}</div>
            <div class="li-info">
              <div class="li-title" style="font-size:13px">${esc(t.title || "غناء")}</div>
              <div class="li-sub">${t.duration ? fmtDur(t.duration) : ""} ${t.requester ? `· بواسطة ${esc(t.requester)}` : ""}</div>
            </div>
          </div>`).join("");
      } else {
        qBox.innerHTML = `<div class="empty"><div class="e-icon">📃</div><div>القائمة فارغة</div></div>`;
      }
    }

    if (_musicInterval) clearInterval(_musicInterval);
    if (np && !st.paused) {
      let el = elapsed;
      _musicInterval = setInterval(() => {
        el++;
        if (el > dur) el = dur;
        const spans = npBox ? npBox.querySelectorAll("span[style*='monospace']") : [];
        if (spans[0]) spans[0].textContent = fmtTime(el);
        const bar = npBox ? npBox.querySelector("div[style*='height:4px'] > div") : null;
        if (bar && dur) bar.style.width = Math.min(100, (el / dur) * 100) + "%";
      }, 1000);
    }
  } catch (e) {
    const npBox = $("musicNowPlaying");
    if (npBox) npBox.style.display = "none";
  }
}

async function searchMusic() {
  const q = $("ytQuery").value.trim();
  if (!q) return UI.toast("warn", "اكتب اسم الأغنية للبحث");
  const box = $("musicResults");
  box.innerHTML = `<div class="empty"><div class="e-icon">⏳</div><div>جاري البحث...</div></div>`;
  try {
    const r = await App.task(API.musicSearch(curGuild(), q), { long: true });
    if (!r.results.length) { box.innerHTML = `<div class="empty"><div class="e-icon">🔍</div><div>لا نتائج</div></div>`; return; }
    box.innerHTML = r.results.map((t, i) => `
      <div class="list-item" style="padding:8px 12px">
        <div style="width:28px;text-align:center;font-size:12px;color:var(--text-faint);flex-shrink:0">${i + 1}</div>
        <div class="li-info">
          <div class="li-title" style="font-size:13px">${esc(t.title)}</div>
          <div class="li-sub">${esc(t.uploader || "")} ${t.duration ? "· " + fmtDur(t.duration) : ""}</div>
        </div>
        <button class="btn btn-success btn-sm" onclick="playNow(${JSON.stringify(t.url).replace(/"/g, "&quot;")})">▶️</button>
      </div>`).join("");
  } catch (e) { box.innerHTML = `<div class="empty"><div>${esc(e.message)}</div></div>`; }
}

async function playNow(q) {
  q = (q || "").trim();
  if (!q) return UI.toast("warn", "اكتب اسم الأغنية أو الصق رابط");
  try {
    await App.task(API.musicPlay(curGuild(), q, "", ""), { long: true });
    await loadMusicStatus();
  } catch (e) { UI.toast("error", e.message); }
}

function renderEmbed(e) {
  if (!e) return "";
  let h = `<div class="embed"><div class="embed-title">${esc(e.title || "")}</div>`;
  if (e.description) h += `<div class="embed-desc">${esc(e.description).replace(/\n/g, "<br>")}</div>`;
  if (e.fields && e.fields.length) {
    h += `<div class="embed-fields">` + e.fields.map(f => `
      <div class="embed-field"><div class="ef-name">${esc(f.name)}</div><div class="ef-val">${esc(f.value).replace(/\n/g, "<br>")}</div></div>`).join("") + `</div>`;
  }
  h += `</div>`;
  return h;
}

async function runConsoleCommand() {
  const inp = $("cmdInput");
  const cmd = (inp.value || "").trim();
  if (!cmd) return UI.toast("warn", "اكتب أمراً");
  const log = $("cmdLog");
  const vcSel = $("vcChannel");
  const vcId = vcSel && vcSel.value ? Number(vcSel.value) : null;
  log.innerHTML += `<div class="cmd-line cmd-user"><span class="cmd-prompt">›</span> ${esc(cmd)}</div>`;
  inp.value = "";
  try {
    const r = await App.task(API.musicCommand(curGuild(), cmd, vcId), { long: true });
    let out = `<div class="cmd-line cmd-bot">`;
    if (r.content) out += `<div>${esc(r.content).replace(/\n/g, "<br>")}</div>`;
    if (r.embed) out += renderEmbed(r.embed);
    out += `</div>`;
    log.innerHTML += out;
    await loadMusicStatus();
  } catch (e) {
    log.innerHTML += `<div class="cmd-line cmd-bot cmd-err">${esc(e.message)}</div>`;
  }
  log.scrollTop = log.scrollHeight;
}

async function joinVoice() {
  const ch = $("vcChannel").value;
  if (!ch) return UI.toast("warn", "اختر قناة صوتية");
  try { await App.task(API.voiceJoin(curGuild(), ch)); await loadMusicStatus(); } catch (e) { UI.toast("error", e.message); }
}

async function leaveVoice() {
  try { await App.task(API.voiceLeave(curGuild())); await loadMusicStatus(); } catch (e) { UI.toast("error", e.message); }
}

async function sendMusicPanel() {
  try {
    const st = await API.musicStatus(curGuild());
    if (!st.connected) return UI.toast("warn", "البوت مو في قناة صوتية");
    const vcCh = $("vcChannel").value;
    if (vcCh) {
      await App.task(API.musicPanel(curGuild(), parseInt(vcCh)));
    }
    UI.toast("success", "✅ تم إرسال Panel الموسيقى");
  } catch (e) { UI.toast("error", e.message); }
}

async function savePanelChannel() {}

async function skipTrack() { try { await App.task(API.musicSkip(curGuild())); setTimeout(loadMusicStatus, 500); } catch (e) { UI.toast("error", e.message); } }
async function stopTrack() { try { await App.task(API.musicStop(curGuild())); await loadMusicStatus(); } catch (e) { UI.toast("error", e.message); } }
async function clearQueue() { try { await App.task(API.musicClear(curGuild())); await loadMusicStatus(); } catch (e) { UI.toast("error", e.message); } }
async function setVol(v) { try { await App.task(API.musicVolume(curGuild(), v)); } catch (e) { UI.toast("error", e.message); } }

async function togglePause() {
  try {
    const st = await API.musicStatus(curGuild());
    if (st.paused) { await App.task(API.musicResume(curGuild())); }
    else { await App.task(API.musicPause(curGuild())); }
    await loadMusicStatus();
  } catch (e) { UI.toast("error", e.message); }
}

async function toggleLoopBtn() { try { await App.task(API.musicLoop(curGuild())); await loadMusicStatus(); } catch (e) { UI.toast("error", e.message); } }
async function toggleQueueLoopBtn() { try { await App.task(API.musicQueueLoop(curGuild())); await loadMusicStatus(); } catch (e) { UI.toast("error", e.message); } }
async function toggleShuffleBtn() { try { await App.task(API.musicShuffle(curGuild())); await loadMusicStatus(); } catch (e) { UI.toast("error", e.message); } }
async function toggleStayBtn() { try { await App.task(API.musicStay(curGuild())); await loadMusicStatus(); } catch (e) { UI.toast("error", e.message); } }

/* ── AutoMod ─────────────────────────────────────────────────── */
async function viewAutomod() {
  if (!requireGuild()) return;
  const view = $("view");
  view.innerHTML = `
    <div class="grid grid-2">
      <div class="card glass">
        <h3>🛡️ الإشراف الآلي</h3>
        <div class="field" style="display:flex;align-items:center;justify-content:space-between">
          <div><b>تفعيل المنظومة بالكامل</b><div style="font-size:12px;color:var(--text-faint)">عند الإيقاف لا يعمل أي إشراف</div></div>
          <label class="toggle"><input type="checkbox" id="amEnabled" /><span class="slider"></span></label>
        </div>
        <div class="field" style="display:flex;align-items:center;justify-content:space-between">
          <div><b>حظر منشن @everyone / @here</b></div>
          <label class="toggle"><input type="checkbox" id="amEveryone" /><span class="slider"></span></label>
        </div>
        <div class="field" style="display:flex;align-items:center;justify-content:space-between">
          <div><b>حظر الأحرف الكبيرة المفرطة</b></div>
          <label class="toggle"><input type="checkbox" id="amCaps" /><span class="slider"></span></label>
        </div>
        <div class="field"><label>نسبة الأحرف الكبيرة قبل الحذف (%)</label><input type="range" id="amCapsTh" min="40" max="100" value="70" oninput="$('capsVal').textContent=this.value+'%'" /><div class="range-val" id="capsVal">70%</div></div>
        <button class="btn btn-success w-full" onclick="saveAutomod()">💾 حفظ الإعدادات</button>
      </div>
      <div class="card glass">
        <h3>🚨 الحماية من RAID و SPAM</h3>
        <div class="field" style="display:flex;align-items:center;justify-content:space-between">
          <div><b>حماية RAID (موجة دخول)</b></div>
          <label class="toggle"><input type="checkbox" id="amRaid" /><span class="slider"></span></label>
        </div>
        <div class="field-row">
          <div class="field"><label>عدد الداخلين المطلوب</label><input id="amRaidTh" type="number" class="input" value="8" /></div>
          <div class="field"><label>خلال (ثوانٍ)</label><input id="amRaidWin" type="number" class="input" value="30" /></div>
        </div>
        <div class="field" style="display:flex;align-items:center;justify-content:space-between">
          <div><b>حماية SPAM</b></div>
          <label class="toggle"><input type="checkbox" id="amSpam" /><span class="slider"></span></label>
        </div>
        <div class="field-row">
          <div class="field"><label>عدد الرسائل المطلوب</label><input id="amSpamTh" type="number" class="input" value="5" /></div>
          <div class="field"><label>خلال (ثوانٍ)</label><input id="amSpamWin" type="number" class="input" value="5" /></div>
        </div>
        <button class="btn btn-cyan w-full" onclick="saveAutomod()">💾 حفظ أيضاً</button>
      </div>
    </div>
    <div class="card glass">
      <h3>📋 قناة السجلات (Logs)</h3>
      <div class="field-row">
        <div class="field"><label>قناة سجلات الأحداث</label><select id="logChannel" class="input"></select></div>
        <div class="field" style="flex:0 0 auto"><label>&nbsp;</label><button class="btn btn-primary" onclick="saveLogChannel()">تثبيت</button></div>
      </div>
      <div style="font-size:12px;color:var(--text-faint)">يستقبل: دخول/خروج الأعضاء، حذف وتعديل الرسائل، إنشاء/حذف القنوات، الحظر، تنبيهات الإشراف الآلي.</div>
    </div>`;

  try {
    const cfg = (await API.getAutomod(curGuild())).config;
    $("amEnabled").checked = cfg.enabled;
    $("amEveryone").checked = cfg.block_everyone;
    $("amCaps").checked = cfg.block_caps;
    $("amCapsTh").value = cfg.caps_threshold;
    $("capsVal").textContent = cfg.caps_threshold + "%";
    $("amRaid").checked = cfg.anti_raid;
    $("amRaidTh").value = cfg.raid_threshold;
    $("amRaidWin").value = cfg.raid_window;
    $("amSpam").checked = cfg.anti_spam;
    $("amSpamTh").value = cfg.spam_threshold;
    $("amSpamWin").value = cfg.spam_window;
    const opts = await channelOptions("text");
    $("logChannel").innerHTML = opts;
    const lc = (await API.getLogChannel(curGuild())).channel_id;
    if (lc && $("logChannel").querySelector(`option[value="${lc}"]`)) $("logChannel").value = String(lc);
  } catch (e) { UI.toast("error", e.message); }
}

async function saveAutomod() {
  const g = curGuild();
  const cfg = {
    enabled: $("amEnabled").checked,
    block_everyone: $("amEveryone").checked,
    block_caps: $("amCaps").checked,
    caps_threshold: parseInt($("amCapsTh").value),
    anti_raid: $("amRaid").checked,
    raid_threshold: parseInt($("amRaidTh").value),
    raid_window: parseInt($("amRaidWin").value),
    anti_spam: $("amSpam").checked,
    spam_threshold: parseInt($("amSpamTh").value),
    spam_window: parseInt($("amSpamWin").value),
  };
  try { await App.task(API.setAutomod(g, cfg)); } catch (e) { UI.toast("error", e.message); }
}

async function saveLogChannel() {
  const ch = $("logChannel").value;
  if (!ch) return UI.toast("warn", "اختر قناة سجلات");
  try { await App.task(API.setLogChannel(curGuild(), ch)); } catch (e) { UI.toast("error", e.message); }
}

/* ── Welcome ─────────────────────────────────────────────────── */
async function viewWelcome() {
  if (!requireGuild()) return;
  const view = $("view");
  view.innerHTML = `
    <div class="card glass">
      <h3>👋 نظام الترحيب التلقائي</h3>
      <div class="field" style="display:flex;align-items:center;justify-content:space-between">
        <div><b>تفعيل الترحيب</b><div style="font-size:12px;color:var(--text-faint)">ترسل رسالة عند انضمام عضو جديد</div></div>
        <label class="toggle"><input type="checkbox" id="wlEnabled" /><span class="slider"></span></label>
      </div>
      <div class="field" style="display:flex;align-items:center;justify-content:space-between">
        <div><b>صورة ترحيب فخمة 🖼️</b></div>
        <label class="toggle"><input type="checkbox" id="wlImage" /><span class="slider"></span></label>
      </div>
      <div class="field"><label>قناة الترحيب</label><select id="wlChannel" class="input"></select></div>
      <div class="field"><label>نص الرسالة — المتغيرات: {user} {username} {server} {count}</label>
        <textarea id="wlMsg" class="input" rows="4">مرحباً {user} في سيرفر {server}! 🎉 أنت العضو رقم {count}</textarea></div>
      <button class="btn btn-primary w-full" onclick="saveWelcome()">💾 حفظ إعدادات الترحيب</button>
    </div>`;
  try {
    const cfg = (await API.getWelcome(curGuild())).config;
    $("wlEnabled").checked = cfg.enabled;
    $("wlImage").checked = cfg.image_enabled;
    $("wlMsg").value = cfg.message;
    $("wlChannel").innerHTML = await channelOptions("text");
    if (cfg.channel_id && $("wlChannel").querySelector(`option[value="${cfg.channel_id}"]`)) $("wlChannel").value = cfg.channel_id;
  } catch (e) { UI.toast("error", e.message); }
}

async function saveWelcome() {
  const cfg = {
    enabled: $("wlEnabled").checked,
    image_enabled: $("wlImage").checked,
    channel_id: $("wlChannel").value,
    message: $("wlMsg").value,
  };
  try { await App.task(API.setWelcome(curGuild(), cfg)); } catch (e) { UI.toast("error", e.message); }
}

/* ── Tickets ─────────────────────────────────────────────────── */
async function viewTickets() {
  if (!requireGuild()) return;
  const view = $("view");
  view.innerHTML = `
    <div class="card glass">
      <h3>🎫 نظام التذاكر</h3>
      <div class="grid grid-2">
        <div>
          <div class="field"><label>فئة التذاكر (Category)</label><select id="tkCat" class="input"></select></div>
          <div class="field"><label>رول فريق الدعم</label><select id="tkRole" class="input"></select></div>
          <div class="field"><label>رسالة الترحيب داخل التذكرة</label><textarea id="tkWelcome" class="input" rows="2">مرحباً! سيتم الرد عليك قريباً من قبل فريق الدعم.</textarea></div>
        </div>
        <div>
          <div class="field"><label>عنوان اللوحة</label><input id="tkTitle" class="input" value="🎫 نظام التذاكر" /></div>
          <div class="field"><label>وصف اللوحة</label><textarea id="tkDesc" class="input" rows="2">اضغط على الزر أدناه لفتح تذكرة دعم فني.</textarea></div>
          <div class="field"><label>اللون</label><input id="tkColor" type="color" class="input" value="#5865f2" style="height:44px;padding:4px" /></div>
        </div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button class="btn btn-success" onclick="saveTickets()">💾 حفظ الإعدادات</button>
        <button class="btn btn-cyan" onclick="sendTicketPanel()">📤 إرسال لوحة التذاكر لقناة</button>
        <select id="tkPanelChan" class="input" style="max-width:260px"></select>
      </div>
    </div>`;
  try {
    const data = await API.guildChannels(curGuild());
    App.state.channels[curGuild()] = data.channels;
    $("tkCat").innerHTML = data.channels.filter(c => c.type === "category").map(c => `<option value="${c.id}">📁 ${esc(c.name)}</option>`).join("");
    const roles = (await API.guildRoles(curGuild())).roles.filter(r => !r.default);
    $("tkRole").innerHTML = roles.map(r => `<option value="${r.id}">🎭 ${esc(r.name)}</option>`).join("");
    $("tkPanelChan").innerHTML = await channelOptions("text");
    const cfg = (await API.getTicketsConfig(curGuild())).config;
    if (cfg.category_id) $("tkCat").value = String(cfg.category_id);
    if (cfg.staff_role_id) { const opt = `<option value="${cfg.staff_role_id}" selected>رول محفوظ (${cfg.staff_role_id})</option>`; $("tkRole").insertAdjacentHTML("afterbegin", opt); }
    if (cfg.welcome_msg) $("tkWelcome").value = cfg.welcome_msg;
    if (cfg.panel_title) $("tkTitle").value = cfg.panel_title;
    if (cfg.panel_desc) $("tkDesc").value = cfg.panel_desc;
    if (cfg.color) $("tkColor").value = cfg.color;
  } catch (e) { UI.toast("error", e.message); }
}

async function saveTickets() {
  const cfg = {
    category_id: $("tkCat").value,
    staff_role_id: $("tkRole").value,
    welcome_msg: $("tkWelcome").value,
    panel_title: $("tkTitle").value,
    panel_desc: $("tkDesc").value,
    color: $("tkColor").value,
  };
  if (!cfg.category_id) return UI.toast("warn", "اختر فئة التذاكر");
  try { await App.task(API.setTicketsConfig(curGuild(), cfg)); } catch (e) { UI.toast("error", e.message); }
}

async function sendTicketPanel() {
  const ch = $("tkPanelChan").value;
  if (!ch) return UI.toast("warn", "اختر قناة إرسال اللوحة");
  try { await App.task(API.sendTicketPanel(ch, curGuild())); } catch (e) { UI.toast("error", e.message); }
}

/* ── Automation ─────────────────────────────────────────────────── */
async function viewAutomation() {
  if (!requireGuild()) return;
  const view = $("view");
  view.innerHTML = `
    <div class="grid grid-2">
      <div class="card glass">
        <h3>⏰ التذكيرات</h3>
        <div class="field"><label>القناة</label><select id="rmChannel" class="input"></select></div>
        <div class="field"><label>الرسالة</label><input id="rmMsg" class="input" /></div>
        <div class="field"><label>الوقت (YYYY-MM-DDTHH:MM)</label><input id="rmTime" type="datetime-local" class="input" /></div>
        <button class="btn btn-primary w-full" onclick="addReminder()">➕ إضافة تذكير</button>
        <div class="section-title">قائمة التذكيرات</div>
        <div id="rmList" class="list" style="max-height:280px"></div>
      </div>
      <div class="card glass">
        <h3>📅 الرسائل المجدولة</h3>
        <div class="field"><label>القناة</label><select id="scChannel" class="input"></select></div>
        <div class="field"><label>الرسالة</label><textarea id="scMsg" class="input" rows="2"></textarea></div>
        <div class="field-row">
          <div class="field"><label>الوقت (HH:MM)</label><input id="scTime" type="time" class="input" /></div>
          <div class="field"><label>التكرار</label><select id="scRepeat" class="input">
            <option value="daily">يومياً</option><option value="weekly">أسبوعياً</option><option value="once">مرة واحدة</option></select></div>
        </div>
        <button class="btn btn-cyan w-full" onclick="addScheduled()">➕ إضافة مجدول</button>
        <div class="section-title">قائمة المجدول</div>
        <div id="scList" class="list" style="max-height:280px"></div>
      </div>
    </div>`;

  const g = curGuild();
  try {
    const opts = await channelOptions("text");
    $("rmChannel").innerHTML = opts;
    $("scChannel").innerHTML = opts;
    const rms = (await API.getReminders()).reminders;
    $("rmList").innerHTML = rms.length ? rms.map((r, i) => `
      <div class="list-item"><div class="li-info"><div class="li-title">${esc(r.message || "")}</div>
      <div class="li-sub">#${channelName(g, r.channel_id)} · ${esc(r.timestamp)}</div></div>
      <button class="btn btn-danger btn-sm" onclick="rmReminder(${i})">🗑</button></div>`).join("")
      : `<div class="empty"><div class="e-icon">⏰</div><div>لا تذكيرات</div></div>`;
    const sc = (await API.getScheduled()).scheduled;
    $("scList").innerHTML = sc.length ? sc.map((s, i) => `
      <div class="list-item"><div class="li-info"><div class="li-title">${esc(s.message || "")}</div>
      <div class="li-sub">#${channelName(g, s.channel_id)} · ${esc(s.time)} · ${esc(s.repeat)}</div></div>
      <button class="btn btn-danger btn-sm" onclick="rmScheduled(${i})">🗑</button></div>`).join("")
      : `<div class="empty"><div class="e-icon">📅</div><div>لا رسائل مجدولة</div></div>`;
  } catch (e) { UI.toast("error", e.message); }
}

async function addReminder() {
  const ch = $("rmChannel").value, msg = $("rmMsg").value.trim(), ts = $("rmTime").value;
  if (!ch || !msg || !ts) return UI.toast("warn", "أكمل البيانات");
  try { await App.task(API.addReminder({ channel_id: ch, message: msg, timestamp: ts })); viewAutomation(); } catch (e) { UI.toast("error", e.message); }
}

function rmReminder(i) { UI.confirm("🗑️ حذف", "حذف هذا التذكير؟", async () => { try { await App.task(API.removeReminder(i)); viewAutomation(); } catch (e) { UI.toast("error", e.message); } }); }

async function addScheduled() {
  const ch = $("scChannel").value, msg = $("scMsg").value.trim(), time = $("scTime").value, repeat = $("scRepeat").value;
  if (!ch || !msg || !time) return UI.toast("warn", "أكمل البيانات");
  try { await App.task(API.addScheduled({ channel_id: ch, message: msg, time, repeat })); viewAutomation(); } catch (e) { UI.toast("error", e.message); }
}

function rmScheduled(i) { UI.confirm("🗑️ حذف", "حذف هذه الرسالة المجدولة؟", async () => { try { await App.task(API.removeScheduled(i)); viewAutomation(); } catch (e) { UI.toast("error", e.message); } }); }

/* ── Emojis ─────────────────────────────────────────────────── */
async function viewEmojis() {
  if (!requireGuild()) return;
  const view = $("view");
  view.innerHTML = `
    <div class="card glass">
      <h3>😀 الرموز التعبيرية (Emojis)</h3>
      <div class="grid grid-2">
        <div class="field-row">
          <div class="field"><label>اسم الرمز</label><input id="emName" class="input" /></div>
          <div class="field"><label>رابط الصورة</label><input id="emUrl" class="input" placeholder="https://..." /></div>
        </div>
        <div style="display:flex;align-items:flex-end;gap:10px">
          <button class="btn btn-success" onclick="uploadEmoji()">➤ رفع الرمز</button>
        </div>
      </div>
      <div id="emGrid" class="emoji-grid" style="margin-top:16px"></div>
    </div>

    <div class="card glass">
      <h3>🔄 نقل الإيموجي بين السيرفرات <span class="sub">نسخ جميع الرموز من سيرفر لآخر</span></h3>
      <div class="grid grid-2">
        <div>
          <div class="section-title">📤 السيرفر المصدر</div>
          <div class="field"><label>اختر السيرفر المصدر</label><select id="emSourceGuild" class="input" onchange="loadSourceEmojis()"></select></div>
          <div id="emSourceInfo" style="font-size:13px;color:var(--text-dim);margin-bottom:12px"></div>
          <div id="emSourceList" class="list" style="max-height:250px"></div>
        </div>
        <div>
          <div class="section-title">📥 السيرفر الهدف</div>
          <div class="field"><label>اختر السيرفر الهدف</label><select id="emTargetGuild" class="input"></select></div>
          <div id="emTargetInfo" style="font-size:13px;color:var(--text-dim);margin-bottom:12px"></div>
          <div style="display:flex;flex-direction:column;gap:10px;margin-top:16px">
            <button class="btn btn-primary w-full" onclick="transferSelectedEmojis()">📤 نقل المحدد فقط</button>
            <button class="btn btn-cyan w-full" onclick="transferAllEmojis()">🚀 نقل الكل دفعة واحدة</button>
          </div>
          <div id="emTransferResult" style="margin-top:12px"></div>
        </div>
      </div>
    </div>`;
  await loadEmojis();
  await loadGuildSelectors();
}

async function loadEmojis() {
  const g = curGuild();
  try {
    const data = await API.emojis(g);
    const box = $("emGrid");
    box.innerHTML = data.emojis.length ? data.emojis.map(e => `
      <div class="emoji-tile" onclick="copyText('${esc(e.name)}')" title="نسخ الاسم">
        <img src="${esc(e.url)}" alt="" />
        <div class="e-name">${e.animated ? '<b>GIF</b> ' : ""}${esc(e.name)}</div>
      </div>`).join("")
      : `<div class="empty" style="grid-column:1/-1"><div class="e-icon">😶</div><div>لا رموز في هذا السيرفر</div></div>`;
  } catch (e) { UI.toast("error", e.message); }
}

async function uploadEmoji() {
  const name = $("emName").value.trim(), url = $("emUrl").value.trim();
  if (!name || !url) return UI.toast("warn", "أكمل الاسم والرابط");
  try { await App.task(API.uploadEmoji(curGuild(), name, url)); viewEmojis(); } catch (e) { UI.toast("error", e.message); }
}

async function loadGuildSelectors() {
  try {
    const data = await API.guilds();
    const opts = data.guilds.map(g => `<option value="${g.id}">${esc(g.name)} (${g.member_count})</option>`).join("");
    $("emSourceGuild").innerHTML = opts;
    $("emTargetGuild").innerHTML = opts;
    if (data.guilds.length >= 2) {
      const current = curGuild();
      const other = data.guilds.find(g => g.id !== current);
      if (other) $("emTargetGuild").value = other.id;
    }
    await loadSourceEmojis();
  } catch (e) { UI.toast("error", e.message); }
}

async function loadSourceEmojis() {
  const sourceId = $("emSourceGuild").value;
  if (!sourceId) return;
  try {
    const data = await API.emojis(sourceId);
    const emojis = data.emojis || [];
    $("emSourceInfo").innerHTML = `<span class="chip cyan">${emojis.length} إيموجي</span>`;
    const box = $("emSourceList");
    if (!emojis.length) {
      box.innerHTML = `<div class="empty"><div class="e-icon">😶</div><div>لا إيموجي</div></div>`;
      return;
    }
    box.innerHTML = `
      <div style="margin-bottom:8px;display:flex;align-items:center;justify-content:space-between">
        <label style="margin:0;font-size:13px"><input type="checkbox" id="emSelectAll" onchange="toggleSelectAllEmojis()" /> تحديد الكل</label>
        <span style="font-size:12px;color:var(--text-faint)" id="emSelectedCount">0 محدد</span>
      </div>
      ${emojis.map(e => `
        <div class="list-item" style="cursor:pointer;padding:8px 12px" onclick="this.querySelector('input').click();event.stopPropagation()">
          <input type="checkbox" class="em-checkbox" value="${esc(e.id)}" data-name="${esc(e.name)}" onchange="updateSelectedCount()" style="margin-left:8px" />
          <img src="${esc(e.url)}" style="width:28px;height:28px;object-fit:contain;flex-shrink:0" />
          <div class="li-info">
            <div class="li-title" style="font-size:13px">${e.animated ? '🎬 ' : ''}${esc(e.name)}</div>
          </div>
        </div>`).join("")}
    `;
  } catch (e) { UI.toast("error", e.message); }
}

function toggleSelectAllEmojis() {
  const checked = $("emSelectAll").checked;
  document.querySelectorAll(".em-checkbox").forEach(cb => cb.checked = checked);
  updateSelectedCount();
}

function updateSelectedCount() {
  const count = document.querySelectorAll(".em-checkbox:checked").length;
  $("emSelectedCount").textContent = `${count} محدد`;
}

async function transferSelectedEmojis() {
  const sourceId = $("emSourceGuild").value;
  const targetId = $("emTargetGuild").value;
  if (!sourceId || !targetId) return UI.toast("warn", "اختر السيرفرات");
  if (sourceId === targetId) return UI.toast("warn", "اختر سيرفرات مختلفة");
  const selected = [...document.querySelectorAll(".em-checkbox:checked")].map(cb => cb.value);
  if (!selected.length) return UI.toast("warn", "حدد إيموجي واحد على الأقل");

  UI.confirm("📤 نقل الإيموجي", `هل تريد نقل ${selected.length} إيموجي؟`, async () => {
    const resultBox = $("emTransferResult");
    resultBox.innerHTML = `<div class="loading" style="padding:20px"><div class="loader"></div><span>جاري النقل...</span></div>`;
    try {
      const r = await App.task(API.transferEmoji(sourceId, targetId, selected), { long: true });
      resultBox.innerHTML = `<div class="live-bar"><span>📋</span><div class="lb-info"><div class="lb-title">${esc(r.message)}</div></div></div>`;
      await loadSourceEmojis();
    } catch (e) {
      resultBox.innerHTML = `<div class="live-bar" style="border-color:rgba(244,63,94,0.4)"><span>❌</span><div class="lb-info"><div class="lb-title">${esc(e.message)}</div></div></div>`;
    }
  });
}

async function transferAllEmojis() {
  const sourceId = $("emSourceGuild").value;
  const targetId = $("emTargetGuild").value;
  if (!sourceId || !targetId) return UI.toast("warn", "اختر السيرفرات");
  if (sourceId === targetId) return UI.toast("warn", "اختر سيرفرات مختلفة");

  const sourceName = $("emSourceGuild").selectedOptions[0]?.textContent || "المصدر";
  const targetName = $("emTargetGuild").selectedOptions[0]?.textContent || "الهدف";

  UI.confirm("🚀 نقل جميع الإيموجي", `هل تريد نقل جميع الإيموجي من:\n📤 ${sourceName}\n📥 ${targetName}\n\nسيتم تخطي الموجود مسبقاً.`, async () => {
    const resultBox = $("emTransferResult");
    resultBox.innerHTML = `<div class="loading" style="padding:20px"><div class="loader"></div><span>جاري نقل جميع الإيموجي...</span></div>`;
    try {
      const r = await App.task(API.transferAllEmoji(sourceId, targetId), { long: true });
      resultBox.innerHTML = `<div class="live-bar"><span>📋</span><div class="lb-info"><div class="lb-title">${esc(r.message)}</div></div></div>`;
      await loadSourceEmojis();
    } catch (e) {
      resultBox.innerHTML = `<div class="live-bar" style="border-color:rgba(244,63,94,0.4)"><span>❌</span><div class="lb-info"><div class="lb-title">${esc(e.message)}</div></div></div>`;
    }
  });
}

/* ── Structure / Clone ───────────────────────────────────────── */
async function viewStructure() {
  if (!requireGuild()) return;
  const view = $("view");
  let guildOpts = "";
  try { const gs = (await API.guilds()).guilds; guildOpts = gs.map(g => `<option value="${g.id}">${esc(g.name)}</option>`).join(""); } catch (e) {}
  view.innerHTML = `
    <div class="card glass">
      <h3>🧬 هيكل السيرفر (تصدير)</h3>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        <button class="btn btn-primary" onclick="exportGuild()">📦 تصدير هيكل JSON</button>
        <span style="color:var(--text-faint);font-size:13px">يرصد: الرولات، الفئات، القنوات مع خصائصها</span>
      </div>
      <pre id="exportBox" style="display:none;margin-top:16px;max-height:280px;overflow:auto;background:rgba(8,10,25,.7);border-radius:12px;padding:14px;font-size:12px;color:var(--cyan)"></pre>
    </div>
    <div class="card glass">
      <h3>📋 استنساخ الهيكل لسيرفر آخر</h3>
      <div class="field-row">
        <div class="field"><label>السيرفر المصدر (الذي تنسخ منه)</label><select id="cloneSrc" class="input">${guildOpts}</select></div>
        <div class="field"><label>السيرفر الهدف (هذا السيرفر)</label><input class="input" value="${esc((await API.guild(curGuild())).guild.name)}" disabled /></div>
      </div>
      <div class="field" style="display:flex;align-items:center;justify-content:space-between">
        <div><b>نسخ الرولات أيضاً</b></div>
        <label class="toggle"><input type="checkbox" id="cloneRoles" checked /><span class="slider"></span></label>
      </div>
      <button class="btn btn-cyan" onclick="cloneGuild()">🧬 بدء الاستنساخ</button>
    </div>
    <div class="card glass">
      <h3>🔍 محرك البحث عن الكيانات</h3>
      <div class="field-row">
        <div class="field"><label>ID (سيرفر / قناة / مستخدم)</label><input id="lookupId" class="input" placeholder="مثال: 123456789" /></div>
        <div class="field" style="flex:0 0 auto"><label>&nbsp;</label><button class="btn btn-success" onclick="lookup()">🔎 بحث</button></div>
      </div>
      <div id="lookupRes" class="live-bar" style="display:none"></div>
    </div>`;
}

async function exportGuild() {
  try {
    const data = await API.exportGuild(curGuild());
    const box = $("exportBox");
    box.style.display = "block";
    box.textContent = JSON.stringify(data.data, null, 2);
    UI.toast("success", "تم تصدير الهيكل بنجاح");
  } catch (e) { UI.toast("error", e.message); }
}

async function cloneGuild() {
  const src = $("cloneSrc").value;
  if (!src) return UI.toast("warn", "اختر السيرفر المصدر");
UI.confirm("🧬 استنساخ", "سيتم إنشاء الرولات/الفئات/القنوات في هذا السيرفر — متابعة؟", async () => {
    try { await App.task(API.cloneGuild(curGuild(), $("cloneSrc").value, $("cloneRoles").checked), { long: true }); } catch (e) { UI.toast("error", e.message); }
  });
}

async function lookup() {
  const id = $("lookupId").value.trim();
  if (!id) return UI.toast("warn", "أدخل ID");
  const box = $("lookupRes");
  try { const r = await App.task(API.fetchById(id)); box.style.display = "flex"; box.innerHTML = `🔎 ${esc(r.message)}`; } catch (e) { UI.toast("error", e.message); }
}

/* ── DM All ─────────────────────────────────────────────────── */
async function viewDmail() {
  if (!requireGuild()) return;
  const view = $("view");
  view.innerHTML = `
    <div class="card glass">
      <h3>📨 إرسال رسالة خاصة لجميع الأعضاء</h3>
      <div class="live-bar" style="margin-bottom:16px">
        <span>⚠️</span>
        <div class="lb-info"><div class="lb-title">رسائل خاصة جماعية</div><div class="lb-sub">يرسل لكل الأعضاء غير البوتات. قد يفشل عند من يغلق خاص الرسائل لديه.</div></div>
      </div>
      <div class="field"><label>نص الرسالة</label><textarea id="dmMsg" class="input" rows="5"></textarea></div>
      <button class="btn btn-danger" onclick="doDmAll()">📨 إرسال للجميع</button>
    </div>`;
}

async function doDmAll() {
  const msg = $("dmMsg").value.trim();
  if (!msg) return UI.toast("warn", "اكتب الرسالة");
  UI.confirm("📨 إرسال جماعي", "سيتم إرسال رسالة خاصة لكل عضو في السيرفر. متابعة؟", async () => {
    UI.toast("info", "📨 جارٍ الإرسال... قد يستغرق دقائق");
    try { await App.task(API.dmAll(curGuild(), msg), { long: true }); } catch (e) { UI.toast("error", e.message); }
  });
}

/* ── Tools ─────────────────────────────────────────────────── */
async function viewTools() {
  const view = $("view");
  view.innerHTML = `
    <div class="card glass">
      <h3>🧰 تشخيص البيئة</h3>
      <div class="grid grid-3">
        <div class="stat-tile"><div class="s-icon">🎬</div><div id="ffmpegVal" class="s-value" style="font-size:16px">فحص...</div><div class="s-label">FFmpeg (الموسيقى)</div></div>
        <div class="stat-tile"><div class="s-icon">⚡</div><div id="pyVer" class="s-value" style="font-size:16px">...</div><div class="s-label">إصدار بايثون</div></div>
        <div class="stat-tile"><div class="s-icon">🐍</div><div class="s-value" style="font-size:16px">discord.py</div><div class="s-label">مكتبة الديسكورد</div></div>
      </div>
      <button class="btn btn-ghost" onclick="scanTools()">⟳ إعادة الفحص</button>
    </div>
    <div class="card glass">
      <h3>ℹ️ حول المنظومة</h3>
      <div style="color:var(--text-dim);font-size:14px;line-height:2">
        <b>NEON CORTEX</b> — منظومة قيادة بوتات ديسكورد عبر الويب.<br/>
        الباك-إند: <b>Python + FastAPI + discord.py</b> · الواجهة: <b>HTML + CSS + JS</b><br/>
        تشمل: رسائل، قنوات، أعضاء، تعديلات، إشراف آلي، ترحيب بالصور، تذاكر، موسيقى يوتيوب، رموز، تذكيرات، جدولة، استنساخ هيكل، إرسال جماعي.
      </div>
    </div>`;
  scanTools();
}

async function scanTools() {
  const ff = $("ffmpegVal");
  try {
    const r = await API.ffmpeg();
    ff.innerHTML = r.ok ? '<span style="color:var(--green)">✅ مثبت</span>' : '<span style="color:var(--red)">❌ مفقود</span>';
    if (!r.ok) UI.toast("warn", r.message.split("\n")[0]);
  } catch (e) { ff.innerHTML = '<span style="color:var(--red)">❌</span>'; }
  const ua = await fetch("/api/status").then(r => r.json()).catch(() => null);
}

/* ── Clipboard ─────────────────────────────────────────────── */
function copyText(t) {
  navigator.clipboard.writeText(t).then(() => UI.toast("success", `📋 نُسخ: ${t.slice(0, 24)}`)).catch(() => UI.toast("warn", "تعذر النسخ"));
}

/* ── Roles Manager (جديد) ───────────────────────────────── */
async function viewRoles() {
  if (!requireGuild()) return;
  const view = $("view");
  view.innerHTML = `
    <div class="card glass">
      <h3>🎭 إدارة الأدوار <span class="sub">إنشاء / تعديل / حذف / تعيين</span></h3>
      <div class="grid grid-2">
        <div>
          <div class="section-title">➕ إنشاء رول جديد</div>
          <div class="field"><label>اسم الرول</label><input id="roleName" class="input" placeholder="مثال: Moderator" /></div>
          <div class="field-row">
            <div class="field"><label>اللون</label><input id="roleColor" type="color" class="input" value="#5865f2" style="height:44px;padding:4px" /></div>
            <div class="field" style="display:flex;align-items:center;justify-content:space-between">
              <div><b>إظهار منفصل</b></div>
              <label class="toggle"><input type="checkbox" id="roleHoist" /><span class="slider"></span></label>
            </div>
          </div>
          <button class="btn btn-success w-full" onclick="createRole()">➕ إنشاء الرول</button>
        </div>
        <div>
          <div class="section-title">🔍 تعيين رول لعضو</div>
          <div class="field"><label>اختر الرول</label><select id="assignRole" class="input"></select></div>
          <div class="field"><label>اسم العضو</label><input id="assignMember" class="input" placeholder="اكتب اسم العضو..." oninput="filterAssignMembers()" /></div>
          <div id="assignMemberList" class="list" style="max-height:200px;margin-top:8px"></div>
        </div>
      </div>
    </div>
    <div class="card glass">
      <h3>📋 قائمة الأدوار <span class="sub">اضغط لتعديل أو حذف</span></h3>
      <div id="rolesList" class="list" style="max-height:500px"></div>
    </div>`;
  await loadRoles();
  await loadAssignMembers();
}

async function loadRoles() {
  const g = curGuild();
  try {
    const data = await API.getRolesManaged(g);
    const box = $("rolesList");
    box.innerHTML = data.roles.length ? data.roles.map(r => `
      <div class="list-item">
        <div style="width:24px;height:24px;border-radius:50%;background:${esc(r.color)};flex-shrink:0"></div>
        <div class="li-info">
          <div class="li-title">${esc(r.name)} ${r.default ? '<span class="chip">افتراضي</span>' : ""} ${r.hoist ? '<span class="chip cyan">منفصل</span>' : ""}</div>
          <div class="li-sub">المنصب: ${r.position} · الأعضاء: ${r.member_count} · ${r.mentionable ? "قابل للإ الجميع" : ""}</div>
        </div>
        <div class="li-actions">
          <button class="btn btn-ghost btn-sm" onclick="editRoleModal('${r.id}', '${esc(r.name)}', '${esc(r.color)}', ${r.hoist}, ${r.mentionable})" title="تعديل">✏️</button>
          ${!r.default ? `<button class="btn btn-danger btn-sm" onclick="deleteRole('${r.id}', '${esc(r.name)}')" title="حذف">🗑</button>` : ""}
        </div>
      </div>`).join("")
    : `<div class="empty"><div class="e-icon">🎭</div><div>لا أدوار</div></div>`;

    $("assignRole").innerHTML = data.roles.filter(r => !r.default).map(r => `<option value="${r.id}">${esc(r.name)}</option>`).join("");
  } catch (e) { UI.toast("error", e.message); }
}

async function createRole() {
  const name = $("roleName").value.trim();
  const color = $("roleColor").value;
  const hoist = $("roleHoist").checked;
  if (!name) return UI.toast("warn", "اكتب اسم الرول");
  try {
    await App.task(API.createRole(curGuild(), { name, color, hoist, mentionable: true }));
    $("roleName").value = "";
    await loadRoles();
  } catch (e) { UI.toast("error", e.message); }
}

async function editRoleModal(id, name, color, hoist, mentionable) {
  UI.modal({
    title: `✏️ تعديل الرول: ${name}`,
    body: `
      <div class="field"><label>الاسم</label><input id="editRoleName" class="input" value="${esc(name)}" /></div>
      <div class="field-row">
        <div class="field"><label>اللون</label><input id="editRoleColor" type="color" class="input" value="${esc(color)}" style="height:44px;padding:4px" /></div>
        <div class="field" style="display:flex;align-items:center;justify-content:space-between">
          <div><b>إظهار منفصل</b></div>
          <label class="toggle"><input type="checkbox" id="editRoleHoist" ${hoist ? "checked" : ""} /><span class="slider"></span></label>
        </div>
      </div>`,
    actions: `
      <button class="btn btn-ghost" onclick="UI.closeModal()">إلغاء</button>
      <button class="btn btn-primary" onclick="saveRoleEdit('${id}')">💾 حفظ</button>`,
  });
}

async function saveRoleEdit(id) {
  const name = $("editRoleName").value.trim();
  const color = $("editRoleColor").value;
  const hoist = $("editRoleHoist").checked;
  if (!name) return UI.toast("warn", "الاسم مطلوب");
  UI.closeModal();
  try { await App.task(API.editRole(curGuild(), id, { name, color, hoist })); await loadRoles(); } catch (e) { UI.toast("error", e.message); }
}

function deleteRole(id, name) {
  UI.confirm("🗑️ حذف رول", `هل تريد حذف رول "${name}" نهائياً؟`, async () => {
    try { await App.task(API.deleteRole(curGuild(), id)); await loadRoles(); } catch (e) { UI.toast("error", e.message); }
  });
}

async function loadAssignMembers() {
  const g = curGuild();
  try {
    const data = await API.guildMembers(g);
    App.state.members[g] = data.members;
    renderAssignMembers(data.members);
  } catch (e) { UI.toast("error", e.message); }
}

function renderAssignMembers(members) {
  const box = $("assignMemberList");
  if (!box) return;
  box.innerHTML = members.slice(0, 20).map(m => `
    <div class="list-item" onclick="assignRoleToMember('${m.id}', '${esc(m.display_name)}')" style="cursor:pointer">
      ${avatarHtml(m)}
      <div class="li-info"><div class="li-title">${esc(m.display_name)}</div><div class="li-sub">${esc(m.name)}</div></div>
    </div>`).join("");
}

function filterAssignMembers() {
  const q = ($("assignMember") ? $("assignMember").value : "").toLowerCase();
  const members = App.state.members[curGuild()] || [];
  const filtered = q ? members.filter(m => (m.display_name + m.name).toLowerCase().includes(q)) : members;
  renderAssignMembers(filtered);
}

async function assignRoleToMember(memberId, memberName) {
  const roleId = $("assignRole").value;
  if (!roleId) return UI.toast("warn", "اختر رولاً أولاً");
  try { await App.task(API.assignRole(curGuild(), roleId, parseInt(memberId))); } catch (e) { UI.toast("error", e.message); }
}

/* ── Polls System (جديد) ────────────────────────────────── */
async function viewPolls() {
  if (!requireGuild()) return;
  const view = $("view");
  view.innerHTML = `
    <div class="grid grid-2">
      <div class="card glass">
        <h3>📊 إنشاء استطلاع جديد</h3>
        <div class="field"><label>السؤال</label><input id="pollQuestion" class="input" placeholder="ما رأيك في...؟" /></div>
        <div class="field"><label>الخيارات (كل سطر = خيار)</label><textarea id="pollOptions" class="input" rows="4" placeholder="نعم&#10;لا&#10;ربما"></textarea></div>
        <div class="field-row">
          <div class="field"><label>المدة (ساعات)</label><input id="pollDuration" type="number" class="input" value="24" min="1" max="168" /></div>
          <div class="field"><label>القناة</label><select id="pollChannel" class="input"></select></div>
        </div>
        <button class="btn btn-primary w-full" onclick="createPoll()">📊 إنشاء الاستطلاع</button>
      </div>
      <div class="card glass">
        <h3>📋 الاستطلاعات النشطة</h3>
        <div id="pollsList" class="list" style="max-height:400px"></div>
      </div>
    </div>`;
  $("pollChannel").innerHTML = await channelOptions("text");
  await loadPolls();
}

async function loadPolls() {
  const g = curGuild();
  try {
    const data = await API.getPolls(g);
    const box = $("pollsList");
    box.innerHTML = data.polls.length ? data.polls.map(p => `
      <div class="list-item">
        <div class="li-info">
          <div class="li-title">📊 ${esc(p.question)}</div>
          <div class="li-sub">${p.options.map((o, i) => `${i+1}. ${esc(o.text)} (${o.votes} صوت)`).join(" · ")} · ${p.active ? "🟢 نشط" : "🔴 منتهي"}</div>
        </div>
        <div class="li-actions">
          ${p.active ? `<button class="btn btn-success btn-sm" onclick="votePollUI('${p.id}', ${JSON.stringify(p.options).replace(/"/g, "&quot;")})">🗳</button>` : ""}
          <button class="btn btn-danger btn-sm" onclick="deletePoll('${p.id}')">🗑</button>
        </div>
      </div>`).join("")
    : `<div class="empty"><div class="e-icon">📊</div><div>لا استطلاعات نشطة</div></div>`;
  } catch (e) { UI.toast("error", e.message); }
}

async function createPoll() {
  const question = $("pollQuestion").value.trim();
  const options = $("pollOptions").value.split("\n").filter(x => x.trim());
  const duration = parseInt($("pollDuration").value) || 24;
  const channelId = $("pollChannel").value;
  if (!question || options.length < 2 || !channelId) return UI.toast("warn", "أكمل جميع البيانات (سؤال + خياران على الأقل + قناة)");
  try {
    await App.task(API.createPoll(curGuild(), { channel_id: channelId, question, options, duration_hours: duration }));
    $("pollQuestion").value = "";
    $("pollOptions").value = "";
    await loadPolls();
  } catch (e) { UI.toast("error", e.message); }
}

function votePollUI(pollId, options) {
  UI.modal({
    title: "🗳️ صوّت الآن",
    body: options.map((o, i) => `
      <button class="btn btn-ghost w-full" style="margin-bottom:8px;text-align:right;justify-content:flex-start" onclick="UI.closeModal();votePoll('${pollId}', ${i})">${i+1}. ${esc(o.text)}</button>
    `).join(""),
  });
}

async function votePoll(pollId, optionIndex) {
  try { await App.task(API.votePoll(curGuild(), pollId, optionIndex)); await loadPolls(); } catch (e) { UI.toast("error", e.message); }
}

function deletePoll(pollId) {
  UI.confirm("🗑️ حذف استطلاع", "هل تريد حذف هذا الاستطلاع؟", async () => {
    try { await App.task(API.deletePoll(curGuild(), pollId)); await loadPolls(); } catch (e) { UI.toast("error", e.message); }
  });
}

/* ── Soundboard (جديد) ──────────────────────────────────── */
async function viewSoundboard() {
  if (!requireGuild()) return;
  const view = $("view");
  view.innerHTML = `
    <div class="card glass">
      <h3>🔊 لوحة الصوت <span class="sub">تشغيل مؤثرات صوتية في القنوات الصوتية</span></h3>
      <div class="field"><label>القناة الصوتية</label><select id="sbChannel" class="input"></select></div>
      <div class="section-title">🎵 المؤثرات المتاحة</div>
      <div id="soundsGrid" class="emoji-grid"></div>
      <div class="section-title" style="margin-top:20px">➕ إضافة صوت جديد</div>
      <div class="field-row">
        <div class="field"><label>الاسم</label><input id="sbName" class="input" placeholder="اسم المؤثر" /></div>
        <div class="field"><label>الرابط</label><input id="sbUrl" class="input" placeholder="رابط الصوت (mp3/wav)" /></div>
      </div>
    </div>`;
  $("sbChannel").innerHTML = await channelOptions("voice");
  await loadSounds();
}

async function loadSounds() {
  const g = curGuild();
  try {
    const data = await API.getSounds(g);
    const box = $("soundsGrid");
    box.innerHTML = data.sounds.length ? data.sounds.map(s => `
      <div class="emoji-tile" onclick="playSound('${esc(s.name)}')" style="cursor:pointer" title="اضغط للتشغيل">
        <div style="font-size:32px">🔊</div>
        <div class="e-name">${esc(s.name)}</div>
      </div>`).join("")
    : `<div class="empty" style="grid-column:1/-1"><div class="e-icon">🔇</div><div>لا مؤثرات — أضف ملفات صوتية في مجلد static/assets/sounds</div></div>`;
  } catch (e) { UI.toast("error", e.message); }
}

async function playSound(name) {
  const ch = $("sbChannel").value;
  if (!ch) return UI.toast("warn", "اختر قناة صوتية");
  try { await App.task(API.playSound(curGuild(), name, ch)); } catch (e) { UI.toast("error", e.message); }
}

/* ── Unified Search (جديد) ──────────────────────────────── */
async function viewSearch() {
  if (!requireGuild()) return;
  const view = $("view");
  view.innerHTML = `
    <div class="card glass">
      <h3>🔍 بحث موحد <span class="sub">بحث في القنوات، الأعضاء، الأدوار، الرموز</span></h3>
      <div class="field"><label>كلمة البحث</label><input id="searchQuery" class="input" placeholder="اكتب كلمة للبحث..." oninput="doSearch()" /></div>
      <div id="searchResults" style="margin-top:16px"></div>
    </div>`;
}

let searchTimeout = null;
function doSearch() {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(async () => {
    const q = ($("searchQuery") ? $("searchQuery").value : "").trim();
    const box = $("searchResults");
    if (!q || q.length < 2) { box.innerHTML = ""; return; }
    try {
      const data = await API.searchGuild(curGuild(), q);
      const r = data.results;
      let html = "";
      if (r.channels.length) {
        html += `<div class="section-title">📢 القنوات (${r.channels.length})</div>`;
        html += r.channels.map(c => `<div class="list-item"><div class="li-info"><div class="li-title">${esc(c.name)}</div><div class="li-sub">ID: ${c.id} · النوع: ${c.type}</div></div><button class="btn btn-ghost btn-sm" onclick="copyText('${c.id}')">📋</button></div>`).join("");
      }
      if (r.members.length) {
        html += `<div class="section-title">👥 الأعضاء (${r.members.length})</div>`;
        html += r.members.map(m => `<div class="list-item"><div class="li-info"><div class="li-title">${esc(m.display_name)}</div><div class="li-sub">ID: ${m.id}</div></div><button class="btn btn-ghost btn-sm" onclick="copyText('${m.id}')">📋</button></div>`).join("");
      }
      if (r.roles.length) {
        html += `<div class="section-title">🎭 الأدوار (${r.roles.length})</div>`;
        html += r.roles.map(r => `<div class="list-item"><div class="li-info"><div class="li-title">${esc(r.name)}</div><div class="li-sub">ID: ${r.id}</div></div><button class="btn btn-ghost btn-sm" onclick="copyText('${r.id}')">📋</button></div>`).join("");
      }
      if (r.emojis.length) {
        html += `<div class="section-title">😀 الرموز (${r.emojis.length})</div>`;
        html += r.emojis.map(e => `<div class="list-item"><div class="li-info"><div class="li-title">${esc(e.name)}</div><div class="li-sub">ID: ${e.id}</div></div><button class="btn btn-ghost btn-sm" onclick="copyText('${e.id}')">📋</button></div>`).join("");
      }
      box.innerHTML = html || `<div class="empty"><div class="e-icon">🔍</div><div>لا نتائج لـ "${esc(q)}"</div></div>`;
    } catch (e) { box.innerHTML = `<div class="empty"><div>${esc(e.message)}</div></div>`; }
  }, 300);
}

/* ── Audit Log (جديد) ──────────────────────────────────── */
async function viewAudit() {
  const view = $("view");
  view.innerHTML = `
    <div class="card glass">
      <h3>📋 سجل التغييرات <span class="sub">تتبع جميع العمليات</span></h3>
      <div style="display:flex;gap:10px;margin-bottom:16px">
        <button class="btn btn-primary" onclick="loadAuditLog()">🔄 تحديث</button>
        <button class="btn btn-danger" onclick="clearAuditLog()">🗑 مسح السجلات</button>
      </div>
      <div id="auditLog" class="list" style="max-height:500px"></div>
    </div>`;
  await loadAuditLog();
}

async function loadAuditLog() {
  const box = $("auditLog");
  try {
    const data = await API.getAuditLog(100);
    box.innerHTML = data.logs.length ? data.logs.reverse().map(log => `
      <div class="activity-entry">${esc(log)}</div>
    `).join("") : `<div class="empty"><div class="e-icon">📋</div><div>لا سجلات بعد</div></div>`;
  } catch (e) { box.innerHTML = `<div class="empty"><div>${esc(e.message)}</div></div>`; }
}

function clearAuditLog() {
  UI.confirm("🗑️ مسح السجلات", "هل تريد مسح جميع سجلات التغييرات؟", async () => {
    try { await App.task(API.clearAuditLog()); await loadAuditLog(); } catch (e) { UI.toast("error", e.message); }
  });
}

/* ── Server Protection ─────────────────────────────────────── */
async function viewProtection() {
  const view = $("view");
  view.innerHTML = `
    <div class="grid grid-2">
      <div class="card glass">
        <h3>🤖 حماية من الإهانات <span class="sub">Bot Insult Protection</span></h3>
        <div class="field" style="display:flex;align-items:center;justify-content:space-between">
          <div><b>تفعيل الحماية</b><div style="font-size:12px;color:var(--text-faint)">حذف رسائل الإهان تلقائياً</div></div>
          <label class="toggle"><input type="checkbox" id="protInsult" /><span class="slider"></span></label>
        </div>
        <div class="field"><label>عدد التحذيرات قبل الحظر</label><input id="protInsultWarns" type="number" class="input" value="2" min="1" max="10" /></div>
      </div>

      <div class="card glass">
        <h3>🚫 حماية من السبام <span class="sub">Anti-Spam</span></h3>
        <div class="field" style="display:flex;align-items:center;justify-content:space-between">
          <div><b>تفعيل حماية السبام</b><div style="font-size:12px;color:var(--text-faint)">منع تكرار الرسائل</div></div>
          <label class="toggle"><input type="checkbox" id="protSpam" /><span class="slider"></span></label>
        </div>
        <div class="field-row">
          <div class="field"><label>عدد الرسائل</label><input id="protSpamTh" type="number" class="input" value="5" min="2" max="20" /></div>
          <div class="field"><label>خلال (ثوانٍ)</label><input id="protSpamWin" type="number" class="input" value="3" min="1" max="30" /></div>
        </div>
      </div>

      <div class="card glass">
        <h3>⚡ حماية من الرايد <span class="sub">Anti-Raid</span></h3>
        <div class="field" style="display:flex;align-items:center;justify-content:space-between">
          <div><b>تفعيل حماية الرايد</b><div style="font-size:12px;color:var(--text-faint)">منع موجة الدخول الجماعي</div></div>
          <label class="toggle"><input type="checkbox" id="protRaid" /><span class="slider"></span></label>
        </div>
        <div class="field-row">
          <div class="field"><label>عدد الدخول المطلوب</label><input id="protRaidTh" type="number" class="input" value="10" min="3" max="50" /></div>
          <div class="field"><label>خلال (ثوانٍ)</label><input id="protRaidWin" type="number" class="input" value="60" min="5" max="120" /></div>
        </div>
      </div>

      <div class="card glass">
        <h3>👥 حماية من المنشن الجماعي <span class="sub">Mass Mention</span></h3>
        <div class="field" style="display:flex;align-items:center;justify-content:space-between">
          <div><b>منع المنشن الجماعي</b><div style="font-size:12px;color:var(--text-faint)">حذف رسائل المنشن المفرط</div></div>
          <label class="toggle"><input type="checkbox" id="protMention" /><span class="slider"></span></label>
        </div>
      </div>

      <div class="card glass">
        <h3>🔗 حظر الروابط <span class="sub">Link Block</span></h3>
        <div class="field" style="display:flex;align-items:center;justify-content:space-between">
          <div><b>حظر الروابط الخارجية</b><div style="font-size:12px;color:var(--text-faint)">منع إرسال أي روابط</div></div>
          <label class="toggle"><input type="checkbox" id="protLinks" /><span class="slider"></span></label>
        </div>
      </div>

      <div class="card glass">
        <h3>🔓 فتح الحظر التلقائي <span class="sub">Auto-Unban</span></h3>
        <div class="field" style="display:flex;align-items:center;justify-content:space-between">
          <div><b>فتح الحظر تلقائياً</b><div style="font-size:12px;color:var(--text-faint)">إلغاء حظر الأعضاء بعد فترة</div></div>
          <label class="toggle"><input type="checkbox" id="protUnban" /><span class="slider"></span></label>
        </div>
        <div class="field"><label>بعد كم ساعة</label><input id="protUnbanHrs" type="number" class="input" value="24" min="1" max="720" /></div>
      </div>

      <div class="card glass" style="grid-column:1/-1">
        <h3>🎭 تعيين رول تلقائي <span class="sub">Auto-Role</span></h3>
        <div class="field" style="display:flex;align-items:center;justify-content:space-between">
          <div><b>تفعيل التعيين التلقائي</b><div style="font-size:12px;color:var(--text-faint)">تعيين رول للأعضاء الجدد تلقائياً</div></div>
          <label class="toggle"><input type="checkbox" id="protAutoRole" /><span class="slider"></span></label>
        </div>
        <div class="field"><label>الرول</label><select id="protRole" class="input"><option value="">— اختر رول —</option></select></div>
        <button class="btn btn-primary w-full" onclick="saveProtection()" style="margin-top:12px">💾 حفظ جميع الإعدادات</button>
      </div>
    </div>`;

  const g = curGuild();
  if (!g) {
    $("protRole").innerHTML = '<option value="">⚠️ اختر سيرفراً أولاً</option>';
    return;
  }
  try {
    const resp = await API.getProtection(g);
    const cfg = resp.config || resp;
    $("protInsult").checked = cfg.bot_insult_kick || false;
    $("protInsultWarns").value = cfg.bot_insult_warns_before_kick || 2;
    $("protSpam").checked = cfg.spam_protection || false;
    $("protSpamTh").value = cfg.spam_threshold || 5;
    $("protSpamWin").value = cfg.spam_window || 3;
    $("protRaid").checked = cfg.raid_protection || false;
    $("protRaidTh").value = cfg.raid_threshold || 10;
    $("protRaidWin").value = cfg.raid_window || 60;
    $("protMention").checked = cfg.anti_mass_mention || false;
    $("protLinks").checked = cfg.link_block_enabled || false;
    $("protUnban").checked = cfg.auto_unban_enabled || false;
    $("protUnbanHrs").value = cfg.auto_unban_hours || 24;
    $("protAutoRole").checked = cfg.auto_role_enabled || false;

    const rolesResp = await API.guildRoles(g);
    const roles = (rolesResp.roles || []).filter(r => !r.default);
    $("protRole").innerHTML = '<option value="">— بدون رول —</option>' + roles.map(r => `<option value="${r.id}">${esc(r.name)}</option>`).join("");
    if (cfg.auto_role_id) $("protRole").value = String(cfg.auto_role_id);
  } catch (e) { UI.toast("error", "خطأ تحميل الإعدادات: " + e.message); }
}

async function saveProtection() {
  const g = curGuild();
  if (!g) return UI.toast("warn", "⚠️ اختر سيرفراً أولاً");
  const cfg = {
    bot_insult_kick: $("protInsult").checked,
    bot_insult_warns_before_kick: parseInt($("protInsultWarns").value) || 2,
    max_warnings_before_ban: 5,
    anti_mass_mention: $("protMention").checked,
    mass_mention_threshold: 5,
    spam_protection: $("protSpam").checked,
    spam_threshold: parseInt($("protSpamTh").value) || 5,
    spam_window: parseInt($("protSpamWin").value) || 3,
    raid_protection: $("protRaid").checked,
    raid_threshold: parseInt($("protRaidTh").value) || 10,
    raid_window: parseInt($("protRaidWin").value) || 60,
    greeting_protection: false,
    link_block_enabled: $("protLinks").checked,
    auto_unban_enabled: $("protUnban").checked,
    auto_unban_hours: parseInt($("protUnbanHrs").value) || 24,
    auto_role_enabled: $("protAutoRole").checked,
    auto_role_id: parseInt($("protRole").value) || 0,
  };
  try {
    await App.task(API.setProtection(g, cfg));
    UI.toast("success", "✅ تم حفظ إعدادات الحماية");
  } catch (e) { UI.toast("error", e.message); }
}

/* ── Live Stats ─────────────────────────────────────────────── */
let _statsInterval = null;

async function viewStats() {
  if (_statsInterval) { clearInterval(_statsInterval); _statsInterval = null; }
  const view = $("view");
  const g = curGuild();
  if (!g) {
    view.innerHTML = `<div class="card glass neon-frame"><div class="empty"><div class="e-icon">📊</div><div>اختر سيرفراً أولاً لعرض الإحصائيات المباشرة</div></div></div>`;
    return;
  }
  view.innerHTML = `
    <div class="card glass neon-frame" id="statsHero">
      <div class="loading"><div class="loader"></div><span>جاري تحميل الإحصائيات...</span></div>
    </div>
    <div id="statsBody"></div>`;
  await loadLiveStats();
  _statsInterval = setInterval(loadLiveStats, 10000);
}

async function loadLiveStats() {
  const g = curGuild();
  if (!g) { if (_statsInterval) { clearInterval(_statsInterval); _statsInterval = null; } return; }
  const hero = $("statsHero");
  const body = $("statsBody");
  if (!hero || !body) { if (_statsInterval) { clearInterval(_statsInterval); _statsInterval = null; } return; }

  try {
    const [guildData, healthData] = await Promise.all([
      API.guildStats(g).catch(() => null),
      API.health().catch(() => null),
    ]);

    const s = guildData ? guildData.stats : null;
    const h = healthData || {};
    const now = new Date();
    const timeStr = now.toLocaleTimeString("ar-SA", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

    const uptime = h.uptime || 0;
    const hrs = Math.floor(uptime / 3600);
    const mins = Math.floor((uptime % 3600) / 60);
    const secs = Math.floor(uptime % 60);
    const uptimeStr = `${hrs}س ${mins}د ${secs}ث`;

    const cpuPct = h.cpu_percent != null ? h.cpu_percent.toFixed(1) : "—";
    const ramPct = h.ram_percent != null ? h.ram_percent.toFixed(1) : "—";
    const ramUsed = h.ram_used_mb != null ? h.ram_used_mb.toFixed(0) : "—";
    const ramTotal = h.ram_total_mb != null ? h.ram_total_mb.toFixed(0) : "—";

    hero.innerHTML = `
      <div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap;box-shadow:none;border:none;background:transparent;padding:0;">
        <div class="logo-ring small"><span>📊</span></div>
        <div style="flex:1;min-width:200px">
          <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
            <h1 class="hero-stat gradient-text">${s ? esc(s.name) : "جاري التحميل..."}</h1>
            <span class="chip green">● مباشر</span>
          </div>
          <div style="color:var(--text-dim);font-size:13px;margin-top:6px">
            آخر تحديث: ${timeStr} · يُحدّث كل 10 ثوانٍ
          </div>
        </div>
      </div>`;

    body.innerHTML = `
      <div class="grid grid-4" style="margin-top:16px">
        <div class="stat-tile"><div class="s-icon">👥</div><div class="s-value">${s ? s.members : "—"}</div><div class="s-label">إجمالي الأعضاء</div></div>
        <div class="stat-tile tile-green"><div class="s-icon">🟢</div><div class="s-value">${s ? s.members_online || "—" : "—"}</div><div class="s-label">متصلون الآن</div></div>
        <div class="stat-tile tile-cyan"><div class="s-icon">💬</div><div class="s-value">${s ? s.text_channels : "—"}</div><div class="s-label">قنوات نصية</div></div>
        <div class="stat-tile tile-magenta"><div class="s-icon">🔊</div><div class="s-value">${s ? s.voice_channels : "—"}</div><div class="s-label">قنوات صوتية</div></div>
      </div>
      <div class="grid grid-4" style="margin-top:16px">
        <div class="stat-tile tile-amber"><div class="s-icon">⏱️</div><div class="s-value" style="font-size:20px">${uptimeStr}</div><div class="s-label">وقت التشغيل</div></div>
        <div class="stat-tile tile-cyan"><div class="s-icon">🖥️</div><div class="s-value" style="font-size:20px">${cpuPct}%</div><div class="s-label">استخدام المعالج</div></div>
        <div class="stat-tile tile-magenta"><div class="s-icon">🧠</div><div class="s-value" style="font-size:20px">${ramPct}%</div><div class="s-label">استخدام الرام</div></div>
        <div class="stat-tile"><div class="s-icon">💾</div><div class="s-value" style="font-size:20px">${ramUsed} MB</div><div class="s-label">الرام المستخدم / ${ramTotal} MB</div></div>
      </div>
      <div class="grid grid-3" style="margin-top:16px">
        <div class="stat-tile tile-green"><div class="s-icon">🎭</div><div class="s-value">${s ? s.roles : "—"}</div><div class="s-label">الرولات</div></div>
        <div class="stat-tile tile-amber"><div class="s-icon">😀</div><div class="s-value">${s ? s.emojis : "—"}</div><div class="s-label">الرموز التعبيرية</div></div>
        <div class="stat-tile"><div class="s-icon">🚀</div><div class="s-value">L${s ? s.boost_level : "—"}</div><div class="s-label">Boost (${s ? s.boosts : "—"})</div></div>
      </div>
      <div class="card glass" style="margin-top:16px">
        <h3>📡 نشاط القنوات الصوتية</h3>
        <div id="statsVoiceActivity" class="list" style="max-height:200px"></div>
      </div>`;

    loadVoiceActivity();
  } catch (e) {
    hero.innerHTML = `<div class="empty"><div class="e-icon">⚠️</div><div>تعذر جلب الإحصائيات: ${esc(e.message)}</div></div>`;
  }
}

async function loadVoiceActivity() {
  const box = $("statsVoiceActivity");
  if (!box) return;
  try {
    const g = curGuild();
    const data = await API.guildChannels(g);
    const voiceChannels = data.channels.filter(c => c.type === "voice" && c.connected_members && c.connected_members.length > 0);
    if (!voiceChannels.length) {
      box.innerHTML = `<div class="empty"><div class="e-icon">🔇</div><div>لا يوجد نشاط في القنوات الصوتية</div></div>`;
      return;
    }
    box.innerHTML = voiceChannels.map(ch => `
      <div class="list-item">
        <div class="li-info">
          <div class="li-title">🔊 ${esc(ch.name)}</div>
          <div class="li-sub">${ch.connected_members.map(m => esc(m.name || m.id)).join(" · ")}</div>
        </div>
        <span class="chip cyan">${ch.connected_members.length}</span>
      </div>`).join("");
  } catch (e) {
    box.innerHTML = `<div class="empty"><div class="e-icon">📡</div><div>${esc(e.message)}</div></div>`;
  }
}

/* ── Welcome Card Designer ──────────────────────────────────── */
async function welcomeCardView() {
  const view = $("view");
  const g = curGuild();
  if (!g) {
    view.innerHTML = `<div class="card glass neon-frame"><div class="empty"><div class="e-icon">🎴</div><div>اختر سيرفراً أولاً لتصميم بطاقة الترحيب</div></div></div>`;
    return;
  }
  view.innerHTML = `
    <div class="card glass">
      <h3>🃏 مصمم بطاقة الترحيب <span class="sub">بطاقة ترحيب فخمة مع معاينة مباشرة</span></h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
        <div>
          <div class="field" style="display:flex;align-items:center;justify-content:space-between">
            <div><b>تفعيل بطاقة الترحيب</b></div>
            <label class="toggle"><input type="checkbox" id="wcEnabled" checked /><span class="slider"></span></label>
          </div>
          <div class="field"><label>قناة الإرسال</label><select id="wcChannel" class="input"></select></div>
          <div class="field"><label>العنوان — استخدم {server} و {user}</label><input id="wcTitle" class="input" value="مرحباً بك في {server}!" placeholder="مرحباً بك في {server}!" oninput="updateWelcomePreview()" /></div>
          <div class="field"><label>العنوان الفرعي — استخدم {server} و {user}</label><input id="wcSubtitle" class="input" value="نتمنى لك وقتاً ممتعاً {user}" placeholder="نتمنى لك وقتاً ممتعاً {user}" oninput="updateWelcomePreview()" /></div>
          <div class="field-row">
            <div class="field"><label>لون الخلفية</label><input id="wcBgColor" type="color" class="input" value="#1a1a2e" style="height:44px;padding:4px" oninput="updateWelcomePreview()" /></div>
            <div class="field"><label>لون النص</label><input id="wcTextColor" type="color" class="input" value="#ffffff" style="height:44px;padding:4px" oninput="updateWelcomePreview()" /></div>
          </div>
          <div class="field-row">
            <div class="field"><label>لون التمييز (Accent)</label><input id="wcAccentColor" type="color" class="input" value="#00d4ff" style="height:44px;padding:4px" oninput="updateWelcomePreview()" /></div>
            <div class="field"><label>نمط الحد</label><select id="wcBorderStyle" class="input" onchange="updateWelcomePreview()">
              <option value="neon">✨ نيون</option>
              <option value="gradient">🌈 تدريجي</option>
              <option value="simple">▪️ بسيط</option>
            </select></div>
          </div>
          <div class="field" style="display:flex;align-items:center;justify-content:space-between">
            <div><b>إظهار الصورة الرمزية</b></div>
            <label class="toggle"><input type="checkbox" id="wcShowAvatar" checked onchange="updateWelcomePreview()" /><span class="slider"></span></label>
          </div>
          <div class="field" style="display:flex;align-items:center;justify-content:space-between">
            <div><b>إظهار عدد الأعضاء</b></div>
            <label class="toggle"><input type="checkbox" id="wcShowCount" checked onchange="updateWelcomePreview()" /><span class="slider"></span></label>
          </div>
          <button class="btn btn-primary w-full" onclick="saveWelcomeCard()" style="margin-top:12px">💾 حفظ إعدادات البطاقة</button>
        </div>
        <div>
          <div class="section-title">👁️ معاينة مباشرة</div>
          <div id="wcPreview" style="width:100%;aspect-ratio:3/1;border-radius:16px;overflow:hidden;position:relative;background:#1a1a2e;border:3px solid #00d4ff;display:flex;align-items:center;padding:24px;box-shadow:0 0 30px rgba(0,212,255,0.3)"></div>
        </div>
      </div>
    </div>`;
  try {
    const opts = await channelOptions("text");
    $("wcChannel").innerHTML = opts;
    const resp = await API.getWelcomeConfig(curGuild());
    if (resp.enabled !== undefined) $("wcEnabled").checked = resp.enabled;
    if (resp.channel_id && $("wcChannel").querySelector(`option[value="${resp.channel_id}"]`)) $("wcChannel").value = resp.channel_id;
    if (resp.title) $("wcTitle").value = resp.title;
    if (resp.subtitle) $("wcSubtitle").value = resp.subtitle;
    if (resp.bg_color) $("wcBgColor").value = resp.bg_color;
    if (resp.text_color) $("wcTextColor").value = resp.text_color;
    if (resp.accent_color) $("wcAccentColor").value = resp.accent_color;
    if (resp.border_style) $("wcBorderStyle").value = resp.border_style;
    if (resp.show_avatar !== undefined) $("wcShowAvatar").checked = resp.show_avatar;
    if (resp.show_member_count !== undefined) $("wcShowCount").checked = resp.show_member_count;
  } catch (e) { UI.toast("error", e.message); }
  updateWelcomePreview();
}

function updateWelcomePreview() {
  const box = $("wcPreview");
  if (!box) return;
  const title = ($("wcTitle") ? $("wcTitle").value : "مرحباً بك في {server}!").replace(/\{server\}/g, "سيرفرنا").replace(/\{user\}/g, "عضو جديد");
  const subtitle = ($("wcSubtitle") ? $("wcSubtitle").value : "").replace(/\{server\}/g, "سيرفرنا").replace(/\{user\}/g, "عضو جديد");
  const bg = $("wcBgColor") ? $("wcBgColor").value : "#1a1a2e";
  const textCol = $("wcTextColor") ? $("wcTextColor").value : "#ffffff";
  const accent = $("wcAccentColor") ? $("wcAccentColor").value : "#00d4ff";
  const borderStyle = $("wcBorderStyle") ? $("wcBorderStyle").value : "neon";
  const showAvatar = $("wcShowAvatar") ? $("wcShowAvatar").checked : true;
  const showCount = $("wcShowCount") ? $("wcShowCount").checked : true;
  let borderCss = "";
  if (borderStyle === "neon") borderCss = `border:3px solid ${accent};box-shadow:0 0 30px ${accent}40, inset 0 0 30px ${accent}15`;
  else if (borderStyle === "gradient") borderCss = `border:3px solid transparent;background-clip:padding-box;box-shadow:0 0 20px ${accent}30`;
  else borderCss = `border:2px solid ${accent}80`;
  let html = `<div style="flex:1;display:flex;flex-direction:column;justify-content:center;gap:6px;z-index:1">`;
  html += `<div style="font-size:22px;font-weight:800;color:${esc(textCol)};text-shadow:0 0 10px ${accent}60">${esc(title)}</div>`;
  if (subtitle) html += `<div style="font-size:13px;color:${esc(textCol)}cc">${esc(subtitle)}</div>`;
  if (showCount) html += `<div style="font-size:11px;color:${esc(accent)};margin-top:4px">👥 العضو رقم #${Math.floor(Math.random() * 500) + 1}</div>`;
  html += `</div>`;
  if (showAvatar) html += `<div style="width:72px;height:72px;border-radius:50%;background:${esc(accent)}30;border:3px solid ${esc(accent)};display:flex;align-items:center;justify-content:center;font-size:30px;flex-shrink:0;z-index:1">👤</div>`;
  box.style.background = `linear-gradient(135deg, ${bg}, ${bg}ee)`;
  box.style.cssText += `;${borderCss}`;
  box.innerHTML = html;
}

async function saveWelcomeCard() {
  const g = curGuild();
  const cfg = {
    enabled: $("wcEnabled").checked,
    channel_id: parseInt($("wcChannel").value) || 0,
    title: $("wcTitle").value,
    subtitle: $("wcSubtitle").value,
    bg_color: $("wcBgColor").value,
    text_color: $("wcTextColor").value,
    accent_color: $("wcAccentColor").value,
    border_style: $("wcBorderStyle").value,
    show_avatar: $("wcShowAvatar").checked,
    show_member_count: $("wcShowCount").checked,
  };
  try {
    await App.task(API.setWelcomeConfig(g, cfg));
    UI.toast("success", "✅ تم حفظ إعدادات بطاقة الترحيب");
  } catch (e) { UI.toast("error", e.message); }
}

/* ── Embed Builder Pro ──────────────────────────────────────── */
let _ebFields = [];

function embedBuilderView() {
  _ebFields = [];
  const view = $("view");
  const g = curGuild();
  if (!g) {
    view.innerHTML = `<div class="card glass neon-frame"><div class="empty"><div class="e-icon">💎</div><div>اختر سيرفراً أولاً لاستخدام منشئ الـ Embed</div></div></div>`;
    return;
  }
  view.innerHTML = `
    <div class="card glass">
      <h3>✨ منشئ الـ Embed الفخم <span class="sub">صمم وعاين وأرسل</span></h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
        <div>
          <div class="field-row">
            <div class="field"><label>العنوان</label><input id="ebProTitle" class="input" placeholder="عنوان الـ Embed" oninput="updateEmbedPreview()" /></div>
            <div class="field"><label>اللون</label><input id="ebProColor" type="color" class="input" value="#5865f2" style="height:44px;padding:4px" oninput="updateEmbedPreview()" /></div>
          </div>
          <div class="field"><label>الوصف (يدعم Markdown)</label><textarea id="ebProDesc" class="input" rows="4" placeholder="اكتب وصف الـ Embed هنا..." oninput="updateEmbedPreview()"></textarea></div>
          <div class="field-row">
            <div class="field"><label>اسم المؤلف</label><input id="ebProAuthor" class="input" placeholder="اسم المؤلف" oninput="updateEmbedPreview()" /></div>
            <div class="field"><label>أيقونة المؤلف</label><input id="ebProAuthorIcon" class="input" placeholder="https://..." oninput="updateEmbedPreview()" /></div>
          </div>
          <div class="field-row">
            <div class="field"><label>نص الفوتر</label><input id="ebProFooter" class="input" placeholder="نص الفوتر" oninput="updateEmbedPreview()" /></div>
            <div class="field"><label>أيقونة الفوتر</label><input id="ebProFooterIcon" class="input" placeholder="https://..." oninput="updateEmbedPreview()" /></div>
          </div>
          <div class="field-row">
            <div class="field"><label>رابط الصورة المصغرة (Thumbnail)</label><input id="ebProThumb" class="input" placeholder="https://..." oninput="updateEmbedPreview()" /></div>
            <div class="field"><label>رابط الصورة الكبيرة (Image)</label><input id="ebProImage" class="input" placeholder="https://..." oninput="updateEmbedPreview()" /></div>
          </div>
          <div class="section-title" style="margin-top:14px">📋 الحقول <button class="btn btn-success btn-sm" onclick="ebAddField()" style="margin-right:8px">➕ إضافة حقل</button></div>
          <div id="ebFieldsList"></div>
          <div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap">
            <div class="field" style="flex:1;min-width:140px"><label>إرسال إلى قناة</label><select id="ebProChannel" class="input"></select></div>
            <div class="field" style="flex:0 0 auto"><label>&nbsp;</label><button class="btn btn-primary" onclick="sendEmbedPro()">📤 إرسال</button></div>
          </div>
          <div style="display:flex;gap:10px;margin-top:10px">
            <button class="btn btn-cyan" style="flex:1" onclick="copyEmbedJSON()">📋 نسخ JSON</button>
            <button class="btn btn-danger" style="flex:1" onclick="clearEmbedForm()">🗑 مسح النموذج</button>
          </div>
        </div>
        <div>
          <div class="section-title">👁️ معاينة مباشرة</div>
          <div id="ebProPreview" style="background:rgba(8,10,25,.7);border-radius:12px;padding:20px;min-height:300px;border:1px solid rgba(88,101,242,0.2)"></div>
        </div>
      </div>
    </div>`;
  channelOptions("text").then(opts => { if ($("ebProChannel")) $("ebProChannel").innerHTML = opts; });
  updateEmbedPreview();
}

function ebAddField() {
  _ebFields.push({ name: "", value: "", inline: true });
  renderEbFields();
  updateEmbedPreview();
}

function ebRemoveField(i) {
  _ebFields.splice(i, 1);
  renderEbFields();
  updateEmbedPreview();
}

function renderEbFields() {
  const box = $("ebFieldsList");
  if (!box) return;
  box.innerHTML = _ebFields.length ? _ebFields.map((f, i) => `
    <div style="display:grid;grid-template-columns:1fr 1fr auto auto;gap:8px;align-items:center;margin-bottom:8px">
      <input class="input" placeholder="اسم الحقل" value="${esc(f.name)}" oninput="_ebFields[${i}].name=this.value;updateEmbedPreview()" />
      <input class="input" placeholder="قيمة الحقل" value="${esc(f.value)}" oninput="_ebFields[${i}].value=this.value;updateEmbedPreview()" />
      <label style="font-size:12px;display:flex;align-items:center;gap:4px;white-space:nowrap"><input type="checkbox" ${f.inline ? "checked" : ""} onchange="_ebFields[${i}].inline=this.checked;updateEmbedPreview()" /> خط</label>
      <button class="btn btn-danger btn-sm" onclick="ebRemoveField(${i})">✕</button>
    </div>`).join("")
    : '<div style="font-size:12px;color:var(--text-faint);padding:8px">لا حقول بعد — اضغط "إضافة حقل" لبدء البناء</div>';
}

function updateEmbedPreview() {
  const box = $("ebProPreview");
  if (!box) return;
  const title = $("ebProTitle") ? $("ebProTitle").value : "";
  const desc = $("ebProDesc") ? $("ebProDesc").value : "";
  const color = $("ebProColor") ? $("ebProColor").value : "#5865f2";
  const author = $("ebProAuthor") ? $("ebProAuthor").value : "";
  const authorIcon = $("ebProAuthorIcon") ? $("ebProAuthorIcon").value : "";
  const footer = $("ebProFooter") ? $("ebProFooter").value : "";
  const footerIcon = $("ebProFooterIcon") ? $("ebProFooterIcon").value : "";
  const thumb = $("ebProThumb") ? $("ebProThumb").value : "";
  const image = $("ebProImage") ? $("ebProImage").value : "";

  let h = `<div style="border-left:4px solid ${esc(color)};padding:0 16px;margin:8px 0">`;
  if (author) h += `<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">${authorIcon ? `<img src="${esc(authorIcon)}" style="width:20px;height:20px;border-radius:50%" />` : ""}<span style="font-weight:700;font-size:13px;color:#fff">${esc(author)}</span></div>`;
  if (title) h += `<div style="font-size:17px;font-weight:800;color:#fff;margin-bottom:6px">${esc(title)}</div>`;
  if (desc) h += `<div style="font-size:14px;color:#dcddde;line-height:1.6;white-space:pre-wrap;margin-bottom:10px">${esc(desc).replace(/\*\*(.*?)\*\*/g, "<b>$1</b>").replace(/\*(.*?)\*/g, "<i>$1</i>").replace(/`(.*?)\`/g, '<code style="background:rgba(0,0,0,.4);padding:2px 6px;border-radius:4px;font-size:13px">$1</code>').replace(/\n/g, "<br>")}</div>`;
  if (_ebFields.length) {
    h += `<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:10px">`;
    _ebFields.forEach(f => {
      const w = f.inline ? "min-width:120px;max-width:200px" : "width:100%";
      h += `<div style="${w}"><div style="font-size:12px;font-weight:700;color:#fff;margin-bottom:2px">${esc(f.name || "—")}</div><div style="font-size:13px;color:#dcddde">${esc(f.value || "—")}</div></div>`;
    });
    h += `</div>`;
  }
  if (thumb || image) {
    h += `<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:8px">`;
    if (thumb) h += `<img src="${esc(thumb)}" style="width:80px;height:80px;border-radius:8px;object-fit:cover" />`;
    h += `</div>`;
    if (image) h += `<img src="${esc(image)}" style="width:100%;max-height:200px;border-radius:8px;object-fit:cover;margin-top:8px" />`;
  }
  if (footer) h += `<div style="display:flex;align-items:center;gap:6px;margin-top:10px;font-size:12px;color:#999">${footerIcon ? `<img src="${esc(footerIcon)}" style="width:16px;height:16px;border-radius:50%" />` : ""}${esc(footer)}</div>`;
  h += `</div>`;
  box.innerHTML = h;
}

function buildEmbedProJSON() {
  const embed = {};
  if ($("ebProTitle")) embed.title = $("ebProTitle").value;
  if ($("ebProDesc")) embed.description = $("ebProDesc").value;
  if ($("ebProColor")) embed.color = parseInt($("ebProColor").value.replace("#", ""), 16);
  if ($("ebProAuthor") && $("ebProAuthor").value) embed.author = { name: $("ebProAuthor").value, icon_url: $("ebProAuthorIcon") ? $("ebProAuthorIcon").value : undefined };
  if ($("ebProFooter") && $("ebProFooter").value) embed.footer = { text: $("ebProFooter").value, icon_url: $("ebProFooterIcon") ? $("ebProFooterIcon").value : undefined };
  if ($("ebProThumb") && $("ebProThumb").value) embed.thumbnail = { url: $("ebProThumb").value };
  if ($("ebProImage") && $("ebProImage").value) embed.image = { url: $("ebProImage").value };
  if (_ebFields.length) embed.fields = _ebFields.filter(f => f.name || f.value).map(f => ({ name: f.name, value: f.value, inline: f.inline }));
  embed.timestamp = new Date().toISOString();
  return embed;
}

async function sendEmbedPro() {
  const g = curGuild();
  const ch = $("ebProChannel") ? $("ebProChannel").value : "";
  if (!ch) return UI.toast("warn", "اختر قناة للإرسال");
  try {
    const embed = buildEmbedProJSON();
    const payload = {
      channel_id: parseInt(ch),
      title: embed.title || "",
      description: embed.description || "",
      color: $("ebProColor") ? $("ebProColor").value : "#5865F2",
      author_name: $("ebProAuthor") ? $("ebProAuthor").value : "",
      author_icon: $("ebProAuthorIcon") ? $("ebProAuthorIcon").value : "",
      footer_text: $("ebProFooter") ? $("ebProFooter").value : "",
      footer_icon: $("ebProFooterIcon") ? $("ebProFooterIcon").value : "",
      thumbnail: $("ebProThumb") ? $("ebProThumb").value : "",
      image: $("ebProImage") ? $("ebProImage").value : "",
      fields: _ebFields.filter(f => f.name || f.value),
    };
    await App.task(API.sendEmbed(g, payload));
    UI.toast("success", "✅ تم إرسال الـ Embed بنجاح");
  } catch (e) { UI.toast("error", e.message); }
}

function copyEmbedJSON() {
  const json = JSON.stringify(buildEmbedProJSON(), null, 2);
  navigator.clipboard.writeText(json).then(() => UI.toast("success", "📋 نُسخ JSON الـ Embed")).catch(() => UI.toast("warn", "تعذر النسخ"));
}

function clearEmbedForm() {
  ["ebProTitle", "ebProDesc", "ebProAuthor", "ebProAuthorIcon", "ebProFooter", "ebProFooterIcon", "ebProThumb", "ebProImage"].forEach(id => { if ($(id)) $(id).value = ""; });
  if ($("ebProColor")) $("ebProColor").value = "#5865f2";
  _ebFields = [];
  renderEbFields();
  updateEmbedPreview();
  UI.toast("info", "🗑 تم مسح جميع الحقول");
}

/* ── Router ─────────────────────────────────────────────────── */
window.Views = {
  dashboard: viewDashboard,
  messages: viewMessages,
  channels: viewChannels,
  members: viewMembers,
  music: viewMusic,
  roles: viewRoles,
  automod: viewAutomod,
  welcome: viewWelcome,
  tickets: viewTickets,
  polls: viewPolls,
  automation: viewAutomation,
  emojis: viewEmojis,
  soundboard: viewSoundboard,
  structure: viewStructure,
  dmail: viewDmail,
  search: viewSearch,
  audit: viewAudit,
  tools: viewTools,
  protection: viewProtection,
  stats: viewStats,
  welcomeCard: welcomeCardView,
  embedBuilder: embedBuilderView,
};