"""
OrcaOS — AudioISR
Captures mic chunks via PyAudio, computes RMS level + 16-band FFT,
pushes to audio_queue. Gracefully no-ops if PyAudio / mic unavailable.
"""
import math
import struct
import threading

import state as _state

CHUNK    = 1024
RATE     = 44100
N_BARS   = 16
CHANNELS = 1

try:
    import pyaudio
    _PYAUDIO_OK = True
except ImportError:
    _PYAUDIO_OK = False

try:
    import numpy as np
    _NUMPY_OK = True
except ImportError:
    _NUMPY_OK = False


def _rms(samples: list[int]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768.0


def _fft_bars(samples: list[int], n_bars: int = N_BARS) -> list[float]:
    """Return n_bars normalised power-spectrum magnitudes (0–1)."""
    n = len(samples)
    if n == 0:
        return [0.0] * n_bars

    if _NUMPY_OK:
        windowed = np.array(samples, dtype=np.float32) * np.hanning(n)
        spectrum  = np.abs(np.fft.rfft(windowed))
        half      = len(spectrum)
        bar_size  = max(1, half // n_bars)
        bars: list[float] = []
        for i in range(n_bars):
            chunk = spectrum[i * bar_size : (i + 1) * bar_size]
            mag   = float(np.mean(chunk)) / (32768 * 0.5) if len(chunk) else 0.0
            bars.append(min(1.0, mag * 4))
        return bars

    # numpy unavailable — split into RMS blocks
    step = max(1, n // n_bars)
    return [min(1.0, _rms(samples[i * step : (i + 1) * step]) * 6) for i in range(n_bars)]


def _audio_loop(stop_event: threading.Event) -> None:
    if not _PYAUDIO_OK:
        _state.update_state(audio_active=False)
        return

    pa = None
    stream = None
    try:
        pa     = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )
        _state.update_state(audio_active=True)

        while not stop_event.is_set():
            try:
                raw     = stream.read(CHUNK, exception_on_overflow=False)
                samples = list(struct.unpack(f"{CHUNK}h", raw))
                rms     = _rms(samples)
                bars    = _fft_bars(samples)
                peak    = max(bars) if bars else 0.0
                _state.audio_queue.put_nowait({
                    "audio_rms":  rms,
                    "audio_fft":  bars,
                    "audio_peak": peak,
                })
            except Exception:
                pass

    except Exception:
        _state.update_state(audio_active=False)
    finally:
        try:
            if stream:
                stream.stop_stream()
                stream.close()
            if pa:
                pa.terminate()
        except Exception:
            pass


def start(stop_event: threading.Event) -> threading.Thread:
    t = threading.Thread(
        target=_audio_loop, args=(stop_event,),
        daemon=True, name="AudioISR"
    )
    t.start()
    return t
