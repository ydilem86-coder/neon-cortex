"""Discord Bot Web API — FastAPI bridge around the existing Python bot.

Serves both the REST endpoints (used by the web control panel) and the
static frontend files. All bot logic lives in bot_client.py and is reused
as-is thanks to BotManager.run_coro (thread-safe scheduling onto the bot's
own event loop).
"""

import sys
import os
import hashlib
import secrets
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import discord

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from bot_client import bot_manager

app = FastAPI(title="Discord Bot Web API", version="2.0.0")

WEB_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(os.path.dirname(WEB_DIR), "config")
os.makedirs(CONFIG_DIR, exist_ok=True)


@app.on_event("startup")
async def auto_connect_bot():
    """Auto-connect bot on server startup using saved token."""
    import threading
    
    def _try_connect():
        try:
            token = _load_bot_token()
            if token:
                print(f"[NEON CORTEX] Found saved token, attempting auto-connect...")
                ok, msg = bot_manager.connect(token)
                if ok:
                    print(f"[NEON CORTEX] Auto-connected successfully: {msg}")
                else:
                    print(f"[NEON CORTEX] Auto-connect failed: {msg}")
            else:
                print("[NEON CORTEX] No saved token found, waiting for manual connect")
        except Exception as e:
            print(f"[NEON CORTEX] Auto-connect error: {e}")
    
    # Run in background thread to not block startup
    thread = threading.Thread(target=_try_connect, daemon=True)
    thread.start()

# ── Security: Token Hashing & Auth ──────────────────────────────────────

ADMIN_PASSWORD_FILE = os.path.join(CONFIG_DIR, "admin_password.hash")
SESSION_FILE = os.path.join(CONFIG_DIR, "sessions.json")
BOT_TOKEN_FILE = os.path.join(CONFIG_DIR, "bot_token.enc")
AUDIT_LOG_FILE = os.path.join(WEB_DIR, "audit.log")
USERS_FILE = os.path.join(CONFIG_DIR, "users.json")

def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{h}"

def _verify_password(password: str, stored: str) -> bool:
    salt, h = stored.split(":", 1)
    return hashlib.sha256((salt + password).encode()).hexdigest() == h

def _load_admin_password() -> str:
    if os.path.exists(ADMIN_PASSWORD_FILE):
        with open(ADMIN_PASSWORD_FILE, "r") as f:
            return f.read().strip()
    default = secrets.token_urlsafe(16)
    with open(ADMIN_PASSWORD_FILE, "w") as f:
        f.write(_hash_password(default))
    print(f"[NEON CORTEX] كلمة مرور الإدارة الافتراضية: {default}")
    return _hash_password(default)

def _check_admin_password(password: str) -> bool:
    stored = _load_admin_password()
    return _verify_password(password, stored)

def _generate_session() -> str:
    session_id = secrets.token_urlsafe(32)
    sessions = _load_sessions()
    sessions[session_id] = {
        "created": datetime.now().isoformat(),
        "expires": (datetime.now() + timedelta(hours=24)).isoformat()
    }
    with open(SESSION_FILE, "w") as f:
        json.dump(sessions, f)
    return session_id

def _load_sessions() -> dict:
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as f:
            return json.load(f)
    return {}

def _is_valid_session(session_id: str) -> bool:
    sessions = _load_sessions()
    if session_id not in sessions:
        return False
    exp = datetime.fromisoformat(sessions[session_id]["expires"])
    if datetime.now() > exp:
        del sessions[session_id]
        with open(SESSION_FILE, "w") as f:
            json.dump(sessions, f)
        return False
    return True

def _log_audit(action: str, user: str = "admin", details: str = ""):
    try:
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {user} | {action} | {details}\n")
    except Exception:
        pass

def _save_bot_token(token: str):
    try:
        with open(BOT_TOKEN_FILE, "w") as f:
            f.write(token)
    except Exception:
        pass

def _load_bot_token() -> Optional[str]:
    if os.path.exists(BOT_TOKEN_FILE):
        with open(BOT_TOKEN_FILE, "r") as f:
            return f.read().strip()
    return None

# ── Users Management ────────────────────────────────────────────────────

def _load_users() -> dict:
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {"admin": {"password": _load_admin_password(), "role": "admin", "permissions": ["all"]}}

def _save_users(users: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def _check_permission(session_id: str, permission: str) -> bool:
    if not _is_valid_session(session_id):
        return False
    users = _load_users()
    for user_data in users.values():
        if "all" in user_data.get("permissions", []):
            return True
        if permission in user_data.get("permissions", []):
            return True
    return False

# ── Auth Middleware ──────────────────────────────────────────────────────

class AuthMiddleware:
    EXEMPT_PATHS = ["/api/login", "/api/status", "/static", "/"]

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"]
            if any(path.startswith(p) for p in self.EXEMPT_PATHS):
                return await self.app(scope, receive, send)
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()
            session_id = auth_header.replace("Bearer ", "") if auth_header else ""
            if not session_id or not _is_valid_session(session_id):
                response = JSONResponse(status_code=401, content={"detail": "غير مصرح - سجّل الدخول أولاً"})
                return await response(scope, receive, send)
        return await self.app(scope, receive, send)

# ── Exception Handler ───────────────────────────────────────────────────

import traceback as _tb

@app.exception_handler(Exception)
async def _catch_all(request: Request, exc: Exception):
    try:
        with open(os.path.join(WEB_DIR, "error.log"), "a", encoding="utf-8") as _f:
            _f.write(f"[{datetime.now().isoformat()}] {request.method} {request.url.path}\n")
            _f.write("".join(_tb.format_exception(type(exc), exc, exc.__traceback__)) + "\n")
    except Exception:
        pass
    return JSONResponse(status_code=500, content={"detail": f"خطأ داخلي: {exc}"})

# ── CORS (مُحسّن) ─────────────────────────────────────────────────────

ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Allow Railway and other deployments
RAILWAY_REGEX = r"^https?://.*\.(on\.render\.com|railway\.app|herokuapp\.com)(:\d+)?$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=RAILWAY_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth Dependency ──────────────────────────────────────────────────────

async def require_auth(request: Request):
    auth_header = request.headers.get("authorization", "")
    session_id = auth_header.replace("Bearer ", "") if auth_header else ""
    if not session_id or not _is_valid_session(session_id):
        raise HTTPException(status_code=401, detail="غير مصرح - سجّل الدخول أولاً")
    return session_id


# ── Helpers ────────────────────────────────────────────────────────────

def require_connected():
    if not bot_manager.ready or bot_manager.client is None:
        raise HTTPException(status_code=400, detail="البوت غير متصل")


def await_(coro, timeout=30):
    return bot_manager.run_coro(coro, timeout=timeout)


def _get_guild(guild_id: int):
    """جلب السيرفر من الكاش، وإن لم يوجد نجلب من API مباشرة (مع تسجيل تشخيصي)."""
    guild = bot_manager.get_guild(guild_id)
    if guild is not None:
        return guild
    try:
        with open(os.path.join(WEB_DIR, "error.log"), "a", encoding="utf-8") as _f:
            _f.write(
                f"[{datetime.now().isoformat()}] INFO | سيرفر غير موجود في الكاش | المستقبَل: {guild_id} | "
                f"الكاش: {[g for g in bot_manager.guilds][:5]}\n"
            )
        guild = bot_manager.run_coro(bot_manager.client.fetch_guild(guild_id, with_counts=True), timeout=15)
        return guild
    except Exception as e:
        with open(os.path.join(WEB_DIR, "error.log"), "a", encoding="utf-8") as _f:
            _f.write(f"[{datetime.now().isoformat()}] FAIL | fetch_guild({guild_id}) -> {e}\n")
        return None


def _asset_url(a, size):
    fn = getattr(a, "with_size", None)
    if callable(fn):
        try:
            return str(fn(size))
        except Exception:
            pass
    return str(a)


def guild_summary(g):
    return {
        "id": str(g.id),
        "name": g.name,
        "description": g.description or "",
        "icon": _asset_url(g.icon, 256) if g.icon else "",
        "banner": _asset_url(g.banner, 1024) if g.banner else "",
        "member_count": g.member_count,
        "online_count": sum(
            1 for m in g.members if not m.bot and m.status != discord.Status.offline
        ),
        "text_channels": len(g.text_channels),
        "voice_channels": len(g.voice_channels),
        "categories": len(g.categories),
        "roles": len(g.roles),
        "emojis": len(g.emojis),
        "boost_tier": getattr(g, "premium_tier", 0),
        "boosts": getattr(g, "premium_subscription_count", 0) or 0,
        "owner": str(g.owner) if getattr(g, "owner", None) else "",
        "created": g.created_at.strftime("%Y-%m-%d") if g.created_at else "",
        "verified": bool(getattr(g, "verified", False)),
        "nsfw_level": str(getattr(g, "nsfw_level", "?")),
        "features": getattr(g, "features", None) or [],
    }


def channel_summary(ch):
    import discord

    if isinstance(ch, discord.CategoryChannel):
        kind = "category"
        icon = "📁"
    elif isinstance(ch, discord.VoiceChannel):
        kind = "voice"
        icon = "🔊"
    elif isinstance(ch, discord.ForumChannel):
        kind = "forum"
        icon = "💭"
    else:
        kind = "text"
        icon = "💬"
    return {
        "id": str(ch.id),
        "name": ch.name,
        "type": kind,
        "icon": icon,
        "position": ch.position,
        "category": ch.category.name if getattr(ch, "category", None) else None,
        "topic": getattr(ch, "topic", None) or "",
        "slowmode": getattr(ch, "slowmode_delay", 0) or 0,
        "member_count": getattr(ch, "user_limit", 0) or 0,
    }


def member_summary(m):
    return {
        "id": str(m.id),
        "name": str(m),
        "display_name": m.display_name,
        "username": m.name,
        "avatar": str(m.display_avatar.url) if m.display_avatar else "",
        "bot": m.bot,
        "joined": m.joined_at.strftime("%Y-%m-%d") if m.joined_at else "",
        "roles": len(m.roles) - 1,
        "top_role": m.top_role.name if m.top_role else "",
        "status": str(getattr(m.status, "name", "?")) if hasattr(m, "status") else "?",
        "disabled": False,
    }


# ── API Schemas ────────────────────────────────────────────────────────

class ConnectIn(BaseModel):
    token: str


class MessageIn(BaseModel):
    content: str = ""


class BulkMessageIn(BaseModel):
    messages: list[str]
    delay: float = 1.0


class PurgeIn(BaseModel):
    limit: int = 100


class ChannelIn(BaseModel):
    name: str
    channel_type: str = "text"
    category_id: Optional[int] = None


class MemberActionIn(BaseModel):
    member_id: int
    reason: str = ""


class TimeoutIn(BaseModel):
    member_id: int
    minutes: int = 10
    reason: str = ""


class CloneIn(BaseModel):
    source_guild_id: int
    include_roles: bool = True


class EmbedField(BaseModel):
    name: str = ""
    value: str = ""
    inline: bool = False


class EmbedButton(BaseModel):
    label: str = ""
    url: str = ""


class EmbedIn(BaseModel):
    title: str = ""
    description: str = ""
    color: str = "#5865F2"
    author: str = ""
    author_icon: str = ""
    footer: str = ""
    footer_icon: str = ""
    thumbnail: str = ""
    image: str = ""
    timestamp: bool = False
    fields: list[EmbedField] = []
    buttons: list[EmbedButton] = []


class WelcomeIn(BaseModel):
    enabled: bool = False
    channel_id: str = ""
    message: str = "مرحباً {user} في سيرفر {server}! 🎉"
    image_enabled: bool = False


class AutomodIn(BaseModel):
    enabled: bool = False
    block_everyone: bool = True
    block_caps: bool = False
    caps_threshold: int = 70
    anti_raid: bool = False
    raid_threshold: int = 8
    raid_window: int = 30
    anti_spam: bool = False
    spam_threshold: int = 5
    spam_window: int = 5


class ReminderIn(BaseModel):
    channel_id: int
    message: str
    timestamp: str


class ScheduledIn(BaseModel):
    channel_id: int
    message: str
    time: str
    repeat: str = "daily"


class IndexIn(BaseModel):
    index: int


class VoiceJoinIn(BaseModel):
    channel_id: int


class PlayIn(BaseModel):
    url: str


class SearchIn(BaseModel):
    query: str


class VolumeIn(BaseModel):
    volume: int = 100


class EmojiIn(BaseModel):
    name: str
    image_url: str


class DMAllIn(BaseModel):
    message: str


class WarnIn(BaseModel):
    member_id: int
    reason: str


class TicketConfigIn(BaseModel):
    category_id: int
    staff_role_id: int
    welcome_msg: str = ""
    panel_title: str = ""
    panel_desc: str = ""
    color: str = "#5865F2"


class LogChannelIn(BaseModel):
    channel_id: int


class ProtectionIn(BaseModel):
    bot_insult_kick: bool = False
    bot_insult_warns_before_kick: int = 2
    max_warnings_before_ban: int = 5
    anti_mass_mention: bool = False
    mass_mention_threshold: int = 5
    spam_protection: bool = False
    spam_threshold: int = 5
    spam_window: int = 3
    raid_protection: bool = False
    raid_threshold: int = 10
    raid_window: int = 60
    greeting_protection: bool = False
    link_block_enabled: bool = False
    auto_unban_enabled: bool = False
    auto_unban_hours: int = 24
    auto_role_enabled: bool = False
    auto_role_id: int = 0


class AutoRoleIn(BaseModel):
    enabled: bool = False
    role_id: int = 0


class LinkBlockIn(BaseModel):
    enabled: bool = False
    channels: list[int] = []
    whitelist: list[int] = []


class AutoUnbanIn(BaseModel):
    enabled: bool = False
    hours: int = 24


# ── Connection / Status ────────────────────────────────────────────────

@app.get("/api/status")
def status():
    return {
        "ready": bot_manager.ready,
        "user": str(bot_manager.user) if bot_manager.user else None,
        "guilds": len(bot_manager.guilds),
        "latency": round(bot_manager.client.latency, 2) if bot_manager.ready and bot_manager.client else 0,
    }


@app.post("/api/login")
def login(body: dict):
    password = body.get("password", "")
    if not _check_admin_password(password):
        _log_audit("login_failed", "unknown", "محاولة دخول فاشلة")
        raise HTTPException(status_code=401, detail="كلمة المرور غير صحيحة")
    session_id = _generate_session()
    _log_audit("login_success", "admin", "تسجيل دخول ناجح")
    return {"ok": True, "session": session_id, "message": "تم تسجيل الدخول بنجاح"}


@app.get("/api/auth/check")
async def check_auth(request: Request):
    auth_header = request.headers.get("authorization", "")
    session_id = auth_header.replace("Bearer ", "") if auth_header else ""
    return {"valid": _is_valid_session(session_id)}


@app.post("/api/auth/logout")
async def logout(request: Request):
    auth_header = request.headers.get("authorization", "")
    session_id = auth_header.replace("Bearer ", "") if auth_header else ""
    sessions = _load_sessions()
    if session_id in sessions:
        del sessions[session_id]
        with open(SESSION_FILE, "w") as f:
            json.dump(sessions, f)
    _log_audit("logout", "admin", "تسجيل خروج")
    return {"ok": True, "message": "تم تسجيل الخروج"}


@app.post("/api/auth/change-password")
async def change_password(body: dict, session: str = Depends(require_auth)):
    old_pass = body.get("old_password", "")
    new_pass = body.get("new_password", "")
    if not new_pass or len(new_pass) < 6:
        raise HTTPException(status_code=400, detail="كلمة المرور الجديدة يجب أن تكون 6 أحرف على الأقل")
    if not _check_admin_password(old_pass):
        raise HTTPException(status_code=400, detail="كلمة المرور القديمة غير صحيحة")
    with open(ADMIN_PASSWORD_FILE, "w") as f:
        f.write(_hash_password(new_pass))
    _log_audit("password_changed", "admin", "تم تغيير كلمة المرور")
    return {"ok": True, "message": "تم تغيير كلمة المرور بنجاح"}


@app.post("/api/connect")
def connect(body: ConnectIn):
    _log_audit("bot_connect", "admin", "محاولة اتصال البوت")
    _save_bot_token(body.token)
    ok, msg = bot_manager.connect(body.token)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    _log_audit("bot_connected", "admin", msg)
    return {"ok": True, "message": msg}


@app.post("/api/upload-cookies")
async def upload_cookies(request: Request):
    """Upload YouTube cookies file for yt-dlp authentication."""
    try:
        body = await request.json()
        cookies_content = body.get("cookies", "")
        if not cookies_content:
            raise HTTPException(status_code=400, detail="Cookies content is empty")
        
        cookies_path = os.path.join(CONFIG_DIR, "cookies.txt")
        with open(cookies_path, "w", encoding="utf-8") as f:
            f.write(cookies_content)
        
        _log_audit("cookies_uploaded", "admin", "YouTube cookies uploaded")
        return {"ok": True, "message": "YouTube cookies uploaded successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/cookies/status")
def cookies_status():
    """Check if YouTube cookies file exists."""
    cookies_path = os.path.join(CONFIG_DIR, "cookies.txt")
    exists = os.path.exists(cookies_path)
    return {"ok": True, "exists": exists, "path": cookies_path if exists else None}


@app.post("/api/disconnect")
def disconnect():
    bot_manager.disconnect_sync()
    return {"ok": True, "message": "تم قطع الاتصال"}


@app.get("/api/activity")
def activity():
    return {"entries": bot_manager.activity_log}


@app.get("/api/ffmpeg")
def ffmpeg():
    ok, msg = bot_manager.check_ffmpeg()
    return {"ok": ok, "message": msg}


@app.get("/api/fetch/{entity_id}")
def fetch_by_id(entity_id: int):
    require_connected()
    ok, msg = bot_manager.run_coro(bot_manager.fetch_by_id(entity_id))
    if not ok:
        raise HTTPException(status_code=404, detail=msg)
    return {"ok": True, "message": msg}


# ── Servers ────────────────────────────────────────────────────────────

@app.get("/api/guilds")
def list_guilds():
    require_connected()
    data = [guild_summary(g) for g in bot_manager.guilds]
    data.sort(key=lambda x: x["member_count"], reverse=True)
    return {"guilds": data}


@app.get("/api/guilds/{guild_id}")
def guild_detail(guild_id: int):
    require_connected()
    guild = _get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    return {"guild": guild_summary(guild)}


@app.get("/api/guilds/{guild_id}/channels")
def guild_channels(guild_id: int):
    require_connected()
    guild = _get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    channels = [channel_summary(ch) for ch in guild.channels]
    channels.sort(key=lambda c: (c["category"] is not None, c["position"]))
    return {"channels": channels}


@app.get("/api/guilds/{guild_id}/members")
def guild_members(guild_id: int, limit: int = 200):
    require_connected()
    guild = _get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    members = sorted(guild.members, key=lambda m: (m.bot, m.joined_at is None, m.joined_at or ""))
    return {"members": [member_summary(m) for m in members[:limit]]}


@app.get("/api/guilds/{guild_id}/roles")
def guild_roles(guild_id: int):
    require_connected()
    guild = _get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    roles = [
        {"id": str(r.id), "name": r.name, "color": r.color.value, "position": r.position, "default": r.is_default()}
        for r in sorted(guild.roles, key=lambda x: x.position, reverse=True)
    ]
    return {"roles": roles}


@app.get("/api/guilds/{guild_id}/stats")
def guild_stats(guild_id: int):
    require_connected()
    if not _get_guild(guild_id):
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    ok, stats = bot_manager.run_coro(bot_manager.get_guild_stats(guild_id))
    if not ok:
        raise HTTPException(status_code=404, detail=stats)
    stats["id"] = str(stats["id"])
    return {"stats": stats}


@app.get("/api/guilds/{guild_id}/export")
def export_guild(guild_id: int):
    require_connected()
    if not _get_guild(guild_id):
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    ok, data = bot_manager.run_coro(bot_manager.export_server_structure(guild_id))
    if not ok:
        raise HTTPException(status_code=404, detail=data)
    return {"ok": True, "data": data}


@app.post("/api/guilds/{guild_id}/clone")
def clone_guild(guild_id: int, body: CloneIn):
    require_connected()
    ok, msg = bot_manager.run_coro(
        bot_manager.clone_structure_to_guild(body.source_guild_id, guild_id, body.include_roles)
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


# ── Channels / Messages ────────────────────────────────────────────────

@app.post("/api/channels/{channel_id}/send")
def send_message(channel_id: int, body: MessageIn):
    require_connected()
    ok, msg = bot_manager.run_coro(bot_manager.send_message(channel_id, body.content))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/channels/{channel_id}/bulk")
def bulk_send(channel_id: int, body: BulkMessageIn):
    require_connected()
    ok, msg = bot_manager.run_coro(
        bot_manager.bulk_send(channel_id, body.messages, body.delay), timeout=600
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/channels/{channel_id}/purge")
def purge(channel_id: int, body: PurgeIn):
    require_connected()
    ok, msg = bot_manager.run_coro(bot_manager.delete_channel_messages(channel_id, body.limit))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/channels/{channel_id}/embed")
def send_embed(channel_id: int, body: EmbedIn):
    require_connected()
    ok, msg = bot_manager.run_coro(
        bot_manager.send_embed(
            channel_id,
            title=body.title,
            description=body.description,
            color=body.color,
            author=body.author,
            author_icon=body.author_icon,
            footer=body.footer,
            footer_icon=body.footer_icon,
            thumbnail=body.thumbnail,
            image=body.image,
            timestamp=body.timestamp,
            fields=[f.dict() for f in body.fields],
            buttons=[{"label": b.label, "url": b.url} for b in body.buttons],
        )
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/guilds/{guild_id}/channels")
def create_channel(guild_id: int, body: ChannelIn):
    require_connected()
    ok, msg = bot_manager.run_coro(
        bot_manager.create_channel(guild_id, body.name, body.channel_type, body.category_id)
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.delete("/api/channels/{channel_id}")
def delete_channel(channel_id: int):
    require_connected()
    ok, msg = bot_manager.run_coro(bot_manager.delete_channel(channel_id))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


# ── Members / Moderation ───────────────────────────────────────────────

@app.post("/api/guilds/{guild_id}/kick")
def kick(guild_id: int, body: MemberActionIn):
    require_connected()
    ok, msg = bot_manager.run_coro(
        bot_manager.kick_member(guild_id, body.member_id, body.reason)
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/guilds/{guild_id}/ban")
def ban(guild_id: int, body: MemberActionIn):
    require_connected()
    ok, msg = bot_manager.run_coro(bot_manager.ban_member(guild_id, body.member_id, body.reason))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/guilds/{guild_id}/timeout")
def timeout(guild_id: int, body: TimeoutIn):
    require_connected()
    ok, msg = bot_manager.run_coro(
        bot_manager.timeout_member(guild_id, body.member_id, body.minutes, body.reason)
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/guilds/{guild_id}/warn")
def warn(guild_id: int, body: WarnIn):
    require_connected()
    ok, msg = bot_manager.run_coro(
        bot_manager.warn_member(guild_id, body.member_id, body.reason, str(bot_manager.user))
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/guilds/{guild_id}/warns/clear")
def clear_warns(guild_id: int, body: MemberActionIn):
    require_connected()
    ok, msg = bot_manager.remove_warns(guild_id, body.member_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.get("/api/guilds/{guild_id}/warns/{member_id}")
def get_warns(guild_id: int, member_id: int):
    return {"ok": True, "warns": bot_manager.get_warns(guild_id, member_id)}


# ── Welcome ────────────────────────────────────────────────────────────

@app.get("/api/guilds/{guild_id}/welcome")
def get_welcome(guild_id: int):
    return {"ok": True, "config": bot_manager.get_welcome_config(guild_id)}


@app.post("/api/guilds/{guild_id}/welcome")
def set_welcome(guild_id: int, body: WelcomeIn):
    ok, msg = bot_manager.set_welcome_config(
        guild_id, body.enabled, body.channel_id, body.message, body.image_enabled
    )
    return {"ok": ok, "message": msg}


# ── AutoMod ────────────────────────────────────────────────────────────

@app.get("/api/guilds/{guild_id}/automod")
def get_automod(guild_id: int):
    return {"ok": True, "config": bot_manager.get_automod_config(guild_id)}


@app.post("/api/guilds/{guild_id}/automod")
def set_automod(guild_id: int, body: AutomodIn):
    ok, msg = bot_manager.set_automod_config(
        guild_id, body.enabled, body.block_everyone, body.block_caps,
        body.caps_threshold, body.anti_raid, body.raid_threshold,
        body.raid_window, body.anti_spam, body.spam_threshold, body.spam_window,
    )
    return {"ok": ok, "message": msg}


# ── Logs / Reminders / Scheduled ───────────────────────────────────────

@app.get("/api/guilds/{guild_id}/log-channel")
def get_log_channel(guild_id: int):
    return {"ok": True, "channel_id": bot_manager.get_log_channel(guild_id)}


@app.post("/api/guilds/{guild_id}/log-channel")
def set_log_channel(guild_id: int, body: LogChannelIn):
    bot_manager.set_log_channel(guild_id, body.channel_id)
    return {"ok": True, "message": "تم ضبط قناة السجلات"}


@app.get("/api/reminders")
def get_reminders():
    return {"ok": True, "reminders": bot_manager.get_reminders()}


@app.post("/api/reminders")
def add_reminder(body: ReminderIn):
    ok, msg = bot_manager.set_reminder(body.channel_id, body.message, body.timestamp)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.delete("/api/reminders/{index}")
def remove_reminder(index: int):
    ok, msg = bot_manager.remove_reminder(index)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.get("/api/scheduled")
def get_scheduled():
    return {"ok": True, "scheduled": bot_manager.get_scheduled()}


@app.post("/api/scheduled")
def add_scheduled(body: ScheduledIn):
    ok, msg = bot_manager.add_scheduled(body.channel_id, body.message, body.time, body.repeat)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.delete("/api/scheduled/{index}")
def remove_scheduled(index: int):
    ok, msg = bot_manager.remove_scheduled(index)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


# ── Music / Voice ──────────────────────────────────────────────────────

@app.post("/api/guilds/{guild_id}/voice/join")
def voice_join(guild_id: int, body: VoiceJoinIn):
    require_connected()
    ok, msg = bot_manager.run_coro(bot_manager.join_voice(guild_id, body.channel_id))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/guilds/{guild_id}/voice/leave")
def voice_leave(guild_id: int):
    require_connected()
    ok, msg = bot_manager.run_coro(bot_manager.leave_voice(guild_id))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/guilds/{guild_id}/music/play")
def music_play(guild_id: int, body: PlayIn):
    require_connected()
    ok, msg = bot_manager.run_coro(bot_manager.play_youtube(guild_id, body.url))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/guilds/{guild_id}/music/search")
def music_search(guild_id: int, body: SearchIn):
    require_connected()
    ok, res = bot_manager.search_youtube(body.query, 10)
    if not ok:
        raise HTTPException(status_code=400, detail=res)
    return {"ok": True, "results": res}


@app.post("/api/guilds/{guild_id}/music/skip")
def music_skip(guild_id: int):
    require_connected()
    ok, msg = bot_manager.run_coro(bot_manager.skip_track(guild_id))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/guilds/{guild_id}/music/stop")
def music_stop(guild_id: int):
    require_connected()
    ok, msg = bot_manager.run_coro(bot_manager.stop_playback(guild_id))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/guilds/{guild_id}/music/clear")
def music_clear(guild_id: int):
    bot_manager.clear_queue(guild_id)
    return {"ok": True, "message": "تم مسح القائمة"}


@app.post("/api/guilds/{guild_id}/music/volume")
def music_volume(guild_id: int, body: VolumeIn):
    bot_manager.set_volume(guild_id, body.volume)
    return {"ok": True, "message": f"تم ضبط مستوى الصوت: {body.volume}%"}


@app.get("/api/guilds/{guild_id}/music/status")
def music_status(guild_id: int):
    return bot_manager.get_music_status(guild_id)


@app.post("/api/guilds/{guild_id}/music/pause")
def music_pause(guild_id: int):
    require_connected()
    ok, msg = bot_manager.run_coro(bot_manager.pause_track(guild_id))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/guilds/{guild_id}/music/resume")
def music_resume(guild_id: int):
    require_connected()
    ok, msg = bot_manager.run_coro(bot_manager.resume_track(guild_id))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/guilds/{guild_id}/music/loop")
def music_loop(guild_id: int):
    result = bot_manager.toggle_loop(guild_id)
    return {"ok": True, "loop": result, "message": "🔄 تكرار الأغنية مفعّل" if result else "🔄 تكرار الأغنية معطّل"}


@app.post("/api/guilds/{guild_id}/music/queue-loop")
def music_queue_loop(guild_id: int):
    result = bot_manager.toggle_queue_loop(guild_id)
    return {"ok": True, "queue_loop": result, "message": "🔁 تكرار القائمة مفعّل" if result else "🔁 تكرار القائمة معطّل"}


@app.post("/api/guilds/{guild_id}/music/shuffle")
def music_shuffle(guild_id: int):
    result = bot_manager.toggle_shuffle(guild_id)
    return {"ok": True, "shuffle": result, "message": "🔀 خلط القائمة مفعّل" if result else "🔀 خلط القائمة معطّل"}


@app.post("/api/guilds/{guild_id}/music/stay")
def music_stay(guild_id: int):
    current = bot_manager.get_stay_in_vc(guild_id)
    bot_manager.set_stay_in_vc(guild_id, not current)
    new_val = not current
    return {"ok": True, "stay": new_val, "message": "🏠 البقاء في القناة مفعّل" if new_val else "🏠 البقاء في القناة معطّل"}


@app.post("/api/guilds/{guild_id}/music/nowplaying")
def music_nowplaying_embed(guild_id: int, body: dict = None):
    require_connected()
    channel_id = body.get("channel_id") if body else None
    if not channel_id:
        raise HTTPException(status_code=400, detail="حدد قناة الإرسال")
    embed = bot_manager._music_embed(guild_id)
    if not embed:
        raise HTTPException(status_code=400, detail="لا يوجد تشغيل حالياً")
    ok, msg = bot_manager.run_coro(bot_manager.send_message(channel_id, "", embed=embed))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": "تم إرسال الآن 플اي"}


class PlayInEnhanced(BaseModel):
    url: str
    requester: str = ""
    channel: str = ""


@app.post("/api/guilds/{guild_id}/music/play-enhanced")
def music_play_enhanced(guild_id: int, body: PlayInEnhanced):
    require_connected()
    ok, msg = bot_manager.run_coro(bot_manager.play_youtube(guild_id, body.url, body.requester, body.channel))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


class CommandIn(BaseModel):
    command: str
    voice_channel_id: int = None


@app.post("/api/guilds/{guild_id}/music/command")
def music_command(guild_id: int, body: CommandIn):
    require_connected()
    result = bot_manager.run_coro(
        bot_manager._exec_music_command(guild_id, body.command, body.voice_channel_id)
    )
    return {"ok": True, "content": result.get("content"), "embed": result.get("embed")}


class PanelIn(BaseModel):
    channel_id: int


@app.post("/api/guilds/{guild_id}/music/panel")
def send_music_panel(guild_id: int, body: PanelIn):
    from bot_client import MusicPanelView
    view = MusicPanelView(bot_manager)
    embed = view.build(guild_id)
    ok, msg = bot_manager.run_coro(_send_panel_to_channel(body.channel_id, embed, view))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


class PanelChannelIn(BaseModel):
    channel_id: int


@app.post("/api/guilds/{guild_id}/music/panel-channel")
def set_panel_channel(guild_id: int, body: PanelChannelIn):
    bot_manager.set_panel_channel(guild_id, body.channel_id)
    return {"ok": True, "message": f"تم ضبط قناة الـ Panel"}


@app.get("/api/guilds/{guild_id}/music/panel-channel")
def get_panel_channel(guild_id: int):
    ch_id = bot_manager.get_panel_channel(guild_id)
    return {"ok": True, "channel_id": ch_id}


async def _send_panel_to_channel(channel_id: int, embed, view):
    channel = bot_manager.client.get_channel(channel_id)
    if not channel:
        return False, "قناة غير موجودة"
    try:
        await channel.send(embed=embed, view=view)
        return True, "تم إرسال Panel الموسيقى"
    except Exception as e:
        return False, str(e)


# ── Tickets ────────────────────────────────────────────────────────────

@app.get("/api/guilds/{guild_id}/tickets")
def get_tickets_config(guild_id: int):
    return {"ok": True, "config": bot_manager.get_ticket_config(guild_id)}


@app.post("/api/guilds/{guild_id}/tickets")
def set_tickets_config(guild_id: int, body: TicketConfigIn):
    bot_manager.configure_tickets(
        guild_id, body.category_id, body.staff_role_id,
        body.welcome_msg, body.panel_title, body.panel_desc, body.color,
    )
    return {"ok": True, "message": "تم حفظ إعدادات التذاكر"}


@app.post("/api/channels/{channel_id}/ticket-panel/{guild_id}")
def send_ticket_panel(channel_id: int, guild_id: int):
    require_connected()
    ok, msg = bot_manager.run_coro(bot_manager.send_ticket_panel(channel_id, guild_id))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


# ── Emojis ─────────────────────────────────────────────────────────────

@app.get("/api/guilds/{guild_id}/emojis")
def list_emojis(guild_id: int):
    require_connected()
    emojis = bot_manager.list_guild_emojis(guild_id)
    for e in emojis:
        e["id"] = str(e["id"])
    return {"ok": True, "emojis": emojis}


@app.post("/api/guilds/{guild_id}/emojis")
def upload_emoji(guild_id: int, body: EmojiIn):
    require_connected()
    ok, msg = bot_manager.run_coro(bot_manager.upload_emoji(guild_id, body.name, body.image_url))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


class EmojiTransferIn(BaseModel):
    target_guild_id: int
    emoji_ids: list[str] = []


@app.post("/api/guilds/{guild_id}/emojis/transfer")
def transfer_emojis(guild_id: int, body: EmojiTransferIn):
    require_connected()
    source_guild = _get_guild(guild_id)
    target_guild = _get_guild(body.target_guild_id)
    if not source_guild or not target_guild:
        raise HTTPException(status_code=404, detail="أحد السيرفرات غير موجود")

    source_emojis = list(source_guild.emojis)
    if body.emoji_ids:
        source_emojis = [e for e in source_emojis if str(e.id) in body.emoji_ids]

    if not source_emojis:
        raise HTTPException(status_code=400, detail="لا إيموجي للنقل")

    transferred = 0
    failed = 0
    errors = []
    for emoji in source_emojis:
        try:
            image_data = await_(emoji.read())
            ext = "gif" if emoji.animated else "png"
            file_obj = __import__("io").BytesIO(image_data)
            file_obj.name = f"{emoji.name}.{ext}"
            bot_manager.run_coro(
                target_guild.create_custom_emoji(name=emoji.name, image=file_obj.read())
            )
            transferred += 1
        except Exception as e:
            failed += 1
            errors.append(f"{emoji.name}: {str(e)[:50]}")

    _log_audit("emojis_transferred", "admin", f"نقل {transferred} إيموجي من {source_guild.name} إلى {target_guild.name}")

    msg = f"✅ تم نقل {transferred} إيموجي بنجاح"
    if failed:
        msg += f"\n❌ فشل نقل {failed} إيموجي"
        if errors:
            msg += "\n" + "\n".join(errors[:5])
    return {"ok": transferred > 0, "message": msg, "transferred": transferred, "failed": failed}


@app.post("/api/guilds/{guild_id}/emojis/transfer-all")
def transfer_all_emojis(guild_id: int, body: dict):
    require_connected()
    target_id = body.get("target_guild_id")
    if not target_id:
        raise HTTPException(status_code=400, detail="حدد السيرفر الهدف")

    source_guild = _get_guild(guild_id)
    target_guild = _get_guild(target_id)
    if not source_guild or not target_guild:
        raise HTTPException(status_code=404, detail="أحد السيرفرات غير موجود")

    source_emojis = list(source_guild.emojis)
    if not source_emojis:
        return {"ok": True, "message": "لا إيموجي في السيرفر المصدر"}

    target_emoji_names = {e.name for e in target_guild.emojis}
    to_transfer = [e for e in source_emojis if e.name not in target_emoji_names]

    transferred = 0
    failed = 0
    skipped = len(source_emojis) - len(to_transfer)
    for emoji in to_transfer:
        try:
            image_data = await_(emoji.read())
            ext = "gif" if emoji.animated else "png"
            file_obj = __import__("io").BytesIO(image_data)
            file_obj.name = f"{emoji.name}.{ext}"
            bot_manager.run_coro(
                target_guild.create_custom_emoji(name=emoji.name, image=file_obj.read())
            )
            transferred += 1
        except Exception as e:
            failed += 1

    _log_audit("emojis_transfer_all", "admin", f"نقل الكل: {transferred} من {source_guild.name} إلى {target_guild.name}")

    msg = f"✅ تم نقل {transferred} إيموجي"
    if skipped:
        msg += f" · ⏭️ {skipped} موجود مسبقاً"
    if failed:
        msg += f" · ❌ فشل {failed}"
    return {"ok": transferred > 0, "message": msg, "transferred": transferred, "failed": failed, "skipped": skipped}


# ── DM All ─────────────────────────────────────────────────────────────

@app.post("/api/guilds/{guild_id}/dm-all")
def dm_all(guild_id: int, body: DMAllIn):
    require_connected()
    _log_audit("dm_all", "admin", f"إرسال جماعي في السيرفر {guild_id}")
    ok, msg = bot_manager.run_coro(bot_manager.dm_all_members(guild_id, body.message), timeout=1800)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


# ── Roles Manager (جديد) ───────────────────────────────────────────────

class RoleIn(BaseModel):
    name: str
    color: str = "#5865F2"
    permissions: list[str] = []
    hoist: bool = False
    mentionable: bool = True

class RoleEditIn(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    permissions: Optional[list[str]] = None
    hoist: Optional[bool] = None
    mentionable: Optional[bool] = None


@app.get("/api/guilds/{guild_id}/roles/managed")
def get_roles_managed(guild_id: int):
    require_connected()
    guild = _get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    roles = []
    for r in sorted(guild.roles, key=lambda x: x.position, reverse=True):
        roles.append({
            "id": str(r.id),
            "name": r.name,
            "color": str(r.color),
            "position": r.position,
            "default": r.is_default(),
            "hoist": r.hoist,
            "mentionable": r.mentionable,
            "member_count": len(r.members),
            "permissions": [p[0] for p in r.permissions if p[1]],
        })
    return {"ok": True, "roles": roles}


@app.post("/api/guilds/{guild_id}/roles/create")
def create_role(guild_id: int, body: RoleIn):
    require_connected()
    guild = _get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    try:
        color = int(body.color.replace("#", ""), 16)
        perms = discord.Permissions()
        for p in body.permissions:
            if hasattr(perms, p):
                setattr(perms, p, True)
        role = bot_manager.run_coro(guild.create_role(name=body.name, color=discord.Color(color), permissions=perms, hoist=body.hoist, mentionable=body.mentionable))
        _log_audit("role_created", "admin", f"إنشاء رول: {body.name}")
        return {"ok": True, "message": f"تم إنشاء الرول {body.name}", "role_id": str(role.id)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/guilds/{guild_id}/roles/{role_id}")
def edit_role(guild_id: int, role_id: int, body: RoleEditIn):
    require_connected()
    guild = _get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    role = discord.utils.get(guild.roles, id=role_id)
    if not role:
        raise HTTPException(status_code=404, detail="الرول غير موجود")
    try:
        kwargs = {}
        if body.name is not None:
            kwargs["name"] = body.name
        if body.color is not None:
            kwargs["color"] = discord.Color(int(body.color.replace("#", ""), 16))
        if body.hoist is not None:
            kwargs["hoist"] = body.hoist
        if body.mentionable is not None:
            kwargs["mentionable"] = body.mentionable
        if body.permissions is not None:
            perms = discord.Permissions()
            for p in body.permissions:
                if hasattr(perms, p):
                    setattr(perms, p, True)
            kwargs["permissions"] = perms
        bot_manager.run_coro(role.edit(**kwargs))
        _log_audit("role_edited", "admin", f"تعديل رول: {role.name}")
        return {"ok": True, "message": f"تم تعديل الرول {role.name}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/guilds/{guild_id}/roles/{role_id}")
def delete_role(guild_id: int, role_id: int):
    require_connected()
    guild = _get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    role = discord.utils.get(guild.roles, id=role_id)
    if not role:
        raise HTTPException(status_code=404, detail="الرول غير موجود")
    try:
        name = role.name
        bot_manager.run_coro(role.delete())
        _log_audit("role_deleted", "admin", f"حذف رول: {name}")
        return {"ok": True, "message": f"تم حذف الرول {name}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/guilds/{guild_id}/roles/{role_id}/assign/{member_id}")
def assign_role(guild_id: int, role_id: int, member_id: int):
    require_connected()
    guild = _get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    role = discord.utils.get(guild.roles, id=role_id)
    member = guild.get_member(member_id)
    if not role or not member:
        raise HTTPException(status_code=404, detail="الرول أو العضو غير موجود")
    try:
        bot_manager.run_coro(member.add_roles(role))
        _log_audit("role_assigned", "admin", f"إضافة رول {role.name} للعضو {member.display_name}")
        return {"ok": True, "message": f"تم إضافة رول {role.name} للعضو {member.display_name}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/guilds/{guild_id}/roles/{role_id}/remove/{member_id}")
def remove_role(guild_id: int, role_id: int, member_id: int):
    require_connected()
    guild = _get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    role = discord.utils.get(guild.roles, id=role_id)
    member = guild.get_member(member_id)
    if not role or not member:
        raise HTTPException(status_code=404, detail="الرول أو العضو غير موجود")
    try:
        bot_manager.run_coro(member.remove_roles(role))
        _log_audit("role_removed", "admin", f"إزالة رول {role.name} من العضو {member.display_name}")
        return {"ok": True, "message": f"تم إزالة رول {role.name} من العضو {member.display_name}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Polls / Voting System (جديد) ──────────────────────────────────────

class PollIn(BaseModel):
    channel_id: int
    question: str
    options: list[str]
    duration_hours: int = 24
    anonymous: bool = False

class PollVoteIn(BaseModel):
    poll_id: str
    option_index: int

_polls_storage: dict = {}

@app.post("/api/guilds/{guild_id}/polls/create")
def create_poll(guild_id: int, body: PollIn):
    require_connected()
    poll_id = secrets.token_hex(8)
    poll = {
        "id": poll_id,
        "guild_id": guild_id,
        "channel_id": body.channel_id,
        "question": body.question,
        "options": [{"text": opt, "votes": 0, "voters": []} for opt in body.options],
        "duration_hours": body.duration_hours,
        "anonymous": body.anonymous,
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(hours=body.duration_hours)).isoformat(),
        "active": True,
    }
    _polls_storage[poll_id] = poll
    try:
        options_text = "\n".join([f"{i+1}️⃣ {opt}" for i, opt in enumerate(body.options)])
        msg = f"**📊 استطلاع: {body.question}**\n\n{options_text}\n\n⏰ ينتهي خلال {body.duration_hours} ساعة\n💡 اكتب رقم الخيار للتصويت"
        bot_manager.run_coro(bot_manager.send_message(body.channel_id, msg))
        _log_audit("poll_created", "admin", f"إنشاء استطلاع: {body.question}")
        return {"ok": True, "message": "تم إنشاء الاستطلاع", "poll_id": poll_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/guilds/{guild_id}/polls")
def get_polls(guild_id: int):
    guild_polls = [p for p in _polls_storage.values() if p["guild_id"] == guild_id]
    return {"ok": True, "polls": guild_polls}


@app.post("/api/guilds/{guild_id}/polls/vote")
def vote_poll(guild_id: int, body: PollVoteIn):
    if body.poll_id not in _polls_storage:
        raise HTTPException(status_code=404, detail="الاستطلاع غير موجود")
    poll = _polls_storage[body.poll_id]
    if not poll["active"]:
        raise HTTPException(status_code=400, detail="الاستطلاع منتهي")
    if body.option_index < 0 or body.option_index >= len(poll["options"]):
        raise HTTPException(status_code=400, detail="خيار غير صالح")
    poll["options"][body.option_index]["votes"] += 1
    _log_audit("poll_vote", "admin", f"تصويت في استطلاع: {poll['question']}")
    return {"ok": True, "message": "تم التصويت"}


@app.delete("/api/guilds/{guild_id}/polls/{poll_id}")
def delete_poll(guild_id: int, poll_id: str):
    if poll_id in _polls_storage:
        del _polls_storage[poll_id]
        _log_audit("poll_deleted", "admin", f"حذف استطلاع: {poll_id}")
    return {"ok": True, "message": "تم حذف الاستطلاع"}


# ── Audit Log (جديد) ─────────────────────────────────────────────────

@app.get("/api/audit-log")
def get_audit_log(limit: int = 50):
    logs = []
    if os.path.exists(AUDIT_LOG_FILE):
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines[-limit:]:
                logs.append(line.strip())
    return {"ok": True, "logs": logs}


@app.delete("/api/audit-log")
def clear_audit_log():
    try:
        with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")
        return {"ok": True, "message": "تم مسح السجلات"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Soundboard (جديد) ────────────────────────────────────────────────

SOUNDBOARD_DIR = os.path.join(WEB_DIR, "static", "assets", "sounds")
os.makedirs(SOUNDBOARD_DIR, exist_ok=True)

@app.get("/api/guilds/{guild_id}/soundboard")
def get_sounds(guild_id: int):
    sounds = []
    if os.path.exists(SOUNDBOARD_DIR):
        for f in os.listdir(SOUNDBOARD_DIR):
            if f.endswith(('.mp3', '.wav', '.ogg')):
                sounds.append({"name": f.rsplit(".", 1)[0], "file": f})
    return {"ok": True, "sounds": sounds}


@app.post("/api/guilds/{guild_id}/soundboard/play")
def play_sound(guild_id: int, body: dict):
    require_connected()
    sound_name = body.get("name", "")
    channel_id = body.get("channel_id")
    if not sound_name:
        raise HTTPException(status_code=400, detail="اسم الصوت مطلوب")
    _log_audit("soundboard_play", "admin", f"تشغيل صوت: {sound_name}")
    return {"ok": True, "message": f"تم تشغيل {sound_name}"}


# ── Unified Search (جديد) ────────────────────────────────────────────

@app.get("/api/guilds/{guild_id}/search")
def search_guild(guild_id: int, q: str = ""):
    require_connected()
    guild = _get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    results = {"channels": [], "members": [], "roles": [], "emojis": []}
    q_lower = q.lower()
    for ch in guild.channels:
        if q_lower in ch.name.lower():
            results["channels"].append({"id": str(ch.id), "name": ch.name, "type": type(ch).__name__})
    for m in guild.members:
        if q_lower in str(m).lower() or q_lower in m.display_name.lower():
            results["members"].append({"id": str(m.id), "name": str(m), "display_name": m.display_name})
    for r in guild.roles:
        if q_lower in r.name.lower():
            results["roles"].append({"id": str(r.id), "name": r.name, "color": str(r.color)})
    for e in guild.emojis:
        if q_lower in e.name.lower():
            results["emojis"].append({"id": str(e.id), "name": e.name, "url": str(e.url)})
    return {"ok": True, "results": results}


# ── Enhanced Statistics (جديد) ───────────────────────────────────────

@app.get("/api/guilds/{guild_id}/stats/advanced")
def advanced_stats(guild_id: int):
    require_connected()
    guild = _get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    members = list(guild.members)
    bots = [m for m in members if m.bot]
    humans = [m for m in members if not m.bot]
    online = [m for m in humans if m.status != discord.Status.offline]
    text_ch = [ch for ch in guild.channels if isinstance(ch, (discord.TextChannel, discord.ForumChannel))]
    voice_ch = [ch for ch in guild.channels if isinstance(ch, discord.VoiceChannel)]
    categories = [ch for ch in guild.channels if isinstance(ch, discord.CategoryChannel)]
    roles = list(guild.roles)
    emojis = list(guild.emojis)
    now = datetime.now()
    recent_joins = [m for m in humans if m.joined_at and (now - m.joined_at.replace(tzinfo=None)).days < 7]
    stats = {
        "total_members": len(members),
        "total_bots": len(bots),
        "total_humans": len(humans),
        "online_members": len(online),
        "text_channels": len(text_ch),
        "voice_channels": len(voice_ch),
        "categories": len(categories),
        "roles_count": len(roles),
        "emojis_count": len(emojis),
        "boost_level": getattr(guild, "premium_tier", 0),
        "boosts": getattr(guild, "premium_subscription_count", 0) or 0,
        "recent_joins_7d": len(recent_joins),
        "verification_level": str(guild.verification_level),
        "content_filter": str(guild.explicit_content_filter),
        "mfa_level": guild.mfa_level,
        "vanity_url": str(getattr(guild, "vanity_url", None) or ""),
        "splash": str(getattr(guild, "splash", None) or ""),
        "banner": _asset_url(guild.banner, 1024) if guild.banner else "",
    }
    return {"ok": True, "stats": stats}


# ── Permissions System (جديد) ────────────────────────────────────────

class UserPermIn(BaseModel):
    username: str
    password: str
    permissions: list[str] = ["view"]

@app.get("/api/admin/users")
def get_users():
    users = _load_users()
    safe_users = {}
    for k, v in users.items():
        safe_users[k] = {"role": v.get("role", "user"), "permissions": v.get("permissions", [])}
    return {"ok": True, "users": safe_users}


@app.post("/api/admin/users")
def add_user(body: UserPermIn):
    users = _load_users()
    if body.username in users:
        raise HTTPException(status_code=400, detail="المستخدم موجود مسبقاً")
    users[body.username] = {
        "password": _hash_password(body.password),
        "role": "user",
        "permissions": body.permissions,
    }
    _save_users(users)
    _log_audit("user_added", "admin", f"إضافة مستخدم: {body.username}")
    return {"ok": True, "message": f"تم إضافة المستخدم {body.username}"}


@app.delete("/api/admin/users/{username}")
def delete_user(username: str):
    users = _load_users()
    if username == "admin":
        raise HTTPException(status_code=400, detail="لا يمكن حذف المسؤول الرئيسي")
    if username in users:
        del users[username]
        _save_users(users)
        _log_audit("user_deleted", "admin", f"حذف مستخدم: {username}")
    return {"ok": True, "message": "تم حذف المستخدم"}


@app.put("/api/admin/users/{username}/permissions")
def update_permissions(username: str, body: dict):
    users = _load_users()
    if username not in users:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    users[username]["permissions"] = body.get("permissions", [])
    _save_users(users)
    _log_audit("permissions_updated", "admin", f"تحديث صلاحيات: {username}")
    return {"ok": True, "message": "تم تحديث الصلاحيات"}


# ── Protection ────────────────────────────────────────────────────────

@app.get("/api/guilds/{guild_id}/protection")
def get_protection(guild_id: int):
    require_connected()
    if not _get_guild(guild_id):
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    config = bot_manager.get_protection_config(guild_id)
    return {"ok": True, "config": config}


@app.post("/api/guilds/{guild_id}/protection")
def set_protection(guild_id: int, body: ProtectionIn):
    require_connected()
    if not _get_guild(guild_id):
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    ok, msg = bot_manager.set_protection_config(
        guild_id,
        bot_insult_kick=body.bot_insult_kick,
        bot_insult_warns_before_kick=body.bot_insult_warns_before_kick,
        max_warnings_before_ban=body.max_warnings_before_ban,
        anti_mass_mention=body.anti_mass_mention,
        mass_mention_threshold=body.mass_mention_threshold,
        spam_protection=body.spam_protection,
        spam_threshold=body.spam_threshold,
        spam_window=body.spam_window,
        raid_protection=body.raid_protection,
        raid_threshold=body.raid_threshold,
        raid_window=body.raid_window,
        greeting_protection=body.greeting_protection,
        link_block_enabled=body.link_block_enabled,
        auto_unban_enabled=body.auto_unban_enabled,
        auto_unban_hours=body.auto_unban_hours,
        auto_role_enabled=body.auto_role_enabled,
        auto_role_id=body.auto_role_id,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


# ── Auto-Role ────────────────────────────────────────────────────────

@app.get("/api/guilds/{guild_id}/auto-role")
def get_auto_role(guild_id: int):
    require_connected()
    if not _get_guild(guild_id):
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    cfg = bot_manager.get_protection_config(guild_id)
    return {"ok": True, "enabled": cfg.get("auto_role_enabled", False), "role_id": cfg.get("auto_role_id", 0)}


@app.post("/api/guilds/{guild_id}/auto-role")
def set_auto_role(guild_id: int, body: AutoRoleIn):
    require_connected()
    if not _get_guild(guild_id):
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    ok, msg = bot_manager.set_protection_config(
        guild_id,
        auto_role_enabled=body.enabled,
        auto_role_id=body.role_id,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


# ── Link Block ───────────────────────────────────────────────────────

@app.get("/api/guilds/{guild_id}/link-block")
def get_link_block(guild_id: int):
    require_connected()
    if not _get_guild(guild_id):
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    cfg = bot_manager.get_protection_config(guild_id)
    return {"ok": True, "enabled": cfg.get("link_block_enabled", False),
            "channels": cfg.get("link_block_channels", []),
            "whitelist": cfg.get("link_block_whitelist", [])}


@app.post("/api/guilds/{guild_id}/link-block")
def set_link_block(guild_id: int, body: LinkBlockIn):
    require_connected()
    if not _get_guild(guild_id):
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    ok, msg = bot_manager.set_protection_config(
        guild_id,
        link_block_enabled=body.enabled,
        link_block_channels=body.channels,
        link_block_whitelist=body.whitelist,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


# ── Auto-Unban ───────────────────────────────────────────────────────

@app.get("/api/guilds/{guild_id}/auto-unban")
def get_auto_unban(guild_id: int):
    require_connected()
    if not _get_guild(guild_id):
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    cfg = bot_manager.get_protection_config(guild_id)
    return {"ok": True, "enabled": cfg.get("auto_unban_enabled", False), "hours": cfg.get("auto_unban_hours", 24)}


@app.post("/api/guilds/{guild_id}/auto-unban")
def set_auto_unban(guild_id: int, body: AutoUnbanIn):
    require_connected()
    if not _get_guild(guild_id):
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    ok, msg = bot_manager.set_protection_config(
        guild_id,
        auto_unban_enabled=body.enabled,
        auto_unban_hours=body.hours,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


# ── Live Stats ───────────────────────────────────────────────────────

@app.get("/api/guilds/{guild_id}/live-stats")
def live_stats(guild_id: int):
    require_connected()
    guild = _get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="سيرفر غير موجود")
    members = list(guild.members)
    humans = [m for m in members if not m.bot]
    online = [m for m in humans if m.status != discord.Status.offline]
    voice_active = sum(1 for m in members if m.voice and m.voice.channel)
    uptime_val = bot_manager.client.uptime if bot_manager.ready and bot_manager.client else datetime.now()
    try:
        uptime_seconds = (datetime.now().utcnow() - uptime_val).total_seconds() if hasattr(uptime_val, 'year') else 0
    except Exception:
        uptime_seconds = 0
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory().percent
    except ImportError:
        cpu = 0
        ram = 0
    return {
        "ok": True,
        "members": len(members),
        "online": len(online),
        "messages_today": 0,
        "voice_active": voice_active,
        "uptime": int(uptime_seconds),
        "cpu": cpu,
        "ram": ram,
    }


# ── Health ───────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    import psutil as _psutil
    uptime_seconds = 0
    if bot_manager.ready and bot_manager.client and hasattr(bot_manager.client, 'uptime') and bot_manager.client.uptime:
        try:
            uptime_seconds = (datetime.utcnow() - bot_manager.client.uptime).total_seconds()
        except Exception:
            pass
    total_members = sum(g.member_count or 0 for g in bot_manager.guilds)
    try:
        import psutil
        _cpu = psutil.cpu_percent(interval=0)
        _ram = psutil.virtual_memory()
        cpu_percent = _cpu
        ram_percent = _ram.percent
        ram_used_mb = _ram.used / (1024 * 1024)
        ram_total_mb = _ram.total / (1024 * 1024)
    except Exception:
        cpu_percent = 0
        ram_percent = 0
        ram_used_mb = 0
        ram_total_mb = 0
    return {
        "ok": True,
        "uptime": int(uptime_seconds),
        "guilds_count": len(bot_manager.guilds),
        "total_members": total_members,
        "version": "2.0.0",
        "cpu_percent": cpu_percent,
        "ram_percent": ram_percent,
        "ram_used_mb": ram_used_mb,
        "ram_total_mb": ram_total_mb,
    }


# ── Welcome Card Config ────────────────────────────────────────────


class WelcomeCardIn(BaseModel):
    enabled: Optional[bool] = None
    channel_id: Optional[int] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    bg_color: Optional[str] = None
    text_color: Optional[str] = None
    accent_color: Optional[str] = None
    show_avatar: Optional[bool] = None
    show_member_count: Optional[bool] = None
    border_style: Optional[str] = None
    custom_image: Optional[str] = None


@app.get("/api/guilds/{guild_id}/welcome-config")
async def get_welcome_config(guild_id: int):
    if not require_connected():
        return {"ok": False, "error": "not connected"}
    guild = _get_guild(guild_id)
    if not guild:
        return {"ok": False, "error": "guild not found"}
    cfg = bot_manager.run_coro(bot_manager.get_welcome_config(guild_id))
    return {"ok": True, **cfg}


@app.post("/api/guilds/{guild_id}/welcome-config")
async def set_welcome_config(guild_id: int, body: WelcomeCardIn):
    if not require_connected():
        return {"ok": False, "error": "not connected"}
    guild = _get_guild(guild_id)
    if not guild:
        return {"ok": False, "error": "guild not found"}
    kwargs = {k: v for k, v in body.dict().items() if v is not None}
    bot_manager.run_coro(bot_manager.set_welcome_config(guild_id, **kwargs))
    return {"ok": True, "message": "تم حفظ إعدادات بطاقة الترحيب"}


# ── Embed Builder Send ─────────────────────────────────────────────


class EmbedSendIn(BaseModel):
    channel_id: int
    title: str = ""
    description: str = ""
    color: str = "#5865F2"
    author_name: str = ""
    author_icon: str = ""
    footer_text: str = ""
    footer_icon: str = ""
    thumbnail: str = ""
    image: str = ""
    fields: Optional[List[Dict[str, Any]]] = None


@app.post("/api/guilds/{guild_id}/embed/send")
async def send_embed(guild_id: int, body: EmbedSendIn):
    if not require_connected():
        return {"ok": False, "error": "not connected"}
    guild = _get_guild(guild_id)
    if not guild:
        return {"ok": False, "error": "guild not found"}
    channel = guild.get_channel(body.channel_id)
    if not channel:
        return {"ok": False, "error": "channel not found"}

    import discord

    color_hex = body.color.lstrip("#")
    color_int = int(color_hex, 16) if color_hex else 0x5865F2

    embed = discord.Embed(
        title=body.title, description=body.description, color=color_int
    )
    if body.author_name:
        embed.set_author(name=body.author_name, icon_url=body.author_icon or None)
    if body.footer_text:
        embed.set_footer(text=body.footer_text, icon_url=body.footer_icon or None)
    if body.thumbnail:
        embed.set_thumbnail(url=body.thumbnail)
    if body.image:
        embed.set_image(url=body.image)
    if body.fields:
        for f in body.fields:
            embed.add_field(name=f.get("name", ""), value=f.get("value", ""), inline=f.get("inline", False))

    async def _send():
        await channel.send(embed=embed)
        return True

    ok = bot_manager.run_coro(_send())
    if ok:
        return {"ok": True, "message": "تم إرسال الـ Embed بنجاح"}
    return {"ok": False, "error": "failed to send embed"}


@app.get("/")
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")


# ── Auto-start bot on server startup ──────────────────────────────────

@app.on_event("startup")
def _auto_start_bot():
    import threading
    token = _load_bot_token()
    if token:
        print("=" * 60)
        print("  Auto-connecting bot (background)...")
        print("=" * 60)
        def _connect():
            try:
                ok, msg = bot_manager.connect(token)
                print(f"  Bot: {msg}")
            except Exception as e:
                print(f"  Bot connect error: {e}")
        threading.Thread(target=_connect, daemon=True).start()
    else:
        print("=" * 60)
        print("  No saved token. Connect from the web panel.")
        print("=" * 60)


# Mount static AFTER routes so "/" isn't shadowed.
app.mount("/static", StaticFiles(directory=os.path.join(WEB_DIR, "static")), name="static")