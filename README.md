# GodFathers OCR

Local helper for **Idle Mafia** in the **Roblox desktop player**. It screenshots the game window on this PC, reads it with **RapidOCR**, then moves the mouse. There is no account, no server, and none of our code makes HTTP requests.

First install (source only) uses pip/winget so Python and RapidOCR can land on disk. After that it is capture + OCR + clicks.

This GitHub repo is the **source code**. You can run it from source, or build a Windows `.exe` that already has Python and RapidOCR inside.

## What it does

Turn on the features you want, then Start. It works the gold buttons. Grey and LEVEL lock are never pressed.

| Feature | What it presses |
| --- | --- |
| **Jobs** | Gold **DO JOB** |
| **Family** | **GIVE 5** then **GIVE 1** until stamina is 0 |
| **Shop** | Cash **ALL**, then gold **BUY**. Grey **LEVEL** is skipped. Stock rotates about every 5 minutes |
| **Bank** | **WITHDRAW ALL** / **DEPOSIT ALL** only if the Bank switch is on |

Tick none on Shop = buy the affordable cash ALL list. Tick names = those items only.

## Two ways to run

### 1. Source (this repo)

Windows. First run needs internet so Python and RapidOCR can install.

1. Download or clone this repo. Keep the files together.
2. Double-click **`Start GodFathers OCR.bat`**.
3. The first run can take a few minutes. Later runs just open the app.
4. Open Idle Mafia in the Roblox **desktop player** (not the browser) and leave it in front.
5. Click **Scan Tabs**, tick Jobs / Family / Shop / Bank, then **Start**.

Same thing from a terminal after the first Start:

```bat
.\.venv\Scripts\python.exe main.py
```

### 2. Windows exe (no Python on their PC)

Build it from this source, then send the zip. RapidOCR is already inside the zip. They do not install Python.

On a PC that already ran Start once:

1. Double-click **`build.bat`**.
2. Wait. It writes `dist\GodFathersOCR\GodFathersOCR.exe` and `dist\GodFathers-OCR-windows.zip`.

Tell them:

1. Download the zip.
2. If Windows blocked it: right-click the zip → Properties → Unblock → OK, then unzip.
3. Unzip the folder. Keep **GodFathersOCR.exe** next to the **`_internal`** folder. Do not move the exe on its own.
4. Double-click **GodFathersOCR.exe**. First open can take a few seconds while OCR loads.
5. Open Idle Mafia in the Roblox desktop player and leave it in front.
6. Scan Tabs, tick what you want, then Start.

Put the folder on the Desktop. Do not put it in Program Files.

`Give to friends.bat` is a **source zip**, not the exe. Friends who get that zip still need **`Start GodFathers OCR.bat`** and internet on first run.

## Keys and HUD

| Key | What it does |
| --- | --- |
| **F2** | Live HUD |
| **F3** | Stop everything |

Clicks pass through the Live HUD. Idle Mafia must stay in front. F3 still stops.

## Using it

1. Leave Idle Mafia large and in front. Not Firefox. Not a tiny window.
2. **Scan Tabs** so it can read Jobs / Family / Shop / Bank.
3. Tick the features you want. Bank only runs if the Bank switch is on.
4. **Start**. The main window hides. The Live HUD stays.
5. Watch the log. Gold **DO JOB**, **GIVE**, gold **BUY**, and **DEPOSIT ALL** are pressed when they are lit.
6. **F3** stops.

It is not 100%. OCR can miss a name, mix Energy / Stamina, or skip a row. If Shop is open and gold BUY is on screen, it should click those, not the green `$` price.

## Files you should not share

Do not commit or zip:

- `.venv/`
- `logs/`
- `captures/`
- `config/clicks.json`
- `config/playbook.json`
- `config/settings.json`
- `dist/` and `build/` (except the zip you mean to send)

Scan learns click spots on **that** PC. Each person should Scan Tabs on their own window.

## Layout

- `main.py` — app entry
- `app/` — OCR, clicks, Jobs / Family / Shop / Bank
- `tests/` — unit tests
- `tools/` — Windows setup, exe build, source zip
- `Start GodFathers OCR.bat` — run from source
- `build.bat` — build the Windows exe + zip
- `Give to friends.bat` — source zip (they still run the `.bat`)
- `GodFathersOCR.spec` — PyInstaller spec
