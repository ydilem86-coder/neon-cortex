/* NEON CORTEX — API client (v2 — with Auth) */
"use strict";

const API = (() => {
  let _session = localStorage.getItem("nc_session") || null;

  function _headers() {
    const h = {};
    if (_session) h["Authorization"] = `Bearer ${_session}`;
    return h;
  }

  async function request(method, path, body) {
    const opts = { method, headers: _headers() };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    if (res.status === 401) {
      _session = null;
      localStorage.removeItem("nc_session");
      if (typeof App !== "undefined" && App.showLogin) App.showLogin();
      throw new Error("غير مصرح - سجّل الدخول مجدداً");
    }
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok) {
      const detail = (data && (data.detail || data.message)) || `خطأ ${res.status}`;
      throw new Error(detail);
    }
    return data;
  }

  return {
    get:   (p) => request("GET", p),
    post:  (p, b) => request("POST", p, b),
    del:   (p) => request("DELETE", p),
    put:   (p, b) => request("PUT", p, b),

    setSession: (s) => { _session = s; localStorage.setItem("nc_session", s); },
    getSession: () => _session,
    clearSession: () => { _session = null; localStorage.removeItem("nc_session"); },

    status: () => request("GET", "/api/status"),
    connect: (token) => request("POST", "/api/connect", { token }),
    disconnect: () => request("POST", "/api/disconnect"),
    activity: () => request("GET", "/api/activity"),
    ffmpeg: () => request("GET", "/api/ffmpeg"),
    fetchById: (id) => request("GET", `/api/fetch/${id}`),

    guilds: () => request("GET", "/api/guilds"),
    guild: (id) => request("GET", `/api/guilds/${id}`),
    guildChannels: (id) => request("GET", `/api/guilds/${id}/channels`),
    guildMembers: (id, limit) => request("GET", `/api/guilds/${id}/members${limit ? "?limit=" + limit : ""}`),
    guildRoles: (id) => request("GET", `/api/guilds/${id}/roles`),
    guildStats: (id) => request("GET", `/api/guilds/${id}/stats`),
    advancedStats: (id) => request("GET", `/api/guilds/${id}/stats/advanced`),
    exportGuild: (id) => request("GET", `/api/guilds/${id}/export`),
    cloneGuild: (id, source, includeRoles) => request("POST", `/api/guilds/${id}/clone`, { source_guild_id: source, include_roles: includeRoles }),

    sendMessage: (chId, content) => request("POST", `/api/channels/${chId}/send`, { content }),
    bulkSend: (chId, messages, delay) => request("POST", `/api/channels/${chId}/bulk`, { messages, delay }),
    purge: (chId, limit) => request("POST", `/api/channels/${chId}/purge`, { limit }),
    sendEmbed: (chId, embed) => request("POST", `/api/channels/${chId}/embed`, embed),
    createChannel: (gid, name, type, cat) => request("POST", `/api/guilds/${gid}/channels`, { name, channel_type: type, category_id: cat || null }),
    deleteChannel: (chId) => request("DELETE", `/api/channels/${chId}`),

    kick: (gid, memberId, reason) => request("POST", `/api/guilds/${gid}/kick`, { member_id: memberId, reason }),
    ban: (gid, memberId, reason) => request("POST", `/api/guilds/${gid}/ban`, { member_id: memberId, reason }),
    timeout: (gid, memberId, minutes, reason) => request("POST", `/api/guilds/${gid}/timeout`, { member_id: memberId, minutes, reason }),
    warn: (gid, memberId, reason) => request("POST", `/api/guilds/${gid}/warn`, { member_id: memberId, reason }),
    clearWarns: (gid, memberId) => request("POST", `/api/guilds/${gid}/warns/clear`, { member_id: memberId }),
    getWarns: (gid, memberId) => request("GET", `/api/guilds/${gid}/warns/${memberId}`),

    getWelcome: (gid) => request("GET", `/api/guilds/${gid}/welcome`),
    setWelcome: (gid, cfg) => request("POST", `/api/guilds/${gid}/welcome`, cfg),
    getAutomod: (gid) => request("GET", `/api/guilds/${gid}/automod`),
    setAutomod: (gid, cfg) => request("POST", `/api/guilds/${gid}/automod`, cfg),

    getLogChannel: (gid) => request("GET", `/api/guilds/${gid}/log-channel`),
    setLogChannel: (gid, channelId) => request("POST", `/api/guilds/${gid}/log-channel`, { channel_id: channelId }),

    getReminders: () => request("GET", "/api/reminders"),
    addReminder: (r) => request("POST", "/api/reminders", r),
    removeReminder: (i) => request("DELETE", `/api/reminders/${i}`),
    getScheduled: () => request("GET", "/api/scheduled"),
    addScheduled: (s) => request("POST", "/api/scheduled", s),
    removeScheduled: (i) => request("DELETE", `/api/scheduled/${i}`),

    voiceJoin: (gid, chId) => request("POST", `/api/guilds/${gid}/voice/join`, { channel_id: chId }),
    voiceLeave: (gid) => request("POST", `/api/guilds/${gid}/voice/leave`),
    musicPlay: (gid, url, requester, channel) => request("POST", `/api/guilds/${gid}/music/play-enhanced`, { url, requester: requester || "", channel: channel || "" }),
    musicSearch: (gid, query) => request("POST", `/api/guilds/${gid}/music/search`, { query }),
    musicCommand: (gid, command, vcId) => request("POST", `/api/guilds/${gid}/music/command`, { command, voice_channel_id: vcId }),
    musicSkip: (gid) => request("POST", `/api/guilds/${gid}/music/skip`),
    musicStop: (gid) => request("POST", `/api/guilds/${gid}/music/stop`),
    musicClear: (gid) => request("POST", `/api/guilds/${gid}/music/clear`),
    musicVolume: (gid, vol) => request("POST", `/api/guilds/${gid}/music/volume`, { volume: vol }),
    musicStatus: (gid) => request("GET", `/api/guilds/${gid}/music/status`),
    musicPause: (gid) => request("POST", `/api/guilds/${gid}/music/pause`),
    musicResume: (gid) => request("POST", `/api/guilds/${gid}/music/resume`),
    musicLoop: (gid) => request("POST", `/api/guilds/${gid}/music/loop`),
    musicQueueLoop: (gid) => request("POST", `/api/guilds/${gid}/music/queue-loop`),
    musicShuffle: (gid) => request("POST", `/api/guilds/${gid}/music/shuffle`),
    musicStay: (gid) => request("POST", `/api/guilds/${gid}/music/stay`),
    musicNowPlayingEmbed: (gid, chId) => request("POST", `/api/guilds/${gid}/music/nowplaying`, { channel_id: chId }),
    musicPanel: (gid, chId) => request("POST", `/api/guilds/${gid}/music/panel`, { channel_id: chId }),
    setPanelChannel: (gid, chId) => request("POST", `/api/guilds/${gid}/music/panel-channel`, { channel_id: chId }),
    getPanelChannel: (gid) => request("GET", `/api/guilds/${gid}/music/panel-channel`),

    getTicketsConfig: (gid) => request("GET", `/api/guilds/${gid}/tickets`),
    setTicketsConfig: (gid, cfg) => request("POST", `/api/guilds/${gid}/tickets`, cfg),
    sendTicketPanel: (chId, gid) => request("POST", `/api/channels/${chId}/ticket-panel/${gid}`),

    emojis: (gid) => request("GET", `/api/guilds/${gid}/emojis`),
    uploadEmoji: (gid, name, url) => request("POST", `/api/guilds/${gid}/emojis`, { name, image_url: url }),
    transferEmoji: (gid, targetId, emojiIds) => request("POST", `/api/guilds/${gid}/emojis/transfer`, { target_guild_id: targetId, emoji_ids: emojiIds }),
    transferAllEmoji: (gid, targetId) => request("POST", `/api/guilds/${gid}/emojis/transfer-all`, { target_guild_id: targetId }),

    dmAll: (gid, message) => request("POST", `/api/guilds/${gid}/dm-all`, { message }),

    getRolesManaged: (gid) => request("GET", `/api/guilds/${gid}/roles/managed`),
    createRole: (gid, role) => request("POST", `/api/guilds/${gid}/roles/create`, role),
    editRole: (gid, roleId, data) => request("PUT", `/api/guilds/${gid}/roles/${roleId}`, data),
    deleteRole: (gid, roleId) => request("DELETE", `/api/guilds/${gid}/roles/${roleId}`),
    assignRole: (gid, roleId, memberId) => request("POST", `/api/guilds/${gid}/roles/${roleId}/assign/${memberId}`),
    removeRole: (gid, roleId, memberId) => request("POST", `/api/guilds/${gid}/roles/${roleId}/remove/${memberId}`),

    getPolls: (gid) => request("GET", `/api/guilds/${gid}/polls`),
    createPoll: (gid, poll) => request("POST", `/api/guilds/${gid}/polls/create`, poll),
    votePoll: (gid, pollId, optionIndex) => request("POST", `/api/guilds/${gid}/polls/vote`, { poll_id: pollId, option_index: optionIndex }),
    deletePoll: (gid, pollId) => request("DELETE", `/api/guilds/${gid}/polls/${pollId}`),

    searchGuild: (gid, q) => request("GET", `/api/guilds/${gid}/search?q=${encodeURIComponent(q)}`),
    getSounds: (gid) => request("GET", `/api/guilds/${gid}/soundboard`),
    playSound: (gid, name, chId) => request("POST", `/api/guilds/${gid}/soundboard/play`, { name, channel_id: chId }),

    getAuditLog: (limit) => request("GET", `/api/audit-log${limit ? "?limit=" + limit : ""}`),
    clearAuditLog: () => request("DELETE", "/api/audit-log"),

    getProtection: (gid) => request("GET", `/api/guilds/${gid}/protection`),
    setProtection: (gid, cfg) => request("POST", `/api/guilds/${gid}/protection`, cfg),

    getWelcomeConfig: (gid) => request("GET", `/api/guilds/${gid}/welcome-config`),
    setWelcomeConfig: (gid, cfg) => request("POST", `/api/guilds/${gid}/welcome-config`, cfg),
    sendEmbed: (gid, embed) => request("POST", `/api/guilds/${gid}/embed/send`, embed),
    health: () => request("GET", "/api/health"),
    getUsers: () => request("GET", "/api/admin/users"),
    addUser: (user) => request("POST", "/api/admin/users", user),
    deleteUser: (username) => request("DELETE", `/api/admin/users/${username}`),
    updatePermissions: (username, perms) => request("PUT", `/api/admin/users/${username}/permissions`, { permissions: perms }),

    // Admin Auth
    login: (username, password) => request("POST", "/api/auth/login", { username, password }),
    logout: () => request("POST", "/api/auth/logout"),
    authMe: () => request("GET", "/api/auth/me"),

    // Anti-Nuke
    getAntinuke: (gid) => request("GET", `/api/guilds/${gid}/antinuke`),
    setAntinuke: (gid, cfg) => request("POST", `/api/guilds/${gid}/antinuke`, cfg),

    // Verification
    getVerification: (gid) => request("GET", `/api/guilds/${gid}/verification`),
    setVerification: (gid, cfg) => request("POST", `/api/guilds/${gid}/verification`, cfg),
    sendVerification: (gid, cfg) => request("POST", `/api/guilds/${gid}/verification/send`, cfg),

    // Reaction Roles
    getReactionRoles: (gid) => request("GET", `/api/guilds/${gid}/reaction-roles`),
    setupReactionRoles: (gid, cfg) => request("POST", `/api/guilds/${gid}/reaction-roles/setup`, cfg),
    removeReactionRoles: (gid) => request("DELETE", `/api/guilds/${gid}/reaction-roles`),

    // Giveaways
    getGiveaways: (gid) => request("GET", `/api/guilds/${gid}/giveaways`),
    createGiveaway: (gid, cfg) => request("POST", `/api/guilds/${gid}/giveaways/create`, cfg),
    endGiveaway: (gid, gwid) => request("POST", `/api/guilds/${gid}/giveaways/${gwid}/end`),

    // Levels
    getLevels: (gid) => request("GET", `/api/guilds/${gid}/levels`),
    setLevels: (gid, cfg) => request("POST", `/api/guilds/${gid}/levels`, cfg),
    getLeaderboard: (gid) => request("GET", `/api/guilds/${gid}/levels/leaderboard`),

    // Custom Commands
    getCommands: (gid) => request("GET", `/api/guilds/${gid}/commands`),
    createCommand: (gid, cmd) => request("POST", `/api/guilds/${gid}/commands`, cmd),
    deleteCommand: (gid, name) => request("DELETE", `/api/guilds/${gid}/commands/${name}`),

    // Birthday
    getBirthdays: (gid) => request("GET", `/api/guilds/${gid}/birthdays`),
    setBirthday: (gid, data) => request("POST", `/api/guilds/${gid}/birthdays`, data),
    deleteBirthday: (gid, uid) => request("DELETE", `/api/guilds/${gid}/birthdays/${uid}`),

    // AFK
    getAfk: (gid) => request("GET", `/api/guilds/${gid}/afk`),

    // Suggestions
    getSuggestions: (gid) => request("GET", `/api/guilds/${gid}/suggestions`),
    setSuggestions: (gid, cfg) => request("POST", `/api/guilds/${gid}/suggestions`, cfg),

    // Music Enhanced
    getQueueDisplay: (gid) => request("GET", `/api/guilds/${gid}/music/queue-display`),
    getMusicStats: (gid) => request("GET", `/api/guilds/${gid}/music/stats`),
    getNowPlaying: (gid) => request("GET", `/api/guilds/${gid}/music/now-playing`),
    searchLyrics: (gid, q) => request("GET", `/api/guilds/${gid}/music/lyrics?q=${encodeURIComponent(q)}`),

    // Webhooks
    getWebhooks: (gid) => request("GET", `/api/guilds/${gid}/webhooks`),
    createWebhook: (gid, data) => request("POST", `/api/guilds/${gid}/webhooks`, data),
    deleteWebhook: (gid, wid) => request("DELETE", `/api/guilds/${gid}/webhooks/${wid}`),

    // Emojis
    getEmojis: (gid) => request("GET", `/api/guilds/${gid}/emojis`),
    deleteEmoji: (gid, eid) => request("DELETE", `/api/guilds/${gid}/emojis/${eid}`),

    // Role Hierarchy
    getRoleHierarchy: (gid) => request("GET", `/api/guilds/${gid}/roles/hierarchy`),

    // Invites
    getInvites: (gid) => request("GET", `/api/guilds/${gid}/invites`),
    getInviteStats: (gid) => request("GET", `/api/guilds/${gid}/invites/stats`),

    // Voice
    getVoiceConnected: (gid) => request("GET", `/api/guilds/${gid}/voice/connected`),
    getVoiceStats: (gid) => request("GET", `/api/guilds/${gid}/voice/stats`),

    // Bot Status
    getBotStatus: () => request("GET", "/api/bot/status"),

    // Stats
    getCommandStats: () => request("GET", "/api/stats/commands"),

    // Errors
    getErrors: () => request("GET", "/api/errors"),
    clearErrors: () => request("DELETE", "/api/errors"),

    // Performance
    getPerformance: () => request("GET", "/api/performance"),

    // Scheduled
    getScheduled: (gid) => request("GET", `/api/guilds/${gid}/scheduled`),
    addScheduled: (gid, data) => request("POST", `/api/guilds/${gid}/scheduled`, data),
    deleteScheduled: (gid, idx) => request("DELETE", `/api/guilds/${gid}/scheduled/${idx}`),

    // Cross-Server
    crossAnnounce: (data) => request("POST", "/api/announce", data),

    // API Rate
    getApiRate: () => request("GET", "/api/stats/api-rate"),
  };
})();
