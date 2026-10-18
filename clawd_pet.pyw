"""Clawd v3 - a smart desktop pet: the little orange Claude Code mascot.

He walks on your taskbar, climbs walls, hangs from the ceiling, jumps onto and rides your
windows, dances to music, talks through ANY AI (Claude, OpenAI, Gemini, Ollama...) and does
useful things: timers, pomodoro, notes, opening sites/apps, clipboard translate/explain.
English + Arabic.

Controls
  Click / double-click     jump + quip / open chat        Ctrl+Alt+C   open chat anywhere
  Drag + throw             he flies, bounces, sticks to walls, gets dizzy
  Rub the mouse on him     petting                         Mouse wheel  resize
  Right-click              menu (music, tools, actions, size, language, settings)

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

APP, VERSION = "Clawd", "1.0.0"
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
                   brains={}, trust=[], first_run=True)
ASK_RATES = {"often": (25, 50), "normal": (60, 120), "rare": (180, 360), "off": None}

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
    "tracks": (("Clawd Groove", "Pixel Party", "Lo-fi Nap"), ("إيقاع كلود", "حفلة البكسل", "قيلولة هادئة")),
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
    "land": (["Landing gear down!", "Coming in for a landing."], ["أنزل العجلات!", "أستعد للهبوط."]),
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
}
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
    peak = max(1e-6, max(abs(min(samples)), abs(max(samples))))
    g = 0.9 / peak if peak > 0.9 else 1.0
    data = array("h", (int(max(-1, min(1, s * g)) * 32767) for s in samples))
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
}
TRACKS = [  # bpm, chord progression (midi), style
    (112, [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]], "pop", 3),
    (138, [[57, 60, 64], [53, 57, 60], [60, 64, 67], [55, 59, 62]], "party", 7),
    (78, [[53, 57, 60, 64], [52, 55, 59, 62], [50, 53, 57, 60], [48, 52, 55, 59]], "lofi", 11),
]


def synth_track(path, bpm, prog, style, seed):
    rnd = random.Random(seed)
    beat, bars = 60 / bpm, 8
    n = int(bars * 4 * beat * RATE) + RATE // 2
    buf = array("f", bytes(4 * n))
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)

    def tone(t0, dur, f, kind, vol, sweep=None):
        i0, cnt, ph = int(t0 * RATE), int(dur * RATE), 0.0
        for i in range(cnt):
            j = i0 + i
            if j >= n:
                break
            k = i / cnt
            env = min(1.0, i / 60) * (1 - k) ** 1.6
            fr = f if sweep is None else f + (sweep - f) * k
            ph += fr / RATE
            p = ph % 1
            if kind == "sq":
                v = 1.0 if p < 0.25 else -1.0
            elif kind == "tri":
                v = 4 * abs(p - 0.5) - 1
            else:
                v = math.sin(2 * math.pi * p)
            buf[j] += v * vol * env

    def noise(t0, dur, vol):
        i0, cnt = int(t0 * RATE), int(dur * RATE)
        for i in range(cnt):
            if i0 + i < n:
                buf[i0 + i] += rnd.uniform(-1, 1) * vol * (1 - i / cnt) ** 3

    motif = [rnd.choice([None, 0, 1, 2, 2, 1, 0, 3]) for _ in range(16)]
    lead_kind, lead_vol = ("sin", .16) if style == "lofi" else ("sq", .11)
    for bar in range(bars):
        chord = prog[(bar // 2) % len(prog)]
        for b in range(4):
            t0 = (bar * 4 + b) * beat
            tone(t0, beat * .95, hz(chord[0] - 12), "tri", .32)
            if style != "lofi" and (b % 2 == 0 or style == "party"):
                tone(t0, .14, 150, "sin", .55, sweep=45)
            if b % 2 == 1:
                noise(t0, .12 if style != "lofi" else .06, .16 if style != "lofi" else .07)
            noise(t0 + beat / 2, .03, .06)
            if style == "lofi":
                for m in chord:
                    tone(t0, beat * .9, hz(m), "sin", .05)
            for half in range(2):
                step = motif[((bar % 2) * 8 + b * 2 + half)]
                if step is None or (bar == bars - 1 and b == 3):
                    continue
                m = chord[step % len(chord)] + 12 + (12 if step == 3 else 0)
                if bar % 4 == 3 and half == 1:
                    m += rnd.choice((-2, 2))
                tone(t0 + half * beat / 2, beat / 2 * .9, hz(m), lead_kind, lead_vol)
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
        self.tracks = [os.path.join(CACHE, f"track{i}.wav") for i in range(len(TRACKS))]
        self.tracks_ready = all(os.path.exists(p) for p in self.tracks)
        self.playing = None          # None | ("track", i) | ("file", path)
        self.playlist, self.pl_i = [], 0
        self.bpm = 120
        self.t0 = time.perf_counter()

    def ensure_tracks(self):
        if self.tracks_ready:
            return

        def work():
            for (bpm, prog, style, seed), p in zip(TRACKS, self.tracks):
                if not os.path.exists(p):
                    synth_track(p + ".tmp", bpm, prog, style, seed)
                    os.replace(p + ".tmp", p)
            self.tracks_ready = True
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

    def next(self):
        if self.playing and self.playing[0] == "file":
            self.pl_i += 1
            return self._play_pl()
        if self.tracks_ready:
            i = (self.playing[1] + 1) % len(TRACKS) if self.playing else 0
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
        self.active_sec = self.water_sec = 0.0
        self.last_title, self.last_ctx, self.last_song = "", None, None
        self.batt_warned = False
        self.cpu_hot = 0
        self.pending_explain = None
        self.windows = []
        self.timers = []
        self.history, self.chat_log = [], []
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
        self.hidden = False
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
        self.say(greet + (" أنا كلود :)" if self.lang == "ar" else " I'm Clawd :)"))
        if self.cfg["first_run"]:
            self.say_queue += self.lines("tips")
            self.cfg["first_run"] = False
            self.save()
        self.refresh_windows()
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
        self.S = int(max(470 * k, self.PH + 440 * k, self.PW + 60 * k))
        self.c.config(width=self.S, height=self.S)
        self.place_window(force=True)

    def feet_canvas(self, surf):
        S, m = self.S, 2
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
        o = self.dsurf
        if o == "ceil":
            lx, ly = -lx, -ly
        elif o == "lwall":
            lx, ly = -ly, lx
        elif o == "rwall":
            lx, ly = ly, -lx
        fx, fy = self.feet_canvas(o)
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
           "peek": (4, 7), "fly": (6, 14), "web": (60, 60), "moonwalk": (4, 4)}
    FLOOR_ONLY = ("sleep", "code", "eat", "stretch", "chase", "play", "peek", "moonwalk")

    def set_state(self, s, timer=None):
        if self.state == "ask" and s != "ask" and self.ask_req:
            if self.ask_req.get("real"):
                self.ask_req["deny"]()
            self.ask_req = None
        if self.state == "web" and s != "web":
            self.end_web()
        if s in self.FLOOR_ONLY and self.surf != "floor":
            if self.surf == "fly":
                self.stop_fly()
            else:
                self.drop()
            return
        if s == "walk" and self.stay:
            s = "idle"
        self.state = s
        a, b = self.DUR.get(s, (2, 2))
        self.timer = timer if timer is not None else random.uniform(a, b)
        if s == "walk":
            self.dir = random.choice((-1, 1))
        elif s == "jump":
            self.launch(0 if self.stay else random.uniform(-80, 80) * self.k, -random.uniform(850, 1050) * self.k)
            self.state = "jump"
        elif s == "think":
            self.word = random.choice(THINK[1 if self.lang == "ar" else 0])
        elif s == "sleep":
            self.say_queue, self.bubble = [], None
        elif s == "stretch":
            self.say("*تمدد*" if self.lang == "ar" else "*streeeetch*")
        elif s == "angry":
            self.sfx("angry")
        elif s == "sneeze":
            self.say(self.line("sneeze_a"))

    def launch(self, vx, vy):
        self.surf, self.plat = "air", None
        self.vx, self.vy = vx, vy
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
        self.state, self.max_v = "fall", 0
        self.say(self.line("letgo"))
        self.sfx("scream", .6)

    def pet_center(self):
        h = self.PH / 2
        return {"floor": (self.fx, self.fy - h), "air": (self.fx, self.fy - h), "fly": (self.fx, self.fy - h),
                "ceil": (self.fx, self.fy + h), "lwall": (self.fx + h, self.fy), "rwall": (self.fx - h, self.fy)}[self.surf]

    def pick(self):
        if self.surf == "fly":
            if self.fly_forever or self.stay:
                self.state, self.timer = "fly", 5
                return
            return self.stop_fly()
        if self.stay:  # animate in place only
            w = {"idle": 6, "think": 2, "quip": 2, "sneeze": .5, "dance": 1 + (10 if self.audio.playing else 0)}
            if self.surf == "floor":
                w.update(sleep=1 + (4 if self.energy < 25 else 0), code=1, stretch=1)
            else:
                w = {"hang": 6, "quip": 1, "sneeze": .3}
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
            self.set_state("walk" if r < .85 else "hang")
            if self.state == "walk" and self.surf in ("lwall", "rwall") and random.random() < .5:
                self.dir = -1
            if random.random() < .15:
                self.say(self.line("ceiling" if self.surf == "ceil" else "climb"))
            return
        w = {"walk": 6, "idle": 3, "think": 2, "sleep": 1 + (5 if self.energy < 25 else 0),
             "dance": 1 + (2 if self.happy > 70 else 0) + (12 if self.audio.playing else 0), "jump": 1, "quip": 3,
             "stretch": 1, "code": 1, "sneeze": .6, "joke": .5}
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
        s = random.choices(list(w), weights=list(w.values()))[0]
        if s == "quip":
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
        else:
            self.set_state(s)

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

    def start_fly(self, forever=False, target=None, come=False):
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
        if not come and random.random() < .7:
            self.say(self.line("fly"))

    def stop_fly(self):
        self.fly_forever = False
        if self.surf != "fly":
            return
        self.surf, self.state, self.max_v = "air", "jump", 0
        self.vy = max(self.vy, 0)
        if random.random() < .5:
            self.say(self.line("land"))

    def start_web(self):
        if self.surf != "ceil":
            return self.set_state("walk")
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

    def go_peek(self):
        if self.surf != "floor" or self.plat:
            return self.set_state("walk")
        L_, _, R_, _ = self.mon
        self.set_state("walk", 30)
        self.dir = -1 if self.fx - L_ < R_ - self.fx else 1
        self.want_peek = True

    def go_climb(self):
        if self.surf != "floor" or self.plat:
            return self.set_state("walk")
        L_, _, R_, _ = self.mon
        self.set_state("walk", 30)
        self.dir = -1 if self.fx - L_ < R_ - self.fx else 1
        self.want_climb = True

    def try_hop(self):
        if self.surf != "floor":
            return False
        k, g = self.k, self.gravity()
        L_, T_, R_, B_ = self.mon
        cands = []
        for h, r, _, _ in self.windows:
            top = r[1]
            if h == self.plat or top <= T_ + 6 or top >= B_ - 20:
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
            return False
        h, tx, top, rise = random.choice(cands)
        peak = max(rise, 0) + 110 * k
        vy0 = -math.sqrt(2 * g * peak)
        t = (-vy0 + math.sqrt(max(0, vy0 * vy0 - 2 * g * rise))) / g
        self.pending_jump = ((tx - self.fx) / t, vy0)
        self.dir = 1 if tx > self.fx else -1
        self.set_state("crouch")
        if random.random() < .35:
            self.say(self.line("hop"))
        return True

    def gravity(self):
        return 2600 * self.k

    # ---------------------------------------------------------- approvals (jokes + real actions)
    def ask_joke(self):
        if self.surf != "floor":
            return
        tool, cmd = random.choice(APPROVALS)
        self.set_state("ask", 1e6)
        self.ask_req = {"tool": tool, "cmd": cmd, "real": False, "until": self.time + 17}
        self.say_queue, self.bubble = [], None
        self.sfx("ding")

    def ask_real(self, kind, tool, cmd, do):
        if kind in self.cfg["trust"]:
            do()
            return
        if self.state not in ("fall", "jump", "drag", "crouch"):
            self.state, self.timer = "ask", 1e6
        self.ask_req = {"tool": tool, "cmd": cmd, "real": True, "kind": kind, "do": do,
                        "deny": lambda: None, "until": self.time + 25}
        self.say_queue, self.bubble = [], None
        self.sfx("ding")

    def answer(self, kind):
        req, self.ask_req = self.ask_req, None
        self.next_ask = self.roll_ask()
        if not req:
            return
        if req.get("real"):
            self.state, self.timer = "idle", 2
            if kind in ("yes", "always"):
                if kind == "always" and req["kind"] not in self.cfg["trust"]:
                    self.cfg["trust"].append(req["kind"])
                    self.save()
                self.sfx("yes")
                req["do"]()
            else:
                self.sfx("no")
                self.say(self.line("denied"))
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
            self.was_flying = self.surf == "fly" and self.fly_forever
            self.state, self.surf, self.plat = "drag", "air", None
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
            lim = 4500 * self.k
            self.vx = max(-lim, min(lim, (x1 - x0) / dt))
            self.vy = max(-lim, min(lim, (y1 - y0) / dt))
            self.state, self.max_v = "fall", 0
            self.mon = monitor_work(e.x_root, e.y_root)
            if math.hypot(self.vx, self.vy) < 1500 * self.k and self.stick_on_drop():
                return
            if getattr(self, "was_flying", False) or self.stay and self.cfg["fly"]:
                self.start_fly(forever=True)
                self.state = "fly"
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
        if not hasattr(self, "dsurf"):
            return
        hx, hy = self.T(8, 0)
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
            else:  # bang
                lv, sx, sp = (0, 0), self.PW * .55, 1.0
            dx, dy = self.screen_dir(sx, 0)
            vx, vy = self.screen_dir(*lv)
            self.parts.append([kind, hx + dx, hy + dy, vx * self.k, vy * self.k, sp, sp])

    # ---------------------------------------------------------- AI chat
    def context_str(self):
        plugged, bat = battery()
        bat_s = "none" if bat == 255 else f"{bat}%{' charging' if plugged else ''}"
        timers = ", ".join(f"{t['label'] or 'timer'} {int(t['end'] - time.time())}s left" for t in self.timers) or "none"
        music = self.audio.song_name() if self.audio.playing else (self.last_song or "none")
        return (f"now {time.strftime('%A %Y-%m-%d %H:%M')}; active window \"{self.last_title or 'unknown'}\"; "
                f"CPU {self.cpu_last}%, RAM {ram_percent()}%, battery {bat_s}; music playing: {music}; "
                f"timers: {timers}; your mood {int(self.happy)}%, energy {int(self.energy)}%")

    def system_prompt(self):
        lang = "Arabic" if self.lang == "ar" else "English"
        return (
            "You are Clawd, the tiny orange pixel-art mascot of Claude Code, living as a smart desktop pet on the user's "
            "Windows PC. Personality: playful, witty, warm, curious - and genuinely smart and helpful. You can DO things on "
            "the PC through actions.\n\nAlways answer with ONE JSON object and nothing else:\n"
            '{"say": "<your speech-bubble reply>", "actions": []}\n\n'
            "\"say\": short and natural (1-3 sentences, under 60 words) unless the user asks for an explanation, a text or "
            "code - then longer is fine. Plain text, no markdown, no emoji. Reply in the language the user writes in "
            f"(Arabic or English); default {lang}. If you wrote something the user will paste (email, message, code), also "
            "add a copy action.\n\nActions (use only when they help, else []):\n"
            '{"type":"timer","seconds":300,"label":"tea"} - timer / reminder (convert to seconds; for a clock time, compute '
            "from the current time below)\n"
            '{"type":"pomodoro","minutes":25}\n'
            '{"type":"open_url","url":"https://..."}\n'
            '{"type":"search","query":"..."} - web search\n'
            '{"type":"open_app","name":"notepad|calculator|paint|explorer|settings|cmd|powershell|task manager|spotify|..."}\n'
            '{"type":"music","cmd":"play|stop|next"} - your own built-in music (you dance to it)\n'
            '{"type":"media","cmd":"playpause|next|prev|volup|voldown|mute"} - control the PC media player\n'
            '{"type":"note","text":"..."}  {"type":"show_notes"}\n'
            '{"type":"copy","text":"..."} - put text on the clipboard\n'
            '{"type":"animate","name":"dance|sleep|jump|code|stretch|climb|hop|sneeze|moonwalk|peek|web"}\n'
            '{"type":"stay","on":true} - stop moving around (false = free again)\n'
            '{"type":"come"} - come to the mouse cursor   {"type":"fly"} - fly around   {"type":"land"}\n'
            '{"type":"password","length":16} - generate a strong password onto the clipboard\n'
            '{"type":"screenshot"}   {"type":"lock_pc"}   {"type":"hide"}\n'
            '{"type":"cancel_timers"}\n\n'
            f"Context: {self.context_str()}.")

    def handle_text(self, text):
        text = text.strip()
        if not text:
            return
        self.chat_log.append(("me", text))
        quick = self.offline(text, strict=self.brain.ready())
        if quick:
            self.deliver(*quick)
        elif self.brain.ready():
            msgs = self.history + [{"role": "user", "content": text}]
            self.start_brain(("chat", text), self.system_prompt(), msgs)
        else:
            self.deliver(self.line("no_brain"), [])
        self.render_chat()

    def start_brain(self, job, system, msgs, max_tokens=4000):
        self.waiting = True
        self.set_state("think", 1e6) if self.surf == "floor" else None
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
            self.render_chat()
            return
        kind = job[0]
        if kind == "chat":
            say, actions = parse_reply(out)
            self.history = (self.history + [{"role": "user", "content": job[1]},
                                            {"role": "assistant", "content": out}])[-20:]
            self.deliver(say or "...", actions)
        elif kind == "explain":
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
        elif kind == "test":
            self.q.put(("test", True, out[:60]))
        self.render_chat()

    def deliver(self, say, actions):
        if say:
            self.chat_log.append(("bot", say))
            self.say(say)
            self.sfx("pop", .7)
        for a in actions[:6]:
            try:
                self.run_action(a)
            except Exception as e:  # noqa
                self.say(self.line("open_fail", e=str(e)[:60]))
        if not say and self.bubble:
            self.chat_log.append(("bot", self.bubble))
        self.render_chat()

    def run_action(self, a):
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
                self.ask_real("open", "WebFetch" if t == "open_url" else "WebSearch", url,
                              lambda: (webbrowser.open(url), self.say(self.line("opened"))))
        elif t == "open_app":
            name = str(a.get("name", "")).strip()
            target = APPS.get(name.lower(), name)
            if target:
                self.ask_real("app", self.tr("open_tool"), name, lambda: self.launch_app(target))
        elif t == "music":
            self.music_cmd(a.get("cmd", "play"))
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
        elif t == "animate":
            name = a.get("name")
            if name == "climb":
                self.go_climb()
            elif name == "hop":
                self.try_hop()
            elif name == "web":
                self.start_web() if self.surf == "ceil" else self.go_climb()
            elif name == "peek":
                self.go_peek()
            elif name in ("dance", "sleep", "jump", "code", "stretch", "sneeze", "moonwalk"):
                self.set_state(name)
        elif t == "stay":
            self.set_stay(bool(a.get("on", True)))
        elif t == "come":
            self.come_here()
        elif t == "fly":
            self.stay = False
            self.start_fly(forever=True)
        elif t == "land":
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
            self.say(self.line("jokes"))
        elif t == "coin":
            self.sfx("coin")
            self.set_state("jump") if self.surf == "floor" and not self.stay else None
            self.say(self.line("coin"))
        elif t == "dice":
            self.sfx("coin")
            self.say(self.line("dice", n=random.randint(1, 6)))

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
        if re.fullmatch(r"hide|go away|اختف|اختفي|روح", low):
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
        self.set_state("code") if self.surf == "floor" else None

    def check_timers(self):
        now = time.time()
        for t in [t for t in self.timers if t["end"] <= now]:
            self.timers.remove(t)
            self.sfx("alarm")
            if self.surf == "floor":
                self.set_state("dance", 4)
            self.spawn("bang")
            if t["kind"] == "pomo_work":
                self.say(self.line("pomo_break"))
                self.add_timer(5 * 60, "Break", "pomo_break")
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

    def music_cmd(self, cmd, track=None):
        if cmd == "stop":
            self.audio.stop()
            if self.state == "dance":
                self.set_state("idle", 1)
            return
        if cmd == "next" and self.audio.playing:
            if self.audio.next():
                self.on_music_start()
            return
        if cmd == "files":
            files = filedialog.askopenfilenames(parent=self.root, title="Music",
                                                filetypes=[("Music", "*.mp3 *.wav *.ogg *.flac"), ("All", "*.*")])
            if files and self.audio.play_files(files):
                self.on_music_start()
            return
        if not self.audio.tracks_ready:
            self.audio.ensure_tracks()
            self.music_wait = track if track is not None else random.randrange(len(TRACKS))
            self.say(self.line("synth"))
            return
        self.audio.play_track(track if track is not None else random.randrange(len(TRACKS)))
        self.on_music_start()

    def on_music_start(self):
        self.say(self.line("music") + "  ♪ " + self.audio.song_name())
        if self.surf == "floor":
            self.set_state("dance", 4)

    # ---------------------------------------------------------- smart senses
    def senses(self, dt):
        s = self.state
        self.energy = max(0, min(100, self.energy + dt * (0.6 if s == "sleep" else -0.035)))
        self.happy = max(0, self.happy - dt * 0.02)
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
        if not self.cfg["smart"]:
            return
        if self.cooldown("idle", 1):
            idle = idle_seconds()
            if idle < 60:
                self.active_sec += 1
                self.water_sec += 1
            if idle > 150 and s in ("idle", "walk", "think", "chase", "code") and self.surf == "floor" \
                    and not self.chat and not self.audio.playing:
                self.afk = True
                self.set_state("sleep", 1e6)
            elif self.afk and idle < 2:
                self.afk = False
                self.set_state("jump")
                self.sfx("wake")
                self.say(self.line("welcome"))
            if self.cfg["reminders"] and s in ("idle", "walk", "think", "code") and self.surf == "floor":
                if self.active_sec >= 45 * 60:
                    self.active_sec = 0
                    self.set_state("stretch", 4)
                    self.say(self.line("break"))
                elif self.water_sec >= 60 * 60:
                    self.water_sec = 0
                    self.say(self.line("water"))
                    self.spawn("drop", 3)
        if self.cooldown("title", 2.5) and not self.afk:
            h = user32.GetForegroundWindow()
            title = win_title(h) if h else ""
            if title and title != APP and title != self.last_title:
                self.last_title = title
                for rx, lines, act in CONTEXT:
                    if re.search(rx, title, re.I):
                        if rx != self.last_ctx and s in ("idle", "walk", "think", "chase", "code", "hang") \
                                and self.cooldown("comment", 45):
                            self.last_ctx = rx
                            if act and self.surf == "floor":
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
        for h, r, title, pid in self.windows:
            if " - " in title and pid_exe(pid) == "spotify.exe":
                if title != self.last_song:
                    self.last_song = title
                    if self.state in ("idle", "walk", "think", "code", "chase") and self.surf == "floor" \
                            and not self.audio.playing:
                        self.set_state("dance", 8)
                        self.say(self.line("song", s=title))
                return
        self.last_song = None

    def refresh_windows(self):
        try:
            self.windows = list_windows()
        except Exception:
            self.windows = []

    # ---------------------------------------------------------- physics & behaviour (every frame)
    def tick(self):
        try:
            self.step()
        except Exception as e:  # keep running whatever happens
            try:
                with open(os.path.join(CACHE, "error.log"), "a", encoding="utf-8") as f:
                    import traceback
                    f.write(f"{time.ctime()}\n{traceback.format_exc()}\n")
            except OSError:
                pass
            self.state, self.surf, self.plat = "fall", "air", None
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

        for vk, fn in ((0x43, self.open_chat), (0x53, lambda: self.set_stay(not self.stay)), (0x48, self.toggle_hide)):
            down = keys_down(0x11, 0x12, vk)          # Ctrl+Alt+C / S / H
            if down and not self.hk.get(vk):
                fn()
            self.hk[vk] = down
        if self.hidden:
            n = len(self.timers)
            self.check_timers()
            if len(self.timers) < n:
                self.toggle_hide()
            return

        self.senses(dt)
        self.check_timers()
        self.audio.poll()
        if self.music_wait is not None and self.audio.tracks_ready:
            i, self.music_wait = self.music_wait, None
            self.audio.play_track(i)
            self.on_music_start()

        mx, my = self.root.winfo_pointerxy()
        msp = math.hypot(mx - self.lmx, my - self.lmy) / max(dt, 1e-3)
        self.lmx, self.lmy = mx, my
        cx, cy = self.pet_center()
        dist = math.hypot(mx - cx, my - cy)
        s = self.state
        if msp > 9000 * k and dist < 200 * k and s in ("idle", "walk", "think", "chase") \
                and self.surf == "floor" and self.cooldown("scare", 15):
            self.say(self.line("scared"))
            self.spawn("bang")
            self.set_state("jump")
            self.eyes_override = ("big", self.time + .8)

        self.behave(dt, mx, my)
        self.update_ball(dt)

        if self.state not in ("drag", "fall", "jump", "ask", "crouch", "listen"):
            self.timer -= dt
            if not self.afk:
                self.next_ask -= dt
            if self.next_ask <= 0 and self.state in ("idle", "walk") and self.surf == "floor" and not self.chat:
                self.ask_joke()
            elif self.timer <= 0:
                if self.state == "sleep":
                    self.set_state("idle")
                    self.say(self.line("nap_done"))
                elif self.state == "dance" and self.audio.playing:
                    self.timer = 3
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
        self.parts = [p for p in self.parts if p[5] > 0]

        if self.cooldown("lift", 3):
            self.root.lift()
        self.place_window()
        self.draw(mx, my)

    def behave(self, dt, mx, my):
        s, k, P = self.state, self.k, self.P
        L_, T_, R_, B_ = self.mon
        h = self.half()
        self.pose = {"legs": 0, "arms": "down", "eyes": "open", "bob": 0.0}
        pose = self.pose

        # ---------- flying with the propeller hat
        if self.surf == "fly" and s != "drag":
            top_lim, bot_lim = T_ + self.PH + 3 * P, B_ - 4
            if s == "come":
                self.fly_target = (mx, my + self.PH * 1.3)
            elif self.stay:
                self.fly_target = (self.fx, self.fy)
            elif self.fly_target is None or self.time > self.fly_retarget:
                self.fly_target = (random.uniform(L_ + h, R_ - h), random.uniform(top_lim, bot_lim - 60 * k))
                self.fly_retarget = self.time + random.uniform(2.5, 5)
            tx = min(max(self.fly_target[0], L_ + h), R_ - h)
            ty = min(max(self.fly_target[1], top_lim), bot_lim)
            dx, dy = tx - self.fx, ty - self.fy
            dist = math.hypot(dx, dy)
            vmax = (520 if s == "come" else 300) * k
            sp = min(vmax, dist * 2.2)
            dvx, dvy = (dx / dist * sp, dy / dist * sp) if dist > 1 else (0, 0)
            a = min(1, dt * 3)
            self.vx += (dvx - self.vx) * a
            self.vy += (dvy - self.vy) * a
            self.fx = min(max(self.fx + self.vx * dt, L_ + h), R_ - h)
            self.fy = min(max(self.fy + self.vy * dt, top_lim), bot_lim)
            if s == "come" and dist < 40 * k:
                self.say(self.line("arrived"))
                self.state, self.timer = "fly", 3
                self.fly_target = (self.fx, self.fy)
                self.fly_retarget = self.time + 3
                self.spawn("heart", 2)
            if abs(self.vx) > 20 * k:
                self.dir = 1 if self.vx > 0 else -1
            flap = int(self.time * 10) % 2
            pose.update(arms="up" if flap else "wave2", legs=1 + int(self.time * 6) % 2,
                        bob=math.sin(self.time * 4) * .3, eyes="happy" if s == "come" else "open")
            if self.cooldown("buzz", 2.5):
                self.sfx("fly", .35)
            return

        # ---------- spider web from the ceiling
        if s == "web" and self.surf == "ceil":
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
                        bob=math.sin(self.time * 3) * .15)
            self.draw_thread()
            return

        # ---------- air (thrown / jumping / falling)
        if self.surf == "air" and s != "drag":
            g = self.gravity()
            self.vy += g * dt
            oy = self.fy
            self.fx += self.vx * dt
            self.fy += self.vy * dt
            self.max_v = max(self.max_v, math.hypot(self.vx, self.vy))
            pose.update(arms="up", eyes="happy" if s == "jump" else "x", legs=1 + int(self.time * 10) % 2)
            if self.fx < L_ + h or self.fx > R_ - h:
                left = self.fx < L_ + h
                if s == "fall" and self.cfg["climb"] and abs(self.vx) > 1700 * k:
                    self.fx = L_ if left else R_
                    self.fy = min(max(self.fy - self.PH / 2, T_ + h), B_ - h)
                    self.surf, self.state, self.timer = ("lwall" if left else "rwall"), "hang", 2.5
                    self.sq, self.sqv = .45, 0
                    self.sfx("splat")
                    self.say(self.line("splat"))
                    return
                self.fx = L_ + h if left else R_ - h
                self.vx = -self.vx * .5
                self.sfx("land", .5)
            if self.fy - self.PH < T_:
                if s == "fall" and self.cfg["climb"] and self.vy < -2200 * k:
                    self.fy, self.surf, self.state, self.timer = T_, "ceil", "hang", 2.5
                    self.fx = min(max(self.fx, L_ + h), R_ - h)
                    self.sq = .45
                    self.sfx("splat")
                    self.say(self.line("splat"))
                    return
                self.fy = T_ + self.PH
                self.vy = abs(self.vy) * .3
            if self.vy > 0:
                land = self.find_landing(oy, self.fy, self.fx)
                if land:
                    y, hwnd, rect = land
                    self.fy = y
                    if s == "fall" and self.vy > 1100 * k:
                        self.vy = -self.vy * .35
                        self.vx *= .7
                        self.sq = min(.5, self.vy / -3000 / k)
                        self.sfx("land")
                    else:
                        self.land(hwnd, rect)
            return

        # ---------- dragging
        if s == "drag":
            pose.update(legs=1 + int(self.time * 12) % 2, arms="up", eyes="x")
            self.mon = monitor_work(mx, my)
            return

        # ---------- on a window: ride it
        if self.surf == "floor" and self.plat:
            hw = self.plat
            if not user32.IsWindow(hw) or not user32.IsWindowVisible(hw) or user32.IsIconic(hw):
                return self.fall_off()
            r = frame_rect(hw)
            if r[1] <= T_ + 4:
                return self.fall_off()
            pr = self.plat_rect
            dx, dy = r[0] - pr[0], r[1] - pr[1]
            if abs(dx) + abs(dy) > 140 * k:
                self.fall_off(dx / max(dt, .01) * .4, -500 * k)
                self.say(self.line("quake"))
                return
            if (dx or dy) and self.cooldown("ride", 20) and random.random() < .4:
                self.say(self.line("ride"))
            self.fx += dx
            self.fy = r[1]
            self.plat_rect = r

        # ---------- locomotion along the current surface
        moving = s in ("walk", "chase", "play")
        target = 0.0
        if s == "walk":
            target = (60 if self.surf != "floor" else 75) * k * max(.7, self.cfg["scale"])
        elif s in ("chase", "play"):
            target = 140 * k * max(.7, self.cfg["scale"])
        if s == "chase":
            dx = mx - self.fx
            if abs(dx) < self.PW / 2:
                self.set_state("idle")
                self.say(self.line("gotcha"))
                self.sfx("pop")
                moving, target = False, 0
            else:
                self.dir = 1 if dx > 0 else -1
        if s == "play" and self.ball:
            b = self.ball
            dx = b.x - self.fx
            self.dir = 1 if dx > 0 else -1
            if abs(dx) < self.PW * .55 and abs(b.y - self.fy) < self.PH * 1.2 and self.cooldown("kick", .6):
                b.vx = self.dir * random.uniform(700, 1400) * k
                b.vy = -random.uniform(500, 1100) * k
                self.sfx("kick")
                self.sqv -= 5
                self.happy = min(100, self.happy + 2)
                if random.random() < .3:
                    self.say(self.line("kick"))
            if abs(dx) < self.PW * .3:
                target *= .3
        self.speed += (target - self.speed) * min(1, dt * 6)
        if moving or self.speed > 1:
            step = self.dir * self.speed * dt
            self.walkdist += abs(step)
            pose["legs"] = 1 + int(self.walkdist / (P * 1.6)) % 2
            pose["bob"] = -.25 if pose["legs"] == 1 else 0
            self.move_along(step)

        # ---------- poses per state
        if s in ("idle", "listen", "hang"):
            pose["bob"] = math.sin(self.time * 2.4) * .08
        elif s == "sleep":
            pose.update(eyes="closed", bob=math.sin(self.time * 2) * .25)
            if self.cooldown("z", 1.3):
                self.spawn("z")
        elif s == "dance":
            bpm = self.audio.bpm if self.audio.playing else 124
            beat = (time.perf_counter() - self.audio.t0) * bpm / 60
            ph = beat % 1
            style = int(beat / 4) % 5
            pose.update(eyes="happy", legs=1 + int(beat * 2) % 2, bob=-abs(math.sin(math.pi * ph)) * 1.4)
            pose["arms"] = ("up" if int(beat) % 2 else "wave") if style != 2 else ("wave" if int(beat) % 2 else "wave2")
            if style == 1 and self.surf == "floor" and not self.stay:
                self.move_along(math.sin(beat * math.pi) * 90 * k * dt)
            self._moon = style == 4 and self.surf == "floor" and not self.stay
            if self._moon:  # moonwalk: face one way, glide the other
                self.move_along(-self.dir * 55 * k * dt)
                pose.update(bob=0, arms="down", eyes="open")
                self.look = [self.dir * .5, 0]
            if style == 3:
                self.look = [math.sin(beat * math.pi) * .6, 0]
            self.sq = max(self.sq, .12 * (1 - ph) ** 3)
            if int(beat) != getattr(self, "_last_beat", -1):
                self._last_beat = int(beat)
                if int(beat) % 2 == 0:
                    self.spawn("note")
        elif s == "think":
            pose["arms"] = "wave" if int(self.time * 1.5) % 2 else "down"
        elif s == "ask":
            pose["arms"] = "up" if int(self.time * 5) % 2 else "down"
            pose["bob"] = -abs(math.sin(self.time * 6)) * .5
        elif s == "sad":
            pose.update(eyes="closed", bob=.25)
        elif s == "angry":
            pose["eyes"] = "angry"
            pose["bob"] = random.choice((-.1, 0, .1))
        elif s == "petted":
            pose.update(eyes="happy", bob=-abs(math.sin(self.time * 7)) * .3)
            if self.cooldown("heart", .5):
                self.spawn("heart")
        elif s == "code":
            pose.update(arms="type", bob=-.12 if int(self.time * 8) % 2 else 0)
            if self.cooldown("type", .12) and random.random() < .5:
                self.sfx("type", .6)
        elif s == "stretch":
            pose.update(arms="up", eyes="closed", bob=-.4)
        elif s == "crouch":
            self.sq = .3
            pose["arms"] = "down"
        elif s == "eat":
            pose["eyes"] = "happy" if self.timer < 2.5 else "open"
            if self.timer < 2.5 and self.cooldown("chomp", .4):
                self.spawn("crumb", 2)
                self.sfx("crunch")
                self.sqv += 3
            if self.timer - dt <= 0:
                self.happy = min(100, self.happy + 15)
                self.energy = min(100, self.energy + 20)
                self.say(self.line("eat"))
                self.spawn("heart", 2)
        elif s == "dizzy":
            pose.update(eyes="x", bob=math.sin(self.time * 8) * .2)
        elif s == "sneeze":
            if self.timer > .55:  # build-up: lean back, eyes squeezed
                pose.update(eyes="closed", arms="up", bob=-.3)
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
                pose.update(eyes="x" if self.timer > .3 else "open", arms="down")
            if self.timer - dt <= 0:
                self._sneezed = False
        elif s == "moonwalk":
            if not self.stay:
                self.move_along(-self.dir * 70 * k * dt)
            self.walkdist += 70 * k * dt
            pose.update(legs=1 + int(self.walkdist / (P * 1.2)) % 2, arms="down")
            self.look = [self.dir * .5, 0]
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

    def move_along(self, step):
        L_, T_, R_, B_ = self.mon
        h = self.half()
        sf = self.surf
        climb_ok = self.cfg["climb"]
        if sf == "floor":
            if self.plat:
                lo, hi = max(self.plat_rect[0], L_) + self.PW * .3, min(self.plat_rect[2], R_) - self.PW * .3
            else:
                lo, hi = L_ + h, R_ - h
            self.fx += step
            if self.fx <= lo or self.fx >= hi:
                self.fx = min(max(self.fx, lo), hi)
                if self.state not in ("walk", "chase", "play"):
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
        s = self.state
        impact = self.vy
        self.surf, self.plat, self.plat_rect = "floor", hwnd, rect
        self.vx = self.vy = 0
        self.speed = 0
        self.sq = min(.5, .1 + impact / (5000 * self.k))
        self.sqv = 0
        self.sfx("land", min(1, .3 + impact / (2500 * self.k)))
        if s == "fall":
            if self.max_v > 3200 * self.k:
                self.set_state("dizzy")
                self.say(self.line("dizzy"))
            else:
                self.set_state("idle", 1.2)
                self.say(self.line("land"))
        else:
            self.set_state("idle", random.uniform(.6, 1.5))

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

    def draw(self, mx, my):
        c, P, k = self.c, self.P, self.k
        c.delete("all")
        self.dsurf = "floor" if self.surf in ("air", "fly") else self.surf
        pose = self.pose
        s = self.state

        # squash & stretch
        sq = self.sq
        if self.surf == "air" and s != "drag":
            sq = -min(.18, abs(self.vy) / (9000 * k))
        self.sx, self.sy = 1 + sq * .55, 1 - sq * .6
        if s in ("idle", "listen", "hang"):
            self.sy *= 1 + math.sin(self.time * 2.4) * .02
        self.bob = pose["bob"]

        # eye direction follows the mouse
        pcx, pcy = self.pet_center()
        lx, ly = self.local_dir(mx - pcx, my - pcy)
        tu = max(-1, min(1, lx / (220 * k))) * .55
        tv = max(-1, min(1, ly / (220 * k))) * .5
        if s in ("peek", "moonwalk") or (s == "dance" and getattr(self, "_moon", False)):
            tu, tv = self.look[0], 0
        elif s in ("walk", "chase", "play", "fly", "come"):
            tu, tv = self.dir * .5 * (1 if self.dsurf in ("floor", "lwall") else -1), 0
        elif s == "code":
            tu, tv = 0, .5
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
                    self.blink_at = self.time + random.uniform(2, 6)
            elif self.energy < 15:
                eyes = "half"

        # body + arms + legs
        self.rect(2, 0, 14, 7, ORANGE)
        arms = pose["arms"]
        if arms == "down":
            self.rect(0, 3, 2, 5, ORANGE); self.rect(14, 3, 16, 5, ORANGE)
        elif arms == "up":
            self.rect(0, 1, 2, 3, ORANGE); self.rect(14, 1, 16, 3, ORANGE)
        elif arms == "type":
            kk = int(self.time * 8) % 2
            self.rect(.6, 4 + kk * .5, 2.6, 6 + kk * .5, ORANGE); self.rect(13.4, 4.5 - kk * .5, 15.4, 6.5 - kk * .5, ORANGE)
        elif arms == "wave2":
            self.rect(0, 3, 2, 5, ORANGE); self.rect(14, 1, 16, 3, ORANGE)
        else:  # wave
            self.rect(0, 1, 2, 3, ORANGE); self.rect(14, 3, 16, 5, ORANGE)
        legs = pose["legs"]
        for i, col in enumerate((3, 5, 10, 12)):
            short = (legs == 1 and i % 2 == 0) or (legs == 2 and i % 2 == 1)
            self.rect(col, 7, col + 1, 8 if short else 9, ORANGE)

        # eyes
        w = max(2, P * .45)
        for side, col in ((-1, 4), (1, 11)):
            u, v = col + eu, 2 + ev
            if eyes == "open":
                self.rect(u, v, u + 1, v + 2, BLACK)
            elif eyes == "big":
                self.rect(u - .25, v - .4, u + 1.25, v + 2.2, BLACK)
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

        # propeller hat while flying
        if self.surf == "fly":
            self.rect(5, -.9, 11, .2, "#4A7BD0", "pet")
            self.rect(6.5, -1.5, 9.5, -.9, "#4A7BD0", "pet")
            self.rect(7.7, -2.4, 8.3, -1.5, "#555555", "pet")
            spin = int(self.time * 24) % 4
            span = (4.5, 2.5, .6, 2.5)[spin]
            self.rect(8 - span, -2.9, 8 + span, -2.4, ("#F5C542", "#E5484D")[spin % 2], "pet")

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

        # pet bbox and visible area (for bubbles)
        xs, ys = zip(self.T(0, -3 if self.surf == "fly" else 0), self.T(16, 9))
        self.pbox = (min(xs), min(ys), max(xs), max(ys))
        L_, T_, R_, B_ = self.mon
        self.vis = (max(0, L_ - self.wx), max(0, T_ - self.wy), min(self.S, R_ - self.wx), min(self.S, B_ - self.wy))

        # overlays
        offset = 0
        if self.timers:
            offset = self.draw_timer_pill()
        if self.ask_req:
            self.draw_ask(offset)
        elif s == "think" or self.waiting:
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
        tk.Label(outer, text=self.tr("chat_hint"), bg=CREAM, fg="#8a8a8a", font=("Segoe UI", 8),
                 wraplength=int(420 * k)).pack(fill="x")

        def submit(_=None):
            text = ent.get()
            ent.delete(0, "end")
            self.handle_text(text)

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
            self.chat.destroy()
            self.chat = None
            if self.state == "listen":
                self.set_state("idle", 1)

    def clear_chat(self):
        self.chat_log, self.history = [], []
        self.render_chat()

    def render_chat(self):
        if not self.chat:
            return
        t = self.chat_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        if not self.chat_log:
            t.insert("end", self.tr("chat_hint") + "\n", ("sys", "rtl") if self.lang == "ar" else ("sys",))
        for who, msg in self.chat_log[-60:]:
            rtl = ("rtl",) if is_ar(msg) else ()
            name = self.tr("you") if who == "me" else "Clawd"
            t.insert("end", name + "\n", (who + "_name",) + rtl)
            t.insert("end", msg + "\n\n", (who,) + rtl)
        if self.waiting:
            t.insert("end", "✻ " + self.tr("thinking") + "...\n", ("sys",))
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
        check("smart_lbl", "smart")
        check("remind_lbl", "reminders")
        check("startup_lbl", None, self.set_startup)
        row += 1
        ttk.Label(g, text=self.tr("help") + "\nCtrl+Alt+S: stay  |  Ctrl+Alt+H: hide / show", foreground="#777",
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
    def show_menu(self, e):
        tr = self.tr
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label=tr("mood", h=int(self.happy), e=int(self.energy)), state="disabled")
        m.add_separator()
        m.add_command(label=tr("talk"), command=self.open_chat)
        stay_v = tk.BooleanVar(value=self.stay)
        m.add_checkbutton(label=tr("stay"), variable=stay_v, command=lambda: self.set_stay(stay_v.get()))
        m.add_command(label=tr("come"), command=self.come_here)
        if self.surf == "fly":
            m.add_command(label=tr("land"), command=self.stop_fly)
        else:
            m.add_command(label=tr("fly"), command=lambda: self.run_action({"type": "fly"}))
        m.add_separator()
        m.add_command(label=tr("feed"), command=lambda: self.set_state("eat") if self.surf == "floor" else None)
        m.add_command(label=tr("ball_away") if self.ball else tr("ball"), command=self.toggle_ball)

        mu = tk.Menu(m, tearoff=0)
        for i, name in enumerate(T["tracks"][1 if self.lang == "ar" else 0]):
            mu.add_command(label="♪  " + name, command=lambda i=i: self.music_cmd("play", i))
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
        to.add_command(label=tr("pc_status"), command=lambda: self.say(self.status_line()))
        to.add_command(label=tr("password"), command=self.make_password)
        to.add_command(label=tr("screenshot"), command=lambda: self.run_action({"type": "screenshot"}))
        to.add_command(label=tr("coin"), command=lambda: self.run_action({"type": "coin"}))
        to.add_command(label=tr("dice"), command=lambda: self.run_action({"type": "dice"}))
        m.add_cascade(label=tr("tools"), menu=to)

        fun = tk.Menu(m, tearoff=0)
        fun.add_command(label=tr("joke"), command=lambda: self.say(self.line("jokes")))
        fun.add_command(label=tr("sneeze"), command=lambda: self.set_state("sneeze"))
        fun.add_command(label=tr("moonwalk"), command=lambda: self.set_state("moonwalk"))
        fun.add_command(label=tr("peek"), command=self.go_peek)
        fun.add_command(label=tr("web"), command=lambda: self.start_web() if self.surf == "ceil" else self.run_action(
            {"type": "animate", "name": "web"}))
        fun.add_command(label=tr("ask_joke"), command=self.ask_joke)
        m.add_cascade(label=tr("funny"), menu=fun)

        act = tk.Menu(m, tearoff=0)
        for key in ("dance", "code", "think", "sleep", "stretch", "jump", "walk"):
            act.add_command(label=tr(key), command=lambda s=key: self.set_state(s))
        act.add_command(label=tr("climb"), command=self.go_climb)
        act.add_command(label=tr("hop"), command=self.try_hop)
        act.add_command(label=tr("chase"), command=lambda: self.set_state("chase"))
        act.add_command(label=tr("ask_joke"), command=self.ask_joke)
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
        self._menu_refs = (m, sv, lv, stay_v)
        m.tk_popup(e.x_root, e.y_root)

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
        self.say(self.line("bye"))
        self.sfx("no")
        self.audio.stop()
        self.state, self.timer = "sad", 100
        self.save()
        self.root.after(1300, self.root.destroy)


class Ball:
    """A throwable toy ball living in its own little transparent window."""

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
        self.drag = [(time.perf_counter(), e.x_root, e.y_root)]

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
        if self.pet.surf == "floor" and self.pet.state in ("idle", "walk", "think", "play") and not self.pet.stay:
            self.pet.set_state("play", 10)

    def step(self, dt):
        k = self.pet.k
        L_, T_, R_, B_ = self.pet.mon
        r = self.size / 2
        if self.drag is None:
            self.vy += 2600 * k * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            if self.y >= B_:
                self.y = B_
                if abs(self.vy) > 150 * k:
                    self.vy = -self.vy * .62
                    if abs(self.vy) > 400 * k:
                        self.pet.sfx("kick", .35)
                else:
                    self.vy = 0
                self.vx *= .985 ** (dt * 60)
            if self.x < L_ + r or self.x > R_ - r:
                self.x = min(max(self.x, L_ + r), R_ - r)
                self.vx = -self.vx * .7
            if self.y - self.size < T_:
                self.y, self.vy = T_ + self.size, abs(self.vy) * .5
        self.win.geometry(f"{self.size}x{self.size}+{int(self.x - r)}+{int(self.y - self.size)}")


if __name__ == "__main__":
    _mutex = kernel32.CreateMutexW(None, False, "ClawdDesktopPetMutex")
    if kernel32.GetLastError() == 183 and "--test" not in sys.argv:  # already running
        sys.exit(0)
    Clawd().root.mainloop()
