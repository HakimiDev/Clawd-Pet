<p align="center"><img src="assets/clawd.png" width="160" alt="Clawd"></p>

# Clawd Desktop Pet

A smart, funny desktop pet for Windows starring Clawd, the little orange pixel character from Claude Code.
English + العربية.

> Fan-made project. Not affiliated with or endorsed by Anthropic.

## Download & run
Grab `Clawd.exe` from the [Releases](../../releases) page and double-click it. No install needed.
Settings, notes and the music cache are saved in a `Clawd Data` folder next to the exe, so the whole
thing is portable: copy the folder, share it, done.

## What he does
- **Moves around for real**: walks on the taskbar, climbs walls, walks upside-down on the ceiling,
  hangs from a spider web, jumps onto windows and rides them when you move them, flies with a propeller hat.
- **Physics**: drag and throw him. He bounces, gets dizzy, or sticks to the wall like a spider.
  Drop him near a screen edge or the top of the screen and he grabs on. Drop him on a window and he stands on it.
- **Stay / come / fly**: say `stay` (or press **Ctrl+Alt+S**) and he stops moving. Say `come`, `fly` or `land`.
- **Talks with any AI**: Claude, OpenAI, Gemini, OpenRouter, Groq, DeepSeek, Mistral, Ollama, LM Studio,
  or any OpenAI-compatible server. Right-click > Settings > AI Brain, paste a key, done.
- **Useful**: timers and reminders ("timer 5 min tea", "remind me at 17:30 call mom"), pomodoro, notes,
  open sites/apps, web search, strong passwords, screenshots, PC media control, and AI clipboard tools
  (explain, translate Arabic <-> English, summarize, fix writing, write a reply).
- **Smart**: reacts to the app you're using, the Spotify song playing, copied error messages,
  being AFK, high CPU, low battery, late nights; reminds you to stretch and drink water.
- **Fun**: built-in chiptune music he dances to (or your own MP3s), a ball to play with, jokes,
  sneezes, moonwalks, peekaboo, petting, cookies, and funny Claude Code-style approval popups.

## Controls
| Action | What happens |
|---|---|
| Click | Jump + a quip |
| Double-click / **Ctrl+Alt+C** | Chat |
| Drag & throw | Fly, bounce, stick to walls |
| Rub with the mouse | Petting |
| Mouse wheel | Resize |
| Right-click | Menu |
| **Ctrl+Alt+S** | Stay / move |
| **Ctrl+Alt+H** | Hide / show |

Chat works offline for commands (`stay`, `fly`, `timer 10 min`, `open youtube`, `play music`, `note: ...`,
`password`, `joke`, `12*7`, and the Arabic versions like `ابق`، `تعال`، `طير`، `ذكرني بعد 10 دقائق`).
Connect an AI brain for real conversation.

## Run from source
```bash
pip install -r requirements.txt
pythonw clawd_pet.pyw
```

## Build the exe
```bash
build.bat
```
The portable exe lands in `dist\Clawd.exe`.

## License
MIT
