"""
OrcaOS — AudioISR
Captures mic chunks via PyAudio, computes RMS level + 16-band FFT,
pushes to audio_queue.  Gracefully no-ops if PyAudio / mic unavailable.
"""
import threading
import math

from state import audio_queue, update_state

CHUNK      = 1024
RATE       = 44100
N_BARS     = 16
CHANNELS   = 1

# ── attempt PyAudio import ────────────────────────────────────────────────────
try:
    import pyaudio
    _PYAUDIO_OK = True
except ImportError:
    _PYAUDIO_OK = False


def _rms(samples):
    if not samples:
        return 0.0
    sq = sum(s * s for s in samples)
    return math.sqrt(sq / len(samples)) / 32768.0


def _fft_bars(samples, n_bars=N_BARS):
    """Rough n_bars power-spectrum estimate using real FFT."""
    try:
        import array as arr
        n = len(samples)
        if n == 0:
            return [0.0] * n_bars
        # Cooley-Tukey not available without numpy; use magnitude approx
        # If numpy is available use it, else degrade to RMS blocks
        try:
            import numpy as np
            windowed = np.array(samples, dtype=np.float32) * np.hanning(n)
            spectrum = np.abs(np.fft.rfft(windowed))
            half     = len(spectrum)
            bar_size = max(1, half // n_bars)
            bars = []
            for i in range(n_bars):
                chunk = spectrum[i * bar_size: (i + 1) * bar_size]
                mag   = float(np.mean(chunk)) / (32768 * 0.5) if len(chunk) else 0.0
                bars.append(min(1.0, mag * 4))
            return bars
        except ImportError:
            # numpy unavailable — split into RMS blocks
            step = n // n_bars
            bars = []
            for i in range(n_bars):
                blk = samples[i * step: (i + 1) * step]
                bars.append(min(1.0, _rms(blk) * 6))
            return bars
    except Exception:
        return [0.0] * n_bars


def _audio_loop(stop_event: threading.Event):
    if not _PYAUDIO_OK:
        update_state(audio_active=False)
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
        update_state(audio_active=True)

        while not stop_event.is_set():
            try:
                raw     = stream.read(CHUNK, exception_on_overflow=False)
                import struct
                samples = list(struct.unpack(f"{CHUNK}h", raw))
                rms     = _rms(samples)
                bars    = _fft_bars(samples)
                peak    = max(bars) if bars else 0.0

                audio_queue.put_nowait({
                    "audio_rms":  rms,
                    "audio_fft":  bars,
                    "audio_peak": peak,
                })
            except Exception:
                pass

    except Exception as e:
        update_state(audio_active=False)
    finally:
        try:
            if stream:
                stream.stop_stream()
                stream.close()
            if pa:
                pa.terminate()
        except Exception:
            pass


def start(stop_event: threading.Event):
    t = threading.Thread(target=_audio_loop, args=(stop_event,), daemon=True, name="AudioISR")
    t.start()
    return t
