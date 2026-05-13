"""
╔═══════════════════════════════════════════════════════════╗
║  OrcaOS v1.0  —  BUILDCORED ORCAS  Day 30 Capstone       ║
║  Full-stack TUI shell integrating 30 days of components   ║
║  python orcaos.py                                         ║
╚═══════════════════════════════════════════════════════════╝
"""
import sys
import argparse
import threading

# ── path fix so panels/isr/tasks can import each other ───────────────────────
import os
sys.path.insert(0, os.path.dirname(__file__))

# ── Textual ───────────────────────────────────────────────────────────────────
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Static, Label
from textual.containers import Horizontal, Vertical, Container
from textual.binding import Binding

# ── OrcaOS internals ─────────────────────────────────────────────────────────
import state as _state
from scheduler import OrcaScheduler
from panels.gesture_panel import GesturePanel
from panels.audio_panel   import AudioPanel
from panels.sys_panel     import SysPanel
from panels.llm_panel     import LLMPanel


# ─────────────────────────────────────────────────────────────────────────────
BANNER = """\
[bold cyan]
  ██████╗ ██████╗  ██████╗ █████╗  ██████╗ ███████╗
 ██╔═══██╗██╔══██╗██╔════╝██╔══██╗██╔═══██╗██╔════╝
 ██║   ██║██████╔╝██║     ███████║██║   ██║███████╗
 ██║   ██║██╔══██╗██║     ██╔══██║██║   ██║╚════██║
 ╚██████╔╝██║  ██║╚██████╗██║  ██║╚██████╔╝███████║
  ╚═════╝ ╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝[/bold cyan]
[dim]  v1.0  ·  BUILDCORED ORCAS Day 30  ·  The Capstone[/dim]
"""


# ─────────────────────────────────────────────────────────────────────────────
class OrcaOS(App):
    """OrcaOS — RTOS-inspired TUI shell."""

    CSS = """
    Screen {
        background: $background;
    }

    #banner {
        height: 9;
        content-align: center middle;
        border-bottom: solid $primary-darken-3;
        padding: 0 2;
    }

    #top-row {
        height: 12;
        margin: 0;
    }

    #bottom-row {
        height: 12;
        margin: 0;
    }

    GesturePanel, AudioPanel, SysPanel {
        width: 1fr;
    }

    LLMPanel {
        width: 2fr;
    }

    #llm-full {
        width: 1fr;
        height: 1fr;
    }

    #cmd-row {
        height: 3;
        border-top: solid $primary-darken-3;
        padding: 0 1;
        align: left middle;
    }

    #cmd-label {
        width: 10;
        color: $accent;
    }

    #cmd-input {
        width: 1fr;
        border: none;
        background: $background;
        color: $text;
    }

    #status-bar {
        height: 1;
        background: $primary-darken-3;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit",        "Quit"),
        Binding("ctrl+l", "clear_llm",   "Clear LLM"),
        Binding("ctrl+g", "toggle_gesture", "Toggle Gesture"),
        Binding("escape", "focus_input", "Focus input"),
    ]

    TITLE    = "OrcaOS v1.0"
    SUB_TITLE = "BUILDCORED ORCAS · Day 30 Capstone"

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def __init__(self, no_gesture: bool = False, no_audio: bool = False,
                 camera_index: int = 0, **kwargs):
        super().__init__(**kwargs)
        self.no_gesture   = no_gesture
        self.no_audio     = no_audio
        self.camera_index = camera_index
        self._stop        = threading.Event()
        self._scheduler   = OrcaScheduler(self)
        self._isr_threads: list[threading.Thread] = []

    @property
    def gesture_panel(self) -> GesturePanel:
        return self.query_one(GesturePanel)

    @property
    def audio_panel(self) -> AudioPanel:
        return self.query_one(AudioPanel)

    @property
    def sys_panel(self) -> SysPanel:
        return self.query_one(SysPanel)

    @property
    def llm_panel(self) -> LLMPanel:
        return self.query_one(LLMPanel)

    # ── compose ───────────────────────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        yield Static(BANNER, id="banner", markup=True)

        with Horizontal(id="top-row"):
            yield GesturePanel()
            yield AudioPanel()
            yield SysPanel()

        with Horizontal(id="bottom-row"):
            yield LLMPanel()

        with Horizontal(id="cmd-row"):
            yield Label("  orca> ", id="cmd-label")
            yield Input(placeholder="ask the LLM, or type a command…", id="cmd-input")

        yield Static("", id="status-bar")
        yield Footer()

    # ── mount: start ISRs ─────────────────────────────────────────────────────
    def on_mount(self):
        # always-on ISRs
        import isr.sys_isr as sys_isr
        self._isr_threads.append(sys_isr.start(self._stop))

        if not self.no_audio:
            import isr.audio_isr as audio_isr
            self._isr_threads.append(audio_isr.start(self._stop))
        else:
            _state.update_state(audio_active=False)

        if not self.no_gesture:
            import isr.gesture_isr as gesture_isr
            self._isr_threads.append(gesture_isr.start(self._stop, self.camera_index))
        else:
            _state.update_state(gesture_active=False)

        # scheduler tick every 50 ms
        self.set_interval(0.05, self._scheduler.tick)

        # status bar update every second
        self.set_interval(1.0, self._update_status)

        self.query_one("#cmd-input").focus()

    # ── status bar ────────────────────────────────────────────────────────────
    def _update_status(self):
        g  = "G:[green]ON[/green]"  if _state.read_state("gesture_active") else "G:[red]OFF[/red]"
        a  = "A:[green]ON[/green]"  if _state.read_state("audio_active")   else "A:[red]OFF[/red]"
        llm_s = "[yellow]LLM:thinking[/yellow]" if _state.read_state("llm_thinking") else "LLM:[green]ready[/green]"
        cpu = _state.read_state("cpu_percent", 0.0)
        up  = _state.read_state("uptime_s", 0)
        h, r = divmod(up, 3600); m, s = divmod(r, 60)
        bar = f"  {g}  {a}  {llm_s}  │  CPU {cpu:.0f}%  │  UP {h:02d}:{m:02d}:{s:02d}  │  threads: {threading.active_count()}"
        self.query_one("#status-bar", Static).update(bar)

    # ── input handling ────────────────────────────────────────────────────────
    def on_input_submitted(self, event: Input.Submitted):
        prompt = event.value.strip()
        if not prompt:
            return
        event.input.clear()

        # built-in commands
        if prompt.lower() in ("exit", "quit", "q"):
            self.action_quit()
            return
        if prompt.lower() == "clear":
            self.action_clear_llm()
            return
        if prompt.lower() == "status":
            self._push_status_to_llm()
            return
        if prompt.lower().startswith("model "):
            model = prompt.split(None, 1)[1]
            self._run_llm(prompt=f"Hello, confirm you are {model} in one sentence.", model=model)
            return

        # default → send to LLM
        self._run_llm(prompt)

    def _run_llm(self, prompt: str, model: str | None = None):
        from tasks.llm_task import run_prompt
        run_prompt(prompt, model=model)

    def _push_status_to_llm(self):
        cpu = _state.read_state("cpu_percent", 0)
        ram = _state.read_state("ram_percent", 0)
        g   = _state.read_state("gesture_label", "—")
        self._run_llm(
            f"OrcaOS status check: CPU {cpu:.0f}%, RAM {ram:.0f}%, "
            f"last gesture={g}. Give a one-sentence system health assessment."
        )

    # ── actions ───────────────────────────────────────────────────────────────
    def action_clear_llm(self):
        self.llm_panel.clear()

    def action_toggle_gesture(self):
        # just shows current state in LLM panel — full restart out of scope
        active = _state.read_state("gesture_active", False)
        self.llm_panel.append_token(
            f"\n[dim][gesture ISR is {'active' if active else 'offline'}][/dim]\n"
        )

    def action_focus_input(self):
        self.query_one("#cmd-input").focus()

    # ── shutdown ──────────────────────────────────────────────────────────────
    def on_unmount(self):
        self._stop.set()
        for t in self._isr_threads:
            t.join(timeout=2.0)


# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="OrcaOS — BUILDCORED ORCAS Day 30")
    parser.add_argument("--no-gesture", action="store_true", help="Disable GestureISR (no webcam needed)")
    parser.add_argument("--no-audio",   action="store_true", help="Disable AudioISR  (no mic needed)")
    parser.add_argument("--headless",   action="store_true", help="No-hardware mode  (implies both above)")
    parser.add_argument("--camera",     type=int, default=0,  help="Camera index to use (default 0). Try 1 or 2 if 0 fails.")
    args = parser.parse_args()

    no_gesture = args.no_gesture or args.headless
    no_audio   = args.no_audio   or args.headless

    app = OrcaOS(no_gesture=no_gesture, no_audio=no_audio, camera_index=args.camera)
    app.run()


if __name__ == "__main__":
    main()
