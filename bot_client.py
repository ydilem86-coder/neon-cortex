"""Discord bot async client wrapper."""

import asyncio
import json
import os
import threading
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
    opts = {"format": "bestaudio/best", "quiet": True, "no_warnings": True, "extract_flat": False}
    if os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    return opts

MUSIC_PREFIX = "!"


def _load_welcome_from_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("welcome", {})
    except Exception:
        return {}


def _load_automod_from_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("automod", {})
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
        self.log_channels: dict[int, int] = {}
        self.scheduled_messages: list = []
        self.ticket_config: dict[int, dict] = {}
        self._bot_tokens: dict[str, "BotManager"] = {}
        self._token_id: str = ""
        self.panel_messages: dict[int, discord.Message] = {}    # guild_id -> panel message
        self.panel_channels: dict[int, int] = {}                # guild_id -> channel_id for panel
        self._welcome_log_callback: Optional[Callable[[str], None]] = None
        self._activity_callback: Optional[Callable[[str], None]] = None
        self._loop_thread = threading.Thread(target=self._run_loop_forever, daemon=True)
        self._loop_thread.start()

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
            await self._send_log(member.guild.id, f"👋 **دخول عضو جديد** {member.mention} ({member.display_name}) — {member.guild.name}")

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
            if message.content.startswith(MUSIC_PREFIX):
                await self._handle_music_command(message)
                return
            await self._handle_automod(message)

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
        async def on_guild_channel_create(channel):
            if not channel.guild:
                return
            ch = self.log_channels.get(channel.guild.id)
            if ch:
                await self._send_log(channel.guild.id, f"📁 **إنشاء قناة** #{channel.name} ({channel.type}) — {channel.guild.name}")

        @self.client.event
        async def on_guild_channel_delete(channel):
            if not channel.guild:
                return
            ch = self.log_channels.get(channel.guild.id)
            if ch:
                await self._send_log(channel.guild.id, f"❌ **حذف قناة** #{channel.name} ({channel.type}) — {channel.guild.name}")

        try:
            await self.client.login(token)
            asyncio.create_task(self.client.connect(reconnect=True))
            await asyncio.wait_for(ready_future, timeout=40)
            asyncio.create_task(self._reminder_worker())
            asyncio.create_task(self._scheduled_worker())
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
            "channel_id": cfg.get("channel_id", ""),
            "message": cfg.get(
                "message",
                "مرحباً {user} في سيرفر {server}! 🎉 أنت العضو رقم {count}",
            ),
            "image_enabled": cfg.get("image_enabled", False),
        }

    def set_welcome_config(
        self, guild_id: int, enabled: bool, channel_id: str, message: str, image_enabled: bool = False
    ) -> tuple[bool, str]:
        self.welcome_config[str(guild_id)] = {
            "enabled": enabled,
            "channel_id": channel_id.strip(),
            "message": message.strip(),
            "image_enabled": image_enabled,
        }
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        config["welcome"] = self.welcome_config
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        status = "مفعّل" if enabled else "معطّل"
        return True, f"تم حفظ إعدادات الترحيب ({status})"

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

        channel_id = cfg.get("channel_id")
        if not channel_id:
            return

        channel = self.client.get_channel(int(channel_id))
        if not channel:
            try:
                channel = await self.client.fetch_channel(int(channel_id))
            except Exception:
                return

        if cfg.get("image_enabled"):
            try:
                buf = await self.generate_welcome_image(member)
                if buf:
                    await channel.send(file=discord.File(buf, "welcome.png"))
                    log_msg = f"👋 صورة ترحيب: {member.display_name} في {member.guild.name}"
                    if self._welcome_log_callback:
                        self._welcome_log_callback(log_msg)
                    return
            except Exception as e:
                if self._welcome_log_callback:
                    self._welcome_log_callback(f"فشل صورة الترحيب: {e}")
        text = self._format_welcome_message(member, cfg["message"])
        try:
            await channel.send(text)
            log_msg = f"👋 ترحيب: {member.display_name} في {member.guild.name}"
            if self._welcome_log_callback:
                self._welcome_log_callback(log_msg)
        except discord.Forbidden:
            if self._welcome_log_callback:
                self._welcome_log_callback(f"لا توجد صلاحية للترحيب في {member.guild.name}")
        except Exception as e:
            if self._welcome_log_callback:
                self._welcome_log_callback(f"فشل الترحيب: {e}")

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
                    import yt_dlp
                    opts = _get_ytdlp_opts()
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        audio_url = info["url"]
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

        try:
            import yt_dlp
            opts = _get_ytdlp_opts()
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                audio_url = info["url"]
                title = info.get("title", title)
                if not thumbnail:
                    thumbnail = info.get("thumbnail", "")
                if not duration:
                    duration = int(info.get("duration") or 0)

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
            import yt_dlp
            source_url = url if (url and url.startswith("http")) else f"ytsearch1:{url}"
            opts = _get_ytdlp_opts()
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(opts).extract_info(source_url, download=False))
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
            import yt_dlp
            opts = {
                "format": "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "default_search": "ytsearch",
            }
            if os.path.exists(COOKIES_FILE):
                opts["cookiefile"] = COOKIES_FILE
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            entries = info.get("entries") or []
            results = []
            for e in entries:
                if not e:
                    continue
                url = e.get("url") or ""
                if url and not url.startswith("http"):
                    url = "https://www.youtube.com/watch?v=" + url
                if not url:
                    vid = e.get("id")
                    if vid:
                        url = "https://www.youtube.com/watch?v=" + vid
                if not url:
                    continue
                results.append({
                    "title": e.get("title", "Unknown"),
                    "url": url,
                    "duration": int(e.get("duration") or 0),
                    "uploader": e.get("uploader", ""),
                })
            return True, results
        except ImportError:
            return False, "yt-dlp غير مثبت. شغّل: pip install yt-dlp"
        except Exception as e:
            return False, f"فشل البحث: {e}"

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


bot_manager = BotManager()


def _yt_search(query: str, limit: int = 5) -> list:
    """Fast YouTube search returning title, url, thumbnail, duration."""
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "default_search": "ytsearch"}
    if os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    results = []
    for e in (info.get("entries") or []):
        if not e:
            continue
        vid = e.get("id") or e.get("url", "")
        url = f"https://www.youtube.com/watch?v={vid}" if vid and not vid.startswith("http") else vid
        thumb = f"https://img.youtube.com/vi/{e.get('id', '0')}/mqdefault.jpg" if e.get("id") else ""
        results.append({
            "title": e.get("title", "?"),
            "url": url,
            "duration": int(e.get("duration") or 0),
            "thumbnail": thumb,
        })
    return results


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
