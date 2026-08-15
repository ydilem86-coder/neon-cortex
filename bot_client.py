"""Discord bot async client wrapper."""

import asyncio
import hashlib
import json
import os
import random
import re
import threading
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import discord
import aiohttp
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
COOKIES_FILE = os.path.join(CONFIG_DIR, "cookies.txt")
TEMP_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "temp"
TEMP_DIR.mkdir(exist_ok=True)


def _get_ytdlp_opts() -> dict:
    """Get yt-dlp options with cookies if available."""
    opts = {
        "format": "ba/b",
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }
    if os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    return opts


def _ytdlp_extract_info(url: str, download: bool = False) -> dict:
    """Extract YouTube info using subprocess to ensure node runtime works."""
    import subprocess
    import json as _json

    cmd = [
        "yt-dlp",
        "--js-runtimes", "node",
        "--dump-json",
        "--no-warnings",
    ]
    if os.path.exists(COOKIES_FILE):
        cmd.extend(["--cookies", COOKIES_FILE])
    if url.startswith("ytsearch"):
        cmd.extend(["--default-search", "ytsearch"])
    cmd.append(url)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        cmd = ["python", "-m", "yt_dlp"] + cmd[1:]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip() or "yt-dlp failed"
        raise Exception(err)

    stdout = result.stdout.strip()
    if not stdout:
        raise Exception("yt-dlp returned empty output")

    data = _json.loads(stdout)

    if "formats" in data and not data.get("url"):
        audio_fmts = [f for f in data["formats"] if f.get("acodec") != "none" and f.get("vcodec") == "none"]
        if audio_fmts:
            best = max(audio_fmts, key=lambda f: f.get("abr", 0) or 0)
            data["url"] = best["url"]
            data["ext"] = best.get("ext", "mp3")
    if "formats" in data and not data.get("url"):
        audio_fmts = [f for f in data["formats"] if f.get("acodec") != "none"]
        if audio_fmts:
            best = max(audio_fmts, key=lambda f: f.get("abr", 0) or 0)
            data["url"] = best["url"]
            data["ext"] = best.get("ext", "mp3")

    return data


async def _invidious_search(query: str, limit: int = 5) -> list:
    """Search via Invidious API as fallback."""
    import aiohttp
    instances = [
        "https://vid.puffyan.us",
        "https://inv.tux.pizza",
        "https://invidious.snopyta.org",
        "https://yewtu.be",
        "https://inv.nadeko.net",
    ]
    for instance in instances:
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{instance}/api/v1/search?q={query}&type=video"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = []
                        for v in data[:limit]:
                            vid_id = v.get("videoId", "")
                            results.append({
                                "title": v.get("title", "?"),
                                "url": f"https://www.youtube.com/watch?v={vid_id}",
                                "duration": int(v.get("lengthSeconds", 0)),
                                "thumbnail": f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg",
                            })
                        if results:
                            return results
        except Exception:
            continue
    return []


async def _invidious_extract(video_id: str) -> dict:
    """Get video info via Invidious API as fallback."""
    import aiohttp
    instances = [
        "https://vid.puffyan.us",
        "https://inv.tux.pizza",
        "https://invidious.snopyta.org",
        "https://yewtu.be",
        "https://inv.nadeko.net",
    ]
    for instance in instances:
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{instance}/api/v1/videos/{video_id}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Find best audio format
                        for fmt in data.get("adaptiveFormats", []):
                            if fmt.get("type", "").startswith("audio"):
                                return {
                                    "url": fmt.get("url", ""),
                                    "title": data.get("title", ""),
                                    "thumbnail": f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                                    "duration": int(data.get("lengthSeconds", 0)),
                                }
        except Exception:
            continue
    raise Exception("Invidious: No audio stream found")


def _ytdlp_search(query: str, limit: int = 5) -> list:
    """Search YouTube using subprocess."""
    import subprocess
    import json as _json

    cmd = [
        "yt-dlp",
        "--js-runtimes", "node",
        "--dump-json",
        "--no-warnings",
        "--flat-playlist",
        "--default-search", "ytsearch",
        f"ytsearch{limit}:{query}",
    ]
    if os.path.exists(COOKIES_FILE):
        cmd.extend(["--cookies", COOKIES_FILE])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        cmd = ["python", "-m", "yt_dlp"] + cmd[1:]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        raise Exception(result.stderr.strip() or result.stdout.strip() or "yt-dlp search failed")

    results = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            e = _json.loads(line)
            vid = e.get("id") or e.get("url", "")
            vid_url = f"https://www.youtube.com/watch?v={vid}" if vid and not vid.startswith("http") else vid
            results.append({
                "title": e.get("title", "?"),
                "url": vid_url,
                "duration": int(e.get("duration") or 0),
                "thumbnail": e.get("thumbnail", f"https://img.youtube.com/vi/{e.get('id', '0')}/mqdefault.jpg"),
            })
        except Exception:
            pass
    return results


async def _resolve_spotify_url(url: str) -> tuple[str, str]:
    """Resolve a Spotify URL to track name + artist. Returns (query, thumbnail)."""
    import aiohttp
    import re

    # Try oembed API
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            async with session.get(f"https://open.spotify.com/oembed?url={url}", headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    if text.strip().startswith("{"):
                        data = __import__("json").loads(text)
                        title = data.get("title", "")
                        thumbnail = data.get("thumbnail_url", "")
                        if title:
                            return f"{title} official audio", thumbnail
    except Exception:
        pass

    # Fallback: extract from URL path
    match = re.search(r"spotify\.com/(track|playlist|album)/([a-zA-Z0-9]+)", url)
    if match:
        track_type = match.group(1)
        track_id = match.group(2)
        # Try to get info from Spotify's public embed page
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://open.spotify.com/embed/{track_type}/{track_id}", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        title_match = re.search(r'"name"\s*:\s*"([^"]+)"', html)
                        artist_match = re.search(r'"artists?\s*:\s*\[\s*\{[^}]*"name"\s*:\s*"([^"]+)"', html)
                        if title_match:
                            title = title_match.group(1)
                            artist = artist_match.group(1) if artist_match else ""
                            query = f"{artist} {title}".strip()
                            return f"{query} official audio", ""
        except Exception:
            pass

    return url, ""


def _is_spotify_url(url: str) -> bool:
    """Check if URL is a Spotify link."""
    return "open.spotify.com" in url or "spotify.link" in url

MUSIC_PREFIX = "!"


def _load_welcome_from_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("welcome_config", data.get("welcome", {}))
    except Exception:
        return {}


def _load_automod_from_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("automod", {})
    except Exception:
        return {}


def _load_protection_from_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("protection", {})
    except Exception:
        return {}


def _load_admins_from_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("admin_users", {})
    except Exception:
        return {}


def _load_antinuke_from_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("antinuke_config", {})
    except Exception:
        return {}


def _load_verification_from_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("verification", {})
    except Exception:
        return {}


def _load_reaction_roles_from_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("reaction_roles", {})
    except Exception:
        return {}


def _load_giveaways_from_config() -> list:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("giveaways", [])
    except Exception:
        return []


def _load_level_from_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("level_config", {})
    except Exception:
        return {}


def _load_levels_from_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("levels", {})
    except Exception:
        return {}


def _load_custom_commands_from_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("custom_commands", {})
    except Exception:
        return {}


def _load_birthday_from_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("birthday_config", {})
    except Exception:
        return {}


def _load_suggestion_from_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("suggestion_config", {})
    except Exception:
        return {}


def _load_suggestion_votes_from_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("suggestion_votes", {})
    except Exception:
        return {}


class BotManager:
    def __init__(self):
        self.client: Optional[discord.Client] = None
        self.loop = asyncio.new_event_loop()
        self.ready = False
        self.user: Optional[discord.ClientUser] = None
        self.guilds: list[discord.Guild] = []
        self.welcome_config: dict = _load_welcome_from_config()
        self.automod_config: dict = _load_automod_from_config()
        self.protection_config: dict = _load_protection_from_config()
        self.activity_log: list[str] = []
        self.voice_clients: dict[int, discord.VoiceClient] = {}
        self.now_playing: dict[int, str] = {}
        self.music_queues: dict[int, list] = {}
        self.music_volumes: dict[int, float] = {}
        self.stay_in_vc: dict[int, bool] = {}
        self._last_search: dict[int, list] = {}
        self.loop_mode: dict[int, bool] = {}          # True = loop single track
        self.queue_loop: dict[int, bool] = {}          # True = loop entire queue
        self.shuffle_mode: dict[int, bool] = {}        # True = shuffle
        self.paused: dict[int, bool] = {}              # True = paused
        self._pause_elapsed: dict[int, float] = {}     # elapsed time when paused
        self.np_info: dict[int, dict] = {}             # Now playing details: {title, url, thumbnail, duration, requester, channel}
        self._join_log: dict[int, list] = {}
        self._spam_log: dict[int, dict] = {}
        self._bot_insult_warns: dict[int, dict] = {}
        self._protection_spam_log: dict[int, dict] = {}
        self._protection_join_log: dict[int, list] = {}
        self.log_channels: dict[int, int] = {}
        self.scheduled_messages: list = []
        self.ticket_config: dict[int, dict] = {}
        self._bot_tokens: dict[str, "BotManager"] = {}
        self._token_id: str = ""
        self.panel_messages: dict[int, discord.Message] = {}    # guild_id -> panel message
        self.panel_channels: dict[int, int] = {}                # guild_id -> channel_id for panel
        self._welcome_log_callback: Optional[Callable[[str], None]] = None
        self._activity_callback: Optional[Callable[[str], None]] = None
        self.admin_users: dict = _load_admins_from_config()
        self.antinuke_config: dict = _load_antinuke_from_config()
        self._nuke_tracker: dict[int, dict] = {}
        self.verification_config: dict = _load_verification_from_config()
        self.reaction_roles_config: dict = _load_reaction_roles_from_config()
        self.giveaways: list = _load_giveaways_from_config()
        self.level_config: dict = _load_level_from_config()
        self.levels: dict = _load_levels_from_config()
        self.custom_commands: dict = _load_custom_commands_from_config()
        self._captcha_pending: dict[int, dict] = {}
        self.afk_users: dict[int, dict] = {}
        self.birthday_config: dict = _load_birthday_from_config()
        self.suggestion_config: dict = _load_suggestion_from_config()
        self.suggestion_votes: dict = _load_suggestion_votes_from_config()
        self.command_stats: dict[str, int] = {}
        self.error_log: list[dict] = []
        self.api_calls: list[dict] = []
        self._music_play_stats: dict[int, dict] = {}
        self._invite_cache: dict[int, list] = {}
        self._connect_time: float = _time.time()
        self._loop_thread = threading.Thread(target=self._run_loop_forever, daemon=True)
        self._loop_thread.start()
        self._ensure_default_admin()

    def _run_loop_forever(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    @staticmethod
    def _sanitize_token(token: str) -> str:
        token = token.strip().strip('"\'').strip()
        token = token.replace("\n", "").replace("\r", "").replace(" ", "")
        return token

    @staticmethod
    def _validate_token_format(token: str) -> tuple[bool, str]:
        if not token:
            return False, "التوكن فارغ"
        parts = token.split(".")
        if len(parts) != 3:
            return False, "صيغة التوكن غير صحيحة — يجب أن يكون 3 أجزاء مفصولة بنقطة"
        if len(parts[0]) < 20 or len(parts[1]) < 5 or len(parts[2]) < 20:
            return False, "التوكن قصير أو ناقص — تأكد من نسخه كاملاً"
        return True, ""

    def set_welcome_log_callback(self, callback: Optional[Callable[[str], None]]):
        self._welcome_log_callback = callback

    def set_activity_callback(self, callback: Optional[Callable[[str], None]]):
        self._activity_callback = callback

    def _log_activity(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {message}"
        self.activity_log.insert(0, entry)
        self.activity_log = self.activity_log[:100]
        if self._activity_callback:
            self._activity_callback(entry)

    def run_coro(self, coro, timeout: float = 60):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=timeout)

    def connect(self, token: str) -> tuple[bool, str]:
        token = self._sanitize_token(token)
        ok, msg = self._validate_token_format(token)
        if not ok:
            return False, msg

        try:
            future = asyncio.run_coroutine_threadsafe(self._connect_async(token), self.loop)
            return future.result(timeout=45)
        except TimeoutError:
            return False, "انتهت مهلة الاتصال — تحقق من الإنترنت وأعد المحاولة"
        except Exception as e:
            return False, f"خطأ: {e}"

    async def _connect_async(self, token: str) -> tuple[bool, str]:
        if self.client:
            await self._disconnect_async()

        self.ready = False
        intents = discord.Intents.all()
        self.client = discord.Client(intents=intents)
        ready_future: asyncio.Future = self.loop.create_future()

        @self.client.event
        async def on_ready():
            self.ready = True
            self.user = self.client.user
            self.guilds = list(self.client.guilds)
            if not ready_future.done():
                ready_future.set_result(True)

        @self.client.event
        async def on_member_join(member: discord.Member):
            self._log_activity(f"✅ انضم {member.display_name} إلى {member.guild.name}")
            await self._handle_member_join(member)
            await self._handle_raid(member)
            await self._handle_auto_role(member)
            await self._send_log(member.guild.id, f"👋 **دخول عضو جديد** {member.mention} ({member.display_name}) — {member.guild.name}")
            try:
                if member.guild:
                    invites = await member.guild.invites()
                    cached = self._invite_cache.get(member.guild.id, [])
                    for inv in invites:
                        for old in cached:
                            if inv.code == old.get("code") and inv.uses > old.get("uses", 0):
                                self._log_activity(f"🔗 دخول عبر دعوة: {member.display_name} بواسطة {inv.inviter} ({inv.code})")
                                await self._send_log(member.guild.id, f"🔗 **دخول عبر دعوة** — {member.mention} بواسطة {inv.inviter} ({inv.code}, استُخدم {inv.uses} مرات)")
                                break
                    self._invite_cache[member.guild.id] = [{"code": i.code, "uses": i.uses, "inviter": str(i.inviter)} for i in invites]
            except Exception:
                pass

        @self.client.event
        async def on_member_remove(member: discord.Member):
            self._log_activity(f"👋 غادر {member.display_name} من {member.guild.name}")
            await self._send_log(member.guild.id, f"🚪 **مغادرة عضو** {member.display_name} — {member.guild.name}")

        @self.client.event
        async def on_guild_join(guild: discord.Guild):
            self.guilds = list(self.client.guilds)
            self._log_activity(f"🆕 البوت انضم لسيرفر: {guild.name} ({guild.member_count} عضو)")

        @self.client.event
        async def on_guild_remove(guild: discord.Guild):
            self.guilds = list(self.client.guilds)
            self._log_activity(f"📤 البوت غادر سيرفر: {guild.name}")

        @self.client.event
        async def on_message(message: discord.Message):
            if message.author.bot or not message.guild:
                return
            if await self._handle_captcha_check(message):
                return
            await self._add_xp(message.guild.id, message.author.id)
            await self._handle_afk_on_message(message)
            await self._handle_suggestion_message(message)
            if message.content.startswith(MUSIC_PREFIX):
                _cmd = message.content.split(None, 1)[0][len(MUSIC_PREFIX):].lower()
                if _cmd:
                    self.command_stats[_cmd] = self.command_stats.get(_cmd, 0) + 1
                await self._handle_music_command(message)
                return
            _first = message.content.split(None, 1)[0] if message.content.strip() else ""
            for _pfx in ("!", ".", "?", "#", "$"):
                if _first.startswith(_pfx) and len(_first) > 1:
                    _cn = _first[1:].lower()
                    self.command_stats[_cn] = self.command_stats.get(_cn, 0) + 1
                    break
            if message.content.lower().startswith("afk"):
                if await self._handle_afk_command(message):
                    return
            if message.content.lower().startswith("remind "):
                if await self._handle_remind_command(message):
                    return
            await self._handle_custom_command(message)
            await self._handle_automod(message)
            await self._handle_bot_insult(message)
            await self._handle_link_block(message)
            await self._handle_spam_protection(message)
            await self._handle_mass_mention(message)

        @self.client.event
        async def on_voice_state_update(member: discord.Member, before, after):
            if member.id != self.client.user.id:
                return
            gid = member.guild.id
            # Bot joined a voice channel
            if not before.channel and after.channel:
                try:
                    await self.send_or_update_panel(gid)
                except Exception:
                    pass
            # Bot left a voice channel
            if before.channel and not after.channel:
                vc = self.voice_clients.pop(gid, None)
                if vc:
                    try:
                        await vc.disconnect()
                    except Exception:
                        pass
                self.now_playing.pop(gid, None)
                self.music_queues.pop(gid, None)
                self.panel_messages.pop(gid, None)

        @self.client.event
        async def on_member_ban(guild: discord.Guild, user):
            ch = self.log_channels.get(guild.id)
            if ch:
                await self._send_log(guild.id, f"🔨 **حظر** {user} — {guild.name}")
            await self._check_antinuke_action(guild, "ban")

        @self.client.event
        async def on_member_unban(guild: discord.Guild, user):
            ch = self.log_channels.get(guild.id)
            if ch:
                await self._send_log(guild.id, f"✅ **فك حظر** {user} — {guild.name}")

        @self.client.event
        async def on_member_remove(member: discord.Member):
            ch = self.log_channels.get(member.guild.id)
            if ch and member.id != self.client.user.id:
                await self._send_log(member.guild.id, f"👋 **غادر** {member.display_name} — {member.guild.name}")
            if self.get_antinuke_config(member.guild.id).get("enabled") and member.id != self.client.user.id:
                try:
                    async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
                        if entry.target and entry.target.id == member.id:
                            if entry.user and entry.user.id != self.client.user.id:
                                await self._check_antinuke_action(member.guild, "kick")
                            break
                except Exception:
                    pass

        @self.client.event
        async def on_message_delete(message):
            if message.author.bot or not message.guild:
                return
            ch = self.log_channels.get(message.guild.id)
            if ch:
                content = message.content[:100] if message.content else "(مرفق/صورة)"
                await self._send_log(message.guild.id, f"🗑 **حذف رسالة** من {message.author.display_name} في #{message.channel.name}:\n> {content}")

        @self.client.event
        async def on_message_edit(before, after):
            if before.author.bot or not before.guild:
                return
            if before.content == after.content:
                return
            ch = self.log_channels.get(before.guild.id)
            if ch:
                old = before.content[:80] if before.content else "(فارغ)"
                new = after.content[:80] if after.content else "(فارغ)"
                await self._send_log(before.guild.id, f"✏️ **تعديل رسالة** من {before.author.display_name} في #{before.channel.name}:\n**قبل:** {old}\n**بعد:** {new}")

        @self.client.event
        async def on_member_update(before: discord.Member, after: discord.Member):
            if before.bot or before.id == self.client.user.id:
                return
            cfg = self.get_protection_config(after.guild.id)
            if not cfg.get("anti_hoist_enabled"):
                return
            if before.display_name == after.display_name:
                return
            hoist_chars = ('!', '.', '@', '#')
            new_name = after.display_name
            if new_name and len(new_name) > 0 and new_name[0] in hoist_chars:
                action = cfg.get("anti_hoist_action", "rename")
                if action == "kick":
                    try:
                        await after.kick(reason="Anti-Hoist: Name starts with special character")
                        self._log_activity(f"👢 Anti-Hoist: Kicked {after.display_name} from {after.guild.name}")
                        await self._send_log(after.guild.id, f"👢 **Anti-Hoist** — تم طرد {after.mention} — الاسم يبدأ بحرف خاص '{new_name[0]}'")
                    except discord.Forbidden:
                        pass
                    except Exception:
                        pass
                else:
                    try:
                        await after.edit(nick="Hoisted User", reason="Anti-Hoist: Name starts with special character")
                        self._log_activity(f"✏️ Anti-Hoist: Renamed {before.display_name} to 'Hoisted User' in {after.guild.name}")
                        await self._send_log(after.guild.id, f"✏️ **Anti-Hoist** — تم تغيير اسم {after.mention} من '{before.display_name}' إلى 'Hoisted User'")
                    except discord.Forbidden:
                        pass
                    except Exception:
                        pass

        @self.client.event
        async def on_guild_channel_create(channel):
            if not channel.guild:
                return
            ch = self.log_channels.get(channel.guild.id)
            if ch:
                await self._send_log(channel.guild.id, f"📁 **إنشاء قناة** #{channel.name} ({channel.type}) — {channel.guild.name}")
            await self._check_antinuke_action(channel.guild, "channel_create")

        @self.client.event
        async def on_guild_channel_delete(channel):
            if not channel.guild:
                return
            ch = self.log_channels.get(channel.guild.id)
            if ch:
                await self._send_log(channel.guild.id, f"❌ **حذف قناة** #{channel.name} ({channel.type}) — {channel.guild.name}")
            await self._check_antinuke_action(channel.guild, "channel_delete")

        @self.client.event
        async def on_guild_role_delete(role: discord.Role):
            if not role.guild:
                return
            ch = self.log_channels.get(role.guild.id)
            if ch:
                await self._send_log(role.guild.id, f"❌ **حذف رول** @{role.name} — {role.guild.name}")
            await self._check_antinuke_action(role.guild, "role_delete")

        @self.client.event
        async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
            if payload.member and payload.member.bot:
                return
            await self._handle_reaction_roles_add(payload)
            await self._handle_suggestion_reaction(payload)

        @self.client.event
        async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
            await self._handle_reaction_roles_remove(payload)

        try:
            await self.client.login(token)
            asyncio.create_task(self.client.connect(reconnect=True))
            await asyncio.wait_for(ready_future, timeout=40)
            asyncio.create_task(self._reminder_worker())
            asyncio.create_task(self._scheduled_worker())
            asyncio.create_task(self._scheduled_worker_cron())
            asyncio.create_task(self._auto_unban_worker())
            asyncio.create_task(self._giveaway_worker())
            asyncio.create_task(self._birthday_worker())
            return True, f"متصل: {self.user} | {len(self.guilds)} سيرفر"
        except discord.LoginFailure:
            await self._disconnect_async()
            return False, (
                "فشل تسجيل الدخول — التوكن غير صالح أو منتهي.\n"
                "اذهب إلى Developer Portal → Bot → Reset Token وأنشئ توكن جديد"
            )
        except asyncio.TimeoutError:
            await self._disconnect_async()
            return False, "انتهت مهلة الاتصال — تحقق من الإنترنت أو أعد المحاولة"
        except Exception as e:
            await self._disconnect_async()
            return False, f"خطأ في الاتصال: {e}"

    async def _disconnect_async(self):
        if self.client:
            try:
                await self.client.close()
            except Exception:
                pass
        self.client = None
        self.ready = False
        self.user = None
        self.guilds = []

    async def disconnect(self):
        await self._disconnect_async()

    def disconnect_sync(self):
        try:
            self.run_coro(self._disconnect_async(), timeout=15)
        except Exception:
            pass

    def get_guild(self, guild_id: int) -> Optional[discord.Guild]:
        if not self.client:
            return None
        return self.client.get_guild(guild_id)

    async def send_message(self, channel_id: int, content: str) -> tuple[bool, str]:
        channel = self.client.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.client.fetch_channel(channel_id)
            except Exception as e:
                return False, f"قناة غير موجودة: {e}"
        try:
            msg = await channel.send(content)
            return True, f"تم الإرسال (ID: {msg.id})"
        except discord.Forbidden:
            return False, "لا توجد صلاحية للإرسال"
        except Exception as e:
            return False, str(e)

    async def bulk_send(self, channel_id: int, messages: list[str], delay: float = 1.0) -> tuple[bool, str]:
        channel = self.client.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.client.fetch_channel(channel_id)
            except Exception as e:
                return False, str(e)
        sent = 0
        for msg in messages:
            if not msg.strip():
                continue
            try:
                await channel.send(msg)
                sent += 1
                await asyncio.sleep(delay)
            except Exception:
                break
        return True, f"تم إرسال {sent} رسالة"

    async def delete_channel_messages(self, channel_id: int, limit: int = 100) -> tuple[bool, str]:
        channel = self.client.get_channel(channel_id)
        if not channel:
            return False, "قناة غير موجودة"
        try:
            deleted = await channel.purge(limit=limit)
            return True, f"تم حذف {len(deleted)} رسالة"
        except discord.Forbidden:
            return False, "لا توجد صلاحية"
        except Exception as e:
            return False, str(e)

    async def create_channel(
        self, guild_id: int, name: str, channel_type: str = "text", category_id: Optional[int] = None
    ) -> tuple[bool, str]:
        guild = self.get_guild(guild_id)
        if not guild:
            return False, "سيرفر غير موجود"
        category = guild.get_channel(category_id) if category_id else None
        try:
            if channel_type == "text":
                ch = await guild.create_text_channel(name, category=category)
            elif channel_type == "voice":
                ch = await guild.create_voice_channel(name, category=category)
            else:
                return False, "نوع غير معروف"
            return True, f"تم إنشاء {ch.name} (ID: {ch.id})"
        except discord.Forbidden:
            return False, "لا توجد صلاحية"
        except Exception as e:
            return False, str(e)

    async def delete_channel(self, channel_id: int) -> tuple[bool, str]:
        channel = self.client.get_channel(channel_id)
        if not channel:
            return False, "قناة غير موجودة"
        try:
            name = channel.name
            await channel.delete()
            return True, f"تم حذف {name}"
        except discord.Forbidden:
            return False, "لا توجد صلاحية"
        except Exception as e:
            return False, str(e)

    async def kick_member(self, guild_id: int, member_id: int, reason: str = "") -> tuple[bool, str]:
        guild = self.get_guild(guild_id)
        member = guild.get_member(member_id) if guild else None
        if not member:
            try:
                member = await self.client.fetch_user(member_id)
                if guild:
                    member = guild.get_member(member_id) or await guild.fetch_member(member_id)
            except Exception:
                return False, "عضو غير موجود"
        try:
            await member.kick(reason=reason)
            return True, f"تم طرد {member}"
        except discord.Forbidden:
            return False, "لا توجد صلاحية"
        except Exception as e:
            return False, str(e)

    async def ban_member(self, guild_id: int, member_id: int, reason: str = "") -> tuple[bool, str]:
        guild = self.get_guild(guild_id)
        if not guild:
            return False, "سيرفر غير موجود"
        try:
            user = await self.client.fetch_user(member_id)
            await guild.ban(user, reason=reason)
            return True, f"تم حظر {user}"
        except discord.Forbidden:
            return False, "لا توجد صلاحية"
        except Exception as e:
            return False, str(e)

    async def timeout_member(
        self, guild_id: int, member_id: int, minutes: int, reason: str = ""
    ) -> tuple[bool, str]:
        guild = self.get_guild(guild_id)
        if not guild:
            return False, "سيرفر غير موجود"
        try:
            member = await guild.fetch_member(member_id)
            until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
            await member.timeout(until, reason=reason)
            return True, f"تايم أوت {minutes} دقيقة لـ {member}"
        except discord.Forbidden:
            return False, "لا توجد صلاحية"
        except Exception as e:
            return False, str(e)

    async def export_server_structure(self, guild_id: int) -> tuple[bool, str | dict]:
        guild = self.get_guild(guild_id)
        if not guild:
            return False, "سيرفر غير موجود"

        data = {
            "name": guild.name,
            "description": guild.description or "",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "categories": [],
            "channels": [],
            "roles": [],
        }

        for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
            if role.is_default():
                continue
            data["roles"].append({
                "name": role.name,
                "color": role.color.value,
                "permissions": role.permissions.value,
                "hoist": role.hoist,
                "mentionable": role.mentionable,
            })

        for cat in guild.categories:
            data["categories"].append({"name": cat.name, "id": cat.id, "position": cat.position})

        for ch in guild.channels:
            if isinstance(ch, discord.CategoryChannel):
                continue
            entry: dict[str, Any] = {
                "name": ch.name,
                "id": ch.id,
                "type": str(ch.type),
                "position": ch.position,
                "category": ch.category.name if ch.category else None,
            }
            if isinstance(ch, discord.TextChannel):
                entry["topic"] = ch.topic or ""
                entry["slowmode"] = ch.slowmode_delay
            data["channels"].append(entry)

        return True, data

    async def clone_structure_to_guild(
        self, source_guild_id: int, target_guild_id: int, include_roles: bool = True
    ) -> tuple[bool, str]:
        ok, data = await self.export_server_structure(source_guild_id)
        if not ok:
            return False, data

        target = self.get_guild(target_guild_id)
        if not target:
            return False, "السيرفر المستهدف غير موجود"

        created_cats: dict[str, discord.CategoryChannel] = {}
        created = {"categories": 0, "channels": 0, "roles": 0}

        try:
            if include_roles:
                for role_data in data["roles"]:
                    try:
                        await target.create_role(
                            name=role_data["name"],
                            color=discord.Color(role_data["color"]),
                            permissions=discord.Permissions(role_data["permissions"]),
                            hoist=role_data["hoist"],
                            mentionable=role_data["mentionable"],
                        )
                        created["roles"] += 1
                    except Exception:
                        pass

            for cat_data in data["categories"]:
                try:
                    cat = await target.create_category(cat_data["name"])
                    created_cats[cat_data["name"]] = cat
                    created["categories"] += 1
                except Exception:
                    pass

            for ch_data in data["channels"]:
                cat = created_cats.get(ch_data["category"]) if ch_data["category"] else None
                try:
                    if ch_data["type"] == "text":
                        await target.create_text_channel(ch_data["name"], category=cat)
                    elif ch_data["type"] == "voice":
                        await target.create_voice_channel(ch_data["name"], category=cat)
                    created["channels"] += 1
                except Exception:
                    pass

            return True, f"تم: {created['categories']} فئة، {created['channels']} قناة، {created['roles']} رول"
        except discord.Forbidden:
            return False, "لا توجد صلاحيات كافية في السيرفر المستهدف"
        except Exception as e:
            return False, str(e)

    async def get_guild_stats(self, guild_id: int) -> tuple[bool, dict | str]:
        guild = self.get_guild(guild_id)
        if not guild:
            return False, "سيرفر غير موجود"
        stats = {
            "name": guild.name,
            "id": guild.id,
            "members": guild.member_count,
            "channels": len(guild.channels),
            "text_channels": len(guild.text_channels),
            "voice_channels": len(guild.voice_channels),
            "roles": len(guild.roles),
            "emojis": len(guild.emojis),
            "owner": str(guild.owner),
            "created": guild.created_at.strftime("%Y-%m-%d"),
            "boost_level": guild.premium_tier,
            "boosts": guild.premium_subscription_count or 0,
        }
        return True, stats

    async def fetch_by_id(self, entity_id: int) -> tuple[bool, str]:
        """جلب معلومات أي كيان عبر ID."""
        try:
            guild = self.client.get_guild(entity_id)
            if guild:
                return True, f"سيرفر: {guild.name} | {guild.member_count} عضو | ID: {guild.id}"

            channel = self.client.get_channel(entity_id)
            if channel:
                return True, f"قناة: {channel.name} | نوع: {channel.type} | سيرفر: {getattr(channel.guild, 'name', '?')}"

            user = self.client.get_user(entity_id)
            if user:
                return True, f"مستخدم: {user} | ID: {user.id}"

            try:
                user = await self.client.fetch_user(entity_id)
                return True, f"مستخدم: {user} | ID: {user.id}"
            except Exception:
                pass

            try:
                ch = await self.client.fetch_channel(entity_id)
                return True, f"قناة: {ch.name} | نوع: {ch.type}"
            except Exception:
                pass

            return False, "لم يتم العثور على كيان بهذا ID"
        except Exception as e:
            return False, str(e)

    def list_guild_channels(self, guild_id: int) -> list[tuple[int, str, str]]:
        guild = self.get_guild(guild_id)
        if not guild:
            return []
        result = []
        for ch in sorted(guild.channels, key=lambda c: c.position):
            prefix = "📁" if isinstance(ch, discord.CategoryChannel) else (
                "💬" if isinstance(ch, discord.TextChannel) else "🔊"
            )
            result.append((ch.id, f"{prefix} {ch.name}", str(ch.type)))
        return result

    def list_guild_members(self, guild_id: int, limit: int = 50) -> list[tuple[int, str]]:
        guild = self.get_guild(guild_id)
        if not guild:
            return []
        members = sorted(guild.members, key=lambda m: m.joined_at or datetime.min.replace(tzinfo=timezone.utc))
        return [(m.id, str(m)) for m in members[:limit]]

    def get_welcome_config(self, guild_id: int) -> dict:
        cfg = self.welcome_config.get(str(guild_id), {})
        return {
            "enabled": cfg.get("enabled", False),
            "channel_id": cfg.get("channel_id", 0),
            "title": cfg.get("title", "Welcome to {server}!"),
            "subtitle": cfg.get("subtitle", "Enjoy your stay, {user}!"),
            "bg_color": cfg.get("bg_color", "#1a1a2e"),
            "text_color": cfg.get("text_color", "#00ff88"),
            "accent_color": cfg.get("accent_color", "#5865F2"),
            "show_avatar": cfg.get("show_avatar", True),
            "show_member_count": cfg.get("show_member_count", True),
            "border_style": cfg.get("border_style", "neon"),
            "custom_image": cfg.get("custom_image", ""),
            "dm_enabled": cfg.get("dm_enabled", False),
            "dm_message": cfg.get("dm_message", "Welcome to {server}! We're glad to have you here, {user}!"),
        }

    def set_welcome_config(self, guild_id: int, **kwargs) -> tuple[bool, str]:
        gid = str(guild_id)
        if gid not in self.welcome_config:
            self.welcome_config[gid] = {}
        for key, value in kwargs.items():
            self.welcome_config[gid][key] = value
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        config["welcome_config"] = self.welcome_config
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        enabled = self.welcome_config[gid].get("enabled", False)
        status = "مفعّل" if enabled else "معطّل"
        return True, f"تم حفظ إعدادات بطاقة الترحيب ({status})"

    def _format_welcome_message(self, member: discord.Member, template: str) -> str:
        return (
            template.replace("{user}", member.mention)
            .replace("{username}", member.display_name)
            .replace("{name}", member.name)
            .replace("{server}", member.guild.name)
            .replace("{count}", str(member.guild.member_count))
        )

    async def _handle_member_join(self, member: discord.Member):
        cfg = self.get_welcome_config(member.guild.id)
        if not cfg["enabled"]:
            return
        try:
            await self._send_welcome_card(member)
        except Exception as e:
            if self._welcome_log_callback:
                self._welcome_log_callback(f"فشل الترحيب: {e}")
        if cfg.get("dm_enabled"):
            try:
                dm_msg = self._format_welcome_message(member, cfg.get("dm_message", "Welcome to {server}!"))
                await member.send(dm_msg)
                self._log_activity(f"📩 DM ترحيب أُرسل لـ {member.display_name}")
            except discord.Forbidden:
                pass
            except Exception:
                pass

    # ── FFmpeg Diagnostic ────────────────────────────────────

    @staticmethod
    def _ffmpeg_bin_path() -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", "ffmpeg.exe")

    def _ffmpeg_exe(self) -> "str | None":
        import shutil
        env = shutil.which("ffmpeg")
        if env:
            return env
        bundled = self._ffmpeg_bin_path()
        if os.path.exists(bundled):
            return bundled
        return None

    @staticmethod
    def check_ffmpeg() -> tuple[bool, str]:
        import shutil
        path = shutil.which("ffmpeg")
        if path:
            return True, f"✅ FFmpeg موجود: {path}"
        alt = BotManager._ffmpeg_bin_path()
        if os.path.exists(alt):
            return True, f"✅ FFmpeg موجود في bin/ffmpeg.exe"
        local = r"ffmpeg.exe"
        if os.path.exists(local):
            return True, f"✅ FFmpeg موجود في المجلد الحالي"
        return False, (
            "❌ FFmpeg غير مثبت!\n\n"
            "لحل مشكلة الموسيقى:\n"
            "1. شغّل من مجلد البوت: python get_ffmpeg.py\n"
            "   (يحمل ffmpeg تلقائياً إلى bin/ffmpeg.exe)\n"
            "2. أو ثبّته يدوياً: winget install ffmpeg\n"
            "   وأضف المسار إلى PATH"
        )

    # ── Anti-Raid / Anti-Spam ─────────────────────────────────

    def get_automod_config(self, guild_id: int) -> dict:
        cfg = self.automod_config.get(str(guild_id), {})
        return {
            "enabled": cfg.get("enabled", False),
            "block_everyone": cfg.get("block_everyone", True),
            "block_caps": cfg.get("block_caps", False),
            "caps_threshold": cfg.get("caps_threshold", 70),
            "anti_raid": cfg.get("anti_raid", False),
            "raid_threshold": cfg.get("raid_threshold", 8),
            "raid_window": cfg.get("raid_window", 30),
            "anti_spam": cfg.get("anti_spam", False),
            "spam_threshold": cfg.get("spam_threshold", 5),
            "spam_window": cfg.get("spam_window", 5),
        }

    def set_automod_config(self, guild_id: int, enabled: bool, block_everyone: bool,
                           block_caps: bool, caps_threshold: int,
                           anti_raid: bool = False, raid_threshold: int = 8,
                           raid_window: int = 30,
                           anti_spam: bool = False, spam_threshold: int = 5,
                           spam_window: int = 5) -> tuple[bool, str]:
        self.automod_config[str(guild_id)] = {
            "enabled": enabled,
            "block_everyone": block_everyone,
            "block_caps": block_caps,
            "caps_threshold": caps_threshold,
            "anti_raid": anti_raid,
            "raid_threshold": raid_threshold,
            "raid_window": raid_window,
            "anti_spam": anti_spam,
            "spam_threshold": spam_threshold,
            "spam_window": spam_window,
        }
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        config["automod"] = self.automod_config
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        status = "مفعّل" if enabled else "معطّل"
        return True, f"تم حفظ الإشراف التلقائي ({status})"

    async def _handle_raid(self, member: discord.Member):
        gid = member.guild.id
        now = datetime.now(timezone.utc).timestamp()
        if gid not in self._join_log:
            self._join_log[gid] = []
        self._join_log[gid].append(now)
        cutoff = now - 60
        self._join_log[gid] = [t for t in self._join_log[gid] if t > cutoff]
        cfg = self.get_automod_config(gid)
        if not cfg.get("anti_raid"):
            return
        threshold = cfg.get("raid_threshold", 8)
        window = cfg.get("raid_window", 30)
        recent = [t for t in self._join_log[gid] if t > now - window]
        if len(recent) >= threshold:
            try:
                for ch in member.guild.text_channels:
                    if ch.permissions_for(member.guild.me).send_messages:
                        await ch.send(
                            f"🚨 **تنبيه RAID!** {len(recent)} عضو انضموا في {window} ثانية!\n"
                            f"تم تفعيل الحماية — يرجى مراجعة الإعدادات"
                        )
                        break
                self._log_activity(f"🚨 RAID detected in {member.guild.name} — {len(recent)} joins in {window}s")
            except Exception:
                pass
            self._join_log[gid] = []

    async def _handle_automod(self, message: discord.Message):
        cfg = self.get_automod_config(message.guild.id)
        if not cfg["enabled"]:
            return

        delete = False
        reason = ""

        if cfg["block_everyone"] and ("@everyone" in message.content or "@here" in message.content):
            perms = message.author.guild_permissions
            if not perms.administrator and not perms.manage_guild:
                delete = True
                reason = "منشن everyone/here"

        if cfg["block_caps"] and len(message.content) > 10:
            letters = [c for c in message.content if c.isalpha()]
            if letters:
                caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters) * 100
                if caps_ratio >= cfg["caps_threshold"]:
                    delete = True
                    reason = "أحرف كبيرة مفرطة"

        if cfg.get("anti_spam") and not delete:
            gid = message.guild.id
            uid = message.author.id
            now = datetime.now(timezone.utc).timestamp()
            if gid not in self._spam_log:
                self._spam_log[gid] = {}
            if uid not in self._spam_log[gid]:
                self._spam_log[gid][uid] = []
            self._spam_log[gid][uid].append(now)
            window = cfg.get("spam_window", 5)
            cutoff = now - window
            self._spam_log[gid][uid] = [t for t in self._spam_log[gid][uid] if t > cutoff]
            threshold = cfg.get("spam_threshold", 5)
            if len(self._spam_log[gid][uid]) >= threshold:
                delete = True
                reason = f"سبام ({len(self._spam_log[gid][uid])} رسائل في {window}ث)"

        if delete:
            try:
                await message.delete()
                self._log_activity(
                    f"🛡️ حذف رسالة {message.author.display_name} في #{message.channel.name}: {reason}"
                )
                await self._send_log(
                    message.guild.id,
                    f"🛡️ **إشراف تلقائي** — تم حذف رسالة من {message.author.display_name} في #{message.channel.name}\n> السبب: {reason}"
                )
            except discord.Forbidden:
                pass
            except Exception:
                pass

    # ── Server Protection System ──────────────────────────────

    def get_protection_config(self, guild_id: int) -> dict:
        cfg = self.protection_config.get(str(guild_id), {})
        return {
            "bot_insult_kick": cfg.get("bot_insult_kick", False),
            "bot_insult_warns_before_kick": cfg.get("bot_insult_warns_before_kick", 2),
            "max_warnings_before_ban": cfg.get("max_warnings_before_ban", 5),
            "anti_mass_mention": cfg.get("anti_mass_mention", False),
            "mass_mention_threshold": cfg.get("mass_mention_threshold", 5),
            "link_block_enabled": cfg.get("link_block_enabled", False),
            "link_block_channels": cfg.get("link_block_channels", []),
            "link_block_whitelist": cfg.get("link_block_whitelist", []),
            "auto_unban_enabled": cfg.get("auto_unban_enabled", False),
            "auto_unban_hours": cfg.get("auto_unban_hours", 24),
            "auto_role_enabled": cfg.get("auto_role_enabled", False),
            "auto_role_id": cfg.get("auto_role_id", 0),
            "spam_protection": cfg.get("spam_protection", False),
            "spam_threshold": cfg.get("spam_threshold", 5),
            "spam_window": cfg.get("spam_window", 3),
            "raid_protection": cfg.get("raid_protection", False),
            "raid_threshold": cfg.get("raid_threshold", 10),
            "raid_window": cfg.get("raid_window", 60),
            "greeting_protection": cfg.get("greeting_protection", False),
            "anti_hoist_enabled": cfg.get("anti_hoist_enabled", False),
            "anti_hoist_action": cfg.get("anti_hoist_action", "rename"),
        }

    def set_protection_config(self, guild_id: int, **kwargs) -> tuple[bool, str]:
        gid = str(guild_id)
        if gid not in self.protection_config:
            self.protection_config[gid] = {}
        for key, value in kwargs.items():
            self.protection_config[gid][key] = value
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        config["protection"] = self.protection_config
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True, "تم حفظ إعدادات الحماية"

    async def _handle_bot_insult(self, message: discord.Message):
        cfg = self.get_protection_config(message.guild.id)
        if not cfg.get("bot_insult_kick"):
            return
        if not self.client.user:
            return
        if message.author.id == self.client.user.id:
            return
        content = message.content.lower()
        bot_mentioned = self.client.user in message.mentions
        insult_patterns = [
            r'\bbot\b', r'\bبوت\b', r'\bحقير\b', r'\bسخيف\b', r'\bقذر\b', r'\btافه\b',
            r'\bزبالة\b', r'\bغبي\b', r'\bakil\b', r'\bstupid\b', r'\bidiot\b', r'\bgarbage\b',
            r'\btrash\b', r'\buseless\b', r'\bعميل\b', r'\bmisht\b', r'\bkharban\b',
            r'\bمنحرف\b', r'\bخسيس\b', r'\bwasekh\b', r'\bhaywan\b', r'\bحيوان\b',
            r'\bكسول\b', r'\blazy\b', r'\bحمار\b', r'\bdonkey\b', r'\bكلب\b', r'\bdog\b',
        ]
        is_insult = False
        if bot_mentioned:
            for pat in insult_patterns:
                if re.search(pat, content):
                    is_insult = True
                    break
        if not is_insult:
            return
        gid = message.guild.id
        uid = message.author.id
        if gid not in self._bot_insult_warns:
            self._bot_insult_warns[gid] = {}
        if uid not in self._bot_insult_warns[gid]:
            self._bot_insult_warns[gid][uid] = 0
        self._bot_insult_warns[gid][uid] += 1
        warn_count = self._bot_insult_warns[gid][uid]
        kick_threshold = cfg.get("bot_insult_warns_before_kick", 2)
        ban_threshold = cfg.get("max_warnings_before_ban", 5)
        try:
            await message.delete()
        except Exception:
            pass
        try:
            member = message.guild.get_member(uid)
            if not member:
                return
            if warn_count >= ban_threshold:
                await message.guild.ban(member, reason=f"إهانة البوت {warn_count} مرات — حظر تلقائي")
                self._log_activity(f"🔨 حظر {member.display_name} — إهانة البوت ({warn_count} مرات)")
                await self._send_log(gid, f"🔨 **حظر تلقائي** — {member.mention} أهان البوت {warn_count} مرات")
                self._bot_insult_warns[gid].pop(uid, None)
            elif warn_count >= kick_threshold:
                await member.kick(reason=f"إهانة البوت {warn_count} مرات — طرد تلقائي")
                self._log_activity(f"👢 طرد {member.display_name} — إهانة البوت ({warn_count} مرات)")
                await self._send_log(gid, f"👢 **طرد تلقائي** — {member.mention} أهان البوت {warn_count} مرات")
                self._bot_insult_warns[gid].pop(uid, None)
            else:
                await message.channel.send(
                    f"⚠️ {member.mention} تحذير {warn_count}/{kick_threshold} — لا تهين البوت!",
                    delete_after=5
                )
                self._log_activity(f"⚠️ تحذير {member.display_name} — إهانة البوت ({warn_count}/{kick_threshold})")
        except discord.Forbidden:
            pass
        except Exception:
            pass

    async def _handle_link_block(self, message: discord.Message):
        cfg = self.get_protection_config(message.guild.id)
        if not cfg.get("link_block_enabled"):
            return
        link_pattern = r'https?://[^\s]+|www\.[^\s]+|discord\.gg/[^\s]+|discord\.com/invite/[^\s]+'
        if not re.search(link_pattern, message.content):
            return
        channel_id = message.channel.id
        block_channels = cfg.get("link_block_channels", [])
        if block_channels and channel_id not in block_channels:
            return
        whitelist = cfg.get("link_block_whitelist", [])
        content_lower = message.content.lower()
        for url in whitelist:
            if url.lower() in content_lower:
                return
        perms = message.author.guild_permissions
        if perms.administrator or perms.manage_guild:
            return
        try:
            await message.delete()
            self._log_activity(f"🔗 حذف رسالة برابط من {message.author.display_name} في #{message.channel.name}")
            await self._send_log(
                message.guild.id,
                f"🔗 **حجب رابط** — تم حذف رسالة من {message.author.display_name} في #{message.channel.name}\n> الرابط محجوب في هذه القناة"
            )
        except discord.Forbidden:
            pass
        except Exception:
            pass

    async def _handle_spam_protection(self, message: discord.Message):
        cfg = self.get_protection_config(message.guild.id)
        if not cfg.get("spam_protection"):
            return
        gid = message.guild.id
        uid = message.author.id
        now = datetime.now(timezone.utc).timestamp()
        if gid not in self._protection_spam_log:
            self._protection_spam_log[gid] = {}
        if uid not in self._protection_spam_log[gid]:
            self._protection_spam_log[gid][uid] = []
        self._protection_spam_log[gid][uid].append(now)
        window = cfg.get("spam_window", 3)
        cutoff = now - window
        self._protection_spam_log[gid][uid] = [t for t in self._protection_spam_log[gid][uid] if t > cutoff]
        threshold = cfg.get("spam_threshold", 5)
        if len(self._protection_spam_log[gid][uid]) >= threshold:
            try:
                await message.delete()
            except Exception:
                pass
            try:
                member = message.guild.get_member(uid)
                if member:
                    until = datetime.now(timezone.utc) + timedelta(minutes=5)
                    await member.timeout(until, reason=f"سبام حماية — {len(self._protection_spam_log[gid][uid])} رسائل في {window}ث")
                    self._log_activity(f"🚫 تايم أوت {member.display_name} — سبام حماية ({len(self._protection_spam_log[gid][uid])} رسائل في {window}ث)")
                    await self._send_log(
                        gid,
                        f"🚫 **حماية السبام** — تايم أوت {member.mention} لمدة 5 دقائق\n> السبب: {len(self._protection_spam_log[gid][uid])} رسائل في {window} ثانية"
                    )
            except discord.Forbidden:
                pass
            except Exception:
                pass
            self._protection_spam_log[gid][uid] = []

    async def _handle_auto_role(self, member: discord.Member):
        cfg = self.get_protection_config(member.guild.id)
        if not cfg.get("auto_role_enabled"):
            return
        role_id = cfg.get("auto_role_id", 0)
        if not role_id:
            return
        role = member.guild.get_role(role_id)
        if not role:
            return
        try:
            await member.add_roles(role, reason="Auto role on join")
            self._log_activity(f"🎖️ تم إعطاء رول تلقائي {role.name} لـ {member.display_name} في {member.guild.name}")
        except discord.Forbidden:
            pass
        except Exception:
            pass

    async def _handle_auto_unban(self, guild: discord.Guild):
        cfg = self.get_protection_config(guild.id)
        if not cfg.get("auto_unban_enabled"):
            return
        hours = cfg.get("auto_unban_hours", 24)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        try:
            async for ban_entry in guild.bans(limit=100):
                if ban_entry.user.id == self.client.user.id:
                    continue
                if ban_entry.user.bot:
                    continue
                if ban_entry.reason and "حماية" in ban_entry.reason:
                    continue
                try:
                    await guild.unban(ban_entry.user, reason="إلغاء حظر تلقائي — انتهت المدة")
                    self._log_activity(f"✅ فك حظر تلقائي {ban_entry.user} من {guild.name} (بعد {hours} ساعة)")
                    await self._send_log(guild.id, f"✅ **فك حظر تلقائي** — {ban_entry.user} بعد {hours} ساعة")
                except Exception:
                    pass
        except discord.Forbidden:
            pass
        except Exception:
            pass

    async def _handle_mass_mention(self, message: discord.Message):
        cfg = self.get_protection_config(message.guild.id)
        if not cfg.get("anti_mass_mention"):
            return
        mention_count = len(message.mentions) + message.content.count("@everyone") + message.content.count("@here")
        threshold = cfg.get("mass_mention_threshold", 5)
        if mention_count < threshold:
            return
        perms = message.author.guild_permissions
        if perms.administrator or perms.manage_guild:
            return
        try:
            await message.delete()
            self._log_activity(f"📢 حذف رسالة منشن جماعي من {message.author.display_name} ({mention_count} منشن)")
            await self._send_log(
                message.guild.id,
                f"📢 **منشن جماعي** — تم حذف رسالة من {message.author.display_name} في #{message.channel.name}\n> عدد المنشن: {mention_count}"
            )
        except discord.Forbidden:
            pass
        except Exception:
            pass

    async def _auto_unban_worker(self):
        await asyncio.sleep(30)
        while True:
            try:
                if self.client and self.guilds:
                    for guild in self.guilds:
                        try:
                            await self._handle_auto_unban(guild)
                        except Exception:
                            pass
            except Exception:
                pass
            await asyncio.sleep(300)

    # ── Admin Login System ──────────────────────────────────

    @staticmethod
    def hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def _ensure_default_admin(self):
        if not self.admin_users:
            self.create_admin("admin", "admin123", ["all"])

    def create_admin(self, username: str, password: str, permissions: list[str] = None) -> tuple[bool, str]:
        username = username.strip().lower()
        if not username or not password:
            return False, "اسم المستخدم وكلمة المرور مطلوبان"
        if username in self.admin_users:
            return False, f"المستخدم {username} موجود بالفعل"
        self.admin_users[username] = {
            "password_hash": self.hash_password(password),
            "permissions": permissions or ["all"],
        }
        self._save_admins()
        return True, f"تم إنشاء المسؤول {username}"

    def delete_admin(self, username: str) -> tuple[bool, str]:
        username = username.strip().lower()
        if username not in self.admin_users:
            return False, f"المستخدم {username} غير موجود"
        del self.admin_users[username]
        self._save_admins()
        return True, f"تم حذف المسؤول {username}"

    def verify_admin(self, username: str, password: str) -> bool:
        username = username.strip().lower()
        admin = self.admin_users.get(username)
        if not admin:
            return False
        return admin.get("password_hash") == self.hash_password(password)

    def list_admins(self) -> list[dict]:
        result = []
        for username, data in self.admin_users.items():
            result.append({
                "username": username,
                "permissions": data.get("permissions", []),
            })
        return result

    def _save_admins(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        config["admin_users"] = self.admin_users
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    # ── Anti-Nuke System ─────────────────────────────────────

    def get_antinuke_config(self, guild_id: int) -> dict:
        cfg = self.antinuke_config.get(str(guild_id), {})
        return {
            "enabled": cfg.get("enabled", False),
            "max_channel_delete": cfg.get("max_channel_delete", 3),
            "channel_delete_window": cfg.get("channel_delete_window", 30),
            "max_role_delete": cfg.get("max_role_delete", 3),
            "role_delete_window": cfg.get("role_delete_window", 30),
            "max_channel_create": cfg.get("max_channel_create", 5),
            "channel_create_window": cfg.get("channel_create_window", 30),
            "max_kick": cfg.get("max_kick", 3),
            "kick_window": cfg.get("kick_window", 60),
            "max_ban": cfg.get("max_ban", 3),
            "ban_window": cfg.get("ban_window", 60),
            "action": cfg.get("action", "kick"),
            "log_channel_id": cfg.get("log_channel_id", 0),
        }

    def set_antinuke_config(self, guild_id: int, **kwargs) -> tuple[bool, str]:
        gid = str(guild_id)
        if gid not in self.antinuke_config:
            self.antinuke_config[gid] = {}
        for key, value in kwargs.items():
            self.antinuke_config[gid][key] = value
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        config["antinuke_config"] = self.antinuke_config
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True, "تم حفظ إعدادات Anti-Nuke"

    async def _find_audit_perpetrator(self, guild: discord.Guild, action_type: str) -> Optional[discord.Member]:
        audit_action_map = {
            "channel_delete": discord.AuditLogAction.channel_delete,
            "role_delete": discord.AuditLogAction.role_delete,
            "channel_create": discord.AuditLogAction.channel_create,
            "kick": discord.AuditLogAction.kick,
            "ban": discord.AuditLogAction.ban,
        }
        action = audit_action_map.get(action_type)
        if not action:
            return None
        try:
            async for entry in guild.audit_logs(limit=10, action=action):
                if entry.user and entry.user.id != self.client.user.id:
                    member = guild.get_member(entry.user.id)
                    return member or entry.user
        except discord.Forbidden:
            pass
        except Exception:
            pass
        return None

    async def _check_antinuke_action(self, guild: discord.Guild, action_type: str):
        cfg = self.get_antinuke_config(guild.id)
        if not cfg.get("enabled"):
            return

        perpetrator = await self._find_audit_perpetrator(guild, action_type)
        if not perpetrator or perpetrator.bot or perpetrator.id == self.client.user.id:
            return

        now = datetime.now(timezone.utc).timestamp()
        gid = guild.id

        if gid not in self._nuke_tracker:
            self._nuke_tracker[gid] = {}
        if action_type not in self._nuke_tracker[gid]:
            self._nuke_tracker[gid][action_type] = []

        self._nuke_tracker[gid][action_type].append(now)

        threshold_map = {
            "channel_delete": (cfg.get("max_channel_delete", 3), cfg.get("channel_delete_window", 30)),
            "role_delete": (cfg.get("max_role_delete", 3), cfg.get("role_delete_window", 30)),
            "channel_create": (cfg.get("max_channel_create", 5), cfg.get("channel_create_window", 30)),
            "kick": (cfg.get("max_kick", 3), cfg.get("kick_window", 60)),
            "ban": (cfg.get("max_ban", 3), cfg.get("ban_window", 60)),
        }

        threshold, window = threshold_map.get(action_type, (3, 30))
        cutoff = now - window
        self._nuke_tracker[gid][action_type] = [
            t for t in self._nuke_tracker[gid][action_type] if t > cutoff
        ]

        if len(self._nuke_tracker[gid][action_type]) >= threshold:
            punish_action = cfg.get("action", "kick")
            log_ch = cfg.get("log_channel_id", 0)

            try:
                if punish_action == "ban":
                    await guild.ban(perpetrator, reason=f"Anti-Nuke: {action_type} threshold exceeded ({len(self._nuke_tracker[gid][action_type])} times)")
                else:
                    await perpetrator.kick(reason=f"Anti-Nuke: {action_type} threshold exceeded ({len(self._nuke_tracker[gid][action_type])} times)")

                action_label = "حظر" if punish_action == "ban" else "طرد"
                msg = f"🚨 **Anti-Nuke** — {action_label} {perpetrator.mention} — {action_type} ({len(self._nuke_tracker[gid][action_type])} مرات في {window}ث)"
                self._log_activity(msg)
                if log_ch:
                    ch = self.client.get_channel(log_ch)
                    if ch:
                        await ch.send(msg)
            except discord.Forbidden:
                self._log_activity(f"⚠️ Anti-Nuke: فشل {punish_action} {perpetrator} — لا توجد صلاحية")
            except Exception:
                pass

            self._nuke_tracker[gid][action_type] = []


# ═══════════════════════════════════════════════════════════
# NEW FEATURES: Welcome Image, Reminder, Music, DM All, Warns
# ═══════════════════════════════════════════════════════════

    # ── Welcome Image Generator ──────────────────────────────

    @staticmethod
    def _find_font(preferred_size=42, small_size=18):
        paths = [
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "segoeuib.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf",
        ]
        for p in paths:
            try:
                return ImageFont.truetype(p, preferred_size), ImageFont.truetype(p.replace("segoeuib","segoeui").replace("arialbd","arial") if "bd" in p or "b" in p else p.replace("arial","arialbd").replace("segoeui","segoeuib"), small_size)
            except:
                continue
        return ImageFont.load_default(), ImageFont.load_default()

    @staticmethod
    def _render_welcome_image(member_name: str, server_name: str, member_count: int, avatar_data: bytes) -> io.BytesIO:
        W, H = 800, 300
        img = Image.new("RGB", (W, H), (13, 14, 18))
        draw = ImageDraw.Draw(img)

        for y in range(H):
            ratio = y / H
            r = int(13 + (88 - 13) * ratio * 0.25)
            g = int(14 + (101 - 14) * ratio * 0.25)
            b = int(18 + (242 - 18) * ratio * 0.25)
            draw.line([(0, y), (W, y)], fill=(r, g, b))

        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse([200, 30, 600, 270], fill=(88, 101, 242, 45))
        glow = glow.filter(ImageFilter.GaussianBlur(45))
        img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
        draw = ImageDraw.Draw(img)

        font_big, font_sm = BotManager._find_font(44, 18)

        try:
            av = Image.open(io.BytesIO(avatar_data)).convert("RGBA")
            av = av.resize((120, 120), Image.LANCZOS)
            mask = Image.new("L", (120, 120), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, 120, 120], fill=255)
            circ = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
            circ.paste(av, (0, 0), mask)
            border = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
            ImageDraw.Draw(border).ellipse([0, 0, 128, 128], fill=(88, 101, 242))
            img.paste(border, (50, H // 2 - 64), border)
            img.paste(circ, (54, H // 2 - 60), circ)
        except Exception:
            pass

        tx = 210
        draw.text((tx, 65), "WELCOME", fill=(88, 101, 242), font=font_big)
        draw.text((tx, 125), f"@{member_name}", fill="white", font=font_big)
        draw.text((tx, 175), f"Member #{member_count}  ·  {server_name}", fill=(148, 155, 164), font=font_sm)
        draw.line([(tx, 220), (tx + 250, 220)], fill=(88, 101, 242, 120), width=2)

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return buf

    async def generate_welcome_image(self, member: discord.Member) -> Optional[io.BytesIO]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(str(member.display_avatar.url)) as resp:
                    avatar_data = await resp.read()
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._render_welcome_image,
                member.display_name, member.guild.name, member.guild.member_count, avatar_data,
            )
        except Exception:
            return None

    # ── Welcome Card Designer ────────────────────────────────

    def _generate_welcome_card(self, member_name: str, server_name: str, member_count: int,
                                avatar_data: bytes, config: dict) -> io.BytesIO:
        W, H = 900, 300

        def hex_to_rgb(hex_color: str) -> tuple:
            hex_color = hex_color.lstrip("#")
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

        bg_color = hex_to_rgb(config.get("bg_color", "#1a1a2e"))
        text_color = hex_to_rgb(config.get("text_color", "#00ff88"))
        accent_color = hex_to_rgb(config.get("accent_color", "#5865F2"))

        img = Image.new("RGB", (W, H), bg_color)
        draw = ImageDraw.Draw(img)

        border_style = config.get("border_style", "neon")

        if border_style == "gradient":
            for y in range(H):
                ratio = y / H
                r = int(bg_color[0] + (accent_color[0] - bg_color[0]) * ratio * 0.3)
                g = int(bg_color[1] + (accent_color[1] - bg_color[1]) * ratio * 0.3)
                b = int(bg_color[2] + (accent_color[2] - bg_color[2]) * ratio * 0.3)
                draw.line([(0, y), (W, y)], fill=(r, g, b))
        else:
            for y in range(H):
                ratio = y / H
                factor = 0.15 * ratio
                r = int(bg_color[0] + (255 - bg_color[0]) * factor)
                g = int(bg_color[1] + (255 - bg_color[1]) * factor)
                b = int(bg_color[2] + (255 - bg_color[2]) * factor)
                draw.line([(0, y), (W, y)], fill=(r, g, b))

        if border_style == "neon":
            glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow)
            gd.ellipse([280, 15, 620, 285], fill=(*accent_color, 45))
            glow = glow.filter(ImageFilter.GaussianBlur(45))
            img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
            draw = ImageDraw.Draw(img)

        font_big, font_sm = BotManager._find_font(44, 18)

        if config.get("show_avatar", True) and avatar_data:
            try:
                av = Image.open(io.BytesIO(avatar_data)).convert("RGBA")
                av = av.resize((140, 140), Image.LANCZOS)
                mask = Image.new("L", (140, 140), 0)
                ImageDraw.Draw(mask).ellipse([0, 0, 140, 140], fill=255)
                circ = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
                circ.paste(av, (0, 0), mask)
                border = Image.new("RGBA", (148, 148), (0, 0, 0, 0))
                ImageDraw.Draw(border).ellipse([0, 0, 148, 148], fill=(*accent_color, 255))
                img.paste(border, (40, H // 2 - 74), border)
                img.paste(circ, (44, H // 2 - 70), circ)
            except Exception:
                pass

        title = config.get("title", "Welcome to {server}!").replace("{server}", server_name)
        tx = 210
        draw.text((tx, 55), title, fill=text_color, font=font_big)

        subtitle = config.get("subtitle", "Enjoy your stay, {user}!").replace("{user}", f"@{member_name}")
        draw.text((tx, 115), subtitle, fill=(200, 200, 200), font=font_sm)

        if config.get("show_member_count", True):
            count_text = f"Member #{member_count}  ·  {server_name}"
            draw.text((tx, 160), count_text, fill=(148, 155, 164), font=font_sm)

        draw.line([(tx, 210), (tx + 250, 210)], fill=accent_color, width=2)

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return buf

    async def _send_welcome_card(self, member: discord.Member):
        config = self.get_welcome_config(member.guild.id)
        if not config.get("enabled"):
            return

        channel_id = config.get("channel_id")
        if not channel_id:
            return

        channel = self.client.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.client.fetch_channel(channel_id)
            except Exception:
                return

        avatar_data = b""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(str(member.display_avatar.url)) as resp:
                    avatar_data = await resp.read()
        except Exception:
            pass

        loop = asyncio.get_event_loop()
        buf = await loop.run_in_executor(
            None, self._generate_welcome_card,
            member.display_name, member.guild.name, member.guild.member_count,
            avatar_data, config,
        )

        title = config.get("title", "Welcome to {server}!").replace("{server}", member.guild.name)
        subtitle = config.get("subtitle", "Enjoy your stay, {user}!").replace("{user}", member.mention)
        text = f"{title}\n{subtitle}"

        try:
            await channel.send(content=text, file=discord.File(buf, "welcome_card.png"))
            log_msg = f"👋 بطاقة ترحيب: {member.display_name} في {member.guild.name}"
            if self._welcome_log_callback:
                self._welcome_log_callback(log_msg)
        except discord.Forbidden:
            if self._welcome_log_callback:
                self._welcome_log_callback(f"لا توجد صلاحية للترحيب في {member.guild.name}")
        except Exception as e:
            if self._welcome_log_callback:
                self._welcome_log_callback(f"فشل إرسال بطاقة الترحيب: {e}")

    # ── Reminder System ──────────────────────────────────────

    def set_reminder(self, channel_id: int, message: str, timestamp_str: str) -> tuple[bool, str]:
        reminders = self._load_reminders()
        reminders.append({"channel_id": channel_id, "message": message, "timestamp": timestamp_str})
        self._save_reminders(reminders)
        return True, f"تم ضبط التذكير لـ {timestamp_str}"

    def get_reminders(self) -> list:
        return self._load_reminders()

    def remove_reminder(self, index: int) -> tuple[bool, str]:
        reminders = self._load_reminders()
        if 0 <= index < len(reminders):
            r = reminders.pop(index)
            self._save_reminders(reminders)
            return True, f"تم حذف التذكير: {r['message'][:30]}..."
        return False, "التذكير غير موجود"

    def _load_reminders(self) -> list:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f).get("reminders", [])
        except Exception:
            return []

    def _save_reminders(self, reminders: list):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["reminders"] = reminders
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    async def _reminder_worker(self):
        await asyncio.sleep(10)
        while True:
            try:
                reminders = self._load_reminders()
                now = datetime.now().isoformat()
                pending = []
                for r in reminders:
                    if r["timestamp"] <= now:
                        ch = self.client.get_channel(r["channel_id"])
                        if ch:
                            try:
                                await ch.send(f"⏰ **تذكير:** {r['message']}")
                                self._log_activity(f"⏰ تم إرسال التذكير: {r['message'][:40]}")
                            except Exception:
                                pass
                    else:
                        pending.append(r)
                self._save_reminders(pending)
            except Exception:
                pass
            await asyncio.sleep(30)

    # ── Server Logs ───────────────────────────────────────────

    async def _send_log(self, guild_id: int, text: str):
        ch_id = self.log_channels.get(guild_id)
        if not ch_id:
            return
        ch = self.client.get_channel(ch_id)
        if not ch:
            return
        try:
            await ch.send(f"📋 {text}")
        except Exception:
            pass

    def set_log_channel(self, guild_id: int, channel_id: int):
        self.log_channels[guild_id] = channel_id
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "log_channels" not in data:
                data["log_channels"] = {}
            data["log_channels"][str(guild_id)] = channel_id
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get_log_channel(self, guild_id: int) -> int:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("log_channels", {}).get(str(guild_id), 0)
        except Exception:
            return 0

    # ── Scheduled Messages ────────────────────────────────────

    def _load_scheduled(self) -> list:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f).get("scheduled", [])
        except Exception:
            return []

    def _save_scheduled(self, data: list):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg["scheduled"] = data
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def add_scheduled(self, channel_id: int, message: str, time_str: str, repeat: str) -> tuple[bool, str]:
        items = self._load_scheduled()
        items.append({
            "channel_id": channel_id,
            "message": message,
            "time": time_str,
            "repeat": repeat,
            "last_sent": "",
        })
        self._save_scheduled(items)
        return True, f"تمت إضافة الرسالة المجدولة ({repeat})"

    def get_scheduled(self) -> list:
        return self._load_scheduled()

    def remove_scheduled(self, index: int) -> tuple[bool, str]:
        items = self._load_scheduled()
        if 0 <= index < len(items):
            items.pop(index)
            self._save_scheduled(items)
            return True, "تم الحذف"
        return False, "غير موجود"

    async def _scheduled_worker(self):
        await asyncio.sleep(15)
        while True:
            try:
                items = self._load_scheduled()
                now = datetime.now()
                today = now.strftime("%Y-%m-%d")
                time_hm = now.strftime("%H:%M")
                updated = []
                for item in items:
                    send = False
                    if item["repeat"] == "daily" and item["time"] == time_hm and item.get("last_sent", "") != today:
                        send = True
                        item["last_sent"] = today
                    elif item["repeat"] == "weekly" and item["time"] == time_hm:
                        wday = str(now.weekday())
                        if item.get("last_sent") != f"{today}_{wday}":
                            send = True
                            item["last_sent"] = f"{today}_{wday}"
                    elif item["repeat"] == "once" and item.get("last_sent") == "":
                        if item["time"] == time_hm:
                            send = True
                            item["last_sent"] = today
                    if send:
                        ch = self.client.get_channel(item["channel_id"])
                        if ch:
                            try:
                                await ch.send(f"📅 **رسالة مجدولة:**\n{item['message']}")
                                self._log_activity(f"📅 تم إرسال المجدول: {item['message'][:40]}")
                            except Exception:
                                pass
                    updated.append(item)
                self._save_scheduled([i for i in updated if i["repeat"] != "once" or i.get("last_sent", "") == "" or i["time"] != time_hm])
            except Exception:
                pass
            await asyncio.sleep(40)

    # ── Embed Builder Helper ──────────────────────────────────

    async def send_embed(self, channel_id: int, title: str = "", description: str = "",
                         color: str = "#5865F2", author: str = "", author_icon: str = "",
                         footer: str = "", footer_icon: str = "",
                         thumbnail: str = "", image: str = "",
                         timestamp: bool = False, fields: list = None,
                         buttons: list = None) -> tuple[bool, str]:
        ch = self.client.get_channel(channel_id)
        if not ch:
            return False, "قناة غير موجودة"
        try:
            color_int = int(color.lstrip("#"), 16) if color else 0x5865F2
            embed = discord.Embed(title=title or None, description=description or None, color=color_int)
            if author:
                embed.set_author(name=author, icon_url=author_icon or None)
            if footer:
                embed.set_footer(text=footer, icon_url=footer_icon or None)
            if thumbnail:
                embed.set_thumbnail(url=thumbnail)
            if image:
                embed.set_image(url=image)
            if timestamp:
                embed.timestamp = datetime.now(timezone.utc)
            if fields:
                for f in fields:
                    embed.add_field(name=f.get("name", ""), value=f.get("value", ""), inline=f.get("inline", False))
            view = None
            if buttons:
                view = discord.ui.View()
                for b in buttons[:3]:
                    label = b.get("label", "").strip()
                    url = b.get("url", "").strip()
                    if url:
                        view.add_item(discord.ui.Button(label=label or "رابط", url=url))
            await ch.send(embed=embed, view=view)
            return True, f"تم إرسال الـ Embed"
        except discord.Forbidden:
            return False, "لا توجد صلاحية"
        except Exception as e:
            return False, str(e)

    # ── Ticket System ──────────────────────────────────────

    def configure_tickets(self, guild_id: int, category_id: int, staff_role_id: int,
                          welcome_msg: str = "", panel_title: str = "",
                          panel_desc: str = "", color: str = "#5865F2"):
        cfg = {
            "category_id": category_id,
            "staff_role_id": staff_role_id,
            "welcome_msg": welcome_msg or "مرحباً! سيتم الرد عليك قريباً من قبل فريق الدعم.",
            "panel_title": panel_title or "🎫 نظام التذاكر",
            "panel_desc": panel_desc or "اضغط على الزر أدناه لفتح تذكرة دعم فني.",
            "color": color,
            "counter": self.ticket_config.get(guild_id, {}).get("counter", 0),
        }
        self.ticket_config[guild_id] = cfg
        self._save_ticket_config(guild_id)

    def get_ticket_config(self, guild_id: int) -> dict:
        return self.ticket_config.get(guild_id, {})

    def _save_ticket_config(self, guild_id: int):
        cfg = self.ticket_config.get(guild_id)
        if not cfg:
            return
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "ticket_config" not in data:
                data["ticket_config"] = {}
            data["ticket_config"][str(guild_id)] = {
                "category_id": cfg["category_id"],
                "staff_role_id": cfg["staff_role_id"],
                "welcome_msg": cfg["welcome_msg"],
                "panel_title": cfg["panel_title"],
                "panel_desc": cfg["panel_desc"],
                "color": cfg["color"],
                "counter": cfg["counter"],
            }
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _load_ticket_config(self, guild_id: int) -> dict:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("ticket_config", {}).get(str(guild_id), {})
        except Exception:
            return {}

    async def send_ticket_panel(self, channel_id: int, guild_id: int) -> tuple[bool, str]:
        cfg = self.ticket_config.get(guild_id) or self._load_ticket_config(guild_id)
        if not cfg:
            return False, "لم يتم ضبط إعدادات التذاكر بعد"
        ch = self.client.get_channel(channel_id)
        if not ch:
            return False, "القناة غير موجودة"
        try:
            color_int = int(cfg.get("color", "#5865F2").lstrip("#"), 16)
            embed = discord.Embed(
                title=cfg.get("panel_title", "🎫 نظام التذاكر"),
                description=cfg.get("panel_desc", "اضغط على الزر أدناه لفتح تذكرة."),
                color=color_int,
            )
            embed.set_footer(text="TicketKing Style • رد آمن وسريع")
            view = TicketView(self, guild_id)
            msg = await ch.send(embed=embed, view=view)
            self._log_activity(f"🎫 تم إرسال لوحة التذاكر في #{ch.name}")
            return True, f"تم إرسال اللوحة (Message ID: {msg.id})"
        except discord.Forbidden:
            return False, "لا توجد صلاحية"
        except Exception as e:
            return False, str(e)

    async def _handle_ticket_create(self, interaction: discord.Interaction, guild_id: int):
        cfg = self.ticket_config.get(guild_id) or self._load_ticket_config(guild_id)
        if not cfg:
            await interaction.response.send_message("❌ لم يتم ضبط التذاكر!", ephemeral=True)
            return
        guild = interaction.guild
        if not guild:
            return
        category = guild.get_channel(cfg["category_id"])
        if not category:
            await interaction.response.send_message("❌ تصنيف التذاكر غير موجود!", ephemeral=True)
            return
        staff_role = guild.get_role(cfg["staff_role_id"])
        user = interaction.user
        cfg["counter"] += 1
        self._save_ticket_config(guild_id)

        ticket_name = f"ticket-{user.display_name[:10]}-{cfg['counter']}".lower()
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True)

        try:
            ticket_ch = await guild.create_text_channel(ticket_name, category=category, overwrites=overwrites)
        except discord.Forbidden:
            await interaction.response.send_message("❌ لا توجد صلاحية لإنشاء القناة!", ephemeral=True)
            return

        welcome = cfg.get("welcome_msg", "مرحباً! فريق الدعم سيصل قريباً.")
        staff_mention = staff_role.mention if staff_role else "فريق الدعم"
        embed = discord.Embed(
            title="🎫 تذكرتك الجديدة",
            description=f"{user.mention}\n\n{welcome}\n\n{staff_mention} سيتم الرد عليك قريباً.",
            color=0x2ECC71
        )
        embed.set_footer(text=f"تذكرة #{cfg['counter']}")
        close_view = TicketCloseView(self)
        await ticket_ch.send(content=staff_mention if staff_role else None, embed=embed, view=close_view)
        await interaction.response.send_message(f"✅ تم إنشاء تذكرتك → {ticket_ch.mention}", ephemeral=True)
        self._log_activity(f"🎫 تذكرة جديدة من {user.display_name} — #{ticket_ch.name} ({guild.name})")

    async def _handle_ticket_close(self, interaction: discord.Interaction):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return
        embed = discord.Embed(
            title="🔒 إغلاق التذكرة",
            description="سيتم حذف القناة بعد 5 ثوانٍ...",
            color=0xE74C3C
        )
        await interaction.response.send_message(embed=embed)
        await asyncio.sleep(5)
        try:
            await channel.delete()
        except Exception:
            pass



    # ── Voice / YouTube Music (Enhanced) ─────────────────────

    async def join_voice(self, guild_id: int, channel_id: int) -> tuple[bool, str]:
        guild = self.get_guild(guild_id)
        if not guild:
            return False, "سيرفر غير موجود"
        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            return False, "قناة صوتية غير موجودة"
        try:
            vc = await channel.connect()
            self.voice_clients[guild_id] = vc
            try:
                await self.send_or_update_panel(guild_id)
            except Exception:
                pass
            return True, f"✅ متصل بـ {channel.name}"
        except Exception as e:
            return False, f"فشل الاتصال: {e}"

    async def leave_voice(self, guild_id: int) -> tuple[bool, str]:
        vc = self.voice_clients.pop(guild_id, None)
        if vc:
            try:
                await vc.disconnect()
            except Exception:
                pass
            self.now_playing.pop(guild_id, None)
            self.music_queues.pop(guild_id, None)
            return True, "تم قطع الاتصال الصوتي"
        return False, "البوت ليس في قناة صوتية"

    def set_panel_channel(self, guild_id: int, channel_id: int):
        self.panel_channels[guild_id] = channel_id

    def get_panel_channel(self, guild_id: int) -> int:
        return self.panel_channels.get(guild_id, 0)

    async def send_or_update_panel(self, guild_id: int):
        channel = None
        ch_id = self.panel_channels.get(guild_id)
        if ch_id:
            channel = self.client.get_channel(ch_id)
        if not channel:
            vc = self.voice_clients.get(guild_id)
            if vc and vc.channel:
                channel = vc.channel
        if not channel:
            return
        view = MusicPanelView(self)
        embed = view.build(guild_id)
        old_msg = self.panel_messages.get(guild_id)
        if old_msg:
            try:
                await old_msg.edit(embed=embed, view=view)
                return
            except Exception:
                self.panel_messages.pop(guild_id, None)
        try:
            msg = await channel.send(embed=embed, view=view)
            self.panel_messages[guild_id] = msg
        except discord.HTTPException as e:
            if "404" in str(e) or "Not Found" in str(e):
                self.panel_channels.pop(guild_id, None)
            try:
                msg = await channel.send(embed=embed)
                self.panel_messages[guild_id] = msg
            except Exception:
                pass
        except Exception:
            pass

    def set_stay_in_vc(self, guild_id: int, stay: bool):
        self.stay_in_vc[guild_id] = stay

    def get_stay_in_vc(self, guild_id: int) -> bool:
        return self.stay_in_vc.get(guild_id, False)

    def set_volume(self, guild_id: int, volume_pct: int):
        self.music_volumes[guild_id] = max(0.05, min(2.0, volume_pct / 100.0))

    def get_volume(self, guild_id: int) -> int:
        return int(self.music_volumes.get(guild_id, 1.0) * 100)

    def _play_next(self, guild_id: int, error=None):
        queue = self.music_queues.get(guild_id, [])
        vc = self.voice_clients.get(guild_id)

        # If loop single track is on, replay current
        if self.loop_mode.get(guild_id) and self.np_info.get(guild_id):
            np = self.np_info[guild_id]
            url = np.get("url", "")
            if url and vc:
                try:
                    info = _ytdlp_extract_info(url)
                    audio_url = info["url"]
                except Exception:
                    import re as _re
                    vid_match = _re.search(r"v=([a-zA-Z0-9_-]+)", url)
                    if vid_match:
                        try:
                            loop = asyncio.new_event_loop()
                            info = loop.run_until_complete(_invidious_extract(vid_match.group(1)))
                            audio_url = info["url"]
                        except Exception:
                            pass
                    else:
                        audio_url = None
                if audio_url:
                    try:
                        ffopts = {"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", "options": "-vn"}
                        ffmpeg_exe = self._ffmpeg_exe()
                        if ffmpeg_exe:
                            ffopts["executable"] = ffmpeg_exe
                        source = discord.FFmpegPCMAudio(audio_url, **ffopts)
                        vol = self.music_volumes.get(guild_id, 1.0)
                        source = discord.PCMVolumeTransformer(source, volume=vol)
                        vc.play(source, after=lambda e: self._play_next(guild_id, e))
                    except Exception:
                        pass
            return

        if not queue:
            self.now_playing.pop(guild_id, None)
            self.np_info.pop(guild_id, None)
            self.paused.pop(guild_id, None)
            try:
                asyncio.run_coroutine_threadsafe(self.send_or_update_panel(guild_id), self.loop)
            except Exception:
                pass
            if not self.stay_in_vc.get(guild_id):
                if vc and not vc.is_playing():
                    try:
                        import asyncio
                        asyncio.run_coroutine_threadsafe(self.leave_voice(guild_id), self.loop)
                    except Exception:
                        pass
            return

        if not vc:
            return

        next_item = queue.pop(0)
        url = next_item["url"]
        title = next_item.get("title", "Unknown")
        thumbnail = next_item.get("thumbnail", "")
        duration = next_item.get("duration", 0)
        requester = next_item.get("requester", "")
        channel = next_item.get("channel", "")

        audio_url = None
        try:
            info = _ytdlp_extract_info(url)
            audio_url = info["url"]
            title = info.get("title", title)
            if not thumbnail:
                thumbnail = info.get("thumbnail", "")
            if not duration:
                duration = int(info.get("duration") or 0)
        except Exception:
            import re as _re
            vid_match = _re.search(r"v=([a-zA-Z0-9_-]+)", url)
            if vid_match:
                try:
                    loop = asyncio.new_event_loop()
                    info = loop.run_until_complete(_invidious_extract(vid_match.group(1)))
                    audio_url = info["url"]
                    title = info.get("title", title)
                except Exception:
                    pass

            ffopts = {"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", "options": "-vn"}
            ffmpeg_exe = self._ffmpeg_exe()
            if ffmpeg_exe:
                ffopts["executable"] = ffmpeg_exe
            source = discord.FFmpegPCMAudio(audio_url, **ffopts)
            vol = self.music_volumes.get(guild_id, 1.0)
            source = discord.PCMVolumeTransformer(source, volume=vol)
            vc.play(source, after=lambda e: self._play_next(guild_id, e))
            self.now_playing[guild_id] = title
            self.np_info[guild_id] = {
                "title": title, "url": url, "thumbnail": thumbnail,
                "duration": duration, "requester": requester, "channel": channel,
                "start_time": __import__("time").time(),
            }
            self.paused[guild_id] = False
            self._track_music_play(guild_id, title, requester, duration)
            try:
                asyncio.run_coroutine_threadsafe(self.send_or_update_panel(guild_id), self.loop)
            except Exception:
                pass
        except Exception:
            self._play_next(guild_id)

    async def play_youtube(self, guild_id: int, url: str, requester: str = "", channel_name: str = "") -> tuple[bool, str]:
        vc = self.voice_clients.get(guild_id)
        if not vc:
            return False, "البوت ليس في قناة صوتية"
        try:
            source_url = url

            # Handle Spotify URLs
            if _is_spotify_url(url):
                query, thumb = await _resolve_spotify_url(url)
                source_url = f"ytsearch1:{query}"

            # Handle plain text search
            if not source_url.startswith("http"):
                source_url = f"ytsearch1:{source_url}"

            loop = asyncio.get_event_loop()

            # Try yt-dlp first
            info = None
            try:
                info = await loop.run_in_executor(None, lambda: _ytdlp_extract_info(source_url))
            except Exception:
                pass

            # Fallback to Invidious
            if not info or not info.get("url"):
                import re as _re
                vid_match = _re.search(r"v=([a-zA-Z0-9_-]+)", source_url)
                if vid_match:
                    info = await _invidious_extract(vid_match.group(1))
                elif source_url.startswith("ytsearch1:"):
                    query = source_url.replace("ytsearch1:", "")
                    results = await _invidious_search(query, 1)
                    if results:
                        vid_match2 = _re.search(r"v=([a-zA-Z0-9_-]+)", results[0]["url"])
                        if vid_match2:
                            info = await _invidious_extract(vid_match2.group(1))

            if not info or not info.get("url"):
                return False, "فشل جلب الأغنية"
            if not url or not url.startswith("http"):
                info = info.get("entries", [info])[0] if info.get("entries") else info
            audio_url = info["url"]
            title = info.get("title", "Unknown")
            thumbnail = info.get("thumbnail", "")
            duration = int(info.get("duration") or 0)

            track = {"url": url, "title": title, "thumbnail": thumbnail, "duration": duration, "requester": requester, "channel": channel_name}

            if vc.is_playing():
                if guild_id not in self.music_queues:
                    self.music_queues[guild_id] = []
                self.music_queues[guild_id].append(track)
                qpos = len(self.music_queues[guild_id])
                return True, f"➕ **{title}** — أضيف للقائمة (رقم {qpos})"

            ffopts = {"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", "options": "-vn"}
            ffmpeg_exe = self._ffmpeg_exe()
            if ffmpeg_exe:
                ffopts["executable"] = ffmpeg_exe
            source = discord.FFmpegPCMAudio(audio_url, **ffopts)
            vol = self.music_volumes.get(guild_id, 1.0)
            source = discord.PCMVolumeTransformer(source, volume=vol)
            vc.play(source, after=lambda e: self._play_next(guild_id, e))
            self.now_playing[guild_id] = title
            self.np_info[guild_id] = {
                "title": title, "url": url, "thumbnail": thumbnail,
                "duration": duration, "requester": requester, "channel": channel_name,
                "start_time": __import__("time").time(),
            }
            self.paused[guild_id] = False
            self._track_music_play(guild_id, title, requester, duration)
            return True, f"🎵 جاري تشغيل: **{title}**"
        except ImportError:
            return False, "yt-dlp غير مثبت. شغّل: pip install yt-dlp"
        except Exception as e:
            return False, f"فشل التشغيل: {e}"

    async def skip_track(self, guild_id: int) -> tuple[bool, str]:
        vc = self.voice_clients.get(guild_id)
        if vc and vc.is_playing():
            vc.stop()
            return True, "⏭ تخطيت الأغنية"
        return False, "لا يوجد تشغيل"

    async def stop_playback(self, guild_id: int) -> tuple[bool, str]:
        vc = self.voice_clients.get(guild_id)
        if vc and vc.is_playing():
            vc.stop()
            self.now_playing.pop(guild_id, None)
            self.music_queues.pop(guild_id, None)
            return True, "⏹ تم إيقاف التشغيل ومسح القائمة"
        return False, "لا يوجد تشغيل"

    def get_now_playing(self, guild_id: int) -> str:
        return self.now_playing.get(guild_id, "")

    def get_queue(self, guild_id: int) -> list:
        return self.music_queues.get(guild_id, [])

    def search_youtube(self, query: str, limit: int = 10) -> tuple[bool, list]:
        try:
            results = _ytdlp_search(query, limit)
            return True, results
        except Exception:
            pass
        # Fallback: Invidious
        try:
            loop = asyncio.get_event_loop()
            results = loop.run_until_complete(_invidious_search(query, limit))
            if results:
                return True, results
        except Exception:
            pass
        return False, "فشل البحث"

    def clear_queue(self, guild_id: int):
        self.music_queues.pop(guild_id, None)

    # ── Enhanced Music Controls ──────────────────────────────

    async def pause_track(self, guild_id: int) -> tuple[bool, str]:
        vc = self.voice_clients.get(guild_id)
        if vc and vc.is_playing():
            np = self.np_info.get(guild_id, {})
            if np.get("start_time"):
                self._pause_elapsed[guild_id] = __import__("time").time() - np["start_time"]
            vc.pause()
            self.paused[guild_id] = True
            return True, "⏸ تم إيقاف التشغيل مؤقتاً"
        return False, "لا يوجد تشغيل"

    async def resume_track(self, guild_id: int) -> tuple[bool, str]:
        vc = self.voice_clients.get(guild_id)
        if vc and vc.is_paused():
            pause_dur = self._pause_elapsed.pop(guild_id, 0)
            np = self.np_info.get(guild_id, {})
            if np.get("start_time") and pause_dur:
                np["start_time"] = __import__("time").time() - pause_dur
            vc.resume()
            self.paused[guild_id] = False
            return True, "▶️ تم استئناف التشغيل"
        return False, "لا يوجد شيء متوقف"

    def toggle_loop(self, guild_id: int) -> bool:
        self.loop_mode[guild_id] = not self.loop_mode.get(guild_id, False)
        if self.loop_mode[guild_id]:
            self.queue_loop[guild_id] = False
        return self.loop_mode[guild_id]

    def toggle_queue_loop(self, guild_id: int) -> bool:
        self.queue_loop[guild_id] = not self.queue_loop.get(guild_id, False)
        if self.queue_loop[guild_id]:
            self.loop_mode[guild_id] = False
        return self.queue_loop[guild_id]

    def toggle_shuffle(self, guild_id: int) -> bool:
        import random
        self.shuffle_mode[guild_id] = not self.shuffle_mode.get(guild_id, False)
        if self.shuffle_mode[guild_id]:
            queue = self.music_queues.get(guild_id, [])
            if len(queue) > 1:
                random.shuffle(queue)
        return self.shuffle_mode[guild_id]

    def get_music_status(self, guild_id: int) -> dict:
        np = self.now_playing.get(guild_id, "")
        info = self.np_info.get(guild_id, {})
        queue = self.music_queues.get(guild_id, [])
        vol = self.get_volume(guild_id)
        vc = self.voice_clients.get(guild_id)

        elapsed = 0
        duration = info.get("duration", 0)
        if info.get("start_time") and not self.paused.get(guild_id):
            elapsed = int(__import__("time").time() - info["start_time"])

        return {
            "now_playing": np,
            "thumbnail": info.get("thumbnail", ""),
            "url": info.get("url", ""),
            "duration": duration,
            "elapsed": elapsed,
            "requester": info.get("requester", ""),
            "channel": info.get("channel", ""),
            "queue": [{"title": t.get("title", ""), "url": t.get("url", ""), "duration": t.get("duration", 0), "requester": t.get("requester", "")} for t in queue],
            "queue_count": len(queue),
            "volume": vol,
            "connected": vc is not None,
            "playing": vc.is_playing() if vc else False,
            "paused": self.paused.get(guild_id, False),
            "loop": self.loop_mode.get(guild_id, False),
            "queue_loop": self.queue_loop.get(guild_id, False),
            "shuffle": self.shuffle_mode.get(guild_id, False),
            "stay_in_vc": self.stay_in_vc.get(guild_id, False),
        }

    def _music_embed_dict(self, guild_id: int) -> dict:
        np = self.get_now_playing(guild_id)
        q = self.get_queue(guild_id)
        vol = self.get_volume(guild_id)
        fields = []
        if np:
            fields.append({"name": "🎶 يُعزف الآن", "value": np, "inline": False})
        else:
            fields.append({"name": "🎶 الحالة", "value": "لا يوجد تشغيل حالياً", "inline": False})
        if q:
            items = "\n".join(f"{i + 1}. {t.get('title', 'أغنية')}" for i, t in enumerate(q[:12]))
            if len(q) > 12:
                items += f"\n...و {len(q) - 12} أخرى"
            fields.append({"name": f"📃 قائمة التشغيل ({len(q)})", "value": items, "inline": False})
        fields.append({"name": "🔊 الصوت", "value": f"{vol}%", "inline": True})
        fields.append({"name": "🔌 متصل", "value": "نعم" if guild_id in self.voice_clients else "لا", "inline": True})
        return {"title": "🎵 مشغل الموسيقى", "color": 0x00e5ff, "fields": fields}

    def _music_embed(self, guild_id: int) -> "discord.Embed":
        return self._dict_to_embed(self._music_embed_dict(guild_id))

    def _dict_to_embed(self, d: dict) -> "discord.Embed":
        if not d:
            return None
        e = discord.Embed(
            title=d.get("title", ""),
            description=d.get("description", ""),
            color=d.get("color", 0x00e5ff),
        )
        for f in d.get("fields", []):
            e.add_field(name=f["name"], value=f["value"], inline=f.get("inline", False))
        if d.get("footer"):
            e.set_footer(text=d["footer"])
        return e

    async def _exec_music_command(self, guild_id: int, raw: str, voice_channel_id: int = None) -> dict:
        res = {"content": None, "embed": None}
        body = raw[len(MUSIC_PREFIX):].strip() if raw.startswith(MUSIC_PREFIX) else raw.strip()
        if not body:
            return res
        parts = body.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        async def ensure_voice():
            vc = self.voice_clients.get(guild_id)
            if vc:
                return True, None
            if voice_channel_id:
                ok, m = await self.join_voice(guild_id, voice_channel_id)
                return (True, None) if ok else (False, m)
            return False, "البوت ليس في قناة صوتية. ادخل قناة من قائمة الصوت ثم شغّل، أو اكتب `!join <ايدي القناة>`"

        if cmd in ("play", "p"):
            if not arg:
                res["content"] = "اكتب اسم الأغنية أو الرابط. مثال: `!play Imagine Dragons`"
                return res
            if arg.isdigit() and guild_id in self._last_search:
                idx = int(arg) - 1
                if 0 <= idx < len(self._last_search[guild_id]):
                    arg = self._last_search[guild_id][idx]
            ok, msg = await ensure_voice()
            if not ok:
                res["content"] = msg
                return res
            ok, msg = await self.play_youtube(guild_id, arg)
            if not ok:
                res["content"] = msg
                return res
            res["embed"] = self._music_embed_dict(guild_id)

        elif cmd in ("skip", "s", "next"):
            ok, msg = await self.skip_track(guild_id)
            if not ok:
                res["content"] = msg
                return res
            res["embed"] = self._music_embed_dict(guild_id)

        elif cmd in ("stop",):
            ok, msg = await self.stop_playback(guild_id)
            if not ok:
                res["content"] = msg
                return res
            res["embed"] = self._music_embed_dict(guild_id)

        elif cmd in ("np", "now", "current", "queue", "q"):
            q = self.get_queue(guild_id)
            if cmd in ("queue", "q") and not q:
                res["content"] = "📃 القائمة فارغة"
                return res
            res["embed"] = self._music_embed_dict(guild_id)

        elif cmd in ("search",):
            if not arg:
                res["content"] = "اكتب كلمة للبحث. مثال: `!search arabic remix`"
                return res
            ok, r = self.search_youtube(arg, 5)
            if not ok:
                res["content"] = r
                return res
            if not r:
                res["content"] = "🔍 لا توجد نتائج"
                return res
            lines = "\n".join(f"`!play {i + 1}` {t['title']}" for i, t in enumerate(r))
            res["embed"] = {"title": "🔎 نتائج البحث", "color": 0x00e5ff, "description": lines, "footer": "اكتب !play متبوعاً برقم النتيجة للتشغيل"}
            self._last_search[guild_id] = [t["url"] for t in r]

        elif cmd in ("vol", "volume"):
            if not arg.isdigit():
                res["content"] = "اكتب رقماً من 5 إلى 200. مثال: `!volume 80`"
                return res
            self.set_volume(guild_id, int(arg))
            res["embed"] = self._music_embed_dict(guild_id)

        elif cmd in ("join",):
            cid = voice_channel_id
            if arg and (arg.isdigit() or arg.startswith("<#")):
                cid = int(arg.strip("<#>"))
            if not cid:
                res["content"] = "حدد قناة صوتية: `!join <ايدي القناة>` أو اختر قناة من القائمة"
                return res
            ok, m = await self.join_voice(guild_id, cid)
            res["content"] = m

        elif cmd in ("leave", "dc"):
            ok, m = await self.leave_voice(guild_id)
            res["content"] = m

        elif cmd in ("panel", "pnl"):
            res["content"] = "__"
            res["panel"] = True

        elif cmd in ("musichelp", "mhelp", "اوامر"):
            res["embed"] = {
                "title": "🎶 أوامر الموسيقى",
                "color": 0x00e5ff,
                "description": (
                    "`!play <اسم أو رابط>` — تشغيل أو إضافة للقائمة\n"
                    "`!skip` — تبديل/تخطي الأغنية\n"
                    "`!stop` — إيقاف ومسح القائمة\n"
                    "`!panel` — إرسال Panel تفاعلي مع أزرار\n"
                    "`!np` — الأغنية الحالية\n"
                    "`!queue` — عرض القائمة\n"
                    "`!search <كلمة>` — بحث وعرض نتائج\n"
                    "`!volume <5-200>` — مستوى الصوت\n"
                    "`!join <ايدي القناة>` — دخول قناة صوتية\n"
                    "`!leave` — خروج من القناة"
                ),
            }

        else:
            res["content"] = "أمر غير معروف. اكتب `!musichelp` لعرض الأوامر"
        return res

    async def _handle_music_command(self, message: "discord.Message"):
        gid = message.guild.id
        res = await self._exec_music_command(gid, message.content)
        if res.get("panel"):
            view = MusicPanelView(self)
            await message.channel.send(
                embed=view.build(gid),
                view=view,
            )
            await message.delete()
            return
        if res.get("content") or res.get("embed"):
            await message.channel.send(
                content=res.get("content"),
                embed=self._dict_to_embed(res.get("embed")),
            )

    # ── Stickers & Emojis ─────────────────────────────────────

    async def fetch_sticker_packs(self) -> list:
        try:
            return await self.client.fetch_sticker_packs()
        except Exception:
            return []

    async def send_sticker(self, channel_id: int, sticker_id: int) -> tuple[bool, str]:
        channel = self.client.get_channel(channel_id)
        if not channel:
            return False, "قناة غير موجودة"
        try:
            sticker = await self.client.fetch_sticker(sticker_id)
            await channel.send(stickers=[sticker])
            return True, f"تم إرسال الملصق: {sticker.name}"
        except Exception as e:
            return False, str(e)

    def list_guild_emojis(self, guild_id: int) -> list:
        guild = self.get_guild(guild_id)
        if not guild:
            return []
        return [{"id": e.id, "name": e.name, "animated": e.animated, "url": str(e.url)} for e in guild.emojis]

    async def upload_emoji(self, guild_id: int, name: str, image_url: str) -> tuple[bool, str]:
        guild = self.get_guild(guild_id)
        if not guild:
            return False, "سيرفر غير موجود"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        return False, "فشل تحميل الصورة"
                    data = await resp.read()
            import base64
            emoji = await guild.create_custom_emoji(name=name, image=data)
            return True, f"تم إنشاء إيموجي: {emoji}"
        except discord.Forbidden:
            return False, "لا توجد صلاحية لإدارة الإيموجيات"
        except Exception as e:
            return False, str(e)

    # ── DM All Members ──────────────────────────────────────

    async def dm_all_members(self, guild_id: int, message: str, progress_callback=None) -> tuple[bool, str]:
        guild = self.get_guild(guild_id)
        if not guild:
            return False, "سيرفر غير موجود"
        sent = 0
        failed = 0
        total = sum(1 for m in guild.members if not m.bot)
        for i, member in enumerate(guild.members):
            if member.bot:
                continue
            try:
                await member.send(f"📨 **رسالة من السيرفر:**\n{message}")
                sent += 1
            except Exception:
                failed += 1
            if progress_callback and i % 5 == 0:
                progress_callback(sent + failed, total)
            await asyncio.sleep(0.3)
        return True, f"✅ تم الإرسال لـ {sent} عضو | ❌ فشل {failed} (من {total})"

    # ── Warn System ─────────────────────────────────────────

    def _load_warns(self) -> dict:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f).get("warns", {})
        except Exception:
            return {}

    def _save_warns(self, warns: dict):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["warns"] = warns
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get_warns(self, guild_id: int, member_id: int) -> list:
        warns = self._load_warns()
        return warns.get(str(guild_id), {}).get(str(member_id), [])

    def remove_warns(self, guild_id: int, member_id: int) -> tuple[bool, str]:
        warns = self._load_warns()
        gid, mid = str(guild_id), str(member_id)
        if gid in warns and mid in warns[gid]:
            member_name = warns[gid][mid][0].get("member_name", member_id) if warns[gid][mid] else member_id
            del warns[gid][mid]
            self._save_warns(warns)
            return True, f"تم مسح تحذيرات {member_name}"
        return False, "لا توجد تحذيرات لهذا العضو"

    async def warn_member(self, guild_id: int, member_id: int, reason: str, moderator: str) -> tuple[bool, str]:
        guild = self.get_guild(guild_id)
        member = guild.get_member(member_id) if guild else None
        if not member:
            try:
                member = await self.client.fetch_user(member_id)
            except Exception:
                return False, "عضو غير موجود"
        warns = self._load_warns()
        gid, mid = str(guild_id), str(member_id)
        if gid not in warns:
            warns[gid] = {}
        if mid not in warns[gid]:
            warns[gid][mid] = []
        warns[gid][mid].append({
            "reason": reason,
            "date": datetime.now().isoformat(),
            "moderator": moderator,
            "member_name": str(member),
        })
        self._save_warns(warns)
        count = len(warns[gid][mid])
        try:
            await member.send(f"⚠️ تم تحذيرك في {guild.name}\nالسبب: {reason}\nالتحذير: {count}/3")
        except Exception:
            pass
        if count >= 3:
            try:
                await guild.ban(member, reason=f"3 تحذيرات - {reason}")
                self._log_activity(f"🔨 حظر تلقائي {member} — 3 تحذيرات")
                return True, f"⚠️ تحذير {count}/3 — تم حظر {member} تلقائياً"
            except Exception:
                return True, f"⚠️ تحذير {count}/3 — فشل الحظر التلقائي (صلاحيات?)"
        return True, f"⚠️ تحذير {count}/3 لـ {member}"

    # ── Verification System ──────────────────────────────────

    def get_verification_config(self, guild_id: int) -> dict:
        cfg = self.verification_config.get(str(guild_id), {})
        return {
            "enabled": cfg.get("enabled", False),
            "channel_id": cfg.get("channel_id", 0),
            "role_id": cfg.get("role_id", 0),
            "type": cfg.get("type", "button"),
            "welcome_message": cfg.get("welcome_message", "Welcome! Please verify yourself."),
            "success_message": cfg.get("success_message", "You have been verified!"),
            "fail_message": cfg.get("fail_message", "Incorrect answer. Try again."),
        }

    def set_verification_config(self, guild_id: int, **kwargs) -> tuple[bool, str]:
        gid = str(guild_id)
        if gid not in self.verification_config:
            self.verification_config[gid] = {}
        for key, value in kwargs.items():
            self.verification_config[gid][key] = value
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        config["verification"] = self.verification_config
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True, "تم حفظ إعدادات التحقق"

    async def _handle_verification(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return
        cfg = self.get_verification_config(guild.id)
        if not cfg["enabled"]:
            await interaction.response.send_message("❌ التحقق غير مفعّل", ephemeral=True)
            return
        member = interaction.user
        role = guild.get_role(cfg["role_id"])
        if not role:
            await interaction.response.send_message("❌ رول التحقق غير موجود", ephemeral=True)
            return
        if role in member.roles:
            await interaction.response.send_message("✅ أنت موثّق بالفعل!", ephemeral=True)
            return
        try:
            await member.add_roles(role, reason="Verification")
            success_msg = cfg.get("success_message", "You have been verified!")
            await interaction.response.send_message(f"✅ {success_msg}", ephemeral=True)
            self._log_activity(f"✅ تم التحقق من {member.display_name} في {guild.name}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ لا توجد صلاحية لإعطاء الرول", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ خطأ: {e}", ephemeral=True)

    async def _handle_captcha_check(self, message: discord.Message) -> bool:
        gid = message.guild.id
        if gid not in self._captcha_pending:
            return False
        pending = self._captcha_pending[gid]
        if message.channel.id != pending.get("channel_id"):
            return False
        cfg = self.get_verification_config(gid)
        try:
            await message.delete()
        except Exception:
            pass
        if message.content.strip() == str(pending["answer"]):
            role = message.guild.get_role(cfg["role_id"])
            if role:
                try:
                    await message.author.add_roles(role, reason="Captcha verification")
                    success_msg = cfg.get("success_message", "You have been verified!")
                    await message.channel.send(f"✅ {success_msg}", delete_after=5)
                    self._log_activity(f"✅ تم التحقق (كابتشا) من {message.author.display_name} في {message.guild.name}")
                except Exception:
                    pass
            del self._captcha_pending[gid]
        else:
            fail_msg = cfg.get("fail_message", "Incorrect answer. Try again.")
            await message.channel.send(f"❌ {fail_msg}", delete_after=5)
        return True

    async def send_verification_panel(self, channel_id: int, guild_id: int) -> tuple[bool, str]:
        cfg = self.get_verification_config(guild_id)
        if not cfg["enabled"]:
            return False, "التحقق غير مفعّل"
        ch = self.client.get_channel(channel_id)
        if not ch:
            return False, "قناة غير موجودة"
        ver_type = cfg.get("type", "button")
        welcome_msg = cfg.get("welcome_message", "Welcome! Please verify yourself.")
        if ver_type == "button":
            embed = discord.Embed(title="🔐 Verification", description=welcome_msg, color=0x5865F2)
            view = VerificationView(self)
            try:
                await ch.send(embed=embed, view=view)
                return True, "تم إرسال لوحة التحقق"
            except Exception as e:
                return False, str(e)
        else:
            a = random.randint(1, 20)
            b = random.randint(1, 20)
            answer = a + b
            self._captcha_pending[guild_id] = {"answer": answer, "channel_id": channel_id}
            embed = discord.Embed(
                title="🔐 Verification",
                description=f"{welcome_msg}\n\n**ما هو ناتج {a} + {b}؟**\nاكتب الإجابة في الشات.",
                color=0x5865F2,
            )
            try:
                await ch.send(embed=embed)
                return True, "تم إرسال كابتشا التحقق"
            except Exception as e:
                return False, str(e)

    # ── Reaction Roles ──────────────────────────────────────

    def setup_reaction_roles(self, guild_id: int, channel_id: int, message_id: int, roles_config: list) -> tuple[bool, str]:
        gid = str(guild_id)
        if gid not in self.reaction_roles_config:
            self.reaction_roles_config[gid] = {}
        self.reaction_roles_config[gid] = {
            "enabled": True,
            "message_id": message_id,
            "channel_id": channel_id,
            "roles": roles_config,
        }
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        config["reaction_roles"] = self.reaction_roles_config
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True, "تم ضبط الرول بالتفاعل"

    def get_reaction_roles(self, guild_id: int) -> dict:
        return self.reaction_roles_config.get(str(guild_id), {})

    def remove_reaction_roles(self, guild_id: int) -> tuple[bool, str]:
        gid = str(guild_id)
        if gid in self.reaction_roles_config:
            del self.reaction_roles_config[gid]
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                config = {}
            config["reaction_roles"] = self.reaction_roles_config
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            return True, "تم حذف الرول بالتفاعل"
        return False, "لا توجد إعدادات رول بالتفاعل لهذا السيرفر"

    async def _handle_reaction_roles_add(self, payload: discord.RawReactionActionEvent):
        gid = str(payload.guild_id)
        rr = self.reaction_roles_config.get(gid, {})
        if not rr.get("enabled"):
            return
        if payload.message_id != rr.get("message_id"):
            return
        emoji = str(payload.emoji)
        for role_entry in rr.get("roles", []):
            if role_entry.get("emoji") == emoji:
                guild = self.client.get_guild(payload.guild_id)
                if not guild:
                    return
                member = guild.get_member(payload.user_id)
                if not member or member.bot:
                    return
                role = guild.get_role(role_entry.get("role_id", 0))
                if role:
                    try:
                        await member.add_roles(role, reason="Reaction role")
                        self._log_activity(f"🎖️ رول تفاعلي {role.name} لـ {member.display_name}")
                    except Exception:
                        pass
                break

    async def _handle_reaction_roles_remove(self, payload: discord.RawReactionActionEvent):
        gid = str(payload.guild_id)
        rr = self.reaction_roles_config.get(gid, {})
        if not rr.get("enabled"):
            return
        if payload.message_id != rr.get("message_id"):
            return
        emoji = str(payload.emoji)
        for role_entry in rr.get("roles", []):
            if role_entry.get("emoji") == emoji:
                guild = self.client.get_guild(payload.guild_id)
                if not guild:
                    return
                member = guild.get_member(payload.user_id)
                if not member or member.bot:
                    return
                role = guild.get_role(role_entry.get("role_id", 0))
                if role:
                    try:
                        await member.remove_roles(role, reason="Reaction role removed")
                        self._log_activity(f"🎖️ إزالة رول تفاعلي {role.name} من {member.display_name}")
                    except Exception:
                        pass
                break

    # ── Giveaway System ──────────────────────────────────────

    def _save_giveaways(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        config["giveaways"] = self.giveaways
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def create_giveaway(self, channel_id: int, prize: str, winners_count: int, duration_hours: float, host_id: int) -> tuple[bool, str]:
        giveaway_id = random.randint(100000, 999999)
        end_time = (datetime.now(timezone.utc) + timedelta(hours=duration_hours)).isoformat()
        giveaway = {
            "id": giveaway_id,
            "channel_id": channel_id,
            "prize": prize,
            "winners_count": winners_count,
            "end_time": end_time,
            "host_id": host_id,
            "ended": False,
            "winner_ids": [],
            "entries": [],
        }
        self.giveaways.append(giveaway)
        self._save_giveaways()
        return True, giveaway_id

    async def end_giveaway(self, giveaway_id: int) -> tuple[bool, str]:
        for gw in self.giveaways:
            if gw["id"] == giveaway_id and not gw.get("ended"):
                gw["ended"] = True
                entries = gw.get("entries", [])
                winners_count = min(gw["winners_count"], len(entries))
                if winners_count > 0:
                    winner_ids = random.sample(entries, winners_count)
                    gw["winner_ids"] = winner_ids
                else:
                    gw["winner_ids"] = []
                self._save_giveaways()
                ch = self.client.get_channel(gw["channel_id"]) if self.client else None
                if ch:
                    if gw["winner_ids"]:
                        mentions = " ".join(f"<@{wid}>" for wid in gw["winner_ids"])
                        embed = discord.Embed(
                            title="🎉 انتهى الإيفنت!",
                            description=f"**الجائزة:** {gw['prize']}\n\n**الفائزون:** {mentions}",
                            color=0xFFD700,
                        )
                    else:
                        embed = discord.Embed(
                            title="🎉 انتهى الإيفنت!",
                            description=f"**الجائزة:** {gw['prize']}\n\nلم يشارك أحد.",
                            color=0xFFD700,
                        )
                    try:
                        await ch.send(embed=embed)
                    except Exception:
                        pass
                self._log_activity(f"🎉 انتهى إيفنت: {gw['prize']}")
                return True, "تم إنهاء الإيفنت"
        return False, "الإيفنت غير موجود أو منتهي بالفعل"

    def get_active_giveaways(self, guild_id: int) -> list:
        result = []
        for gw in self.giveaways:
            if not gw.get("ended"):
                ch = self.client.get_channel(gw["channel_id"]) if self.client else None
                if ch and hasattr(ch, "guild") and ch.guild and ch.guild.id == guild_id:
                    result.append(gw)
        return result

    async def _giveaway_worker(self):
        await asyncio.sleep(30)
        while True:
            try:
                now = datetime.now(timezone.utc)
                for gw in list(self.giveaways):
                    if gw.get("ended"):
                        continue
                    end_time = datetime.fromisoformat(gw["end_time"])
                    if now >= end_time:
                        await self.end_giveaway(gw["id"])
            except Exception:
                pass
            await asyncio.sleep(30)

    async def send_giveaway_message(self, channel_id: int, giveaway: dict) -> tuple[bool, str]:
        ch = self.client.get_channel(channel_id)
        if not ch:
            return False, "قناة غير موجودة"
        try:
            end_dt = datetime.fromisoformat(giveaway["end_time"])
            remaining = end_dt - datetime.now(timezone.utc)
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            embed = discord.Embed(
                title="🎉 إيفنت!",
                description=(
                    f"**الجائزة:** {giveaway['prize']}\n"
                    f"**عدد الفائزين:** {giveaway['winners_count']}\n"
                    f"**المتبقي:** {time_str}\n"
                    f"**عدد المشاركين:** {len(giveaway.get('entries', []))}"
                ),
                color=0xFFD700,
            )
            embed.set_footer(text=f"ID: {giveaway['id']}")
            view = GiveawayView(self, giveaway["id"])
            await ch.send(embed=embed, view=view)
            return True, f"تم إرسال الإيفنت (ID: {giveaway['id']})"
        except Exception as e:
            return False, str(e)

    # ── Level System ─────────────────────────────────────────

    def get_level_config(self, guild_id: int) -> dict:
        cfg = self.level_config.get(str(guild_id), {})
        return {
            "enabled": cfg.get("enabled", False),
            "xp_per_message": cfg.get("xp_per_message", [15, 25]),
            "level_up_channel": cfg.get("level_up_channel", 0),
            "level_roles": cfg.get("level_roles", []),
        }

    def set_level_config(self, guild_id: int, **kwargs) -> tuple[bool, str]:
        gid = str(guild_id)
        if gid not in self.level_config:
            self.level_config[gid] = {}
        for key, value in kwargs.items():
            self.level_config[gid][key] = value
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        config["level_config"] = self.level_config
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True, "تم حفظ إعدادات المستويات"

    def _save_levels(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        config["levels"] = self.levels
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def get_user_level(self, guild_id: int, user_id: int) -> dict:
        gid = str(guild_id)
        uid = str(user_id)
        return self.levels.get(gid, {}).get(uid, {"xp": 0, "level": 0, "messages": 0})

    def get_level_leaderboard(self, guild_id: int, limit: int = 10) -> list:
        gid = str(guild_id)
        guild_levels = self.levels.get(gid, {})
        sorted_users = sorted(
            guild_levels.items(),
            key=lambda x: (x[1].get("level", 0), x[1].get("xp", 0)),
            reverse=True,
        )
        leaderboard = []
        for uid, data in sorted_users[:limit]:
            leaderboard.append({
                "user_id": int(uid),
                "level": data.get("level", 0),
                "xp": data.get("xp", 0),
                "messages": data.get("messages", 0),
            })
        return leaderboard

    def _get_xp_for_level(self, level: int) -> int:
        return 5 * (level ** 2) + 50 * level + 100

    async def _add_xp(self, guild_id: int, user_id: int):
        cfg = self.get_level_config(guild_id)
        if not cfg.get("enabled"):
            return
        gid = str(guild_id)
        uid = str(user_id)
        if gid not in self.levels:
            self.levels[gid] = {}
        if uid not in self.levels[gid]:
            self.levels[gid][uid] = {"xp": 0, "level": 0, "messages": 0}
        user_data = self.levels[gid][uid]
        xp_range = cfg.get("xp_per_message", [15, 25])
        if isinstance(xp_range, list) and len(xp_range) >= 2:
            xp_gain = random.randint(xp_range[0], xp_range[1])
        elif isinstance(xp_range, (int, float)):
            xp_gain = int(xp_range)
        else:
            xp_gain = random.randint(15, 25)
        user_data["xp"] = user_data.get("xp", 0) + xp_gain
        user_data["messages"] = user_data.get("messages", 0) + 1
        old_level = user_data.get("level", 0)
        xp_needed = self._get_xp_for_level(old_level)
        leveled_up = False
        while user_data["xp"] >= xp_needed:
            user_data["level"] = user_data.get("level", 0) + 1
            user_data["xp"] -= xp_needed
            leveled_up = True
            old_level = user_data["level"]
            xp_needed = self._get_xp_for_level(old_level)
        if leveled_up:
            self._save_levels()
            guild = self.client.get_guild(guild_id) if self.client else None
            if guild:
                member = guild.get_member(user_id)
                if member:
                    level_up_channel_id = cfg.get("level_up_channel", 0)
                    channel = self.client.get_channel(level_up_channel_id) if level_up_channel_id else None
                    if not channel:
                        channel = guild.system_channel
                    if channel:
                        try:
                            await channel.send(f"🎉 {member.mention} leveled up to **Level {user_data['level']}**!")
                        except Exception:
                            pass
                    level_roles = cfg.get("level_roles", [])
                    for lr in level_roles:
                        if lr.get("level") == user_data["level"]:
                            role = guild.get_role(lr.get("role_id", 0))
                            if role:
                                try:
                                    await member.add_roles(role, reason=f"Level {user_data['level']}")
                                except Exception:
                                    pass
        else:
            self._save_levels()

    # ── Custom Commands ──────────────────────────────────────

    def create_custom_command(self, guild_id: int, name: str, **kwargs) -> tuple[bool, str]:
        gid = str(guild_id)
        if gid not in self.custom_commands:
            self.custom_commands[gid] = {}
        cmd_data = {
            "response": kwargs.get("response", ""),
            "type": kwargs.get("type", "text"),
            "embed_data": kwargs.get("embed_data", {}),
            "cooldown": kwargs.get("cooldown", 0),
            "permissions": kwargs.get("permissions", []),
        }
        self.custom_commands[gid][name.lower()] = cmd_data
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        config["custom_commands"] = self.custom_commands
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True, f"تم إنشاء الأمر المخصص: {name}"

    def delete_custom_command(self, guild_id: int, name: str) -> tuple[bool, str]:
        gid = str(guild_id)
        cmds = self.custom_commands.get(gid, {})
        if name.lower() in cmds:
            del cmds[name.lower()]
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                config = {}
            config["custom_commands"] = self.custom_commands
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            return True, f"تم حذف الأمر: {name}"
        return False, "الأمر غير موجود"

    def get_custom_commands(self, guild_id: int) -> dict:
        return self.custom_commands.get(str(guild_id), {})

    async def _handle_custom_command(self, message: discord.Message):
        content = message.content
        if not content or len(content) < 2:
            return
        prefix = content[0]
        if prefix not in ("!", ".", "?", "#", "$"):
            return
        parts = content.split(None, 1)
        cmd_name = parts[0][1:].lower()
        if not cmd_name:
            return
        gid = str(message.guild.id)
        cmds = self.custom_commands.get(gid, {})
        if cmd_name not in cmds:
            return
        cmd = cmds[cmd_name]
        cmd_type = cmd.get("type", "text")
        response = cmd.get("response", "")
        if cmd_type == "embed":
            embed_data = cmd.get("embed_data", {})
            embed = discord.Embed(
                title=embed_data.get("title", ""),
                description=embed_data.get("description", response),
                color=int(embed_data.get("color", "#5865F2").lstrip("#"), 16) if embed_data.get("color") else 0x5865F2,
            )
            if embed_data.get("footer"):
                embed.set_footer(text=embed_data["footer"])
            if embed_data.get("image"):
                embed.set_image(url=embed_data["image"])
            if embed_data.get("thumbnail"):
                embed.set_thumbnail(url=embed_data["thumbnail"])
            for field in embed_data.get("fields", []):
                embed.add_field(name=field.get("name", ""), value=field.get("value", ""), inline=field.get("inline", False))
            try:
                await message.channel.send(embed=embed)
            except Exception:
                pass
        else:
            try:
                await message.channel.send(response)
            except Exception:
                pass

    # ── Birthday System ──────────────────────────────────────

    def get_birthday_config(self, guild_id: int) -> dict:
        cfg = self.birthday_config.get(str(guild_id), {})
        return {
            "birthday_enabled": cfg.get("birthday_enabled", False),
            "birthday_channel_id": cfg.get("birthday_channel_id", 0),
            "birthday_role_id": cfg.get("birthday_role_id", 0),
        }

    def set_birthday_config(self, guild_id: int, **kwargs) -> tuple[bool, str]:
        gid = str(guild_id)
        if gid not in self.birthday_config:
            self.birthday_config[gid] = {}
        for key, value in kwargs.items():
            self.birthday_config[gid][key] = value
        self._save_birthday_config()
        return True, "تم حفظ إعدادات أعياد الميلاد"

    def _save_birthday_config(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        config["birthday_config"] = self.birthday_config
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def set_birthday(self, guild_id: int, user_id: int, month: int, day: int, year: int = 0) -> tuple[bool, str]:
        gid = str(guild_id)
        uid = str(user_id)
        if gid not in self.birthday_config:
            self.birthday_config[gid] = {}
        if "birthdays" not in self.birthday_config[gid]:
            self.birthday_config[gid]["birthdays"] = {}
        self.birthday_config[gid]["birthdays"][uid] = {
            "month": month,
            "day": day,
            "year": year,
            "last_wished": 0,
        }
        self._save_birthday_config()
        return True, f"تم ضبط عيد الميلاد: {month}/{day}"

    def remove_birthday(self, guild_id: int, user_id: int) -> tuple[bool, str]:
        gid = str(guild_id)
        uid = str(user_id)
        birthdays = self.birthday_config.get(gid, {}).get("birthdays", {})
        if uid in birthdays:
            del birthdays[uid]
            self._save_birthday_config()
            return True, "تم حذف عيد الميلاد"
        return False, "لم يتم العثور على عيد ميلاد لهذا العضو"

    def get_birthdays(self, guild_id: int) -> dict:
        gid = str(guild_id)
        return self.birthday_config.get(gid, {}).get("birthdays", {})

    async def _birthday_worker(self):
        await asyncio.sleep(60)
        while True:
            try:
                now = datetime.now()
                current_year = now.year
                current_month = now.month
                current_day = now.day
                for guild in list(self.guilds):
                    cfg = self.get_birthday_config(guild.id)
                    if not cfg.get("birthday_enabled"):
                        continue
                    channel_id = cfg.get("birthday_channel_id", 0)
                    role_id = cfg.get("birthday_role_id", 0)
                    if not channel_id:
                        continue
                    birthdays = self.get_birthdays(guild.id)
                    for uid_str, bday_data in birthdays.items():
                        if bday_data["month"] == current_month and bday_data["day"] == current_day:
                            if bday_data.get("last_wished") == current_year:
                                continue
                            user_id = int(uid_str)
                            member = guild.get_member(user_id)
                            if not member:
                                continue
                            bday_data["last_wished"] = current_year
                            self._save_birthday_config()
                            ch = guild.get_channel(channel_id)
                            if ch:
                                try:
                                    age_str = ""
                                    if bday_data.get("year") and bday_data["year"] > 0:
                                        age = current_year - bday_data["year"]
                                        age_str = f" — {age} سنة!"
                                    embed = discord.Embed(
                                        title="🎂 عيد ميلاد سعيد!",
                                        description=f"**{member.mention}** عيد ميلاده اليوم{age_str}\n\nكل سنة وأنت بخير! 🎉",
                                        color=0xFFD700,
                                    )
                                    embed.set_thumbnail(url=str(member.display_avatar.url))
                                    content = member.mention if role_id else None
                                    await ch.send(content=content, embed=embed)
                                    self._log_activity(f"🎂 عيد ميلاد: {member.display_name} في {guild.name}")
                                except Exception:
                                    pass
                            if role_id:
                                role = guild.get_role(role_id)
                                if role:
                                    try:
                                        await member.add_roles(role, reason="Birthday role")
                                    except Exception:
                                        pass
            except Exception:
                pass
            await asyncio.sleep(300)

    # ── AFK System ───────────────────────────────────────────

    def _set_afk(self, user_id: int, guild_id: int, reason: str = "No reason"):
        self.afk_users[user_id] = {
            "reason": reason,
            "since": _time.time(),
            "guild_id": guild_id,
        }

    def _remove_afk(self, user_id: int) -> dict | None:
        return self.afk_users.pop(user_id, None)

    def _get_afk(self, user_id: int) -> dict | None:
        return self.afk_users.get(user_id)

    def _format_time_ago(self, timestamp: float) -> str:
        diff = _time.time() - timestamp
        if diff < 60:
            return f"{int(diff)} ثانية"
        elif diff < 3600:
            return f"{int(diff // 60)} دقيقة"
        elif diff < 86400:
            return f"{int(diff // 3600)} ساعة"
        else:
            return f"{int(diff // 86400)} يوم"

    async def _handle_afk_command(self, message: discord.Message):
        content = message.content
        if not content.startswith("afk ") and content.strip().lower() != "afk":
            return False
        parts = content.split(None, 1)
        reason = parts[1].strip() if len(parts) > 1 else "No reason"
        self._set_afk(message.author.id, message.guild.id, reason)
        try:
            await message.channel.send(
                f"💤 **{message.author.display_name}** is now AFK: {reason}",
                delete_after=8,
            )
        except Exception:
            pass
        return True

    async def _handle_afk_on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        afk_data = self._remove_afk(message.author.id)
        if afk_data:
            try:
                elapsed = self._format_time_ago(afk_data["since"])
                await message.channel.send(
                    f"👋 Welcome back **{message.author.display_name}**! You were AFK for {elapsed}.",
                    delete_after=8,
                )
            except Exception:
                pass
        for user in message.mentions:
            if user.id == message.author.id:
                continue
            afk_data = self._get_afk(user.id)
            if afk_data:
                try:
                    elapsed = self._format_time_ago(afk_data["since"])
                    await message.channel.send(
                        f"💤 **{user.display_name}** is AFK since {elapsed}: {afk_data['reason']}",
                        delete_after=10,
                    )
                except Exception:
                    pass
                break

    # ── Reminder System Enhancement ──────────────────────────

    @staticmethod
    def _parse_time(time_str: str) -> int | None:
        """Parse time string like 1h, 30m, 2d into seconds."""
        match = re.match(r'^(\d+)([smhd])$', time_str.lower().strip())
        if not match:
            return None
        amount = int(match.group(1))
        unit = match.group(2)
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        return amount * multipliers[unit]

    async def _handle_remind_command(self, message: discord.Message):
        content = message.content
        if not content.startswith("remind "):
            return False
        parts = content.split(None, 2)
        if len(parts) < 3:
            try:
                await message.channel.send("Usage: `remind <time> <message>` (e.g., `remind 1h Check this`)", delete_after=8)
            except Exception:
                pass
            return True
        time_str = parts[1]
        seconds = self._parse_time(time_str)
        if seconds is None or seconds <= 0:
            try:
                await message.channel.send("Invalid time format. Use `s` (seconds), `m` (minutes), `h` (hours), `d` (days).", delete_after=8)
            except Exception:
                pass
            return True
        reminder_msg = parts[2]
        timestamp = (datetime.now() + timedelta(seconds=seconds)).isoformat()
        self.set_reminder(message.channel.id, f"{message.author.mention}: {reminder_msg}", timestamp)
        try:
            await message.channel.send(f"⏰ Reminder set! I'll remind you in `{time_str}`.", delete_after=8)
        except Exception:
            pass
        return True

    # ── Suggestion System ────────────────────────────────────

    def get_suggestion_config(self, guild_id: int) -> dict:
        cfg = self.suggestion_config.get(str(guild_id), {})
        return {
            "enabled": cfg.get("enabled", False),
            "channel_id": cfg.get("channel_id", 0),
            "up_emoji": cfg.get("up_emoji", "👍"),
            "down_emoji": cfg.get("down_emoji", "👎"),
            "min_votes": cfg.get("min_votes", 3),
            "log_channel": cfg.get("log_channel", 0),
        }

    def set_suggestion_config(self, guild_id: int, **kwargs) -> tuple[bool, str]:
        gid = str(guild_id)
        if gid not in self.suggestion_config:
            self.suggestion_config[gid] = {}
        for key, value in kwargs.items():
            self.suggestion_config[gid][key] = value
        self._save_suggestion_config()
        return True, "تم حفظ إعدادات الاقتراحات"

    def _save_suggestion_config(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        config["suggestion_config"] = self.suggestion_config
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def _save_suggestion_votes(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        config["suggestion_votes"] = self.suggestion_votes
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    async def _handle_suggestion_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        cfg = self.get_suggestion_config(message.guild.id)
        if not cfg["enabled"]:
            return
        if message.channel.id != cfg["channel_id"]:
            return
        perms = message.author.guild_permissions
        if perms.manage_messages or perms.administrator:
            return
        up_emoji = cfg["up_emoji"]
        down_emoji = cfg["down_emoji"]
        embed = discord.Embed(
            title="💡 Suggestion",
            description=message.content,
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=str(message.author), icon_url=str(message.author.display_avatar.url))
        embed.set_footer(text=f"Suggestion by {message.author.display_name}")
        try:
            await message.delete()
            suggestion_msg = await message.channel.send(embed=embed)
            await suggestion_msg.add_reaction(up_emoji)
            await suggestion_msg.add_reaction(down_emoji)
            gid = str(message.guild.id)
            sid = str(suggestion_msg.id)
            if gid not in self.suggestion_votes:
                self.suggestion_votes[gid] = {}
            self.suggestion_votes[gid][sid] = {
                "upvotes": [],
                "downvotes": [],
                "author_id": message.author.id,
                "channel_id": message.channel.id,
            }
            self._save_suggestion_votes()
            self._log_activity(f"💡 اقتراح جديد من {message.author.display_name} في #{message.channel.name}")
        except discord.Forbidden:
            pass
        except Exception:
            pass

    async def _handle_suggestion_reaction(self, payload: discord.RawReactionActionEvent):
        if payload.member and payload.member.bot:
            return
        if not payload.guild_id:
            return
        cfg = self.get_suggestion_config(payload.guild_id)
        if not cfg["enabled"]:
            return
        gid = str(payload.guild_id)
        sid = str(payload.message_id)
        votes = self.suggestion_votes.get(gid, {}).get(sid)
        if not votes:
            return
        user_id = payload.user_id
        emoji_str = str(payload.emoji)
        up_emoji = cfg["up_emoji"]
        down_emoji = cfg["down_emoji"]
        if emoji_str == up_emoji:
            if user_id in votes["downvotes"]:
                votes["downvotes"].remove(user_id)
            if user_id not in votes["upvotes"]:
                votes["upvotes"].append(user_id)
        elif emoji_str == down_emoji:
            if user_id in votes["upvotes"]:
                votes["upvotes"].remove(user_id)
            if user_id not in votes["downvotes"]:
                votes["downvotes"].append(user_id)
        else:
            return
        self._save_suggestion_votes()
        up_count = len(votes["upvotes"])
        down_count = len(votes["downvotes"])
        min_votes = cfg.get("min_votes", 3)
        log_channel_id = cfg.get("log_channel", 0)
        if (up_count >= min_votes or down_count >= min_votes) and log_channel_id:
            ch = self.client.get_channel(log_channel_id)
            if ch:
                status = "✅ Accepted" if up_count > down_count else "❌ Rejected"
                try:
                    embed = discord.Embed(
                        title=f"Suggestion {status}",
                        description=f"👍 {up_count} | 👎 {down_count}\n\n[Jump to suggestion](https://discord.com/channels/{payload.guild_id}/{votes['channel_id']}/{sid})",
                        color=0x2ECC71 if up_count > down_count else 0xE74C3C,
                    )
                    await ch.send(embed=embed)
                except Exception:
                    pass


    # ── 1. Music Queue Visual ──────────────────────────────────

    def get_queue_display(self, guild_id: int) -> str:
        info = self.np_info.get(guild_id, {})
        queue = self.music_queues.get(guild_id, [])
        lines = []
        if info.get("title"):
            dur = info.get("duration", 0)
            d = f"{dur // 60}:{dur % 60:02d}" if dur else "?"
            lines.append(f"▶️ **{info['title'][:60]}** ({d}) — {info.get('requester', '?')}")
        else:
            lines.append("🔴 لا يوجد تشغيل حالياً")
        if queue:
            lines.append("")
            for i, t in enumerate(queue[:10]):
                dur = t.get("duration", 0)
                d = f"{dur // 60}:{dur % 60:02d}" if dur else ""
                lines.append(f"`{i+1}.` {t.get('title', '?')[:50]} `{d}` — {t.get('requester', '?')}")
            if len(queue) > 10:
                lines.append(f"\n...و {len(queue) - 10} أغنية أخرى")
        lines.append(f"\n📋 الإجمالي: {len(queue)} في القائمة")
        return "\n".join(lines)

    def get_music_stats(self, guild_id: int) -> dict:
        stats = self._music_play_stats.get(guild_id, {})
        queue = self.music_queues.get(guild_id, [])
        total_plays = stats.get("total_plays", 0)
        total_time = stats.get("total_time", 0)
        top_songs = sorted(stats.get("songs", {}).items(), key=lambda x: x[1], reverse=True)[:10]
        top_requesters = sorted(stats.get("requesters", {}).items(), key=lambda x: x[1], reverse=True)[:10]
        return {
            "total_plays": total_plays,
            "total_time": total_time,
            "total_time_fmt": f"{total_time // 3600}h {(total_time % 3600) // 60}m",
            "top_songs": [{"title": t, "plays": c} for t, c in top_songs],
            "top_requesters": [{"requester": r, "plays": c} for r, c in top_requesters],
            "queue_size": len(queue),
        }

    def _track_music_play(self, guild_id: int, title: str, requester: str, duration: int):
        if guild_id not in self._music_play_stats:
            self._music_play_stats[guild_id] = {"total_plays": 0, "total_time": 0, "songs": {}, "requesters": {}}
        s = self._music_play_stats[guild_id]
        s["total_plays"] += 1
        s["total_time"] += duration
        s["songs"][title] = s["songs"].get(title, 0) + 1
        if requester:
            s["requesters"][requester] = s["requesters"].get(requester, 0) + 1

    # ── 2. Lyrics Search ──────────────────────────────────────

    async def search_lyrics(self, query: str) -> Optional[dict]:
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                search_url = f"https://api.lyrics.ovh/v1/{query}"
                async with session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        lyrics_data = data.get("lyrics", {})
                        return {
                            "title": lyrics_data.get("title", query),
                            "artist": lyrics_data.get("artist", ""),
                            "lyrics": lyrics_data.get("lyrics", ""),
                            "url": f"https://genius.com/search?q={query.replace(' ', '+')}",
                        }
        except Exception:
            pass
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                search_url = f"https://lrclib.net/api/search?q={query}"
                async with session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        results = await resp.json()
                        if results:
                            r = results[0]
                            synced = r.get("syncedLyrics") or r.get("plainLyrics", "")
                            return {
                                "title": r.get("trackName", query),
                                "artist": r.get("artistName", ""),
                                "lyrics": synced,
                                "url": r.get("url", ""),
                            }
        except Exception:
            pass
        return None

    # ── 4. Now Playing Enhanced ────────────────────────────────

    def get_now_playing_info(self, guild_id: int) -> Optional[dict]:
        info = self.np_info.get(guild_id)
        if not info:
            return None
        elapsed = 0
        duration = info.get("duration", 0)
        if info.get("start_time"):
            if self.paused.get(guild_id):
                elapsed = int(self._pause_elapsed.get(guild_id, 0))
            else:
                elapsed = int(_time.time() - info["start_time"])
        return {
            "title": info.get("title", ""),
            "url": info.get("url", ""),
            "thumbnail": info.get("thumbnail", ""),
            "duration": duration,
            "requester": info.get("requester", ""),
            "channel": info.get("channel", ""),
            "progress": elapsed,
            "progress_fmt": f"{elapsed // 60}:{elapsed % 60:02d}",
            "duration_fmt": f"{duration // 60}:{duration % 60:02d}" if duration else "?",
            "volume": self.get_volume(guild_id),
            "paused": self.paused.get(guild_id, False),
        }

    # ── 5. Webhook Manager ────────────────────────────────────

    async def get_webhooks(self, guild_id: int) -> list[dict]:
        guild = self.get_guild(guild_id)
        if not guild:
            return []
        try:
            webhooks = await guild.webhooks()
            return [{"id": w.id, "name": w.name, "channel_id": w.channel.id if w.channel else 0,
                      "channel_name": w.channel.name if w.channel else "?", "avatar": str(w.avatar.url) if w.avatar else ""} for w in webhooks]
        except discord.Forbidden:
            return []
        except Exception:
            return []

    async def create_webhook(self, guild_id: int, channel_id: int, name: str = "Bot Webhook") -> tuple[bool, str]:
        guild = self.get_guild(guild_id)
        if not guild:
            return False, "سيرفر غير موجود"
        channel = guild.get_channel(channel_id)
        if not channel:
            return False, "قناة غير موجودة"
        try:
            wh = await channel.create_webhook(name=name)
            return True, f"تم إنشاء Webhook: {wh.name} (ID: {wh.id})"
        except discord.Forbidden:
            return False, "لا توجد صلاحية لإنشاء Webhook"
        except Exception as e:
            return False, str(e)

    async def delete_webhook(self, guild_id: int, webhook_id: int) -> tuple[bool, str]:
        guild = self.get_guild(guild_id)
        if not guild:
            return False, "سيرفر غير موجود"
        try:
            webhooks = await guild.webhooks()
            for wh in webhooks:
                if wh.id == webhook_id:
                    await wh.delete()
                    return True, f"تم حذف Webhook: {wh.name}"
            return False, "Webhook غير موجود"
        except discord.Forbidden:
            return False, "لا توجد صلاحية لحذف Webhook"
        except Exception as e:
            return False, str(e)

    async def send_webhook(self, webhook_id: int, content: str = "", embeds: list = None) -> tuple[bool, str]:
        if not self.client:
            return False, "البوت غير متصل"
        try:
            wh = await self.client.fetch_webhook(webhook_id)
            discord_embeds = []
            if embeds:
                for ed in embeds:
                    e = discord.Embed(
                        title=ed.get("title", ""),
                        description=ed.get("description", ""),
                        color=int(ed.get("color", "#5865F2").lstrip("#"), 16) if ed.get("color") else 0x5865F2,
                    )
                    for f in ed.get("fields", []):
                        e.add_field(name=f.get("name", ""), value=f.get("value", ""), inline=f.get("inline", False))
                    discord_embeds.append(e)
            await wh.send(content=content or None, embeds=discord_embeds if discord_embeds else None)
            return True, "تم الإرسال عبر Webhook"
        except Exception as e:
            return False, str(e)

    # ── 6. Emoji Manager ──────────────────────────────────────

    async def get_emojis(self, guild_id: int) -> list[dict]:
        guild = self.get_guild(guild_id)
        if not guild:
            return []
        result = []
        for e in guild.emojis:
            result.append({
                "id": e.id,
                "name": e.name,
                "animated": e.animated,
                "url": str(e.url),
                "available": e.available,
                "created": e.created_at.strftime("%Y-%m-%d") if e.created_at else "",
            })
        return result

    async def create_emoji(self, guild_id: int, name: str, image_url: str) -> tuple[bool, str]:
        guild = self.get_guild(guild_id)
        if not guild:
            return False, "سيرفر غير موجود"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        return False, "فشل تحميل الصورة"
                    data = await resp.read()
            emoji = await guild.create_custom_emoji(name=name, image=data)
            return True, f"تم إنشاء الإيموجي: {emoji} (ID: {emoji.id})"
        except discord.Forbidden:
            return False, "لا توجد صلاحية لإدارة الإيموجيات"
        except Exception as e:
            return False, str(e)

    async def delete_emoji(self, guild_id: int, emoji_id: int) -> tuple[bool, str]:
        guild = self.get_guild(guild_id)
        if not guild:
            return False, "سيرفر غير موجود"
        emoji = guild.get_emoji(emoji_id)
        if not emoji:
            return False, "إيموجي غير موجود"
        try:
            name = emoji.name
            await emoji.delete()
            return True, f"تم حذف الإيموجي: {name}"
        except discord.Forbidden:
            return False, "لا توجد صلاحية لحذف الإيموجي"
        except Exception as e:
            return False, str(e)

    # ── 7. Role Hierarchy ─────────────────────────────────────

    def get_role_hierarchy(self, guild_id: int) -> list[dict]:
        guild = self.get_guild(guild_id)
        if not guild:
            return []
        roles = sorted(guild.roles, key=lambda r: r.position, reverse=True)
        result = []
        for r in roles:
            member_count = sum(1 for m in guild.members if r in m.roles and not r.is_default())
            result.append({
                "id": r.id,
                "name": r.name,
                "position": r.position,
                "color": str(r.color) if r.color != discord.Color.default() else "#000000",
                "member_count": member_count,
                "mentionable": r.mentionable,
                "hoist": r.hoist,
                "is_default": r.is_default(),
            })
        return result

    # ── 8. Invite Tracker ─────────────────────────────────────

    async def get_invites(self, guild_id: int) -> list[dict]:
        guild = self.get_guild(guild_id)
        if not guild:
            return []
        try:
            invites = await guild.invites()
            self._invite_cache[guild_id] = [{"code": i.code, "uses": i.uses, "inviter": str(i.inviter)} for i in invites]
            result = []
            for inv in invites:
                result.append({
                    "code": inv.code,
                    "uses": inv.uses,
                    "max_uses": inv.max_uses,
                    "inviter": str(inv.inviter),
                    "inviter_id": inv.inviter.id if inv.inviter else 0,
                    "channel": str(inv.channel) if inv.channel else "?",
                    "created": inv.created_at.strftime("%Y-%m-%d %H:%M") if inv.created_at else "",
                    "expires": inv.expires_at.strftime("%Y-%m-%d %H:%M") if inv.expires_at else "never",
                    "url": inv.url,
                })
            return result
        except discord.Forbidden:
            return []
        except Exception:
            return []

    async def get_invite_stats(self, guild_id: int) -> list[dict]:
        invites = await self.get_invites(guild_id)
        inviter_stats: dict[str, dict] = {}
        for inv in invites:
            inviter = inv.get("inviter", "Unknown")
            if inviter not in inviter_stats:
                inviter_stats[inviter] = {"inviter": inviter, "total_uses": 0, "invites": []}
            inviter_stats[inviter]["total_uses"] += inv.get("uses", 0)
            inviter_stats[inviter]["invites"].append(inv)
        leaderboard = sorted(inviter_stats.values(), key=lambda x: x["total_uses"], reverse=True)
        return leaderboard

    # ── 9. Voice Connected ────────────────────────────────────

    def get_voice_connected(self, guild_id: int) -> list[dict]:
        guild = self.get_guild(guild_id)
        if not guild:
            return []
        result = []
        for vc in guild.voice_channels:
            members = [m for m in vc.members if not m.bot]
            if members:
                result.append({
                    "channel_id": vc.id,
                    "channel_name": vc.name,
                    "member_count": len(members),
                    "members": [{"id": m.id, "name": m.display_name, "status": str(m.status)} for m in members],
                })
        return result

    def get_voice_stats(self, guild_id: int) -> dict:
        guild = self.get_guild(guild_id)
        if not guild:
            return {"total_in_voice": 0, "active_channels": 0, "channels": []}
        total = 0
        active = []
        for vc in guild.voice_channels:
            non_bot = [m for m in vc.members if not m.bot]
            if non_bot:
                total += len(non_bot)
                active.append({"channel_id": vc.id, "channel_name": vc.name, "count": len(non_bot)})
        return {
            "total_in_voice": total,
            "active_channels": len(active),
            "channels": active,
        }

    # ── 10. Bot Status Page ───────────────────────────────────

    def get_bot_status(self) -> dict:
        uptime_secs = int(_time.time() - self._connect_time)
        h = uptime_secs // 3600
        m = (uptime_secs % 3600) // 60
        s = uptime_secs % 60
        total_members = sum(g.member_count or 0 for g in self.guilds)
        return {
            "uptime": f"{h}h {m}m {s}s",
            "uptime_seconds": uptime_secs,
            "guilds": len(self.guilds),
            "members": total_members,
            "version": "2.0",
            "latency": round(self.client.latency * 1000, 2) if self.client else 0,
            "status": "connected" if self.ready else "disconnected",
        }

    # ── 11. Command Usage Stats ───────────────────────────────

    def get_command_stats(self, limit: int = 20) -> list[dict]:
        sorted_cmds = sorted(self.command_stats.items(), key=lambda x: x[1], reverse=True)[:limit]
        total = sum(self.command_stats.values())
        return [{"command": cmd, "count": count, "percent": round(count / total * 100, 1) if total else 0} for cmd, count in sorted_cmds]

    # ── 12. Error Dashboard ───────────────────────────────────

    def log_error(self, error_type: str, message: str, guild_id: int = None, user_id: int = None):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": error_type,
            "message": str(message)[:500],
            "guild_id": guild_id,
            "guild_name": "",
            "user_id": user_id,
            "user_name": "",
        }
        if guild_id:
            g = self.get_guild(guild_id)
            if g:
                entry["guild_name"] = g.name
        if user_id and self.client:
            u = self.client.get_user(user_id)
            if u:
                entry["user_name"] = str(u)
        self.error_log.insert(0, entry)
        self.error_log = self.error_log[:500]

    def get_errors(self, limit: int = 50) -> list[dict]:
        return self.error_log[:limit]

    def clear_errors(self):
        self.error_log.clear()

    # ── 13. Performance Monitor ───────────────────────────────

    def get_performance(self) -> dict:
        import os
        try:
            import psutil
            proc = psutil.Process(os.getpid())
            mem = proc.memory_info().rss / (1024 * 1024)
            cpu = proc.cpu_percent(interval=0.1)
        except ImportError:
            mem = 0
            cpu = 0
        uptime_secs = int(_time.time() - self._connect_time)
        total_members = sum(g.member_count or 0 for g in self.guilds)
        api_latency = 0
        if self.client and self.client.ws:
            api_latency = round(self.client.ws.latency * 1000, 2)
        return {
            "latency": round(self.client.latency * 1000, 2) if self.client else 0,
            "api_latency": api_latency,
            "memory_mb": round(mem, 2),
            "cpu_percent": round(cpu, 2),
            "guilds": len(self.guilds),
            "members": total_members,
            "uptime": uptime_secs,
        }

    # ── 14. Scheduled Messages (cron-based) ───────────────────

    def add_scheduled_message(self, channel_id: int, message: str, cron_expr: str) -> tuple[bool, str]:
        entry = {
            "channel_id": channel_id,
            "message": message,
            "cron_expr": cron_expr,
            "enabled": True,
            "last_run": None,
        }
        self.scheduled_messages.append(entry)
        return True, f"تمت إضافة الرسالة المجدولة: {cron_expr}"

    def remove_scheduled_message(self, index: int) -> tuple[bool, str]:
        if 0 <= index < len(self.scheduled_messages):
            removed = self.scheduled_messages.pop(index)
            return True, f"تم حذف الرسالة: {removed.get('message', '')[:30]}..."
        return False, "غير موجود"

    def get_scheduled_messages(self) -> list[dict]:
        return list(self.scheduled_messages)

    def _parse_cron_field(self, field: str, current_val: int, min_val: int, max_val: int) -> bool:
        if field == "*":
            return True
        if field.isdigit():
            return int(field) == current_val
        if "/" in field:
            parts = field.split("/")
            step = int(parts[1])
            return current_val % step == 0
        if "-" in field:
            lo, hi = field.split("-")
            return int(lo) <= current_val <= int(hi)
        if "," in field:
            return current_val in [int(x) for x in field.split(",")]
        return False

    def _cron_matches(self, cron_expr: str, now: datetime) -> bool:
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return False
        return (
            self._parse_cron_field(parts[0], now.minute, 0, 59) and
            self._parse_cron_field(parts[1], now.hour, 0, 23) and
            self._parse_cron_field(parts[2], now.day, 1, 31) and
            self._parse_cron_field(parts[3], now.month, 1, 12) and
            self._parse_cron_field(parts[4], now.isoweekday() % 7, 0, 6)
        )

    async def _scheduled_worker_cron(self):
        await asyncio.sleep(60)
        while True:
            try:
                now = datetime.now()
                for entry in self.scheduled_messages:
                    if not entry.get("enabled"):
                        continue
                    last = entry.get("last_run")
                    if last:
                        try:
                            last_dt = datetime.fromisoformat(last)
                            if (now - last_dt).total_seconds() < 50:
                                continue
                        except Exception:
                            pass
                    if self._cron_matches(entry.get("cron_expr", ""), now):
                        ch = self.client.get_channel(entry["channel_id"])
                        if ch:
                            try:
                                await ch.send(f"📅 **رسالة مجدولة:**\n{entry['message']}")
                                entry["last_run"] = now.isoformat()
                                self._log_activity(f"📅 cron: {entry['message'][:40]}")
                            except Exception:
                                pass
            except Exception:
                pass
            await asyncio.sleep(60)

    # ── 15. Cross-Server Announce ─────────────────────────────

    async def cross_announce(self, message: str, guild_ids: list[int] = None) -> dict:
        sent = 0
        failed = 0
        guilds = guild_ids if guild_ids else [g.id for g in self.guilds]
        for gid in guilds:
            ch_id = self.log_channels.get(gid)
            if not ch_id:
                guild = self.get_guild(gid)
                if guild and guild.system_channel:
                    ch_id = guild.system_channel.id
            if not ch_id:
                failed += 1
                continue
            ch = self.client.get_channel(ch_id) if self.client else None
            if not ch:
                failed += 1
                continue
            try:
                await ch.send(f"📢 **إعلان عام:**\n{message}")
                sent += 1
            except Exception:
                failed += 1
        return {"sent": sent, "failed": failed, "total": len(guilds)}

    # ── 16. API Rate Monitor ──────────────────────────────────

    def track_api_call(self, endpoint: str, status: int):
        self.api_calls.append({
            "timestamp": _time.time(),
            "endpoint": endpoint,
            "status": status,
        })
        if len(self.api_calls) > 10000:
            self.api_calls = self.api_calls[-5000:]

    def get_api_rate_stats(self) -> dict:
        now = _time.time()
        last_minute = [c for c in self.api_calls if now - c["timestamp"] <= 60]
        last_hour = [c for c in self.api_calls if now - c["timestamp"] <= 3600]
        total = len(last_hour)
        errors = sum(1 for c in last_hour if c["status"] >= 400)
        return {
            "calls_per_minute": len(last_minute),
            "calls_per_hour": total,
            "error_count": errors,
            "error_rate": round(errors / total * 100, 2) if total else 0,
            "total_tracked": len(self.api_calls),
        }

    # ── Hook: Track music plays ───────────────────────────────

    async def _track_play_hook(self, guild_id: int, title: str, requester: str, duration: int):
        self._track_music_play(guild_id, title, requester, duration)


bot_manager = BotManager()


def _yt_search(query: str, limit: int = 5) -> list:
    """Fast YouTube search - try yt-dlp then Invidious."""
    try:
        return _ytdlp_search(query, limit)
    except Exception:
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            return loop.run_until_complete(_invidious_search(query, limit))
        except Exception:
            return []


async def _yt_search_async(query: str, limit: int = 5) -> list:
    import asyncio
    return await asyncio.get_event_loop().run_in_executor(None, _yt_search, query, limit)


class SearchModal(discord.ui.Modal, title="🔎 بحث يوتيوب"):
    query = discord.ui.TextInput(label="اسم الأغنية", placeholder="مثلاً: Imagine Dragons Believer", style=discord.TextStyle.short, required=True)

    def __init__(self, bm: "BotManager", guild_id: int):
        super().__init__()
        self.bm = bm
        self.gid = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            results = await _yt_search_async(self.query.value, 5)
        except Exception as e:
            await interaction.followup.send(f"❌ فشل البحث: {e}", ephemeral=True)
            return
        if not results:
            await interaction.followup.send("🔍 لا توجد نتائج", ephemeral=True)
            return
        self.bm._last_search[self.gid] = results

        view = SearchSelectView(self.bm, self.gid, results)
        embed = discord.Embed(title="🔎 نتائج البحث", description=f"**{self.query.value}**", color=0x00e5ff)
        for i, r in enumerate(results):
            dur = f"{r['duration'] // 60}:{r['duration'] % 60:02d}" if r['duration'] else "?"
            embed.add_field(
                name=f"`{i+1}.` {r['title'][:55]}",
                value=f"⏱ {dur}",
                inline=False,
            )
        if results and results[0].get("thumbnail"):
            embed.set_thumbnail(url=results[0]["thumbnail"])
        embed.set_footer(text="اختر من القائمة للتشغيل ⬇️")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class SearchSelectView(discord.ui.View):
    def __init__(self, bm: "BotManager", guild_id: int, results: list):
        super().__init__(timeout=60)
        self.bm = bm
        self.gid = guild_id
        self.results = results
        opts = []
        for i, r in enumerate(results):
            dur = f"{r['duration'] // 60}:{r['duration'] % 60:02d}" if r['duration'] else "?"
            opts.append(discord.SelectOption(
                label=r["title"][:100],
                description=f"⏱ {dur}",
                value=str(i),
                emoji="▶️",
            ))
        sel = discord.ui.Select(placeholder="▶️ اختر أغنية...", options=opts)
        sel.callback = self._pick
        self.add_item(sel)

    async def _pick(self, interaction: discord.Interaction):
        try:
            idx = int(interaction.data["values"][0])
            r = self.results[idx]
            gid = self.gid
            bm = self.bm
            member = interaction.user

            await interaction.response.defer(ephemeral=True)

            vc = bm.voice_clients.get(gid)
            if not vc:
                if not member.voice or not member.voice.channel:
                    return await interaction.followup.send("❌ ادخل قناة صوتية", ephemeral=True)
                try:
                    vc = await member.voice.channel.connect(timeout=10)
                    bm.voice_clients[gid] = vc
                except Exception as e:
                    return await interaction.followup.send(f"❌ {e}", ephemeral=True)

            ch_name = member.voice.channel.name if member.voice and member.voice.channel else ""
            ok, msg = await bm.play_youtube(gid, r["url"], str(member), ch_name)
            if ok:
                await interaction.followup.send(f"▶️ **{r['title'][:60]}** ✅", ephemeral=True)
                try:
                    await bm.send_or_update_panel(gid)
                except Exception:
                    pass
            else:
                await interaction.followup.send(f"❌ {msg}", ephemeral=True)
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            except Exception:
                pass


class MusicPanelView(discord.ui.View):
    def __init__(self, bm: "BotManager"):
        super().__init__(timeout=None)
        self.bm = bm

    def _state(self, gid: int) -> dict:
        vc = self.bm.voice_clients.get(gid)
        np = self.bm.np_info.get(gid, {})
        q = self.bm.music_queues.get(gid, [])
        vol = int(self.bm.music_volumes.get(gid, 1.0) * 100)
        elapsed = 0
        if np.get("start_time"):
            elapsed = __import__("time").time() - np["start_time"]
            if self.bm.paused.get(gid):
                elapsed = self.bm._pause_elapsed.get(gid, 0)
        return {
            "vc": vc,
            "connected": vc is not None and vc.is_connected(),
            "playing": vc.is_playing() if vc else False,
            "paused": self.bm.paused.get(gid, False),
            "title": np.get("title", ""),
            "url": np.get("url", ""),
            "thumb": np.get("thumbnail", ""),
            "requester": np.get("requester", ""),
            "duration": np.get("duration", 0),
            "elapsed": elapsed,
            "queue": q,
            "vol": vol,
            "loop": self.bm.loop_mode.get(gid, False),
            "qloop": self.bm.queue_loop.get(gid, False),
            "shuffle": self.bm.shuffle_mode.get(gid, False),
        }

    def _t(self, sec: int) -> str:
        m, s = divmod(max(0, int(sec)), 60)
        return f"{m}:{s:02d}"

    def _bar(self, cur: int, total: int, length: int = 18) -> str:
        if total <= 0:
            return "░" * length
        pct = min(1.0, cur / total)
        filled = int(length * pct)
        return "█" * filled + "░" * (length - filled)

    def build(self, gid: int) -> discord.Embed:
        s = self._state(gid)
        if s["title"]:
            bar = self._bar(s["elapsed"], s["duration"])
            desc = (
                f"```\n{bar}\n```\n"
                f"`{self._t(s['elapsed'])}` / `{self._t(s['duration'])}`\n\n"
            )
            icons = []
            if s["paused"]:
                icons.append("⏸️")
            elif s["playing"]:
                icons.append("▶️")
            if s["loop"]:
                icons.append("🔁")
            if s["qloop"]:
                icons.append("🔂")
            if s["shuffle"]:
                icons.append("🔀")
            desc += " ".join(icons) + "\n\n"
            desc += f"👤 **{s['requester']}**\n"
            desc += f"🔊 **{s['vol']}%** • 📋 **{len(s['queue'])}** في القائمة"
            e = discord.Embed(title=s["title"][:256], url=s["url"] or discord.Embed.Empty, description=desc, color=0x00e5ff)
            if s["thumb"]:
                e.set_thumbnail(url=s["thumb"])
            e.set_author(name="🎶 NEON Music", icon_url="https://cdn-icons-png.flaticon.com/512/3659/3659783.png")
        else:
            desc = "🔴 لا يوجد تشغيل\n\nاضغط 🔎 للبحث أو اكتب `!play <اسم>`"
            if s["connected"]:
                desc = "🟢 متصل — جاهز للتشغيل\n\nاضغط 🔎 للبحث أو اكتب `!play <اسم>`"
            e = discord.Embed(title="🎶 NEON Music", description=desc, color=0x5865f2)
            e.set_author(name="NEON Music", icon_url="https://cdn-icons-png.flaticon.com/512/3659/3659783.png")
        return e

    async def _respond(self, interaction: discord.Interaction, gid: int):
        try:
            await interaction.response.edit_message(embed=self.build(gid), view=self)
        except Exception:
            try:
                await interaction.message.edit(embed=self.build(gid), view=self)
            except Exception:
                pass

    # ── Row 0 ──

    @discord.ui.button(label="⏯ Play/Pause", style=discord.ButtonStyle.primary, row=0)
    async def btn_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.guild_id
        s = self._state(gid)
        if not s["connected"]:
            return await interaction.response.send_message("❌ غير متصل", ephemeral=True)
        if s["paused"]:
            await self.bm.resume_track(gid)
        elif s["playing"]:
            await self.bm.pause_track(gid)
        else:
            return await interaction.response.send_message("❌ لا يوجد أغنية", ephemeral=True)
        await self._respond(interaction, gid)

    @discord.ui.button(label="⏭ Skip", style=discord.ButtonStyle.secondary, row=0)
    async def btn_skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.guild_id
        ok, msg = await self.bm.skip_track(gid)
        if not ok:
            return await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
        await __import__("asyncio").sleep(0.3)
        await self._respond(interaction, gid)

    @discord.ui.button(label="⏹ Stop", style=discord.ButtonStyle.danger, row=0)
    async def btn_stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.guild_id
        ok, msg = await self.bm.stop_playback(gid)
        if not ok:
            return await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
        await self._respond(interaction, gid)

    @discord.ui.button(label="🔊+", style=discord.ButtonStyle.secondary, row=0)
    async def btn_vup(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.guild_id
        cur = self.bm.music_volumes.get(gid, 1.0)
        new_v = min(2.0, cur + 0.1)
        self.bm.music_volumes[gid] = new_v
        vc = self.bm.voice_clients.get(gid)
        if vc and vc.source:
            vc.source.volume = new_v
        await self._respond(interaction, gid)

    # ── Row 1 ──

    @discord.ui.button(label="🔇-", style=discord.ButtonStyle.secondary, row=1)
    async def btn_vdown(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.guild_id
        cur = self.bm.music_volumes.get(gid, 1.0)
        new_v = max(0.05, cur - 0.1)
        self.bm.music_volumes[gid] = new_v
        vc = self.bm.voice_clients.get(gid)
        if vc and vc.source:
            vc.source.volume = new_v
        await self._respond(interaction, gid)

    @discord.ui.button(label="🔁 Loop", style=discord.ButtonStyle.secondary, row=1)
    async def btn_loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.guild_id
        self.bm.loop_mode[gid] = not self.bm.loop_mode.get(gid, False)
        await self._respond(interaction, gid)

    @discord.ui.button(label="🔀 Shuffle", style=discord.ButtonStyle.secondary, row=1)
    async def btn_shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.guild_id
        self.bm.shuffle_mode[gid] = not self.bm.shuffle_mode.get(gid, False)
        if self.bm.shuffle_mode[gid] and self.bm.music_queues.get(gid):
            import random
            random.shuffle(self.bm.music_queues[gid])
        await self._respond(interaction, gid)

    @discord.ui.button(label="🔂 Queue", style=discord.ButtonStyle.secondary, row=1)
    async def btn_qloop(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.guild_id
        self.bm.queue_loop[gid] = not self.bm.queue_loop.get(gid, False)
        await self._respond(interaction, gid)

    # ── Row 2 ──

    @discord.ui.button(label="📋 Queue", style=discord.ButtonStyle.secondary, row=2)
    async def btn_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.guild_id
        s = self._state(gid)
        q = s["queue"]
        np = s["title"]
        if not q and not np:
            return await interaction.response.send_message("📋 القائمة فارغة", ephemeral=True)
        lines = []
        if np:
            lines.append(f"▶️ **{np}**\n")
        for i, t in enumerate(q[:10]):
            dur = t.get("duration", 0)
            d = f"{dur // 60}:{dur % 60:02d}" if dur else ""
            lines.append(f"`{i+1}.` {t.get('title', '?')[:50]} `{d}`")
        if len(q) > 10:
            lines.append(f"\n+{len(q) - 10} أخرى")
        e = discord.Embed(title="📋 قائمة التشغيل", description="\n".join(lines), color=0x00e5ff)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @discord.ui.button(label="🔎 Search", style=discord.ButtonStyle.success, row=2)
    async def btn_search(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.guild_id
        vc = self.bm.voice_clients.get(gid)
        if not vc:
            member = interaction.user
            if member.voice and member.voice.channel:
                ok, msg = await self.bm.join_voice(gid, member.voice.channel.id)
                if not ok:
                    return await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
            else:
                return await interaction.response.send_message("❌ ادخل قناة صوتية", ephemeral=True)
        await interaction.response.send_modal(SearchModal(self.bm, gid))

    @discord.ui.button(label="🔌 Leave", style=discord.ButtonStyle.danger, row=2)
    async def btn_leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.guild_id
        ok, msg = await self.bm.leave_voice(gid)
        await interaction.response.send_message(msg or "🔌 تم", ephemeral=True)
        try:
            await interaction.message.edit(embed=self.build(gid), view=self)
        except Exception:
            pass


class TicketView(discord.ui.View):
    def __init__(self, bot_manager: BotManager, guild_id: int):
        super().__init__(timeout=None)
        self.bot_manager = bot_manager
        self.guild_id = guild_id

    @discord.ui.button(label="🎫 فتح تذكرة", style=discord.ButtonStyle.primary, emoji="🎫")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.bot_manager._handle_ticket_create(interaction, self.guild_id)

class TicketCloseView(discord.ui.View):
    def __init__(self, bot_manager: BotManager):
        super().__init__(timeout=None)
        self.bot_manager = bot_manager

    @discord.ui.button(label="🔒 إغلاق التذكرة", style=discord.ButtonStyle.danger, emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.bot_manager._handle_ticket_close(interaction)


class VerificationView(discord.ui.View):
    def __init__(self, bot_manager: BotManager):
        super().__init__(timeout=None)
        self.bot_manager = bot_manager

    @discord.ui.button(label="✅ Verify", style=discord.ButtonStyle.success, custom_id="verify_button")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.bot_manager._handle_verification(interaction)


class GiveawayView(discord.ui.View):
    def __init__(self, bot_manager: BotManager, giveaway_id: int):
        super().__init__(timeout=None)
        self.bot_manager = bot_manager
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="🎉 Enter", style=discord.ButtonStyle.primary, custom_id="giveaway_enter")
    async def enter_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        for gw in self.bot_manager.giveaways:
            if gw["id"] == self.giveaway_id and not gw.get("ended"):
                entries = gw.get("entries", [])
                if user_id in entries:
                    entries.remove(user_id)
                    await interaction.response.send_message("❌ تم إزالتك من الإيفنت", ephemeral=True)
                else:
                    entries.append(user_id)
                    gw["entries"] = entries
                    self.bot_manager._save_giveaways()
                    await interaction.response.send_message("✅ تم تسجيلك في الإيفنت!", ephemeral=True)
                return
        await interaction.response.send_message("❌ الإيفنت منتهي أو غير موجود", ephemeral=True)
