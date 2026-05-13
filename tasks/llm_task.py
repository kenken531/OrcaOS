"""
OrcaOS — LLMTask
Streams a prompt through ollama (subprocess, same as EdgeAgent pattern).
Pushes token chunks + status to llm_queue.
"""
import subprocess
import threading
import json

from state import llm_queue, update_state

DEFAULT_MODEL = "llama3.2"


def _detect_model() -> str:
    """Pick first available model from ollama list."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().splitlines()
        for line in lines[1:]:   # skip header
            parts = line.split()
            if parts:
                return parts[0]
    except Exception:
        pass
    return DEFAULT_MODEL


def run_prompt(prompt: str, model: str | None = None):
    """
    Launch a background thread that streams ollama response tokens
    into llm_queue.  Non-blocking — returns immediately.
    """
    if not model:
        model = _detect_model()

    update_state(llm_thinking=True, llm_model=model, llm_response="")
    llm_queue.put_nowait({"type": "start", "model": model})

    def _stream():
        try:
            proc = subprocess.Popen(
                ["ollama", "run", model, prompt],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            # separate thread for stderr to avoid deadlock
            def _drain_err():
                for _ in proc.stderr:
                    pass
            threading.Thread(target=_drain_err, daemon=True).start()

            full = ""
            for line in proc.stdout:
                full += line
                llm_queue.put_nowait({"type": "token", "text": line})

            proc.wait()
            llm_queue.put_nowait({"type": "done", "text": full})
            update_state(llm_thinking=False, llm_response=full)

        except FileNotFoundError:
            msg = "[ollama not found — install from https://ollama.ai]"
            llm_queue.put_nowait({"type": "error", "text": msg})
            update_state(llm_thinking=False, llm_response=msg)
        except Exception as e:
            msg = f"[LLM error: {e}]"
            llm_queue.put_nowait({"type": "error", "text": msg})
            update_state(llm_thinking=False, llm_response=msg)

    t = threading.Thread(target=_stream, daemon=True, name="LLMTask")
    t.start()
    return t
