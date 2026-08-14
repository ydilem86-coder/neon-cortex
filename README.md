# 🎵 NEON Cortex - Discord Bot Control Panel

بوت ديسكورد مع لوحة تحكم ويب كاملة — إدارة السيرفر والموسيقى والإعدادات من الموقع.

## ✨ الميزات

- 🎶 **موسيقى** — بحث يوتيوب + تشغيل + Queue + أزرار تفاعلية
- 🔍 **بحث مدمج** — ابحث وشغّل مباشرة من Panel
- 📊 **إحصائيات** — عدد الأعضاء والقونالات والبومستات
- 🛡️ **إشراف آلي** — حماية سيرفر من الرييد والسبام
- 🎫 **تذاكر** — نظام دعم فني
- 👋 **ترحيب** — رسالة ترحيب تلقائية
- 📋 **سجل النشاط** — تتبع كل العمليات

## 🚀 التشغيل المحلي

```bash
# تثبيت المكتبات
pip install -r requirements.txt -r web/requirements.txt

# شغّل الموقع + البوت
cd web
python run_web.py
```

ثم افتح http://localhost:8000

## ☁️ النشر على السحابة (مجاني)

### Oracle Cloud (مجاني للأبد)
```bash
# على السيرفر:
sudo apt update && sudo apt install python3-pip python3-venv ffmpeg git -y
git clone https://github.com/your-username/neon-cortex.git
cd neon-cortex
pip3 install -r requirements.txt -r web/requirements.txt
cd web
nohup python3 run_web.py 8000 &
```

### Railway
ارفع على GitHub → سجّل في railway.app → اختر المستودع

### Render
ارفع على GitHub → سجّل في render.com → اختر Docker

## 📁 هيكل المشروع

```
discord/
├── bot_client.py          # بوت ديسكورد
├── requirements.txt       # مكتبات البوت
├── Dockerfile             # للنشر بالـ Docker
├── deploy.sh              # سكربت النشر
├── config/                # إعدادات (محفوظة محلياً)
├── web/
│   ├── api_server.py      # FastAPI server
│   ├── run_web.py         # نقطة الدخول
│   ├── start_web.bat      # تشغيل ويندوز
│   ├── requirements.txt   # مكتبات الويب
│   ├── Procfile           # للنشر على Heroku/Railway
│   ├── railway.toml       # إعدادات Railway
│   ├── render.yaml        # إعدادات Render
│   └── static/            # ملفات الواجهة
│       ├── index.html
│       ├── css/style.css
│       └── js/
│           ├── api.js
│           ├── main.js
│           └── views.js
```

## 🔧 المتغيرات

لا تحتاج متغيرات بيئة — التوكن يُحفظ من الموقع.

## 📝 الترخيص

MIT License
