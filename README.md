# OrcaOS v1.0

> **BUILDCORED ORCAS — Day 30 Capstone**
> A full-stack RTOS-inspired TUI shell integrating the best components from 30 days of Python challenges.

```
  ██████╗ ██████╗  ██████╗ █████╗  ██████╗ ███████╗
 ██╔═══██╗██╔══██╗██╔════╝██╔══██╗██╔═══██╗██╔════╝
 ██║   ██║██████╔╝██║     ███████║██║   ██║███████╗
 ██║   ██║██╔══██╗██║     ██╔══██║██║   ██║╚════██║
 ╚██████╔╝██║  ██║╚██████╗██║  ██║╚██████╔╝███████║
  ╚═════╝ ╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝
  v1.0  ·  The Capstone
```

---

## What it does

OrcaOS is a unified command shell that wires 30 days of hardware-adjacent Python into one running system. It models an RTOS in software — ISR threads push data into queues, a scheduler drains them on every tick, and four live panels display the results in a Textual TUI.

### Four panels, always live

| Panel | Source project | What you see |
|---|---|---|
| **GESTURE** | VolumeKnuckle, BlinkLock | Hand pose (FIST / OPEN / POINT / PINCH), value bar, FPS |
| **AUDIO** | AudioScope, EchoKiller | 16-band FFT spectrum, RMS level bar, dBFS reading |
| **SYSTEM** | All prior projects | CPU %, RAM %, session uptime |
| **LLM** | EdgeAgent | Streaming ollama responses to anything you type |

### Command input
Type any prompt at `orca>` and it streams through your local ollama model. Built-in commands:

| Command | Action |
|---|---|
| `status` | Ask the LLM for a one-sentence system health assessment |
| `model <name>` | Switch ollama model on the fly |
| `clear` | Clear the LLM response buffer |
| `quit` / `exit` / `q` | Shut down cleanly |

---

## How it works

```
Webcam ──► GestureISR (thread) ──► gesture_queue ──┐
Mic    ──► AudioISR   (thread) ──► audio_queue   ──┤
psutil ──► SysISR     (thread) ──► sys_queue     ──┤
                                                    ▼
                                          OrcaScheduler (50 ms tick)
                                          drains queues → updates panels
                                                    │
                                   ┌────────────────┼────────────────┐
                                   ▼                ▼                ▼
                             GesturePanel     AudioPanel       SysPanel
                                                    +
                             LLMTask (thread) ──► llm_queue ──► LLMPanel
```

The architecture mirrors embedded RTOS concepts:

| RTOS concept | OrcaOS equivalent |
|---|---|
| ISR | Background thread reading sensor data |
| Queue | `threading.Queue` per channel |
| Scheduler | `set_interval(0.05, scheduler.tick)` |
| Task | Handler function invoked when queue has data |
| Firmware | `python orcaos.py` — single command boot |

---

## Requirements

- Python 3.11+
- Windows 10/11
- [ollama](https://ollama.ai) installed and running (`ollama serve`)
- Webcam (optional — `--no-gesture` to skip)
- Microphone (optional — `--no-audio` to skip)

### Python packages

```
textual>=0.52.0
psutil>=5.9.0
opencv-python>=4.8.0
mediapipe>=0.10.0
pyaudio>=0.2.13
numpy>=1.24.0
```

---

## Setup

```bash
git clone https://github.com/yourusername/orcaos
cd orcaos
pip install -r requirements.txt
```

Pull a model for ollama (if you haven't):
```bash
ollama pull llama3.2
```

---

## Usage

```bash
# Full mode — webcam + mic + LLM
python orcaos.py

# No webcam (no MediaPipe)
python orcaos.py --no-gesture

# No mic (no PyAudio)
python orcaos.py --no-audio

# Pure headless — SysPanel + LLM only
python orcaos.py --headless
```

### Keyboard bindings

| Key | Action |
|---|---|
| `Ctrl+C` | Quit cleanly (stops all ISR threads) |
| `Ctrl+L` | Clear LLM panel |
| `Ctrl+G` | Show gesture ISR status |
| `Escape` | Focus command input |

---

## Common fixes

**`pyaudio` install fails on Windows**
```bash
pip install pipwin
pipwin install pyaudio
```

**`mediapipe` import error**
```bash
pip install mediapipe --upgrade
```

**ollama not responding**
```bash
ollama serve   # run in a separate terminal
```

**Textual renders blank**
Run from a real terminal (Windows Terminal or cmd), not Spyder or Jupyter.

---

## Hardware concept

OrcaOS is firmware that runs on your laptop instead of bare metal.

- **Input → Process → Output** with real constraints
- ISR threads model hardware interrupt handlers — they fire continuously and never block the main loop
- The queue model is identical to what you'd write for an RP2040 or STM32 with FreeRTOS
- Panels are the "display actuators" — the software equivalent of LEDs or a servo

### v2.0 bridge — OrcaOS on a Pico

In v2.0, the OrcaOS architecture ports to a Raspberry Pi Pico:

| v1.0 (laptop) | v2.0 (Pico) |
|---|---|
| Webcam → MediaPipe | PIR sensor / ultrasonic |
| PyAudio mic | MEMS microphone (I²S) |
| psutil CPU | Internal ADC / temperature |
| Textual TUI | OLED display (SSD1306) |
| `threading.Queue` | FreeRTOS queue |
| `set_interval` | FreeRTOS `vTaskDelay` |

The queue model stays identical. Only the hardware layer changes.

---

## Integrated projects

| Day | Project | Component in OrcaOS |
|---|---|---|
| 1 | VolumeKnuckle | GestureISR — fist/open/point/pinch detection |
| 2 | BlinkLock | GestureISR — landmark pipeline |
| 8 | EdgeAgent | LLMTask — ollama subprocess streamer |
| 12 | AudioScope | AudioISR — 16-band FFT, RMS |
| 13 | EchoKiller | AudioISR — PyAudio chunk pipeline |
| All | psutil usage | SysISR — CPU / RAM / uptime |

---

## Credits

Built as the Day 30 capstone of **BUILDCORED ORCAS** — 30 days of hardware-adjacent Python, shipping one working project per day.

Challenge attribution: BUILDCORED ORCAS · Day 30 of 30 · Expert tier
