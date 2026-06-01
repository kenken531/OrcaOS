"""OrcaOS — SysPanel"""
import platform

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


def _bar(val: float, width: int = 14) -> str:
    level = min(int(val / 100 * width), width)
    color = "green" if val < 60 else ("yellow" if val < 85 else "red")
    return f"[{color}]{'█' * level}[/{color}]{'░' * (width - level)}"


def _fmt_uptime(s: int) -> str:
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


class SysPanel(Widget):
    DEFAULT_CSS = """
    SysPanel {
        border: solid $primary-darken-2;
        height: 100%;
        padding: 0 1;
    }
    """

    cpu    = reactive(0.0)
    ram    = reactive(0.0)
    uptime = reactive(0)

    # Cached at class level — these never change at runtime
    _OS_NAME = platform.system()
    _NODE    = platform.node()[:12]

    def compose(self) -> ComposeResult:
        yield Static(id="sys-content")

    def _render_content(self) -> str:
        lines = [
            " [bold cyan]SYSTEM[/bold cyan]           [green]● LIVE[/green]",
            "",
            f"  CPU  {_bar(self.cpu)}  {self.cpu:5.1f}%",
            f"  RAM  {_bar(self.ram)}  {self.ram:5.1f}%",
            f"  UP   {_fmt_uptime(self.uptime)}",
            "",
            f"  [dim]{self._OS_NAME} · {self._NODE}[/dim]",
            "  [dim]psutil · SysISR[/dim]",
        ]
        return "\n".join(lines)

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        self.query_one("#sys-content", Static).update(self._render_content())

    def watch_cpu(self, _):    self._refresh()
    def watch_ram(self, _):    self._refresh()
    def watch_uptime(self, _): self._refresh()
