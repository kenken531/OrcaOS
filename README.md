# OrcaOS v1.0

```
  ██████╗ ██████╗  ██████╗ █████╗  ██████╗ ███████╗
 ██╔═══██╗██╔══██╗██╔════╝██╔══██╗██╔═══██╗██╔════╝
 ██║   ██║██████╔╝██║     ███████║██║   ██║███████╗
 ██║   ██║██╔══██╗██║     ██╔══██║██║   ██║╚════██║
 ╚██████╔╝██║  ██║╚██████╗██║  ██║╚██████╔╝███████║
  ╚═════╝ ╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝
  v1.0 · BUILDCORED ORCAS · Day 30 Capstone
```

> A full-stack RTOS-inspired TUI shell that unifies 30 days of hardware-adjacent Python into one running system — gesture-controlled volume, workstation locking, live audio analysis, local LLM reasoning, and system monitoring, all from a single terminal command.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Folder Structure](#folder-structure)
- [Requirements](#requirements)
- [Setup](#setup)
- [Usage](#usage)
- [Gesture Controls](#gesture-controls)
- [LLM Shell](#llm-shell)
- [Keyboard Bindings](#keyboard-bindings)
- [Recommended Models](#recommended-models)
- [Common Fixes](#common-fixes)
- [Integrated Projects](#integrated-projects)
- [Hardware Concept and v2.0 Bridge](#hardware-concept-and-v20-bridge)

---

## Features

### Four live panels

| Panel | What you see |
|---|---|
| **GESTURE** | Hand pose, confidence, FPS, live volume bar, last action log |
| **AUDIO** | 16-band FFT spectrum, RMS level bar, peak, dBFS reading |
| **SYSTEM** | CPU %, RAM %, session uptime |
| **LLM** | Token-by-token streaming responses from a local ollama model |

### Gesture controls (real system actions)

| Gesture | Action |
|---|---|
| ✊ **FIST** — make a fist anywhere | Captures current volume as baseline |
| ✊ **FIST** — move hand **up** | Increases volume relative to where you started |
| ✊ **FIST** — move hand **down** | Decreases volume relative to where you started |
| ✊ **FIST** — release | Volume stays where you left it, ready for next engage |
| 🤏 **PINCH** — hold 1.5 seconds | Locks the workstation |

Volume control is **relative** — making a fist at any position captures the current system volume as the baseline. Moving up/down adjusts from there. No snapping, no position dependency.

### LLM shell

Type any prompt at `orca>` to stream a response from your local ollama model. Built-in commands let you check system status, switch models on the fly, and clear the output buffer.

---

## Architecture

OrcaOS models an RTOS in software. ISR threads read hardware into queues; a 50ms scheduler drains queues and dispatches actions; panels render reactively.

```
Webcam  ──► GestureCapture (thread) ──► frame_queue ──► GestureInference (thread)
                                                               │
                                                        gesture_queue
                                                               │
Mic     ──► AudioISR       (thread) ──► audio_queue ──┐       │
psutil  ──► SysISR         (thread) ──► sys_queue  ──┤        ▼
ollama  ──► LLMTask        (thread) ──► llm_queue  ──┤  OrcaScheduler (50ms tick)
                                                      └────────┤
                                                               │
                                              ┌────────────────┼──────────────────┐
                                              ▼                ▼                  ▼
                                        GesturePanel     AudioPanel / SysPanel  LLMPanel
                                              │
                                              ▼
                                       GestureActionProcessor
                                       (non-blocking — returns instantly)
                                              │
                                              ▼
                                        VolumeWorker (thread)
                                        owns COM permanently
                                        SetMasterVolumeLevelScalar()
```

| RTOS concept | OrcaOS equivalent |
|---|---|
| ISR | Daemon thread reading from hardware |
| Queue | `threading.Queue` per channel |
| Scheduler | `set_interval(0.05, tick)` on Textual main thread |
| Task | Handler fired when queue has data |
| Firmware | `python orcaos.py` |

### Threading model

Every piece of hardware gets its own thread. The Textual main thread never touches hardware or COM — it only reads from queues and updates widgets. `VolumeWorker` owns the pycaw COM object permanently on its own thread, accepting volume targets via a non-blocking queue so the UI never waits on Windows audio APIs.

Gesture capture and inference are **decoupled** into two threads with a 2-frame drop queue between them. When MediaPipe takes longer on a fist, the camera keeps reading at full speed and drops stale frames, so the TUI never freezes.

---

## Folder Structure

```
orcaos/
├── orcaos.py               # Entry point — Textual App, ISR boot, CLI flags
├── scheduler.py            # OrcaScheduler — 50ms tick, queue drain, action dispatch
├── state.py                # Shared queues + state dict + thread lock
├── download_model.py       # One-time: downloads hand_landmarker.task (~9 MB)
├── camera_check.py         # Diagnostic: scans all camera indices and backends
├── debug_volume.py         # Diagnostic: tests pycaw step by step in isolation
├── hand_landmarker.task    # MediaPipe hand model (created by download_model.py)
├── volume_worker.log       # Created at runtime: VolumeWorker debug log
├── requirements.txt
└── README.md
│
├── isr/
│   ├── gesture_isr.py      # Webcam capture + MediaPipe/OpenCV inference → gesture_queue
│   ├── audio_isr.py        # PyAudio mic stream → FFT + RMS → audio_queue
│   └── sys_isr.py          # psutil 1s poll → sys_queue
│
├── tasks/
│   ├── gesture_actions.py  # GestureActionProcessor + VolumeWorker (COM thread)
│   └── llm_task.py         # ollama subprocess streamer → llm_queue
│
└── panels/
    ├── gesture_panel.py    # Live gesture + volume bar + action log
    ├── audio_panel.py      # FFT spectrum + RMS level
    ├── sys_panel.py        # CPU / RAM / uptime
    └── llm_panel.py        # Streaming LLM output + thinking spinner
```

---

## Requirements

**System**
- Python 3.11 or 3.13+ (tested on both)
- Windows 10 / 11
- Webcam (optional — `--no-gesture` to skip)
- Microphone (optional — `--no-audio` to skip)
- [ollama](https://ollama.ai) installed and running

**Python packages**

```
textual>=0.52.0
psutil>=5.9.0
opencv-python>=4.8.0
numpy>=1.24.0
pyaudio>=0.2.13
pycaw>=20230407
comtypes>=1.4.0
mediapipe==0.10.35
```

---

## Setup

**1. Clone and install dependencies**

```bash
git clone https://github.com/yourusername/orcaos
cd orcaos
pip install -r requirements.txt
```

If `pyaudio` fails on Windows:
```bash
pip install pipwin
pipwin install pyaudio
```

**2. Download the hand landmark model**

```bash
python download_model.py
```

Downloads `hand_landmarker.task` (~9 MB) into the `orcaos/` folder. Only needed once. Without it, gesture detection falls back to OpenCV skin detection (less accurate, no volume control).

**3. Pull an ollama model**

```bash
ollama pull llama3.2:3b
```

See [Recommended Models](#recommended-models) for guidance on which model fits your hardware.

**4. Verify your camera** (if gesture panel shows OFFLINE)

```bash
python camera_check.py
```

**5. Verify volume control** (if volume doesn't respond to gestures)

```bash
python debug_volume.py
```

---

## Usage

```bash
# Full mode — webcam + mic + LLM
python orcaos.py

# Specify camera index (try 1 or 2 if 0 fails)
python orcaos.py --camera 1

# No webcam
python orcaos.py --no-gesture

# No microphone
python orcaos.py --no-audio

# Headless — SysPanel + LLM only, no hardware needed
python orcaos.py --headless
```

---

## Gesture Controls

Make sure the GESTURE panel shows `● LIVE` and the `MediaPipe` badge is green before using gestures.

### Volume control

1. Hold your hand in front of the webcam and **close it into a fist** ✊
2. OrcaOS captures the current system volume and your hand position as the baseline — no snapping
3. **Move your fist up** to increase volume, **move it down** to decrease
4. The amount you move determines how much volume changes — half the frame height ≈ 75% change
5. **Open your hand** to release. Volume stays at the level you set
6. Make a fist again anywhere — the new current volume becomes the new baseline

The live volume bar in the GESTURE panel updates in real time. The last action is shown with a timestamp.

### Lock screen

1. **Pinch** your thumb and index finger together 🤏
2. The panel shows `hold 1.5s to lock 🔒`
3. Hold for **1.5 seconds** — the workstation locks automatically
4. Release before 1.5 seconds to cancel

---

## LLM Shell

Type any prompt at the `orca>` input and press Enter. Responses stream token by token.

| Command | Description |
|---|---|
| `<any text>` | Send as prompt to the local ollama model |
| `status` | LLM gives a one-sentence system health assessment using live CPU/RAM/gesture data |
| `model <name>` | Switch ollama model live (e.g. `model phi3:mini`) |
| `clear` | Clear the LLM response panel |
| `quit` / `exit` / `q` | Shut down OrcaOS cleanly |

---

## Keyboard Bindings

| Key | Action |
|---|---|
| `Ctrl+C` | Quit — stops all ISR threads cleanly before exit |
| `Ctrl+L` | Clear LLM response panel |
| `Ctrl+G` | Show gesture ISR status in LLM panel |
| `Escape` | Focus the command input |

---

## Recommended Models

OrcaOS auto-detects the first model in `ollama list`. Switch anytime with `model <name>` at the prompt.

| Model | Size | Best for |
|---|---|---|
| `llama3.2:3b` | ~2 GB | **Best overall** — fast, fits fully in 4 GB VRAM |
| `gemma2:2b` | ~1.5 GB | Fastest responses, very light |
| `phi3:mini` | ~2.3 GB | Best reasoning and code, slightly slower |
| `llama3.2` (8B) | ~4.7 GB | Too large for 4 GB VRAM — runs on CPU, slow |

For hardware with 4 GB dedicated VRAM (GTX 1650, RTX 3050, etc.):
```bash
ollama pull llama3.2:3b   # recommended
ollama pull phi3:mini      # alternative for technical tasks
```

For hardware with 8 GB+ VRAM:
```bash
ollama pull llama3.1:8b
ollama pull mistral:7b
```

---

## Common Fixes

**GESTURE panel: `MediaPipe init failed`**

You may be on Python 3.13. Install the correct wheel:
```bash
pip install mediapipe==0.10.35
python download_model.py
```

**GESTURE panel: `● LIVE` but badge says `OpenCV` (yellow)**

The `hand_landmarker.task` model is missing. Run:
```bash
python download_model.py
```

**Camera not found**

```bash
python camera_check.py        # find the working index
python orcaos.py --camera 1   # use it
```

**Volume doesn't change when making a fist**

```bash
python debug_volume.py
```

If Step 5 fails with `'AudioDevice' object has no attribute 'Activate'`:
```bash
pip install pycaw comtypes --upgrade
```

If all steps pass but volume still doesn't change in OrcaOS, check `volume_worker.log` after running for a few seconds with a fist gesture.

**pyaudio install fails**

```bash
pip install pipwin
pipwin install pyaudio
```

**ollama not responding**

```bash
ollama serve    # run in a separate terminal, then relaunch OrcaOS
```

**TUI renders blank or corrupted**

Run from Windows Terminal or `cmd.exe`. Spyder, Jupyter, and VS Code's built-in terminal may not render Textual correctly.

**Volume snaps to wrong level when making a fist**

The gesture recognition may be flickering between FIST and another label, resetting the baseline. Make sure your hand is clearly closed before moving it. The panel shows the current label in real time.

---

## Integrated Projects

| Day | Project | Role in OrcaOS |
|---|---|---|
| 1 | VolumeKnuckle | Gesture → volume concept; pycaw integration |
| 2 | BlinkLock | PINCH hold → `LockWorkStation()` via ctypes |
| 8 | EdgeAgent | LLMTask — ollama subprocess with dual stderr thread |
| 12 | AudioScope | AudioISR — 16-band FFT from PyAudio chunks via numpy |
| 13 | EchoKiller | AudioISR — PyAudio stream pipeline with overflow handling |
| All | psutil usage | SysISR — CPU / RAM / uptime every second |

---

## Hardware Concept and v2.0 Bridge

OrcaOS is firmware that runs on your laptop instead of bare metal. Every design decision maps directly to embedded systems thinking:

- **ISR threads** fire continuously and never block the main loop — exactly like hardware interrupt handlers
- **The frame drop queue** between capture and inference models what a DMA controller does: keeps the bus moving even when the CPU is busy
- **VolumeWorker** is a dedicated peripheral driver — it owns its hardware interface and accepts commands via a message queue, just like an I²C driver on a microcontroller
- **The scheduler tick** is the main task loop — equivalent to `vTaskDelay` in FreeRTOS
- **Panels** are output actuators — the software equivalent of driving an LED or servo

### v2.0 — OrcaOS on a Raspberry Pi Pico

The queue model is identical. Only the hardware layer changes.

| v1.0 (laptop) | v2.0 (Pico W) |
|---|---|
| Webcam → MediaPipe | PIR + ultrasonic distance sensor |
| PyAudio mic | MEMS microphone (I²S / PDM) |
| psutil CPU % | Internal ADC + RP2040 temperature |
| pycaw → Windows audio | PWM → RC filter → analog out |
| Textual TUI | SSD1306 OLED (128×64, I²C) |
| `threading.Queue` | FreeRTOS `xQueueSend` / `xQueueReceive` |
| `set_interval(0.05)` | `vTaskDelayUntil` at 20 Hz |
| `LockWorkStation()` | GPIO output → relay / solenoid |
| VolumeWorker thread | Dedicated FreeRTOS task pinned to core 1 |

---

## Credits

Built as the Day 30 capstone of **BUILDCORED ORCAS** — 30 days of hardware-adjacent Python challenges, one working project shipped per day.

**BUILDCORED ORCAS · Day 30 of 30 · Expert tier**
