# 🚀 دليل النشر المجاني إلى الأبد

## الخيار 1: Oracle Cloud (مجاني للأبد ✅)
أفضل خيار — سيرفر مجاني دائماً:

### الخطوات:
1. سجّل في https://cloud.oracle.com/free
2. اختر **"Always Free"** → **"Create a VM Instance"**
3. اختر **Ubuntu** + **ARM** (مجاني للأبد)
4. افتح الـ SSH وشغّل:

```bash
# تحديث النظام
sudo apt update && sudo apt upgrade -y

# تثبيت Python
sudo apt install python3-pip python3-venv ffmpeg git -y

# نسخ المشروع
git clone https://github.com/your-repo/discord-bot.git
cd discord-bot

# تثبيت المكتبات
pip3 install -r requirements.txt -r web/requirements.txt

# شغّل البوت
cd web
nohup python3 run_web.py 8000 &
```

5. افتح البورت 8000 في Oracle Cloud (Security List)
6. افتح: `http://your-ip:8000`

---

## الخيار 2: Railway (مجاني محدود)
سجّل في https://railway.app
- يعطي $5 شهرياً مجاناً
- يكفي للبوت

---

## الخيار 3: Render (مجاني بس ينام)
سجّل في https://render.com
- مجاني بس ينام بعد15 دقيقة
- يرجع شغّل لما أحد يفتح الموقع

---

## ملاحظات مهمة:
- **Oracle Cloud** = مجاني للأبد (أنصحك فيه)
- **Railway** = مجاني بس محدود
- **Render** = مجاني بس ينام
- **التوكن** تدخله من الموقع أول مرة
