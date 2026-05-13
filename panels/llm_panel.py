"""OrcaOS — LLMPanel"""
from textual.widget import Widget
from textual.reactive import reactive
from textual.app import ComposeResult
from textual.widgets import Static


SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class LLMPanel(Widget):
    DEFAULT_CSS = """
    LLMPanel {
        border: solid $primary-darken-2;
        height: 100%;
        padding: 0 1;
    }
    LLMPanel #llm-header { height: 3; }
    LLMPanel #llm-body   { height: 1fr; overflow-y: auto; }
    """

    thinking     = reactive(False)
    model        = reactive("—")
    response_buf = reactive("")
    spin_idx     = reactive(0)

    def compose(self) -> ComposeResult:
        yield Static(id="llm-header")
        yield Static(id="llm-body")

    def on_mount(self):
        self._refresh_header()
        self._refresh_body()

    # ── public API called by scheduler ───────────────────────────────────────
    def append_token(self, text: str):
        self.response_buf += text
        self._refresh_body()

    def clear(self):
        self.response_buf = ""
        self._refresh_body()

    # ── rendering ─────────────────────────────────────────────────────────────
    def _refresh_header(self):
        spin = SPINNER[self.spin_idx % len(SPINNER)] if self.thinking else "✓"
        status = (
            f"[yellow]{spin} thinking…[/yellow]"
            if self.thinking
            else "[green]● ready[/green]"
        )
        header = (
            f" [bold cyan]LLM[/bold cyan]  [dim]{self.model}[/dim]"
            f"{'':>4}{status}\n"
            " [dim]EdgeAgent · ollama · LLMTask[/dim]"
        )
        self.query_one("#llm-header", Static).update(header)

    def _refresh_body(self):
        text = self.response_buf or "[dim]  orca> waiting for prompt…[/dim]"
        self.query_one("#llm-body", Static).update(text)

    def watch_thinking(self, _):  self._refresh_header()
    def watch_model(self, _):     self._refresh_header()
    def watch_spin_idx(self, _):  self._refresh_header()
