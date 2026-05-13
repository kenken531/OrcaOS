"""OrcaOS — AudioPanel"""
from textual.widget import Widget
from textual.reactive import reactive
from textual.app import ComposeResult
from textual.widgets import Static

_BAR_BLOCKS = " ▁▂▃▄▅▆▇█"

def _fft_display(bars: list, width: int = 16) -> str:
    """Render FFT bars as a single-line ASCII spectrum."""
    out = []
    for b in bars[:width]:
        idx = min(int(b * (len(_BAR_BLOCKS) - 1)), len(_BAR_BLOCKS) - 1)
        out.append(_BAR_BLOCKS[idx])
    return "".join(out)

def _level_bar(rms: float, width: int = 20) -> str:
    level = min(int(rms * width), width)
    color = "green" if rms < 0.5 else ("yellow" if rms < 0.8 else "red")
    return f"[{color}]{'█' * level}[/{color}]{'░' * (width - level)}"


class AudioPanel(Widget):
    DEFAULT_CSS = """
    AudioPanel {
        border: solid $primary-darken-2;
        height: 100%;
        padding: 0 1;
    }
    """

    rms    = reactive(0.0)
    fft    = reactive([])
    peak   = reactive(0.0)
    active = reactive(False)

    def compose(self) -> ComposeResult:
        yield Static(id="audio-content")

    def _render_content(self) -> str:
        status = "[green]● LIVE[/green]" if self.active else "[red]○ OFFLINE[/red]"
        fft_line  = _fft_display(self.fft if self.fft else [0.0] * 16)
        level_bar = _level_bar(self.rms)
        db = 20 * __import__("math").log10(max(self.rms, 1e-6))

        lines = [
            f" [bold cyan]AUDIO[/bold cyan]            {status}",
            "",
            f"  FFT  [yellow]{fft_line}[/yellow]",
            f"  RMS  {level_bar}",
            f"  peak {self.peak:.3f}   {db:+.1f} dBFS",
            "",
            "  [dim]AudioScope / EchoKiller[/dim]",
            "  [dim]PyAudio 44100 Hz · ISR[/dim]",
        ]
        return "\n".join(lines)

    def on_mount(self):
        self._refresh()

    def _refresh(self):
        self.query_one("#audio-content", Static).update(self._render_content())

    def watch_rms(self, _):    self._refresh()
    def watch_fft(self, _):    self._refresh()
    def watch_peak(self, _):   self._refresh()
    def watch_active(self, _): self._refresh()
