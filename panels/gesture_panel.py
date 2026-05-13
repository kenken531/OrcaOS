"""OrcaOS — GesturePanel"""
from textual.widget import Widget
from textual.reactive import reactive
from textual.app import ComposeResult
from textual.widgets import Static

GESTURE_ART = {
    "FIST":      "✊",
    "OPEN":      "🖐",
    "POINT":     "👆",
    "PINCH":     "🤏",
    "HOLD":      "🤚",
    "PEACE":     "✌️ ",
    "THUMBS_UP": "👍",
    "NONE":      "·",
}

def _bar(value: float, width: int = 10) -> str:
    level = min(int(value * width), width)
    return "█" * level + "░" * (width - level)

def _vol_bar(volume: float, width: int = 14) -> str:
    if volume < 0:
        return "░" * width + " N/A"
    level = min(int(volume * width), width)
    color = "green" if volume < 0.6 else ("yellow" if volume < 0.85 else "red")
    filled = "█" * level
    empty  = "░" * (width - level)
    return f"[{color}]{filled}[/{color}]{empty} {volume*100:3.0f}%"


class GesturePanel(Widget):
    DEFAULT_CSS = """
    GesturePanel {
        border: solid $primary-darken-2;
        height: 100%;
        padding: 0 1;
    }
    """

    label       = reactive("NONE")
    value       = reactive(0.0)
    fps         = reactive(0.0)
    active      = reactive(False)
    error       = reactive("")
    open_log    = reactive([])
    cam_idx     = reactive(-1)
    backend     = reactive("")
    volume      = reactive(-1.0)
    vol_avail   = reactive(False)
    last_action = reactive("")

    def compose(self) -> ComposeResult:
        yield Static(id="gesture-content")

    def _render_content(self) -> str:
        if self.active:
            # backend badge
            if "MediaPipe" in self.backend:
                be = "[green]MediaPipe[/green]"
            elif self.backend:
                be = "[yellow]OpenCV[/yellow]"
            else:
                be = "[dim]?[/dim]"

            emoji = GESTURE_ART.get(self.label, "·")
            bar   = _bar(self.value)
            vbar  = _vol_bar(self.volume)

            # Gesture-specific hint
            if self.label == "FIST":
                hint = "[cyan]↑↓ move to change vol[/cyan]"
            elif self.label == "PINCH":
                hint = "[yellow]hold 1.5s to lock 🔒[/yellow]"
            else:
                hint = "[dim]FIST=vol  PINCH=lock[/dim]"

            lines = [
                f" [bold cyan]GESTURE[/bold cyan]   [green]● LIVE[/green]  {be}",
                "",
                f"  {emoji}  [bold white]{self.label:<10}[/bold white]",
                f"  conf [{bar}] {self.value:.2f}  {self.fps:.0f}fps",
                "",
                f"  VOL  {vbar}",
                f"  {hint}",
            ]
            if self.last_action:
                lines.append(f"  [dim]{self.last_action[-38:]}[/dim]")

        else:
            err      = (self.error or "camera not opened")[:40]
            log_tail = self.open_log[-2:] if self.open_log else []
            lines = [
                " [bold cyan]GESTURE[/bold cyan]   [red]○ OFFLINE[/red]",
                "",
                f"  [red]{err}[/red]",
            ]
            for entry in log_tail:
                lines.append(f"  [dim]{entry[:40]}[/dim]")
            lines += [
                "",
                "  [dim]pip install mediapipe==0.10.35[/dim]",
                "  [dim]python download_model.py[/dim]",
            ]
        return "\n".join(lines)

    def on_mount(self):
        self._refresh()

    def _refresh(self):
        self.query_one("#gesture-content", Static).update(self._render_content())

    def watch_label(self, _):       self._refresh()
    def watch_value(self, _):       self._refresh()
    def watch_fps(self, _):         self._refresh()
    def watch_active(self, _):      self._refresh()
    def watch_error(self, _):       self._refresh()
    def watch_open_log(self, _):    self._refresh()
    def watch_cam_idx(self, _):     self._refresh()
    def watch_backend(self, _):     self._refresh()
    def watch_volume(self, _):      self._refresh()
    def watch_vol_avail(self, _):   self._refresh()
    def watch_last_action(self, _): self._refresh()