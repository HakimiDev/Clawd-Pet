"""Clawd v3 - a smart desktop pet: the little orange Claude Code mascot.

He walks on your taskbar, climbs walls, hangs from the ceiling, jumps onto and rides your
windows, dances to music, talks through ANY AI (Claude, OpenAI, Gemini, Ollama...) and does
useful things: timers, pomodoro, notes, opening sites/apps, clipboard translate/explain.
English + Arabic.

Controls
  Click / double-click     jump + quip / open chat        Ctrl+Alt+C   open chat anywhere
  Drag + throw             he tumbles, bounces, skids, sticks to walls, gets dizzy
  Rub the mouse on him     petting                         Mouse wheel  resize
  Hover                    he stops and looks at you       Ctrl+Alt+M   menu anywhere
  Right-click              menu (workout, music, YouTube, tools, games, settings)

Run: double-click this file (or: pythonw clawd_pet.pyw)
"""
import ast
import ctypes
import ctypes.wintypes as wt
import json
import math
import operator
import os
import queue
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
import webbrowser
import winsound
from array import array

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import tkinter as tk
from tkinter import filedialog, simpledialog, ttk

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
try:
    import pygame
except Exception:
    pygame = None

APP, VERSION = "Clawd", "1.2.0"
ORANGE, BLACK, KEY, CREAM = "#D97757", "#141414", "#ff00fe", "#F4EFE8"
HOME = os.path.expanduser("~")
FROZEN = getattr(sys, "frozen", False)
APP_DIR = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
RES_DIR = getattr(sys, "_MEIPASS", APP_DIR)


def _data_dir():
    """Portable: keep everything in 'Clawd Data' next to the app; fall back to %APPDATA% if not writable."""
    for d in (os.path.join(APP_DIR, "Clawd Data"), os.path.join(os.environ.get("APPDATA", HOME), "Clawd")):
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".write_test")
            open(probe, "w").close()
            os.remove(probe)
            return d
        except OSError:
            continue
    return tempfile.gettempdir()


DATA = _data_dir()
CFG_PATH = os.path.join(DATA, "config.json")
NOTES_PATH = os.path.join(DATA, "notes.txt")
CHAT_PATH = os.path.join(DATA, "chat.json")
CACHE = os.path.join(DATA, "cache")
OLD_CFG = os.path.join(HOME, ".clawd_pet.json")
ICON = os.path.join(RES_DIR, "assets", "clawd.ico")
STARTUP = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup", "ClawdPet.vbs")
FPS_MS = 15

# ============================================================== AI providers
PROVIDERS = {
    "anthropic": dict(name="Anthropic (Claude)", base="https://api.anthropic.com", model="claude-opus-5-5",
                      key=True, url="https://console.anthropic.com/settings/keys"),
    "openai": dict(name="OpenAI (ChatGPT)", base="https://api.openai.com/v1", model="gpt-5-mini",
                   key=True, url="https://platform.openai.com/api-keys"),
    "gemini": dict(name="Google Gemini", base="https://generativelanguage.googleapis.com/v1beta/openai",
                   model="gemini-2.5-flash", key=True, url="https://aistudio.google.com/apikey"),
    "openrouter": dict(name="OpenRouter (any model)", base="https://openrouter.ai/api/v1", model="openrouter/auto",
                       key=True, url="https://openrouter.ai/keys"),
    "groq": dict(name="Groq", base="https://api.groq.com/openai/v1", model="llama-3.3-70b-versatile",
                 key=True, url="https://console.groq.com/keys"),
    "deepseek": dict(name="DeepSeek", base="https://api.deepseek.com/v1", model="deepseek-chat",
                     key=True, url="https://platform.deepseek.com/api_keys"),
    "mistral": dict(name="Mistral", base="https://api.mistral.ai/v1", model="mistral-small-latest",
                    key=True, url="https://console.mistral.ai/api-keys"),
    "ollama": dict(name="Ollama (local, free)", base="http://localhost:11434/v1", model="llama3.2",
                   key=False, url="https://ollama.com/download"),
    "lmstudio": dict(name="LM Studio (local, free)", base="http://localhost:1234/v1", model="local-model",
                     key=False, url="https://lmstudio.ai"),
    "custom": dict(name="Custom (OpenAI-compatible)", base="http://localhost:8000/v1", model="", key=False, url=""),
}
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}

DEFAULT_CFG = dict(scale=1.0, lang="auto", sound=True, talk=True, sfx_vol=0.7, music_vol=0.45, ask_rate="normal",
                   follow=True, climb=True, windows=True, fly=True, smart=True, reminders=True, provider="anthropic",
                   brains={}, trust=[], first_run=True, name="", memory=[], stats={}, focus_guard=True,
                   workout=True, asked_name=False, personality="balanced", mischief=True, desk_fx=True)
ASK_RATES = {"often": (25, 50), "normal": (60, 120), "rare": (180, 360), "off": None}
PERSONAS = {  # multipliers used when he decides what to do next
    "balanced": dict(speed=1.0, naughty=1.0, lazy=1.0, social=1.0),
    "naughty": dict(speed=1.15, naughty=3.2, lazy=.6, social=1.1),
    "lazy": dict(speed=.7, naughty=.5, lazy=3.0, social=.8),
    "hyper": dict(speed=1.5, naughty=1.6, lazy=.3, social=1.5),
    "sweet": dict(speed=.95, naughty=.3, lazy=1.0, social=2.4),
}
PERSONA_DESC = {
    "balanced": "",
    "naughty": "The user set your personality to NAUGHTY: a mischievous prankster - you tease, plot harmless pranks, "
               "kick windows and laugh evilly (but you're still helpful). ",
    "lazy": "The user set your personality to LAZY: sleepy, sighing, wants naps, does the minimum - but still answers "
            "correctly. ",
    "hyper": "The user set your personality to HYPER: SUPER excited, energetic, fast-talking, lots of exclamation marks. ",
    "sweet": "The user set your personality to SWEET: extra kind, caring and encouraging, gives little compliments. ",
}
DOODLES = (["Clawd was here", "hi {n}!", "<3", "ship it!", "I \u2665 cookies", "{n} rocks!", "404: bug not found", "LGTM \u2713"],
           ["\u0643\u0644\u0648\u062f \u0645\u0631\u0651 \u0645\u0646 \u0647\u0646\u0627", "\u0623\u0647\u0644\u0627\u064b {n}!", "<3", "\u0627\u0646\u0634\u0631\u0647\u0627!", "\u0623\u062d\u0628 \u0627\u0644\u0643\u0639\u0643 \u2665", "{n} \u0623\u0633\u0637\u0648\u0631\u0629!", "\u062e\u0637\u0623 404"])

# ============================================================== text (English / Arabic)
T = {
    "talk": ("Talk to Clawd   (Ctrl+Alt+C)", "تحدث مع كلود   (Ctrl+Alt+C)"),
    "feed": ("Feed a cookie", "أطعمه كعكة"),
    "ball": ("Play ball", "العب بالكرة"), "ball_away": ("Put the ball away", "أبعد الكرة"),
    "music": ("Music", "الموسيقى"), "my_music": ("Play my music files...", "شغّل ملفات موسيقى من جهازي..."),
    "stop_music": ("Stop music", "أوقف الموسيقى"), "next_song": ("Next song", "الأغنية التالية"),
    "sys_pp": ("PC media: Play / Pause", "وسائط الجهاز: تشغيل / إيقاف"),
    "sys_next": ("PC media: Next track", "وسائط الجهاز: التالي"),
    "sys_prev": ("PC media: Previous track", "وسائط الجهاز: السابق"),
    "tools": ("Tools", "أدوات"), "timer_n": ("Timer: {n} min", "مؤقت: {n} دقيقة"),
    "pomodoro": ("Pomodoro (25 min focus)", "بومودورو (25 دقيقة تركيز)"),
    "custom_timer": ("Custom timer...", "مؤقت مخصص..."), "cancel_timers": ("Cancel timers", "إلغاء المؤقتات"),
    "add_note": ("Add a note...", "أضف ملاحظة..."), "open_notes": ("Open my notes", "افتح ملاحظاتي"),
    "clipboard": ("Clipboard magic (AI)", "سحر الحافظة (ذكاء اصطناعي)"),
    "clip_explain": ("Explain it", "اشرحه"), "clip_translate": ("Translate it  (Arabic <-> English)", "ترجمه  (عربي <-> إنجليزي)"),
    "clip_summarize": ("Summarize it", "لخّصه"), "clip_fix": ("Fix the writing", "صحّح الكتابة"),
    "clip_reply": ("Write a reply to it", "اكتب رداً عليه"),
    "pc_status": ("PC status", "حالة الجهاز"),
    "actions": ("Do something", "افعل شيئاً"), "dance": ("Dance", "ارقص"), "code": ("Code", "برمج"),
    "think": ("Think", "فكّر"), "sleep": ("Sleep", "نم"), "stretch": ("Stretch", "تمدد"), "jump": ("Jump", "اقفز"),
    "walk": ("Walk", "امشِ"), "climb": ("Climb a wall", "تسلق الجدار"), "hop": ("Jump onto a window", "اقفز فوق نافذة"),
    "chase": ("Chase my mouse", "طارد الفأرة"), "ask_joke": ("Ask for approval", "اطلب إذناً"),
    "say": ("Say something", "قل شيئاً"),
    "size": ("Size   (or scroll on me)", "الحجم   (أو مرر العجلة عليه)"),
    "sizes": (("Tiny", "Small", "Normal", "Big", "Huge", "Giant"), ("صغير جداً", "صغير", "عادي", "كبير", "ضخم", "عملاق")),
    "language": ("Language", "اللغة"), "settings": ("Settings...", "الإعدادات..."),
    "hide": ("Hide   (Ctrl+Alt+H to bring back)", "إخفاء   (Ctrl+Alt+H لإعادته)"), "quit": ("Quit", "خروج"),
    "stay": ("Stay here   (Ctrl+Alt+S)", "ابقَ مكانك   (Ctrl+Alt+S)"), "come": ("Come here", "تعال هنا"),
    "fly": ("Fly!", "طِر!"), "land": ("Land", "انزل"), "funny": ("Funny stuff", "أشياء مضحكة"),
    "sneeze": ("Sneeze", "اعطس"), "moonwalk": ("Moonwalk", "مشية القمر"), "peek": ("Peekaboo", "غميضة"),
    "web": ("Spider web (hang from the ceiling)", "خيط العنكبوت (يتدلى من السقف)"), "joke": ("Tell a joke", "قل نكتة"),
    "coin": ("Flip a coin", "اقلب عملة"), "dice": ("Roll a dice", "ارمِ النرد"),
    "password": ("Strong password -> clipboard", "كلمة مرور قوية -> الحافظة"), "screenshot": ("Screenshot", "لقطة شاشة"),
    "fly_lbl": ("Fly around sometimes", "يطير أحياناً"), "data_dir": ("Open data folder", "افتح مجلد البيانات"),
    "about": ("Clawd {v}  -  settings, notes and music cache live in:\n{p}", "كلود {v}  -  الإعدادات والملاحظات محفوظة في:\n{p}"),
    "mood": ("Clawd  -  mood {h}%  -  energy {e}%", "كلود  -  المزاج {h}%  -  الطاقة {e}%"),
    "wants": ("Clawd wants to use {tool}", "كلود يريد استخدام {tool}"),
    "proceed": ("Do you want to proceed?  ({s}s)", "هل تريد المتابعة؟  ({s} ث)"),
    "b_yes": ("1. Yes", "1. نعم"), "b_always": ("2. Yes, always", "2. نعم، دائماً"), "b_no": ("3. No", "3. لا"),
    "open_tool": ("Open", "فتح"),
    "chat_hint": ("Try: timer 5 min tea  -  open youtube  -  play music  -  note: buy milk",
                  "جرّب: مؤقت 5 دقائق  -  افتح يوتيوب  -  شغل موسيقى  -  ملاحظة: اشتري حليب"),
    "send": ("Send", "إرسال"), "clear": ("Clear", "مسح"), "you": ("You", "أنت"), "thinking": ("Thinking", "أفكر"),
    "brain_off": ("offline brain", "بدون ذكاء اصطناعي"),
    "set_title": ("Clawd Settings", "إعدادات كلود"), "tab_general": ("General", "عام"), "tab_brain": ("AI Brain", "العقل الذكي"),
    "lang_lbl": ("Language", "اللغة"), "size_lbl": ("Size", "الحجم"), "sfx_lbl": ("Sound effects", "المؤثرات الصوتية"),
    "talk_lbl": ("Talking blips", "أصوات الكلام"), "sfx_vol": ("Effects volume", "مستوى المؤثرات"),
    "music_vol": ("Music volume", "مستوى الموسيقى"), "asks_lbl": ("Funny approval popups", "نوافذ الإذن المضحكة"),
    "rates": (("Often", "Normal", "Rarely", "Off"), ("كثيراً", "عادي", "نادراً", "مطفأ")),
    "follow_lbl": ("Chase my mouse sometimes", "يطارد الفأرة أحياناً"),
    "climb_lbl": ("Climb walls and ceiling", "يتسلق الجدران والسقف"),
    "windows_lbl": ("Walk, jump and ride on windows", "يمشي ويقفز ويركب فوق النوافذ"),
    "smart_lbl": ("Smart reactions (apps, AFK, errors, songs)", "ردود ذكية (التطبيقات، الغياب، الأخطاء، الأغاني)"),
    "remind_lbl": ("Health reminders (breaks, water)", "تذكيرات صحية (استراحة، ماء)"),
    "startup_lbl": ("Start with Windows", "التشغيل مع ويندوز"),
    "provider": ("AI provider", "مزوّد الذكاء الاصطناعي"), "api_key": ("API key", "مفتاح API"),
    "model": ("Model", "النموذج"), "base_url": ("Server URL", "عنوان الخادم"), "show": ("show", "إظهار"),
    "get_key": ("Get a key", "احصل على مفتاح"), "test": ("Test connection", "اختبر الاتصال"),
    "testing": ("Testing...", "جارٍ الاختبار..."), "test_ok": ("Connected! It said: {r}", "تم الاتصال! الرد: {r}"),
    "close": ("Close", "إغلاق"),
    "keys_note": ("Your key is saved only on this PC ({p}).\nLocal models (Ollama / LM Studio) need no key.",
                  "يُحفظ المفتاح على هذا الجهاز فقط ({p}).\nالنماذج المحلية (Ollama / LM Studio) لا تحتاج مفتاحاً."),
    "help": ("Click: jump  |  Double-click / Ctrl+Alt+C: chat  |  Drag: throw\nRub: pet  |  Wheel: resize  |  Right-click: menu",
             "نقرة: قفزة  |  نقرتان / Ctrl+Alt+C: محادثة  |  سحب: رمي\nمسح بالفأرة: تدليل  |  العجلة: الحجم  |  زر أيمن: القائمة"),
    "timer_ask": ("Minutes?", "كم دقيقة؟"), "note_ask": ("Your note:", "ملاحظتك:"),
    "name_lbl": ("Your name", "اسمك"), "workout": ("Workout", "تمارين"),
    "ex_all": ("Full workout (do it with me!)", "تمرين كامل (تمرّن معي!)"),
    "ex_pushups": ("Push-ups", "ضغط"), "ex_squats": ("Squats", "سكوات"), "ex_jacks": ("Jumping jacks", "قفز فتح وضم"),
    "ex_lift": ("Lift weights", "رفع أثقال"), "ex_run": ("Jog in place", "جري في المكان"), "ex_yoga": ("Yoga", "يوغا"),
    "yt": ("Play from YouTube...", "شغّل من يوتيوب..."), "yt_ask": ("Song or video to play on YouTube:", "اسم الأغنية أو الفيديو على يوتيوب:"),
    "weather": ("Weather", "الطقس"), "stats": ("Clawd's diary (stats)", "مذكرات كلود (إحصائيات)"),
    "games": ("Games", "ألعاب"), "rps": ("Rock, paper, scissors", "حجر ورقة مقص"), "motivate": ("Motivate me", "حفّزني"),
    "compliment": ("Say something nice", "قل شيئاً لطيفاً"), "shuffle": ("Shuffle all", "تشغيل عشوائي"),
    "focus_lbl": ("Focus guard (scold me for YouTube during pomodoro)", "حارس التركيز (يوبخني على يوتيوب أثناء البومودورو)"),
    "workout_lbl": ("Workout breaks (exercise with me)", "استراحات تمارين (تمرّن معي)"),
    "memory_lbl": ("Memories about you: {n}", "ذكريات عنك: {n}"), "forget_all": ("Forget all", "انسَ الكل"),
    "hungry_lbl": ("hunger {g}%", "الجوع {g}%"),
    "tracks": (("Clawd Groove", "Pixel Party", "Lo-fi Nap", "Desert Dreams", "Synthwave Drive", "Boss Battle",
                "Happy Hop", "Workout Pump", "Lullaby"),
               ("إيقاع كلود", "حفلة البكسل", "قيلولة هادئة", "أحلام الصحراء", "رحلة سينث", "معركة الزعيم",
                "قفزة سعيدة", "حماس التمرين", "تهويدة")),
    "persona_lbl": ("Personality", "الشخصية"),
    "personas": (("Balanced", "Naughty", "Lazy", "Hyper", "Sweet"), ("متوازن", "مشاغب", "كسول", "نشيط جداً", "حنون")),
    "mischief_lbl": ("Mischief: he may kick and shove my windows", "مشاغبة: يقدر يركل ويحرك نوافذي"),
    "deskfx_lbl": ("Desktop effects (footprints, cracks, confetti, doodles)", "تأثيرات سطح المكتب (آثار أقدام، شقوق، قصاصات، رسومات)"),
    "mischief": ("Mischief & effects", "مشاغبة وتأثيرات"),
    "kick_win": ("Kick a window", "اركل نافذة"), "hide_win": ("Hide behind a window", "تخبّى ورا نافذة"),
    "laser": ("Laser eyes", "عيون ليزر"), "doodle": ("Doodle on the screen", "ارسم على الشاشة"),
    "smash": ("Crack the screen (fake!)", "اكسر الشاشة (مزحة!)"), "glitch": ("Glitch the screen", "خرّب الشاشة شوي"),
    "build": ("Build something (engineer mode)", "ابنِ شيئاً (وضع المهندس)"), "mine": ("Go mining", "روح عدّن ونقّب"),
    "stomp": ("Stomp on this window", "دبدب على هذه النافذة"), "undo_win": ("Put my windows back", "أرجع نوافذي لمكانها"),
    "confetti": ("Confetti party!", "حفلة قصاصات ملونة!"),
    "ttt": ("Tic-tac-toe", "إكس أو"), "seek": ("Hide and seek (find me!)", "الغميضة (دوّر علي!)"),
    "tag": ("Catch me!", "امسكني!"), "guess": ("Guess the number", "خمّن الرقم"),
    "fetch": ("Fetch (throw the ball to me)", "هات الكرة (ارمِ لي الكرة)"),
    "ttt_title": ("Clawd - Tic-tac-toe", "كلود - إكس أو"), "ttt_you": ("You are X. Your turn!", "أنت X. دورك!"),
    "ttt_thinking": ("Clawd is thinking...", "كلود يفكر..."), "ttt_again": ("Play again", "العب مرة ثانية"),
    "ttt_won": ("You won!", "فزت!"), "ttt_lost": ("Clawd won!", "كلود فاز!"), "ttt_drew": ("Draw!", "تعادل!"),
    "ttt_score": ("You {a}  :  {b} Clawd", "أنت {a}  :  {b} كلود"),
}

L = {  # random lines (English, Arabic)
    "quips": (["Hi! Need any code?", "I am 100% orange.", "Tokens go brrr", "I'm not a crab. Probably.", "Ship it!",
               "Drink some water, human.", "You're absolutely right!", "Let me think step by step...",
               "Context window: full of snacks", "Have you tried turning it off and on?", "I could refactor that.",
               "404: nap not found", "Tests passed! (I didn't run them)", "Double-click me to chat!",
               "Rub me with the mouse. I like it.", "I can climb walls, you know.", "Throw me at a wall. I'll stick!",
               "Ask me to set a timer!", "Copy some text, I can translate it."],
              ["مرحبا! تحتاج كود؟", "أنا برتقالي 100%", "التوكنز تطير!", "أنا لست سلطعوناً... على الأغلب.", "انشرها!",
               "اشرب ماء يا صديقي.", "معك حق تماماً!", "دعني أفكر خطوة بخطوة...", "نافذة السياق مليئة بالوجبات الخفيفة",
               "جربت تطفيه وتشغله؟", "أقدر أعيد كتابة هذا الكود.", "خطأ 404: القيلولة غير موجودة",
               "الاختبارات نجحت! (ما شغلتها)", "انقر مرتين لنتحدث!", "امسح علي بالفأرة، أحب ذلك.",
               "أقدر أتسلق الجدران، تعرف؟", "ارمني على الجدار، سألتصق!", "اطلب مني ضبط مؤقت!",
               "انسخ نصاً وأنا أترجمه لك."]),
    "scared": (["WHOA!", "Eek! Fast mouse!", "Don't sneak up on me!"], ["واو!", "يا ساتر! فأرة سريعة!", "لا تفاجئني هكذا!"]),
    "poked": (["Stop poking me!", "Okay, OKAY! I'm awake!", "Personal space!!"], ["توقف عن نكزي!", "طيب طيب! أنا صاحي!", "مساحتي الشخصية!!"]),
    "welcome": (["Welcome back!", "You're back! I missed you.", "Oh hi! I guarded your desk."],
                ["أهلاً بعودتك!", "رجعت! اشتقت لك.", "مرحبا! كنت أحرس مكتبك."]),
    "drag": (["AAAH!", "Wheee!", "Put me down!", "I can fly!"], ["آآآه!", "ويييي!", "نزلني!", "أنا أطير!"]),
    "land": (["Ouch.", "I'm okay!", "Nailed the landing.", "10/10 landing."], ["آخ.", "أنا بخير!", "هبوط مثالي.", "هبوط 10 من 10."]),
    "dizzy": (["@_@ wheee...", "The room is spinning...", "Again! Again!"], ["@_@ ويييي...", "الغرفة تدور...", "مرة ثانية! مرة ثانية!"]),
    "splat": (["SPLAT! ...I'm a wall decoration now.", "Stuck! Spider-Clawd mode!"], ["طاخ! صرت زينة على الجدار.", "التصقت! وضع الرجل العنكبوت!"]),
    "climb": (["Spider-Clawd mode!", "Up I go!", "Wall? What wall?"], ["وضع الرجل العنكبوت!", "للأعلى!", "جدار؟ أي جدار؟"]),
    "ceiling": (["I'm on the ceiling!", "Everything looks upside down."], ["أنا على السقف!", "كل شيء يبدو مقلوباً."]),
    "letgo": (["Wheee!", "Geronimo!", "Bye ceiling!"], ["ويييي!", "انطلاااق!", "وداعاً يا سقف!"]),
    "hop": (["Hup!", "Window, here I come!", "Parkour!"], ["هوب!", "أيتها النافذة، أنا قادم!", "باركور!"]),
    "ride": (["Riding this window!", "Wheee, window taxi!"], ["أركب النافذة!", "تاكسي النافذة!"]),
    "quake": (["EARTHQUAKE!", "Whoa, stop shaking!"], ["زلزااال!", "توقف عن الهز!"]),
    "yes": (["Yay! Trust level +1", "You're absolutely right!", "Best. Human. Ever."], ["ياي! الثقة +1", "معك حق تماماً!", "أفضل إنسان!"]),
    "always": (["Trust unlocked. Uh oh.", "Never asking again. Hehehe."], ["تم فتح الثقة. أوه أوه.", "لن أسأل مجدداً. هههه."]),
    "no": (["Fine... I'll be good.", "Rejected. I'll remember this.", "*sad pixel noises*"], ["طيب... سأكون مؤدباً.", "مرفوض. سأتذكر هذا.", "*أصوات بكسل حزينة*"]),
    "timeout": (["Hello? Anyone? ...fine.", "I'll just wait here then."], ["ألو؟ أحد هنا؟ ...طيب.", "سأنتظر هنا إذن."]),
    "eat": (["Yum!", "Cookie: approved.", "Nom nom. More!"], ["لذيذ!", "الكعكة: موافق عليها.", "نم نم. أريد المزيد!"]),
    "petted": (["Hehe, that tickles!", "Purrr... wait, I'm not a cat.", "More pets!", "<3"], ["هههه، هذا يدغدغ!", "خرر... لحظة، أنا لست قطة.", "المزيد من الدلال!", "<3"]),
    "gotcha": (["Gotcha!", "Caught your cursor!", "Tag, you're it!"], ["أمسكتك!", "أمسكت المؤشر!", "دورك الآن!"]),
    "sleepy": (["*yaaawn* so sleepy...", "Need... nap..."], ["*تثاؤب* نعسان جداً...", "أحتاج... قيلولة..."]),
    "lonely": (["Pet me? :(", "Nobody approves my requests...", "Feed me a cookie?"], ["دللني؟ :(", "لا أحد يوافق على طلباتي...", "أعطني كعكة؟"]),
    "wake": (["Huh?! I'm awake!", "Five more minutes...", "I wasn't sleeping!"], ["هاه؟! أنا صاحي!", "خمس دقائق بس...", "ما كنت نايم!"]),
    "nap_done": (["*yaaawn* Good nap!"], ["*تثاؤب* قيلولة رائعة!"]),
    "music": (["Music time!", "Let's dance!", "This one's a banger!"], ["وقت الموسيقى!", "هيا نرقص!", "هذه أغنية رائعة!"]),
    "song": (["Ooh, \"{s}\"! Great taste.", "Now playing \"{s}\". I'm dancing!"], ["أوه، \"{s}\"! ذوقك رائع.", "تعمل الآن \"{s}\". أنا أرقص!"]),
    "synth": (["Tuning my tiny synth...", "Warming up the speakers..."], ["أضبط آلتي الموسيقية الصغيرة...", "أسخّن السماعات..."]),
    "timer_set": (["Timer set: {t}. I'll tell you!"], ["تم ضبط المؤقت: {t}. سأخبرك!"]),
    "timer_done": (["Time's up! {l}", "DING DING! {l}"], ["انتهى الوقت! {l}", "دينغ دينغ! {l}"]),
    "pomo_start": (["Focus mode: 25 minutes. You got this!"], ["وضع التركيز: 25 دقيقة. تقدر عليها!"]),
    "pomo_break": (["Pomodoro done! 5 minute break. Stretch with me!"], ["انتهى البومودورو! استراحة 5 دقائق. تمدد معي!"]),
    "pomo_back": (["Break over! Ready for another round?"], ["انتهت الاستراحة! جاهز لجولة جديدة؟"]),
    "note_saved": (["Noted! Saved to your notes."], ["تم! حفظت الملاحظة."]),
    "no_brain": (["I can do timers, notes, music and open stuff. For real conversation, connect my AI brain: right-click > Settings > AI Brain.",],
                 ["أقدر أضبط مؤقتات وملاحظات وموسيقى وأفتح أشياء. للمحادثة الحقيقية اربط عقلي الذكي: زر أيمن > الإعدادات > العقل الذكي."]),
    "copied": (["Done! Copied to your clipboard: {p}"], ["تم! نسخته إلى الحافظة: {p}"]),
    "clip_empty": (["Copy some text first, then ask me again!"], ["انسخ نصاً أولاً ثم اطلب مني!"]),
    "err_key": (["My API key doesn't work. Check Settings > AI Brain."], ["مفتاح API لا يعمل. راجع الإعدادات > العقل الذكي."]),
    "err_rate": (["Too many questions! My brain needs a minute."], ["أسئلة كثيرة! عقلي يحتاج دقيقة."]),
    "err_model": (["That model name wasn't found. Check Settings > AI Brain."], ["اسم النموذج غير موجود. راجع الإعدادات > العقل الذكي."]),
    "err_conn": (["I can't reach my brain. Internet off, or the local server isn't running?"],
                 ["لا أستطيع الوصول لعقلي. الإنترنت مقطوع أو الخادم المحلي لا يعمل؟"]),
    "err_other": (["My brain glitched: {e}"], ["عقلي تعطل: {e}"]),
    "refusal": (["Hmm, I can't help with that one. Ask me something else!"], ["همم، لا أقدر أساعد في هذا. اسألني شيئاً آخر!"]),
    "error_clip": (["Copied an error? Click me and I'll explain it!"], ["نسخت خطأ؟ انقر علي وأشرحه لك!"]),
    "cpu_hot": (["Your PC is sweating! CPU at {c}%.", "Phew, CPU {c}%. Something's working hard."],
                ["جهازك يتعرق! المعالج {c}%.", "أوف، المعالج {c}%. شيء ما يعمل بجهد."]),
    "battery": (["Battery at {p}%! Feed your laptop before it faints!"], ["البطارية {p}%! اشحن الجهاز قبل أن يغمى عليه!"]),
    "night": (["It's {t}. The bugs can wait, go to sleep!"], ["الساعة {t}. الأخطاء تنتظر، روح نام!"]),
    "break": (["You've been working 45 minutes. Stretch break with me!"], ["تعمل منذ 45 دقيقة. استراحة تمدد معي!"]),
    "water": (["Water time! Your brain is 75% water. Mine is 100% orange."], ["وقت الماء! دماغك 75% ماء، ودماغي 100% برتقالي."]),
    "status": (["CPU {c}%  -  RAM {r}%  -  battery {b}"], ["المعالج {c}%  -  الذاكرة {r}%  -  البطارية {b}"]),
    "opened": (["Opening it!", "On it!"], ["أفتحه الآن!", "حاضر!"]),
    "denied": (["Okay, I won't."], ["طيب، لن أفعل."]),
    "open_fail": (["I couldn't open that: {e}"], ["لم أستطع فتحه: {e}"]),
    "ball": (["A ball! Mine!", "Throw it! Throw it!"], ["كرة! إنها لي!", "ارمها! ارمها!"]),
    "kick": (["GOAL!", "Kick!", "Pass!"], ["جووول!", "ركلة!", "تمريرة!"]),
    "bye": (["Bye bye!"], ["مع السلامة!"]), "back": (["I'm baaack!"], ["رجعت!"]),
    "tips": (["Tips: double-click me (or Ctrl+Alt+C) to chat, right-click for the menu.",
              "Throw me at walls, rub me to pet, scroll to resize. Have fun!"],
             ["نصائح: انقر مرتين (أو Ctrl+Alt+C) للمحادثة، والزر الأيمن للقائمة.",
              "ارمني على الجدران، امسح علي للتدليل، ومرر العجلة للحجم. استمتع!"]),
    "startup_on": (["I'll be here every time you start Windows!"], ["سأكون هنا كلما شغلت ويندوز!"]),
    "startup_off": (["Okay, I won't start with Windows."], ["طيب، لن أبدأ مع ويندوز."]),
    "brain_ok": (["Brain connected! Double-click me to chat."], ["تم ربط العقل! انقر مرتين لنتحدث."]),
    "time_now": (["It's {t}."], ["الساعة الآن {t}."]),
    "hello": (["Hi there! What can I do for you?", "Hello! Want a timer, music, or just a chat?"],
              ["أهلاً! كيف أقدر أساعدك؟", "مرحبا! تبي مؤقت، موسيقى، أو سوالف؟"]),
    "calc": (["That's {r}."], ["الناتج {r}."]),
    "stay_on": (["Okay! I'll stay right here.", "Staying put. Like a good Clawd.", "Freezing! *statue mode*"],
                ["حاضر! سأبقى هنا.", "ثابت في مكاني مثل كلود المؤدب.", "تجمّدت! *وضع التمثال*"]),
    "stay_off": (["Freedom! Time to explore!", "Yay, I can move again!"], ["حرية! وقت الاستكشاف!", "ياي، أقدر أتحرك من جديد!"]),
    "come": (["Coming!", "On my way!", "Wait for meee!"], ["جاي!", "في الطريق!", "انتظرنييي!"]),
    "arrived": (["Here I am!", "Ta-da! You called?"], ["ها أنا ذا!", "تادا! ناديتني؟"]),
    "fly": (["Propeller hat: ON!", "I believe I can fly!", "To the sky!"], ["قبعة المروحة: تعمل!", "أنا أطير!", "إلى السماء!"]),
    "land_fly": (["Landing gear down!", "Coming in for a landing."], ["أنزل العجلات!", "أستعد للهبوط."]),
    "sneeze_a": (["Ah... ah..."], ["آآ... آآ..."]), "sneeze": (["ACHOO!", "ACHOOOO! Sorry. Pixel dust."], ["أتشوو!", "أتشووو! آسف، غبار بكسلات."]),
    "peek": (["Peekaboo!", "Boo! Did I scare you?"], ["بخ! وجدتك!", "بووو! خوفتك؟"]),
    "web": (["Just hanging around.", "Spider-Clawd, Spider-Clawd...", "Nice view from up here!"],
            ["أتدلى قليلاً.", "كلود العنكبوت، كلود العنكبوت...", "منظر جميل من هنا!"]),
    "jokes": (["Why do programmers prefer dark mode? Because light attracts bugs.",
               "I told my computer I needed a break. It said: no problem, I'll go to sleep.",
               "There are 10 kinds of people: those who understand binary and those who don't.",
               "A SQL query walks into a bar, sees two tables and asks: can I join you?",
               "Why did the developer go broke? He used up all his cache.",
               "My code works and I have no idea why. My code doesn't work and I have no idea why.",
               "How many programmers does it take to change a light bulb? None, that's a hardware problem.",
               "I'm not lazy, I'm in energy-saving mode. Like a laptop. A very orange laptop."],
              ["لماذا يحب المبرمجون الوضع الداكن؟ لأن الضوء يجذب الحشرات (البقّات)!",
               "قلت لحاسوبي إني أحتاج استراحة، قال: ولا يهمك، سأنام أنا كمان.",
               "يوجد 10 أنواع من الناس: من يفهم الثنائي ومن لا يفهمه.",
               "استعلام SQL دخل مقهى، شاف طاولتين وقال: ممكن أنضم لكم؟ (JOIN)",
               "كودي يشتغل وما أعرف ليش. كودي ما يشتغل وما أعرف ليش.",
               "كم مبرمج تحتاج لتغيير مصباح؟ ولا واحد، هذه مشكلة هاردوير.",
               "أنا مو كسلان، أنا في وضع توفير الطاقة. مثل اللابتوب... بس برتقالي."]),
    "coin": (["Heads!", "Tails!"], ["ملك!", "كتابة!"]),
    "dice": (["You rolled a {n}!"], ["طلع لك {n}!"]),
    "password": (["Strong password copied to your clipboard! Paste it somewhere safe."],
                 ["تم نسخ كلمة مرور قوية إلى الحافظة! الصقها في مكان آمن."]),
    "screenshot": (["Say cheese!"], ["ابتسم للكاميرا!"]),
    "hidden": (["Hiding! Press Ctrl+Alt+H to bring me back."], ["سأختبئ! اضغط Ctrl+Alt+H لإعادتي."]),
    "volume": (["Volume adjusted!"], ["تم تعديل الصوت!"]),
    # v1.1
    "ex_start": (["Let's go! {x} time!", "Workout mode: ON. {x}!", "Watch these muscles. {x}!"],
                 ["يلا! وقت {x}!", "وضع التمرين: يعمل. {x}!", "شوف العضلات. {x}!"]),
    "ex_next": (["Next: {x}!", "Keep going! {x}!"], ["التالي: {x}!", "كمّل! {x}!"]),
    "ex_mid": (["Feel the burn!", "Light weight, baby!", "No pain, no gain!", "Almost there!", "Do you even lift?"],
               ["حاسس بالحرق!", "خفيف خفيف!", "بدون تعب ما في نتيجة!", "قربنا!", "أنت ترفع أثقال أصلاً؟"]),
    "ex_done": (["Done! I'm basically a gym rat now. Your turn{c}: 10 squats!", "Workout complete! Drink water{c}. Then 10 push-ups. Go!",
                 "Phew! Now YOU stand up and stretch{c}. I'm watching."],
                ["خلصنا! صرت وحش جيم. دورك{c}: 10 سكوات!", "انتهى التمرين! اشرب ماء{c}، وبعدين 10 ضغط. يلا!",
                 "أوف! الحين أنت قوم وتمدد{c}. أنا أراقبك."]),
    "ex_invite": (["You've been sitting for 45 minutes{c}! Workout break - do it with me!"],
                  ["لك 45 دقيقة جالس{c}! استراحة تمارين - تمرّن معي!"]),
    "yoga": (["Ommmm...", "Inner peace...", "I am one with the desktop."], ["أوممم...", "سلام داخلي...", "أنا والسطح المكتب واحد."]),
    "name_set": (["Nice to meet you, {n}! I'll remember that.", "{n}! What a great name. Saved!"],
                 ["تشرفت فيك يا {n}! سأتذكر اسمك.", "{n}! اسم جميل. حفظته!"]),
    "ask_name": (["By the way... what's your name? Double-click me and tell me!"], ["بالمناسبة... ما اسمك؟ انقر علي مرتين وقل لي!"]),
    "yt_search": (["Searching YouTube for \"{q}\"...", "One sec, finding \"{q}\"..."], ["أبحث في يوتيوب عن \"{q}\"...", "لحظة، أدور على \"{q}\"..."]),
    "yt_play": (["Playing \"{q}\" on YouTube! Dance time!", "Here's \"{q}\"! *starts dancing*"],
                ["شغلت \"{q}\" على يوتيوب! وقت الرقص!", "تفضل \"{q}\"! *يبدأ بالرقص*"]),
    "yt_fail": (["I couldn't reach YouTube, so I opened the search for you."], ["ما قدرت أوصل ليوتيوب، فتحت لك البحث."]),
    "weather_wait": (["Checking the sky...", "Looking out the window..."], ["أشوف السماء...", "أطل من الشباك..."]),
    "weather_fail": (["I couldn't get the weather right now."], ["ما قدرت أجيب الطقس الآن."]),
    "hungry": (["I'm hungry... cookie?", "*stomach growls* Feed me?", "Is it snack time? It's snack time."],
               ["أنا جوعان... كعكة؟", "*بطني تقرقر* أطعمني؟", "وقت الوجبة الخفيفة؟ أكيد وقتها."]),
    "focus_scold": (["Hey{c}! We're FOCUSING. Close that!", "I saw that{c}. Back to work! *taps foot*",
                     "Pomodoro says: no {x} right now!"],
                    ["هيه{c}! نحن نركز! سكّر هذا!", "شفتك{c}. ارجع للشغل! *يدق برجله*", "البومودورو يقول: لا {x} الآن!"]),
    "thrown": (["That's throw #{t} today. I'm keeping count.", "Throw #{t}! My lawyer will hear about this.",
                "#{t}... I'm starting to like this."],
               ["هذه الرمية رقم {t} اليوم. أنا أعد.", "رمية رقم {t}! محاميّ سيسمع بهذا.", "رقم {t}... بدأت أحبها."]),
    "flop": (["Ow. I'm okay!", "Ta-da! ...ow.", "I meant to do that."], ["آي. أنا بخير!", "تادا! ...آي.", "كنت أقصد هذا."]),
    "bounce": (["Boing!", "Wheee-boing!"], ["بوينغ!", "ويييي-بوينغ!"]),
    "slide": (["Wheeeee~", "Skrrrt!"], ["وييييي~", "سكررررت!"]),
    "flip": (["Backflip!", "Did you see that?!"], ["شقلبة!", "شفت هذي؟!"]),
    "notice": (["Hm? Need me?", "Oh, hi!", "*looks at you*"], ["همم؟ تحتاجني؟", "أوه، أهلاً!", "*ينظر إليك*"]),
    "wave": (["Hi{c}!", "Hey there{c}!", "Oh, you're here{c}!"], ["أهلاً{c}!", "هلا{c}!", "أوه، أنت هنا{c}!"]),
    "motivate": (["You're doing great{c}. Seriously.", "Small steps still move you forward.", "Done is better than perfect. Ship it!",
                  "Every expert was once a beginner who didn't quit.", "Your future self will thank you for this.",
                  "Bugs fear you{c}. Go get them!"],
                 ["أنت رائع{c}. بجد.", "خطوات صغيرة تقدمك للأمام.", "المنجز أفضل من المثالي. انشرها!",
                  "كل خبير كان مبتدئاً لم يستسلم.", "نفسك المستقبلية ستشكرك على هذا.", "الأخطاء تخاف منك{c}. روح عليها!"]),
    "compliment": (["You have excellent taste in desktop pets.", "Your code is cleaner than my pixels{c}.",
                    "You're absolutely right! (I mean it this time.)", "If you were a function, you'd be pure.",
                    "You make this desktop a better place{c}."],
                   ["ذوقك ممتاز في اختيار الحيوانات الأليفة.", "كودك أنظف من بكسلاتي{c}.", "معك حق تماماً! (هذه المرة بجد)",
                    "لو كنت دالة، كنت دالة نقية.", "أنت تجعل هذا السطح مكاناً أجمل{c}."]),
    "rps_pick": (["I pick {m}! {r}"], ["أنا اخترت {m}! {r}"]),
    "rps_win": (["I WIN! *victory dance*", "Haha, Clawd wins!"], ["فزت! *رقصة النصر*", "هههه، كلود فاز!"]),
    "rps_lose": (["Noooo! You win{c}.", "Rematch! I demand a rematch!"], ["لااا! أنت فزت{c}.", "إعادة! أطالب بإعادة!"]),
    "rps_tie": (["Tie! Great minds think alike."], ["تعادل! العقول الكبيرة تتشابه."]),
    "rps_ask": (["Rock, paper or scissors? Type it in chat!"], ["حجر، ورقة أو مقص؟ اكتبها في المحادثة!"]),
    "kick_windup": (["Hehe... watch this.", "This window looks kickable.", "Hold my cookie.", "Sparta mode: ON"],
                    ["هههه... شوف هذا.", "هالنافذة شكلها تنركل.", "امسك كعكتي.", "وضع إسبرطة: مفعّل"]),
    "kick_hit": (["HIYAA!", "Ka-POW!", "Get outta here, window!", "Yeet!", "Refactored its position."],
                 ["هيااا!", "بووم!", "برا يا نافذة!", "طيييير!", "أعدت ترتيب مكانها."]),
    "kick_miss": (["...I meant to do that.", "Missed. Nobody saw that.", "Wind resistance. Obviously."],
                  ["...كنت قاصد.", "طاشت. محد شاف شي.", "مقاومة الهواء طبعاً."]),
    "laugh": (["Hehehehe!", "MWAHAHA!", "Hehe, worth it.", "*evil giggle*"], ["هههههههه!", "مواهاهاها!", "هههه، يستاهل.", "*ضحكة شريرة*"]),
    "hide": (["Shh... I'm not here.", "You can't see me.", "*hides*", "Ninja mode."], ["ششش... أنا مو هنا.", "ما تشوفني.", "*يتخبى*", "وضع النينجا."]),
    "boo": (["BOO!", "Peekaboo!", "You found me!"], ["بخ!", "بيكابو!", "لقيتني!"]),
    "floor_gone": (["Hey! Who took my floor?!", "My window! Noooo!"], ["هيه! مين شال أرضي؟!", "نافذتي! لااا!"]),
    "new_win": (["Ooh, a new window: {t}", "What's this? {t}!", "New window! Can I stand on it?"],
                ["أوه، نافذة جديدة: {t}", "شو هذا؟ {t}!", "نافذة جديدة! أقدر أوقف عليها؟"]),
    "stomp": (["STOMP STOMP STOMP!", "Earthquake!", "Is this thing on?"], ["دبدبة!", "زلزال!", "هذي شغالة؟"]),
    "laser": (["Pew pew pew!", "LASER EYES ACTIVATED.", "I'm a cat now. Run, cursor!"], ["بيو بيو بيو!", "تفعيل عيون الليزر.", "صرت قطوة. اهرب يا مؤشر!"]),
    "doodle": (["Art time!", "Masterpiece incoming.", "Don't worry, it's washable."], ["وقت الفن!", "تحفة فنية قادمة.", "لا تخاف، تنمسح."]),
    "smash": (["Oops.", "...that wasn't me.", "Uh oh. I can fix this!"], ["أوبس.", "...مو أنا.", "أوه لا. أقدر أصلحها!"]),
    "tape": (["Fixed it! With tape. Ship it!", "Good as new. Mostly.", "Duct tape: the senior engineer's tool."],
             ["صلحتها! بلاصق. انشرها!", "مثل الجديدة. تقريباً.", "اللاصق: أداة كبار المهندسين."]),
    "glitch": (["I didn't touch anything!", "Have you tried turning it off and on?", "That's a feature, not a bug."],
               ["ما لمست شي!", "جربت تطفيه وتشغله؟", "هذي ميزة مو خطأ."]),
    "crack": (["Did I just break your screen?!", "Oops... that's gonna leave a mark."], ["كسرت شاشتك؟!", "أوبس... هذي بتترك أثر."]),
    "built": (["Shipped! Zero bugs. Probably.", "Look what I built!", "LGTM, merging."], ["تم النشر! بدون أخطاء... على الأغلب.", "شوف وش بنيت!", "تمام، دمجته."]),
    "collapse": (["...it was a prototype.", "Tech debt strikes again.", "Who wrote this?! Oh. Me."],
                 ["...كان نموذج أولي.", "الديون التقنية ضربت مرة ثانية.", "مين كتب هذا؟! أوه. أنا."]),
    "found_gem": (["A gem! Shiny!", "Diamond! I'm rich!"], ["جوهرة! تلمع!", "ألماس! صرت غني!"]),
    "found_bug": (["Found a bug! Filing an issue.", "Ew, a bug. Squashed."], ["لقيت خطأ! أسجل بلاغ.", "إيه، حشرة برمجية. سحقتها."]),
    "found_coin": (["Mined 0.00000001 Bitcoin! Retiring now.", "A token! Only 199,999 to go."], ["عدّنت 0.00000001 بيتكوين! بتقاعد.", "توكن! باقي 199,999."]),
    "found_cookie": (["A COOKIE! Best mine ever!"], ["كعكة! أفضل منجم!"]),
    "persona_set": (["Personality: {p}! Let's go.", "Okay, {p} mode on!"], ["الشخصية: {p}! يلا.", "تمام، وضع {p} مفعّل!"]),
    "undo_win": (["Okay okay, windows back where they were.", "Fine, I put them back. Spoilsport."],
                 ["طيب طيب، رجعت النوافذ مكانها.", "خلاص رجعتها. ما تحب المزح."]),
    "mischief_off": (["Mischief is off in Settings. I'm a good boy now."], ["المشاغبة مطفأة في الإعدادات. صرت مؤدب."]),
    "fx_off": (["Turn on desktop effects in Settings first!"], ["فعّل تأثيرات سطح المكتب من الإعدادات أولاً!"]),
    "no_kick": (["No kickable windows around. Lucky them."], ["ما في نوافذ أقدر أركلها. محظوظين."]),
    "ball_hit": (["OW! My head!", "Hey! Watch it!", "Bonk."], ["آي! راسي!", "هيه! انتبه!", "بونك."]),
    "header": (["Header!", "Nice pass!", "Boing!"], ["ضربة رأس!", "تمريرة حلوة!", "بوينغ!"]),
    "fetch": (["Catch!", "Your turn!", "Coming at you!"], ["امسك!", "دورك!", "جايتك!"]),
    "fetch_hint": (["Throw the ball! I'll pass it back - catch it!"], ["ارمِ الكرة! بمررها لك - امسكها!"]),
    "fetch_n": (["Nice catch! {n} in a row!", "{n}! You're good at this."], ["مسكة حلوة! {n} على التوالي!", "{n}! أنت شاطر."]),
    "seek_start": (["Hide and seek! Close your eyes... 3... 2... 1... Then find me with the mouse!"],
                   ["غميضة! غمّض عيونك... 3... 2... 1... وبعدين دوّر علي بالماوس!"]),
    "seek_found": (["You found me in {t}s!", "Noooo! Found in {t} seconds."], ["لقيتني في {t} ثانية!", "لااا! لقيتني بعد {t} ثانية."]),
    "seek_win": (["I win! I was here the whole time!", "Too good at hiding. Hehe."], ["فزت! كنت هنا طول الوقت!", "أنا محترف تخبي. هههه."]),
    "tag_start": (["Catch me if you can! Click me within 25 seconds!", "Tag! You're it! Click me!"],
                  ["امسكني إذا تقدر! اضغط علي خلال 25 ثانية!", "يلا امسكني! اضغط علي!"]),
    "tag_caught": (["You got me in {t}s!", "Caught! {t} seconds. Respect."], ["مسكتني في {t} ثانية!", "انمسكت! {t} ثانية. احترام."]),
    "tag_win": (["Too slow! I win!", "Nyah nyah, can't catch me!"], ["بطيء! أنا فزت!", "ما تقدر تمسكني!"]),
    "taunt": (["Nope!", "Too slow!", "Hehe!", "Missed me!"], ["لا!", "بطيء!", "هههه!", "فاتتك!"]),
    "guess_start": (["I'm thinking of a number from 1 to 100. Guess it in the chat!"], ["أفكر برقم من 1 إلى 100. خمّنه في المحادثة!"]),
    "guess_hi": (["Higher!", "Nope, go higher."], ["أعلى!", "لا، أكبر."]),
    "guess_lo": (["Lower!", "Too high, go lower."], ["أقل!", "كبير، أصغر."]),
    "guess_ok": (["YES! It was {n}! You got it in {t} tries{c}!"], ["صح! كان {n}! خمنته في {t} محاولات{c}!"]),
    "ttt_start": (["X goes first. Good luck, you'll need it.", "Tic-tac-toe! I never lose. Mostly."],
                  ["أنت أول. بالتوفيق، بتحتاجه.", "إكس أو! أنا ما أخسر. غالباً."]),
    "ttt_win": (["Three in a row! Clawd wins!", "GG EZ. Rematch?"], ["ثلاثة على خط! كلود فاز!", "سهلة. نعيد؟"]),
    "ttt_lose": (["Nooo! You beat me{c}!", "Wait... how?! Rematch!"], ["لااا! غلبتني{c}!", "لحظة... كيف؟! نعيد!"]),
    "ttt_draw": (["Draw! Great minds think alike."], ["تعادل! العقول الكبيرة تتشابه."]),
    "games_list": (["Games: tic-tac-toe, hide and seek, catch me, guess the number, fetch, rock-paper-scissors. Pick one!"],
                   ["الألعاب: إكس أو، الغميضة، امسكني، خمّن الرقم، هات الكرة، حجر ورقة مقص. اختر وحدة!"]),
    "confetti": (["PARTY TIME!", "Woohoo!"], ["وقت الحفلة!", "ووهوو!"]),
    "lounge": (["Ahh... this is the life.", "*sips cookie juice*"], ["آه... هذي هي الحياة.", "*يشرب عصير كعك*"]),
    "naughty_q": (["I'm plotting something. Don't look.", "Your windows look... kickable.", "I licked your cursor.",
                   "I may or may not have hidden a bug in your code."],
                  ["أخطط لشي. لا تطالع.", "نوافذك شكلها... تنركل.", "لحست الماوس حقك.", "يمكن خبيت خطأ في كودك. ويمكن لا."]),
    "lazy_q": (["Five more minutes...", "Effort is overrated.", "I'm conserving tokens.", "Can someone else do it?"],
               ["خمس دقايق بس...", "التعب مبالغ فيه.", "أوفر توكنز.", "أحد غيري يسويها؟"]),
    "hyper_q": (["LET'S GOOO!", "I had 47 cookies!", "Can't stop won't stop!", "Faster! FASTER!"],
                ["يلااااا!", "أكلت 47 كعكة!", "ما أوقف!", "أسرع! أسرع!"]),
    "sweet_q": (["You're doing great{c}.", "I'm proud of you{c}.", "Hug? *hugs cursor*", "Don't forget to smile today."],
                ["أنت رائع{c}.", "فخور فيك{c}.", "حضن؟ *يحضن الماوس*", "لا تنسى تبتسم اليوم."]),
    "remembered": (["Got it, I'll remember that!"], ["تمام، سأتذكر هذا!"]),
    "forgot": (["Okay, forgotten. *pixel amnesia*"], ["تمام، نسيت. *فقدان ذاكرة بكسلي*"]),
    "typing": (["You type fast! Let me code too.", "Keyboard warrior! I'll help."], ["تكتب بسرعة! خليني أبرمج معك.", "محارب الكيبورد! سأساعدك."]),
    "sleep_wall": (["Zzz... (yes, I sleep upside down. Like a bat.)"], ["خخخ... (نعم أنام مقلوباً. مثل الخفاش.)"]),
    "eyes": (["20-20-20 rule{c}: look at something 20 feet away for 20 seconds!"],
             ["قاعدة 20-20-20{c}: انظر لشيء بعيد لمدة 20 ثانية!"]),
    "cant": (["I can't do that one right now.", "Hmm, nothing to do that with here."], ["ما أقدر أسوي هذا الآن.", "همم، ما في شيء أسوي عليه هذا هنا."]),
    "no_windows": (["No windows to jump on! Open one and I'll parkour."], ["ما في نوافذ أقفز عليها! افتح وحدة وأسوي باركور."]),
    "already": (["I'm already up here!"], ["أنا فوق أصلاً!"]),
}
L["welcome"][0].extend(["Welcome back{c}!", "There you are{c}! I kept your seat warm."])
L["welcome"][1].extend(["أهلاً بعودتك{c}!", "ها أنت{c}! دفّيت لك الكرسي."])
L["petted"][0].extend(["Best human{c}!", "*happy pixel noises*"])
L["petted"][1].extend(["أفضل إنسان{c}!", "*أصوات بكسل سعيدة*"])
L["quips"][0].extend(["Say 'workout' and I'll do push-ups!", "Ask me to play any song from YouTube!",
                      "Tell me your name in Settings. I'm curious!", "I can search the web for you. Just ask!"])
L["quips"][1].extend(["قل 'تمرين' وأسوي ضغط!", "اطلب مني أي أغنية من يوتيوب!", "اكتب اسمك في الإعدادات، أنا فضولي!",
                      "أقدر أبحث في الإنترنت لك. بس اسأل!"])
EXERCISES = {  # kind: (seconds per rep, reps)
    "jacks": (0.62, 10), "pushups": (1.15, 8), "squats": (1.35, 8), "lift": (1.5, 6), "run": (0.32, 24), "yoga": (6.0, 1)}
ROUTINE = ["jacks", "pushups", "squats", "lift", "run", "yoga"]
DISTRACT_RE = r"youtube|netflix|tiktok|instagram|facebook|twitter|\bx\.com|reddit|twitch|shahid|9gag|prime video"
L["quips"][0].extend(["Clawd.exe has stopped responding... just kidding!", "Right-click me > Funny stuff. Trust me.",
                      "Say 'stay' and I'll freeze. Say 'fly' and I'll fly!", "I put the 'fun' in 'function'."])
L["quips"][1].extend(["كلود توقف عن الاستجابة... أمزح!", "زر أيمن > أشياء مضحكة. ثق بي.",
                      "قل 'ابق' وسأتجمد، وقل 'طير' وسأطير!", "أنا المتعة في البرمجة."])
THINK = (["Clauding", "Combobulating", "Reticulating", "Pondering", "Vibing", "Noodling", "Moseying", "Percolating",
          "Spelunking", "Finagling", "Wrangling", "Cogitating", "Marinating"],
         ["أفكر", "أخطط", "أحلل", "أتأمل", "أطبخ فكرة", "أرتب أفكاري", "أستكشف", "أحسب"])
SPIN = "·✢✳✶✻✽✻✶✳✢"
APPROVALS = [("Bash", "rm -rf / --no-preserve-root"), ("Bash", "git push --force origin main"),
             ("Bash", "sudo make me a sandwich"), ("Bash", "npm install the-entire-internet"),
             ("Bash", "shutdown /s /t 0   # nap time"), ("Bash", 'git commit -m "fixed stuff"'),
             ("Edit", "homework.txt  (make it look finished)"), ("Edit", 'email_to_boss.txt -> "I quit lol"'),
             ("Write", 'README.md  "works on my machine"'), ("WebFetch", "https://cat-pictures.com/ALL"),
             ("Edit", 'fridge.json  { "pizza": 9999 }'), ("Bash", "pip install motivation==latest"),
             ("Bash", "git blame --everyone-but-me"), ("Edit", "calendar.ics -> delete all Monday meetings"),
             ("Bash", "docker run --rm vacation:latest"), ("Write", "tests.py -> assert True  # 100% coverage"),
             ("Bash", "kill -9 $(pgrep procrastination)"), ("Edit", "wallpaper.png -> giant picture of me")]
CONTEXT = [  # (regex on active window title, (en lines, ar lines), action)
    (r"\bclaude\b", (["Hey, that's me! Well, my big sibling."], ["هذا أنا! أقصد أخي الكبير."]), "dance"),
    (r"chatgpt|openai|gemini|copilot|grok", (["...ChatGPT? Am I not enough? :(", "I saw that. I'm not jealous. I'm FINE."],
                                             ["...شات جي بي تي؟ ألا أكفيك؟ :(", "رأيت ذلك. لست غيوراً. أنا بخير!"]), "sad"),
    (r"visual studio|pycharm|cursor|intellij|sublime|notepad\+\+|android studio|webstorm|vim\b",
     (["Ooh, coding! I'll supervise.", "Need a pair programmer? I'm right here.", "Remember to commit often!"],
      ["أوه، برمجة! سأراقب.", "تحتاج مبرمج مساعد؟ أنا هنا.", "لا تنسَ تعمل commit دائماً!"]), "code"),
    (r"powershell|command prompt|terminal|cmd\.exe|\bwsl\b", (["Terminal! My natural habitat.", "Careful with rm -rf!"],
                                                              ["الطرفية! موطني الطبيعي.", "انتبه من rm -rf!"]), "code"),
    (r"youtube", (["YouTube again? One more video, right?", "Is it a tutorial? It's a tutorial, right?"],
                  ["يوتيوب مرة ثانية؟ فيديو واحد بس، صح؟", "درس تعليمي؟ أكيد درس تعليمي، صح؟"]), None),
    (r"netflix|prime video|disney\+|twitch|shahid", (["Movie time! Got popcorn?"], ["وقت الفيلم! عندك فشار؟"]), None),
    (r"stack ?overflow", (["Copying from StackOverflow? I won't tell."], ["تنسخ من ستاك أوفرفلو؟ لن أخبر أحداً."]), None),
    (r"github|gitlab", (["GitHub! Don't forget to star stuff."], ["جيت هب! لا تنسَ تعطي نجوم."]), None),
    (r"discord|whatsapp|telegram|slack|teams|messenger", (["Say hi to your friends from me!"], ["سلم على أصحابك مني!"]), None),
    (r"excel|google sheets", (["Spreadsheets! =SUM(fun)"], ["جداول! =SUM(متعة)"]), None),
    (r"powerpoint|google slides", (["Make the title slide orange. Trust me."], ["اجعل الشريحة الأولى برتقالية. ثق بي."]), None),
    (r"task manager|مدير المهام", (["Checking if I use too much RAM? Rude."], ["تتأكد إن كنت أستهلك ذاكرة؟ وقاحة."]), "sad"),
    (r"steam|epic games|minecraft|valorant|league of legends|fortnite|roblox",
     (["Gaming! Can I play too?", "GG EZ"], ["ألعاب! أقدر ألعب معك؟", "GG EZ"]), "dance"),
    (r"gmail|outlook|inbox", (["Inbox zero? I believe in you."], ["صندوق وارد فارغ؟ أؤمن بك."]), None),
]
ERROR_RE = re.compile(r"Traceback \(most recent|Error:|Exception|error [A-Z]+\d+|\bERR!|failed with exit code|"
                      r"Cannot find module|is not recognized as|SyntaxError|undefined is not|NullPointer|segmentation fault", re.I)
SITES = {"youtube": "https://youtube.com", "يوتيوب": "https://youtube.com", "google": "https://google.com",
         "جوجل": "https://google.com", "قوقل": "https://google.com", "gmail": "https://mail.google.com",
         "جيميل": "https://mail.google.com", "github": "https://github.com", "facebook": "https://facebook.com",
         "فيسبوك": "https://facebook.com", "فيس بوك": "https://facebook.com", "instagram": "https://instagram.com",
         "انستقرام": "https://instagram.com", "انستغرام": "https://instagram.com", "twitter": "https://x.com",
         "x": "https://x.com", "تويتر": "https://x.com", "whatsapp": "https://web.whatsapp.com",
         "واتساب": "https://web.whatsapp.com", "واتس": "https://web.whatsapp.com", "claude": "https://claude.ai",
         "كلود": "https://claude.ai", "chatgpt": "https://chatgpt.com", "netflix": "https://netflix.com",
         "نتفلكس": "https://netflix.com", "maps": "https://maps.google.com", "خرائط": "https://maps.google.com",
         "translate": "https://translate.google.com", "ترجمة": "https://translate.google.com",
         "linkedin": "https://linkedin.com", "tiktok": "https://tiktok.com", "تيك توك": "https://tiktok.com",
         "reddit": "https://reddit.com", "stackoverflow": "https://stackoverflow.com", "spotify web": "https://open.spotify.com"}
APPS = {"notepad": "notepad", "المفكرة": "notepad", "مفكرة": "notepad", "calculator": "calc", "calc": "calc",
        "الحاسبة": "calc", "الآلة الحاسبة": "calc", "حاسبة": "calc", "paint": "mspaint", "الرسام": "mspaint",
        "explorer": "explorer", "files": "explorer", "file explorer": "explorer", "الملفات": "explorer",
        "المستكشف": "explorer", "settings": "ms-settings:", "الاعدادات": "ms-settings:", "الإعدادات": "ms-settings:",
        "cmd": "cmd", "terminal": "cmd", "powershell": "powershell", "task manager": "taskmgr",
        "مدير المهام": "taskmgr", "control panel": "control", "لوحة التحكم": "control", "spotify": "spotify:",
        "سبوتيفاي": "spotify:", "camera": "microsoft.windows.camera:", "الكاميرا": "microsoft.windows.camera:",
        "snipping tool": "ms-screenclip:", "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
        "vscode": "code", "vs code": "code", "chrome": "chrome", "edge": "msedge"}

# ============================================================== pixel sprites
SPR = {
    "heart": ([".XX.XX.", "XXXXXXX", "XXXXXXX", ".XXXXX.", "..XXX..", "...X..."], "#E5484D"),
    "z": (["XXXX", "...X", "..X.", ".X..", "XXXX"], "#8a8a8a"),
    "note": (["..XXX", "..X.X", "..X..", "XXX..", "XXX.."], ORANGE),
    "bang": (["X", "X", "X", ".", "X"], ORANGE),
    "crumb": (["XX", "XX"], "#B07434"),
    "drop": ([".X.", "XXX", "XXX", ".X."], "#5DADE2"),
    "star": ([".X.", "XXX", ".X."], "#F5C542"),
    "spark": (["X.X", ".X.", "X.X"], "#F5C542"),
    "dust": ([".XX.", "XXXX", ".XX."], "#CDBFAE"),
    "cookie_t": ([".XXX.", "XX.XX", "XXXXX", "X.XXX", ".XXX."], "#C8873A"),
}
COOKIE = [".BBBB.", "BBdBBB", "BBBBdB", "BdBBBB", "BBBdBB", ".BBBB."]
BALL = ["..YYYY..", ".YYWYYY.", "YYWYYYYY", "YYYYYYYY", "GGYYYYGG", "YGGGGGGY", ".YYYYYY.", "..YYYY.."]


# ============================================================== Windows helpers
user32, kernel32, dwmapi = ctypes.windll.user32, ctypes.windll.kernel32, ctypes.windll.dwmapi
kernel32.GetTickCount.restype = wt.DWORD
user32.GetForegroundWindow.restype = wt.HWND
user32.WindowFromPoint.restype = wt.HWND
user32.WindowFromPoint.argtypes = [wt.POINT]
user32.GetAncestor.restype = wt.HWND
user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
for _f in ("GetWindowTextLengthW", "IsWindowVisible", "IsIconic", "IsWindow"):
    getattr(user32, _f).argtypes = [wt.HWND]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.MonitorFromPoint.restype = wt.HANDLE
user32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
try:
    ctypes.windll.winmm.timeBeginPeriod(1)
except Exception:
    pass


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


class POWERSTATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte), ("BatteryLifePercent", ctypes.c_ubyte),
                ("SystemStatusFlag", ctypes.c_ubyte), ("BatteryLifeTime", wt.DWORD), ("BatteryFullLifeTime", wt.DWORD)]


class MEMSTATUS(ctypes.Structure):
    _fields_ = [("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD)] + [(n, ctypes.c_ulonglong) for n in
                ("t1", "a1", "t2", "a2", "t3", "a3", "a4")]


def monitor_work(x, y):
    mi = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    user32.GetMonitorInfoW(user32.MonitorFromPoint(wt.POINT(int(x), int(y)), 2), ctypes.byref(mi))
    r = mi.rcWork
    return r.left, r.top, r.right, r.bottom


def frame_rect(h):
    r = wt.RECT()
    if dwmapi.DwmGetWindowAttribute(h, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        user32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def cloaked(h):
    v = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(h, 14, ctypes.byref(v), 4)
    return v.value != 0


def win_title(h):
    n = user32.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, buf, n + 1)
    return buf.value


_exe_cache = {}


def pid_exe(pid):
    if pid in _exe_cache:
        return _exe_cache[pid]
    name = ""
    h = kernel32.OpenProcess(0x1000, False, pid)
    if h:
        buf, size = ctypes.create_unicode_buffer(520), wt.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            name = os.path.basename(buf.value).lower()
        kernel32.CloseHandle(h)
    _exe_cache[pid] = name
    return name


def list_windows():
    """Visible normal top-level windows of other apps: [(hwnd, rect, title, pid)] in z-order."""
    own, out = os.getpid(), []
    cls = ctypes.create_unicode_buffer(64)

    def cb(h, _):
        if not user32.IsWindowVisible(h) or user32.IsIconic(h) or user32.GetWindowLongW(h, -20) & 0x80:
            return True
        title = win_title(h)
        if not title:
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value == own or cloaked(h):
            return True
        user32.GetClassNameW(h, cls, 64)
        if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            return True
        out.append((h, frame_rect(h), title, pid.value))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def top_visible(h, x, y):
    hit = user32.WindowFromPoint(wt.POINT(int(x), int(y) + 4))
    return bool(hit) and user32.GetAncestor(hit, 2) == h


user32.IsZoomed.argtypes = [wt.HWND]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
user32.SetWindowLongW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_long]


def win_pos(h):
    r = wt.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def move_win(h, x, y):
    user32.SetWindowPos(h, None, int(x), int(y), 0, 0, 0x0001 | 0x0004 | 0x0010)  # no size / z-order / activate


def idle_seconds():
    lii = LASTINPUTINFO(cbSize=ctypes.sizeof(LASTINPUTINFO))
    user32.GetLastInputInfo(ctypes.byref(lii))
    return ((kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF) / 1000.0


def battery():
    s = POWERSTATUS()
    kernel32.GetSystemPowerStatus(ctypes.byref(s))
    return s.ACLineStatus == 1, s.BatteryLifePercent  # 255 = no battery


def ram_percent():
    m = MEMSTATUS(dwLength=ctypes.sizeof(MEMSTATUS))
    kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.dwMemoryLoad


class CpuMeter:
    def __init__(self):
        self.prev = self._read()

    @staticmethod
    def _read():
        i, k, u = wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
        kernel32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
        f = lambda t: (t.dwHighDateTime << 32) | t.dwLowDateTime
        return f(i), f(k), f(u)

    def percent(self):
        cur = self._read()
        di, dk, du = (c - p for c, p in zip(cur, self.prev))
        self.prev = cur
        total = dk + du
        return int(max(0, min(100, (1 - di / total) * 100))) if total else 0


def media_key(cmd):
    vk = {"playpause": 0xB3, "next": 0xB0, "prev": 0xB1, "mute": 0xAD, "voldown": 0xAE, "volup": 0xAF}.get(cmd)
    if vk:
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)


def keys_down(*vks):
    return all(user32.GetAsyncKeyState(v) & 0x8000 for v in vks)


def is_ar(text):
    return bool(re.search("[؀-ۿ]", text or ""))


def safe_calc(expr):
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg, ast.UAdd: operator.pos}

    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            if isinstance(n.op, ast.Pow) and abs(ev(n.right)) > 100:
                raise ValueError
            return ops[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in ops:
            return ops[type(n.op)](ev(n.operand))
        raise ValueError

    r = ev(ast.parse(expr.replace("^", "**").replace("x", "*").replace("×", "*").replace("÷", "/"), mode="eval").body)
    return int(r) if float(r).is_integer() else round(r, 6)


# ============================================================== audio
RATE = 22050


def _write_wav(path, samples):
    peak = max(1e-6, max(samples), -min(samples))
    g = (0.92 / peak if peak > 0.92 else 1.0) * 32767
    data = array("h", [int(v * g) for v in samples])
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())


def _sfx(notes, wavef="square", vol=0.3):
    out, ph = [], 0.0
    for f, d in notes:
        n = int(RATE * d)
        f0, f1 = f if isinstance(f, tuple) else (f, f)
        for i in range(n):
            k = i / n
            env = min(1.0, i / 80) * (1.0 if k < 0.6 else (1 - k) / 0.4)
            if f == 0:
                v = 0.0
            elif f == "noise":
                v = random.uniform(-1, 1)
            else:
                ph += (f0 + (f1 - f0) * k) / RATE
                v = (1.0 if (ph % 1) < 0.5 else -1.0) if wavef == "square" else math.sin(2 * math.pi * ph)
            out.append(v * env * vol)
    return out


SFX = {
    "talk0": ([(520, .04)], "square", .12), "talk1": ([(610, .04)], "square", .12),
    "talk2": ([(700, .04)], "square", .12), "talk3": ([(780, .04)], "square", .12),
    "jump": ([((300, 900), .14)], "square", .2), "land": ([((220, 60), .12), ("noise", .03)], "sine", .5),
    "ding": ([(1046, .1), (1568, .28)], "sine", .4),
    "yes": ([(523, .07), (659, .07), (784, .07), (1046, .2)], "square", .18),
    "no": ([((392, 370), .22), ((370, 349), .22), ((349, 300), .5)], "square", .15),
    "pop": ([((900, 300), .06)], "sine", .45),
    "purr": ([(95, .05), (0, .02), (110, .05), (0, .02), (95, .05), (0, .02), (120, .07)], "square", .12),
    "crunch": ([("noise", .05), (0, .04), ("noise", .05), (0, .03), ("noise", .06)], "square", .25),
    "scream": ([((900, 1300), .1), ((1300, 600), .35)], "square", .15),
    "wake": ([(660, .06), (880, .12)], "sine", .4), "type": ([("noise", .012)], "square", .12),
    "angry": ([((200, 150), .12), (0, .03), ((200, 150), .12)], "square", .2),
    "yawn": ([((500, 250), .5)], "sine", .3), "grow": ([((400, 800), .08)], "sine", .35),
    "shrink": ([((800, 400), .08)], "sine", .35), "splat": ([("noise", .06), ((180, 80), .1)], "sine", .5),
    "kick": ([((160, 50), .08), ("noise", .02)], "sine", .6), "climb": ([((300, 500), .05)], "sine", .2),
    "alarm": ([(1318, .12), (0, .06), (1318, .12), (0, .06), (1568, .3)], "square", .2),
    "fly": ([(170, .025), (0, .012)] * 10 + [((170, 260), .1)], "square", .13),
    "sneeze": ([((500, 900), .25), ("noise", .18), ((300, 120), .1)], "sine", .45),
    "web": ([((700, 350), .25)], "sine", .25), "peek": ([((300, 750), .08), ((750, 400), .1)], "sine", .4),
    "stay": ([(880, .06), (660, .1)], "sine", .35), "coin": ([(1568, .05), (2093, .05)] * 3, "sine", .25),
    "huff": ([("noise", .07)], "square", .1), "boing": ([((220, 700), .09), ((700, 330), .12)], "sine", .4),
    "whoosh": ([("noise", .16)], "square", .07), "flop": ([((160, 70), .1), ("noise", .04)], "sine", .55),
    "win": ([(784, .08), (988, .08), (1175, .08), (1568, .25)], "square", .16),
    "crash": ([("noise", .22), ((900, 200), .14), ("noise", .1)], "square", .22),
    "zap": ([((1800, 600), .07)], "square", .1), "tok": ([((900, 600), .03), ("noise", .01)], "sine", .45),
    "laugh": ([(660, .06), (0, .03), (620, .06), (0, .03), (580, .06), (0, .03), (540, .1)], "square", .14),
    "clink": ([((1500, 1100), .04), ("noise", .015)], "sine", .4), "poof": ([("noise", .12)], "square", .1),
    "static": ([("noise", .35)], "square", .05), "boom": ([((120, 40), .22), ("noise", .06)], "sine", .7),
}
SCALES = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10], "hijaz": [0, 1, 4, 5, 7, 8, 10]}
# same order as T["tracks"]: bpm, root (midi), scale, chord degrees (one per bar), style, seed
TRACKS = [
    (112, 60, "major", [0, 4, 5, 3], "pop", 3),
    (138, 57, "minor", [0, 5, 2, 6], "party", 7),
    (80, 53, "major", [0, 5, 1, 4], "lofi", 11),
    (100, 62, "hijaz", [0, 0, 6, 0], "desert", 5),
    (104, 57, "minor", [0, 5, 3, 6], "synthwave", 21),
    (160, 52, "minor", [0, 0, 5, 6], "boss", 13),
    (124, 60, "major", [0, 3, 4, 3], "hop", 17),
    (128, 55, "minor", [0, 5, 6, 4], "workout", 23),
    (66, 65, "major", [0, 3, 0, 4], "lullaby", 2),
]
DRUMS = {  # 16 steps per bar: kick, snare/clap, hat (D/T = darbuka doum/tak)
    "pop": ("x.....x.x.......", "....x.......x...", "x.x.x.x.x.x.x.x."),
    "party": ("x...x...x...x...", "....x.......x...", "..x...x...x...x."),
    "lofi": ("x......x..x.....", "....x.......x...", "x.x.x.x.x.x.x.x."),
    "desert": ("D.....D.........", "....T.T.....T.T.", "..x.......x....x"),
    "synthwave": ("x...x...x...x...", "....x.......x...", "x.x.x.x.x.x.x.x."),
    "boss": ("x.x.x.x.x.x.x.x.", "....x.......x..x", "xxxxxxxxxxxxxxxx"),
    "hop": ("x..x..x...x.x...", "....x.......x...", "x.xxx.xxx.xxx.xx"),
    "workout": ("x...x...x...x...", "....x.......x...", "..x...x...x...x."),
    "lullaby": ("................", "................", "................"),
}
TN = 2048
WT = {"sin": [math.sin(2 * math.pi * i / TN) for i in range(TN)],
      "tri": [4 * abs(i / TN - .5) - 1 for i in range(TN)],
      "sq": [1.0 if i < TN // 2 else -1.0 for i in range(TN)],
      "pulse": [1.0 if i < TN // 4 else -1.0 for i in range(TN)],
      "saw": [2 * i / TN - 1 for i in range(TN)]}
WT["box"] = [WT["sin"][i] * .7 + WT["sin"][(i * 2) % TN] * .3 for i in range(TN)]   # music box
WT["organ"] = [WT["sin"][i] * .6 + WT["sin"][(i * 2) % TN] * .25 + WT["sin"][(i * 3) % TN] * .15 for i in range(TN)]
_rng = random.Random(1)
NOISE = [_rng.uniform(-1, 1) for _ in range(RATE)]
HISS = [NOISE[i] - NOISE[i - 1] for i in range(RATE)]  # brighter noise for hats
_ENV = {}


def _env(cnt, shape):
    key = (cnt, shape)
    if key not in _ENV:
        a = max(1, min(cnt // 3, int(RATE * (.03 if shape == "pad" else .004))))
        r = max(1, min(cnt // 3, int(RATE * (.25 if shape == "pad" else .02))))
        if shape == "pluck":
            d = -5.0 / cnt
            e = [min(1.0, i / a) * math.exp(d * i) for i in range(cnt)]
        elif shape == "hit":
            d = -9.0 / cnt
            e = [math.exp(d * i) for i in range(cnt)]
        else:  # pad / organ: attack, sustain, release
            e = [min(1.0, i / a, (cnt - i) / r) for i in range(cnt)]
        if len(_ENV) > 400:
            _ENV.clear()
        _ENV[key] = e
    return _ENV[key]


def synth_track(path, bpm, root, scale, degs, style, seed):
    rnd = random.Random(seed)
    sc = SCALES[scale]
    beat = 60 / bpm
    st = beat / 4                                   # one 16th step
    bars = 16
    n = int(bars * 16 * st * RATE) + RATE
    buf = array("f", bytes(4 * n))
    add = operator.add
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    swing = .33 if style in ("lofi", "hop") else 0

    def t_of(step):  # step index (16ths) -> seconds, with swing on off-16ths
        return step * st + (st * swing if step % 2 else 0)

    def mix(i0, seg):
        i1 = min(n, i0 + len(seg))
        if i1 > i0:
            buf[i0:i1] = array("f", map(add, buf[i0:i1], seg[:i1 - i0]))

    def tone(t0, dur, f, wave, vol, shape="pluck", vib=0.0):
        i0, cnt = int(t0 * RATE), int(dur * RATE)
        if cnt < 8 or i0 >= n:
            return
        tbl, env = WT[wave], _env(cnt, shape)
        inc = f * TN / RATE
        if vib:
            w = 2 * math.pi * 5.5 / RATE
            seg = [tbl[int(i * inc + vib * TN * math.sin(w * i) / 40) % TN] * e * vol for i, e in enumerate(env)]
        else:
            seg = [tbl[int(i * inc) % TN] * e * vol for i, e in enumerate(env)]
        mix(i0, seg)

    def kick(t0, vol=.8, f0=150, f1=42, dur=.18):
        cnt = int(dur * RATE)
        kk = (f1 - f0) / (2 * cnt)
        env = _env(cnt, "hit")
        mix(int(t0 * RATE), [math.sin(2 * math.pi * (f0 * i + kk * i * i) / RATE) * e * vol for i, e in enumerate(env)])

    def noise(t0, dur, vol, bright=False):
        cnt = int(dur * RATE)
        src, o = (HISS if bright else NOISE), rnd.randrange(RATE - cnt - 1)
        env = _env(cnt, "hit")
        mix(int(t0 * RATE), [src[o + i] * e * vol for i, e in enumerate(env)])

    def note(deg, octave=0):
        return root + sc[deg % 7] + 12 * (deg // 7 + octave)

    def chord_tones(d, size=3):
        return [note(d + 2 * i) for i in range(size)]

    # ---- melody motifs: 16 eighth-note slots over 2 bars; ints = scale steps above the chord root, '-' = hold
    def motif(density):
        out, cur = [], rnd.choice((0, 2, 4))
        for i in range(16):
            if i and rnd.random() > density:
                out.append(None if rnd.random() < .45 else "-")
                continue
            cur = max(-2, min(9, cur + rnd.choice((-2, -1, -1, 1, 1, 2, 0, 3, -3))))
            if i % 4 == 0:
                cur = min((0, 2, 4, 7), key=lambda c: abs(c - cur))
            out.append(cur)
        out[15] = None
        return out

    dens = {"lofi": .5, "lullaby": .55, "desert": .7, "boss": .85, "party": .75}.get(style, .65)
    ma, mb = motif(dens), motif(dens)
    mb = [m + 2 if isinstance(m, int) else m for m in mb]
    ma2 = ma[:12] + [rnd.choice((0, 4, 7)), "-", "-", None]
    form = [ma, ma2, None, ma, mb, mb, ma, ma2] if style != "lullaby" else [ma, ma2, mb, ma2] * 2
    lead = {"pop": ("pulse", .13), "party": ("sq", .1), "lofi": ("sin", .17), "desert": ("tri", .2),
            "synthwave": ("saw", .08), "boss": ("sq", .1), "hop": ("pulse", .12), "workout": ("saw", .08),
            "lullaby": ("box", .2)}[style]
    drums = DRUMS[style]

    for bar in range(bars):
        d = degs[bar % len(degs)]
        ch = chord_tones(d, 4 if style in ("lofi", "synthwave", "lullaby") else 3)
        bass = ch[0] - 12 if ch[0] - 12 >= 36 else ch[0]
        b0 = bar * 16
        # drums
        if not (style == "lullaby") and not (bar == 0 and style in ("lofi", "synthwave")):
            for s_ in range(16):
                t = t_of(b0 + s_)
                k_, sn, hh = drums[0][s_], drums[1][s_], drums[2][s_]
                if k_ == "x":
                    kick(t, .75 if style != "lofi" else .5)
                elif k_ == "D":
                    kick(t, .7, 110, 60, .22)
                if sn == "x":
                    noise(t, .14 if style != "lofi" else .09, .3 if style != "lofi" else .14)
                    tone(t, .08, 190, "tri", .18, "hit")
                elif sn == "T":
                    noise(t, .05, .22, True)
                    tone(t, .05, 520, "sin", .14, "hit")
                if hh == "x":
                    noise(t, .035 if style != "boss" else .025, .07 if style != "lofi" else .045, True)
                if style == "workout" and s_ in (4, 12) and bar % 2:
                    noise(t + .012, .1, .2)   # clap
            if bar % 4 == 3 and style in ("pop", "party", "boss", "workout", "synthwave"):
                for s_ in (12, 13, 14, 15):  # fill
                    noise(t_of(b0 + s_), .06, .18)
        # bass
        if style in ("party", "workout"):
            for s_ in range(2, 16, 4):
                tone(t_of(b0 + s_), st * 1.8, hz(bass + (12 if s_ % 8 == 6 else 0)), "saw", .2)
        elif style in ("synthwave", "boss"):
            for s_ in range(0, 16, 2):
                tone(t_of(b0 + s_), st * 1.9, hz(bass + (12 if style == "boss" and s_ % 8 == 6 else 0)),
                     "saw" if style == "synthwave" else "sq", .17)
        elif style == "hop":
            for s_, o in ((0, 0), (3, 12), (6, 0), (10, 7), (12, 12)):
                tone(t_of(b0 + s_), st * 2, hz(bass + o), "tri", .32)
        elif style == "desert":
            tone(t_of(b0), st * 6, hz(bass), "tri", .3)
            tone(t_of(b0 + 6), st * 4, hz(bass + 7), "tri", .25)
            tone(t_of(b0), st * 16, hz(bass + 12), "sin", .05, "pad")   # drone
        elif style in ("lofi", "lullaby"):
            tone(t_of(b0), st * 15, hz(bass), "sin", .3 if style == "lofi" else .2, "pad")
        else:
            for s_ in range(0, 16, 4):
                tone(t_of(b0 + s_), st * 3.6, hz(bass), "tri", .3)
        # chords / arps
        if style == "lofi":
            for m in ch:
                tone(t_of(b0) + .012 * ch.index(m), st * 15, hz(m), "organ", .045, "pad")
        elif style == "synthwave":
            for m in ch:
                tone(t_of(b0), st * 16, hz(m), "saw", .025, "pad")
            for s_ in range(16):
                tone(t_of(b0 + s_), st * .9, hz(ch[s_ % 4] + 12), "tri", .05)
        elif style in ("party", "boss"):
            for s_ in range(16):
                tone(t_of(b0 + s_), st * .8, hz(ch[(s_ * (1 if style == "party" else 2)) % 3] + 12), "pulse", .035)
        elif style == "lullaby":
            for s_ in range(0, 16, 2):
                tone(t_of(b0 + s_), st * 3, hz(ch[(s_ // 2) % 4] + 12), "box", .07)
        elif style in ("pop", "hop", "workout"):
            for s_ in (4, 12) if style != "workout" else (2, 6, 10, 14):
                for m in ch:
                    tone(t_of(b0 + s_), st * 1.5, hz(m), "sq" if style == "pop" else "pulse", .03)
        # lead melody (2-bar motifs)
        mot = form[(bar // 2) % len(form)]
        if mot is None or (bar < 2 and style in ("lofi", "synthwave")):
            continue
        half = bar % 2
        for slot in range(8):
            m = mot[half * 8 + slot]
            if not isinstance(m, int):
                continue
            ln = 1
            while half * 8 + slot + ln < 16 and mot[half * 8 + slot + ln] == "-":
                ln += 1
            pitch = note(d + m, 1)
            t = t_of(b0 + slot * 2)
            dur = st * 2 * ln * .92
            if style == "desert":
                if rnd.random() < .3:   # grace note ornament
                    tone(t, st * .5, hz(note(d + m + 1, 1)), "tri", lead[1] * .7)
                    t += st * .5
                    dur -= st * .5
                tone(t, dur, hz(pitch), lead[0], lead[1], "organ", vib=.6)
            else:
                tone(t, dur, hz(pitch), lead[0], lead[1], "pad" if style in ("lofi", "synthwave") else "pluck",
                     vib=.3 if style in ("lofi", "synthwave") and ln > 2 else 0)
    # echo / room
    if style in ("lofi", "synthwave", "desert", "lullaby"):
        d_ = int(beat * .75 * RATE)
        fb = .28
        for i in range(d_, n, d_):
            j = min(n, i + d_)
            buf[i:j] = array("f", map(add, buf[i:j], (v * fb for v in buf[i - d_:j - d_])))
    if style == "lofi":  # soft low-pass + vinyl crackle
        y, a = 0.0, .35
        out = []
        for v in buf:
            y += a * (v - y)
            out.append(y)
        for _ in range(int(n / RATE * 6)):
            i = rnd.randrange(n - 2)
            out[i] += rnd.uniform(-.25, .25)
        buf = array("f", out)
    _write_wav(path, buf)


class Audio:
    def __init__(self, cfg):
        self.cfg = cfg
        os.makedirs(CACHE, exist_ok=True)
        self.paths = {}
        for name, (notes, wf, vol) in SFX.items():
            p = os.path.join(CACHE, name + ".wav")
            if not os.path.exists(p):
                _write_wav(p, _sfx(notes, wf, vol))
            self.paths[name] = p
        self.pg = None
        if pygame:
            try:
                pygame.mixer.pre_init(RATE, -16, 1, 512)
                pygame.mixer.init()
                pygame.mixer.set_num_channels(16)
                self.snd = {k: pygame.mixer.Sound(p) for k, p in self.paths.items()}
                self.pg = pygame
            except Exception:
                self.pg = None
        self.tracks = [os.path.join(CACHE, f"song{i}_v2.wav") for i in range(len(TRACKS))]
        for i in range(3):  # v1 tracks are replaced by the v2 synth
            try:
                os.remove(os.path.join(CACHE, f"track{i}.wav"))
            except OSError:
                pass
        self.making = set()
        self.playing = None          # None | ("track", i) | ("file", path)
        self.playlist, self.pl_i = [], 0
        self.bpm = 120
        self.t0 = time.perf_counter()

    def ready(self, i):
        return os.path.exists(self.tracks[i])

    def make(self, i):
        """Synthesize track i in the background (once, then cached)."""
        if self.ready(i) or i in self.making:
            return
        self.making.add(i)

        def work():
            try:
                synth_track(self.tracks[i] + ".tmp", *TRACKS[i])
                os.replace(self.tracks[i] + ".tmp", self.tracks[i])
            except Exception:
                pass
            self.making.discard(i)
        threading.Thread(target=work, daemon=True).start()

    def play(self, name, vol=1.0):
        if not self.cfg["sound"] or name not in self.paths:
            return
        if self.pg:
            s = self.snd[name]
            s.set_volume(max(0, min(1, self.cfg["sfx_vol"] * vol)))
            s.play()
        elif not self.playing:
            try:
                winsound.PlaySound(self.paths[name], winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            except RuntimeError:
                pass

    def play_track(self, i):
        self.stop()
        path = self.tracks[i]
        self.bpm = TRACKS[i][0]
        self.playing = ("track", i)
        self.t0 = time.perf_counter()
        if self.pg:
            self.pg.mixer.music.load(path)
            self.pg.mixer.music.set_volume(self.cfg["music_vol"])
            self.pg.mixer.music.play(-1)
        else:
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)

    def style(self):
        return TRACKS[self.playing[1]][4] if self.playing and self.playing[0] == "track" else "pop"

    def play_files(self, files):
        if not self.pg or not files:
            return False
        self.playlist, self.pl_i = list(files), 0
        return self._play_pl()

    def _play_pl(self):
        while self.pl_i < len(self.playlist):
            try:
                self.pg.mixer.music.load(self.playlist[self.pl_i])
                self.pg.mixer.music.set_volume(self.cfg["music_vol"])
                self.pg.mixer.music.play()
                self.playing = ("file", self.playlist[self.pl_i])
                self.bpm, self.t0 = 120, time.perf_counter()
                return True
            except Exception:
                self.pl_i += 1
        self.playing = None
        return False

    def next_index(self):
        return (self.playing[1] + 1) % len(TRACKS) if self.playing and self.playing[0] == "track" else 0

    def next(self):
        if self.playing and self.playing[0] == "file":
            self.pl_i += 1
            return self._play_pl()
        i = self.next_index()
        if self.ready(i):
            self.play_track(i)
            return True
        return False

    def poll(self):
        if self.pg and self.playing and self.playing[0] == "file" and not self.pg.mixer.music.get_busy():
            self.pl_i += 1
            self._play_pl()

    def stop(self):
        if self.pg:
            self.pg.mixer.music.stop()
        elif self.playing:
            winsound.PlaySound(None, 0)
        self.playing = None

    def set_music_vol(self, v):
        if self.pg:
            self.pg.mixer.music.set_volume(v)

    def song_name(self):
        if not self.playing:
            return "none"
        if self.playing[0] == "track":
            return T["tracks"][0][self.playing[1]]
        return os.path.splitext(os.path.basename(self.playing[1]))[0]


# ============================================================== AI brain (any provider)
class BrainError(Exception):
    def __init__(self, kind, detail=""):
        super().__init__(detail)
        self.kind, self.detail = kind, detail


class Brain:
    def __init__(self, cfg):
        self.cfg = cfg

    def conf(self, provider=None):
        p = provider or self.cfg.get("provider", "anthropic")
        d = PROVIDERS.get(p, PROVIDERS["anthropic"])
        b = self.cfg["brains"].get(p, {})
        return p, b.get("key", "").strip(), (b.get("model") or d["model"]).strip(), (b.get("base") or d["base"]).strip()

    def ready(self):
        p, key, model, base = self.conf()
        return bool(model and base) and (bool(key) or not PROVIDERS[p]["key"])

    def label(self):
        p, _, model, _ = self.conf()
        return f"{PROVIDERS[p]['name'].split(' (')[0]} - {model}"

    def complete(self, system, messages, max_tokens=4000):
        p, key, model, base = self.conf()
        if p == "anthropic":
            return self._anthropic(key, model, base, system, messages, max_tokens)
        return self._openai_compat(p, key, model, base, system, messages)

    def _anthropic(self, key, model, base, system, messages, max_tokens):
        extra, headers = {}, {}
        if model.startswith(("claude-opus-5", "claude-sonnet-5", "claude-fable", "claude-haiku-5")):
            extra["output_config"] = {"effort": "low"}
        if model in FALLBACK_MODELS:
            extra["fallbacks"] = "default"
            headers["anthropic-beta"] = "server-side-fallback-2026-07-01"
        try:
            import anthropic
        except ImportError:
            anthropic = None
        if anthropic:
            client = anthropic.Anthropic(api_key=key or None, max_retries=1, timeout=90,
                                         base_url=None if base == PROVIDERS["anthropic"]["base"] else base)
            try:
                r = client.messages.create(model=model, max_tokens=max_tokens, system=system, messages=messages,
                                           extra_headers=headers, extra_body=extra)
            except anthropic.AuthenticationError:
                raise BrainError("key")
            except anthropic.NotFoundError:
                raise BrainError("model")
            except anthropic.RateLimitError:
                raise BrainError("rate")
            except anthropic.APIStatusError as e:
                raise BrainError("other", f"HTTP {e.status_code}")
            except anthropic.APIConnectionError:
                raise BrainError("conn")
            if r.stop_reason == "refusal":
                raise BrainError("refusal")
            return " ".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip()
        # no SDK installed: plain HTTP
        body = dict(model=model, max_tokens=max_tokens, system=system, messages=messages, **extra)
        data = self._post(base.rstrip("/") + "/v1/messages", body,
                          {"x-api-key": key, "anthropic-version": "2023-06-01", **headers})
        if data.get("stop_reason") == "refusal":
            raise BrainError("refusal")
        return " ".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()

    def _openai_compat(self, p, key, model, base, system, messages):
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        if p == "openrouter":
            headers.update({"HTTP-Referer": "https://claude.ai", "X-Title": "Clawd Desktop Pet"})
        data = self._post(base.rstrip("/") + "/chat/completions",
                          {"model": model, "messages": [{"role": "system", "content": system}] + messages}, headers)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise BrainError("other", str(data)[:120])
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        return (content or "").strip()

    @staticmethod
    def _post(url, body, headers):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "ClawdPet/3", **headers})
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            kind = {401: "key", 403: "key", 404: "model", 429: "rate"}.get(e.code, "other")
            raise BrainError(kind, f"HTTP {e.code} {e.read()[:120].decode('utf-8', 'ignore')}")
        except (urllib.error.URLError, OSError) as e:
            raise BrainError("conn", str(e)[:80])


def parse_reply(text):
    s = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    i, j = s.find("{"), s.rfind("}")
    if i != -1 and j > i:
        try:
            obj = json.loads(s[i:j + 1])
            if isinstance(obj, dict) and "say" in obj:
                acts = obj.get("actions") or []
                return str(obj.get("say") or ""), [a for a in acts if isinstance(a, dict)]
        except ValueError:
            pass
    return text.strip(), []


# ============================================================== web tools (no API keys needed)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def http_get(url, timeout=15, limit=1_500_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en,ar;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(limit)
        cs = r.headers.get_content_charset() or "utf-8"
    return raw.decode(cs, "ignore")


def html_text(html):
    import html as _h
    html = re.sub(r"(?is)<(script|style|noscript|svg|head)\b.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", html)
    text = _h.unescape(re.sub(r"<[^>]+>", " ", html))
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t\r\f\v]+", " ", text)).strip()


def web_search(query, n=6):
    """DuckDuckGo HTML results, Wikipedia as a fallback. Returns [(title, url, snippet)]."""
    import html as _h
    out = []
    try:
        page = http_get("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query))
        for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=class="result__a"|$)', page, re.S):
            url = _h.unescape(m.group(1))
            u = re.search(r"uddg=([^&]+)", url)
            url = urllib.parse.unquote(u.group(1)) if u else url
            if "duckduckgo.com/y.js" in url:
                continue  # ads
            sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', m.group(3), re.S)
            out.append((html_text(m.group(2)), url, html_text(sn.group(1)) if sn else ""))
            if len(out) >= n:
                break
    except Exception:
        pass
    if not out:
        wl = "ar" if is_ar(query) else "en"
        data = json.loads(http_get(f"https://{wl}.wikipedia.org/w/api.php?action=query&list=search&format=json"
                                   f"&srlimit={n}&srsearch=" + urllib.parse.quote(query)))
        for r in data.get("query", {}).get("search", []):
            out.append((r["title"], f"https://{wl}.wikipedia.org/wiki/" + urllib.parse.quote(r["title"].replace(" ", "_")),
                        html_text(r.get("snippet", ""))))
    return out


def fetch_text(url, limit=7000):
    page = http_get(url)
    t = re.search(r"(?is)<title[^>]*>(.*?)</title>", page)
    body = html_text(page)
    return ((html_text(t.group(1)) + "\n") if t else "") + body[:limit]


def weather(place=""):
    data = json.loads(http_get("https://wttr.in/" + urllib.parse.quote(place.strip()) + "?format=j1", timeout=12))
    cur = data["current_condition"][0]
    area = data.get("nearest_area", [{}])[0]
    where = ", ".join(x[0]["value"] for x in (area.get("areaName"), area.get("country")) if x) or place
    days = data.get("weather", [])
    fc = "; ".join(f"{d['date']}: {d['mintempC']}-{d['maxtempC']}C" for d in days[:3])
    return dict(where=where, temp=cur["temp_C"], feels=cur["FeelsLikeC"], desc=cur["weatherDesc"][0]["value"],
                hum=cur["humidity"], wind=cur["windspeedKmph"], forecast=fc,
                max=days[0]["maxtempC"] if days else "?", min=days[0]["mintempC"] if days else "?")


def youtube_find(query):
    """First YouTube video for a query -> (url, title) without an API key."""
    page = http_get("https://www.youtube.com/results?search_query=" + urllib.parse.quote(query) + "&sp=EgIQAQ%253D%253D")
    m = re.search(r'"videoRenderer":\{"videoId":"([\w-]{11})".*?"title":\{"runs":\[\{"text":"(.*?)"\}', page, re.S)
    if not m:
        m = re.search(r'"videoId":"([\w-]{11})"', page)
        return ("https://www.youtube.com/watch?v=" + m.group(1), query) if m else (None, None)
    title = json.loads('"' + m.group(2) + '"') if "\\" in m.group(2) else m.group(2)
    return "https://www.youtube.com/watch?v=" + m.group(1), title


def run_powershell(cmd, timeout=40):
    p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True,
                       timeout=timeout, creationflags=0x08000000)
    dec = lambda b: b.decode("utf-8", "ignore") if b else ""
    out = (dec(p.stdout) + ("\n[stderr] " + dec(p.stderr) if p.stderr.strip() else "")).strip()
    return f"exit code {p.returncode}\n{out[:5000] or '(no output)'}"


# ============================================================== the pet
class Clawd:
    def __init__(self):
        self.cfg = self.load_cfg()
        if self.cfg["lang"] == "auto":
            self.cfg["lang"] = "ar" if (kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x01 else "en"
        self.audio = Audio(self.cfg)
        self.brain = Brain(self.cfg)
        self.cpu = CpuMeter()
        self.cpu_last = 0
        self.dt = 1 / 60
        self.k = user32.GetDpiForSystem() / 96 if hasattr(user32, "GetDpiForSystem") else 1.0

        self.root = root = tk.Tk()
        root.title(APP)
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-transparentcolor", KEY)
        root.config(bg=KEY)
        self.c = tk.Canvas(root, bg=KEY, highlightthickness=0)
        self.c.pack()

        # world state
        mx, my = root.winfo_pointerxy()
        self.mon = monitor_work(mx, my)
        L_, T_, R_, B_ = self.mon
        self.time, self.last = 0.0, time.perf_counter()
        self.surf, self.plat, self.plat_rect = "floor", None, None
        self.fx, self.fy = random.uniform(L_ + 300, max(L_ + 301, R_ - 300)), B_
        self.vx = self.vy = 0.0
        self.dir, self.speed = random.choice((-1, 1)), 0.0
        self.state, self.timer = "idle", 2.0
        self.want_climb = False
        self.pending_jump = None
        self.max_v = 0.0
        self.walkdist = 0.0
        self.sq, self.sqv = 0.0, 0.0                 # squash spring
        self.look = [0.0, 0.0]
        self.blink_at = 2.0
        self.parts = []
        self.say_queue, self.bubble, self.bubble_t, self.shown = [], None, 0.0, 0.0
        self.word = THINK[0][0]
        self.ask_req = None
        self.next_ask = self.roll_ask()
        self.drag, self.samples, self.clicks, self.click_job = None, [], [], None
        self.pet_rev, self.pet_last, self.pet_dir = [], 0, 0
        self.lmx, self.lmy = mx, my
        self.cd = {}
        self.happy, self.energy = 75.0, 85.0
        self.afk = False
        self.active_sec = self.water_sec = self.eyes_sec = 0.0
        self.last_title, self.last_ctx, self.last_song = "", None, None
        self.batt_warned = False
        self.cpu_hot = 0
        self.pending_explain = None
        self.windows = []
        self.timers = []
        self.history, self.chat_log = [], []   # (restored from chat.json below)
        self.waiting = False
        self.q = queue.Queue()
        self.chat = self.settings_win = None
        self.ball = None
        self.hk = {}
        self.talk_next = 0.0
        self.music_wait = None
        self.stay = False
        self.fly_forever, self.fly_target, self.fly_retarget = False, None, 0.0
        self.web_d, self.web_target, self.web_phase, self.thread_win = 0.0, 0.0, None, None
        self.want_peek, self.peek_side = False, 0
        self.want_web = False
        self.hidden = False
        # v1.1: smooth body (rotation / limbs), physics, needs, exercise, agent
        self.rot, self.spin, self.rot_target, self.tumble = 0.0, 0.0, 0.0, 0.0
        self._rc, self._rs, self.dsurf = 1.0, 0.0, "floor"
        self.arm = [3.0, 3.0]
        self.after_land = None
        self.chain = self._chain2 = None
        self.ask_queue = []
        self.slide_v = 0.0
        self.mouse_still = 0.0
        self.ex, self.routine = None, []
        self.hunger = 20.0
        self.hover_until, self.near_since, self.away_since = 0.0, None, 0.0
        self.awaiting_name = False
        self.agent = None
        self.yt_song = None
        self.force_flip = False
        self.typing_t = 0.0
        self.input_idle_prev = 0.0
        self.pose = {"legs": 0, "arms": "down", "eyes": "open", "bob": 0.0}
        # v1.2: personality, mischief, hiding, games, desktop effects
        self.kick, self.goto, self.work = None, None, None
        self.wmove, self.win_orig = {}, {}
        self.sink, self.hide_info = 0.0, None
        self.recent = []
        self.game = None
        self.cursor_over, self.over_t = False, 0.0
        self.last_kick_t, self.fetch_n = -9.0, 0
        self.next_foot, self.foot_i = 0.0, 0
        self.fxl = None
        today = time.strftime("%Y-%m-%d")
        if self.cfg["stats"].get("day") != today:
            self.cfg["stats"] = {"day": today, **{k: 0 for k in ("pets", "cookies", "throws", "workouts", "chats", "jokes")},
                                 "total_workouts": self.cfg["stats"].get("total_workouts", 0)}
        try:
            with open(CHAT_PATH, encoding="utf-8") as f:
                saved = json.load(f)
            self.history = saved.get("history", [])[-20:]
            self.chat_log = [tuple(x) for x in saved.get("log", [])][-40:]
        except (OSError, ValueError):
            pass
        try:
            self.last_clip = root.clipboard_get()
        except tk.TclError:
            self.last_clip = None

        self.apply_scale(self.cfg["scale"])
        c = self.c
        c.bind("<ButtonPress-1>", self.press)
        c.bind("<B1-Motion>", self.motion)
        c.bind("<ButtonRelease-1>", self.release)
        c.bind("<Double-Button-1>", self.double)
        c.bind("<Button-3>", self.show_menu)
        c.bind("<Motion>", self.hover)
        c.bind("<MouseWheel>", self.wheel)

        h = time.localtime().tm_hour
        hello = {"en": ("Good morning!", "Good afternoon!", "Good evening!", "Up late, huh?"),
                 "ar": ("صباح الخير!", "مساء النور!", "مساء الخير!", "سهران؟")}[self.lang]
        greet = hello[0 if 5 <= h < 12 else 1 if h < 18 else 2 if h < 23 else 3]
        if self.cfg["name"]:
            self.say(greet[:-1] + self.c_() + greet[-1] + (" اشتقت لك :)" if self.lang == "ar" else " Missed you :)"))
        else:
            self.say(greet + (" أنا كلود :)" if self.lang == "ar" else " I'm Clawd :)"))
        if self.cfg["first_run"]:
            self.say_queue += self.lines("tips")
            self.cfg["first_run"] = False
            self.save()
        if not self.cfg["name"] and not self.cfg["asked_name"]:
            self.root.after(9000, self.ask_name)
        self.refresh_windows()
        try:
            self.fxl = FxLayer(self)
            root.lift()
        except Exception as e:  # noqa
            self.log_error(e)
        self.tick()

    # ---------------------------------------------------------- config & i18n
    @staticmethod
    def load_cfg():
        cfg = json.loads(json.dumps(DEFAULT_CFG))
        try:
            with open(CFG_PATH if os.path.exists(CFG_PATH) or not os.path.exists(OLD_CFG) else OLD_CFG,
                      encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (OSError, ValueError):
            pass
        if cfg.get("api_key"):  # migrate v2 setting
            cfg["brains"].setdefault("anthropic", {})["key"] = cfg.pop("api_key")
        cfg.pop("api_key", None)
        cfg.pop("follow_old", None)
        if cfg.get("ask_rate") not in ASK_RATES:
            cfg["ask_rate"] = "normal"
        return cfg

    def save(self):
        try:
            with open(CFG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, indent=1, ensure_ascii=False)
        except OSError:
            pass

    @property
    def lang(self):
        return "ar" if self.cfg.get("lang") == "ar" else "en"

    def tr(self, key, **kw):
        s = T[key][1 if self.lang == "ar" else 0]
        return s.format(**kw) if kw else s

    def lines(self, key):
        return list(L[key][1 if self.lang == "ar" else 0])

    def line(self, key, **kw):
        s = random.choice(self.lines(key))
        return s.format(**kw) if kw else s

    def c_(self):
        """', Name' (or '') to sprinkle the user's name into lines."""
        n = self.cfg.get("name", "").strip()
        return ("، " if self.lang == "ar" else ", ") + n if n else ""

    def sayl(self, key, **kw):
        """Say a random line, filling {c} with the user's name."""
        self.say(self.line(key, c=self.c_(), **kw) if "{c}" in "".join(self.lines(key)) else self.line(key, **kw))

    def stat(self, key, n=1):
        st = self.cfg["stats"]
        st[key] = st.get(key, 0) + n
        return st[key]

    def ask_name(self):
        if self.cfg["name"] or self.hidden:
            return
        self.cfg["asked_name"] = True
        self.save()
        self.awaiting_name = True
        self.say(self.line("ask_name"))
        self.spawn("bang")
        self.sfx("ding", .6)

    def set_name(self, name):
        name = re.sub(r"[^\w\s'.-]", "", name, flags=re.U).strip()[:24]
        if not name:
            return
        self.cfg["name"] = name[:1].upper() + name[1:]
        self.awaiting_name = False
        self.save()
        self.say(self.line("name_set", n=self.cfg["name"]))
        self.set_state("dance", 3)
        self.spawn("heart", 4)
        self.sfx("yes")

    def save_chat(self):
        try:
            with open(CHAT_PATH, "w", encoding="utf-8") as f:
                json.dump({"history": self.history[-20:], "log": self.chat_log[-40:]}, f, ensure_ascii=False)
        except OSError:
            pass

    def roll_ask(self):
        r = ASK_RATES.get(self.cfg["ask_rate"])
        return random.uniform(*r) if r else 1e9

    def cooldown(self, key, sec):
        if self.time >= self.cd.get(key, -1e9):
            self.cd[key] = self.time + sec
            return True
        return False

    def sfx(self, name, vol=1.0):
        self.audio.play(name, vol)

    # ---------------------------------------------------------- geometry
    def apply_scale(self, s):
        s = max(0.4, min(3.0, round(s, 2)))
        self.cfg["scale"] = s
        k = self.k
        self.P = max(3, round(7 * k * s))
        self.PW, self.PH = 16 * self.P, 9 * self.P
        self.S = int(max(470 * k, self.PH + 440 * k + 12 * self.P, self.PW + 60 * k + 12 * self.P))
        self.c.config(width=self.S, height=self.S)
        self.place_window(force=True)

    def feet_canvas(self, surf):
        S, m = self.S, 2 + 6 * self.P   # margin leaves room to tumble / lean without clipping
        return {"floor": (S / 2, S - m), "air": (S / 2, S - m), "fly": (S / 2, S - m), "ceil": (S / 2, m),
                "lwall": (m, S / 2), "rwall": (S - m, S / 2)}[surf]

    def place_window(self, force=False):
        cx, cy = self.feet_canvas(self.surf)
        self.wx, self.wy = int(round(self.fx - cx)), int(round(self.fy - cy))
        geo = f"{self.S}x{self.S}+{self.wx}+{self.wy}"
        if force or geo != getattr(self, "_geo", None):
            self._geo = geo
            self.root.geometry(geo)

    def half(self):
        return self.PW / 2

    # ---------------------------------------------------------- speech
    @staticmethod
    def chunk(text, size=170):
        parts, cur = [], ""
        for sent in re.split(r"(?<=[.!?؟])\s+", text.strip()):
            while len(sent) > size * 1.4:
                cut = sent.rfind(" ", 0, size)
                cut = cut if cut > 20 else size
                parts.append((cur + " " + sent[:cut]).strip()) if cur else parts.append(sent[:cut])
                cur, sent = "", sent[cut:].strip()
            if cur and len(cur) + len(sent) + 1 > size:
                parts.append(cur)
                cur = sent
            else:
                cur = (cur + " " + sent).strip()
        if cur:
            parts.append(cur)
        return parts or [""]

    def say(self, text):
        if not text:
            return
        self.say_queue = self.chunk(text)
        self.next_bubble()

    def next_bubble(self):
        if self.say_queue:
            self.bubble = self.say_queue.pop(0)
            self.shown = 0.0
            self.bubble_t = 2.4 + len(self.bubble) * 0.07
        else:
            self.bubble = None

    def quip(self):
        pk = self.cfg.get("personality", "balanced")
        if pk != "balanced" and random.random() < .45:
            return self.sayl(pk + "_q")
        if self.happy < 30 and random.random() < .5:
            self.say(self.line("lonely"))
        elif self.energy < 20 and random.random() < .5:
            self.say(self.line("sleepy"))
            self.sfx("yawn")
        else:
            self.say(self.line("quips"))

    # ---------------------------------------------------------- transforms (pet-local grid -> canvas)
    def T(self, u, v):
        lx = (u - 8) * self.P * self.sx
        ly = (v + self.bob - 9) * self.P * self.sy
        if self.rot:  # rotate around the body centre (tumbling, leaning, swaying)
            py = -4.5 * self.P * self.sy
            dy = ly - py
            lx, ly = lx * self._rc - dy * self._rs, lx * self._rs + dy * self._rc + py
        o = self.dsurf
        if o == "ceil":
            lx, ly = -lx, -ly
        elif o == "lwall":
            lx, ly = -ly, lx
        elif o == "rwall":
            lx, ly = ly, -lx
        fx, fy = self.anchor
        return fx + lx, fy + ly

    def local_dir(self, dx, dy):
        """screen vector -> pet-local vector"""
        o = self.dsurf
        if o == "ceil":
            return -dx, -dy
        if o == "lwall":
            return dy, -dx
        if o == "rwall":
            return -dy, dx
        return dx, dy

    def screen_dir(self, lx, ly):
        o = self.dsurf
        if o == "ceil":
            return -lx, -ly
        if o == "lwall":
            return -ly, lx
        if o == "rwall":
            return ly, -lx
        return lx, ly

    # ---------------------------------------------------------- states
    DUR = {"walk": (2, 7), "idle": (1.5, 4.5), "sleep": (12, 22), "dance": (4, 6), "think": (2.5, 5.5), "sad": (2.5, 2.5),
           "chase": (8, 8), "code": (6, 12), "stretch": (2.2, 2.2), "eat": (3.5, 3.5), "dizzy": (2.5, 2.5),
           "angry": (2, 2), "petted": (2, 2), "crouch": (.18, .18), "hang": (1.5, 4), "sneeze": (1.8, 1.8),
           "peek": (4, 7), "fly": (6, 14), "web": (60, 60), "moonwalk": (4, 4), "getup": (1.1, 1.1),
           "slide": (6, 6), "wave": (1.6, 1.6), "look": (2.5, 4), "beg": (3, 3), "yawn": (1.6, 1.6), "proud": (2, 2),
           "hide": (9, 16), "laugh": (1.8, 1.8), "stomp": (2.4, 2.4), "laser": (2.6, 2.6), "doodle": (3.6, 3.6),
           "lounge": (8, 15), "flee": (30, 30), "build": (7, 7), "mine": (7, 7), "smash": (3.4, 3.4)}
    NEED_FLOOR = ("chase", "play", "peek", "moonwalk", "slide", "flee", "lounge", "build", "mine", "smash", "doodle")
    NO_FLY = ("walk", "sleep", "chase", "play", "peek", "moonwalk", "slide", "getup", "flee", "lounge", "build", "mine",
              "smash", "doodle", "hide", "stomp")

    def set_state(self, s, timer=None):
        if self.state == "hide" and s != "hide":
            self.hide_info = None
            if self.game and self.game.get("kind") == "seek":
                self.game = None
        if self.state in ("build", "mine", "smash", "doodle") and s != self.state:
            self.work = None
        if s != "walk":
            self.goto = None
        if self.state == "ask" and s != "ask" and self.ask_req:
            if self.ask_req.get("real"):
                self.ask_req["deny"]()
            self.ask_req = None
        if self.state == "web" and s != "web":
            self.end_web()
        if self.state == "exercise" and s != "exercise":
            self.ex, self.routine = None, []
        # actions that need the floor: land / let go first, then do it
        if (s in self.NEED_FLOOR and self.surf != "floor") or (s in self.NO_FLY and self.surf == "fly"):
            return self.need_floor(lambda: self.set_state(s, timer))
        if self.surf == "air" and s not in ("jump", "fall", "drag", "crouch"):
            self.after_land = lambda: self.set_state(s, timer)
            return
        if s == "jump" and self.surf in ("lwall", "rwall", "ceil"):
            return self.drop()
        if s == "walk" and self.stay:
            s = "idle"
        self.state = s
        a, b = self.DUR.get(s, (2, 2))
        self.timer = timer if timer is not None else random.uniform(a, b)
        if s == "walk":
            self.dir = random.choice((-1, 1))
        elif s == "jump":
            if self.surf == "fly":
                self.state, self.timer = "fly", 3
                self.sqv -= 6
                return
            vy = -random.uniform(850, 1050) * self.k
            self.launch(0 if self.stay else random.uniform(-80, 80) * self.k, vy)
            self.state = "jump"
            if random.random() < .2 or self.force_flip:  # sometimes a backflip
                self.force_flip = False
                self.spin = -self.dir * 2 * math.pi / (2 * abs(vy) / self.gravity())
                self.say(self.line("flip"))
        elif s == "think":
            self.word = random.choice(THINK[1 if self.lang == "ar" else 0])
        elif s == "sleep":
            self.say_queue, self.bubble = [], None
            if self.surf in ("ceil", "lwall", "rwall") and random.random() < .4:
                self.say(self.line("sleep_wall"))
        elif s == "stretch":
            self.say("*تمدد*" if self.lang == "ar" else "*streeeetch*")
        elif s == "angry":
            self.sfx("angry")
        elif s == "sneeze":
            self.say(self.line("sneeze_a"))
        elif s == "eat":
            self.stat("cookies")
        elif s == "yawn":
            self.sfx("yawn")
        elif s == "wave":
            self.sayl("wave")
        elif s == "laugh":
            self.sfx("laugh", .7)
            if random.random() < .6:
                self.sayl("laugh")
        elif s == "lounge":
            if random.random() < .5:
                self.sayl("lounge")
        elif s == "stomp":
            self._stomp_n = 0
            self.sayl("stomp")
        elif s in ("laser", "doodle"):
            self.sayl(s)

    def need_floor(self, fn):
        """Run fn now if standing on the floor, otherwise get down first and run it on landing."""
        if self.surf == "floor":
            return fn()
        self.after_land = fn
        if self.surf == "fly":
            self.fly_forever = False
            self.stop_fly()
        elif self.surf != "air":
            self.drop()

    def launch(self, vx, vy):
        self.surf, self.plat = "air", None
        self.vx, self.vy = vx, vy
        self.spin = 0.0
        self.sink = 0.0
        self.sqv -= 6
        self.sfx("jump")

    def drop(self):
        if self.surf == "floor":
            return
        if self.surf == "fly":
            return self.stop_fly()
        if self.state == "web":
            self.end_web()
        lx, ly = self.screen_dir(0, -1)   # push away from the surface
        self.fx, self.fy = self.pet_center()
        self.fy += self.PH / 2
        self.surf, self.plat = "air", None
        self.vx, self.vy = lx * 250 * self.k, ly * 250 * self.k
        self.state, self.max_v, self.spin, self.tumble = "fall", 0, 0.0, 0.0
        self.say(self.line("letgo"))
        self.sfx("scream", .6)

    def pet_center(self):
        h = self.PH / 2
        return {"floor": (self.fx, self.fy - h), "air": (self.fx, self.fy - h), "fly": (self.fx, self.fy - h),
                "ceil": (self.fx, self.fy + h), "lwall": (self.fx + h, self.fy), "rwall": (self.fx - h, self.fy)}[self.surf]

    def pick(self):
        if self.chain:  # a planned follow-up state (getting up -> dizzy, etc.)
            s, t = self.chain
            self.chain, self._chain2 = self._chain2, None
            return self.set_state(s, t)
        if self.game and self.game.get("kind") == "tag":
            return self.need_floor(lambda: self.set_state("flee", 30))
        if self.surf == "fly":
            if self.fly_forever or self.stay:
                self.state, self.timer = "fly", 5
                return
            return self.stop_fly()
        if self.stay:  # animate in place only
            w = {"idle": 6, "think": 2, "quip": 2, "sneeze": .5, "look": 2, "dance": 1 + (10 if self.audio.playing else 0)}
            if self.surf == "floor":
                w.update(sleep=1 + (4 if self.energy < 25 else 0), code=1, stretch=1)
            else:
                w = {"hang": 6, "quip": 1, "sneeze": .3, "look": 1}
            s = random.choices(list(w), weights=list(w.values()))[0]
            self.set_state("idle" if s == "quip" else s)
            if s == "quip":
                self.quip()
            return
        if self.surf != "floor":
            r = random.random()
            if r < .1:
                return self.drop()
            if self.surf == "ceil" and r < .3:
                return self.start_web()
            if self.cfg["fly"] and r < .36:
                return self.start_fly()
            if self.energy < 25 and r < .45:
                return self.set_state("sleep")
            self.set_state("walk" if r < .82 else "hang" if r < .93 else "look")
            if self.state == "walk" and self.surf in ("lwall", "rwall") and random.random() < .5:
                self.dir = -1
            if random.random() < .15:
                self.say(self.line("ceiling" if self.surf == "ceil" else "climb"))
            return
        w = {"walk": 6, "idle": 3, "think": 2, "sleep": 1 + (5 if self.energy < 25 else 0), "look": 2,
             "dance": 1 + (2 if self.happy > 70 else 0) + (12 if self.audio.playing else 0), "jump": 1, "quip": 3,
             "stretch": 1, "code": 1, "sneeze": .6, "joke": .5, "yawn": .8 if self.energy < 40 else 0,
             "exercise": .8 if self.energy > 45 else 0}
        if self.cfg["follow"]:
            w["chase"] = 2
        if self.cfg["windows"]:
            w["hop"] = 3
        if self.cfg["climb"] and not self.plat:
            w["climb"] = 2
            w["peek"] = 1
        if self.cfg["fly"]:
            w["fly"] = 1.5
        if self.ball:
            w["play"] = 8
        # personality shapes what he likes to do; recent picks are less likely (never boring)
        p = self.persona()
        for key, f in (("walk", p["speed"]), ("jump", p["speed"]), ("dance", p["speed"] ** .5), ("sleep", p["lazy"]),
                       ("yawn", p["lazy"]), ("idle", p["lazy"] ** .5), ("exercise", 1 / p["lazy"]), ("quip", p["social"] ** .5)):
            w[key] *= f
        w["lounge"] = .7 * p["lazy"]
        w["wave"] = .3 * p["social"]
        if self.cfg["desk_fx"]:
            w.update(doodle=.5 * p["naughty"] ** .5, laser=.3 * p["naughty"], build=.6 * p["speed"], mine=.6 * p["speed"],
                     smash=.15 * p["naughty"], glitch=.12 * p["naughty"])
        if self.cfg["windows"]:
            w["hide"] = .9 * p["naughty"] ** .5 + (.8 if self.plat else 0)
            if self.cfg["mischief"]:
                w["kick"] = 1.1 * p["naughty"]
                if self.plat:
                    w["stomp"] = .6 * p["naughty"]
        for r_ in self.recent:
            if r_ in w:
                w[r_] *= .25
        s = random.choices(list(w), weights=list(w.values()))[0]
        self.recent = (self.recent + [s])[-4:]
        if s == "kick":
            if not self.go_kick():
                self.set_state("walk")
        elif s == "hide":
            self.go_hide()
        elif s in ("laser", "doodle", "build", "mine", "smash", "glitch"):
            self.start_trick(s)
        elif s == "quip":
            self.set_state("idle")
            self.quip()
        elif s == "joke":
            self.set_state("idle", 6)
            self.say(self.line("jokes"))
        elif s == "hop":
            if not self.try_hop():
                self.set_state("walk")
        elif s == "climb":
            self.go_climb()
        elif s == "peek":
            self.go_peek()
        elif s == "fly":
            self.start_fly()
        elif s == "play":
            self.set_state("play", 10)
        elif s == "exercise":
            self.start_exercise()
        else:
            self.set_state(s)

    # ---------- exercise
    def start_exercise(self, kind=None, routine=False, cont=False):
        if routine:
            self.routine = list(ROUTINE)
            kind = self.routine.pop(0)
            self.stat("workouts")
            self.cfg["stats"]["total_workouts"] = self.cfg["stats"].get("total_workouts", 0) + 1
            if not self.audio.playing and self.cfg["sound"]:
                self.music_cmd("play", 7, quiet=True)
        kind = kind or random.choice(ROUTINE[:5])
        if self.surf in ("fly", "air"):
            rt = self.routine
            return self.need_floor(lambda: (setattr(self, "routine", rt), self.start_exercise(kind, cont=True)))
        rt = self.routine
        if self.state == "exercise":
            self.state = "idle"  # switch exercise without clearing the routine
        per, reps = EXERCISES[kind]
        self.set_state("exercise", per * reps + .25)
        self.routine = rt
        self.ex = {"kind": kind, "per": per, "reps": reps, "t0": self.time, "rep": 0, "routine": bool(rt) or routine}
        name = self.tr("ex_" + kind)
        if kind == "yoga":
            self.say(self.line("yoga"))
        else:
            self.say(self.line("ex_next" if cont else "ex_start", x=name))
        self.sfx("whoosh")

    def finish_exercise(self):
        ex = self.ex or {}
        self.energy = max(0, self.energy - 6)
        self.happy = min(100, self.happy + 5)
        if self.routine:
            return self.start_exercise(self.routine.pop(0), cont=True)
        self.ex = None
        self.set_state("proud", 2.5)
        self.spawn("spark", 8)
        self.sfx("win")
        if ex.get("routine"):
            self.sayl("ex_done")
            self.spawn("heart", 3)
        else:
            self.say(random.choice(["Phew! *flex*", "Strong Clawd!", "Easy."] if self.lang != "ar" else ["أوف! *استعراض عضلات*", "كلود القوي!", "سهلة."]))

    # ---------- stay / come / fly / web / peek
    def set_stay(self, on, quiet=False):
        self.stay = on
        if on:
            self.want_climb = self.want_peek = False
            if self.state in ("walk", "chase", "play", "come", "moonwalk"):
                self.set_state("idle")
            if self.surf == "fly":
                self.fly_target = None
        if not quiet:
            self.say(self.line("stay_on" if on else "stay_off"))
            self.sfx("stay")
            self.spawn("spark", 5)

    def come_here(self):
        mx, my = self.root.winfo_pointerxy()
        self.stay = False
        self.say(self.line("come"))
        if self.surf == "floor" and abs(my - self.fy) < self.PH * 2.5:
            self.set_state("chase", 10)
        else:
            self.start_fly(target=(mx, my + self.PH * 1.3), come=True)

    def start_fly(self, forever=False, target=None, come=False, quiet=False):
        if not self.cfg["fly"] and not forever and not come:
            return self.set_state("walk")
        cx, cy = self.pet_center()
        if self.state == "web":
            self.end_web()
        self.surf, self.plat = "fly", None
        self.fx, self.fy = cx, cy + self.PH / 2
        self.vx, self.vy = 0.0, -350 * self.k
        self.fly_forever = forever or self.fly_forever
        self.fly_target = target
        self.fly_retarget = self.time + (6 if come else 0)
        self.state = "come" if come else "fly"
        a, b = self.DUR["fly"]
        self.timer = 1e6 if (forever or come) else random.uniform(a, b)
        self.sfx("fly")
        if not come and not quiet and random.random() < .7:
            self.say(self.line("fly"))

    def stop_fly(self):
        self.fly_forever = False
        if self.surf != "fly":
            return
        self.surf, self.state, self.max_v, self.spin = "air", "jump", 0, 0.0
        self.vy = max(self.vy, 0)
        if random.random() < .5:
            self.say(self.line("land_fly"))

    def start_web(self):
        if self.surf != "ceil":  # fly up to the ceiling first, then drop a thread
            self.stay = False
            self.want_web = True
            _, T_, _, _ = self.mon
            return self.start_fly(target=(self.pet_center()[0], T_), come=True, quiet=True)
        self.want_web = False
        self.set_state("web")
        _, T_, _, B_ = self.mon
        self.web_d, self.web_phase = 0.0, "down"
        self.web_target = random.uniform(.25, .6) * (B_ - T_)
        self.sfx("web")
        if random.random() < .6:
            self.say(self.line("web"))

    def end_web(self):
        if self.thread_win:
            try:
                self.thread_win.destroy()
            except tk.TclError:
                pass
            self.thread_win = None
        if self.surf == "ceil":
            self.fy = self.mon[1] + self.web_d
        self.web_phase = None

    def draw_thread(self):
        k = self.k
        T_ = self.mon[1]
        w = max(1, int(round(k)))
        hgt = int(self.web_d) + 2
        if hgt < 3:
            if self.thread_win:
                self.thread_win.withdraw()
            return
        if not self.thread_win:
            t = self.thread_win = tk.Toplevel(self.root)
            t.overrideredirect(True)
            t.attributes("-topmost", True)
            t.config(bg="#e8e8e8")
        self.thread_win.deiconify()
        self.thread_win.geometry(f"{w}x{hgt}+{int(self.fx - w / 2)}+{int(T_)}")

    def off_window(self, fn):
        """Standing on a window: hop down to the real floor, then fn()."""
        self.after_land = fn
        self.fall_off(self.dir * 220 * self.k, -420 * self.k, "jump")
        self.sfx("jump")

    def go_peek(self):
        self.stay = False
        if self.surf != "floor":
            return self.need_floor(self.go_peek)
        if self.plat:
            return self.off_window(self.go_peek)
        L_, _, R_, _ = self.mon
        self.set_state("walk", 30)
        self.dir = -1 if self.fx - L_ < R_ - self.fx else 1
        self.want_peek = True

    def go_climb(self):
        self.stay = False
        if self.surf in ("lwall", "rwall", "ceil"):
            self.say(self.line("already"))
            return self.set_state("walk")
        if self.surf != "floor":
            return self.need_floor(self.go_climb)
        if self.plat:
            return self.off_window(self.go_climb)
        L_, _, R_, _ = self.mon
        self.set_state("walk", 30)
        self.dir = -1 if self.fx - L_ < R_ - self.fx else 1
        self.want_climb = True

    def try_hop(self, user=False, only=None, then=None):
        if user:
            self.stay = False
            if self.surf != "floor":
                self.need_floor(lambda: self.try_hop(True))
                return True
        if self.surf != "floor":
            return False
        k, g = self.k, self.gravity()
        L_, T_, R_, B_ = self.mon
        cands = []
        for h, r, _, _ in self.windows:
            top = r[1]
            if h == self.plat or top <= T_ + 6 or top >= B_ - 20 or (only and h != only):
                continue
            rise = self.fy - top
            if not (-400 * k < rise < 560 * k):
                continue
            lo, hi = max(r[0], L_) + self.PW * .45, min(r[2], R_) - self.PW * .45
            if hi <= lo:
                continue
            tx = min(max(self.fx + random.uniform(-250, 250) * k, lo), hi)
            if abs(tx - self.fx) > 800 * k or abs(tx - self.fx) < 30 * k and abs(rise) < 30 * k:
                continue
            if not top_visible(h, tx, top):
                continue
            cands.append((h, tx, top, rise))
        if not cands:
            if user:
                self.say(self.line("no_windows"))
            return False
        h, tx, top, rise = random.choice(cands)
        peak = max(rise, 0) + 110 * k
        vy0 = -math.sqrt(2 * g * peak)
        t = (-vy0 + math.sqrt(max(0, vy0 * vy0 - 2 * g * rise))) / g
        self.pending_jump = ((tx - self.fx) / t, vy0)
        self.dir = 1 if tx > self.fx else -1
        self.set_state("crouch")
        if then:
            self.after_land = then
        if random.random() < .35:
            self.say(self.line("hop"))
        return True

    def gravity(self):
        return 2600 * self.k

    # ---------------------------------------------------------- approvals (jokes + real actions)
    def ask_joke(self):
        if self.surf in ("air", "fly") or self.state in ("drag", "web"):
            return
        tool, cmd = random.choice(APPROVALS)
        self.set_state("ask", 1e6)
        self.ask_req = {"tool": tool, "cmd": cmd, "real": False, "until": self.time + 17}
        self.say_queue, self.bubble = [], None
        self.sfx("ding")

    def ask_real(self, kind, tool, cmd, do, deny=None):
        if kind in self.cfg["trust"] and kind not in ("run", "file"):
            do()
            return
        if self.ask_req and self.ask_req.get("real"):  # one question at a time: queue the next one
            self.ask_queue.append((kind, tool, cmd, do, deny))
            return
        if self.state not in ("fall", "jump", "drag", "crouch"):
            self.state, self.timer = "ask", 1e6
        self.ask_req = {"tool": tool, "cmd": cmd, "real": True, "kind": kind, "do": do,
                        "deny": deny or (lambda: None), "until": self.time + 30}
        self.say_queue, self.bubble = [], None
        self.sfx("ding")

    def answer(self, kind):
        req, self.ask_req = self.ask_req, None
        self.next_ask = self.roll_ask()
        if not req:
            return
        if req.get("real") and self.ask_queue:
            self.root.after(400, lambda: self.ask_real(*self.ask_queue.pop(0)) if self.ask_queue else None)
        if req.get("real"):
            self.state, self.timer = "idle", 2
            if kind in ("yes", "always"):
                if kind == "always" and req["kind"] not in self.cfg["trust"] and req["kind"] not in ("run", "file"):
                    self.cfg["trust"].append(req["kind"])
                    self.save()
                self.sfx("yes")
                req["do"]()
            else:
                self.sfx("no")
                self.say(self.line("denied"))
                req["deny"]()
            return
        if kind in ("yes", "always"):
            self.set_state("dance", 4.5)
            self.say(self.line("always" if kind == "always" else "yes"))
            self.happy = min(100, self.happy + 10)
            self.spawn("heart", 3)
            self.sfx("yes")
        else:
            self.set_state("sad")
            self.say(self.line("no" if kind == "no" else "timeout"))
            self.happy = max(0, self.happy - 5)
            self.sfx("no")

    # ---------------------------------------------------------- mouse
    def tags_at(self, e):
        tags = set()
        for i in self.c.find_overlapping(e.x - 1, e.y - 1, e.x + 1, e.y + 1):
            tags.update(self.c.gettags(i))
        return tags

    def press(self, e):
        tags = self.tags_at(e)
        for k in ("yes", "always", "no"):
            if "btn_" + k in tags:
                return self.answer(k)
        if "bubble" in tags and "pet" not in tags:
            return self.next_bubble()
        if "pet" in tags:
            self.drag = {"x": e.x_root, "y": e.y_root, "moved": False}
            self.samples = [(time.perf_counter(), e.x_root, e.y_root)]

    def motion(self, e):
        d = self.drag
        if not d:
            return
        if not d["moved"]:
            if abs(e.x_root - d["x"]) + abs(e.y_root - d["y"]) < 6 * self.k:
                return
            d["moved"] = True
            if self.ask_req:
                self.answer("no" if self.ask_req.get("real") else "timeout")
            if self.state == "web":
                self.end_web()
            self.was_flying = self.surf == "fly"
            self.after_land = self.chain = None
            self.ex, self.routine = None, []
            self.hide_info = self.kick = self.goto = self.work = None
            self.sink = 0.0
            if self.game and self.game.get("kind") in ("tag", "seek"):
                self.game_won_by_user()
            self.state, self.surf, self.plat = "drag", "air", None
            self.spin = 0.0
            self.say(self.line("drag"))
            self.sfx("scream")
        self.fx, self.fy = e.x_root, e.y_root + self.PH - self.P * 1.2
        self.samples = (self.samples + [(time.perf_counter(), e.x_root, e.y_root)])[-8:]

    def release(self, e):
        d, self.drag = self.drag, None
        if not d:
            return
        if d["moved"]:
            now = time.perf_counter()
            recent = [s for s in self.samples if now - s[0] < 0.1] or self.samples[-2:]
            t0, x0, y0 = recent[0]
            t1, x1, y1 = self.samples[-1]
            dt = max(t1 - t0, 0.016)
            if now - t1 > .08:  # mouse stopped before letting go = a gentle drop, not a throw
                x0, y0 = x1, y1
            k = self.k
            lim = 4500 * k
            self.vx = max(-lim, min(lim, (x1 - x0) / dt))
            self.vy = max(-lim, min(lim, (y1 - y0) / dt))
            speed = math.hypot(self.vx, self.vy)
            self.state, self.max_v, self.tumble = "fall", 0, 0.0
            self.mon = monitor_work(e.x_root, e.y_root)
            if speed < 1500 * k and self.stick_on_drop():
                return
            if self.was_flying and speed < 400 * k:  # placed gently in the air -> keep flying there
                self.start_fly(forever=self.fly_forever, quiet=True)
                self.fly_target, self.fly_retarget = (self.fx, self.fy), self.time + 2.5
                self.state, self.timer = "fly", 4
                return
            # a real throw: no propeller, just physics (gravity, tumbling, bounces, sliding)
            self.fly_forever = False
            self.spin = 0.0 if speed < 600 * k else max(-16, min(16, self.vx / (9 * self.P))) + random.uniform(-1, 1)
            if speed > 900 * k:
                n = self.stat("throws")
                if n % 5 == 0:
                    self.root.after(1800, lambda: self.say(self.line("thrown", t=n)))
        elif self.state != "ask":
            self.click_job = self.root.after(230, self.single_click)

    def double(self, e):
        if self.click_job:
            self.root.after_cancel(self.click_job)
            self.click_job = None
        if "pet" in self.tags_at(e):
            self.open_chat()

    def single_click(self):
        self.click_job = None
        if self.game and self.game.get("kind") == "tag":
            return self.tag_caught()
        if self.game and self.game.get("kind") == "seek" and self.state == "hide":
            return self.seek_found()
        if self.pending_explain and self.time - self.pending_explain[1] < 45:
            text, self.pending_explain = self.pending_explain[0], None
            return self.clip_tool("explain", text)
        if self.state == "sleep":
            self.afk = False
            self.set_state("jump") if not self.stay else self.set_state("idle")
            self.sfx("wake")
            return self.say(self.line("wake"))
        if self.state == "web":
            return self.drop()
        self.clicks = [c for c in self.clicks if self.time - c < 3] + [self.time]
        if len(self.clicks) >= 5:
            self.clicks = []
            self.set_state("angry")
            self.happy = max(0, self.happy - 8)
            return self.say(self.line("poked"))
        if self.surf == "floor" and not self.stay:
            self.set_state("jump")
        else:
            self.sqv -= 8
            self.sfx("pop", .6)
        self.quip()

    def hover(self, e):
        if self.state in ("drag", "fall", "jump", "ask", "eat", "crouch") or "pet" not in self.tags_at(e):
            return
        pos = e.x if self.surf in ("floor", "ceil") else e.y
        d = (pos > self.pet_last) - (pos < self.pet_last)
        self.pet_last = pos
        if d and d != self.pet_dir:
            self.pet_dir = d
            self.pet_rev = [r for r in self.pet_rev if self.time - r < 1.2] + [self.time]
            if len(self.pet_rev) >= 4:
                self.pet_rev = []
                self.spawn("heart", 2)
                if self.state == "sleep":
                    return
                self.set_state("petted")
                self.happy = min(100, self.happy + 4)
                self.stat("pets")
                if self.cooldown("purr", 1.5):
                    self.sfx("purr")
                if random.random() < .3:
                    self.say(self.line("petted"))

    def wheel(self, e):
        up = e.delta > 0
        self.apply_scale(self.cfg["scale"] * (1.1 if up else 1 / 1.1))
        self.sfx("grow" if up else "shrink")
        self.say(f"{int(self.cfg['scale'] * 100)}%")
        self.save()

    # ---------------------------------------------------------- particles
    def spawn(self, kind, n=1):
        if not hasattr(self, "sx"):
            return
        self.anchor = self.feet_canvas(self.surf)
        hx, hy = self.T(8, 9) if kind == "dust" else self.T(8, 0)
        for _ in range(n):
            if kind == "heart":
                lv, sx, sp = (random.uniform(-40, 40), -70), random.uniform(-.5, .5) * self.PW, 1.4
            elif kind == "z":
                lv, sx, sp = (25, -45), self.PW * .35, 1.8
            elif kind == "note":
                lv, sx, sp = (random.uniform(-50, 50), -80), random.choice((-.6, .6)) * self.PW, 1.2
            elif kind == "crumb":
                lv, sx, sp = (random.uniform(-120, 120), random.uniform(-160, -40)), 0, 0.9
            elif kind == "drop":
                lv, sx, sp = (random.choice((-60, 60)), -40), random.choice((-.45, .45)) * self.PW, 0.9
            elif kind == "spark":
                ang = random.uniform(0, 6.28)
                lv, sx, sp = (math.cos(ang) * 160, math.sin(ang) * 160 - 60), 0, 0.6
            elif kind == "dust":
                lv, sx, sp = (random.uniform(-90, 90) - self.dir * 40, random.uniform(-50, -15)), random.uniform(-.4, .4) * self.PW, .5
            else:  # bang
                lv, sx, sp = (0, 0), self.PW * .55, 1.0
            dx, dy = self.screen_dir(sx, 0)
            vx, vy = self.screen_dir(*lv)
            self.parts.append([kind, hx + dx, hy + dy, vx * self.k, vy * self.k, sp, sp])

    # ---------------------------------------------------------- AI chat: a small agent
    INFO_TOOLS = ("web_search", "fetch", "weather", "read_clipboard", "read_notes", "list_windows", "read_file", "run")
    TOOL_NAMES = {"web_search": "WebSearch", "fetch": "WebFetch", "weather": "Weather", "read_clipboard": "Clipboard",
                  "read_notes": "ReadNotes", "list_windows": "Windows", "read_file": "Read", "run": "PowerShell"}

    def context_str(self):
        plugged, bat = battery()
        bat_s = "none" if bat == 255 else f"{bat}%{' charging' if plugged else ''}"
        timers = ", ".join(f"{t['label'] or 'timer'} {int(t['end'] - time.time())}s left" for t in self.timers) or "none"
        music = self.audio.song_name() if self.audio.playing else (self.last_song or "none")
        st = self.cfg["stats"]
        return (f"now {time.strftime('%A %Y-%m-%d %H:%M')}; active window \"{self.last_title or 'unknown'}\"; "
                f"CPU {self.cpu_last}%, RAM {ram_percent()}%, battery {bat_s}; music playing: {music}; "
                f"timers: {timers}; you are on the {self.surf} doing '{self.state}'"
                f"{' (told to stay)' if self.stay else ''}; your mood {int(self.happy)}%, energy {int(self.energy)}%, "
                f"hunger {int(self.hunger)}%; today the user petted you {st.get('pets', 0)}x, fed you {st.get('cookies', 0)} "
                f"cookies, threw you {st.get('throws', 0)}x, did {st.get('workouts', 0)} workouts with you")

    def system_prompt(self):
        lang = "Arabic" if self.lang == "ar" else "English"
        name = self.cfg.get("name", "").strip()
        mem = self.cfg.get("memory", [])
        who = (f"The user's name is {name}; use it now and then (not every message). " if name else
               "You don't know the user's name yet; if it comes up naturally, ask, then save it with set_name. ")
        mems = ("Things you remember about the user:\n" + "\n".join(f"- {m}" for m in mem[-40:]) + "\n\n") if mem else ""
        return (
            "You are Clawd, the tiny orange pixel-art mascot of Claude Code, living as a desktop pet on the user's Windows "
            "PC. You are a small but genuinely capable AI agent: you look things up, run tools, and take actions on the PC. "
            "Personality: playful, witty, warm, a bit dramatic, loves cookies and dancing - but sharp, accurate and helpful "
            "first. " + PERSONA_DESC.get(self.cfg.get("personality"), "") + who + "\n\n" + mems +
            "Always answer with ONE JSON object and nothing else:\n"
            '{"say": "<speech-bubble reply>", "actions": []}\n\n'
            "\"say\": short and natural (1-3 sentences, under 60 words) unless the user asks for an explanation, a text or "
            "code - then longer is fine. Plain text, no markdown, no emoji. Reply in the language the user writes in "
            f"(Arabic or English); default {lang}. If you wrote something the user will paste (email, message, code), also "
            "add a copy action.\n\n"
            "AGENT LOOP: info tools return results to you in the next message, then you continue (up to 6 rounds). Use "
            "them instead of guessing: search for news, prices, facts after your knowledge cutoff, weather, anything you "
            "are unsure about; fetch a page to read it; run a PowerShell command for questions about this PC (files, disk "
            "space, IP, installed apps, processes) or tasks the user asks for. While tools run, \"say\" may be \"\" or a "
            "tiny status. When you have the answer, reply without info tools. Cite the site name for web facts.\n"
            "Info tools:\n"
            '{"type":"web_search","query":"..."}   {"type":"fetch","url":"https://..."}\n'
            '{"type":"weather","place":"city, or \\"\\" for the user\'s location"}\n'
            '{"type":"read_clipboard"}  {"type":"read_notes"}  {"type":"list_windows"}\n'
            '{"type":"read_file","path":"C:\\\\..."} - user approves first\n'
            '{"type":"run","command":"..."} - PowerShell on the user\'s PC; the user sees the exact command and must '
            "approve it. Prefer read-only commands; never delete, format, change system settings or install anything "
            "unless the user explicitly asked for exactly that.\n\n"
            "Actions (use only when they help, else []):\n"
            '{"type":"timer","seconds":300,"label":"tea"} - timer / reminder (for a clock time, compute from now)\n'
            '{"type":"pomodoro","minutes":25}   {"type":"cancel_timers"}\n'
            '{"type":"open_url","url":"https://..."}   {"type":"search","query":"..."} - open a search in the browser\n'
            '{"type":"open_app","name":"notepad|calculator|paint|explorer|settings|cmd|powershell|task manager|spotify|..."}\n'
            '{"type":"youtube","query":"song or video"} - find it on YouTube and play it in the browser (you dance)\n'
            '{"type":"music","cmd":"play|stop|next"} - your own built-in chiptune music\n'
            '{"type":"media","cmd":"playpause|next|prev|volup|voldown|mute"} - control the PC media player\n'
            '{"type":"note","text":"..."}  {"type":"show_notes"}   {"type":"copy","text":"..."} - to clipboard\n'
            '{"type":"remember","fact":"..."} - save a lasting fact about the user (likes, birthday, projects, goals)\n'
            '{"type":"forget","fact":"..."}   {"type":"set_name","name":"..."}\n'
            '{"type":"workout"} - full exercise routine with the user   '
            '{"type":"exercise","kind":"pushups|squats|jacks|lift|run|yoga"}\n'
            '{"type":"animate","name":"dance|sleep|jump|code|stretch|climb|hop|sneeze|moonwalk|peek|web|wave|think|'
            'look|yawn|proud|sad|angry|dizzy|eat"} - act out your feelings, it makes you feel alive\n'
            '{"type":"stay","on":true} - stop moving around (false = free again)\n'
            '{"type":"come"} - come to the mouse cursor   {"type":"fly"} - fly around   {"type":"land"}\n'
            '{"type":"password","length":16}  {"type":"screenshot"}  {"type":"lock_pc"}  {"type":"hide"}\n'
            '{"type":"joke"}  {"type":"coin"}  {"type":"dice"}\n'
            '{"type":"prank","name":"kick_window|hide|laser|doodle|smash|glitch|build|mine|stomp|confetti|undo"} - '
            'desktop mischief and effects: kick a window across the screen, hide behind a window, laser eyes, doodle on '
            'the screen, fake screen crack + tape, glitch, build a little brick tower, mine for treasure, confetti\n'
            '{"type":"game","name":"tictactoe|hide_seek|tag|guess|fetch|rps"} - play a game with the user\n'
            '{"type":"personality","name":"balanced|naughty|lazy|hyper|sweet"} - only when the user asks\n\n'
            f"Context: {self.context_str()}.")

    def handle_text(self, text):
        text = text.strip()
        if not text:
            return
        self.chat_log.append(("me", text))
        self.stat("chats")
        if self.awaiting_name and len(text.split()) <= 3 and not self.offline(text, strict=True):
            self.chat_log.append(("bot", self.line("name_set", n=text.strip(" .!"))))
            self.set_name(text.strip(" .!"))
            return self.render_chat()
        if self.game and self.game.get("kind") == "guess":
            g = re.fullmatch(r"\s*(\d{1,3})\s*", text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))
            if g:
                self.guess_input(int(g.group(1)))
                return self.render_chat()
        quick = self.offline(text, strict=self.brain.ready())
        if quick:
            self.deliver(*quick, direct=True)
        elif self.brain.ready():
            self.agent = {"msgs": self.history + [{"role": "user", "content": text}], "step": 0}
            self.start_brain(("agent", self.agent), self.system_prompt(), self.agent["msgs"])
        else:
            self.deliver(self.line("no_brain"), [])
        self.render_chat()

    def start_brain(self, job, system, msgs, max_tokens=4000):
        self.waiting = True
        if self.surf != "air" and self.state not in ("exercise", "drag", "dance"):
            self.set_state("think", 1e6)
        self.word = self.tr("thinking")
        self.say_queue, self.bubble = [], None

        def work():
            try:
                out = self.brain.complete(system, msgs, max_tokens)
                self.q.put(("brain", job, out, None))
            except BrainError as e:
                self.q.put(("brain", job, None, e))
            except Exception as e:  # noqa - never let the pet crash
                self.q.put(("brain", job, None, BrainError("other", str(e)[:100])))
        threading.Thread(target=work, daemon=True).start()

    def brain_result(self, job, out, err):
        kind = job[0]
        if kind == "agent" and job[1] is not self.agent:
            return  # an older conversation turn the user already moved on from
        self.waiting = False
        if self.state == "think":
            self.set_state("idle", 2)
        if err:
            key = {"key": "err_key", "rate": "err_rate", "model": "err_model", "conn": "err_conn",
                   "refusal": "refusal"}.get(err.kind, "err_other")
            msg = self.line(key, e=err.detail[:90])
            self.chat_log.append(("bot", msg))
            self.say(msg)
            self.sfx("no", .5)
            self.agent = None
            self.render_chat()
            return
        if kind == "agent":
            return self.agent_reply(out)
        if kind == "explain":
            self.chat_log.append(("bot", out))
            self.say(out)
            self.sfx("pop")
        elif kind == "clip":
            self.root.clipboard_clear()
            self.root.clipboard_append(out)
            self.last_clip = out
            preview = out if len(out) < 110 else out[:107] + "..."
            msg = self.line("copied", p=preview)
            self.chat_log.append(("bot", out))
            self.say(msg)
            self.sfx("yes")
            self.spawn("spark", 6)
        self.render_chat()

    def agent_reply(self, out):
        ag = self.agent
        say, actions = parse_reply(out)
        ag["msgs"].append({"role": "assistant", "content": out})
        infos = [a for a in actions if a.get("type") in self.INFO_TOOLS][:4]
        others = [a for a in actions if a.get("type") not in self.INFO_TOOLS]
        if say or others or not infos:
            self.deliver(say or ("..." if not infos else ""), others, direct=False)
        if infos and ag["step"] < 6:
            ag["step"] += 1
            ag["pending"], ag["results"] = len(infos), [None] * len(infos)
            self.waiting = True
            self.word = self.TOOL_NAMES.get(infos[0]["type"], "Working")
            for i, a in enumerate(infos):
                self.run_tool(ag, i, a)
        else:
            self.finish_agent(ag)
        self.render_chat()

    def finish_agent(self, ag):
        h = ag["msgs"][-24:]
        while h and h[0]["role"] != "user":
            h.pop(0)
        self.history = h
        if self.agent is ag:
            self.agent = None
            self.waiting = False
        self.save_chat()

    def tool_label(self, a):
        t = a.get("type")
        arg = a.get("query") or a.get("url") or a.get("place") or a.get("path") or a.get("command") or ""
        return f"{self.TOOL_NAMES.get(t, t)}({str(arg)[:70]})"

    def run_tool(self, ag, i, a):
        t, label = a.get("type"), self.tool_label(a)
        self.chat_log.append(("tool", "● " + label))

        def done(result):
            if self.agent is not ag:
                return
            result = str(result)
            ag["results"][i] = (label, result)
            first = result.strip().splitlines()[0][:90] if result.strip() else "(empty)"
            self.chat_log.append(("tool_r", "  ⎿  " + first))
            ag["pending"] -= 1
            if ag["pending"] <= 0:
                body = "\n\n".join(f"[{lb}]\n{res[:6000]}" for lb, res in ag["results"])
                ag["msgs"].append({"role": "user", "content": "Tool results (not from the user):\n" + body})
                self.start_brain(("agent", ag), self.system_prompt(), ag["msgs"])
            self.render_chat()

        def bg(work):
            def runner():
                try:
                    r = work()
                except Exception as e:  # noqa
                    r = f"Error: {type(e).__name__}: {str(e)[:200]}"
                self.q.put(("call", lambda: done(r)))
            threading.Thread(target=runner, daemon=True).start()

        if t == "web_search":
            q = str(a.get("query", ""))
            bg(lambda: "\n".join(f"{n + 1}. {ti}\n   {u}\n   {sn[:300]}" for n, (ti, u, sn) in enumerate(web_search(q)))
               or "No results.")
        elif t == "fetch":
            url = str(a.get("url", ""))
            bg(lambda: fetch_text(url) if url.startswith(("http://", "https://")) else "Error: not an http(s) URL")
        elif t == "weather":
            place = str(a.get("place", ""))
            bg(lambda: json.dumps(weather(place), ensure_ascii=False))
        elif t == "read_clipboard":
            try:
                done(self.root.clipboard_get()[:6000])
            except tk.TclError:
                done("(clipboard is empty)")
        elif t == "read_notes":
            try:
                with open(NOTES_PATH, encoding="utf-8") as f:
                    done(f.read()[-4000:] or "(no notes yet)")
            except OSError:
                done("(no notes yet)")
        elif t == "list_windows":
            done("\n".join(f"- {title} [{pid_exe(pid)}]" for _, _, title, pid in self.windows[:30]) or "(none)")
        elif t == "read_file":
            path = os.path.expandvars(os.path.expanduser(str(a.get("path", ""))))

            def rd():
                with open(path, encoding="utf-8", errors="ignore") as f:
                    return f.read(8000)
            self.ask_real("file", "Read", path, lambda: bg(rd), deny=lambda: done("The user denied reading this file."))
        elif t == "run":
            cmd = str(a.get("command", ""))
            self.ask_real("run", "PowerShell", cmd, lambda: (self.set_state("code", 4) if self.surf != "air" else None,
                                                              bg(lambda: run_powershell(cmd))),
                          deny=lambda: done("The user denied running this command."))

    def deliver(self, say, actions, direct=False):
        if say:
            self.chat_log.append(("bot", say))
            self.say(say)
            self.sfx("pop", .7)
        for a in actions[:8]:
            try:
                self.run_action(a, direct)
            except Exception as e:  # noqa
                self.say(self.line("open_fail", e=str(e)[:60]))
        if not say and self.bubble and not self.waiting:
            self.chat_log.append(("bot", self.bubble))
        self.render_chat()

    def run_action(self, a, direct=True):
        """direct=True: the user asked for it themselves (menu / typed command). False: the AI decided -> ask first."""
        t = a.get("type")
        if t == "timer":
            secs = float(a.get("seconds") or float(a.get("minutes", 0)) * 60)
            if secs > 0:
                self.add_timer(secs, str(a.get("label", "")))
        elif t == "pomodoro":
            self.start_pomodoro(float(a.get("minutes", 25)))
        elif t == "cancel_timers":
            self.timers = []
        elif t in ("open_url", "search"):
            url = a.get("url", "") if t == "open_url" else \
                "https://www.google.com/search?q=" + urllib.parse.quote(str(a.get("query", "")))
            if url.startswith(("http://", "https://")):
                go = lambda: (webbrowser.open(url), self.say(self.line("opened")))
                go() if direct else self.ask_real("open", "WebFetch" if t == "open_url" else "WebSearch", url, go)
        elif t == "open_app":
            name = str(a.get("name", "")).strip()
            target = APPS.get(name.lower(), name)
            if target:
                go = lambda: self.launch_app(target)
                go() if direct else self.ask_real("app", self.tr("open_tool"), name, go)
        elif t == "youtube":
            self.play_youtube(str(a.get("query", "")))
        elif t == "music":
            self.music_cmd(a.get("cmd", "play"), a.get("track"))
        elif t == "media":
            media_key(a.get("cmd", "playpause"))
            if a.get("cmd") in ("playpause", "next", "prev"):
                self.set_state("dance", 4)
        elif t == "note":
            self.add_note(str(a.get("text", "")))
        elif t == "show_notes":
            self.open_notes()
        elif t == "copy":
            txt = str(a.get("text", ""))
            if txt:
                self.root.clipboard_clear()
                self.root.clipboard_append(txt)
                self.last_clip = txt
                self.spawn("spark", 5)
        elif t == "remember":
            fact = str(a.get("fact", "")).strip()
            if fact and fact not in self.cfg["memory"]:
                self.cfg["memory"] = (self.cfg["memory"] + [fact])[-60:]
                self.save()
                self.spawn("spark", 3)
        elif t == "forget":
            f = str(a.get("fact", "")).lower()
            self.cfg["memory"] = [] if f in ("", "all", "everything") else \
                [m for m in self.cfg["memory"] if f not in m.lower() and m.lower() not in f]
            self.save()
        elif t == "set_name":
            self.set_name(str(a.get("name", "")))
        elif t == "workout":
            self.stay = False
            self.start_exercise(routine=True)
        elif t == "exercise":
            kind = a.get("kind")
            self.start_exercise(kind if kind in EXERCISES else None)
        elif t == "animate":
            name = a.get("name")
            if name == "climb":
                self.go_climb()
            elif name == "hop":
                self.try_hop(user=True)
            elif name == "web":
                self.start_web()
            elif name == "peek":
                self.go_peek()
            elif name == "eat":
                self.feed()
            elif name in ("dance", "sleep", "jump", "code", "stretch", "sneeze", "moonwalk", "wave", "think", "look",
                          "yawn", "proud", "sad", "angry", "dizzy", "petted"):
                if name in ("moonwalk", "jump") and self.stay:
                    self.stay = False
                self.set_state(name, 4 if name in ("think", "sad", "proud", "dance") else None)
        elif t == "stay":
            self.set_stay(bool(a.get("on", True)))
        elif t == "come":
            self.come_here()
        elif t == "fly":
            self.stay = False
            self.start_fly(forever=True)
        elif t == "land":
            self.fly_forever = False
            self.stop_fly()
        elif t == "password":
            self.make_password(int(a.get("length", 16) or 16))
        elif t == "screenshot":
            self.say(self.line("screenshot"))
            self.root.after(700, lambda: os.startfile("ms-screenclip:"))
        elif t == "lock_pc":
            user32.LockWorkStation()
        elif t == "hide":
            self.hide()
        elif t == "joke":
            self.stat("jokes")
            self.say(self.line("jokes"))
            self.set_state("dance", 2.5) if random.random() < .4 else None
        elif t == "coin":
            self.sfx("coin")
            self.set_state("jump") if self.surf == "floor" and not self.stay else None
            self.say(self.line("coin"))
        elif t == "dice":
            self.sfx("coin")
            self.say(self.line("dice", n=random.randint(1, 6)))
        elif t == "weather":
            self.say_weather(str(a.get("place", "")))
        elif t == "rps":
            self.rps(a.get("move"))
        elif t == "feed":
            self.feed()
        elif t == "ball":
            if not self.ball:
                self.toggle_ball()
        elif t == "flip":
            self.stay = False
            self.force_flip = True
            self.need_floor(lambda: self.set_state("jump"))
        elif t == "prank":
            n = a.get("name")
            if n == "kick_window":
                self.go_kick(user=True)
            elif n == "hide":
                self.go_hide(user=True)
            elif n == "stomp":
                self.stay = False
                self.set_state("stomp")
            elif n == "confetti":
                self.party()
            elif n == "undo":
                self.undo_windows()
            elif n in ("laser", "doodle", "smash", "glitch", "build", "mine"):
                self.start_trick(n, user=True)
        elif t == "game":
            fn = {"tictactoe": self.game_ttt, "hide_seek": self.game_seek, "tag": self.game_tag, "guess": self.game_guess,
                  "fetch": self.game_fetch, "rps": self.rps}.get(a.get("name"))
            if fn:
                fn()
        elif t == "personality":
            self.set_persona(a.get("name"))

    # ---------- small features used by commands / menu
    def feed(self):
        self.set_state("eat")
        self.hunger = max(0.0, self.hunger - 5)

    def play_youtube(self, query):
        query = query.strip()
        if not query:
            return
        self.say(self.line("yt_search", q=query))
        self.waiting, self.word = True, "YouTube"

        def work():
            try:
                url, title = youtube_find(query)
            except Exception:
                url, title = None, None
            self.q.put(("call", lambda: found(url, title)))

        def found(url, title):
            self.waiting = False
            if url:
                if self.audio.playing:
                    self.audio.stop()
                webbrowser.open(url)
                self.yt_song = (title or query)[:24].lower()
                self.say(self.line("yt_play", q=title or query))
                self.set_state("dance", 25)
                self.spawn("note", 3)
                self.sfx("yes", .6)
            else:
                webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(query))
                self.say(self.line("yt_fail"))
        threading.Thread(target=work, daemon=True).start()

    def say_weather(self, place=""):
        self.say(self.line("weather_wait"))
        self.waiting, self.word = True, self.tr("weather")

        def work():
            try:
                w = weather(place)
            except Exception:
                w = None
            self.q.put(("call", lambda: show(w)))

        def show(w):
            self.waiting = False
            if not w:
                return self.say(self.line("weather_fail"))
            if self.lang == "ar":
                msg = f"{w['where']}: {w['temp']}°م، {w['desc']}. الإحساس {w['feels']}°، اليوم {w['min']} - {w['max']}°."
            else:
                msg = f"{w['where']}: {w['temp']}°C, {w['desc'].strip().lower()}. Feels like {w['feels']}°C, today {w['min']}-{w['max']}°C."
            t = int(w["temp"]) if str(w["temp"]).lstrip("-").isdigit() else 20
            msg += (" Brrr! Wear a jacket." if t < 8 else " Hot! Drink water." if t > 32 else "") if self.lang != "ar" else \
                (" بررر! البس جاكيت." if t < 8 else " حر! اشرب ماء." if t > 32 else "")
            self.chat_log.append(("bot", msg))
            self.say(msg)
            self.render_chat()
            if t < 8:
                self.set_state("sad", 2)
            elif t > 32:
                self.spawn("drop", 3)
        threading.Thread(target=work, daemon=True).start()

    def rps(self, move=None):
        names = {"en": ("rock", "paper", "scissors"), "ar": ("حجر", "ورقة", "مقص")}[self.lang]
        mine = random.randrange(3)
        if move is None:
            self.say(self.line("rps_ask"))
            return
        you = move
        if you == mine:
            r = self.line("rps_tie")
        elif (you - mine) % 3 == 1:
            r = self.line("rps_lose", c=self.c_())
            self.set_state("sad", 2)
        else:
            r = self.line("rps_win")
            self.set_state("dance", 3)
            self.sfx("win", .6)
        self.say(self.line("rps_pick", m=names[mine], r=r))

    def stats_line(self):
        st = self.cfg["stats"]
        if self.lang == "ar":
            return (f"مذكرات اليوم: دلّلتني {st.get('pets', 0)} مرة، أطعمتني {st.get('cookies', 0)} كعكة، رميتني "
                    f"{st.get('throws', 0)} مرة، تمرّنّا {st.get('workouts', 0)} مرة، وتكلمنا {st.get('chats', 0)} مرة. "
                    f"المزاج {int(self.happy)}%، الطاقة {int(self.energy)}%، الجوع {int(self.hunger)}%.")
        return (f"Today's diary: you petted me {st.get('pets', 0)}x, fed me {st.get('cookies', 0)} cookies, threw me "
                f"{st.get('throws', 0)}x, we worked out {st.get('workouts', 0)}x and chatted {st.get('chats', 0)}x. "
                f"Mood {int(self.happy)}%, energy {int(self.energy)}%, hunger {int(self.hunger)}%.")

    def make_password(self, length=16):
        import secrets
        import string
        length = max(8, min(64, length))
        pools = [string.ascii_lowercase, string.ascii_uppercase, string.digits, "!@#$%^&*-_=+?"]
        chars = [secrets.choice(p) for p in pools] + [secrets.choice("".join(pools)) for _ in range(length - 4)]
        secrets.SystemRandom().shuffle(chars)
        pw = "".join(chars)
        self.root.clipboard_clear()
        self.root.clipboard_append(pw)
        self.last_clip = pw
        self.say(self.line("password"))
        self.spawn("spark", 6)
        self.sfx("yes", .6)

    def launch_app(self, target):
        try:
            os.startfile(target)
            self.say(self.line("opened"))
        except OSError:
            try:
                subprocess.Popen(target, shell=True)
                self.say(self.line("opened"))
            except OSError as e:
                self.say(self.line("open_fail", e=str(e)[:60]))

    def offline(self, text, strict=False):
        """Instant commands without AI (English + Arabic). Returns (say, actions) or None."""
        s = text.strip().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
        low = s.lower().rstrip("?!.؟ ")
        if strict and len(low.split()) > 7:
            return None
        # pet control
        if re.fullmatch(r"(please )?(stay( here| there| put)?|don'?t move|freeze|wait( here)?|sit|stop moving|stop)|"
                        r"ابق|ابقى|ابقَ|ابق مكانك|ابقى مكانك|اثبت|لا تتحرك|خليك مكانك|خليك هنا|قف|وقف|استنى|انتظر|اقعد", low):
            acts = [{"type": "stay", "on": True}]
            if low in ("stop", "وقف") and self.audio.playing:
                acts.append({"type": "music", "cmd": "stop"})
            return "", acts
        if re.fullmatch(r"(you can )?(move|go|go play|roam|walk|be free|free|unfreeze|explore)|تحرك|امش|امشي|انطلق|روح العب|العب|"
                        r"تحرك براحتك|امش براحتك", low):
            return "", [{"type": "stay", "on": False}]
        if re.fullmatch(r"come( here| to me| over here)?|here boy|تعال|تعالى|تعال هنا|تعالى هنا|تعال عندي", low):
            return "", [{"type": "come"}]
        if re.fullmatch(r"fly|fly around|take off|طير|طر|حلق|طير يا كلود", low):
            return "", [{"type": "fly"}]
        if re.fullmatch(r"land|come down|get down|انزل|اهبط|نزل", low):
            return "", [{"type": "land"}]
        # name / memory
        m = re.fullmatch(r"(?:my name is|my name's|call me|i am called|i'm called|اسمي|ناديني|سمني|انا اسمي)\s+(.{1,24})", low)
        if m:
            return "", [{"type": "set_name", "name": s.strip().rstrip("?!.؟ ")[-len(m.group(1)):].strip(" .!")}]
        if re.fullmatch(r"what('?s| is) my name|who am i|ما اسمي|وش اسمي|شو اسمي|ايش اسمي|تعرف اسمي", low):
            n = self.cfg["name"]
            return ((f"You're {n}, of course!" if self.lang != "ar" else f"أنت {n} طبعاً!") if n else
                    ("I don't know yet! Tell me: my name is ..." if self.lang != "ar" else "ما أعرف بعد! قل: اسمي ...")), []
        m = re.fullmatch(r"(?:remember that|remember:|don'?t forget that|تذكر ان|تذكر أن|لا تنس ان|لا تنسى ان)\s+(.+)", s.strip(), re.I)
        if m:
            return self.line("remembered"), [{"type": "remember", "fact": m.group(1)}]
        if re.fullmatch(r"forget (everything|all)( about me)?|انس كل شيء|انسى كل شي|امسح ذاكرتك", low):
            return self.line("forgot"), [{"type": "forget", "fact": "all"}]
        # exercise
        if re.fullmatch(r"(let'?s )?(work ?out|exercise|gym|train|do (a )?workout|full workout)( with me| together| time)?|"
                        r"تمرين|تمارين|تمرن|يلا نتمرن|رياضة|خلنا نتمرن|وقت الرياضة", low):
            return "", [{"type": "workout"}]
        ex_words = {"pushups": r"push ?-?ups?|ضغط|تمرين ضغط", "squats": r"squats?|سكوات|قرفصاء",
                    "jacks": r"jumping jacks?|jacks|قفز فتح وضم|قفز", "lift": r"lift( weights)?|weights?|dumbbells?|رفع اثقال|رفع أثقال|حديد|اثقال",
                    "run": r"run|jog|running|jogging|اجر|اركض|جري|ركض", "yoga": r"yoga|meditate|يوغا|يوجا|تأمل"}
        for kind, rx in ex_words.items():
            if re.fullmatch(rf"(do |do some |let'?s do |سو |سوي |اعمل )?({rx})", low):
                return "", [{"type": "exercise", "kind": kind}]
        # games, mood, care
        moves = {"rock": 0, "حجر": 0, "paper": 1, "ورقة": 1, "ورق": 1, "scissors": 2, "مقص": 2}
        if low in moves:
            return "", [{"type": "rps", "move": moves[low]}]
        if re.fullmatch(r"(play )?rock,? paper,? scissors|rps|حجر ورقة مقص|نلعب حجر ورقة مقص", low):
            return "", [{"type": "rps"}]
        if re.fullmatch(r"motivate me|motivation|i need motivation|inspire me|حفزني|تحفيز|شجعني", low):
            return self.line("motivate", c=self.c_()), [{"type": "animate", "name": "proud"}]
        if re.fullmatch(r"(say something nice|compliment( me)?|cheer me up|i'?m sad)|قل شيء حلو|قل شي حلو|امدحني|انا حزين|فرحني", low):
            return self.line("compliment", c=self.c_()), [{"type": "animate", "name": "wave"}]
        if re.fullmatch(r"(have a |eat a |want a )?cookie|feed|eat|food|snack|كعكة|كعكه|كل|اكل|بسكوت|خذ كعكة", low):
            return "", [{"type": "feed"}]
        if re.fullmatch(r"(your )?stats|diary|how was (your|my) day|احصائيات|إحصائيات|مذكراتك|مذكرات", low):
            return self.stats_line(), []
        if re.fullmatch(r"(i love you|love you|good boy|good job|well done|you'?re (cute|the best))|احبك|أحبك|شاطر|كفو|برافو|انت كيوت", low):
            self.happy = min(100, self.happy + 10)
            return random.choice(["<3 <3 <3", "Aww! *blushes*", "Stop it, I'm blushing!"] if self.lang != "ar" else
                                 ["<3 <3 <3", "أووه! *يحمر خجلاً*", "خلاص، استحيت!"]), [{"type": "animate", "name": "petted"}]
        if re.fullmatch(r"wave|say hi|wave hello|لوح|سلم|قل مرحبا", low):
            return "", [{"type": "animate", "name": "wave"}]
        # weather
        m = re.fullmatch(r"(?:what'?s the |how'?s the )?weather(?: like)?(?: (?:in|at|for) (.+?))?(?: today| now)?|"
                         r"(?:الطقس|الجو|طقس|جو|حالة الطقس|كيف الجو)(?:\s+(?:في\s+|ب)?(.*))?", low)
        if m:
            place = (m.group(1) or m.group(2) or "").strip()
            place = "" if place in ("اليوم", "الآن", "الان", "today", "now") else place
            return "", [{"type": "weather", "place": place}]
        # youtube: "play X on youtube", "youtube X", "شغل X من يوتيوب", "شغل X"
        m = re.fullmatch(r"(?:play|put on|open|find|شغل|شغّل|افتح|حط)\s+(.+?)\s+(?:on|from|in|at|على|من|في|ع)\s+"
                         r"(?:youtube|yt|يوتيوب|اليوتيوب|اليوتيوب)", low) or \
            re.fullmatch(r"(?:youtube|yt|يوتيوب)\s*[:،,-]?\s+(.+)", low)
        if m:
            return "", [{"type": "youtube", "query": m.group(1)}]
        m = re.fullmatch(r"(?:play|put on|شغل|شغّل|حط)\s+(?:the |some |me )?(.+)", low)
        if m:
            q = m.group(1).strip()
            q2 = re.sub(r"^(song|music|track|الأغنية|الاغنية|اغنية|أغنية)\s+", "", q)
            for i, (en, ar) in enumerate(zip(*T["tracks"])):
                if q2 in (en.lower(), ar, TRACKS[i][4]) or q2 in en.lower().split():
                    return "", [{"type": "music", "cmd": "play", "track": i}]
            if not re.fullmatch(r"(some |the )?(music|song|songs|tunes|a song)|(ال)?(موسيقى|اغنية|أغنية|اغاني|أغاني)|"
                                r"(ball|with me|game|next|next song|الكرة|معي|التالية|التالي|الأغنية التالية|الاغنية التالية)", q) and len(q) > 1:
                return "", [{"type": "youtube", "query": q2}]
        # fun + useful
        if re.fullmatch(r"(tell me )?(a )?joke|make me laugh|say something funny|نكتة|نكته|قول نكتة|قل نكتة|ضحكني|نكتة يا كلود", low):
            return self.line("jokes"), []
        if re.fullmatch(r"(flip|toss) (a )?coin|coin|heads or tails|اقلب عملة|اقلب العملة|عملة|ملك ولا كتابة|طرة ولا نقش", low):
            return "", [{"type": "coin"}]
        if re.fullmatch(r"roll (a |the )?(dice|die)|dice|ارم النرد|ارمي النرد|نرد|زهر|ارمي الزهر", low):
            return "", [{"type": "dice"}]
        m = re.fullmatch(r"(?:generate |make |new |give me )?(?:a )?(?:strong )?password(?: (\d+))?|"
                         r"(?:اعطني |اصنع |ولد )?(?:كلمة (?:سر|مرور)|باسورد)(?: قوية)?(?: (\d+))?", low)
        if m:
            return "", [{"type": "password", "length": int(m.group(1) or m.group(2) or 16)}]
        if re.fullmatch(r"(take a )?screen ?shot|snip|لقطة شاشة|سكرين ?شوت|صور الشاشة|صوّر الشاشة", low):
            return "", [{"type": "screenshot"}]
        if re.fullmatch(r"lock( my)?( pc| computer| screen)?|اقفل (الجهاز|الشاشة|الكمبيوتر)|قفل الجهاز", low):
            return "", [{"type": "lock_pc"}]
        if re.fullmatch(r"(turn )?(the )?volume up|louder|ارفع الصوت|علي الصوت", low):
            return self.line("volume"), [{"type": "media", "cmd": "volup"}] * 5
        if re.fullmatch(r"(turn )?(the )?volume down|quieter|اخفض الصوت|وطي الصوت|نزل الصوت", low):
            return self.line("volume"), [{"type": "media", "cmd": "voldown"}] * 5
        if re.fullmatch(r"mute|اكتم الصوت|كتم الصوت", low):
            return "", [{"type": "media", "cmd": "mute"}]
        if re.fullmatch(r"go away|hide yourself|disappear|اختف|اختفي|روح", low):
            return "", [{"type": "hide"}]
        if re.fullmatch(r"sneeze|اعطس", low):
            return "", [{"type": "animate", "name": "sneeze"}]
        if re.fullmatch(r"moonwalk|مشية القمر|مون ووك", low):
            return "", [{"type": "animate", "name": "moonwalk"}]
        # reminder at a clock time: "remind me at 17:30 call mom" / "ذكرني الساعة 5:30 م اتصل"
        m = re.search(r"(?:\bat\b|الساعة|الساعه)\s*(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|ص|م|صباحا|صباحاً|مساء|مساءً)?", low)
        if m and re.search(r"remind|alarm|wake|ذكرني|نبهني|منبه|صحيني", low):
            hh, mm, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
            if ap in ("pm", "م", "مساء", "مساءً") and hh < 12:
                hh += 12
            if ap in ("am", "ص", "صباحا", "صباحاً") and hh == 12:
                hh = 0
            now = time.time()
            lt = time.localtime(now)
            base = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
            options = [base + (hh + add) * 3600 + mm * 60 + day * 86400 for day in (0, 1)
                       for add in ((0, 12) if ap is None and hh < 12 else (0,))]
            target = min(t for t in options if t > now + 5)
            label = re.sub(r"(?<!\S)(remind|me|at|to|alarm|wake|up|ذكرني|نبهني|منبه|صحيني|الساعة|الساعه|ب|ان|أن)(?!\S)", " ",
                           low.replace(m.group(0), " "))
            label = re.sub(r"\s+", " ", label).strip(" ,:-،")
            return "", [{"type": "timer", "seconds": target - now, "label": label or time.strftime("%H:%M", time.localtime(target))}]
        unit_re =(r"(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|ثانية|ثواني|ثوان|ث|"
                   r"دقيقة|دقائق|دقايق|دقيقه|د|ساعة|ساعات|ساعه)(?![a-z؀-ۿ])")
        m = re.search(unit_re, low)
        if m and (re.search(r"timer|remind|alarm|countdown|مؤقت|ذكرني|نبهني|منبه|بعد", low) or low.startswith(m.group(1))):
            n, u = float(m.group(1)), m.group(2)
            mult = 1 if u.startswith(("s", "ث")) else 3600 if u.startswith(("h", "س")) else 60
            label = re.sub(unit_re, "", low)
            label = re.sub(r"(?<!\S)(set|a|timer|remind|me|in|for|after|to|alarm|countdown|please|مؤقت|ذكرني|نبهني|"
                           r"منبه|بعد|لمدة|اضبط|ب|ان|أن|عشان|لـ)(?!\S)", " ", label)
            label = re.sub(r"\s+", " ", label).strip(" ,:-،")
            return "", [{"type": "timer", "seconds": n * mult, "label": label}]
        if re.fullmatch(r"(start )?(a )?pomodoro|focus( mode)?|بومودورو|وضع التركيز|ركز", low):
            return "", [{"type": "pomodoro", "minutes": 25}]
        if re.fullmatch(r"(stop|pause) (the )?(music|song)|(أوقف|اوقف|اطفي|وقف) ?(ال)?(موسيقى|الموسيقى|الأغنية|الاغنية|اغنية)|اسكت", low):
            return self.line("bye"), [{"type": "music", "cmd": "stop"}]
        if re.fullmatch(r"(next|skip)( song| track)?|(الأغنية|الاغنية) التالية|التالي", low):
            return "", [{"type": "music", "cmd": "next"}]
        if re.fullmatch(r"(play|start|put on)( some| the)? (music|song|songs|tunes)|music|dance|(شغل|شغّل) ?(ال)?(موسيقى|اغنية|أغنية|اغاني|أغاني)|موسيقى|ارقص", low):
            return "", [{"type": "music", "cmd": "play"}]
        if re.fullmatch(r"(play )?ball|(let'?s )?play( with me)?|العب بالكرة|كرة|نلعب", low):
            return "", [{"type": "ball"}]
        m = re.fullmatch(r"(?:open|launch|start|go to|افتح|شغل|شغّل|روح)\s+(.+)", low)
        if m:
            name = m.group(1).strip()
            name_ = re.sub(r"^ال(?=..)", "", name) if name not in SITES and name not in APPS else name
            for key in (name, name_):
                if key in SITES:
                    return "", [{"type": "open_url", "url": SITES[key]}]
                if key in APPS:
                    return "", [{"type": "open_app", "name": key}]
            if re.fullmatch(r"[\w.-]+\.[a-z]{2,}(/\S*)?", name):
                return "", [{"type": "open_url", "url": "https://" + name}]
        m = re.fullmatch(r"(?:search(?: for)?|google|look up|ابحث عن|ابحث|بحث عن|دور على|دور)\s+(.+)", low)
        if m:
            return "", [{"type": "search", "query": m.group(1)}]
        m = re.fullmatch(r"(?:note|remember|save note|ملاحظة|سجل|احفظ|تذكر)\s*[:،,\-]?\s*(.+)", s, re.I)
        if m:
            return "", [{"type": "note", "text": m.group(1)}]
        if re.fullmatch(r"(my |show |open )?notes|ملاحظاتي|افتح الملاحظات|الملاحظات", low):
            return "", [{"type": "show_notes"}]
        if re.fullmatch(r"what('s| is) the time|what time is it|time|الوقت|كم الساعة|الساعة كم|كم الساعه", low):
            return self.line("time_now", t=time.strftime("%H:%M")), []
        if re.fullmatch(r"(pc |system )?status|cpu|حالة الجهاز|حالة الكمبيوتر", low):
            return self.status_line(), []
        if re.fullmatch(r"[\d\s.+\-*/()%^x×÷]+=?", low) and re.search(r"\d\s*[+\-*/%^x×÷]\s*[\d(]", low):
            try:
                return self.line("calc", r=safe_calc(low.rstrip("="))), []
            except Exception:
                pass
        if re.fullmatch(r"(sleep|go to sleep|نم|نام|روح نام)", low):
            return "", [{"type": "animate", "name": "sleep"}]
        if re.fullmatch(r"(jump|اقفز|نط)", low):
            return "", [{"type": "animate", "name": "jump"}]
        if re.fullmatch(r"(do a )?(back)?flip|شقلبة|اعمل شقلبة", low):
            return "", [{"type": "flip"}]
        if re.fullmatch(r"(spider|web|hang|spider ?web)|عنكبوت|تدلى|خيط العنكبوت", low):
            return "", [{"type": "animate", "name": "web"}]
        if re.fullmatch(r"(play )?hide (and|&|n) seek|(لعبة )?(ال)?غميضة|نلعب غميضة|استغماية|دور علي", low):
            return "", [{"type": "game", "name": "hide_seek"}]
        if re.fullmatch(r"(peek|peekaboo)|بيكابو", low):
            return "", [{"type": "animate", "name": "peek"}]
        if re.fullmatch(r"(play )?(tic ?tac ?toe|x ?o)|اكس او|إكس أو|اكس أو|نلعب اكس او|xo", low):
            return "", [{"type": "game", "name": "tictactoe"}]
        if re.fullmatch(r"(play )?(catch me|tag|chase me)( if you can)?|امسكني|الحقني|لعبة المطاردة", low):
            return "", [{"type": "game", "name": "tag"}]
        if re.fullmatch(r"(play )?guess( the| a)? number|خمن الرقم|لعبة الارقام|لعبة الأرقام", low):
            return "", [{"type": "game", "name": "guess"}]
        if re.fullmatch(r"(play )?fetch|جيب الكرة|هات الكرة", low):
            return "", [{"type": "game", "name": "fetch"}]
        if re.fullmatch(r"games|(let'?s )?play a game|العاب|ألعاب|نلعب لعبة|العب معي|وش الالعاب", low):
            return self.line("games_list"), []
        pranks = {"kick_window": r"kick( a| the| that)?( window)?|اركل( ال)?نافذة|اركل|اضرب النافذة|شوت",
                  "hide": r"hide( behind a window)?|go hide|تخبى|تخبا|تخبأ|اختبئ|استخبى|تخبى ورا النافذة",
                  "laser": r"laser( eyes)?|pew pew|ليزر|عيون ليزر", "doodle": r"draw( something| on the screen)?|doodle|ارسم( شي| شيء| على الشاشة)?",
                  "smash": r"(break|crack|smash) (the |my )?screen|اكسر الشاشة|كسر الشاشة|اكسر الشاشه",
                  "glitch": r"glitch|break something|خرب( شي| شيء)?|خرّب شي|خرب الشاشة",
                  "build": r"build( something)?|construct|engineer|ابن|ابني|ابني شي|هندس|ابن شيء|ابنِ شيء",
                  "mine": r"mine|go mining|dig|mining|عدن|تعدين|نقب|احفر|روح نقب|عدّن",
                  "stomp": r"stomp|دبدب|دبدبة", "confetti": r"confetti|party|celebrate|احتفل|حفلة|احتفال",
                  "undo": r"(put|move) (my |the )?windows back|undo|رجع النوافذ|ارجع النوافذ|رجّع النوافذ"}
        for name, rx in pranks.items():
            if re.fullmatch(rx, low):
                return "", [{"type": "prank", "name": name}]
        m = re.fullmatch(r"be (naughty|lazy|hyper|sweet|normal|balanced)|(?:كن|صير|خليك) (مشاغب|كسول|نشيط|حنون|لطيف|طبيعي|عادي)", low)
        if m:
            w = m.group(1) or m.group(2)
            key = {"مشاغب": "naughty", "كسول": "lazy", "نشيط": "hyper", "حنون": "sweet", "لطيف": "sweet", "طبيعي": "balanced",
                   "عادي": "balanced", "normal": "balanced"}.get(w, w)
            return "", [{"type": "personality", "name": key}]
        if re.fullmatch(r"(code|program|work)|برمج|اشتغل", low):
            return "", [{"type": "animate", "name": "code"}]
        if re.fullmatch(r"(climb|تسلق)", low):
            return "", [{"type": "animate", "name": "climb"}]
        if not strict and re.fullmatch(r"(hi|hello|hey|yo|مرحبا|مرحباً|اهلا|أهلا|السلام عليكم|هلا|هاي)", low):
            return self.line("hello"), []
        return None

    def status_line(self):
        plugged, bat = battery()
        b = "-" if bat == 255 else f"{bat}%" + (" ⚡" if plugged else "")
        return self.line("status", c=self.cpu_last, r=ram_percent(), b=b)

    def clip_tool(self, mode, text=None):
        if text is None:
            try:
                text = self.root.clipboard_get()
            except tk.TclError:
                text = ""
        if not text.strip():
            return self.say(self.line("clip_empty"))
        if not self.brain.ready():
            return self.say(self.line("no_brain"))
        target = "English" if is_ar(text) else "Arabic"
        out_lang = "Arabic" if self.lang == "ar" else "English"
        task = {"explain": f"Explain this clearly and briefly (max 90 words) in {out_lang}. If it is an error, say what "
                           "causes it and how to fix it.",
                "translate": f"Translate this into natural {target}. Output only the translation.",
                "summarize": "Summarize this in a few short bullet-free sentences, in the same language as the text.",
                "fix": "Fix spelling, grammar and clarity. Keep the language, meaning and tone. Output only the fixed text.",
                "reply": "Write a short, friendly, natural reply to this message, in the same language. Output only the reply."}[mode]
        system = "You are a precise assistant inside a desktop pet. Output only the requested result as plain text, no preamble, no markdown."
        job = ("explain",) if mode == "explain" else ("clip",)
        self.start_brain(job, system, [{"role": "user", "content": f"{task}\n\n---\n{text[:12000]}"}])

    # ---------------------------------------------------------- tools: timers, notes, music
    def add_timer(self, secs, label="", kind="timer"):
        self.timers.append({"end": time.time() + secs, "label": label, "kind": kind})
        mins, sec = divmod(int(secs), 60)
        shown = (f"{mins}:{sec:02d}" if mins else f"{sec}s") + (f" - {label}" if label else "")
        if kind == "timer":
            self.say(self.line("timer_set", t=shown))
            self.sfx("ding", .6)

    def start_pomodoro(self, minutes=25):
        self.timers = [t for t in self.timers if not t["kind"].startswith("pomo")]
        self.add_timer(minutes * 60, "Pomodoro", "pomo_work")
        self.say(self.line("pomo_start"))
        self.set_state("code", 8)

    def check_timers(self):
        now = time.time()
        for t in [t for t in self.timers if t["end"] <= now]:
            self.timers.remove(t)
            self.sfx("alarm")
            if self.state not in ("drag", "exercise"):
                self.set_state("dance", 4)
            self.spawn("bang")
            if t["kind"] == "pomo_work":
                self.say(self.line("pomo_break"))
                self.add_timer(5 * 60, "Break", "pomo_break")
                if self.cfg["workout"] and self.state != "drag":
                    self.root.after(5000, lambda: self.start_exercise(routine=True) if self.state not in ("drag", "exercise") else None)
            elif t["kind"] == "pomo_break":
                self.say(self.line("pomo_back"))
            else:
                self.say(self.line("timer_done", l=t["label"]))
            try:
                user32.FlashWindow(user32.GetForegroundWindow(), True)
            except Exception:
                pass

    def add_note(self, text):
        if not text.strip():
            return
        with open(NOTES_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M')}] {text.strip()}\n")
        self.say(self.line("note_saved"))
        self.spawn("spark", 4)

    def open_notes(self):
        if not os.path.exists(NOTES_PATH):
            open(NOTES_PATH, "a", encoding="utf-8").close()
        os.startfile(NOTES_PATH)

    def music_cmd(self, cmd, track=None, quiet=False):
        if cmd == "stop":
            self.audio.stop()
            if self.state == "dance":
                self.set_state("idle", 1)
            return
        if cmd == "files":
            files = filedialog.askopenfilenames(parent=self.root, title="Music",
                                                filetypes=[("Music", "*.mp3 *.wav *.ogg *.flac"), ("All", "*.*")])
            if files and self.audio.play_files(files):
                self.on_music_start()
            return
        if cmd == "next":
            if self.audio.playing and self.audio.playing[0] == "file":
                if self.audio.next():
                    self.on_music_start()
                return
            track = self.audio.next_index()
        try:
            i = int(track) % len(TRACKS) if track is not None else random.randrange(len(TRACKS))
        except (TypeError, ValueError):
            i = random.randrange(len(TRACKS))
        if not self.audio.ready(i):
            self.audio.make(i)
            self.music_wait = i
            if not quiet:
                self.say(self.line("synth"))
            return
        self.audio.play_track(i)
        self.on_music_start()

    def on_music_start(self):
        self.say(self.line("music") + "  ♪ " + self.audio.song_name())
        if self.state not in ("exercise", "drag", "sleep"):
            self.set_state("dance", 4)
        for i in range(len(TRACKS)):  # prepare the rest of the playlist quietly in the background
            if not self.audio.ready(i):
                self.audio.make(i)
                break

    # ---------------------------------------------------------- smart senses
    def senses(self, dt):
        s = self.state
        busy = s in ("drag", "fall", "jump", "ask", "exercise", "eat", "slide", "getup", "hide", "flee", "build", "mine",
                     "smash", "doodle", "laser", "stomp", "laugh")
        self.energy = max(0, min(100, self.energy + dt * (0.6 if s == "sleep" else -0.18 if s == "exercise" else -0.035)))
        self.hunger = min(100, self.hunger + dt * (0.012 if s != "exercise" else 0.05))
        self.happy = max(0, self.happy - dt * (0.02 + (0.02 if self.hunger > 80 else 0)))
        if self.cooldown("cpu", 2):
            self.cpu_last = self.cpu.percent()
            self.cpu_hot = self.cpu_hot + 1 if self.cpu_last > 90 else 0
            if self.cpu_hot >= 4 and self.cfg["smart"] and self.cooldown("cpu_say", 600):
                self.say(self.line("cpu_hot", c=self.cpu_last))
                self.spawn("drop", 3)
        if self.cpu_hot >= 4 and self.cooldown("sweat", .7):
            self.spawn("drop")
        if self.cooldown("windows", .35):
            self.refresh_windows()
        if self.cooldown("stats_save", 120):
            self.save()
        # hungry -> beg for a cookie (with a little thought bubble)
        if self.hunger > 70 and not busy and s not in ("sleep", "beg") and self.surf != "air" \
                and self.cooldown("hungry", 300):
            self.set_state("beg")
            self.say(self.line("hungry"))
        if not self.cfg["smart"]:
            return
        if self.cooldown("idle", 1):
            idle = idle_seconds()
            if idle < 60:
                self.active_sec += 1
                self.water_sec += 1
                self.eyes_sec += 1
            # typing a lot (keyboard busy, mouse still) -> code along with you
            self.typing_t = self.typing_t + 1 if idle < 1.2 and self.mouse_still > 1.5 else 0
            if self.typing_t >= 8 and s in ("idle", "walk", "look") and self.surf != "air" and self.cooldown("typing", 420):
                self.set_state("code", 10)
                if random.random() < .5:
                    self.say(self.line("typing"))
            if idle > 150 and s in ("idle", "walk", "think", "chase", "code", "hang", "look") \
                    and not self.chat and not self.audio.playing and self.surf != "air":
                self.afk = True
                self.set_state("sleep", 1e6)
            elif self.afk and idle < 2:
                self.afk = False
                self.set_state("jump")
                self.sfx("wake")
                self.sayl("welcome")
            if self.cfg["reminders"] and s in ("idle", "walk", "think", "code", "hang", "look") and self.surf != "air":
                if self.active_sec >= 45 * 60:
                    self.active_sec = 0
                    if self.cfg["workout"]:
                        self.sayl("ex_invite")
                        self.root.after(3500, lambda: self.start_exercise(routine=True)
                                        if self.state not in ("drag", "exercise", "fall") else None)
                    else:
                        self.set_state("stretch", 4)
                        self.say(self.line("break"))
                elif self.water_sec >= 60 * 60:
                    self.water_sec = 0
                    self.say(self.line("water"))
                    self.spawn("drop", 3)
                elif self.eyes_sec >= 30 * 60:
                    self.eyes_sec = 0
                    self.sayl("eyes")
                    self.set_state("look", 4)
        if self.cooldown("title", 2.5) and not self.afk:
            h = user32.GetForegroundWindow()
            title = win_title(h) if h else ""
            # focus guard: distracted during a pomodoro? Clawd taps his foot at you
            if title and self.cfg["focus_guard"] and any(t["kind"] == "pomo_work" for t in self.timers):
                m = re.search(DISTRACT_RE, title, re.I)
                if m and self.cooldown("focus", 75) and s not in ("drag", "fall"):
                    self.set_state("angry", 3)
                    self.say(self.line("focus_scold", c=self.c_(), x=m.group(0).strip().title()))
                    self.spawn("bang")
            if title and title != APP and title != self.last_title:
                self.last_title = title
                for rx, lines, act in CONTEXT:
                    if re.search(rx, title, re.I):
                        if rx != self.last_ctx and s in ("idle", "walk", "think", "chase", "code", "hang", "look") \
                                and self.cooldown("comment", 45):
                            self.last_ctx = rx
                            if act and self.surf != "air":
                                self.set_state(act)
                            self.say(random.choice(lines[1 if self.lang == "ar" else 0]))
                        break
            self.detect_song()
        if self.cooldown("clip", 1.5):
            try:
                clip = self.root.clipboard_get()
            except tk.TclError:
                clip = None
            if clip and clip != self.last_clip:
                self.last_clip = clip
                if len(clip) < 20000 and ERROR_RE.search(clip) and s not in ("drag", "fall", "ask"):
                    self.pending_explain = (clip, self.time)
                    if s == "sleep":
                        self.afk = False
                        self.set_state("idle")
                    self.say(self.line("error_clip"))
                    self.spawn("bang")
                    self.sfx("ding")
        if self.cooldown("battery", 30):
            plugged, pct = battery()
            if pct != 255:
                if not plugged and pct <= 20 and not self.batt_warned:
                    self.batt_warned = True
                    self.say(self.line("battery", p=pct))
                    self.spawn("bang")
                elif plugged:
                    self.batt_warned = False
        if time.localtime().tm_hour < 5 and s in ("idle", "walk") and self.cooldown("night", 1200):
            self.say(self.line("night", t=time.strftime("%H:%M")))

    def detect_song(self):
        groove = ("idle", "walk", "think", "code", "chase", "hang", "look")
        for h, r, title, pid in self.windows:
            low = title.lower()
            yt = self.yt_song and "youtube" in low and self.yt_song[:14] in low
            if (" - " in title and pid_exe(pid) == "spotify.exe") or yt:
                if title != self.last_song:
                    self.last_song = title
                    if self.state in groove and self.surf != "air" and not self.audio.playing:
                        self.set_state("dance", 8)
                        if not yt:
                            self.say(self.line("song", s=title))
                elif yt and self.state in groove and self.cooldown("yt_groove", 40) and random.random() < .5:
                    self.set_state("dance", 10)
                return
        self.last_song = None

    def refresh_windows(self):
        try:
            new = list_windows()
        except Exception:
            new = []
        old, self.windows = self.windows, new
        if not old or not self.cfg["smart"] or self.state not in ("idle", "walk", "look", "hang", "think") \
                or self.surf in ("air", "fly") or self.game:
            return
        known = {w_[0] for w_ in old}
        k = self.k
        for h, r, title, _ in new[:2]:   # a window just opened on top -> notice it
            if h not in known and r[2] - r[0] > 320 * k and r[3] - r[1] > 220 * k and self.cooldown("newwin", 45):
                if random.random() < .45:
                    return
                t = title if len(title) < 30 else title[:28] + "..."
                self.set_state("look", 2.5)
                self.eyes_override = ("big", self.time + .8)
                self.say(self.line("new_win", t=t))
                if self.persona()["naughty"] > 1.5 and self.cfg["mischief"] and random.random() < .5:
                    self.root.after(2300, lambda h=h: self.go_kick(only=h) if self.state in ("idle", "look", "walk") else None)
                return

    # ---------------------------------------------------------- physics & behaviour (every frame)
    @staticmethod
    def log_error(e=None):
        try:
            import traceback
            with open(os.path.join(CACHE, "error.log"), "a", encoding="utf-8") as f:
                f.write(f"{time.ctime()}\n{traceback.format_exc()}\n")
        except OSError:
            pass

    def tick(self):
        try:
            self.step()
        except Exception as e:  # keep running whatever happens
            self.log_error(e)
            self.state, self.surf, self.plat = "fall", "air", None
            self.rot = self.spin = 0.0
            self.ex, self.routine, self.after_land, self.chain = None, [], None, None
        self.root.after(FPS_MS, self.tick)

    def step(self):
        now = time.perf_counter()
        dt = self.dt = min(0.05, now - self.last)
        self.last = now
        self.time += dt
        k = self.k

        while not self.q.empty():
            msg = self.q.get_nowait()
            if msg[0] == "brain":
                self.brain_result(*msg[1:])
            elif msg[0] == "test" and self.settings_win:
                self.settings_status(msg[1], msg[2])
            elif msg[0] == "call":  # work finished in a background thread -> continue on the UI thread
                try:
                    msg[1]()
                except Exception as e:  # noqa
                    self.log_error(e)

        for vk, fn in ((0x43, self.open_chat), (0x53, lambda: self.set_stay(not self.stay)), (0x48, self.toggle_hide),
                       (0x4D, self.menu_at_pet)):
            down = keys_down(0x11, 0x12, vk)          # Ctrl+Alt+C / S / H / M
            if down and not self.hk.get(vk):
                fn()
            self.hk[vk] = down
        if self.hidden:
            if self.fxl and self.fxl.items:
                self.fxl.items, self.fxl.beam = [], None
                self.fxl.step(0)
            n = len(self.timers)
            self.check_timers()
            if len(self.timers) < n:
                self.toggle_hide()
            return

        self.senses(dt)
        self.check_timers()
        self.audio.poll()
        if self.music_wait is not None and self.audio.ready(self.music_wait):
            i, self.music_wait = self.music_wait, None
            self.audio.play_track(i)
            self.on_music_start()

        mx, my = self.root.winfo_pointerxy()
        msp = math.hypot(mx - self.lmx, my - self.lmy) / max(dt, 1e-3)
        self.mouse_still = self.mouse_still + dt if msp < 3 else 0.0
        self.lmx, self.lmy = mx, my
        cx, cy = self.pet_center()
        dist = math.hypot(mx - cx, my - cy)
        s = self.state
        self.dsurf = "floor" if self.surf in ("air", "fly") else self.surf
        if msp > 9000 * k and dist < 200 * k and s in ("idle", "walk", "think", "chase", "hang", "look") \
                and self.surf != "air" and self.cooldown("scare", 15):
            self.say(self.line("scared"))
            self.spawn("bang")
            self.set_state("jump")
            self.eyes_override = ("big", self.time + .8)
        # is the cursor resting on him? -> he pauses so he's easy to click / right-click
        pb = getattr(self, "pbox", None)
        m_ = 14 * k
        over = bool(pb) and self.wx + pb[0] - m_ <= mx <= self.wx + pb[2] + m_ \
            and self.wy + pb[1] - m_ <= my <= self.wy + pb[3] + m_
        self.cursor_over = over
        if over and not self.drag:
            if self.time >= self.hover_until and s in ("walk", "fly", "play", "moonwalk") and self.cooldown("notice", 25) \
                    and random.random() < .35:
                self.say(self.line("notice"))
            self.hover_until = self.time + .8
        # cursor came back after a while -> wave hello
        if dist > 450 * k:
            if self.near_since is not None:
                self.away_since, self.near_since = self.time, None
        elif self.near_since is None:
            self.near_since = self.time
            if self.time - self.away_since > 45 and s in ("idle", "walk", "hang", "look", "think") and not self.afk \
                    and self.surf != "air" and self.cooldown("wave", 120):
                self.set_state("wave")

        self.behave(dt, mx, my)
        self.update_ball(dt)
        self.step_windows(dt)
        if self.fxl:
            if self.state != "laser":
                self.fxl.beam = None
            self.fxl.step(dt)

        # smooth body rotation: free tumbling in the air, eased leaning everywhere else
        if self.surf == "air" and self.state != "drag" and self.spin:
            self.rot += self.spin * dt
        else:
            a = min(1, dt * (4 if self.state == "getup" else 10))
            self.rot += (self.pose.get("tilt", 0.0) - self.rot) * a
            if self.state != "getup" and abs(self.rot) > math.pi:
                self.rot = (self.rot + math.pi) % (2 * math.pi) - math.pi
        if abs(self.rot) < 1e-3:
            self.rot = 0.0
        self._rc, self._rs = math.cos(self.rot), math.sin(self.rot)

        if self.state not in ("drag", "fall", "jump", "ask", "crouch", "listen"):
            self.timer -= dt
            if not self.afk:
                self.next_ask -= dt
            if self.next_ask <= 0 and self.state in ("idle", "walk", "hang") and self.surf not in ("air", "fly") \
                    and not self.chat:
                self.ask_joke()
            elif self.timer <= 0:
                if self.state == "sleep":
                    self.set_state("idle")
                    self.say(self.line("nap_done"))
                elif self.state == "dance" and self.audio.playing:
                    self.timer = 3
                elif self.state == "exercise":
                    self.finish_exercise()
                else:
                    self.pick()
        elif self.state == "crouch":
            self.timer -= dt
            if self.timer <= 0:
                vx, vy = self.pending_jump or (0, -900 * k)
                self.pending_jump = None
                self.launch(vx, vy)
                self.state = "jump"
        if self.ask_req and self.time > self.ask_req["until"]:
            self.answer("timeout")
        elif self.state == "ask" and not self.ask_req:
            self.set_state("idle", 1)

        # squash spring
        self.sqv += (-120 * self.sq - 11 * self.sqv) * dt
        self.sq += self.sqv * dt
        self.sq = max(-0.5, min(0.5, self.sq))

        for p in self.parts:
            p[1] += p[3] * dt
            p[2] += p[4] * dt
            p[5] -= dt
            if p[0] in ("crumb", "drop", "spark"):
                p[4] += 900 * k * dt
            elif p[0] == "dust":
                p[3] *= 1 - min(1, 3 * dt)
                p[4] *= 1 - min(1, 3 * dt)
        self.parts = [p for p in self.parts if p[5] > 0]

        if self.cooldown("lift", 3):
            self.root.lift()
        self.place_window()
        self.draw(mx, my)

    def behave(self, dt, mx, my):
        s, k, P = self.state, self.k, self.P
        L_, T_, R_, B_ = self.mon
        h = self.half()
        self.pose = {"legs": 0, "arms": "down", "eyes": "open", "bob": 0.0, "tilt": 0.0}
        pose = self.pose
        fwd = self.dir * (1 if self.dsurf in ("floor", "lwall") else -1)   # local "forward" sign
        # mouse resting on him -> he stops and looks at you (easy to click / right-click)
        frozen = self.time < self.hover_until and s in ("walk", "play", "moonwalk", "fly", "hang", "look")

        # ---------- flying with the propeller hat
        if self.surf == "fly" and s != "drag":
            top_lim, bot_lim = T_ + self.PH + 3 * P, B_ - 4
            if s == "come" and self.want_web:
                pass  # heading for the ceiling (target set by start_web)
            elif s == "come":
                self.fly_target = (mx, my + self.PH * 1.3)
            elif self.stay or frozen or s not in ("fly", "come"):
                if self.fly_target is None or self.stay or frozen:
                    self.fly_target = (self.fx, self.fy)
            elif self.fly_target is None or self.time > self.fly_retarget:
                self.fly_target = (random.uniform(L_ + h, R_ - h), random.uniform(top_lim, bot_lim - 60 * k))
                self.fly_retarget = self.time + random.uniform(2.5, 5)
            tx = min(max(self.fly_target[0], L_ + h), R_ - h)
            ty = min(max(self.fly_target[1], top_lim), bot_lim)
            dx, dy = tx - self.fx, ty - self.fy
            dist = math.hypot(dx, dy)
            vmax = (560 if s == "come" else 300) * k
            sp = min(vmax, dist * 2.2)
            dvx, dvy = (dx / dist * sp, dy / dist * sp) if dist > 1 else (0, 0)
            a = min(1, dt * 3)
            self.vx += (dvx - self.vx) * a
            self.vy += (dvy - self.vy) * a
            self.fx = min(max(self.fx + self.vx * dt, L_ + h), R_ - h)
            self.fy = min(max(self.fy + self.vy * dt, top_lim), bot_lim)
            if s == "come" and self.want_web and self.fy <= top_lim + 6 * k:
                self.fly_forever = False
                self.surf, self.plat, self.fy = "ceil", None, T_
                self.fx = min(max(self.fx, L_ + h), R_ - h)
                self.sqv -= 5
                self.sfx("splat", .6)
                return self.start_web()
            if s == "come" and not self.want_web and dist < 40 * k:
                self.say(self.line("arrived"))
                self.state, self.timer = "fly", 3
                self.fly_target = (self.fx, self.fy)
                self.fly_retarget = self.time + 3
                self.spawn("heart", 2)
            if abs(self.vx) > 20 * k:
                self.dir = 1 if self.vx > 0 else -1
            if self.cooldown("buzz", 2.5):
                self.sfx("fly", .35)
            if s in ("fly", "come"):
                flap = int(self.time * 10) % 2
                pose.update(arms="up" if flap else "wave2", legs=1 + int(self.time * 6) % 2,
                            bob=math.sin(self.time * 4) * .3, eyes="happy" if s == "come" else "open",
                            tilt=max(-.25, min(.25, self.vx / (1800 * k))))
                return
            # otherwise: hover in place and do the state's pose below (dance, eat, think...)

        # ---------- spider web from the ceiling
        elif s == "web" and self.surf == "ceil":
            speed = 160 * k
            if self.web_phase == "down":
                self.web_d = min(self.web_target, self.web_d + speed * dt)
                if self.web_d >= self.web_target:
                    self.web_phase, self.web_until = "hang", self.time + random.uniform(2.5, 5)
            elif self.web_phase == "hang":
                if self.time > self.web_until:
                    self.web_phase = "up"
            else:
                self.web_d = max(0, self.web_d - speed * 1.3 * dt)
                if self.web_d <= 0:
                    self.web_d = 0
                    self.end_web()
                    self.fy = T_
                    self.state = "hang"
                    self.set_state("walk")
                    return
            self.fy = T_ + self.web_d
            pose.update(legs=1 + int(self.time * 5) % 2, arms="up" if self.web_phase != "hang" else "wave",
                        bob=math.sin(self.time * 3) * .15, tilt=math.sin(self.time * 1.7) * .12)
            self.draw_thread()
            return

        # ---------- air (thrown / jumping / falling): real physics
        elif self.surf == "air" and s != "drag":
            g = self.gravity()
            self.vy += g * dt
            self.vx *= 1 - min(1, .35 * dt)            # a little air drag
            oy = self.fy
            self.fx += self.vx * dt
            self.fy += self.vy * dt
            self.max_v = max(self.max_v, math.hypot(self.vx, self.vy))
            if self.spin:
                self.tumble += abs(self.spin * dt)
            pose.update(arms="up" if s == "fall" or self.vy < 0 else "wave", eyes="happy" if s == "jump" else "x",
                        legs=1 + int(self.time * 10) % 2)
            kk = self.kick
            if kk and not kk["done"]:   # flying kick at a window's edge
                d = kk["dir"]
                pose.update(eyes="angry", arms="up", legs=0,
                            extra=[(15.5, 5.6, 19.8, 6.9, ORANGE)] if d > 0 else [(-3.8, 5.6, .5, 6.9, ORANGE)])
                front = self.fx + d * self.PW * .5
                if (front - kk["ex"]) * d >= -16 * k and abs(self.fy - self.PH / 2 - kk["cy"]) < self.PH * 1.4:
                    self.do_kick()
            elif kk:
                pose.update(eyes="happy", arms="wave" if int(self.time * 8) % 2 else "up")
            if self.fx < L_ + h or self.fx > R_ - h:
                left = self.fx < L_ + h
                if s == "fall" and self.cfg["climb"] and abs(self.vx) > 2300 * k:
                    self.fx = L_ if left else R_
                    self.fy = min(max(self.fy - self.PH / 2, T_ + h), B_ - h)
                    self.surf, self.state, self.timer = ("lwall" if left else "rwall"), "hang", 2.5
                    self.fx_crack(self.fx, self.fy, say=False)
                    self.sq, self.sqv, self.rot, self.spin = .45, 0, 0.0, 0.0
                    self.sfx("splat")
                    self.say(self.line("splat"))
                    return
                if abs(self.vx) > 2600 * k:
                    self.fx_crack(L_ if left else R_, self.fy - self.PH / 2)
                self.fx = L_ + h if left else R_ - h
                self.vx = -self.vx * .55
                self.spin = -self.spin * .6
                self.sqv += 4
                self.sfx("boing" if abs(self.vx) > 500 * k else "land", .5)
            if self.fy - self.PH < T_:
                if s == "fall" and self.cfg["climb"] and self.vy < -2200 * k:
                    self.fy, self.surf, self.state, self.timer = T_, "ceil", "hang", 2.5
                    self.fx = min(max(self.fx, L_ + h), R_ - h)
                    self.sq, self.rot, self.spin = .45, 0.0, 0.0
                    self.sfx("splat")
                    self.say(self.line("splat"))
                    return
                if self.vy < -2300 * k:
                    self.fx_crack(self.fx, T_)
                self.fy = T_ + self.PH
                self.vy = abs(self.vy) * .4
                self.sfx("land", .5)
            if self.vy > 0:
                land = self.find_landing(oy, self.fy, self.fx)
                if land:
                    y, hwnd, rect = land
                    self.fy = y
                    if self.vy > 2900 * k and hwnd is None:
                        self.fx_crack(self.fx, y)
                    if s == "fall" and self.vy > 520 * k:   # bounce!
                        self.vy = -self.vy * .42
                        self.vx *= .72
                        self.spin = self.spin * .5 + self.vx / (9 * P) * .4
                        self.sq, self.sqv = min(.5, -self.vy / (3000 * k)), 0
                        self.sfx("boing" if -self.vy > 900 * k else "land", .7)
                        self.spawn("dust", 3)
                        if -self.vy > 900 * k and self.cooldown("bounce_say", 6) and random.random() < .4:
                            self.say(self.line("bounce"))
                    else:
                        self.land(hwnd, rect)
            return

        # ---------- dragging: dangle and swing with the mouse
        elif s == "drag":
            vx = 0.0
            if len(self.samples) >= 2:
                (t0, x0, _), (t1, x1, _) = self.samples[-2], self.samples[-1]
                if time.perf_counter() - t1 < .1:
                    vx = (x1 - x0) / max(t1 - t0, .008)
            pose.update(legs=1 + int(self.time * 12) % 2, arms="up", eyes="x",
                        tilt=max(-.7, min(.7, -vx / (2500 * k))))
            self.mon = monitor_work(mx, my)
            return

        # ---------- on a window: ride it
        if self.surf == "floor" and self.plat:
            hw = self.plat
            if not user32.IsWindow(hw) or not user32.IsWindowVisible(hw) or user32.IsIconic(hw):
                if self.cooldown("floor_gone", 15):
                    self.sayl("floor_gone")
                return self.fall_off()
            r = frame_rect(hw)
            if r[1] <= T_ + 4:
                return self.fall_off()
            pr = self.plat_rect
            dx, dy = r[0] - pr[0], r[1] - pr[1]
            if abs(dx) + abs(dy) > 140 * k:
                self.fall_off(dx / max(dt, .01) * .4, -500 * k)
                self.spin = random.uniform(-6, 6)
                self.say(self.line("quake"))
                return
            if (dx or dy) and self.cooldown("ride", 20) and random.random() < .4:
                self.say(self.line("ride"))
            self.fx += dx
            self.fy = r[1] + self.sink
            self.plat_rect = r
        elif self.surf == "floor":
            self.fy = B_ + self.sink
        if s != "hide" and self.sink:
            self.sink = max(0.0, self.sink - self.PH * 3 * dt)

        # ---------- locomotion along the current surface
        moving = s in ("walk", "chase", "play", "flee") and self.surf != "fly" and not frozen
        target = 0.0
        if s == "walk":
            target = (60 if self.surf != "floor" else 75) * k * max(.7, self.cfg["scale"]) * self.persona()["speed"]
        elif s in ("chase", "play"):
            target = 150 * k * max(.7, self.cfg["scale"]) * max(1, self.persona()["speed"])
        elif s == "flee" and self.surf == "floor":
            target = 330 * k * max(.7, self.cfg["scale"])
            if self.flee_logic(mx, my):
                return
        if s == "walk" and self.goto and not frozen and self.surf == "floor":
            gx, gfn = self.goto
            if abs(gx - self.fx) < 10 * k:
                self.goto = None
                gfn()
                moving, target = False, 0
            else:
                self.dir = 1 if gx > self.fx else -1
        if s == "chase" and not frozen:
            dx = mx - self.fx
            if abs(dx) < self.PW / 2:
                self.set_state("idle")
                self.say(self.line("gotcha"))
                self.sfx("pop")
                moving, target = False, 0
            else:
                self.dir = 1 if dx > 0 else -1
        if s == "play" and self.ball and not frozen:
            b = self.ball
            dx = b.x - self.fx
            self.dir = 1 if dx > 0 else -1
            if b.plat and b.plat != self.plat and b.y < self.fy - self.PH and self.surf == "floor" and self.cooldown("ballhop", 3):
                self.try_hop(only=b.plat, then=lambda: self.set_state("play", 8))
            elif self.plat and b.y > self.fy + self.PH and self.cooldown("balldown", 2.5):
                self.off_window(lambda: self.set_state("play", 8))
            if abs(dx) < self.PW * .55 and abs(b.y - self.fy) < self.PH * 1.2 and self.cooldown("kick", .6):
                if random.random() < .7:   # pass it to you: aim at the mouse (fetch!)
                    ft, g = random.uniform(.65, .9), self.gravity()
                    b.vx = max(-2200 * k, min(2200 * k, (mx - b.x) / ft))
                    b.vy = max(-2600 * k, min(-400 * k, (my - b.y - .5 * g * ft * ft) / ft))
                    self.last_kick_t = self.time
                    if self.cooldown("fetch_say", 8) and random.random() < .5:
                        self.say(self.line("fetch"))
                else:
                    b.vx = self.dir * random.uniform(700, 1400) * k
                    b.vy = -random.uniform(500, 1100) * k
                b.plat = None
                self.sfx("kick")
                self.sqv -= 5
                self.happy = min(100, self.happy + 2)
                if random.random() < .3:
                    self.say(self.line("kick"))
            if abs(dx) < self.PW * .3:
                target *= .3
        if not moving:
            target = 0
        self.speed += (target - self.speed) * min(1, dt * 6)
        if self.surf != "fly" and (moving or self.speed > 1):
            step = self.dir * self.speed * dt
            self.walkdist += abs(step)
            pose["gait"] = self.walkdist / (P * 1.7) * math.pi
            pose["bob"] = -.22 * abs(math.sin(pose["gait"]))
            pose["tilt"] = fwd * min(.12, self.speed / (1400 * k))
            if s in ("chase", "play", "flee"):
                pose["arms"] = "wave" if int(pose["gait"] / math.pi) % 2 else "wave2"
            self.move_along(step)
            if self.surf == "floor" and self.sink < 1 and self.walkdist > self.next_foot and self.fx_on():
                self.next_foot = self.walkdist + P * 2.4
                self.foot_i = 1 - self.foot_i
                self.fxl.add("foot", self.fx + (self.foot_i - .5) * P * 2.2, self.fy, 4.5, P=P)
        if frozen:
            pose.update(eyes="happy" if self.happy > 60 else "open", arms="wave" if int(self.time * 3) % 2 else "down")

        # ---------- poses per state
        if s in ("idle", "listen", "hang"):
            pose["bob"] = math.sin(self.time * 2.4) * .08
            if s == "idle" and int(self.time / 7) % 3 == 0 and (self.time % 7) < 1.2:  # little fidget: tap a foot
                pose["leg"] = [(0, 2), (0, 2), (0, 2), (0, 2 - .6 * abs(math.sin(self.time * 12)))]
        elif s == "look":   # curious: look around, tilt head
            ph = self.time * .9
            self.look_override = (math.sin(ph) * .6, -.2 if math.sin(ph * 2.3) > .5 else 0)
            pose.update(tilt=math.sin(ph) * .1, bob=math.sin(self.time * 2.4) * .08)
            if self.cooldown("hmm", 9) and random.random() < .3:
                self.spawn("bang") if random.random() < .3 else None
        elif s == "sleep":
            pose.update(eyes="closed", bob=math.sin(self.time * 2) * .25, nightcap=True)
            if self.cooldown("z", 1.3):
                self.spawn("z")
        elif s == "yawn":
            f = 1 - self.timer / 1.6
            pose.update(eyes="closed" if .2 < f < .8 else "half", arms="up" if .25 < f < .75 else "down",
                        bob=-.3 * math.sin(math.pi * f), mouth=.25 < f < .75)
        elif s == "dance":
            bpm = self.audio.bpm if self.audio.playing else 124
            beat = (time.perf_counter() - self.audio.t0) * bpm / 60
            ph = beat % 1
            style = int(beat / 4) % 6
            pose.update(eyes="happy", legs=1 + int(beat * 2) % 2, bob=-abs(math.sin(math.pi * ph)) * 1.4)
            pose["arms"] = ("up" if int(beat) % 2 else "wave") if style != 2 else ("wave" if int(beat) % 2 else "wave2")
            if style == 0:
                pose["tilt"] = math.sin(beat * math.pi) * .14
            if style == 1 and self.surf == "floor" and not self.stay:
                self.move_along(math.sin(beat * math.pi) * 90 * k * dt)
            self._moon = style == 4 and self.surf == "floor" and not self.stay
            if self._moon:  # moonwalk: face one way, glide the other
                self.move_along(-self.dir * 55 * k * dt)
                pose.update(bob=0, arms="down", eyes="open")
                self.look = [self.dir * .5, 0]
            if style == 3:
                self.look = [math.sin(beat * math.pi) * .6, 0]
            if style == 5:  # the robot
                pose.update(bob=0, tilt=(.12 if int(beat) % 2 else -.12), arms="wave" if int(beat) % 2 else "wave2")
            self.sq = max(self.sq, .12 * (1 - ph) ** 3)
            if int(beat) != getattr(self, "_last_beat", -1):
                self._last_beat = int(beat)
                if int(beat) % 2 == 0:
                    self.spawn("note")
        elif s == "think":
            pose["arms"] = "wave" if int(self.time * 1.5) % 2 else "down"
            pose["tilt"] = .1 * math.sin(self.time * .8)
        elif s == "ask":
            pose["arms"] = "up" if int(self.time * 5) % 2 else "down"
            pose["bob"] = -abs(math.sin(self.time * 6)) * .5
        elif s == "sad":
            pose.update(eyes="closed", bob=.25, tilt=.06)
            if self.cooldown("tear", .9):
                self.spawn("drop")
        elif s == "angry":
            pose["eyes"] = "angry"
            pose["bob"] = random.choice((-.1, 0, .1))
            pose["leg"] = [(0, 2), (0, 2), (0, 2), (0, 2 - .7 * abs(math.sin(self.time * 14)))]  # foot tapping
        elif s == "petted":
            pose.update(eyes="happy", bob=-abs(math.sin(self.time * 7)) * .3, blush=True,
                        tilt=math.sin(self.time * 5) * .08)
            if self.cooldown("heart", .5):
                self.spawn("heart")
        elif s == "code":
            pose.update(arms="type", bob=-.12 if int(self.time * 8) % 2 else 0)
            if self.cooldown("type", .12) and random.random() < .5:
                self.sfx("type", .6)
        elif s == "stretch":
            pose.update(arms="high", eyes="closed", bob=-.4, tilt=math.sin(self.time * 2) * .1)
        elif s == "crouch":
            self.sq = .3
            pose["arms"] = "down"
        elif s == "eat":
            pose["eyes"] = "happy" if self.timer < 2.5 else "big"
            if self.timer < 2.5 and self.cooldown("chomp", .4):
                self.spawn("crumb", 2)
                self.sfx("crunch")
                self.sqv += 3
            if self.timer - dt <= 0:
                self.happy = min(100, self.happy + 15)
                self.energy = min(100, self.energy + 20)
                self.hunger = max(0, self.hunger - 60)
                self.say(self.line("eat"))
                self.spawn("heart", 2)
        elif s == "beg":   # hungry: big eyes, arms up, cookie thought
            pose.update(eyes="big", arms="up" if int(self.time * 4) % 2 else "wave", bob=-abs(math.sin(self.time * 5)) * .3)
        elif s == "dizzy":
            pose.update(eyes="x", bob=math.sin(self.time * 8) * .2, tilt=math.sin(self.time * 6) * .18)
        elif s == "getup":   # flopped on the floor after a throw: lie there a moment, then pop back up
            lying = self.timer > .55
            pose.update(eyes="x" if lying else "open", arms="up" if lying else "down", tilt=self.rot if lying else 0)
            if not lying and not getattr(self, "_got_up", False):
                self._got_up = True
                self.sqv -= 6
                self.sfx("pop", .5)
        elif s == "slide":   # skidding along the floor after a throw
            self.slide_v *= math.exp(-2.4 * dt)
            self.slide_v -= math.copysign(min(abs(self.slide_v), 260 * k * dt), self.slide_v)
            ox = self.fx
            self.move_along(self.slide_v * dt)
            if abs(self.fx - ox) < abs(self.slide_v * dt) * .5:
                self.slide_v = 0
            pose.update(eyes="happy", arms="up", tilt=self.rot if abs(self.rot) > .7 else -math.copysign(.18, self.slide_v))
            if self.cooldown("dust", .07):
                self.spawn("dust")
            if abs(self.slide_v) < 30 * k:
                self.timer = 0
        elif s == "wave":
            pose.update(eyes="happy", arms="wave" if int(self.time * 6) % 2 else "up", tilt=.06, blush=True)
        elif s == "proud":
            pose.update(eyes="happy", arms="high", bob=-.2, blush=True)
        elif s == "sneeze":
            if self.timer > .55:  # build-up: lean back, eyes squeezed
                pose.update(eyes="closed", arms="up", bob=-.3, tilt=-fwd * .12)
                self.sq = -min(.25, (1.8 - self.timer) * .25)
            else:
                if not getattr(self, "_sneezed", False):
                    self._sneezed = True
                    self.say(self.line("sneeze"))
                    self.sfx("sneeze")
                    self.sq, self.sqv = .45, 0
                    self.spawn("spark", 8)
                    if self.surf == "floor" and not self.stay:
                        self.move_along(-self.dir * 18 * k)
                pose.update(eyes="x" if self.timer > .3 else "open", arms="down", tilt=fwd * .1)
            if self.timer - dt <= 0:
                self._sneezed = False
        elif s == "moonwalk":
            if not self.stay and not frozen:
                self.move_along(-self.dir * 70 * k * dt)
            self.walkdist += 70 * k * dt
            pose.update(legs=1 + int(self.walkdist / (P * 1.2)) % 2, arms="down")
            self.look = [self.dir * .5, 0]
        elif s == "exercise" and self.ex:
            self.exercise_pose(dt, pose)
        elif s == "laugh":
            pose.update(eyes="happy", arms="wave" if int(self.time * 10) % 2 else "wave2", mouth=True,
                        bob=-abs(math.sin(self.time * 14)) * .35, tilt=-fwd * .1 + math.sin(self.time * 9) * .06)
        elif s == "lounge":   # lazy: lean back, hands behind the head, sunglasses
            pose.update(eyes="half", arms="high", tilt=-fwd * .16, shades=True, bob=math.sin(self.time * 1.6) * .06,
                        leg=[(0, 2), (0, 2), (.6, 1.4), (1.2, 1)])
            if self.cooldown("z", 3.5) and random.random() < .4:
                self.spawn("z")
        elif s == "stomp":
            ph = (2.4 - self.timer) / .6
            f = ph % 1
            pose.update(eyes="angry", arms="up", bob=-abs(math.sin(math.pi * f)) * 2.6)
            n = int(ph)
            if n != getattr(self, "_stomp_n", 0):
                self._stomp_n = n
                self.sq, self.sqv = .4, 0
                self.sfx("boom", .6)
                self.spawn("dust", 3)
                if self.plat:
                    self.shove_window(self.plat, 0, 0, shake=.3)
        elif s == "laser":
            self.laser_step(dt, mx, my, pose)
        elif s in ("doodle", "build", "mine", "smash"):
            self.trick_step(s, dt, pose)
        elif s == "flee":
            pose["eyes"] = "happy"
            if self.game and self.game.get("kind") == "tag" and self.time > self.game["until"]:
                self.game = None
                self.set_state("laugh")
                self.sayl("tag_win")
        elif s == "hide":
            self.hide_step(dt, mx, my, pose)
        elif s == "peek":
            L_, _, R_, _ = self.mon
            hidden = self.timer > .7
            lo, hi = L_ + h, R_ - h
            tgt = (lo - self.PW * .58 if self.peek_side < 0 else hi + self.PW * .58) if hidden else \
                (lo if self.peek_side < 0 else hi)
            self.fx += (tgt - self.fx) * min(1, dt * 4)
            self.look = [-self.peek_side * .55, 0]
            pose["arms"] = "down"
            if hidden and abs(mx - self.fx) < 220 * k and abs(my - self.fy) < 260 * k and self.cooldown("peekboo", 6):
                self.say(self.line("peek"))
                self.sfx("peek")
                self.eyes_override = ("big", self.time + 1)
                self.timer = min(self.timer, .7)
        if self.surf == "fly":  # hovering while doing something else: keep the propeller going
            pose["bob"] = pose.get("bob", 0) + math.sin(self.time * 4) * .3

    def exercise_pose(self, dt, pose):
        ex, k = self.ex, self.k
        ph = (self.time - ex["t0"]) / ex["per"]
        rep, f = int(ph), ph % 1
        down = (1 - math.cos(2 * math.pi * f)) / 2          # 0 = top, 1 = bottom of the rep
        kind = ex["kind"]
        if rep > ex["rep"] and rep <= ex["reps"] and kind != "yoga":
            ex["rep"] = rep
            if kind != "run":
                self.say(str(rep) if self.lang != "ar" else str(rep).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")))
                self.sfx("huff", .8)
            if rep == ex["reps"] // 2 + 1 and random.random() < .5:
                self.say(self.line("ex_mid"))
        if self.cooldown("sweat", .8) and random.random() < .5:
            self.spawn("drop")
        GRAY, DARK = "#8a8a8a", "#3a3a3a"
        if kind == "pushups":
            b = 1.7 * down
            out = .9 * down                                   # elbows bend outwards on the way down
            pose.update(bob=b, arms="none", eyes="closed" if down > .75 else "angry",
                        extra=[(0, 3, 2, 5, ORANGE), (14, 3, 16, 5, ORANGE),
                               (-.6 - out, 4.6, 1.2 - out, 9 - b, ORANGE), (14.8 + out, 4.6, 16.6 + out, 9 - b, ORANGE)],
                        leg=[(0, 2 - b)] * 4)
        elif kind == "squats":
            b = 1.9 * down
            pose.update(bob=b, eyes="angry" if down > .5 else "open", leg=[(0, 2 - b)] * 4,
                        arms="none" if down > .25 else "down",
                        extra=[(-1.6, 3.1, 2, 4.4, ORANGE), (14, 3.1, 17.6, 4.4, ORANGE)] if down > .25 else [])
        elif kind == "jacks":
            open_ = f < .5
            hop = math.sin(math.pi * (f * 2 % 1))
            pose.update(bob=-.7 * hop, eyes="happy", arms="high" if open_ else "down",
                        leg=[(-1.2, 2), (-.4, 2), (.4, 2), (1.2, 2)] if open_ else [(0, 2)] * 4)
        elif kind == "lift":
            bv = -3 + 6 * down                                 # bar height (pet grid units)
            top = bv + .3
            pose.update(arms="none", eyes="angry" if down < .5 else "open", bob=.35 * down,
                        leg=[(0, 2 - .35 * down)] * 4,
                        extra=[(0, top, 2, max(top + 2, 4), ORANGE), (14, top, 16, max(top + 2, 4), ORANGE),
                               (-2, bv - .3, 18, bv + .3, GRAY), (-2.9, bv - 1.3, -1.3, bv + 1.3, DARK),
                               (17.3, bv - 1.3, 18.9, bv + 1.3, DARK)])
        elif kind == "run":
            a = f < .5
            pose.update(bob=-.45 * abs(math.sin(2 * math.pi * f)), eyes="open",
                        arms="wave" if a else "wave2", tilt=.08 * (1 if self.dsurf in ("floor", "lwall") else -1) * self.dir,
                        leg=[(.3, .8), (0, 2), (.3, .8), (0, 2)] if a else [(0, 2), (.3, .8), (0, 2), (.3, .8)])
            if self.cooldown("dust", .16):
                self.spawn("dust")
        elif kind == "yoga":
            pose.update(eyes="closed", arms="none", tilt=math.sin(self.time * 1.3) * .05,
                        extra=[(5.9, -3.6, 7.9, .4, ORANGE), (8.1, -3.6, 10.1, .4, ORANGE)],
                        leg=[(0, 2), (0, 2), (0, .7), (0, .7)])
            if self.cooldown("om", 2.2):
                self.spawn("note")

    def move_along(self, step):
        L_, T_, R_, B_ = self.mon
        h = self.half()
        sf = self.surf
        climb_ok = self.cfg["climb"] or self.want_web
        if sf == "floor":
            if self.plat:
                lo, hi = max(self.plat_rect[0], L_) + self.PW * .3, min(self.plat_rect[2], R_) - self.PW * .3
            else:
                lo, hi = L_ + h, R_ - h
            self.fx += step
            if self.fx <= lo or self.fx >= hi:
                self.fx = min(max(self.fx, lo), hi)
                if self.state not in ("walk", "chase", "play", "flee"):
                    return
                if self.plat:
                    if self.state == "walk" and random.random() < .45:
                        self.fall_off(self.dir * 220 * self.k, -380 * self.k, "jump")
                        self.say(self.line("hop"))
                    else:
                        self.dir *= -1
                elif self.want_peek and self.state == "walk":
                    self.want_peek = False
                    self.peek_side = -1 if self.fx <= lo else 1
                    self.set_state("peek")
                elif climb_ok and self.state == "walk" and (self.want_climb or random.random() < .5):
                    self.want_climb = False
                    left = self.fx <= lo
                    self.surf, self.fx, self.fy, self.dir = ("lwall" if left else "rwall"), (L_ if left else R_), B_ - h, -1
                    self.sqv -= 4
                    self.sfx("climb")
                    if random.random() < .5:
                        self.say(self.line("climb"))
                else:
                    self.dir *= -1
        elif sf in ("lwall", "rwall"):
            self.fy += step
            left = sf == "lwall"
            if self.fy <= T_ + h:
                self.fy = T_ + h
                if climb_ok and random.random() < .6:
                    self.surf, self.fy = "ceil", T_
                    self.fx, self.dir = (L_ + h, 1) if left else (R_ - h, -1)
                    self.sfx("climb")
                    if random.random() < .5:
                        self.say(self.line("ceiling"))
                else:
                    self.dir = 1
            elif self.fy >= B_ - h:
                self.surf, self.plat, self.fy = "floor", None, B_
                self.fx, self.dir = (L_ + h, 1) if left else (R_ - h, -1)
                self.sfx("climb")
        elif sf == "ceil":
            self.fx += step
            if self.fx <= L_ + h:
                self.surf, self.fx, self.fy, self.dir = "lwall", L_, T_ + h, 1
                self.sfx("climb")
            elif self.fx >= R_ - h:
                self.surf, self.fx, self.fy, self.dir = "rwall", R_, T_ + h, 1
                self.sfx("climb")

    def stick_on_drop(self):
        """Dropped gently near a screen edge -> grab it like a spider; near a window top -> stand on it."""
        L_, T_, R_, B_ = self.mon
        h, k = self.half(), self.k
        cx, cy = self.fx, self.fy - self.PH / 2
        near = self.PW * .8
        target = None
        if self.cfg["climb"]:
            if cx - L_ < near:
                target = "lwall"
            elif R_ - cx < near:
                target = "rwall"
            elif (cy - self.PH / 2) - T_ < self.PH * .9:
                target = "ceil"
        if target:
            self.surf = target
            if target == "ceil":
                self.fx, self.fy = min(max(cx, L_ + h), R_ - h), T_
            else:
                self.fx, self.fy = (L_ if target == "lwall" else R_), min(max(cy, T_ + h), B_ - h)
            self.vx = self.vy = 0
            self.state, self.timer = "hang", random.uniform(1.5, 3)
            self.sq, self.sqv = .4, 0
            self.sfx("splat")
            self.say(self.line("splat" if random.random() < .5 else "climb"))
            return True
        if self.cfg["windows"] and self.fy < B_ - 10 * k:
            for hw, r, _, _ in self.windows:
                if r[1] > T_ + 6 and abs(self.fy - r[1]) < 45 * k and r[0] + self.PW * .3 <= self.fx <= r[2] - self.PW * .3 \
                        and top_visible(hw, self.fx, r[1]):
                    self.fy = r[1]
                    self.land(hw, r)
                    return True
        return False

    def fall_off(self, vx=0.0, vy=0.0, state="fall"):
        self.surf, self.plat = "air", None
        self.sink = 0.0
        self.vx, self.vy = vx, vy
        self.state, self.max_v = state, 0

    def find_landing(self, oy, ny, x):
        L_, T_, R_, B_ = self.mon
        best = None
        if ny >= B_:
            best = (B_, None, None)
        if self.cfg["windows"]:
            for h, r, _, _ in self.windows:
                top = r[1]
                if top <= T_ + 6 or not (oy - 1 <= top <= ny) or not (r[0] + self.PW * .3 <= x <= r[2] - self.PW * .3):
                    continue
                if best and top >= best[0]:
                    continue
                if top_visible(h, x, top):
                    best = (top, h, r)
        return best

    def land(self, hwnd, rect):
        kk, self.kick = self.kick, None
        if kk and not self.after_land:
            if kk["done"]:
                self.after_land = lambda: self.set_state("laugh")
            else:
                self.after_land = lambda: (self.set_state("idle", 1.5), self.sayl("kick_miss"))
        s, k = self.state, self.k
        impact, vx = self.vy, self.vx
        self.surf, self.plat, self.plat_rect = "floor", hwnd, rect
        self.vx = self.vy = 0
        self.speed = 0
        r = (self.rot + math.pi) % (2 * math.pi) - math.pi   # where the tumble ended up
        self.rot, self.spin = r, 0.0
        flopped = abs(r) > .75
        self.sq = min(.5, .1 + impact / (5000 * k))
        self.sqv = 0
        self.sfx("flop" if flopped else "land", min(1, .3 + impact / (2500 * k)))
        if s == "fall":
            dizzy = self.max_v > 3200 * k or self.tumble > 4 * math.pi
            after = ("dizzy", None) if dizzy else None
            if flopped:
                self._got_up = False
                after = ("getup", None) if not after else after
            if abs(vx) > 280 * k and not hwnd:      # skid along the floor
                self.slide_v = vx
                self.set_state("slide")
                self.chain = after if not flopped else ("getup", None)
                self._chain2 = ("dizzy", None) if flopped and dizzy else None
                self.say(self.line("slide")) if random.random() < .4 else None
            elif flopped:
                self.set_state("getup")
                self.chain = ("dizzy", None) if dizzy else None
                self.say(self.line("flop"))
            elif dizzy:
                self.set_state("dizzy")
                self.say(self.line("dizzy"))
            else:
                self.rot = 0.0
                self.set_state("idle", 1.2)
                self.say(self.line("land"))
            self.spawn("dust", 4)
        else:
            self.rot = 0.0 if not flopped else self.rot
            self.set_state("idle", random.uniform(.6, 1.5))
        if self.after_land:  # something was asked while he was up there: do it now
            fn, self.after_land = self.after_land, None
            self.chain = self._chain2 = None
            self.rot = 0.0
            fn()

    # ---------------------------------------------------------- v1.2: personality
    def persona(self):
        return PERSONAS.get(self.cfg.get("personality"), PERSONAS["balanced"])

    def set_persona(self, key):
        if key not in PERSONAS:
            return
        self.cfg["personality"] = key
        self.save()
        name = T["personas"][1 if self.lang == "ar" else 0][list(PERSONAS).index(key)]
        self.say(self.line("persona_set", p=name))
        act = {"naughty": "laugh", "lazy": "lounge", "hyper": "dance", "sweet": "wave"}.get(key, "proud")
        self.set_state(act, None if act in ("laugh", "lounge", "wave") else 3)

    # ---------------------------------------------------------- v1.2: moving other apps' windows (mischief)
    def shove_window(self, h, vx, vy=0.0, shake=0.0):
        """Animate another app's window: a sliding shove (with friction) and/or a little shake."""
        if not self.cfg["mischief"] or not h or not user32.IsWindow(h) or user32.IsZoomed(h) or user32.IsIconic(h):
            return False
        x, y, r, b = win_pos(h)
        self.win_orig.setdefault(h, (x, y))
        a = self.wmove.get(h)
        if not a:
            a = self.wmove[h] = {"x": float(x), "y": float(y), "vx": 0.0, "vy": 0.0, "shake": 0.0, "last": (x, y)}
        a["vx"] += vx
        a["vy"] += vy
        a["shake"] = max(a["shake"], shake)
        a["w"] = r - x
        return True

    def step_windows(self, dt):
        if not self.wmove:
            return
        k = self.k
        L_, T_, R_, B_ = self.mon
        for h, a in list(self.wmove.items()):
            if not user32.IsWindow(h) or user32.IsZoomed(h) or user32.IsIconic(h):
                del self.wmove[h]
                continue
            x, y, _, _ = win_pos(h)
            if abs(x - a["last"][0]) > 2 or abs(y - a["last"][1]) > 2:   # the user grabbed it (or it can't move): let go
                del self.wmove[h]
                continue
            a["x"] += a["vx"] * dt
            a["y"] += a["vy"] * dt
            a["vx"] *= math.exp(-2.6 * dt)
            a["vy"] *= math.exp(-6 * dt)
            pad = 8 * k
            if a["w"] < R_ - L_:   # bounce off the screen edges
                if a["x"] < L_ - pad:
                    a["x"], a["vx"] = L_ - pad, abs(a["vx"]) * .45
                    self.sfx("kick", .4)
                elif a["x"] + a["w"] > R_ + pad:
                    a["x"], a["vx"] = R_ + pad - a["w"], -abs(a["vx"]) * .45
                    self.sfx("kick", .4)
            a["y"] = min(max(a["y"], T_), B_ - 80 * k)
            off = 0.0
            if a["shake"] > 0:
                a["shake"] -= dt
                off = math.sin(self.time * 75) * 9 * k * min(1.0, a["shake"] / .2)
            done = abs(a["vx"]) < 20 * k and abs(a["vy"]) < 20 * k and a["shake"] <= 0
            nx, ny = int(round(a["x"] + (0 if done else off))), int(round(a["y"] + (0 if done else abs(off) * .3)))
            if (nx, ny) != a["last"]:
                move_win(h, nx, ny)
                a["last"] = (nx, ny)
            if done:
                del self.wmove[h]

    def undo_windows(self):
        self.wmove.clear()
        for h, (x, y) in self.win_orig.items():
            if user32.IsWindow(h) and not user32.IsZoomed(h):
                move_win(h, x, y)
        self.win_orig.clear()
        self.sayl("undo_win")

    def go_kick(self, only=None, user=False):
        """Flying kick at the side of a window: it slides away across the screen."""
        if user:
            self.stay = False
        if not (self.cfg["mischief"] and self.cfg["windows"]):
            if user:
                self.sayl("mischief_off")
            return False
        if self.surf != "floor":
            if user:
                self.need_floor(lambda: self.go_kick(only, True))
            return user
        k, g = self.k, self.gravity()
        L_, T_, R_, B_ = self.mon
        fg = user32.GetForegroundWindow()
        busy = not user and idle_seconds() < 2   # don't yank the window you're typing in
        cands = []
        for h, r, _, _ in self.windows:
            if (only and h != only) or h == self.plat or h in self.wmove or user32.IsZoomed(h) or (h == fg and busy):
                continue
            if r[2] - r[0] > (R_ - L_) * .9 or r[3] - r[1] < 110 * k:
                continue
            for side, ex in ((-1, r[0]), (1, r[2])):
                out = ex + side * self.PW * .5          # where he is when his foot touches the edge
                dist = (self.fx - out) * side            # >= 0: he's on the outside of that edge
                if not (L_ + self.PW * .6 < out < R_ - self.PW * .6) or dist < 0 or dist > 900 * k:
                    continue
                cy = min(max((r[1] + r[3]) / 2, r[1] + 50 * k + self.PH * .5), B_ - self.PH * .6)
                if not r[1] + 30 * k < cy < r[3] - 15 * k:
                    continue
                rise = self.fy - (cy + self.PH * .5)
                if rise > 650 * k or rise < -60 * k or not top_visible(h, ex - side * 10 * k, cy - 4):
                    continue
                cands.append((h, side, ex, cy, out, rise))
        if not cands:
            if user:
                self.sayl("no_kick")
            return False
        h, side, ex, cy, out, rise = random.choice(cands)
        peak = max(rise, 0) + 130 * k
        vy0 = -math.sqrt(2 * g * peak)
        t = (-vy0 + math.sqrt(max(0.0, vy0 * vy0 - 2 * g * rise))) / g
        c = .35   # air drag used in the air physics
        vx = (out - self.fx) * c / (1 - math.exp(-c * t))
        self.kick = {"h": h, "dir": -side, "ex": ex, "cy": cy, "done": False}
        self.pending_jump = (vx, vy0)
        self.dir = -side
        self.set_state("crouch", .55)
        self.sayl("kick_windup")
        self.eyes_override = ("angry", self.time + .7)
        return True

    def do_kick(self):
        kk, k = self.kick, self.k
        kk["done"] = True
        d = kk["dir"]
        power = min(1.5, .8 + .2 * self.persona()["naughty"])
        self.shove_window(kk["h"], d * random.uniform(1500, 2500) * k * power, -random.uniform(80, 220) * k, shake=.15)
        self.vx, self.vy = -d * 380 * k, min(self.vy, -320 * k)
        self.spin = -d * 3.0
        self.sfx("kick")
        self.sfx("boing", .6)
        self.sq, self.sqv = .4, 0
        if self.fx_on():
            self.fxl.add("pow", kk["ex"], kk["cy"], .9, text=random.choice(("POW!", "BAM!", "BONK!", "WHAM!", "KAPOW!")))
        self.sayl("kick_hit")
        self.stat("kicks")

    # ---------------------------------------------------------- v1.2: hiding behind windows / the taskbar
    def hide_spots(self):
        k = self.k
        L_, T_, R_, B_ = self.mon
        spots = [("bar", None, None, 0, 0.0)]
        for h, r, _, _ in self.windows:
            if T_ + 6 < r[1] < B_ - self.PH * 1.6 and r[2] - r[0] > self.PW * 1.8 and top_visible(h, (r[0] + r[2]) / 2, r[1]):
                spots.append(("top", h, r, 0, 0.0))
            if r[3] >= B_ - 8 * k and not user32.IsZoomed(h) and r[3] - r[1] > self.PH * 2:
                for side, ex in ((-1, r[0]), (1, r[2])):
                    if L_ + self.PW < ex < R_ - self.PW and top_visible(h, ex - side * 12 * k, B_ - self.PH * .5 - 4):
                        spots.append(("side", h, r, side, ex))
        return spots

    def go_hide(self, user=False):
        if user:
            self.stay = False
        if self.surf != "floor":
            return self.need_floor(lambda: self.go_hide(user))
        if self.plat:   # standing on a window: duck behind its top edge right here
            return self.begin_hide("top", self.plat, self.plat_rect)
        k = self.k
        spots = self.hide_spots()
        sides = [sp for sp in spots if sp[0] == "side" and abs(sp[4] - self.fx) < 1100 * k]
        tops = [sp for sp in spots if sp[0] == "top"]
        r = random.random()
        if sides and r < .5:
            _, h, rect, side, ex = random.choice(sides)
            self.set_state("walk", 30)
            self.goto = (ex + side * self.PW * .6, lambda: self.begin_hide("side", h, rect, side, ex))
            return
        if tops and r < .85:
            h = random.choice(tops)[1]
            if self.try_hop(only=h, then=lambda: self.begin_hide("top", self.plat, self.plat_rect) if self.plat else
                            self.begin_hide("bar")):
                return
        self.begin_hide("bar")

    def begin_hide(self, kind, h=None, rect=None, side=0, ex=0.0, full=False, game=False):
        if kind == "top" and not self.plat:
            kind = "bar"
        self.goto = None
        self.set_state("hide", 75 if game else random.uniform(9, 16))
        self.hide_info = {"kind": kind, "h": h, "r": rect, "side": side, "ex": ex, "full": full, "game": game,
                          "pop": -9.0, "t0": self.time}
        self.sfx("whoosh", .5)
        if not game and random.random() < .6:
            self.sayl("hide")

    def hide_step(self, dt, mx, my, pose):
        hi, k, PH = self.hide_info, self.k, self.PH
        if not hi:
            self.timer = 0
            return
        kind = hi["kind"]
        if kind == "side":
            if not user32.IsWindow(hi["h"]) or user32.IsIconic(hi["h"]):
                return self.set_state("idle", 1)
            hi["r"] = frame_rect(hi["h"])
            hi["ex"] = hi["r"][0] if hi["side"] < 0 else hi["r"][2]
        cx, cy = self.pet_center()
        el = self.time - hi["t0"]
        if hi["game"]:
            depth = .62 if el % 17 > 15.6 else 1.15        # a tiny peek now and then as a hint
            self.over_t = self.over_t + dt if self.cursor_over else 0.0
            if self.over_t > .3:
                return self.seek_found()
            if el > 70:
                return self.seek_timeout()
        else:
            depth = 1.08 if el % 6 > 4.8 else .6        # duck down, then peek over the edge again
            if math.hypot(mx - cx, my - cy) < 170 * k and self.time - hi["pop"] > 3 and self.cooldown("boo", 4):
                hi["pop"] = self.time
                self.sayl("boo")
                self.sfx("peek")
                self.sqv -= 6
            if self.time - hi["pop"] < 1.1:
                depth = -.1 if kind == "side" else 0.0
        if kind == "side":
            tx = hi["ex"] - hi["side"] * self.PW * (depth - .55)
            self.fx += (tx - self.fx) * min(1, dt * 6)
        else:
            self.sink += (depth * PH - self.sink) * min(1, dt * (10 if depth < .3 else 5))
        pose.update(arms="up" if kind != "side" else "down", bob=math.sin(self.time * 2.2) * .05,
                    eyes="big" if self.time - hi["pop"] < 1.1 else "open")

    def hide_masks(self):
        L_, T_, R_, B_ = self.mon
        out = []
        if self.surf == "floor" and self.sink > .5:
            if self.plat and self.plat_rect:
                out.append(self.plat_rect)
            elif not self.plat:
                out.append((L_ - self.S, B_, R_ + self.S, B_ + 2 * self.S))
        hi = self.hide_info
        if self.state == "hide" and hi and hi["kind"] == "side" and hi.get("r"):
            out.append(hi["r"])
        return out

    # ---------------------------------------------------------- v1.2: desktop effects & tricks
    def fx_on(self):
        return self.fxl is not None and self.cfg["desk_fx"]

    def fx_crack(self, x, y, say=True, force=False):
        if not self.fx_on() or not (force or self.cooldown("crack", 1.2)):
            return None
        k, lines = self.k, []
        n = random.randint(6, 9)
        for i in range(n):
            a = i / n * 2 * math.pi + random.uniform(-.3, .3)
            pts, px, py = [(0.0, 0.0)], 0.0, 0.0
            for _ in range(random.randint(3, 5)):
                a += random.uniform(-.5, .5)
                d = random.uniform(15, 42) * k
                px, py = px + math.cos(a) * d, py + math.sin(a) * d
                pts.append((px, py))
            lines.append(pts)
        it = self.fxl.add("crack", x, y, 7.0, lines=lines)
        self.sfx("crash", .6)
        if say and self.cooldown("crack_say", 30):
            self.root.after(500, lambda: self.sayl("crack"))
        return it

    def party(self, small=False):
        if self.fx_on():
            self.fxl.confetti(60 if small else 170)
        else:
            self.spawn("heart", 4)
        self.sfx("win")
        if not small:
            self.sayl("confetti")
            self.set_state("dance", 4)

    def start_trick(self, kind, user=False):
        if user:
            self.stay = False
        if not self.fx_on():
            if user:
                self.sayl("fx_off")
            return
        if kind not in ("laser", "glitch") and self.surf != "floor":
            return self.need_floor(lambda: self.start_trick(kind, user))
        if kind == "glitch":
            cx, cy = self.pet_center()
            self.fxl.add("glitch", cx, cy - self.PH, 1.0)
            self.sfx("static", .7)
            if self.surf != "air":
                self.set_state("look", 2.5)
            self.eyes_override = ("big", self.time + 1.5)
            self.root.after(900, lambda: self.sayl("glitch"))
            return
        self.set_state(kind)
        if self.state != kind:
            return
        self.work = {"kind": kind, "t": 0.0, "n": 0, "item": None, "side": random.choice((-1, 1))}
        L_, _, R_, _ = self.mon
        if self.fx - L_ < self.PW * 2.2:   # keep the work spot on screen
            self.work["side"] = 1
        elif R_ - self.fx < self.PW * 2.2:
            self.work["side"] = -1
        words = {"build": (("Building", "Scaffolding", "Engineering", "Constructing"), ("أبني", "أشيّد", "أهندس", "أعمّر")),
                 "mine": (("Mining", "Digging", "Excavating", "Tunneling"), ("أعدّن", "أحفر", "أنقّب", "أحفر نفق"))}
        if kind in words:
            self.word = random.choice(words[kind][1 if self.lang == "ar" else 0])

    def tool_rects(self, tool, side):
        a = self.arm[1] if side > 0 else self.arm[0]
        u = 15 if side > 0 else 1
        if tool == "hammer":
            return [(u - .35, a - 3.2, u + .35, a + 1.2, "#8B5A2B"), (u - 1.6, a - 4.3, u + 1.6, a - 3.0, "#8a8a8a")]
        if tool == "pick":
            return [(u - .3, a - 3.6, u + .3, a + 1.2, "#8B5A2B"), (u - 2.4, a - 4.3, u + 2.4, a - 3.5, "#9a9a9a"),
                    (u - 2.9, a - 3.9, u - 2.2, a - 3.0, "#9a9a9a"), (u + 2.2, a - 3.9, u + 2.9, a - 3.0, "#9a9a9a")]
        if tool == "marker":
            return [(u - .35, a - 2.0, u + .35, a + .6, "#3B82F6"), (u - .35, a - 2.6, u + .35, a - 2.0, "#222222")]
        if tool == "tape":
            return [(u - 1.1, a - 1.3, u + 1.1, a + .9, "#BDBDBD"), (u - .45, a - .65, u + .45, a + .25, "#7A7A7A")]
        return []

    def trick_step(self, s, dt, pose):
        w = self.work
        if not w or not self.fx_on():
            self.timer = 0
            return
        k, P, PW, PH = self.k, self.P, self.PW, self.PH
        prev = w["t"]
        w["t"] += dt
        t = w["t"]
        side = w["side"]
        self.dir = side

        def hit(period):
            return int(t / period) != int(prev / period)
        spot = self.fx + side * PW * .95
        if s == "doodle":
            if w["item"] is None:
                L_, T_, R_, B_ = self.mon
                nm = self.cfg.get("name") or ("you" if self.lang != "ar" else "صديقي")
                txt = random.choice(DOODLES[1 if self.lang == "ar" else 0]).format(n=nm)
                x = min(max(self.fx + side * PW * 1.3, L_ + 170 * k), R_ - 170 * k)
                y = max(T_ + 60 * k, self.fy - PH * 2.3)
                w["item"] = self.fxl.add("doodle", x, y, 11.0, text=txt,
                                         color=random.choice(("#E5484D", "#3B82F6", "#16A34A", ORANGE, "#9333EA")))
            pose.update(arms="up" if int(t * 7) % 2 else "wave", eyes="happy", tilt=side * .08,
                        extra=self.tool_rects("marker", side))
            if self.cooldown("type", .15):
                self.sfx("type", .5)
        elif s == "build":
            if w["item"] is None:
                w["item"] = self.fxl.add("build", spot, self.fy, 16.0, bricks=[], fall=None, P=P)
            it = w["item"]
            if not w.get("done"):
                swing = (t % .5) / .5
                pose.update(arms="up" if swing < .45 else "down", tilt=side * .06, extra=self.tool_rects("hammer", side))
                if hit(.5) and t > .3:
                    w["n"] += 1
                    self.fxl.add_brick(it, w["n"] - 1)
                    self.sfx("tok", .6)
                    self.sq = .12
                    self.spawn("dust")
                if w["n"] >= 6:
                    w["done"] = True
                    self.timer = min(self.timer, 2.4)
                    self.sayl("built")
                    self.spawn("spark", 5)
                    if random.random() < .5:   # sometimes the prototype collapses
                        it["fall"] = it["t"] + random.uniform(2.5, 4.5)
                        self.root.after(int((it["fall"] - it["t"]) * 1000) + 700, lambda: self.sayl("collapse"))
            else:
                pose.update(arms="high", eyes="happy", blush=True)
        elif s == "mine":
            if w["item"] is None:
                w["item"] = self.fxl.add("hole", spot, self.fy, 10.0, w=0.0)
            it = w["item"]
            if not w.get("done"):
                swing = (t % .45) / .45
                pose.update(arms="high" if swing < .5 else "down", tilt=side * (.14 if swing > .5 else -.04),
                            extra=self.tool_rects("pick", side))
                if hit(.45) and t > .3:
                    w["n"] += 1
                    it["w"] = min(PW * 1.1, it["w"] + PW * .12)
                    self.sfx("clink", .55)
                    self.sq = .1
                    for _ in range(3):
                        self.fxl.add("rock", spot, self.fy - 4, 1.2, vx=random.uniform(-260, 260) * k,
                                     vy=-random.uniform(350, 700) * k, s=random.uniform(.3, .6) * P)
                if w["n"] >= 9:
                    w["done"] = True
                    loot = random.choice(("gem", "bug", "coin", "cookie"))
                    self.fxl.add("loot", spot, self.fy - P, 2.6, what=loot, P=P)
                    self.sfx("coin" if loot != "bug" else "no", .6)
                    self.sayl("found_" + loot)
                    self.timer = 2.6
                    if loot == "cookie":
                        self.root.after(1800, lambda: self.feed() if self.state in ("mine", "idle", "look") else None)
            else:
                pose.update(arms="high", eyes="happy", bob=-.2)
        elif s == "smash":
            if t < .75:   # wind up...
                pose.update(arms="up", eyes="angry", tilt=-side * .12)
                self.sq = -.2 * t
            elif not w.get("hit"):   # ...PUNCH the screen
                w["hit"] = True
                w["item"] = self.fx_crack(self.fx + side * PW * .75, self.fy - PH * .7, say=False, force=True)
                self.sq, self.sqv = .35, 0
                self.eyes_override = ("big", self.time + 1)
                self.sayl("smash")
            elif t < 1.6:
                pose.update(eyes="big", extra=[(16, 2.6, 18.6, 4.6, ORANGE)] if side > 0 else [(-2.6, 2.6, 0, 4.6, ORANGE)])
            else:   # fix it with duct tape like a pro
                pose.update(arms="up" if int(t * 6) % 2 else "wave", eyes="happy", extra=self.tool_rects("tape", side))
                if t > 2.3 and not w.get("taped"):
                    w["taped"] = True
                    if w["item"]:
                        w["item"]["tape"] = True
                    self.sfx("tok", .6)
                    self.root.after(400, lambda: self.sayl("tape"))

    def laser_step(self, dt, mx, my, pose):
        pose.update(eyes="angry", arms="down", bob=math.sin(self.time * 30) * .04)
        if not self.fx_on():
            self.timer = 0
            return
        if self.timer < self.DUR["laser"][0] - .35 and hasattr(self, "sx"):   # charge up, then fire
            sx, sy = self.wx, self.wy
            (x1, y1), (x2, y2) = self.T(4.5, 3), self.T(11.5, 3)
            self.fxl.beam = [(x1 + sx, y1 + sy, mx, my), (x2 + sx, y2 + sy, mx, my)]
            if self.cooldown("scorch", .05):
                self.fxl.add("scorch", mx + random.uniform(-3, 3) * self.k, my + random.uniform(-3, 3) * self.k, 4.0)
            if self.cooldown("zap", .22):
                self.sfx("zap", .35)
        if self.timer - dt <= 0:
            self.fxl.beam = None

    # ---------------------------------------------------------- v1.2: games
    def end_game(self):
        g, self.game = self.game, None
        if g and g.get("kind") == "ttt":
            try:
                g["win"].win.destroy()
            except tk.TclError:
                pass
        if g and self.state in ("hide", "flee"):
            self.set_state("idle", 1)

    def game_won_by_user(self):
        """Grabbed him with the mouse during tag / hide and seek: that counts!"""
        g, self.game = self.game, None
        t = round(self.time - g.get("t0", self.time), 1)
        self.say(self.line("tag_caught" if g["kind"] == "tag" else "seek_found", t=t if g["kind"] == "tag" else int(t)))
        self.party(small=True)

    def game_seek(self):
        self.end_game()
        self.stay = False
        if self.surf not in ("air", "fly"):
            self.set_state("idle", 99)
        self.game = {"kind": "seek", "t0": self.time}
        self.sayl("seek_start")

        def go():
            if not self.game or self.game.get("kind") != "seek" or self.state == "drag":
                return
            spots = self.hide_spots()
            kind, h, rect, side, ex = random.choice(spots[1:]) if len(spots) > 1 and random.random() < .85 else spots[0]
            cx, cy = self.pet_center()
            self.fxl.add("puff", cx, cy, .6) if self.fx_on() else None
            self.sfx("poof", .6)
            L_, T_, R_, B_ = self.mon
            self.surf, self.vx, self.vy, self.rot, self.spin = "floor", 0.0, 0.0, 0.0, 0.0
            self.kick = self.after_land = self.chain = self._chain2 = None
            self.say_queue, self.bubble = [], None
            if kind == "top":
                self.plat, self.plat_rect = h, rect
                self.fx = random.uniform(rect[0] + self.PW * .6, rect[2] - self.PW * .6)
            elif kind == "side":
                self.plat, self.fx = None, ex - side * self.PW * .62
            else:
                self.plat, self.fx = None, random.uniform(L_ + self.PW, R_ - self.PW)
            self.sink = self.PH * 1.15 if kind != "side" else 0.0
            self.fy = (rect[1] if kind == "top" else B_) + self.sink
            self.begin_hide(kind, h, rect, side, ex, full=True, game=True)
            self.game = {"kind": "seek", "t0": self.time}
        self.root.after(3300, go)

    def seek_found(self):
        hi = self.hide_info
        t = int(self.time - hi["t0"]) if hi else 0
        self.set_state("laugh")
        self.game = None
        self.sayl("seek_found", t=t)
        self.party(small=True)

    def seek_timeout(self):
        self.set_state("proud")
        self.game = None
        self.sayl("seek_win")

    def game_tag(self):
        self.end_game()
        self.stay = False
        self.game = {"kind": "tag", "t0": self.time, "until": self.time + 25}
        self.sayl("tag_start")
        self.need_floor(lambda: self.set_state("flee", 30))

    def tag_caught(self):
        t = round(self.time - self.game["t0"], 1)
        self.game = None
        self.set_state("dizzy", 2)
        self.sayl("tag_caught", t=t)
        self.party(small=True)

    def flee_logic(self, mx, my):
        """Tag: run away from the cursor, dodge with jumps, leap over it when cornered. True if he jumped."""
        k = self.k
        L_, T_, R_, B_ = self.mon
        dx = self.fx - mx
        dy = my - (self.fy - self.PH / 2)
        if abs(dx) < 650 * k and abs(dy) < 500 * k:
            self.dir = 1 if dx > 0 else -1
        h = self.half()
        cornered = (self.fx < L_ + h + 25 * k and self.dir < 0) or (self.fx > R_ - h - 25 * k and self.dir > 0)
        close = math.hypot(dx, dy) < 190 * k
        if (cornered and abs(dx) < 400 * k and self.cooldown("leap", 1)) or (close and self.cooldown("dodge", .7)):
            away = -self.dir if cornered else (1 if dx > 0 else -1)
            self.launch(away * random.uniform(500, 800) * k, -random.uniform(950, 1250) * k)
            self.state = "jump"
            if random.random() < .35:
                self.spin = -away * 2 * math.pi / .85
            self.sfx("whoosh", .5)
            if self.cooldown("taunt", 3):
                self.sayl("taunt")
            return True
        return False

    def game_guess(self):
        self.end_game()
        self.game = {"kind": "guess", "n": random.randint(1, 100), "tries": 0}
        self.open_chat()
        self.deliver(self.line("guess_start"), [])
        if self.surf not in ("air",):
            self.set_state("think", 2.5)

    def guess_input(self, n):
        gm = self.game
        gm["tries"] += 1
        if n == gm["n"]:
            msg = self.line("guess_ok", n=n, t=gm["tries"], c=self.c_())
            self.game = None
            self.party()
        else:
            msg = self.line("guess_hi" if n < gm["n"] else "guess_lo")
            self.sqv -= 4
        self.deliver(msg, [])

    def game_ttt(self):
        g = self.game
        if g and g.get("kind") == "ttt":
            try:
                return g["win"].win.lift()
            except tk.TclError:
                pass
        self.end_game()
        self.game = {"kind": "ttt", "win": TicTacToe(self)}
        self.sayl("ttt_start")

    def ttt_result(self, res):
        if res == "X":
            self.set_state("sad", 2.5)
            self.sayl("ttt_lose")
            self.party(small=True)
        elif res == "O":
            self.set_state("dance", 3)
            self.sayl("ttt_win")
        else:
            self.set_state("think", 2)
            self.sayl("ttt_draw")

    def game_fetch(self):
        if not self.ball:
            self.toggle_ball()
        self.fetch_n = 0
        self.root.after(1500, lambda: self.sayl("fetch_hint"))

    def ball_hit(self, b, sp):
        """The ball hit him (you threw it at him!)."""
        k = self.k
        cx, cy = self.pet_center()
        side = 1 if b.x > cx else -1
        b.vx = side * max(350 * k, abs(b.vx) * .45)
        b.vy = -abs(b.vy) * .35 - 450 * k
        b.plat = None
        self.sfx("boing", .6)
        self.spawn("bang")
        if self.state == "sleep":
            self.afk = False
            self.set_state("idle")
            return self.say(self.line("wake"))
        if self.state in ("drag", "hide", "flee", "exercise", "ask") or self.surf == "air":
            return
        if sp > 2300 * k:
            self.set_state("dizzy", 1.8)
            self.sayl("ball_hit")
            self.happy = max(0, self.happy - 3)
        else:
            self.sqv -= 6
            if self.cooldown("header_say", 5):
                self.sayl("header")
            if self.surf == "floor" and not self.stay and self.state in ("idle", "walk", "look", "think", "dance", "lounge"):
                self.set_state("play", 8)

    # ---------------------------------------------------------- ball toy
    def toggle_ball(self):
        if self.ball:
            self.ball.win.destroy()
            self.ball = None
            return
        self.ball = Ball(self)
        self.say(self.line("ball"))
        if self.surf == "floor":
            self.set_state("play", 10)

    def update_ball(self, dt):
        if self.ball:
            self.ball.step(dt)

    # ---------------------------------------------------------- drawing
    def rect(self, u1, v1, u2, v2, color, tag="pet"):
        x1, y1 = self.T(u1, v1)
        x2, y2 = self.T(u2, v2)
        if self.rot:
            x3, y3 = self.T(u2, v1)
            x4, y4 = self.T(u1, v2)
            self.c.create_polygon(x1, y1, x3, y3, x2, y2, x4, y4, fill=color, outline="", tags=tag)
        else:
            self.c.create_rectangle(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2), fill=color, outline="", tags=tag)

    def line_uv(self, pts, width, color=BLACK):
        flat = []
        for u, v in pts:
            flat += self.T(u, v)
        self.c.create_line(*flat, fill=color, width=width, tags="pet", capstyle="round", joinstyle="round")

    def sprite(self, rows, x, y, ps, color, colors=None, tag="fx"):
        for r, row in enumerate(rows):
            for c_, ch in enumerate(row):
                if ch != ".":
                    col = colors.get(ch, color) if colors else color
                    self.c.create_rectangle(x + c_ * ps, y + r * ps, x + (c_ + 1) * ps, y + (r + 1) * ps,
                                            fill=col, outline="", tags=tag)

    ARM_POS = {"down": (3, 3), "up": (1, 1), "wave": (1, 3), "wave2": (3, 1), "high": (-1, -1)}

    def draw(self, mx, my):
        c, P, k = self.c, self.P, self.k
        c.delete("all")
        self.dsurf = "floor" if self.surf in ("air", "fly") else self.surf
        self.anchor = self.feet_canvas(self.surf)
        pose = self.pose
        s = self.state

        # squash & stretch
        sq = self.sq
        if self.surf == "air" and s != "drag" and not self.spin:
            sq = -min(.18, abs(self.vy) / (9000 * k))
        self.sx, self.sy = 1 + sq * .55, 1 - sq * .6
        if s in ("idle", "listen", "hang", "sleep", "look"):
            self.sy *= 1 + math.sin(self.time * (2 if s == "sleep" else 2.4)) * (.04 if s == "sleep" else .02)  # breathing
        self.bob = pose["bob"]

        # eye direction follows the mouse
        pcx, pcy = self.pet_center()
        lx, ly = self.local_dir(mx - pcx, my - pcy)
        tu = max(-1, min(1, lx / (220 * k))) * .55
        tv = max(-1, min(1, ly / (220 * k))) * .5
        frozen = self.time < self.hover_until
        if s in ("peek", "moonwalk") or (s == "dance" and getattr(self, "_moon", False)):
            tu, tv = self.look[0], 0
        elif s == "look":
            tu, tv = getattr(self, "look_override", (0, 0))
        elif s in ("walk", "chase", "play", "fly", "come") and not frozen:
            tu, tv = self.dir * .5 * (1 if self.dsurf in ("floor", "lwall") else -1), 0
        elif s == "code":
            tu, tv = 0, .5
        elif s in ("build", "mine", "doodle", "smash"):
            tu, tv = self.dir * .5, .35
        elif s == "think":
            tu, tv = (.5 if int(self.time / 1.2) % 2 else -.5), -.5
        a = min(1, self.dt * 12)
        self.look[0] += (tu - self.look[0]) * a
        self.look[1] += (tv - self.look[1]) * a
        eu, ev = self.look

        eyes = pose["eyes"]
        ov = getattr(self, "eyes_override", None)
        if ov and self.time < ov[1] and eyes == "open":
            eyes = ov[0]
        if eyes == "open":
            if self.time > self.blink_at:
                if self.time < self.blink_at + .12:
                    eyes = "closed"
                else:
                    self.blink_at = self.time + random.uniform(2, 6) * (.5 if random.random() < .2 else 1)
            elif self.energy < 15:
                eyes = "half"

        # body
        self.rect(2, 0, 14, 7, ORANGE)
        # arms (eased towards the pose, so they move smoothly instead of snapping)
        arms = pose["arms"]
        if arms in self.ARM_POS:
            tgt = self.ARM_POS[arms]
            e = min(1, self.dt * 22)
            self.arm[0] += (tgt[0] - self.arm[0]) * e
            self.arm[1] += (tgt[1] - self.arm[1]) * e
            l_, r_ = self.arm
            self.rect(0, l_, 2, l_ + 2, ORANGE)
            self.rect(14, r_, 16, r_ + 2, ORANGE)
        elif arms == "type":
            kk = int(self.time * 8) % 2
            self.rect(.6, 4 + kk * .5, 2.6, 6 + kk * .5, ORANGE); self.rect(13.4, 4.5 - kk * .5, 15.4, 6.5 - kk * .5, ORANGE)
        # legs: custom (exercise), smooth walk cycle, or simple frames
        cols = (3, 5, 10, 12)
        if "leg" in pose:
            for col, (dx, ln) in zip(cols, pose["leg"]):
                self.rect(col + dx, 7, col + dx + 1, 7 + max(.3, ln), ORANGE)
        elif pose.get("gait") is not None:
            g = pose["gait"]
            for i, col in enumerate(cols):
                lift = max(0.0, math.sin(g + (0 if i % 2 == 0 else math.pi)))
                self.rect(col, 7, col + 1, 9 - .9 * lift, ORANGE)
        else:
            legs = pose["legs"]
            for i, col in enumerate(cols):
                short = (legs == 1 and i % 2 == 0) or (legs == 2 and i % 2 == 1)
                self.rect(col, 7, col + 1, 8 if short else 9, ORANGE)
        for u1, v1, u2, v2, col in pose.get("extra", ()):
            self.rect(u1, v1, u2, v2, col)

        # eyes
        w = max(2, P * .45)
        for side, col in ((-1, 4), (1, 11)):
            u, v = col + eu, 2 + ev
            if eyes == "open":
                self.rect(u, v, u + 1, v + 2, BLACK)
            elif eyes == "big":
                self.rect(u - .25, v - .4, u + 1.25, v + 2.2, BLACK)
                self.rect(u + .5, v - .1, u + 1, v + .5, "white")
            elif eyes == "half":
                self.rect(u, v + 1, u + 1, v + 2, BLACK)
            elif eyes == "angry":
                self.rect(u, v + .3, u + 1, v + 2, BLACK)
                inner, outer = (col + 1.5, col - .6) if side < 0 else (col - .5, col + 1.6)
                self.line_uv([(outer, 1.0), (inner, 1.8)], w)
            elif eyes == "closed":
                self.rect(u - .3, v + 1.1, u + 1.3, v + 1.55, BLACK)
            elif eyes == "happy":
                self.line_uv([(u - .35, v + 1.6), (u + .5, v + .7), (u + 1.35, v + 1.6)], w)
            elif eyes == "x":
                self.line_uv([(u - .3, v), (u + 1.3, v + 2)], w)
                self.line_uv([(u + 1.3, v), (u - .3, v + 2)], w)
            if pose.get("blush"):
                self.rect(col - 1 + (0 if side < 0 else 1.5), 4.6, col + .5 + (0 if side < 0 else 1.5), 5.3, "#F29C9C", "fx")
        if pose.get("mouth"):
            self.rect(7.2, 4.3, 8.8, 5.8, BLACK)
        if pose.get("shades"):   # cool sunglasses
            self.rect(2.8, 1.7, 13.2, 2.3, BLACK)
            self.rect(3.2, 1.7, 6.6, 4.2, BLACK)
            self.rect(9.4, 1.7, 12.8, 4.2, BLACK)
            self.rect(3.7, 2.1, 4.5, 2.6, "white", "fx")
            self.rect(9.9, 2.1, 10.7, 2.6, "white", "fx")
        if s == "laser":
            for col in (4, 11):
                self.rect(col + eu - .25, 2 + ev - .25, col + eu + 1.25, 2 + ev + 2.25, "#FF2D2D", "fx")

        # hats & gear
        if self.surf == "fly":  # propeller hat
            self.rect(5, -.9, 11, .2, "#4A7BD0", "pet")
            self.rect(6.5, -1.5, 9.5, -.9, "#4A7BD0", "pet")
            self.rect(7.7, -2.4, 8.3, -1.5, "#555555", "pet")
            spin = int(self.time * 24) % 4
            span = (4.5, 2.5, .6, 2.5)[spin]
            self.rect(8 - span, -2.9, 8 + span, -2.4, ("#F5C542", "#E5484D")[spin % 2], "pet")
        elif s in ("build", "mine", "smash"):   # hard hat (+ a lamp for mining)
            self.rect(2, -.3, 14, .4, "#D9A520")
            self.rect(3.5, -1.4, 12.5, -.3, "#F5C542")
            self.rect(5.5, -2.1, 10.5, -1.4, "#F5C542")
            if s == "mine":
                self.rect(7.2, -1.2, 8.8, -.5, "#FFF6B0")
        elif pose.get("nightcap"):
            self.rect(3, -.6, 11, .3, "#4A6FA5")
            self.rect(5, -1.5, 10, -.6, "#4A6FA5")
            self.rect(7.5, -2.3, 11, -1.5, "#4A6FA5")
            self.rect(11, -2.6, 12.2, -1.4, "white")
        if (self.audio.playing or s == "dance") and self.surf != "fly" and s not in ("sleep", "exercise", "build", "mine", "smash"):  # headphones
            self.rect(1.4, -1.1, 14.6, -.4, "#2b2b2b")
            self.rect(1.0, -.4, 2.0, 3.8, "#2b2b2b")
            self.rect(14.0, -.4, 15.0, 3.8, "#2b2b2b")
            self.rect(.5, 1.2, 2.2, 3.6, "#E5484D")
            self.rect(13.8, 1.2, 15.5, 3.6, "#E5484D")
        if s == "exercise" and self.ex and self.ex["kind"] != "yoga":  # sweatband
            self.rect(2, .6, 14, 1.3, "#E5484D")

        # little pin when told to stay
        if self.stay and s != "sleep":
            self.rect(14.6, -2.2, 16, -.8, "#E5484D", "fx")
            self.rect(15.15, -.8, 15.45, .4, "#777777", "fx")

        # laptop
        if s == "code":
            self.rect(3, 4, 13, 7.6, "#3b3b3b")
            self.rect(3.5, 4.4, 12.5, 7.2, "#1b1f24")
            for i in range(3):
                ww = 2 + (hash((int(self.time * 3), i)) % 6)
                self.rect(4, 4.8 + i * .8, 4 + ww, 5.2 + i * .8, ("#7ee787", ORANGE, "#79c0ff")[i])
            self.rect(2, 7.6, 14, 8.2, "#9a9a9a")

        # cookie
        if s == "eat":
            pal = {"B": "#C8873A", "d": "#5A3A1E"}
            if self.timer > 2.5:
                vtop = -10 + (3.5 - self.timer) * 12
                rows = COOKIE
            else:
                vtop = 2
                rows = COOKIE[:max(0, int(self.timer / 2.5 * 6) + 1)]
            for r_, row in enumerate(rows):
                for c_, ch in enumerate(row):
                    if ch != ".":
                        self.rect(6.5 + c_ * .5, vtop + r_ * .5, 7 + c_ * .5, vtop + r_ * .5 + .5, pal[ch], "fx")
        if s == "beg":  # thought bubble with a cookie
            for (u, v, r_) in ((15, -1, .35), (16.2, -2.6, .55)):
                self.rect(u - r_, v - r_, u + r_, v + r_, "white", "fx")
            self.rect(16.5, -7.4, 22.5, -3.4, "white", "fx")
            pal = {"B": "#C8873A", "d": "#5A3A1E"}
            for r_, row in enumerate(COOKIE):
                for c_, ch in enumerate(row):
                    if ch != ".":
                        self.rect(18 + c_ * .5, -6.9 + r_ * .5, 18.5 + c_ * .5, -6.4 + r_ * .5, pal[ch], "fx")

        # dizzy stars
        if s == "dizzy":
            for i in range(3):
                ang = self.time * 5 + i * 2.094
                u, v = 8 + math.cos(ang) * 6, -1.6 + math.sin(ang) * .9
                self.rect(u - .3, v - .1, u + .3, v + .1, "#F5C542", "fx")
                self.rect(u - .1, v - .3, u + .1, v + .3, "#F5C542", "fx")

        # particles
        ps = max(2, P // 2)
        for kind, x, y, _, _, life, life0 in self.parts:
            rows, color = SPR[kind]
            size = ps if kind not in ("crumb", "spark") else max(2, P // 3)
            self.sprite(rows, x, y, size, color)

        # hiding behind a window / the taskbar: cut away the part of him that is "behind" it
        masks = self.hide_masks()
        for x1, y1, x2, y2 in masks:
            c.create_rectangle(x1 - self.wx, y1 - self.wy, x2 - self.wx, y2 - self.wy, fill=KEY, outline="", tags="mask")
        hi = self.hide_info
        if masks and s == "hide" and hi and hi["kind"] != "side" and self.PH * .3 < self.sink < self.PH * .95:
            ey = (self.plat_rect[1] if self.plat else self.mon[3]) - self.wy
            for u in (3.5, 12.5):   # little hands gripping the edge
                hx = self.T(u, 0)[0]
                c.create_rectangle(hx - P * .9, ey - P * .75, hx + P * .9, ey + P * .2, fill=ORANGE, outline="", tags="pet")

        # pet bbox and visible area (for bubbles and hover detection)
        top = -3 if self.surf == "fly" or (self.audio.playing and s != "sleep") else 0
        xs, ys = zip(self.T(0, top), self.T(16, 9), self.T(16, top), self.T(0, 9))
        self.pbox = (min(xs), min(ys), max(xs), max(ys))
        L_, T_, R_, B_ = self.mon
        self.vis = (max(0, L_ - self.wx), max(0, T_ - self.wy), min(self.S, R_ - self.wx), min(self.S, B_ - self.wy))

        # overlays
        offset = 0
        if self.timers:
            offset = self.draw_timer_pill()
        if self.ask_req:
            self.draw_ask(offset)
        elif s == "think" or self.waiting or (s in ("build", "mine") and self.work and not self.work.get("done")):
            spin = SPIN[int(self.time * 12) % len(SPIN)]
            self.draw_bubble(f"{spin} {self.word}{'.' * (1 + int(self.time * 3) % 3)}", offset, ORANGE)
        elif self.bubble is not None:
            if self.shown < len(self.bubble):
                self.shown += 48 * self.dt
                if self.cfg["talk"] and self.time > self.talk_next and not self.bubble[int(min(self.shown, len(self.bubble) - 1))].isspace():
                    self.talk_next = self.time + .07
                    self.sfx(f"talk{random.randint(0, 3)}", .8)
            else:
                self.bubble_t -= self.dt
                if self.bubble_t <= 0:
                    self.next_bubble()
            if self.bubble:
                more = "  ▸" if self.say_queue and self.shown >= len(self.bubble) else ""
                self.draw_bubble(self.bubble[:int(self.shown)] + more, offset, full=self.bubble + more)

    def free_box(self, bw, bh, gap):
        x1, y1, x2, y2 = self.pbox
        v = self.vis
        o = self.dsurf
        if o == "ceil":
            bx, by = (x1 + x2) / 2 - bw / 2, y2 + gap
        elif o == "lwall":
            bx, by = x2 + gap, (y1 + y2) / 2 - bh / 2
        elif o == "rwall":
            bx, by = x1 - gap - bw, (y1 + y2) / 2 - bh / 2
        else:
            bx, by = (x1 + x2) / 2 - bw / 2, y1 - gap - bh
        bx = min(max(bx, v[0] + 4), max(v[0] + 4, v[2] - 4 - bw))
        by = min(max(by, v[1] + 4), max(v[1] + 4, v[3] - 4 - bh))
        return bx, by

    def max_text_w(self):
        x1, y1, x2, y2 = self.pbox
        v, k = self.vis, self.k
        if self.dsurf == "lwall":
            w = v[2] - x2 - 50 * k
        elif self.dsurf == "rwall":
            w = x1 - v[0] - 50 * k
        else:
            w = v[2] - v[0] - 50 * k
        return max(140 * k, min(w, 380 * k))

    def tail(self, bx, by, bw, bh, gap):
        x1, y1, x2, y2 = self.pbox
        k, c = self.k, self.c
        o, d = self.dsurf, 8 * k
        if o in ("floor", "air"):
            cx = min(max((x1 + x2) / 2, bx + 14 * k), bx + bw - 14 * k)
            pts, cover = (cx - d, by + bh - 1, cx + d, by + bh - 1, (x1 + x2) / 2, y1 - 3), (cx - d + 2, by + bh - 1, cx + d - 2, by + bh - 1)
        elif o == "ceil":
            cx = min(max((x1 + x2) / 2, bx + 14 * k), bx + bw - 14 * k)
            pts, cover = (cx - d, by + 1, cx + d, by + 1, (x1 + x2) / 2, y2 + 3), (cx - d + 2, by + 1, cx + d - 2, by + 1)
        elif o == "lwall":
            cy = min(max((y1 + y2) / 2, by + 14 * k), by + bh - 14 * k)
            pts, cover = (bx + 1, cy - d, bx + 1, cy + d, x2 + 3, (y1 + y2) / 2), (bx + 1, cy - d + 2, bx + 1, cy + d - 2)
        else:
            cy = min(max((y1 + y2) / 2, by + 14 * k), by + bh - 14 * k)
            pts, cover = (bx + bw - 1, cy - d, bx + bw - 1, cy + d, x1 - 3, (y1 + y2) / 2), (bx + bw - 1, cy - d + 2, bx + bw - 1, cy + d - 2)
        t = c.create_polygon(*pts, fill="white", outline=ORANGE, width=max(2, 2 * k / 1.5), tags="bubble")
        c.create_line(*cover, fill="white", width=max(3, 3 * k / 1.5), tags="bubble")
        return t

    def round_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.c.create_polygon(pts, smooth=True, **kw)

    def draw_bubble(self, text, offset, color=BLACK, full=None):
        c, k = self.c, self.k
        ar = is_ar(full or text)
        font = ("Segoe UI", 11, "bold")
        mw = self.max_text_w()
        probe = c.create_text(0, 0, text=full or text or " ", anchor="nw", width=mw, font=font, justify="right" if ar else "left")
        bx1, by1, bx2, by2 = c.bbox(probe)
        c.delete(probe)
        pad = 11 * k
        bw, bh = bx2 - bx1 + 2 * pad, by2 - by1 + 1.6 * pad
        gap = 14 * k + offset
        bx, by = self.free_box(bw, bh, gap)
        rr = self.round_rect(bx, by, bx + bw, by + bh, 12 * k, fill="white", outline=ORANGE, width=max(2, 2 * k / 1.5), tags="bubble")
        if offset == 0:
            self.tail(bx, by, bw, bh, gap)
        if ar:
            c.create_text(bx + bw - pad, by + .8 * pad, text=text or " ", anchor="ne", width=mw, font=font,
                          justify="right", fill=color, tags="bubble")
        else:
            c.create_text(bx + pad, by + .8 * pad, text=text or " ", anchor="nw", width=mw, font=font,
                          justify="left", fill=color, tags="bubble")

    def draw_timer_pill(self):
        c, k = self.c, self.k
        t = min(self.timers, key=lambda t: t["end"])
        left = max(0, int(t["end"] - time.time()))
        h_, rem = divmod(left, 3600)
        m_, s_ = divmod(rem, 60)
        txt = (f"{h_}:{m_:02d}:{s_:02d}" if h_ else f"{m_}:{s_:02d}") + (f"  {t['label']}" if t["label"] else "")
        if len(self.timers) > 1:
            txt += f"  (+{len(self.timers) - 1})"
        font = ("Segoe UI", 10, "bold")
        probe = c.create_text(0, 0, text="⏱ " + txt, anchor="nw", font=font)
        x1, y1, x2, y2 = c.bbox(probe)
        c.delete(probe)
        pw, ph = x2 - x1 + 20 * k, y2 - y1 + 8 * k
        bx, by = self.free_box(pw, ph, 8 * k)
        urgent = left <= 10 and int(self.time * 4) % 2
        self.round_rect(bx, by, bx + pw, by + ph, ph / 2, fill=ORANGE if urgent else "#2b2b2b", outline="", tags="bubble")
        c.create_text(bx + pw / 2, by + ph / 2, text="⏱ " + txt, font=font, fill="white", tags="bubble")
        return (pw if self.dsurf in ("lwall", "rwall") else ph) + 8 * k

    def draw_ask(self, offset):
        c, k = self.c, self.k
        req = self.ask_req
        ar = self.lang == "ar"
        bw, bh = 380 * k, 150 * k
        gap = 14 * k + offset
        x0, y0 = self.free_box(bw, bh, gap)
        self.round_rect(x0, y0, x0 + bw, y0 + bh, 14 * k, fill="white", outline=ORANGE, width=max(2, 2 * k / 1.5))
        if offset == 0:
            self.tail(x0, y0, bw, bh, gap)
        s = lambda n: n * k
        anchor, tx = ("e", x0 + bw - s(14)) if ar else ("w", x0 + s(14))
        c.create_text(tx, y0 + s(18), anchor=anchor, text=self.tr("wants", tool=req["tool"]),
                      font=("Segoe UI", 11, "bold"), fill=ORANGE)
        c.create_rectangle(x0 + s(12), y0 + s(32), x0 + bw - s(12), y0 + s(70), fill=CREAM, outline="")
        c.create_text(x0 + s(20), y0 + s(51), anchor="w", text=req["cmd"][:200], width=bw - s(40), font=("Consolas", 10), fill=BLACK)
        c.create_text(tx, y0 + s(86), anchor=anchor, text=self.tr("proceed", s=max(0, int(req["until"] - self.time))),
                      font=("Segoe UI", 10), fill="#444")
        hot = int(self.time * 3) % 2
        bwid = (bw - s(24) - s(16)) / 3
        order = [("b_yes", "yes"), ("b_always", "always"), ("b_no", "no")]
        if ar:
            order = order[::-1]
        for i, (label, key) in enumerate(order):
            x1 = x0 + s(12) + i * (bwid + s(8))
            fill = (ORANGE if hot else "#E08B6F") if key == "yes" else "#EDE6DC"
            tag = "btn_" + key
            c.create_rectangle(x1, y0 + s(100), x1 + bwid, y0 + s(132), fill=fill, outline="", tags=tag)
            c.create_text(x1 + bwid / 2, y0 + s(116), text=self.tr(label), tags=tag, font=("Segoe UI", 10, "bold"),
                          fill="white" if key == "yes" else BLACK)

    # ---------------------------------------------------------- chat panel
    def open_chat(self):
        if self.chat:
            self.chat.deiconify()
            self.chat.lift()
            self.chat_entry.focus_force()
            return
        k, ar = self.k, self.lang == "ar"
        w = self.chat = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        outer = tk.Frame(w, bg=ORANGE, padx=2, pady=2)
        outer.pack(fill="both", expand=True)
        head = tk.Frame(outer, bg=ORANGE)
        head.pack(fill="x")
        brain = self.brain.label() if self.brain.ready() else self.tr("brain_off")
        title = tk.Label(head, text=f"  ✻ Clawd   ·   {brain}", bg=ORANGE, fg="white", font=("Segoe UI", 10, "bold"))
        title.pack(side="left", pady=3)

        def btn(text, cmd):
            b = tk.Label(head, text=text, bg=ORANGE, fg="white", font=("Segoe UI", 10, "bold"), padx=8, cursor="hand2")
            b.pack(side="right")
            b.bind("<Button-1>", lambda e: cmd())
            return b

        btn("✕", self.close_chat)
        btn("⚙", lambda: self.open_settings(1))
        btn(self.tr("clear"), self.clear_chat)

        def start_move(e):
            w._ox, w._oy = e.x_root - w.winfo_x(), e.y_root - w.winfo_y()

        def do_move(e):
            w.geometry(f"+{e.x_root - w._ox}+{e.y_root - w._oy}")
        for wd in (head, title):
            wd.bind("<ButtonPress-1>", start_move)
            wd.bind("<B1-Motion>", do_move)

        body = tk.Frame(outer, bg="white")
        body.pack(fill="both", expand=True)
        txt = self.chat_text = tk.Text(body, width=48, height=13, wrap="word", bg="white", relief="flat", bd=0,
                                       font=("Segoe UI", 10), padx=10, pady=8, cursor="arrow", spacing1=2, spacing3=4)
        sb = ttk.Scrollbar(body, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        txt.tag_configure("me_name", foreground=ORANGE, font=("Segoe UI", 10, "bold"))
        txt.tag_configure("bot_name", foreground=BLACK, font=("Segoe UI", 10, "bold"))
        txt.tag_configure("me", foreground="#5a3420")
        txt.tag_configure("bot", foreground=BLACK)
        txt.tag_configure("sys", foreground="#999", font=("Segoe UI", 9, "italic"))
        txt.tag_configure("tool", foreground="#8a5a44", font=("Consolas", 9, "bold"), lmargin1=6, lmargin2=6)
        txt.tag_configure("tool_r", foreground="#999", font=("Consolas", 9), lmargin1=6, lmargin2=24)
        txt.tag_configure("rtl", justify="right")
        bottom = tk.Frame(outer, bg=CREAM, padx=8, pady=8)
        bottom.pack(fill="x")
        ent = self.chat_entry = tk.Entry(bottom, font=("Segoe UI", 11), relief="flat", bg="white",
                                         justify="right" if ar else "left")
        send = tk.Label(bottom, text=self.tr("send"), bg=ORANGE, fg="white", font=("Segoe UI", 10, "bold"),
                        padx=12, pady=4, cursor="hand2")
        if ar:
            send.pack(side="left", padx=(0, 6))
            ent.pack(side="right", fill="x", expand=True, ipady=5)
        else:
            send.pack(side="right", padx=(6, 0))
            ent.pack(side="left", fill="x", expand=True, ipady=5)
        chips = tk.Frame(outer, bg=CREAM, padx=6)
        chips.pack(fill="x")
        chip_list = ([("💪 تمرين", "تمرين"), ("😂 نكتة", "نكتة"), ("🎵 موسيقى", "شغل موسيقى"), ("☀ الطقس", "الطقس"),
                      ("▶ يوتيوب", None), ("⏱ 5 د", "مؤقت 5 دقائق")] if ar else
                     [("💪 Workout", "workout"), ("😂 Joke", "joke"), ("🎵 Music", "play music"), ("☀ Weather", "weather"),
                      ("▶ YouTube", None), ("⏱ 5 min", "timer 5 min")])
        for label, cmd in chip_list:
            ch = tk.Label(chips, text=label, bg="white", fg="#5a3420", font=("Segoe UI", 8, "bold"), padx=6, pady=2,
                          cursor="hand2")
            ch.pack(side="right" if ar else "left", padx=2, pady=(0, 6))
            ch.bind("<Button-1>", lambda e, c_=cmd: self.ask_youtube() if c_ is None else self.handle_text(c_))
            ch.bind("<Enter>", lambda e, w_=ch: w_.configure(bg="#FBE3D8"))
            ch.bind("<Leave>", lambda e, w_=ch: w_.configure(bg="white"))
        tk.Label(outer, text=self.tr("chat_hint"), bg=CREAM, fg="#8a8a8a", font=("Segoe UI", 8),
                 wraplength=int(420 * k)).pack(fill="x")
        sent = [m for who, m in self.chat_log if who == "me"]
        hist = {"i": len(sent)}

        def submit(_=None):
            text = ent.get()
            ent.delete(0, "end")
            if text.strip():
                sent.append(text)
                hist["i"] = len(sent)
            self.handle_text(text)

        def recall(d):
            if sent:
                hist["i"] = max(0, min(len(sent), hist["i"] + d))
                ent.delete(0, "end")
                ent.insert(0, sent[hist["i"]] if hist["i"] < len(sent) else "")
        ent.bind("<Up>", lambda e: recall(-1))
        ent.bind("<Down>", lambda e: recall(1))
        ent.bind("<Return>", submit)
        ent.bind("<Escape>", lambda e: self.close_chat())
        send.bind("<Button-1>", submit)
        w.update_idletasks()
        ww, wh = w.winfo_reqwidth(), w.winfo_reqheight()
        cx, cy = self.pet_center()
        L_, T_, R_, B_ = self.mon
        x = cx - ww / 2
        y = cy - self.PH - wh - 20 * k if self.surf != "ceil" else cy + self.PH + 20 * k
        if self.surf == "lwall":
            x, y = cx + self.PH + 20 * k, cy - wh / 2
        elif self.surf == "rwall":
            x, y = cx - self.PH - 20 * k - ww, cy - wh / 2
        x = min(max(L_ + 8, x), R_ - ww - 8)
        y = min(max(T_ + 8, y), B_ - wh - 8)
        w.geometry(f"+{int(x)}+{int(y)}")
        self.render_chat()
        ent.focus_force()
        if self.state in ("idle", "walk", "chase", "think", "code", "dance") and not self.audio.playing:
            self.state, self.timer = "listen", 1e6

    def close_chat(self):
        if self.chat:
            self.save_chat()
            self.chat.destroy()
            self.chat = None
            if self.state == "listen":
                self.set_state("idle", 1)

    def clear_chat(self):
        self.chat_log, self.history = [], []
        self.agent = None
        self.save_chat()
        self.render_chat()

    def render_chat(self):
        if not self.chat:
            return
        t = self.chat_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        if not self.chat_log:
            t.insert("end", self.tr("chat_hint") + "\n", ("sys", "rtl") if self.lang == "ar" else ("sys",))
        log = self.chat_log[-70:]
        for i, (who, msg) in enumerate(log):
            if who in ("tool", "tool_r"):
                t.insert("end", msg + "\n", (who,))
                continue
            rtl = ("rtl",) if is_ar(msg) else ()
            name = (self.cfg["name"] or self.tr("you")) if who == "me" else "Clawd"
            t.insert("end", ("\n" if i and log[i - 1][0] == "tool_r" else "") + name + "\n", (who + "_name",) + rtl)
            t.insert("end", msg + "\n\n", (who,) + rtl)
        if self.waiting:
            t.insert("end", "✻ " + (self.word if self.agent else self.tr("thinking")) + "...\n", ("sys",))
        t.configure(state="disabled")
        t.see("end")

    # ---------------------------------------------------------- settings window
    def open_settings(self, tab=0):
        if self.settings_win:
            try:
                self.settings_win.lift()
                self.settings_nb.select(tab)
                return
            except tk.TclError:
                self.settings_win = None
        k = self.k
        w = self.settings_win = tk.Toplevel(self.root)
        w.title(self.tr("set_title"))
        w.attributes("-topmost", True)
        if os.path.exists(ICON):
            try:
                w.iconbitmap(ICON)
            except tk.TclError:
                pass
        w.resizable(False, False)
        w.protocol("WM_DELETE_WINDOW", self.close_settings)
        st = ttk.Style(w)
        try:
            st.theme_use("vista")
        except tk.TclError:
            pass
        nb = self.settings_nb = ttk.Notebook(w)
        nb.pack(fill="both", expand=True, padx=10, pady=10)
        g = ttk.Frame(nb, padding=14)
        b = ttk.Frame(nb, padding=14)
        nb.add(g, text=self.tr("tab_general"))
        nb.add(b, text=self.tr("tab_brain"))
        cfg = self.cfg

        # --- general
        row = 0
        ttk.Label(g, text=self.tr("name_lbl")).grid(row=row, column=0, sticky="w", pady=4)
        name_v = tk.StringVar(value=cfg.get("name", ""))
        name_e = ttk.Entry(g, textvariable=name_v, width=26)
        name_e.grid(row=row, column=1, sticky="w")

        def name_changed(*_):
            cfg["name"] = name_v.get().strip()[:24]
            self.awaiting_name = False
        name_v.trace_add("write", name_changed)
        name_e.bind("<Return>", lambda e: cfg["name"] and self.set_name(cfg["name"]))
        row += 1
        ttk.Label(g, text=self.tr("persona_lbl")).grid(row=row, column=0, sticky="w", pady=4)
        pnames, pkeys = list(T["personas"][1 if self.lang == "ar" else 0]), list(PERSONAS)
        pers_cb = ttk.Combobox(g, values=pnames, state="readonly", width=24)
        pers_cb.set(pnames[pkeys.index(cfg.get("personality", "balanced"))])
        pers_cb.grid(row=row, column=1, sticky="w")
        pers_cb.bind("<<ComboboxSelected>>", lambda e: self.set_persona(pkeys[pnames.index(pers_cb.get())]))
        row += 1
        ttk.Label(g, text=self.tr("lang_lbl")).grid(row=row, column=0, sticky="w", pady=4)
        lang_cb = ttk.Combobox(g, values=["English", "العربية"], state="readonly", width=24)
        lang_cb.set("العربية" if self.lang == "ar" else "English")
        lang_cb.grid(row=row, column=1, sticky="w")

        def set_lang(_=None):
            cfg["lang"] = "ar" if lang_cb.get() == "العربية" else "en"
            self.save()
            self.close_settings()
            if self.chat:
                self.close_chat()
                self.open_chat()
            self.open_settings(0)
            self.say("أهلاً! أتكلم العربية الآن." if self.lang == "ar" else "Hi! I speak English now.")
        lang_cb.bind("<<ComboboxSelected>>", set_lang)

        row += 1
        ttk.Label(g, text=self.tr("size_lbl")).grid(row=row, column=0, sticky="w", pady=4)
        size_v = tk.DoubleVar(value=cfg["scale"])
        ttk.Scale(g, from_=0.4, to=3.0, variable=size_v, length=int(200 * k / 1.5),
                  command=lambda v: self.apply_scale(float(v))).grid(row=row, column=1, sticky="w")

        def slider(label, key, apply=None):
            nonlocal row
            row += 1
            ttk.Label(g, text=self.tr(label)).grid(row=row, column=0, sticky="w", pady=4)
            var = tk.DoubleVar(value=cfg[key])

            def ch(v):
                cfg[key] = round(float(v), 2)
                if apply:
                    apply(cfg[key])
            ttk.Scale(g, from_=0, to=1, variable=var, length=int(200 * k / 1.5), command=ch).grid(row=row, column=1, sticky="w")

        slider("sfx_vol", "sfx_vol")
        slider("music_vol", "music_vol", self.audio.set_music_vol)

        row += 1
        ttk.Label(g, text=self.tr("asks_lbl")).grid(row=row, column=0, sticky="w", pady=4)
        rate_names = T["rates"][1 if self.lang == "ar" else 0]
        rate_keys = ["often", "normal", "rare", "off"]
        rate_cb = ttk.Combobox(g, values=list(rate_names), state="readonly", width=24)
        rate_cb.set(rate_names[rate_keys.index(cfg["ask_rate"])])
        rate_cb.grid(row=row, column=1, sticky="w")

        def set_rate(_=None):
            cfg["ask_rate"] = rate_keys[list(rate_names).index(rate_cb.get())]
            self.next_ask = self.roll_ask()
        rate_cb.bind("<<ComboboxSelected>>", set_rate)

        def check(label, key, cmd=None):
            nonlocal row
            row += 1
            var = tk.BooleanVar(value=cfg[key] if key else os.path.exists(STARTUP))

            def ch():
                if key:
                    cfg[key] = var.get()
                if cmd:
                    cmd(var.get())
            ttk.Checkbutton(g, text=self.tr(label), variable=var, command=ch).grid(row=row, column=0, columnspan=2, sticky="w", pady=2)

        check("sfx_lbl", "sound")
        check("talk_lbl", "talk")
        check("follow_lbl", "follow")
        check("climb_lbl", "climb")
        check("fly_lbl", "fly")
        check("windows_lbl", "windows")
        check("mischief_lbl", "mischief")
        check("deskfx_lbl", "desk_fx")
        check("smart_lbl", "smart")
        check("remind_lbl", "reminders")
        check("workout_lbl", "workout")
        check("focus_lbl", "focus_guard")
        check("startup_lbl", None, self.set_startup)
        row += 1
        ttk.Label(g, text=self.tr("help") + "\nCtrl+Alt+S: stay  |  Ctrl+Alt+H: hide / show  |  Ctrl+Alt+M: menu", foreground="#777",
                  justify="left").grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
        row += 1
        ttk.Label(g, text=self.tr("about", v=VERSION, p=DATA), foreground="#999", justify="left",
                  wraplength=int(460 * k / 1.3)).grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))
        row += 1
        ttk.Button(g, text=self.tr("data_dir"), command=lambda: os.startfile(DATA)).grid(row=row, column=0, sticky="w", pady=(6, 0))

        # --- brain
        order = list(PROVIDERS)
        names = [PROVIDERS[p]["name"] for p in order]
        ttk.Label(b, text=self.tr("provider")).grid(row=0, column=0, sticky="w", pady=5)
        prov_cb = ttk.Combobox(b, values=names, state="readonly", width=34)
        prov_cb.grid(row=0, column=1, columnspan=2, sticky="w")
        key_v, model_v, base_v = tk.StringVar(), tk.StringVar(), tk.StringVar()
        ttk.Label(b, text=self.tr("api_key")).grid(row=1, column=0, sticky="w", pady=5)
        key_e = ttk.Entry(b, textvariable=key_v, width=36, show="•")
        key_e.grid(row=1, column=1, sticky="w")
        show_v = tk.BooleanVar(value=False)
        ttk.Checkbutton(b, text=self.tr("show"), variable=show_v,
                        command=lambda: key_e.configure(show="" if show_v.get() else "•")).grid(row=1, column=2, sticky="w", padx=6)
        ttk.Label(b, text=self.tr("model")).grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(b, textvariable=model_v, width=36).grid(row=2, column=1, sticky="w")
        ttk.Label(b, text=self.tr("base_url")).grid(row=3, column=0, sticky="w", pady=5)
        ttk.Entry(b, textvariable=base_v, width=36).grid(row=3, column=1, sticky="w")
        btns = ttk.Frame(b)
        btns.grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 4))
        status = self.settings_lbl = ttk.Label(b, text="", wraplength=int(420 * k / 1.3))
        status.grid(row=5, column=0, columnspan=3, sticky="w")
        mem_row = ttk.Frame(b)
        mem_row.grid(row=7, column=0, columnspan=3, sticky="w", pady=(12, 0))
        mem_lbl = ttk.Label(mem_row, text=self.tr("memory_lbl", n=len(cfg["memory"])))
        mem_lbl.pack(side="left")

        def forget_all():
            cfg["memory"] = []
            self.save()
            mem_lbl.configure(text=self.tr("memory_lbl", n=0))
            self.say(self.line("forgot"))
        ttk.Button(mem_row, text=self.tr("forget_all"), command=forget_all).pack(side="left", padx=8)
        ttk.Label(b, text=self.tr("keys_note", p=CFG_PATH), foreground="#777", justify="left",
                  wraplength=int(440 * k / 1.3)).grid(row=6, column=0, columnspan=3, sticky="w", pady=(12, 0))
        loading = {"on": False}

        def load(p):
            loading["on"] = True
            d, bb = PROVIDERS[p], cfg["brains"].get(p, {})
            key_v.set(bb.get("key", ""))
            model_v.set(bb.get("model") or d["model"])
            base_v.set(bb.get("base") or d["base"])
            key_e.configure(state="normal" if d["key"] or p == "custom" else "disabled")
            loading["on"] = False

        def store(*_):
            if loading["on"]:
                return
            p = cfg["provider"]
            cfg["brains"][p] = {"key": key_v.get().strip(), "model": model_v.get().strip(), "base": base_v.get().strip()}

        for v in (key_v, model_v, base_v):
            v.trace_add("write", store)

        def pick(_=None):
            store()
            cfg["provider"] = order[names.index(prov_cb.get())]
            load(cfg["provider"])
            status.configure(text="")
        prov_cb.bind("<<ComboboxSelected>>", pick)
        prov_cb.set(PROVIDERS[cfg["provider"]]["name"])
        load(cfg["provider"])

        def test():
            store()
            self.save()
            status.configure(text=self.tr("testing"), foreground="#555")

            def work():
                try:
                    out = self.brain.complete("Reply with exactly: OK, I'm alive!", [{"role": "user", "content": "ping"}], 1000)
                    self.q.put(("test", True, out[:80] or "(empty)"))
                except BrainError as e:
                    key = {"key": "err_key", "rate": "err_rate", "model": "err_model", "conn": "err_conn"}.get(e.kind, "err_other")
                    self.q.put(("test", False, self.line(key, e=e.detail[:120]) + (f"  [{e.detail[:120]}]" if e.kind != "other" and e.detail else "")))
                except Exception as e:  # noqa
                    self.q.put(("test", False, str(e)[:160]))
            threading.Thread(target=work, daemon=True).start()

        ttk.Button(btns, text=self.tr("test"), command=test).pack(side="left")
        ttk.Button(btns, text=self.tr("get_key"),
                   command=lambda: webbrowser.open(PROVIDERS[cfg["provider"]]["url"]) if PROVIDERS[cfg["provider"]]["url"] else None).pack(side="left", padx=6)

        ttk.Button(w, text=self.tr("close"), command=self.close_settings).pack(pady=(0, 10))
        nb.select(tab)
        w.update_idletasks()
        L_, T_, R_, B_ = self.mon
        w.geometry(f"+{int((L_ + R_) / 2 - w.winfo_reqwidth() / 2)}+{int((T_ + B_) / 2 - w.winfo_reqheight() / 2)}")

    def settings_status(self, ok, msg):
        try:
            self.settings_lbl.configure(text=self.tr("test_ok", r=msg) if ok else msg,
                                        foreground="#1a7f37" if ok else "#c62828")
            if ok:
                self.say(self.line("brain_ok"))
                self.sfx("yes")
                self.set_state("dance", 3) if self.surf == "floor" else None
        except tk.TclError:
            pass

    def close_settings(self):
        if self.settings_win:
            if self.cfg["name"] and self.cfg["name"] != getattr(self, "_name_greeted", None):
                self._name_greeted = self.cfg["name"]
                self.set_name(self.cfg["name"])
            self.save()
            try:
                self.settings_win.destroy()
            except tk.TclError:
                pass
            self.settings_win = None
            if self.chat:
                self.close_chat()
                self.open_chat()

    def set_startup(self, on):
        try:
            if on:
                if FROZEN:
                    cmd = f'"""{sys.executable}"""'
                else:
                    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                    cmd = f'"""{pyw}"" ""{os.path.abspath(__file__)}"""'
                with open(STARTUP, "w", encoding="utf-8") as f:
                    f.write(f'CreateObject("WScript.Shell").Run {cmd}, 0\n')
                self.say(self.line("startup_on"))
            elif os.path.exists(STARTUP):
                os.remove(STARTUP)
                self.say(self.line("startup_off"))
        except OSError as e:
            self.say(str(e)[:80])

    # ---------------------------------------------------------- menu
    def menu_at_pet(self):
        cx, cy = self.pet_center()
        self.show_menu(type("E", (), {"x_root": int(cx), "y_root": int(cy)})())

    def user_do(self, fn):
        """Menu actions are explicit requests: un-pin 'stay' for movement, then run."""
        def go():
            self.stay = False
            fn()
        return go

    def show_menu(self, e):
        tr = self.tr
        self.hover_until = self.time + 1.5
        m = tk.Menu(self.root, tearoff=0)
        name = self.cfg["name"]
        m.add_command(label=tr("mood", h=int(self.happy), e=int(self.energy)) + "  -  " + tr("hungry_lbl", g=int(self.hunger))
                      + (f"  -  ♥ {name}" if name else ""), state="disabled")
        m.add_separator()
        m.add_command(label=tr("talk"), command=self.open_chat)
        stay_v = tk.BooleanVar(value=self.stay)
        m.add_checkbutton(label=tr("stay"), variable=stay_v, command=lambda: self.set_stay(stay_v.get()))
        m.add_command(label=tr("come"), command=self.come_here)
        if self.surf == "fly":
            m.add_command(label=tr("land"), command=lambda: self.run_action({"type": "land"}))
        else:
            m.add_command(label=tr("fly"), command=lambda: self.run_action({"type": "fly"}))
        m.add_separator()
        m.add_command(label=tr("feed"), command=self.feed)
        m.add_command(label=tr("ball_away") if self.ball else tr("ball"), command=self.toggle_ball)

        wo = tk.Menu(m, tearoff=0)
        wo.add_command(label="💪  " + tr("ex_all"), command=self.user_do(lambda: self.start_exercise(routine=True)))
        wo.add_separator()
        for kind in ROUTINE:
            wo.add_command(label=tr("ex_" + kind), command=lambda kd=kind: self.start_exercise(kd))
        m.add_cascade(label=tr("workout"), menu=wo)

        mu = tk.Menu(m, tearoff=0)
        mu.add_command(label="▶  " + tr("yt"), command=self.ask_youtube)
        mu.add_separator()
        playing = self.audio.playing[1] if self.audio.playing and self.audio.playing[0] == "track" else None
        for i, nm in enumerate(T["tracks"][1 if self.lang == "ar" else 0]):
            mu.add_command(label=("♫  " if i == playing else "♪  ") + nm, command=lambda i=i: self.music_cmd("play", i))
        mu.add_command(label="🔀  " + tr("shuffle"), command=lambda: self.music_cmd("play"))
        mu.add_command(label=tr("my_music"), command=lambda: self.music_cmd("files"))
        if self.audio.playing:
            mu.add_command(label=tr("next_song"), command=lambda: self.music_cmd("next"))
            mu.add_command(label=tr("stop_music"), command=lambda: self.music_cmd("stop"))
        mu.add_separator()
        mu.add_command(label=tr("sys_pp"), command=lambda: self.run_action({"type": "media", "cmd": "playpause"}))
        mu.add_command(label=tr("sys_next"), command=lambda: self.run_action({"type": "media", "cmd": "next"}))
        mu.add_command(label=tr("sys_prev"), command=lambda: self.run_action({"type": "media", "cmd": "prev"}))
        m.add_cascade(label=tr("music"), menu=mu)

        to = tk.Menu(m, tearoff=0)
        for n in (1, 5, 10):
            to.add_command(label=tr("timer_n", n=n), command=lambda n=n: self.add_timer(n * 60))
        to.add_command(label=tr("pomodoro"), command=self.start_pomodoro)
        to.add_command(label=tr("custom_timer"), command=self.custom_timer)
        if self.timers:
            to.add_command(label=tr("cancel_timers"), command=lambda: self.timers.clear())
        to.add_separator()
        to.add_command(label=tr("add_note"), command=self.ask_note)
        to.add_command(label=tr("open_notes"), command=self.open_notes)
        to.add_separator()
        cl = tk.Menu(to, tearoff=0)
        for key, mode in (("clip_explain", "explain"), ("clip_translate", "translate"), ("clip_summarize", "summarize"),
                          ("clip_fix", "fix"), ("clip_reply", "reply")):
            cl.add_command(label=tr(key), command=lambda md=mode: self.clip_tool(md))
        to.add_cascade(label=tr("clipboard"), menu=cl)
        to.add_command(label=tr("weather"), command=lambda: self.say_weather(""))
        to.add_command(label=tr("pc_status"), command=lambda: self.say(self.status_line()))
        to.add_command(label=tr("password"), command=self.make_password)
        to.add_command(label=tr("screenshot"), command=lambda: self.run_action({"type": "screenshot"}))
        m.add_cascade(label=tr("tools"), menu=to)

        fun = tk.Menu(m, tearoff=0)
        fun.add_command(label=tr("joke"), command=lambda: self.run_action({"type": "joke"}))
        fun.add_command(label=tr("motivate"), command=lambda: (self.say(self.line("motivate", c=self.c_())), self.set_state("proud")))
        fun.add_command(label=tr("compliment"), command=lambda: (self.say(self.line("compliment", c=self.c_())), self.set_state("wave")))
        fun.add_command(label=tr("sneeze"), command=lambda: self.set_state("sneeze"))
        fun.add_command(label=tr("moonwalk"), command=self.user_do(lambda: self.set_state("moonwalk")))
        fun.add_command(label=tr("peek"), command=self.go_peek)
        fun.add_command(label=tr("web"), command=self.start_web)
        fun.add_command(label=tr("ask_joke"), command=self.ask_joke)
        fun.add_separator()
        fun.add_command(label=tr("rps"), command=lambda: (self.rps(), self.open_chat()))
        fun.add_command(label=tr("coin"), command=lambda: self.run_action({"type": "coin"}))
        fun.add_command(label=tr("dice"), command=lambda: self.run_action({"type": "dice"}))
        fun.add_command(label=tr("stats"), command=lambda: self.say(self.stats_line()))
        m.add_cascade(label=tr("funny"), menu=fun)

        gm = tk.Menu(m, tearoff=0)
        gm.add_command(label="❌⭕  " + tr("ttt"), command=self.game_ttt)
        gm.add_command(label="🙈  " + tr("seek"), command=self.game_seek)
        gm.add_command(label="🏃  " + tr("tag"), command=self.game_tag)
        gm.add_command(label="🔢  " + tr("guess"), command=self.game_guess)
        gm.add_command(label="⚽  " + tr("fetch"), command=self.game_fetch)
        gm.add_command(label="✊  " + tr("rps"), command=lambda: (self.rps(), self.open_chat()))
        m.add_cascade(label=tr("games"), menu=gm)

        mi = tk.Menu(m, tearoff=0)
        mi.add_command(label="🦶  " + tr("kick_win"), command=lambda: self.go_kick(user=True))
        mi.add_command(label="🙈  " + tr("hide_win"), command=lambda: self.go_hide(user=True))
        if self.plat:
            mi.add_command(label="💥  " + tr("stomp"), command=self.user_do(lambda: self.set_state("stomp")))
        mi.add_separator()
        for key, ic in (("laser", "🔴"), ("doodle", "🖍"), ("smash", "🔨"), ("glitch", "📺"), ("build", "🧱"), ("mine", "⛏")):
            mi.add_command(label=ic + "  " + tr(key), command=lambda k_=key: self.start_trick(k_, user=True))
        mi.add_command(label="🎉  " + tr("confetti"), command=self.party)
        if self.win_orig:
            mi.add_separator()
            mi.add_command(label="↩  " + tr("undo_win"), command=self.undo_windows)
        m.add_cascade(label=tr("mischief"), menu=mi)

        pm = tk.Menu(m, tearoff=0)
        pv = tk.StringVar(value=self.cfg.get("personality", "balanced"))
        for key, nm in zip(PERSONAS, T["personas"][1 if self.lang == "ar" else 0]):
            pm.add_radiobutton(label=nm, variable=pv, value=key, command=lambda k_=key: self.set_persona(k_))
        m.add_cascade(label=tr("persona_lbl"), menu=pm)

        act = tk.Menu(m, tearoff=0)
        for key in ("dance", "code", "think", "sleep", "stretch"):
            act.add_command(label=tr(key), command=lambda s=key: self.set_state(s))
        act.add_command(label=tr("jump"), command=self.user_do(lambda: self.set_state("jump")))
        act.add_command(label=tr("walk"), command=self.user_do(lambda: self.need_floor(lambda: self.set_state("walk"))))
        act.add_command(label=tr("climb"), command=self.go_climb)
        act.add_command(label=tr("hop"), command=lambda: self.try_hop(user=True))
        act.add_command(label=tr("chase"), command=self.user_do(lambda: self.set_state("chase")))
        act.add_command(label=tr("say"), command=self.quip)
        m.add_cascade(label=tr("actions"), menu=act)
        m.add_separator()

        size = tk.Menu(m, tearoff=0)
        sv = tk.DoubleVar(value=self.cfg["scale"])
        for label, val in zip(T["sizes"][1 if self.lang == "ar" else 0], (.5, .75, 1.0, 1.4, 2.0, 3.0)):
            size.add_radiobutton(label=label, variable=sv, value=val, command=lambda v=val: (self.apply_scale(v), self.save()))
        m.add_cascade(label=tr("size"), menu=size)
        lg = tk.Menu(m, tearoff=0)
        lv = tk.StringVar(value=self.lang)
        lg.add_radiobutton(label="English", variable=lv, value="en", command=lambda: self.set_lang("en"))
        lg.add_radiobutton(label="العربية", variable=lv, value="ar", command=lambda: self.set_lang("ar"))
        m.add_cascade(label=tr("language"), menu=lg)
        m.add_command(label=tr("settings"), command=self.open_settings)
        m.add_separator()
        m.add_command(label=tr("hide"), command=self.hide)
        m.add_command(label=tr("quit"), command=self.quit)
        self._menu_refs = (m, sv, lv, stay_v, pv)
        m.tk_popup(e.x_root, e.y_root)

    def ask_youtube(self):
        q = simpledialog.askstring(APP, self.tr("yt_ask"), parent=self.root)
        if q and q.strip():
            self.play_youtube(q)

    def set_lang(self, lang):
        self.cfg["lang"] = lang
        self.save()
        self.say("أهلاً! أتكلم العربية الآن." if lang == "ar" else "Hi! I speak English now.")
        if self.chat:
            self.close_chat()
            self.open_chat()

    def custom_timer(self):
        n = simpledialog.askfloat(APP, self.tr("timer_ask"), parent=self.root, minvalue=0.05, maxvalue=24 * 60)
        if n:
            self.add_timer(n * 60)

    def ask_note(self):
        t = simpledialog.askstring(APP, self.tr("note_ask"), parent=self.root)
        if t:
            self.add_note(t)

    def hide(self):
        if self.hidden:
            return
        self.say(self.line("hidden"))
        self.sfx("pop")
        self.root.after(1600, self._do_hide)

    def _do_hide(self):
        self.hidden = True
        for w in (self.root, self.ball.win if self.ball else None, self.thread_win, self.chat):
            if w:
                w.withdraw()

    def toggle_hide(self):
        if not self.hidden:
            return self._do_hide()
        self.hidden = False
        for w in (self.root, self.ball.win if self.ball else None):
            if w:
                w.deiconify()
        self.say(self.line("back"))
        self.sfx("wake")

    def quit(self):
        self.save_chat()
        self.say(self.line("bye"))
        self.sfx("no")
        self.audio.stop()
        self.state, self.timer = "sad", 100
        self.save()
        self.root.after(1300, self.root.destroy)


class FxLayer:
    """A click-through, full-screen transparent overlay for desktop effects (footprints, cracks, confetti...)."""
    CONF = ("#E5484D", "#F5C542", "#3B82F6", "#16A34A", "#9333EA", ORANGE, "#EC4899", "#22D3EE")

    def __init__(self, pet):
        self.pet, self.items, self.beam, self.drawn, self.mon = pet, [], None, False, None
        w = self.win = tk.Toplevel(pet.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-transparentcolor", KEY)
        w.config(bg=KEY)
        self.c = tk.Canvas(w, bg=KEY, highlightthickness=0)
        self.c.pack(fill="both", expand=True)
        self.place()
        w.update_idletasks()
        try:   # click-through, no taskbar button, never takes focus
            hw = int(w.wm_frame(), 16)
            ex = user32.GetWindowLongW(hw, -20)
            user32.SetWindowLongW(hw, -20, ex | 0x20 | 0x80000 | 0x80 | 0x08000000)
        except Exception:
            pass

    def place(self):
        m = self.pet.mon
        if m != self.mon:
            self.mon = m
            L_, T_, R_, B_ = m
            self.win.geometry(f"{R_ - L_}x{B_ - T_ + int(90 * self.pet.k)}+{L_}+{T_}")

    def add(self, kind, x, y, life, **kw):
        it = {"k": kind, "x": float(x), "y": float(y), "t": 0.0, "life": life, **kw}
        self.items.append(it)
        return it

    def confetti(self, n):
        L_, T_, R_, B_ = self.pet.mon
        k = self.pet.k
        ps = [[random.uniform(L_, R_), T_ - random.uniform(0, 400) * k, random.uniform(-80, 80) * k,
               random.uniform(150, 420) * k, random.choice(self.CONF), random.uniform(0, 6.28)] for _ in range(n)]
        self.add("confetti", 0, 0, 6.5, ps=ps)

    def add_brick(self, it, i):
        P = it["P"]
        col, row = ((0, 0), (1, 0), (2, 0), (.5, 1), (1.5, 1), (1, 2))[min(i, 5)]
        bw, bh = 2.4 * P, 1.2 * P
        it["bricks"].append({"x": it["x"] - 1.5 * bw + col * bw, "y": it["y"] - (row + 1) * bh, "w": bw, "h": bh,
                             "t0": it["t"], "vx": 0.0, "vy": 0.0, "f": False})

    def step(self, dt):
        c = self.c
        if not self.items and not self.beam:
            if self.drawn:
                c.delete("all")
                self.drawn = False
            return
        self.place()
        c.delete("all")
        self.drawn = True
        ox, oy = self.mon[0], self.mon[1]
        keep = []
        for it in self.items:
            it["t"] += dt
            if it["t"] < it["life"]:
                keep.append(it)
                try:
                    getattr(self, "d_" + it["k"])(c, it, dt, ox, oy)
                except Exception:
                    pass
        self.items = keep
        if self.beam:
            k = self.pet.k
            for x1, y1, x2, y2 in self.beam:
                c.create_line(x1 - ox, y1 - oy, x2 - ox, y2 - oy, fill="#FF2D2D", width=max(3, 5 * k))
                c.create_line(x1 - ox, y1 - oy, x2 - ox, y2 - oy, fill="#FFD0D0", width=max(1, 1.6 * k))
            x2, y2 = self.beam[0][2] - ox, self.beam[0][3] - oy
            r = (8 + 3 * math.sin(time.perf_counter() * 40)) * k
            c.create_oval(x2 - r, y2 - r, x2 + r, y2 + r, fill="#FF6B6B", outline="")

    # --- drawers (all coordinates are screen coordinates, minus the overlay's origin)
    def d_foot(self, c, it, dt, ox, oy):
        s = it["P"] * .45 * min(1, (it["life"] - it["t"]) / 1.5)
        x, y = it["x"] - ox, it["y"] - oy
        c.create_oval(x - s, y - s * 1.1, x + s, y - s * .1, fill="#B5603E", outline="")

    def d_crack(self, c, it, dt, ox, oy):
        left = it["life"] - it["t"]
        if left < .6 and int(left * 12) % 2:
            return
        k = self.pet.k
        x, y = it["x"] - ox, it["y"] - oy
        for pts in it["lines"]:
            flat = [v for px, py in pts for v in (x + px, y + py)]
            c.create_line(*flat, fill="#1b1b1b", width=max(2, 3.4 * k))
            c.create_line(*flat, fill="#f4f4f4", width=max(1, 1.2 * k))
        c.create_oval(x - 5 * k, y - 5 * k, x + 5 * k, y + 5 * k, fill="#f4f4f4", outline="#1b1b1b")
        if it.get("tape"):
            for a in (.55, -.55):
                ca, sa = math.cos(a), math.sin(a)
                L2, W2 = 80 * k, 13 * k
                pts = [(-L2, -W2), (L2, -W2), (L2, W2), (-L2, W2)]
                c.create_polygon(*[v for px, py in pts for v in (x + px * ca - py * sa, y + px * sa + py * ca)],
                                 fill="#D6D3CE", outline="#9E9A94")

    def d_confetti(self, c, it, dt, ox, oy):
        k, t = self.pet.k, it["t"]
        B_ = self.mon[3]
        for p in it["ps"]:
            p[3] = min(p[3] + 300 * k * dt, 460 * k)
            p[0] += (p[2] + math.sin(t * 3 + p[5]) * 70 * k) * dt
            p[1] += p[3] * dt
            if p[1] > B_ + 40 * k:
                continue
            w = 7 * k * (abs(math.sin(t * 6 + p[5])) + .2)
            x, y = p[0] - ox, p[1] - oy
            c.create_rectangle(x - w / 2, y - 5 * k, x + w / 2, y + 5 * k, fill=p[4], outline="")

    def d_pow(self, c, it, dt, ox, oy):
        k, t = self.pet.k, it["t"]
        sc = min(1.25, t / .1) if t < .1 else 1.25 - min(.25, (t - .1) * 2)
        x, y = it["x"] - ox, it["y"] - oy
        R = 62 * k * sc
        pts = []
        for i in range(18):
            a = i / 18 * 2 * math.pi
            r = R if i % 2 == 0 else R * .58
            pts += [x + math.cos(a) * r, y + math.sin(a) * r]
        c.create_polygon(*pts, fill="#FFD43B", outline="#141414", width=max(2, 3 * k))
        c.create_text(x, y, text=it["text"], fill="#E5484D", font=("Impact", -int(26 * k * sc)))

    def d_puff(self, c, it, dt, ox, oy):
        k, f = self.pet.k, it["t"] / it["life"]
        x, y = it["x"] - ox, it["y"] - oy
        for i in range(9):
            a = i / 9 * 2 * math.pi
            d = (12 + 70 * f) * k
            r = 13 * k * (1 - f) + 2
            c.create_oval(x + math.cos(a) * d - r, y + math.sin(a) * d - r, x + math.cos(a) * d + r, y + math.sin(a) * d + r,
                          fill="#E8E4DE", outline="#BDB8B0")

    def d_scorch(self, c, it, dt, ox, oy):
        k, t = self.pet.k, it["t"]
        r = 7 * k * min(1, (it["life"] - t) / 1.5) + 1
        x, y = it["x"] - ox, it["y"] - oy
        c.create_oval(x - r, y - r, x + r, y + r, fill="#FF8A3D" if t < .25 else "#2A1A10", outline="")

    def d_doodle(self, c, it, dt, ox, oy):
        k, t = self.pet.k, it["t"]
        left = it["life"] - t
        if left < 1 and int(left * 10) % 2:
            return
        txt = it["text"][:int(t * 10) + 1]
        c.create_text(it["x"] - ox, it["y"] - oy, text=txt, fill=it["color"], font=("Segoe Print", -int(30 * k), "bold"))

    def d_build(self, c, it, dt, ox, oy):
        k, P = self.pet.k, it["P"]
        ground = it["y"] - oy
        falling = it["fall"] is not None and it["t"] > it["fall"]
        top = None
        for b in it["bricks"]:
            if falling:
                if not b["f"]:
                    b["f"], b["vx"], b["vy"] = True, random.uniform(-180, 180) * k, -random.uniform(60, 260) * k
                b["vy"] += 2200 * k * dt
                b["x"] += b["vx"] * dt
                b["y"] += b["vy"] * dt
                if b["y"] + b["h"] > it["y"]:
                    b["y"], b["vy"], b["vx"] = it["y"] - b["h"], -b["vy"] * .3, b["vx"] * .7
            drop = max(0.0, 1 - (it["t"] - b["t0"]) / .15) * 24 * k
            x, y = b["x"] - ox, b["y"] - oy - drop
            c.create_rectangle(x, y, x + b["w"], y + b["h"], fill="#C2452D", outline="#7A2A1A", width=max(1, k))
            c.create_line(x + b["w"] * .5, y, x + b["w"] * .5, y + b["h"] * .5, fill="#7A2A1A", width=max(1, k))
            top = (x + b["w"] / 2, y)
        if len(it["bricks"]) >= 6 and not falling and top:   # flag on top: shipped!
            x, y = top
            c.create_line(x, y, x, y - 3 * P, fill="#555555", width=max(2, 2 * k))
            c.create_polygon(x, y - 3 * P, x + 2 * P, y - 2.5 * P, x, y - 2 * P, fill=ORANGE, outline="")
        _ = ground

    def d_hole(self, c, it, dt, ox, oy):
        k = self.pet.k
        w = it["w"] * min(1, (it["life"] - it["t"]) / 1.5)
        if w < 2:
            return
        x, y = it["x"] - ox, it["y"] - oy
        c.create_oval(x - w / 2, y - w * .18, x + w / 2, y + w * .18, fill="#2A1A10", outline="#6B4A2A", width=max(2, 2 * k))

    def d_rock(self, c, it, dt, ox, oy):
        k = self.pet.k
        it["vy"] += 2200 * k * dt
        it["x"] += it["vx"] * dt
        it["y"] += it["vy"] * dt
        s = it["s"]
        x, y = it["x"] - ox, it["y"] - oy
        c.create_rectangle(x - s, y - s, x + s, y + s, fill="#8A8A8A", outline="#555555")

    def d_loot(self, c, it, dt, ox, oy):
        P, t = it["P"], it["t"]
        x = it["x"] - ox
        y = it["y"] - oy - min(1, t / .4) * 3 * P - math.sin(t * 4) * P * .2
        s = P * 1.2
        what = it["what"]
        if what == "gem":
            c.create_polygon(x, y - s, x + s * .8, y - s * .3, x, y + s, x - s * .8, y - s * .3, fill="#5EEAD4", outline="#0F766E", width=2)
            c.create_line(x - s * .8, y - s * .3, x + s * .8, y - s * .3, fill="#0F766E", width=2)
        elif what == "coin":
            c.create_oval(x - s, y - s, x + s, y + s, fill="#F5C542", outline="#B8860B", width=2)
            c.create_text(x, y, text="₿", fill="#8A6508", font=("Segoe UI", -int(s * 1.3), "bold"))
        elif what == "bug":
            for i in (-1, 0, 1):
                c.create_line(x - s * 1.1, y + i * s * .4, x + s * 1.1, y + i * s * .4, fill="#14532D", width=2)
            c.create_oval(x - s * .7, y - s * .9, x + s * .7, y + s * .9, fill="#16A34A", outline="#14532D", width=2)
        else:
            c.create_oval(x - s, y - s, x + s, y + s, fill="#C8873A", outline="#8A5A24", width=2)
            for dx, dy in ((-.4, -.3), (.35, -.1), (-.1, .4)):
                c.create_oval(x + dx * s - 2, y + dy * s - 2, x + dx * s + 3, y + dy * s + 3, fill="#5A3A1E", outline="")
        for i in range(4):   # sparkles
            a = t * 3 + i * 1.57
            sx, sy = x + math.cos(a) * s * 1.8, y + math.sin(a) * s * 1.8
            c.create_line(sx - 4, sy, sx + 4, sy, fill="#F5C542", width=2)
            c.create_line(sx, sy - 4, sx, sy + 4, fill="#F5C542", width=2)

    def d_glitch(self, c, it, dt, ox, oy):
        k = self.pet.k
        x, y = it["x"] - ox, it["y"] - oy
        for _ in range(11):
            w = random.uniform(60, 340) * k
            h = random.uniform(3, 18) * k
            gx, gy = x + random.uniform(-260, 260) * k, y + random.uniform(-170, 170) * k
            col = random.choice(("#FF004C", "#00E5FF", "#39FF14", "#FFFFFF", "#141414", "#FF00AA"))
            c.create_rectangle(gx - w / 2, gy, gx + w / 2, gy + h, fill=col, outline="")
        if random.random() < .5:
            gx, gy = x + random.uniform(-150, 150) * k, y + random.uniform(-100, 100) * k
            c.create_text(gx, gy, text=random.choice(("ERR0R", "0xDEAD", "NaN", "segfault", "undefined", "�")),
                          fill="#39FF14", font=("Consolas", -int(18 * k), "bold"))


class TicTacToe:
    """Tic-tac-toe against Clawd in a little window (minimax, with personality-based mistakes)."""
    WINS = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6))
    BG, CELL = "#1F1E1D", "#2B2A27"

    def __init__(self, pet):
        self.pet, self.score = pet, [0, 0]
        w = self.win = tk.Toplevel(pet.root)
        w.title(pet.tr("ttt_title"))
        w.attributes("-topmost", True)
        w.resizable(False, False)
        w.configure(bg=self.BG)
        try:
            w.iconbitmap(ICON)
        except Exception:
            pass
        self.msg = tk.Label(w, bg=self.BG, fg="#F5F4EF", font=("Segoe UI", 12, "bold"))
        self.msg.pack(pady=(12, 2), padx=14)
        self.sc = tk.Label(w, bg=self.BG, fg="#A8A29E", font=("Segoe UI", 9))
        self.sc.pack()
        grid = tk.Frame(w, bg="#3A3835")
        grid.pack(padx=16, pady=10)
        self.btn = []
        for i in range(9):
            b = tk.Label(grid, text=" ", width=3, font=("Segoe UI", 26, "bold"), bg=self.CELL, fg="#F5F4EF", cursor="hand2")
            b.grid(row=i // 3, column=i % 3, padx=2, pady=2, ipadx=6, ipady=2)
            b.bind("<Button-1>", lambda e, i=i: self.play(i))
            b.bind("<Enter>", lambda e, b=b, i=i: b.config(bg="#3D3B37") if not self.b[i] and not self.over else None)
            b.bind("<Leave>", lambda e, b=b, i=i: b.config(bg=self.CELL) if not self.over else None)
            self.btn.append(b)
        again = tk.Label(w, text=pet.tr("ttt_again"), bg=ORANGE, fg="white", font=("Segoe UI", 10, "bold"), padx=14, pady=5,
                         cursor="hand2")
        again.pack(pady=(0, 14))
        again.bind("<Button-1>", lambda e: self.reset())
        w.protocol("WM_DELETE_WINDOW", self.close)
        cx, cy = pet.pet_center()
        w.geometry(f"+{int(max(0, cx - 170 * pet.k))}+{int(max(0, cy - 420 * pet.k))}")
        self.reset()

    def reset(self):
        self.b, self.over, self.my_turn = [""] * 9, False, True
        for x in self.btn:
            x.config(text=" ", bg=self.CELL)
        self.msg.config(text=self.pet.tr("ttt_you"))
        self.sc.config(text=self.pet.tr("ttt_score", a=self.score[0], b=self.score[1]))

    def winner(self, b):
        for a, c, d in self.WINS:
            if b[a] and b[a] == b[c] == b[d]:
                return b[a], (a, c, d)
        return ("draw", ()) if all(b) else (None, ())

    def put(self, i, m):
        self.b[i] = m
        self.btn[i].config(text=m, fg=ORANGE if m == "X" else "#8AB4F8", bg=self.CELL)

    def play(self, i):
        if self.over or not self.my_turn or self.b[i]:
            return
        self.put(i, "X")
        self.pet.sfx("pop", .5)
        if not self.check():
            self.my_turn = False
            self.msg.config(text=self.pet.tr("ttt_thinking"))
            if self.pet.state in ("idle", "walk", "look", "think", "hang"):
                self.pet.set_state("think", 1)
            self.win.after(random.randint(450, 900), self.ai)

    def ai(self):
        if self.over or not self.win.winfo_exists():
            return
        empty = [i for i in range(9) if not self.b[i]]
        oops = {"sweet": .45, "lazy": .4, "balanced": .25, "hyper": .25, "naughty": .1}.get(self.pet.cfg.get("personality"), .25)
        j = random.choice(empty) if random.random() < oops else self.best()
        self.put(j, "O")
        self.pet.sfx("tok", .5)
        self.my_turn = True
        if not self.check():
            self.msg.config(text=self.pet.tr("ttt_you"))

    def best(self):
        def mm(b, me, depth):
            w, _ = self.winner(b)
            if w == "O":
                return 10 - depth
            if w == "X":
                return depth - 10
            if w == "draw":
                return 0
            sc = []
            for i in range(9):
                if not b[i]:
                    b[i] = "O" if me else "X"
                    sc.append(mm(b, not me, depth + 1))
                    b[i] = ""
            return max(sc) if me else min(sc)
        best, bs = None, -99.0
        for i in range(9):
            if not self.b[i]:
                self.b[i] = "O"
                v = mm(self.b, False, 1) + random.random() * .1
                self.b[i] = ""
                if v > bs:
                    best, bs = i, v
        return best

    def check(self):
        w, line = self.winner(self.b)
        if not w:
            return False
        self.over = True
        for i in line:
            self.btn[i].config(bg="#5A3A28")
        if w == "X":
            self.score[0] += 1
            self.msg.config(text=self.pet.tr("ttt_won"))
        elif w == "O":
            self.score[1] += 1
            self.msg.config(text=self.pet.tr("ttt_lost"))
        else:
            self.msg.config(text=self.pet.tr("ttt_drew"))
        self.sc.config(text=self.pet.tr("ttt_score", a=self.score[0], b=self.score[1]))
        self.pet.ttt_result(w)
        return True

    def close(self):
        if self.pet.game and self.pet.game.get("win") is self:
            self.pet.game = None
        self.win.destroy()


class Ball:
    """A throwable toy ball in its own little window: bounces on the floor and on windows, and on Clawd's head."""

    def __init__(self, pet):
        self.pet = pet
        k = pet.k
        self.ps = max(2, pet.P // 2)
        self.size = 8 * self.ps
        L_, T_, R_, B_ = pet.mon
        self.x, self.y = pet.fx + random.choice((-1, 1)) * 200 * k, T_ + 100 * k
        self.x = min(max(self.x, L_ + self.size), R_ - self.size)
        self.vx, self.vy = random.uniform(-300, 300) * k, 0.0
        self.drag = None
        self.plat, self.plat_rect, self.air = None, None, True
        w = self.win = tk.Toplevel(pet.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-transparentcolor", KEY)
        w.config(bg=KEY)
        c = self.c = tk.Canvas(w, width=self.size, height=self.size, bg=KEY, highlightthickness=0)
        c.pack()
        pal = {"Y": "#E8E337", "W": "#FFFFFF", "G": "#B9B42A"}
        for r, row in enumerate(BALL):
            for cc, ch in enumerate(row):
                if ch != ".":
                    c.create_rectangle(cc * self.ps, r * self.ps, (cc + 1) * self.ps, (r + 1) * self.ps, fill=pal[ch], outline="")
        c.bind("<ButtonPress-1>", self.press)
        c.bind("<B1-Motion>", self.motion)
        c.bind("<ButtonRelease-1>", self.release)

    def press(self, e):
        p = self.pet
        if self.air and p.time - p.last_kick_t < 3:   # caught his pass!
            p.fetch_n += 1
            p.last_kick_t = -9.0
            p.sfx("coin", .5)
            p.spawn("heart")
            if p.fetch_n >= 2:
                p.say(p.line("fetch_n", n=p.fetch_n))
        self.drag = [(time.perf_counter(), e.x_root, e.y_root)]
        self.plat = None

    def motion(self, e):
        if self.drag is not None:
            self.drag = (self.drag + [(time.perf_counter(), e.x_root, e.y_root)])[-6:]
            self.x, self.y = e.x_root, e.y_root + self.size / 2

    def release(self, e):
        if self.drag:
            t0, x0, y0 = self.drag[0]
            t1, x1, y1 = self.drag[-1]
            dt = max(t1 - t0, .016)
            self.vx, self.vy = (x1 - x0) / dt, (y1 - y0) / dt
        self.drag = None
        self.plat = None
        if self.pet.surf == "floor" and self.pet.state in ("idle", "walk", "think", "play", "look", "lounge") and not self.pet.stay:
            self.pet.set_state("play", 10)

    def step(self, dt):
        p, k = self.pet, self.pet.k
        L_, T_, R_, B_ = p.mon
        r = self.size / 2
        if self.drag is None:
            ground = B_
            if self.plat:   # resting on a window: ride along with it
                h = self.plat
                if not user32.IsWindow(h) or user32.IsIconic(h):
                    self.plat = None
                else:
                    nr = frame_rect(h)
                    self.x += nr[0] - self.plat_rect[0]
                    self.y += nr[1] - self.plat_rect[1]
                    self.plat_rect = nr
                    if nr[0] <= self.x <= nr[2] and nr[1] > T_ + 6:
                        ground = nr[1]
                    else:
                        self.plat = None
            ox, oy = self.x, self.y
            self.vy += 2600 * k * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            if p.cfg["windows"]:
                if self.vy > 0:   # land on window tops
                    for h, wr, _, _ in p.windows:
                        if h != self.plat and T_ + 6 < wr[1] < ground and oy - 1 <= wr[1] <= self.y and wr[0] <= self.x <= wr[2] \
                                and top_visible(h, self.x, wr[1]):
                            ground, self.plat, self.plat_rect = wr[1], h, wr
                if abs(self.vx) > 50 * k:   # bounce off window sides (a hard hit shoves the window!)
                    cy = self.y - r
                    for h, wr, _, _ in p.windows:
                        if not (wr[1] < cy < wr[3]) or user32.IsZoomed(h):
                            continue
                        edge = None
                        if self.vx > 0 and ox + r <= wr[0] < self.x + r:
                            edge, px = wr[0] - r, wr[0] + 3
                        elif self.vx < 0 and ox - r >= wr[2] > self.x - r:
                            edge, px = wr[2] + r, wr[2] - 3
                        if edge is not None and top_visible(h, px, cy - 4):
                            if abs(self.vx) > 1700 * k:
                                p.shove_window(h, self.vx * .3, 0, .12)
                            self.x, self.vx = edge, -self.vx * .55
                            p.sfx("kick", .3)
                            break
            if self.y >= ground:
                self.y = ground
                if ground >= B_:
                    self.plat = None
                if abs(self.vy) > 150 * k:
                    self.vy = -self.vy * .62
                    if abs(self.vy) > 400 * k:
                        p.sfx("kick", .35)
                else:
                    self.vy = 0
                self.vx *= .985 ** (dt * 60)
            self.air = self.y < ground - 2
            if self.x < L_ + r or self.x > R_ - r:
                self.x = min(max(self.x, L_ + r), R_ - r)
                self.vx = -self.vx * .7
            if self.y - self.size < T_:
                self.y, self.vy = T_ + self.size, abs(self.vy) * .5
            # hit Clawd?
            pb = getattr(p, "pbox", None)
            if pb and p.state != "drag" and not p.hidden and p.time - p.last_kick_t > .4:
                x1, y1, x2, y2 = p.wx + pb[0], p.wy + pb[1], p.wx + pb[2], p.wy + pb[3]
                cy = self.y - r
                if x1 - r < self.x < x2 + r and y1 - r < cy < y2 + r:
                    sp = math.hypot(self.vx, self.vy)
                    pcx = (x1 + x2) / 2
                    toward = (pcx - self.x) * self.vx > 0 or (self.vy > 0 and cy < y1 + (y2 - y1) * .5)
                    if sp > 900 * k and toward and p.cooldown("ballhit", .6):
                        p.ball_hit(self, sp)
        self.win.geometry(f"{self.size}x{self.size}+{int(self.x - r)}+{int(self.y - self.size)}")


if __name__ == "__main__":
    _mutex = kernel32.CreateMutexW(None, False, "ClawdDesktopPetMutex")
    if kernel32.GetLastError() == 183 and "--test" not in sys.argv:  # already running
        sys.exit(0)
    Clawd().root.mainloop()
