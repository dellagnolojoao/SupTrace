import ctypes
import sys

# ✅ ELEVAÇÃO DE PRIVILÉGIOS – deve ser o primeiro bloco executado
def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def _elevar() -> None:
    params = " ".join(f'"{a}"' for a in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    sys.exit(0)

if not _is_admin():
    _elevar()

# ─────────────────────────────────────────────────────────────────────────────
import os

_PW_BROWSERS_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "SupTrace", "pw-browsers",
)
os.makedirs(_PW_BROWSERS_PATH, exist_ok=True)
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _PW_BROWSERS_PATH

_APP_TMP_ROOT = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "SupTrace", "tmp",
)
os.makedirs(_APP_TMP_ROOT, exist_ok=True)
os.environ["TEMP"] = _APP_TMP_ROOT
os.environ["TMP"]  = _APP_TMP_ROOT
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import threading
import shutil
import tempfile
import time
import zipfile
import json
import html as html_lib
import subprocess
import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime
from urllib.parse import urlparse
from playwright.async_api import async_playwright

# ─── ffmpeg via imageio-ffmpeg ───────────────────────────────────────────────
try:
    import imageio_ffmpeg
    FFMPEG_EXE: str | None = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_EXE = None

# ─── Configurações ────────────────────────────────────────────────────────────
OUTPUT_DIR     = r"C:\Temp"
VIDEO_SPEED    = 1.5
VIDEO_W        = 1920
VIDEO_H        = 1080
HAR_SKIP_TYPES = {"image", "stylesheet", "script", "font", "media", "manifest", "ping"}

_CREATE_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

_LIBVPX_FAST_ARGS = [
    "-c:v", "libvpx",
    "-deadline", "realtime",
    "-cpu-used", "8",
    "-crf", "18",
    "-b:v", "0",
]

_CHROME_PATHS: list[str] = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
]

_EDGE_PATHS: list[str] = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

C = {
    "dark":    "#1a1a2e",
    "bg":      "#f5f6fa",
    "white":   "#ffffff",
    "green":   "#2dc653",
    "green_h": "#25a244",
    "red":     "#e63946",
    "red_h":   "#c1121f",
    "blue":    "#3a86ff",
    "orange":  "#fb8500",
    "gray":    "#adb5bd",
    "subtext": "#6c757d",
    "dis_bg":  "#ced4da",
    "dis_fg":  "#868e96",
    "warn_bg": "#fff3cd",
    "warn_fg": "#856404",
}

# ─────────────────────────────────────────────────────────────────────────────

def _safe_rmtree(path: str, tentativas: int = 5, espera: float = 0.6) -> bool:
    if not path or not os.path.isdir(path):
        return True
    for tentativa in range(tentativas):
        try:
            shutil.rmtree(path)
            return True
        except Exception:
            if tentativa < tentativas - 1:
                time.sleep(espera)
    return False


def _limpar_temporarios_orfaos() -> None:
    try:
        for nome in os.listdir(_APP_TMP_ROOT):
            if nome.startswith("gravador_suporte_"):
                _safe_rmtree(os.path.join(_APP_TMP_ROOT, nome), tentativas=1)
    except Exception:
        pass


def _detectar_canal_browser() -> tuple[str, str] | tuple[None, None]:
    for path in _CHROME_PATHS:
        if os.path.exists(path):
            return "chrome", "Google Chrome"
    for path in _EDGE_PATHS:
        if os.path.exists(path):
            return "msedge", "Microsoft Edge"
    return None, None


def _fmt_size(size_bytes: int) -> str:
    """Tamanho legível para humanos."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024 ** 2:.1f} MB"
    else:
        return f"{size_bytes / 1024 ** 3:.2f} GB"


def _setup_ffmpeg_para_playwright() -> None:
    if not getattr(sys, "frozen", False):
        return
    if not FFMPEG_EXE or not os.path.exists(FFMPEG_EXE):
        return
    base = getattr(sys, "_MEIPASS", "")
    if not base:
        return
    candidates = [
        os.path.join(base, "playwright", "driver", "package", "browsers.json"),
        os.path.join(base, "playwright", "driver", "browsers.json"),
    ]
    browsers_json = next((p for p in candidates if os.path.exists(p)), None)
    if not browsers_json:
        return
    try:
        with open(browsers_json, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    revision = None
    for browser in data.get("browsers", []):
        if browser.get("name") == "ffmpeg":
            revision = browser.get("revision")
            break
    if not revision:
        return
    target_dir = os.path.join(_PW_BROWSERS_PATH, f"ffmpeg-{revision}")
    target_exe = os.path.join(target_dir, "ffmpeg-win64.exe")
    if not os.path.exists(target_exe):
        try:
            os.makedirs(target_dir, exist_ok=True)
            shutil.copy2(FFMPEG_EXE, target_exe)
        except Exception:
            pass


_setup_ffmpeg_para_playwright()


# ─────────────────────────────────────────────────────────────────────────────

class GravadorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SupTrace v1.3")
        self.root.resizable(False, False)
        self.root.configure(bg=C["bg"])

        WIN_W, WIN_H = 480, 400
        self.root.update_idletasks()
        self._screen_w: int = self.root.winfo_screenwidth()
        self._screen_h: int = self.root.winfo_screenheight()
        x = (self._screen_w - WIN_W) // 2
        y = (self._screen_h - WIN_H) // 2
        self.root.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

        # ── Playwright state
        self._loop: asyncio.AbstractEventLoop | None = None
        self._playwright = None
        self._browser    = None
        self._context    = None
        self._page       = None
        # ✅ Multi-tab: lista de todas as pages rastreadas
        self._pages: list = []
        self._gravando: bool = False
        self._salvando: bool = False
        self._stop_event = threading.Event()

        # ── File paths
        self._tmp_dir:   str = ""
        self._har_path:  str = ""
        self._video_dir: str = ""

        # ── Processing window refs
        self._proc_win: tk.Toplevel | None = None
        self._proc_lbl: tk.Label | None = None
        self._progress_var: tk.IntVar | None = None
        self._progress_pct_lbl: tk.Label | None = None
        self._proc_step_lbl: tk.Label | None = None

        # ── Timer / blink
        self._recording_start: datetime | None = None
        self._timer_id: str | None = None
        self._blink_state: bool = True

        # ── Dynamic UI refs
        self._tab_count_lbl: tk.Label | None = None

        self._canal_browser, self._nome_browser = _detectar_canal_browser()

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        _limpar_temporarios_orfaos()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=C["dark"], height=78)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)

        hdr_left = tk.Frame(hdr, bg=C["dark"])
        hdr_left.pack(side=tk.LEFT, padx=20, fill=tk.Y)

        tk.Label(
            hdr_left, text="⏺  SupTrace",
            bg=C["dark"], fg=C["white"],
            font=("Segoe UI", 17, "bold"),
        ).pack(anchor="w", pady=(12, 2))

        badge_color = C["green"] if self._canal_browser else C["red"]
        badge_text  = (
            f"🌐  Navegador: {self._nome_browser}"
            if self._canal_browser
            else "⚠️  Nenhum navegador homologado encontrado"
        )
        tk.Label(
            hdr_left, text=badge_text,
            bg=C["dark"], fg=badge_color,
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w")

        # Versão alinhada à direita no header
        tk.Label(
            hdr, text="v1.3",
            bg=C["dark"], fg=C["gray"],
            font=("Segoe UI", 8),
        ).pack(side=tk.RIGHT, padx=16, pady=8, anchor="ne")

        # ── Body ──────────────────────────────────────────────────────────────
        body = tk.Frame(self.root, bg=C["bg"])
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            body,
            text="Grave a tela e as requisições de rede para diagnóstico do suporte.",
            bg=C["bg"], fg=C["subtext"],
            font=("Segoe UI", 9, "bold"), wraplength=420,
        ).pack(pady=(14, 4))

        # ✅ Contador de abas (oculto em repouso, atualizado durante gravação)
        self._tab_count_lbl = tk.Label(
            body, text="",
            bg=C["bg"], fg=C["blue"],
            font=("Segoe UI", 9),
        )
        self._tab_count_lbl.pack(pady=(0, 4))

        # Alerta de navegador ausente
        if not self._canal_browser:
            alerta = tk.Frame(body, bg=C["warn_bg"], padx=12, pady=8)
            alerta.pack(fill=tk.X, padx=24, pady=(0, 8))
            tk.Label(
                alerta,
                text=(
                    "O SupTrace requer o Google Chrome ou o Microsoft Edge instalado.\n"
                    "Instale um dos navegadores e reinicie a aplicação."
                ),
                bg=C["warn_bg"], fg=C["warn_fg"],
                font=("Segoe UI", 9), wraplength=400, justify=tk.LEFT,
            ).pack(anchor="w")

        # Botão Iniciar
        self.btn_iniciar = tk.Button(
            body, text="⏺   Iniciar Gravação",
            command=self.iniciar_fluxo,
            bg=C["green"] if self._canal_browser else C["dis_bg"],
            fg=C["white"]  if self._canal_browser else C["dis_fg"],
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT, cursor="hand2",
            pady=10, width=28, bd=0,
            state=tk.NORMAL if self._canal_browser else tk.DISABLED,
            activebackground=C["green_h"],
            activeforeground=C["white"],
        )
        self.btn_iniciar.pack(pady=(0, 8))
        if self._canal_browser:
            self._bind_hover(self.btn_iniciar, C["green"], C["green_h"])

        # Botão Parar
        self.btn_parar = tk.Button(
            body, text="⏹   Salvar e Fechar",
            command=self.parar_fluxo,
            bg=C["dis_bg"], fg=C["dis_fg"],
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT, cursor="hand2",
            pady=10, width=28, bd=0,
            state=tk.DISABLED,
            activebackground=C["red_h"],
            activeforeground=C["white"],
        )
        self.btn_parar.pack(pady=(0, 6))
        self._bind_hover(self.btn_parar, C["red"], C["red_h"])

        # ✅ Dica de atalho de teclado
        tk.Label(
            body,
            text="Dica: pressione  Esc  para encerrar a gravação",
            bg=C["bg"], fg=C["gray"],
            font=("Segoe UI", 8),
        ).pack(pady=(0, 10))
        self.root.bind("<Escape>", lambda _: self.parar_fluxo())

        # ── Card de diretório ─────────────────────────────────────────────────
        dir_outer = tk.Frame(body, bg=C["white"])
        dir_outer.pack(fill=tk.X, padx=24)
        tk.Frame(dir_outer, bg=C["dark"], width=5).pack(side=tk.LEFT, fill=tk.Y)

        dir_inner = tk.Frame(dir_outer, bg=C["white"])
        dir_inner.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, pady=10)

        tk.Label(
            dir_inner, text="📁  Arquivos salvos em:",
            bg=C["white"], fg=C["subtext"],
            font=("Segoe UI", 8, "bold"), anchor="w",
        ).pack(fill=tk.X)

        dir_row = tk.Frame(dir_inner, bg=C["white"])
        dir_row.pack(fill=tk.X, pady=(2, 0))

        self.lbl_dir = tk.Label(
            dir_row, text=OUTPUT_DIR,
            bg=C["white"], fg=C["dark"],
            font=("Segoe UI", 9, "bold"),
            anchor="w", cursor="hand2",
        )
        self.lbl_dir.pack(side=tk.LEFT)

        lbl_open = tk.Label(
            dir_row, text="  ↗ abrir",
            bg=C["white"], fg=C["blue"],
            font=("Segoe UI", 8, "underline"),
            cursor="hand2",
        )
        lbl_open.pack(side=tk.LEFT)

        for w in (self.lbl_dir, lbl_open, dir_row):
            w.bind("<Button-1>", lambda _: os.startfile(OUTPUT_DIR))

        # ── Status Bar ────────────────────────────────────────────────────────
        sbar = tk.Frame(self.root, bg=C["dark"], height=32)
        sbar.pack(fill=tk.X, side=tk.BOTTOM)
        sbar.pack_propagate(False)

        sbar_in = tk.Frame(sbar, bg=C["dark"])
        sbar_in.pack(side=tk.LEFT, padx=14, fill=tk.Y)

        self._dot_cv = tk.Canvas(
            sbar_in, width=10, height=10,
            bg=C["dark"], highlightthickness=0,
        )
        self._dot_cv.pack(side=tk.LEFT, pady=11, padx=(0, 7))
        self._dot = self._dot_cv.create_oval(1, 1, 9, 9, fill=C["gray"], outline="")

        self.lbl_status = tk.Label(
            sbar_in,
            text="Pronto para iniciar" if self._canal_browser else "Navegador não encontrado",
            bg=C["dark"],
            fg=C["gray"] if self._canal_browser else C["red"],
            font=("Segoe UI", 9),
        )
        self.lbl_status.pack(side=tk.LEFT)

    # ─── Helpers de UI ────────────────────────────────────────────────────────

    @staticmethod
    def _bind_hover(btn: tk.Button, normal: str, hover: str) -> None:
        btn.bind("<Enter>", lambda _: btn.config(bg=hover)  if btn.cget("state") == tk.NORMAL else None)
        btn.bind("<Leave>", lambda _: btn.config(bg=normal) if btn.cget("state") == tk.NORMAL else None)

    def _btn_enable(self, btn: tk.Button, color: str) -> None:
        btn.config(state=tk.NORMAL, bg=color, fg=C["white"])

    def _btn_disable(self, btn: tk.Button) -> None:
        btn.config(state=tk.DISABLED, bg=C["dis_bg"], fg=C["dis_fg"])

    def _set_status(self, text: str, color: str = "gray") -> None:
        dot_map = {
            "gray":   C["gray"],
            "blue":   C["blue"],
            "red":    C["red"],
            "green":  C["green"],
            "orange": C["orange"],
        }
        clr = dot_map.get(color, C["gray"])
        def _upd():
            self.lbl_status.config(text=text, fg=clr)
            self._dot_cv.itemconfig(self._dot, fill=clr)
        self.root.after(0, _upd)

    def _set_progress(self, value: int, step_text: str) -> None:
        """Atualiza a barra de progresso determinística de qualquer thread (thread-safe)."""
        def _upd():
            if self._progress_var is not None:
                self._progress_var.set(value)
            if self._progress_pct_lbl is not None:
                try:
                    self._progress_pct_lbl.config(text=f"{value}%")
                except Exception:
                    pass
            if self._proc_step_lbl is not None:
                try:
                    self._proc_step_lbl.config(text=step_text)
                except Exception:
                    pass
        self.root.after(0, _upd)

    # ─── Janela de processamento ──────────────────────────────────────────────

    def _mostrar_janela_processando(self, titulo: str) -> None:
        if self._proc_win is not None:
            return

        win = tk.Toplevel(self.root)
        win.title("Gerando pacote de suporte...")
        win.configure(bg=C["white"])
        win.resizable(False, False)
        win.transient(self.root)
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", self._bloquear_fechamento_processando)

        WIN_W, WIN_H = 460, 220
        x = (self._screen_w - WIN_W) // 2
        y = (self._screen_h - WIN_H) // 2
        win.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

        tk.Label(
            win, text="⏳  Gerando o pacote de suporte...",
            bg=C["white"], fg=C["dark"],
            font=("Segoe UI", 11, "bold"),
        ).pack(pady=(18, 2))

        # Descrição (qtd de vídeos + HAR)
        self._proc_lbl = tk.Label(
            win, text=titulo,
            bg=C["white"], fg=C["subtext"],
            font=("Segoe UI", 9),
        )
        self._proc_lbl.pack(pady=(0, 10))

        # ✅ Barra determinística com percentual
        self._progress_var = tk.IntVar(value=0)
        barra = ttk.Progressbar(
            win, mode="determinate", length=400,
            variable=self._progress_var, maximum=100,
        )
        barra.pack(padx=28, pady=(0, 4))

        # Linha de percentual + descrição da etapa
        pct_row = tk.Frame(win, bg=C["white"])
        pct_row.pack(fill=tk.X, padx=30)

        self._progress_pct_lbl = tk.Label(
            pct_row, text="0%",
            bg=C["white"], fg=C["dark"],
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self._progress_pct_lbl.pack(side=tk.LEFT)

        self._proc_step_lbl = tk.Label(
            pct_row, text="Iniciando...",
            bg=C["white"], fg=C["subtext"],
            font=("Segoe UI", 8),
            anchor="e",
        )
        self._proc_step_lbl.pack(side=tk.RIGHT)

        # Separador
        tk.Frame(win, bg=C["gray"], height=1).pack(fill=tk.X, padx=28, pady=(14, 8))

        tk.Label(
            win, text="⚠️  Não feche o aplicativo até esta janela desaparecer.",
            bg=C["white"], fg=C["red"],
            font=("Segoe UI", 8, "bold"),
        ).pack()

        win.grab_set()
        self._proc_win = win

    def _fechar_janela_processando(self) -> None:
        if self._proc_win is not None:
            try:
                self._proc_win.grab_release()
                self._proc_win.destroy()
            except Exception:
                pass
            self._proc_win      = None
            self._proc_lbl      = None
            self._progress_var  = None
            self._progress_pct_lbl = None
            self._proc_step_lbl = None

    def _bloquear_fechamento_processando(self) -> None:
        messagebox.showwarning(
            "Aguarde",
            "O pacote ainda está sendo gerado.\n"
            "Feche esta janela apenas quando o processo terminar,\n"
            "ou os arquivos serão perdidos.",
            parent=self._proc_win,
        )

    # ─── Timer de gravação + blink ────────────────────────────────────────────

    def _elapsed_str(self) -> str:
        if not self._recording_start:
            return "00:00:00"
        elapsed = int((datetime.now() - self._recording_start).total_seconds())
        h = elapsed // 3600
        m = (elapsed % 3600) // 60
        s = elapsed % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _tick_timer(self) -> None:
        if not self._gravando:
            return
        n = len(self._pages)
        plural = "s" if n != 1 else ""

        # Blink no dot da status bar
        self._blink_state = not self._blink_state
        self._dot_cv.itemconfig(self._dot, fill=C["red"] if self._blink_state else "#8b0000")
        self.lbl_status.config(
            text=f"GRAVANDO — {n} aba{plural} | {self._elapsed_str()}",
            fg=C["red"],
        )

        # Atualiza label de contagem de abas no body
        if self._tab_count_lbl:
            self._tab_count_lbl.config(
                text=f"📑  {n} aba{plural} sendo gravada{plural}",
            )

        self._timer_id = self.root.after(1000, self._tick_timer)

    def _parar_timer(self) -> None:
        if self._timer_id:
            self.root.after_cancel(self._timer_id)
            self._timer_id = None
        self._dot_cv.itemconfig(self._dot, fill=C["orange"])

    # ─── Iniciar ──────────────────────────────────────────────────────────────

    def iniciar_fluxo(self):
        if not self._canal_browser:
            messagebox.showerror(
                "Navegador não encontrado",
                "O SupTrace requer o Google Chrome ou o Microsoft Edge instalado.\n\n"
                "Instale um dos navegadores e reinicie a aplicação.",
            )
            return

        self._tmp_dir   = tempfile.mkdtemp(prefix="gravador_suporte_", dir=_APP_TMP_ROOT)
        self._har_path  = os.path.join(self._tmp_dir, "rede.har")
        self._video_dir = os.path.join(self._tmp_dir, "video")
        os.makedirs(self._video_dir, exist_ok=True)

        self._pages = []
        self._stop_event.clear()
        self._gravando = True
        self._salvando = False

        self._btn_disable(self.btn_iniciar)
        self._set_status(f"Abrindo {self._nome_browser}...", "blue")

        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._run_loop, daemon=True).start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._abrir_navegador())
        except Exception as exc:
            self.root.after(
                0, lambda e=exc: messagebox.showerror(
                    "Erro",
                    f"Falha ao iniciar o {self._nome_browser}:\n\n{e}\n\n"
                    "Verifique se o navegador está instalado corretamente.",
                )
            )
            self._set_status("Erro ao abrir o navegador.", "red")
            self.root.after(0, lambda: self._btn_enable(self.btn_iniciar, C["green"]))
            self._gravando = False
        finally:
            self._loop.close()

    async def _abrir_navegador(self):
        self._playwright = await async_playwright().start()

        self._browser = await self._playwright.chromium.launch(
            channel=self._canal_browser,
            headless=False,
            args=["--incognito", "--start-maximized"],
        )

        self._context = await self._browser.new_context(
            record_har_path=self._har_path,
            record_video_dir=self._video_dir,
            # ✅ FIX 1: resolução fixa → FFmpeg sempre usa fast path (zero re-encode)
            record_video_size={"width": VIDEO_W, "height": VIDEO_H},
            no_viewport=True,
        )

        # ✅ Multi-tab: captura qualquer aba aberta pelo usuário (Ctrl+T, window.open, etc.)
        self._context.on("page", self._on_new_page)

        self._page = await self._context.new_page()
        self._pages = [self._page]
        await self._page.goto("https://google.com")

        # Inicia timer e habilita botão Parar
        self._recording_start = datetime.now()
        self.root.after(0, lambda: self._btn_enable(self.btn_parar, C["red"]))
        self.root.after(0, self._tick_timer)

        while not self._stop_event.is_set():
            await asyncio.sleep(0.3)

        await self._fechar_tudo_async()

    def _on_new_page(self, page) -> None:
        """Callback síncrono do Playwright: chamado ao abrir qualquer nova aba."""
        if page not in self._pages:
            self._pages.append(page)

    # ─── Parar ────────────────────────────────────────────────────────────────

    def parar_fluxo(self):
        if self._salvando or not self._gravando:
            return
        self._salvando = True
        self._gravando = False
        self._parar_timer()
        self._btn_disable(self.btn_parar)
        if self._tab_count_lbl:
            self._tab_count_lbl.config(text="")
        self._set_status("Encerrando gravação...", "orange")
        self._stop_event.set()

    # ─── Fechar Playwright ────────────────────────────────────────────────────

    async def _fechar_tudo_async(self):
        # ── 1. Coleta paths de vídeo de TODAS as abas rastreadas (antes do close)
        video_paths: list[str] = []
        for page in self._pages:
            try:
                if page.video:
                    vp = await page.video.path()
                    if vp and vp not in video_paths:
                        video_paths.append(vp)
            except Exception:
                pass

        # ── 2. context.close() finaliza HAR + todos os vídeos no disco
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass

        # ── 3. Fallback: varre diretório para capturar abas não rastreadas pelo evento
        try:
            for f in sorted(os.listdir(self._video_dir)):
                if f.endswith(".webm"):
                    full = os.path.join(self._video_dir, f)
                    if full not in video_paths and os.path.exists(full):
                        video_paths.append(full)
        except Exception:
            pass

        # Ordena por mtime → preserva a ordem de abertura das abas
        video_paths = [p for p in video_paths if os.path.exists(p)]
        video_paths.sort(key=os.path.getmtime)

        self._set_progress(12, "Encerrando navegador...")

        # ✅ FIX 2: HAR finalizado no disco → processa em paralelo com browser.close()
        har_result: list[str | None] = [None]
        har_done = threading.Event()

        def _har_worker() -> None:
            har_result[0] = self._gerar_html_har(self._har_path)
            har_done.set()

        threading.Thread(target=_har_worker, daemon=True).start()

        for obj, method in [
            (self._browser,    "close"),
            (self._playwright, "stop"),
        ]:
            try:
                if obj:
                    await getattr(obj, method)()
            except Exception:
                pass

        n = len(video_paths)
        self._set_progress(22, f"Navegador encerrado — {n} vídeo(s) para processar...")

        self.root.after(
            0,
            lambda vps=video_paths, hr=har_result, hd=har_done: (
                self._iniciar_processamento(vps, hr, hd)
            ),
        )

    # ─── Processamento ────────────────────────────────────────────────────────

    def _iniciar_processamento(
        self,
        video_paths: list[str],
        har_result: list[str | None],
        har_done: threading.Event,
    ) -> None:
        n = len(video_paths)
        desc = (
            f"Processando {n} vídeo(s) e relatório de rede..."
            if n else "Processando relatório de rede..."
        )
        self._mostrar_janela_processando(desc)
        threading.Thread(
            target=self._processar_em_thread,
            args=(video_paths, har_result, har_done),
            daemon=True,
        ).start()

    def _processar_em_thread(
        self,
        video_paths: list[str],
        har_result: list[str | None],
        har_done: threading.Event,
    ) -> None:
        erros: list[str] = []
        zip_filename: str = ""
        zip_size_str: str = ""
        n_tabs_ok: int    = 0

        n_videos = len(video_paths)
        video_results: list[str | None] = [None] * max(n_videos, 1)
        video_threads: list[threading.Thread] = []

        try:
            self._set_status("Processando arquivos...", "blue")
            self._set_progress(25, f"Processando {n_videos} vídeo(s) em paralelo...")

            # ✅ Multi-tab: uma thread por vídeo (abas processadas em paralelo)
            for idx in range(n_videos):
                vp = video_paths[idx]

                def _video_worker(path=vp, i=idx) -> None:
                    video_results[i] = self._acelerar_video(path, i)

                t = threading.Thread(target=_video_worker, daemon=True)
                video_threads.append(t)
                t.start()

            # ✅ FIX 2: HAR já processa desde context.close() → wait() quase imediato
            har_done.wait(timeout=30)
            self._set_progress(52, "Relatório HTML pronto. Aguardando vídeo(s)...")

            for t in video_threads:
                t.join()

            self._set_progress(68, "Vídeo(s) processado(s). Montando ZIP...")
            self._set_status("Compactando arquivos...", "blue")

            # ── Monta lista de arquivos para o ZIP ───────────────────────────
            timestamp    = datetime.now().strftime("%d%m%Y-%H%M%S")
            zip_filename = f"{timestamp}.zip"
            zip_path     = os.path.join(OUTPUT_DIR, zip_filename)
            arquivos_zip: list[tuple[str, str]] = []

            har_html = har_result[0]
            if har_html and os.path.exists(har_html):
                arquivos_zip.append((har_html, f"{timestamp}_relatorio.html"))
            else:
                erros.append("⚠️ Relatório HTML não foi gerado.")

            valid_videos = [vr for vr in video_results if vr and os.path.exists(vr)]
            n_tabs_ok = len(valid_videos)

            if valid_videos:
                for i, vp in enumerate(valid_videos):
                    suffix    = "_1.5x" if "acelerado" in vp else ""
                    tab_label = f"_aba{i + 1}" if len(valid_videos) > 1 else ""
                    arquivos_zip.append((vp, f"{timestamp}_video{tab_label}{suffix}.webm"))
            else:
                erros.append("⚠️ Nenhum vídeo foi gerado.")

            # ── Cria o ZIP com progresso por arquivo ─────────────────────────
            if arquivos_zip:
                try:
                    with zipfile.ZipFile(zip_path, "w") as zf:
                        n_files = len(arquivos_zip)
                        for file_idx, (filepath, arcname) in enumerate(arquivos_zip):
                            pct   = 70 + int((file_idx / n_files) * 22)
                            short = arcname if len(arcname) <= 40 else arcname[:37] + "..."
                            self._set_progress(pct, f"Compactando: {short}")
                            if arcname.endswith(".webm"):
                                # .webm já comprimido → ZIP_STORED evita CPU desnecessária
                                zf.write(filepath, arcname, compress_type=zipfile.ZIP_STORED)
                            else:
                                zf.write(filepath, arcname, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)

                    size_bytes   = os.path.getsize(zip_path)
                    zip_size_str = _fmt_size(size_bytes)
                    self._set_progress(93, f"ZIP criado — {zip_size_str}")
                except Exception as exc:
                    erros.append(f"❌ Erro ao criar ZIP: {exc}")
                    zip_filename = ""

            # ── Limpeza ───────────────────────────────────────────────────────
            self._set_progress(96, "Limpando arquivos temporários...")
            if not _safe_rmtree(self._tmp_dir):
                erros.append(
                    "⚠️ Não foi possível apagar os arquivos temporários "
                    "(serão removidos na próxima abertura do SupTrace)."
                )

            self._set_progress(100, "✅ Concluído!")

        except Exception as exc:
            erros.append(f"❌ Erro inesperado: {exc}")
            for t in video_threads:
                if t.is_alive():
                    t.join(timeout=60)

        finally:
            # 700ms para o usuário ver o 100% antes da janela fechar
            self.root.after(
                700,
                lambda: self._mostrar_resultado_final(erros, zip_filename, zip_size_str, n_tabs_ok),
            )

    # ─── Acelerar vídeo ───────────────────────────────────────────────────────

    def _acelerar_video(self, input_path: str | None, idx: int = 0) -> str | None:
        if not input_path or not os.path.exists(input_path):
            return input_path
        if not FFMPEG_EXE:
            return input_path

        # ✅ FIX 1 → needs_scale sempre False; idx no nome evita colisão entre abas
        needs_scale = False
        if VIDEO_SPEED == 1.0 and not needs_scale:
            return input_path

        output_path = os.path.join(self._tmp_dir, f"video_acelerado_{idx}.webm")

        if not needs_scale:
            # ✅ FAST PATH: manipula apenas timestamps → zero re-encode, puro I/O
            cmd = [
                FFMPEG_EXE,
                "-probesize",        "500000",
                "-analyzeduration",  "100000",
                "-itsscale",         f"{1.0 / VIDEO_SPEED:.6f}",
                "-i",                input_path,
                "-c:v",              "copy",
                "-an",
                "-avoid_negative_ts", "make_zero",
                "-y",                output_path,
            ]
        else:
            # SLOW PATH (salvaguarda para alterações futuras em VIDEO_W/H)
            cmd = [
                FFMPEG_EXE,
                "-probesize",       "500000",
                "-analyzeduration", "100000",
                "-i",               input_path,
                "-vf",              f"setpts=PTS/{VIDEO_SPEED},scale={VIDEO_W}:{VIDEO_H}",
                *_LIBVPX_FAST_ARGS,
                "-an", "-threads", "0",
                "-y",  output_path,
            ]

        try:
            subprocess.run(
                cmd,
                check=True, capture_output=True, timeout=300,
                creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            return output_path if os.path.exists(output_path) else input_path
        except Exception:
            return input_path

    # ─── Resultado final ──────────────────────────────────────────────────────

    def _mostrar_resultado_final(
        self,
        erros: list[str],
        zip_filename: str,
        zip_size_str: str,
        n_tabs: int,
    ) -> None:
        self._fechar_janela_processando()

        tab_info  = f"\n🎥 Abas gravadas: {n_tabs}" if n_tabs > 1 else ""
        size_info = f"\n📏 Tamanho:   {zip_size_str}"  if zip_size_str else ""

        if erros and not zip_filename:
            messagebox.showerror("Erro ao gerar o pacote", "\n".join(erros))
        elif erros:
            messagebox.showwarning(
                "Concluído com avisos",
                "\n".join(erros) + f"\n\n📁 Pasta:   {OUTPUT_DIR}\n📦 Arquivo: {zip_filename}",
            )
        else:
            messagebox.showinfo(
                "✅ Gravação concluída!",
                f"Pacote gerado com sucesso!\n\n"
                f"📁 Pasta:   {OUTPUT_DIR}\n"
                f"📦 Arquivo: {zip_filename}"
                f"{size_info}"
                f"{tab_info}\n\n"
                "Envie o arquivo .zip para a equipe técnica.",
            )

        status_extra = f" ({zip_size_str})" if zip_size_str else ""
        self._set_status(f"Concluído → {zip_filename}{status_extra}", "green")
        self.root.after(0, lambda: self._btn_enable(self.btn_iniciar, C["green"]))
        self._salvando = False

    # ─── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _fmt_json(text: str) -> str:
        if not text:
            return "—"
        try:
            return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
        except Exception:
            return text or "—"

    @staticmethod
    def _extrair_endpoint(url: str) -> str:
        try:
            path = urlparse(url).path or "/"
            return path if len(path) <= 60 else path[:57] + "..."
        except Exception:
            return "-"

    # ─── Gerar HTML interativo do HAR ─────────────────────────────────────────

    def _gerar_html_har(self, har_path: str) -> str | None:
        if not har_path or not os.path.exists(har_path):
            return None
        try:
            with open(har_path, "r", encoding="utf-8") as f:
                har_data = json.load(f)
        except Exception:
            return None

        entries = har_data.get("log", {}).get("entries", [])
        creator = har_data.get("log", {}).get("creator", {}).get("name", "Playwright")

        filtered = [
            e for e in entries
            if e.get("_resourceType", "other") not in HAR_SKIP_TYPES
        ]

        total     = len(filtered)
        count_5xx = sum(1 for e in filtered if e.get("response", {}).get("status", 0) >= 500)
        count_4xx = sum(1 for e in filtered if 400 <= e.get("response", {}).get("status", 0) < 500)
        count_ok  = total - count_5xx - count_4xx

        # ✅ FIX 3: lista + join único → O(n) em vez de O(n²)
        rows: list[str] = []

        for i, entry in enumerate(filtered):
            req         = entry.get("request",  {})
            resp        = entry.get("response", {})
            method      = req.get("method",     "-")
            url         = req.get("url",        "-")
            status      = resp.get("status",    "-")
            status_text = resp.get("statusText","")
            rtype       = entry.get("_resourceType", "-")
            time_ms     = round(entry.get("time", 0))
            started     = entry.get("startedDateTime", "")[:19].replace("T", " ")
            endpoint    = self._extrair_endpoint(url)
            url_short   = url if len(url) <= 70 else url[:67] + "..."

            sc = ("s2" if isinstance(status, int) and status < 300 else
                  "s3" if isinstance(status, int) and status < 400 else
                  "s4" if isinstance(status, int) and status < 500 else
                  "s5" if isinstance(status, int) else "")

            mc = {"GET":"mg","POST":"mp","PUT":"mu","DELETE":"md","PATCH":"mpa"}.get(method, "mo")

            req_hdrs_json  = json.dumps({h["name"]: h["value"] for h in req.get("headers", [])}, indent=2, ensure_ascii=False)
            req_params     = req.get("queryString", [])
            req_params_str = json.dumps({p["name"]: p["value"] for p in req_params}, indent=2, ensure_ascii=False) if req_params else ""
            post_data      = req.get("postData") or {}
            req_body       = self._fmt_json(post_data.get("text", ""))
            resp_hdrs_json = json.dumps({h["name"]: h["value"] for h in resp.get("headers", [])}, indent=2, ensure_ascii=False)
            content        = resp.get("content", {})
            resp_body_raw  = content.get("text", "")
            resp_mime      = content.get("mimeType", "")
            resp_size      = content.get("size", 0)
            resp_body      = self._fmt_json(resp_body_raw) if "json" in resp_mime else (resp_body_raw or "—")
            resp_body_trunc = resp_body[:10_000]
            resp_truncated  = len(resp_body) > 10_000

            tab_btns     = f'<button class="tab-btn active" onclick="showTab(event,\'t{i}_rqh\')">📤 Request Headers</button>'
            tab_contents = f'<div class="tab-content active" id="t{i}_rqh"><pre>{html_lib.escape(req_hdrs_json)}</pre></div>'

            if req_params_str:
                tab_btns     += f'<button class="tab-btn" onclick="showTab(event,\'t{i}_qp\')">🔗 Query Params</button>'
                tab_contents += f'<div class="tab-content" id="t{i}_qp"><pre>{html_lib.escape(req_params_str)}</pre></div>'

            if req_body.strip() and req_body != "—":
                tab_btns     += f'<button class="tab-btn" onclick="showTab(event,\'t{i}_pay\')">📦 Payload</button>'
                tab_contents += f'<div class="tab-content" id="t{i}_pay"><pre>{html_lib.escape(req_body)}</pre></div>'

            tab_btns += (
                f'<button class="tab-btn" onclick="showTab(event,\'t{i}_rsh\')">📥 Response Headers</button>'
                f'<button class="tab-btn" onclick="showTab(event,\'t{i}_rsb\')">📋 Response Body</button>'
            )
            trunc_note    = '<span class="trunc">⚠️ Corpo truncado em 10.000 caracteres</span>' if resp_truncated else ""
            tab_contents += (
                f'<div class="tab-content" id="t{i}_rsh"><pre>{html_lib.escape(resp_hdrs_json)}</pre></div>'
                f'<div class="tab-content" id="t{i}_rsb">'
                f'<small>Tamanho: {resp_size} bytes | MIME: {html_lib.escape(resp_mime)}</small>'
                f'{trunc_note}<pre>{html_lib.escape(resp_body_trunc)}</pre></div>'
            )

            rows.append(
                f'<tr class="req-row" onclick="toggleRow({i})" title="Clique para expandir detalhes">'
                f'<td><span class="method {mc}">{html_lib.escape(method)}</span></td>'
                f'<td class="ep-cell" title="{html_lib.escape(url)}">{html_lib.escape(endpoint)}</td>'
                f'<td class="url-cell" title="{html_lib.escape(url)}">{html_lib.escape(url_short)}</td>'
                f'<td><span class="{sc}">{status} {html_lib.escape(status_text)}</span></td>'
                f'<td>{html_lib.escape(rtype)}</td>'
                f'<td>{time_ms}ms</td>'
                f'<td>{html_lib.escape(started)}</td>'
                f'</tr>'
                f'<tr class="detail-row" id="d{i}"><td colspan="7">'
                f'<div class="detail-box"><div class="tabs">{tab_btns}</div>{tab_contents}</div>'
                f'</td></tr>'
            )

        rows_html    = "".join(rows)     # ✅ FIX 3: única alocação após o loop
        generated_at = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        html_doc = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Relatório HAR — Suporte Técnico</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;font-family:"Segoe UI",Arial,sans-serif}}
body{{background:#f0f2f5;color:#222;padding:20px}}
h1{{font-size:22px;margin-bottom:4px;color:#1a1a2e}}
.subtitle{{font-size:12px;color:#666;margin-bottom:16px}}
.summary{{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap}}
.card{{background:#fff;border-radius:8px;padding:12px 20px;box-shadow:0 1px 4px rgba(0,0,0,.1);min-width:120px;text-align:center}}
.card .val{{font-size:28px;font-weight:bold}}
.card .lbl{{font-size:11px;color:#888;margin-top:2px}}
.c-ok .val{{color:#28a745}}.c-4xx .val{{color:#fd7e14}}.c-5xx .val{{color:#dc3545}}
.search-bar{{margin-bottom:14px}}
.search-bar input{{width:100%;padding:8px 12px;border-radius:6px;border:1px solid #ccc;font-size:13px;outline:none;transition:border .2s}}
.search-bar input:focus{{border-color:#1a1a2e}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
thead{{background:#1a1a2e;color:#fff}}
thead th{{padding:10px 12px;text-align:left;font-size:12px;font-weight:600;letter-spacing:.4px}}
.req-row{{cursor:pointer;transition:background .12s}}
.req-row:hover{{background:#eef2ff}}
.req-row td{{padding:8px 12px;font-size:12px;border-bottom:1px solid #f0f0f0;vertical-align:middle}}
.ep-cell{{font-family:"Consolas",monospace;font-size:11px;color:#1a1a2e;font-weight:600;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.url-cell{{font-family:"Consolas",monospace;font-size:11px;color:#555;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.method{{display:inline-block;padding:2px 7px;border-radius:4px;font-weight:bold;font-size:11px;color:#fff}}
.mg{{background:#28a745}}.mp{{background:#007bff}}.mu{{background:#fd7e14}}
.md{{background:#dc3545}}.mpa{{background:#6f42c1}}.mo{{background:#6c757d}}
.s2{{color:#28a745;font-weight:600}}.s3{{color:#17a2b8;font-weight:600}}
.s4{{color:#fd7e14;font-weight:bold}}.s5{{color:#dc3545;font-weight:bold}}
.detail-row{{display:none}}.detail-row.open{{display:table-row}}
.detail-box{{padding:12px;background:#f8f9fa;border-top:2px solid #1a1a2e}}
.tabs{{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap}}
.tab-btn{{background:#e9ecef;border:none;padding:5px 12px;border-radius:4px;cursor:pointer;font-size:12px;transition:background .1s}}
.tab-btn:hover{{background:#ced4da}}.tab-btn.active{{background:#1a1a2e;color:#fff}}
.tab-content{{display:none}}.tab-content.active{{display:block}}
pre{{background:#1e1e2e;color:#cdd6f4;padding:12px;border-radius:6px;font-size:12px;font-family:"Consolas","Courier New",monospace;overflow-x:auto;white-space:pre-wrap;word-wrap:break-word;max-height:420px;overflow-y:auto;margin-top:6px}}
small{{font-size:11px;color:#888;display:block;margin-bottom:4px}}
.trunc{{font-size:11px;color:#fd7e14;display:block;margin:4px 0;font-weight:600}}
.hidden{{display:none!important}}
</style>
</head>
<body>
<h1>📜 Relatório de Requisições de Rede</h1>
<p class="subtitle">Gerado em {generated_at} &nbsp;|&nbsp; Fonte: {html_lib.escape(creator)} &nbsp;|&nbsp; Filtro: XHR · Fetch · Document · WebSocket</p>
<div class="summary">
  <div class="card c-ok"><div class="val">{total}</div><div class="lbl">Total</div></div>
  <div class="card c-ok"><div class="val">{count_ok}</div><div class="lbl">2xx / 3xx</div></div>
  <div class="card c-4xx"><div class="val">{count_4xx}</div><div class="lbl">Erros 4xx</div></div>
  <div class="card c-5xx"><div class="val">{count_5xx}</div><div class="lbl">Erros 5xx</div></div>
</div>
<div class="search-bar">
  <input type="text" id="searchInput" placeholder="🔍  Filtrar por endpoint, URL, método, status, tipo..." oninput="filterTable()">
</div>
<table id="mainTable">
  <thead><tr><th>Método</th><th>Endpoint (API)</th><th>URL Completa</th><th>Status</th><th>Tipo</th><th>Tempo</th><th>Horário</th></tr></thead>
  <tbody>{rows_html}</tbody>
</table>
<script>
function toggleRow(i){{const d=document.getElementById('d'+i);const opening=!d.classList.contains('open');d.classList.toggle('open');if(opening){{const btns=d.querySelectorAll('.tab-btn');const contents=d.querySelectorAll('.tab-content');btns.forEach((b,j)=>b.classList.toggle('active',j===0));contents.forEach((c,j)=>c.classList.toggle('active',j===0));}}}}
function showTab(ev,id){{const box=ev.target.closest('.detail-box');box.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));box.querySelectorAll('.tab-content').forEach(c=>c.classList.remove('active'));ev.target.classList.add('active');document.getElementById(id).classList.add('active');}}
function filterTable(){{const q=document.getElementById('searchInput').value.toLowerCase();let idx=0;document.querySelectorAll('.req-row').forEach(row=>{{const show=!q||row.textContent.toLowerCase().includes(q);row.classList.toggle('hidden',!show);const det=document.getElementById('d'+idx);if(det){{det.classList.toggle('hidden',!show);if(!show)det.classList.remove('open');}}idx++;}});}}
</script>
</body></html>"""

        html_path = os.path.join(self._tmp_dir, "relatorio_rede.html")
        try:
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_doc)
            return html_path
        except Exception:
            return None

    # ─── Fechar janela principal ──────────────────────────────────────────────

    def _on_close(self):
        if self._salvando:
            self._bloquear_fechamento_processando()
            return

        if self._gravando:
            if not messagebox.askokcancel(
                "Sair",
                "Uma gravação está em andamento.\n"
                "Os dados NÃO serão salvos. Deseja sair mesmo assim?",
            ):
                return
            self._parar_timer()

        _safe_rmtree(self._tmp_dir, tentativas=2)
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = GravadorApp(root)
    root.mainloop()
