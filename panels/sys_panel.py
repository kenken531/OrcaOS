"""OrcaOS — SysPanel"""
from textual.widget import Widget
from textual.reactive import reactive
from textual.app import ComposeResult
from textual.widgets import Static
import platform


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

    def compose(self) -> ComposeResult:
        yield Static(id="sys-content")

    def _render_content(self) -> str:
        os_name = platform.system()
        node    = platform.node()[:12]
        lines = [
            " [bold cyan]SYSTEM[/bold cyan]           [green]● LIVE[/green]",
            "",
            f"  CPU  {_bar(self.cpu)}  {self.cpu:5.1f}%",
            f"  RAM  {_bar(self.ram)}  {self.ram:5.1f}%",
            f"  UP   {_fmt_uptime(self.uptime)}",
            "",
            f"  [dim]{os_name} · {node}[/dim]",
            "  [dim]psutil · SysISR[/dim]",
        ]
        return "\n".join(lines)

    def on_mount(self):
        self._refresh()

    def _refresh(self):
        self.query_one("#sys-content", Static).update(self._render_content())

    def watch_cpu(self, _):    self._refresh()
    def watch_ram(self, _):    self._refresh()
    def watch_uptime(self, _): self._refresh()
