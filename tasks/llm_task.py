"""
OrcaOS — LLMTask
Streams a prompt through ollama (subprocess, same as EdgeAgent pattern).
Pushes token chunks + status to llm_queue.
"""
import subprocess
import threading

import state as _state

DEFAULT_MODEL = "llama3.2"


def _detect_model() -> str:
    """Pick first available model from `ollama list`."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().splitlines()[1:]:  # skip header
            parts = line.split()
            if parts:
                return parts[0]
    except Exception:
        pass
    return DEFAULT_MODEL


def run_prompt(prompt: str, model: str | None = None) -> threading.Thread:
    """
    Launch a background thread that streams ollama response tokens
    into llm_queue. Non-blocking — returns immediately.
    """
    if not model:
        model = _detect_model()

    _state.update_state(llm_thinking=True, llm_model=model, llm_response="")
    try:
        _state.llm_queue.put_nowait({"type": "start", "model": model})
    except Exception:
        pass

    def _stream() -> None:
        try:
            proc = subprocess.Popen(
                ["ollama", "run", model, prompt],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            # Drain stderr on a separate thread to avoid deadlock
            threading.Thread(
                target=lambda: proc.stderr.read(),
                daemon=True,
            ).start()

            full = ""
            for line in proc.stdout:
                full += line
                try:
                    _state.llm_queue.put_nowait({"type": "token", "text": line})
                except Exception:
                    pass

            proc.wait()
            try:
                _state.llm_queue.put_nowait({"type": "done", "text": full})
            except Exception:
                pass
            _state.update_state(llm_thinking=False, llm_response=full)

        except FileNotFoundError:
            msg = "[ollama not found — install from https://ollama.ai]"
            try:
                _state.llm_queue.put_nowait({"type": "error", "text": msg})
            except Exception:
                pass
            _state.update_state(llm_thinking=False, llm_response=msg)
        except Exception as e:
            msg = f"[LLM error: {e}]"
            try:
                _state.llm_queue.put_nowait({"type": "error", "text": msg})
            except Exception:
                pass
            _state.update_state(llm_thinking=False, llm_response=msg)

    t = threading.Thread(target=_stream, daemon=True, name="LLMTask")
    t.start()
    return t
