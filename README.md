# 🏎️⚡ APEX OVERDRIVE 🏁🔥

[![CI](https://github.com/skrehanahamed/Apex_Overdrive/actions/workflows/ci.yml/badge.svg)](https://github.com/skrehanahamed/Apex_Overdrive/actions/workflows/ci.yml)
[![Release](https://github.com/skrehanahamed/Apex_Overdrive/actions/workflows/release.yml/badge.svg)](https://github.com/skrehanahamed/Apex_Overdrive/actions/workflows/release.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Pygame](https://img.shields.io/badge/pygame--ce-2.5%2B-red.svg?logo=gamepad)](https://pyga.me/)

> 🌆 **Retro-pixel pseudo-3D street racer** featuring high-speed police pursuits 🚓🚨, explosive nitro boosts 💥, a functional rear-view mirror 🪞, procedural synthwave music 🎵, and escalating heat levels 🌡️. Built with **Python 🐍** and **pygame-ce 🎮**.

![APEX OVERDRIVE Gameplay](brand/gameplay_preview.png)

---

## 🎮 Quick Start 🚀

### 📋 Prerequisites
- 🐍 **Python 3.10+**
- 📦 **pip** / **make**

```bash
# 📥 1. Clone the repository
git clone git@github.com:skrehanahamed/Apex_Overdrive.git
cd Apex_Overdrive

# 🏎️ 2. Run the game (auto-creates .venv and installs dependencies)
make run

# 🤖 3. Watch the AI autopilot drive
make bot

# 🎨 4. Rebuild transparent sprites from raw sheets (optional)
make assets
```

### 🛠️ Manual Run
```bash
python3 -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

---

## 🕹️ Controls 🎯

| Key | Action | Details |
|:---:|:---|:---|
| ⬅️ ➡️ ⬆️ ⬇️ / **WASD** | 🏎️ Steer, Gas, Brake | Full throttle to build distance from pursuers |
| **Space** / **Shift** | 💥 Nitro Boost | Extreme speed burst to escape police heat |
| **P** / **Esc** | ⏸️ Pause Game | Toggle pause overlay |
| **M** | 🔇 Mute Audio | Silence engine & procedural synthesizer |
| **C** | 📺 CRT Scanlines | Retro arcade scanline & curvature simulation |
| **F** | 🖥️ Fullscreen | Toggle display mode |
| **Enter** | 🚦 Start / Retry | Launch race or retry after getting busted |

---

## 🏁 Gameplay & Core Features 🌟

- 🚨 **High-Speed Police Pursuits & Heat Meter**: You start with an open highway. Soon the sirens blaze and police cruisers join the chase. Keep the distance bar away from **BUSTED**. Fill the meter to escape and elevate your Heat level 🌡️ (faster cruisers, heavier traffic, double roadblocks 🚧).
- 💥 **Near Misses & Nitro Refills**: Weave tightly between lanes and thread the needle through congested traffic to rack up score combos and replenish your nitro tank. Collect glowing blue canisters 🧪 on the asphalt for instant refills.
- 🪞 **Functional Rear-View Mirror**: Live real-time rear-view mirror showing squad cars closing in from behind.
- 🎵 **100% Procedural Synthwave Audio**: Zero external `.wav` or `.mp3` files! Layered engine audio with multi-gear acceleration, tyre squeals, turbo spool whines, police sirens, and a custom procedural synthwave soundtrack synthesized on the fly with NumPy 🎹.
- 🌆 **Dynamic Themes & Scenery**: 4 distinct visual biomes (🌅 Sunset, 🌃 Midnight, 🌄 Dawn, 💜 Vaporwave) with custom roadside dressings, palm trees, skyscrapers, and panoramic horizons.
- 📺 **Authentic Arcade CRT Filter**: Instant retro arcade CRT scanline post-processing filter.

![APEX OVERDRIVE Title Screen](brand/title_preview.png)

---

## 📁 Repository Architecture 🗂️

```text
📁 Apex_Overdrive/
├── 📄 main.py               # 🚀 Entry point (--bot, --shot out.png, --title)
├── 📁 apex/                 # ⚙️ Core game engine
│   ├── 🐍 world.py          # 🏎️ Physics simulation, traffic AI, pursuit logic
│   ├── 🐍 render.py         # 🎨 Pseudo-3D road projection, backdrops, HUD
│   ├── 🐍 track.py          # 🛣️ Procedural track curves, hills & themes
│   ├── 🐍 assets.py         # 🖼️ Sprite management & world-scale coordinates
│   ├── 🐍 audio.py          # 🎹 NumPy procedural audio synthesis engine
│   ├── 🐍 font.py           # 🔤 Pixel UI typography system
│   └── 🐍 game.py           # 🔄 Fixed-timestep game loop & state manager
├── 📁 assets/               # ✂️ Transparent cut sprites and game elements
├── 📁 sheets/               # 🎨 Raw generated sprite sheets & horizons
├── 📁 brand/                # 🏷️ APEX logo and HD gameplay previews
├── 📁 tools/                # 🧰 Sprite cutter & asset build automation
├── ⚙️ ApexOverdrive.spec     # 📦 Cross-platform PyInstaller bundle specification
└── 📁 .github/workflows/    # 🤖 GitHub Actions CI/CD automation
    ├── ⚡ ci.yml            # 🧪 Automated multi-OS test matrix & smoke tests
    └── 🚀 release.yml       # 📦 Standalone binary packager & auto-release publisher
```

---

## 🚀 Standalone Releases & Binaries 📦

Standalone zero-dependency desktop executables for **Windows**, **Linux**, and **macOS** are automatically built and published on every release!

👉 **[Download the Latest Release on GitHub](https://github.com/skrehanahamed/Apex_Overdrive/releases)**

| Platform | Package | How to Run |
|:---|:---|:---|
| 🪟 **Windows (x64)** | `apex-overdrive-windows-x64.zip` | Extract and run `ApexOverdrive.exe` |
| 🐧 **Linux (x64)** | `apex-overdrive-linux-x64.tar.gz` | Extract and run `./ApexOverdrive` |
| 🍎 **macOS (ARM/Intel)** | `apex-overdrive-macos-x64.zip` | Extract and run `./ApexOverdrive` |
| 🐍 **Cross-Platform** | `apex-overdrive-source.zip` | Run with Python 3.10+ & `pip install -r requirements.txt` |

### 🔨 Building Standalone Executables Locally
```bash
pip install pyinstaller
pyinstaller ApexOverdrive.spec --noconfirm
# ✨ The compiled standalone application will be ready in dist/ApexOverdrive/
```

---

## 📜 License 📄

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for complete details.

---

<p align="center">
  <b>🏎️ Buckle up, hit the nitro, and outrun the law! 💨</b>
</p>
