import ctypes
import sys

# ✅ ELEVAÇÃO DE PRIVILÉGIOS
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
import re

# ✅ FIX PYINSTALLER — antes de qualquer import do playwright
_BROWSERS_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "SupTrace", "browsers",
)
os.makedirs(_BROWSERS_PATH, exist_ok=True)
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _BROWSERS_PATH

import asyncio
import threading
import shutil
import tempfile
import zipfile
import json
import html as html_lib
import subprocess
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import messagebox
from datetime import datetime
from urllib.parse import urlparse
from playwright.async_api import async_playwright

# ─── ffmpeg via imageio-ffmpeg ────────────────────────────────────────────────
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

# ✅ Suprime a janela preta do console em subprocessos no Windows
_CREATE_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

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
}


class GravadorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SupTrace v1.0")
        self.root.resizable(False, False)
        self.root.configure(bg=C["bg"])

        WIN_W, WIN_H = 480, 380
        self.root.update_idletasks()
        self._screen_w: int = self.root.winfo_screenwidth()
        self._screen_h: int = self.root.winfo_screenheight()
        x = (self._screen_w - WIN_W) // 2
        y = (self._screen_h - WIN_H) // 2
        self.root.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

        # ✅ Estilo da barra de progresso do download
        _style = ttk.Style()
        _style.theme_use("default")
        _style.configure(
            "SupTrace.Horizontal.TProgressbar",
            troughcolor=C["dis_bg"],
            background=C["blue"],
            borderwidth=0,
            thickness=10,
        )

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

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─── UI ──────────────────────────────────────────────────────────────────

    def _build_ui(self):

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=C["dark"], height=72)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)

        hdr_left = tk.Frame(hdr, bg=C["dark"])
        hdr_left.pack(side=tk.LEFT, padx=20, fill=tk.Y)

        tk.Label(
            hdr_left, text="⏺  SupTrace",
            bg=C["dark"], fg=C["white"],
            font=("Segoe UI", 17, "bold"),
        ).pack(anchor="w", pady=(14, 0))

        # ── Body ──────────────────────────────────────────────────────────────
        body = tk.Frame(self.root, bg=C["bg"])
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            body,
            text="Grave a tela e as requisições de rede para diagnóstico do suporte.",
            bg=C["bg"], fg=C["subtext"],
            font=("Segoe UI", 9, "bold"), wraplength=420,
        ).pack(pady=(16, 14))

        # Botão Iniciar
        self.btn_iniciar = tk.Button(
            body, text="⏺   Iniciar Gravação",
            command=self.iniciar_fluxo,
            bg=C["green"], fg=C["white"],
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT, cursor="hand2",
            pady=10, width=28, bd=0,
            activebackground=C["green_h"],
            activeforeground=C["white"],
        )
        self.btn_iniciar.pack(pady=(0, 8))
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

        # ✅ Barra de progresso do Chromium (oculta por padrão)
        # Não chamamos .pack() aqui — será exibida apenas durante o download
        self._progress_frame = tk.Frame(body, bg=C["bg"])

        prog_inner = tk.Frame(self._progress_frame, bg=C["bg"])
        prog_inner.pack(fill=tk.X, padx=24)

        self._progress_bar = ttk.Progressbar(
            prog_inner,
            style="SupTrace.Horizontal.TProgressbar",
            orient=tk.HORIZONTAL,
            mode="indeterminate",
            length=100,
        )
        self._progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._progress_lbl = tk.Label(
            prog_inner,
            text="  ...",
            bg=C["bg"], fg=C["dark"],
            font=("Segoe UI", 9, "bold"),
            width=5, anchor="e",
        )
        self._progress_lbl.pack(side=tk.LEFT, padx=(8, 0))

        # ── Card de diretório ─────────────────────────────────────────────────
        # Mantemos referência para posicionar a progress bar ANTES dele
        self._dir_outer = tk.Frame(body, bg=C["white"])
        self._dir_outer.pack(fill=tk.X, padx=24)

        tk.Frame(self._dir_outer, bg=C["dark"], width=5).pack(side=tk.LEFT, fill=tk.Y)

        dir_inner = tk.Frame(self._dir_outer, bg=C["white"])
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
            sbar_in, text="Pronto para iniciar",
            bg=C["dark"], fg=C["gray"],
            font=("Segoe UI", 9),
        )
        self.lbl_status.pack(side=tk.LEFT)

    # ─── Helpers de UI ───────────────────────────────────────────────────────

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

    # ─── Progresso do download ────────────────────────────────────────────────

    def _show_progress(self) -> None:
        """Exibe a barra pulsante (indeterminada) antes de receber o primeiro %."""
        self._progress_bar.config(mode="indeterminate")
        self._progress_bar["value"] = 0
        self._progress_lbl.config(text="  ...")
        self._progress_bar.start(12)
        # Insere visualmente ANTES do card de diretório
        self._progress_frame.pack(fill=tk.X, pady=(0, 10), before=self._dir_outer)

    def _update_progress(self, pct: int) -> None:
        """Muda para modo determinado e atualiza o percentual."""
        self._progress_bar.stop()
        self._progress_bar.config(mode="determinate")
        self._progress_bar["value"] = pct
        self._progress_lbl.config(text=f"{pct:>3}%")

    def _hide_progress(self) -> None:
        """Oculta a barra de progresso após o download."""
        self._progress_bar.stop()
        self._progress_frame.pack_forget()

    # ─── Driver do Playwright ─────────────────────────────────────────────────

    @staticmethod
    def _get_driver_cmd() -> list[str]:
        if getattr(sys, "frozen", False):
            base       = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
            driver_dir = os.path.join(base, "playwright", "driver")
            node_exe   = os.path.join(driver_dir, "node.exe")
            cli_js     = os.path.join(driver_dir, "package", "cli.js")

            if os.path.exists(node_exe) and os.path.exists(cli_js):
                return [node_exe, cli_js]

            pw_cmd = os.path.join(driver_dir, "playwright.cmd")
            if os.path.exists(pw_cmd):
                return ["cmd.exe", "/c", pw_cmd]

            raise FileNotFoundError(
                f"Playwright driver não encontrado em:\n{driver_dir}\n\n"
                "Recompile com:  --collect-all playwright"
            )
        else:
            from playwright._impl._driver import compute_driver_executable
            driver = str(compute_driver_executable())
            if sys.platform == "win32" and driver.lower().endswith(".cmd"):
                return ["cmd.exe", "/c", driver]
            return [driver]

    # ─── Verificar / instalar Chromium ───────────────────────────────────────

    def _verificar_chromium(self) -> bool:
        """
        Verifica se o Chromium está instalado.
        Se não estiver, faz o download exibindo progresso em tempo real na UI.

        • Janela preta suprimida via CREATE_NO_WINDOW.
        • Playwright emite progresso com \\r (mesma linha); lemos em chunks
          binários, dividimos por [\\r\\n] e extraímos o % com regex.
        """
        browsers_path = os.environ["PLAYWRIGHT_BROWSERS_PATH"]

        chromium_ok = (
            os.path.isdir(browsers_path)
            and any(e.startswith("chromium") for e in os.listdir(browsers_path))
        )

        if chromium_ok:
            return True

        # ── Primeira execução: precisa baixar o Chromium ──────────────────────
        self._set_status("Baixando Chromium... (pode levar alguns minutos)", "orange")
        self.root.after(0, self._show_progress)

        try:
            driver_cmd     = self._get_driver_cmd()
            creation_flags = _CREATE_NO_WINDOW if sys.platform == "win32" else 0

            # ✅ Popen em modo binário — lemos a saída em tempo real
            proc = subprocess.Popen(
                [*driver_cmd, "install", "chromium"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,   # unifica stderr → stdout
                env=os.environ.copy(),
                creationflags=creation_flags,
            )

            buf = b""
            while True:
                chunk = proc.stdout.read(128)   # bloqueante, sem spin-lock
                if not chunk:
                    break
                buf += chunk

                # ✅ Divide nos separadores \r e \n para capturar cada update
                segments = re.split(b"[\r\n]", buf)
                buf = segments[-1]              # fragmento incompleto — guarda
                for seg in segments[:-1]:
                    line = seg.decode("utf-8", errors="replace").strip()
                    m    = re.search(r"(\d+)\s*%", line)
                    if m:
                        pct = min(int(m.group(1)), 100)
                        self.root.after(0, lambda p=pct: self._update_progress(p))

            # Processa o que restar no buffer
            if buf.strip():
                line = buf.decode("utf-8", errors="replace").strip()
                m    = re.search(r"(\d+)\s*%", line)
                if m:
                    pct = min(int(m.group(1)), 100)
                    self.root.after(0, lambda p=pct: self._update_progress(p))

            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()

            self.root.after(0, self._hide_progress)

            if proc.returncode not in (0, None):
                raise subprocess.CalledProcessError(proc.returncode, driver_cmd)

            self._set_status("Chromium instalado! Abrindo navegador...", "blue")
            return True

        except FileNotFoundError as exc:
            self.root.after(0, self._hide_progress)
            self.root.after(0, lambda e=exc: messagebox.showerror(
                "Erro de configuração",
                "O driver do Playwright não foi encontrado no executável.\n\n"
                "Recompile o app com:\n\n"
                "  pyinstaller --onefile --windowed --uac-admin --name SupTrace \\\n"
                "    --collect-all playwright --collect-all imageio_ffmpeg suptrace.py\n\n"
                f"Detalhe:\n{e}",
            ))
            self._set_status("Erro de configuração do driver.", "red")
            return False

        except subprocess.CalledProcessError as exc:
            self.root.after(0, self._hide_progress)
            self.root.after(0, lambda e=exc: messagebox.showerror(
                "Falha no download do Chromium",
                "Não foi possível baixar o Chromium.\n\n"
                "Verifique sua conexão com a internet e tente novamente.\n\n"
                f"Código de saída: {e.returncode}",
            ))
            self._set_status("Falha ao baixar Chromium.", "red")
            return False

        except Exception as exc:
            self.root.after(0, self._hide_progress)
            self.root.after(0, lambda e=exc: messagebox.showerror(
                "Chromium não instalado",
                f"Erro inesperado ao instalar o Chromium:\n\n{e}",
            ))
            self._set_status("Chromium não instalado.", "red")
            return False

    # ─── Iniciar ─────────────────────────────────────────────────────────────

    def iniciar_fluxo(self):
        self._tmp_dir   = tempfile.mkdtemp(prefix="gravador_suporte_")
        self._har_path  = os.path.join(self._tmp_dir, "rede.har")
        self._video_dir = os.path.join(self._tmp_dir, "video")
        os.makedirs(self._video_dir, exist_ok=True)

        self._stop_event.clear()
        self._gravando = True
        self._salvando = False

        self._btn_disable(self.btn_iniciar)
        self._set_status("Verificando Chromium...", "blue")

        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._run_loop, daemon=True).start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)

        if not self._verificar_chromium():
            self._gravando = False
            self.root.after(0, lambda: self._btn_enable(self.btn_iniciar, C["green"]))
            self._loop.close()
            return

        try:
            self._loop.run_until_complete(self._abrir_navegador())
        except Exception as exc:
            self.root.after(
                0, lambda e=exc: messagebox.showerror("Erro", f"Falha ao iniciar o navegador:\n{e}")
            )
            self._set_status("Erro ao abrir o navegador.", "red")
            self.root.after(0, lambda: self._btn_enable(self.btn_iniciar, C["green"]))
            self._gravando = False
        finally:
            self._loop.close()

    async def _abrir_navegador(self):
        self._playwright = await async_playwright().start()

        self._browser = await self._playwright.chromium.launch(
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

    # ─── Parar ───────────────────────────────────────────────────────────────

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
        threading.Thread(target=self._processar_em_thread, args=(video_path,), daemon=True).start()

    def _processar_em_thread(self, video_path: str | None):
        video_final = self._acelerar_video(video_path)
        self._set_status("Gerando relatório de rede...", "blue")
        har_html = self._gerar_html_har(self._har_path)
        self._set_status("Compactando arquivos...", "blue")
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

        output_path = os.path.join(self._tmp_dir, "video_acelerado.webm")
        try:
            subprocess.run(
                [
                    FFMPEG_EXE, "-i", input_path,
                    "-vf", f"setpts=PTS/{VIDEO_SPEED},scale={VIDEO_W}:{VIDEO_H}",
                    "-an", "-y", output_path,
                ],
                check=True, capture_output=True, timeout=300,
                creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            return output_path if os.path.exists(output_path) else input_path
        except Exception:
            return input_path

    # ─── Helpers ─────────────────────────────────────────────────────────────

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
<h1>📡 Relatório de Requisições de Rede</h1>
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
                with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
                    for filepath, arcname in arquivos_zip:
                        zf.write(filepath, arcname)
            except Exception as exc:
                erros.append(f"❌ Erro ao criar ZIP: {exc}")

        shutil.rmtree(self._tmp_dir, ignore_errors=True)

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
        if self._gravando:
            if not messagebox.askokcancel(
                "Sair",
                "Uma gravação está em andamento.\n"
                "Os dados NÃO serão salvos. Deseja sair mesmo assim?",
            ):
                return
        shutil.rmtree(self._tmp_dir, ignore_errors=True)
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = GravadorApp(root)
    root.mainloop()
