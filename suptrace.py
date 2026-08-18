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
# ✅ PLAYWRIGHT_BROWSERS_PATH – definido antes de qualquer import do playwright.
#    Aponta para um diretório persistente e gravável onde o ffmpeg será
#    copiado do imageio-ffmpeg na primeira execução do .exe.
import os

_PW_BROWSERS_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "SupTrace", "pw-browsers",
)
os.makedirs(_PW_BROWSERS_PATH, exist_ok=True)
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _PW_BROWSERS_PATH

# ─────────────────────────────────────────────────────────────────────────────
# ✅ TEMP/TMP fixos em uma pasta própria e sempre gravável.
#    Quando o app roda elevado (UAC/"runas"), o Windows às vezes resolve
#    %TEMP% para um perfil incorreto (ex.: "...\Application Data"), que pode
#    não ter permissão de escrita. Isso causava falha ao apagar arquivos
#    temporários e, em seguida, falha nas gravações seguintes. Fixamos aqui
#    ANTES de qualquer uso de tempfile, para garantir um caminho previsível.
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

# ─── Preset de re-encode rápido (usado SOMENTE quando há reescala de resolução)
# ✅ VP8 "realtime" é drasticamente mais rápido que o default do FFmpeg,
#    a um custo de qualidade irrelevante para fins de suporte técnico.
_LIBVPX_FAST_ARGS = [
    "-c:v", "libvpx",
    "-deadline", "realtime",   # preset máximo de velocidade do VP8
    "-cpu-used", "8",          # 0 = melhor qualidade; 8 = máxima velocidade
    "-crf", "18",
    "-b:v", "0",
]

# ─── Caminhos dos navegadores homologados ─────────────────────────────────────
_CHROME_PATHS: list[str] = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        r"Google\Chrome\Application\chrome.exe",
    ),
]

_EDGE_PATHS: list[str] = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# ─── Paleta de cores ──────────────────────────────────────────────────────────
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

def _safe_rmtree(path: str, tentativas: int = 5, espera: float = 0.6) -> bool:
    """
    Remove um diretório com tentativas repetidas. No Windows é comum um
    processo (ffmpeg, antivírus) segurar o arquivo por uma fração de
    segundo a mais – isso fazia a limpeza falhar e "empacar" pastas
    temporárias, causando os erros relatados. Aqui insistimos por alguns
    segundos antes de desistir.
    """
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
    """
    Remove, na inicialização, pastas temporárias de execuções anteriores
    que não puderam ser apagadas (ex.: app fechado à força, arquivo
    travado). Evita acúmulo de lixo em disco e problemas futuros de
    permissão/espaço. Falhas aqui são silenciosas – não é crítico.
    """
    try:
        for nome in os.listdir(_APP_TMP_ROOT):
            if nome.startswith("gravador_suporte_"):
                _safe_rmtree(os.path.join(_APP_TMP_ROOT, nome), tentativas=1)
    except Exception:
        pass

def _detectar_canal_browser() -> tuple[str, str] | tuple[None, None]:
    """
    Detecta o navegador instalado disponível no sistema.
    Prioridade: Google Chrome → Microsoft Edge.
    Retorna (canal_playwright, nome_exibição) ou (None, None).
    """
    for path in _CHROME_PATHS:
        if os.path.exists(path):
            return "chrome", "Google Chrome"
    for path in _EDGE_PATHS:
        if os.path.exists(path):
            return "msedge", "Microsoft Edge"
    return None, None

def _setup_ffmpeg_para_playwright() -> None:
    """
    Quando executado como .exe (PyInstaller), o Playwright não encontra o
    ffmpeg no diretório _MEIPASS. Esta função resolve isso sem nenhum download:

      1. Lê o browsers.json empacotado pelo PyInstaller para descobrir a
         revisão exata de ffmpeg que a versão atual do Playwright espera.
      2. Copia o binário do imageio-ffmpeg para _PW_BROWSERS_PATH com o
         nome e estrutura de diretórios exatos que o Playwright exige.

    Em desenvolvimento (VSCode) não executa nada – o Playwright usa o
    cache normal do usuário em AppData/Local/ms-playwright.
    """
    if not getattr(sys, "frozen", False):
        return  # Só age quando rodando como .exe

    if not FFMPEG_EXE or not os.path.exists(FFMPEG_EXE):
        return  # imageio-ffmpeg não disponível

    base = getattr(sys, "_MEIPASS", "")
    if not base:
        return

    # Possíveis localizações do browsers.json dentro do bundle PyInstaller
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

    # Descobre a revisão do ffmpeg que esta versão do Playwright espera
    revision = None
    for browser in data.get("browsers", []):
        if browser.get("name") == "ffmpeg":
            revision = browser.get("revision")
            break

    if not revision:
        return

    # Copia o binário do imageio-ffmpeg para o local esperado pelo Playwright
    target_dir = os.path.join(_PW_BROWSERS_PATH, f"ffmpeg-{revision}")
    target_exe = os.path.join(target_dir, "ffmpeg-win64.exe")

    if not os.path.exists(target_exe):
        try:
            os.makedirs(target_dir, exist_ok=True)
            shutil.copy2(FFMPEG_EXE, target_exe)
        except Exception:
            pass  # Falha silenciosa – o vídeo não será gerado, mas o HAR sim

# ✅ Configura o ffmpeg antes de qualquer chamada ao Playwright
_setup_ffmpeg_para_playwright()

class GravadorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SupTrace v1.2")
        self.root.resizable(False, False)
        self.root.configure(bg=C["bg"])

        WIN_W, WIN_H = 480, 350
        self.root.update_idletasks()
        self._screen_w: int = self.root.winfo_screenwidth()
        self._screen_h: int = self.root.winfo_screenheight()
        x = (self._screen_w - WIN_W) // 2
        y = (self._screen_h - WIN_H) // 2
        self.root.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

        self._loop: asyncio.AbstractEventLoop | None = None
        self._playwright = None
        self._browser    = None
        self._context    = None
        self._page       = None
        self._gravando: bool = False
        self._salvando: bool = False
        self._stop_event = threading.Event()

        self._tmp_dir:   str = ""
        self._har_path:  str = ""
        self._video_dir: str = ""
        self._proc_win: tk.Toplevel | None = None
        self._proc_lbl: tk.Label | None = None

        # ✅ Detecta o navegador disponível na inicialização
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

        # ✅ Badge do navegador detectado
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

        # ── Body ──────────────────────────────────────────────────────────────
        body = tk.Frame(self.root, bg=C["bg"])
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            body,
            text="Grave a tela e as requisições de rede para diagnóstico do suporte.",
            bg=C["bg"], fg=C["subtext"],
            font=("Segoe UI", 9, "bold"), wraplength=420,
        ).pack(pady=(14, 10))

        # ✅ Alerta visível quando nenhum navegador é encontrado
        if not self._canal_browser:
            alerta = tk.Frame(body, bg=C["warn_bg"], padx=12, pady=8)
            alerta.pack(fill=tk.X, padx=24, pady=(0, 10))
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
        self.btn_parar.pack(pady=(0, 12))
        self._bind_hover(self.btn_parar, C["red"], C["red_h"])

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

    # ─── Janela de "Processando..." ───────────────────────────────────────────

    def _mostrar_janela_processando(self, texto_inicial: str) -> None:
        if self._proc_win is not None:
            return

        win = tk.Toplevel(self.root)
        win.title("Processando...")
        win.configure(bg=C["white"])
        win.resizable(False, False)
        win.transient(self.root)
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", self._bloquear_fechamento_processando)

        WIN_W, WIN_H = 380, 150
        x = (self._screen_w - WIN_W) // 2
        y = (self._screen_h - WIN_H) // 2
        win.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

        tk.Label(
            win, text="⏳  Gerando o pacote de suporte...",
            bg=C["white"], fg=C["dark"],
            font=("Segoe UI", 11, "bold"),
        ).pack(pady=(18, 4))

        self._proc_lbl = tk.Label(
            win, text=texto_inicial,
            bg=C["white"], fg=C["subtext"],
            font=("Segoe UI", 9),
        )
        self._proc_lbl.pack(pady=(0, 10))

        barra = ttk.Progressbar(win, mode="indeterminate", length=300)
        barra.pack(pady=(0, 10))
        barra.start(12)

        tk.Label(
            win, text="⚠️  Não feche o aplicativo até esta janela desaparecer.",
            bg=C["white"], fg=C["red"],
            font=("Segoe UI", 8, "bold"),
        ).pack()

        win.grab_set()
        self._proc_win = win

    def _atualizar_janela_processando(self, texto: str) -> None:
        if self._proc_lbl is not None:
            try:
                self._proc_lbl.config(text=texto)
            except Exception:
                pass

    def _fechar_janela_processando(self) -> None:
        if self._proc_win is not None:
            try:
                self._proc_win.grab_release()
                self._proc_win.destroy()
            except Exception:
                pass
            self._proc_win = None
            self._proc_lbl = None

    def _bloquear_fechamento_processando(self) -> None:
        messagebox.showwarning(
            "Aguarde",
            "O pacote ainda está sendo gerado.\n"
            "Feche esta janela apenas quando o processo terminar,\n"
            "ou os arquivos serão perdidos.",
            parent=self._proc_win,
        )

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
            record_video_size={"width": self._screen_w, "height": self._screen_h},
            no_viewport=True,
        )

        self._page = await self._context.new_page()
        await self._page.goto("https://google.com")

        self.root.after(0, lambda: self._btn_enable(self.btn_parar, C["red"]))
        self._set_status("GRAVANDO — Realize o teste no navegador.", "red")

        while not self._stop_event.is_set():
            await asyncio.sleep(0.3)

        await self._fechar_tudo_async()

    # ─── Parar ────────────────────────────────────────────────────────────────

    def parar_fluxo(self):
        if self._salvando:
            return
        self._salvando = True
        self._gravando = False
        self._btn_disable(self.btn_parar)
        self._set_status("Encerrando gravação...", "orange")
        self._stop_event.set()

    # ─── Fechar Playwright ────────────────────────────────────────────────────

    async def _fechar_tudo_async(self):
        video_path: str | None = None

        try:
            if self._page and self._page.video:
                video_path = await self._page.video.path()
        except Exception:
            pass

        if not video_path or not os.path.exists(video_path):
            try:
                files = [
                    os.path.join(self._video_dir, f)
                    for f in os.listdir(self._video_dir)
                    if f.endswith(".webm")
                ]
                if files:
                    video_path = max(files, key=os.path.getmtime)
            except Exception:
                pass

        for obj, method in [
            (self._context,    "close"),
            (self._browser,    "close"),
            (self._playwright, "stop"),
        ]:
            try:
                if obj:
                    await getattr(obj, method)()
            except Exception:
                pass

        self.root.after(0, lambda: self._iniciar_processamento(video_path))

    # ─── Processamento ────────────────────────────────────────────────────────

    def _iniciar_processamento(self, video_path: str | None):
        self._set_status("Processando vídeo (1.5×)...", "blue")
        self._mostrar_janela_processando("Acelerando e ajustando o vídeo...")
        threading.Thread(target=self._processar_em_thread, args=(video_path,), daemon=True).start()

    def _processar_em_thread(self, video_path: str | None):
        resultado: dict[str, str | None] = {"video": None, "har": None}
        video_final: str | None = None
        har_html:    str | None = None

        try:
            def _tarefa_video():
                resultado["video"] = self._acelerar_video(video_path)

            def _tarefa_har():
                resultado["har"] = self._gerar_html_har(self._har_path)

            self.root.after(0, lambda: self._atualizar_janela_processando(
                "Acelerando o vídeo e gerando o relatório de rede..."
            ))
            self._set_status("Processando vídeo e relatório...", "blue")

            t_video = threading.Thread(target=_tarefa_video, daemon=True)
            t_har   = threading.Thread(target=_tarefa_har,   daemon=True)
            t_video.start()
            t_har.start()
            t_video.join()
            t_har.join()

            self.root.after(0, lambda: self._atualizar_janela_processando("Compactando arquivos..."))
            self._set_status("Compactando arquivos...", "blue")

            video_final = resultado["video"]
            har_html    = resultado["har"]
        except Exception:
            video_final = video_final or resultado.get("video")
            har_html    = har_html or resultado.get("har")
        finally:
            self.root.after(
                0,
                lambda vf=video_final, hh=har_html: self._salvar_arquivos_finais(vf, hh),
            )

    # ─── Acelerar + normalizar vídeo ─────────────────────────────────────────

    def _acelerar_video(self, input_path: str | None) -> str | None:
        if not input_path or not os.path.exists(input_path):
            return input_path
        if not FFMPEG_EXE:
            return input_path

        # Atalho: sem aceleração E sem reescala → devolve o original intacto
        needs_scale = (self._screen_w, self._screen_h) != (VIDEO_W, VIDEO_H)
        if VIDEO_SPEED == 1.0 and not needs_scale:
            return input_path

        output_path = os.path.join(self._tmp_dir, "video_acelerado.webm")

        if not needs_scale:
            # ✅ FAST PATH — manipula somente os timestamps do container WebM.
            #
            # -itsscale reescala cada PTS/DTS de entrada antes de passá-lo
            # ao muxer: PTS_saída = PTS_entrada × (1 / VIDEO_SPEED).
            # Com timestamps menores, o player reproduz os frames mais rápido.
            #
            # -c:v copy → bitstream VP8/VP9 copiado byte-a-byte.
            # Nenhum frame é decodificado ou reencodado.
            # Custo: praticamente só I/O de disco.
            # Resultado: ~15–20 s de FFmpeg → < 1 s para qualquer duração.
            #
            # -probesize / -analyzeduration cortam o tempo de análise inicial
            # do container (padrão 5 MB / 5 s → reduzido para 500 KB / 0,1 s).
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
            # SLOW PATH — resolução diferente: re-encode inevitável.
            # Usa VP8 "realtime" + cpu-used 8 para minimizar o tempo de encode.
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
            return input_path  # degradação silenciosa: devolve o .webm original

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

        rows_html = ""

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

            tab_btns = f'<button class="tab-btn active" onclick="showTab(event,\'t{i}_rqh\')">📤 Request Headers</button>'
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

            rows_html += (
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

    # ─── Salvar + ZIP ─────────────────────────────────────────────────────────

    def _salvar_arquivos_finais(self, video_path: str | None, har_html: str | None):
        timestamp    = datetime.now().strftime("%d%m%Y-%H%M%S")
        zip_filename = f"{timestamp}.zip"
        zip_path     = os.path.join(OUTPUT_DIR, zip_filename)

        erros: list[str] = []
        arquivos_zip: list[tuple[str, str]] = []

        if har_html and os.path.exists(har_html):
            arquivos_zip.append((har_html, f"{timestamp}_relatorio.html"))
        else:
            erros.append("⚠️ Relatório HTML não foi gerado.")

        if video_path and os.path.exists(video_path):
            suffix = "_1.5x" if "acelerado" in video_path else ""
            arquivos_zip.append((video_path, f"{timestamp}_video{suffix}.webm"))
        else:
            erros.append("⚠️ Arquivo de vídeo não foi gerado.")

        if arquivos_zip:
            try:
                with zipfile.ZipFile(zip_path, "w") as zf:
                    for filepath, arcname in arquivos_zip:
                        # ✅ .webm já é comprimido — ZIP_STORED evita CPU desnecessária.
                        # HTML (texto) se beneficia de ZIP_DEFLATED.
                        if arcname.endswith(".webm"):
                            zf.write(filepath, arcname, compress_type=zipfile.ZIP_STORED)
                        else:
                            zf.write(filepath, arcname, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
            except Exception as exc:
                erros.append(f"❌ Erro ao criar ZIP: {exc}")

        if not _safe_rmtree(self._tmp_dir):
            erros.append(
                "⚠️ Não foi possível apagar todos os arquivos temporários "
                "(serão limpos automaticamente na próxima abertura do SupTrace)."
            )

        self._fechar_janela_processando()

        if erros and not arquivos_zip:
            messagebox.showerror("Erro", "\n".join(erros))
        elif erros:
            messagebox.showwarning(
                "Concluído com avisos",
                "\n".join(erros) + f"\n\n📁 Pasta:   {OUTPUT_DIR}\n📦 Arquivo: {zip_filename}",
            )
        else:
            messagebox.showinfo(
                "✅ Gravação concluída!",
                f"Arquivo salvo com sucesso!\n\n"
                f"📁 Pasta:   {OUTPUT_DIR}\n"
                f"📦 Arquivo: {zip_filename}\n\n"
                "Envie o arquivo .zip para a equipe técnica.",
            )

        self._set_status(f"Concluído → {zip_filename}", "green")
        self.root.after(0, lambda: self._btn_enable(self.btn_iniciar, C["green"]))
        self._salvando = False

    # ─── Fechar janela ────────────────────────────────────────────────────────

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

        _safe_rmtree(self._tmp_dir, tentativas=2)
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = GravadorApp(root)
    root.mainloop()
