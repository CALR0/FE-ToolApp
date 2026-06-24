import tkinter as tk
from tkinter import ttk, messagebox
import os
from datetime import datetime

from config.theme import (
    BG, BG2, BG3, ACCENT, ACCENT2, SUCCESS, WARNING, DANGER,
    TEXT, TEXT2, BORDER, HOVER_ADD, HOVER_DEL,
    FONT_H1, FONT_H2, FONT_BODY, FONT_SMALL,
)
from config.perfiles import PERFILES
from core.xml_generator import generar_xml, _parse_valor
from services.rndc_service import consultar_radicado_remesa
from utils.helpers import resource_path

from ui.excel_loader import ExcelLoaderWindow
from ui.rndc_uploader import RndcUploaderWindow
from ui.consultar_remesas import ConsultarRemesasModule
from ui.editar_xml import EditarXMLModule
from ui.reconstruir_xml import ReconstruirXMLModule
from ui.extraer_datos_rg import ExtraerDatosRGModule
from ui.cruzar_remesas import CruzarRemesasModule
from ui.corregir_remesa import CorregirRemesaModule
from ui.anular_cumplido_remesa import AnularCumplidoRemesaModule
from ui.cumplir_remesa import CumplirRemesaModule
from ui.proceso_completo_remesa import ProcesoCompletoRemesaModule
from ui.anular_cumplido_manifiesto import AnularCumplidoManifiestoModule


class GeneradorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FE-Tool")
        self.root.geometry("860x680")
        self.root.minsize(700, 500)
        self.root.configure(bg=BG)
        self.rem_rows = []
        # Icono de la ventana (esquina superior izquierda)
        try:
            self.root.iconbitmap(resource_path("icono.ico"))
        except Exception:
            pass
        self._apply_styles()
        self._build_ui()

    # ── Estilos ttk ──────────────────────────────────────────────────────────
    def _make_numeric_validator(self):
        """Ya no bloquea puntos ni comas — el parseo se hace al leer el valor."""
        def _validate(new_val):
            return True
        return (self.root.register(_validate), '%P')

    def _apply_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        # Frame / LabelFrame
        s.configure("TFrame",       background=BG)
        s.configure("Card.TFrame",  background=BG2, relief="flat")
        s.configure("TLabelframe",  background=BG2, foreground=TEXT2,
                    font=FONT_H2, bordercolor=BORDER, relief="flat")
        s.configure("TLabelframe.Label", background=BG2, foreground=TEXT2, font=FONT_H2)
        # Entry
        s.configure("TEntry", fieldbackground=BG3, foreground=TEXT,
                    insertcolor=TEXT, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER,
                    font=FONT_BODY, padding=6)
        s.map("TEntry",
              fieldbackground=[("focus", "#2a2f45")],
              bordercolor=[("focus", ACCENT)])
        # Scrollbar
        s.configure("Vertical.TScrollbar", background=BG2, troughcolor=BG,
                    bordercolor=BG, arrowcolor=TEXT2, relief="flat")

    # ── UI principal ─────────────────────────────────────────────────────────
    def _build_ui(self):
        root = self.root
        self._vcmd_num = self._make_numeric_validator()

        # ── Header ───────────────────────────────────────────────────────────
        hdr = tk.Frame(root, bg=BG2, height=56)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)

        # Gradiente simulado con dos labels
        hdr_inner = tk.Frame(hdr, bg=BG2)
        hdr_inner.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(hdr_inner, text="⚡", font=("Segoe UI Emoji", 16),
                 bg=BG2, fg=ACCENT).pack(side=tk.LEFT, padx=(0, 6))
        tk.Label(hdr_inner, text="FE-Tool",
                 font=FONT_H1, bg=BG2, fg=TEXT).pack(side=tk.LEFT)
        tk.Label(hdr_inner, text="  V1.4",
                 font=("Segoe UI", 9), bg=BG2, fg=TEXT2).pack(side=tk.LEFT, pady=4)

        # ── Selector de perfil (pill bar bajo el header) ──────────────────────
        prof_bar = tk.Frame(root, bg=BG2, pady=8)
        prof_bar.pack(fill=tk.X)

        tk.Label(prof_bar, text="Perfil:", font=FONT_BODY,
                 bg=BG2, fg=TEXT2).pack(side=tk.LEFT, padx=(18, 8))

        self._perfil_var = tk.StringVar(value="ut_tsp")
        self._prof_btns = {}
        for pid, pd in PERFILES.items():
            btn = tk.Label(prof_bar, text=pd["nombre"], font=FONT_BODY,
                           bg=ACCENT if pid == "ut_tsp" else BG3,
                           fg="white", cursor="hand2",
                           padx=14, pady=4)
            btn.pack(side=tk.LEFT, padx=3)
            btn.bind("<Button-1>", lambda e, k=pid: self._sel_perfil(k))
            self._prof_btns[pid] = btn

        # ── Layout principal: sidebar + área de contenido ──────────────────────
        main_area = tk.Frame(root, bg=BG)
        main_area.pack(fill=tk.BOTH, expand=True)

        # ── Sidebar ───────────────────────────────────────────────────────────
        sidebar = tk.Frame(main_area, bg=BG2, width=180)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)
        tk.Frame(sidebar, bg=BORDER, height=1).pack(fill=tk.X)
        tk.Label(sidebar, text="MÓDULOS", font=("Segoe UI", 7, "bold"),
                 bg=BG2, fg=TEXT2, anchor="w").pack(fill=tk.X, padx=14, pady=(12,4))

        self._nav_panels  = {}
        self._nav_buttons = {}
        self._nav_active  = tk.StringVar(value="")
        self._nav_activate = {}

        def _mk_nav_btn(key, icono, label):
            frm = tk.Frame(sidebar, bg=BG2, cursor="hand2")
            frm.pack(fill=tk.X, padx=6, pady=2)
            ic  = tk.Label(frm, text=icono, font=("Segoe UI Emoji", 13),
                           bg=BG2, fg=TEXT2, width=2)
            ic.pack(side=tk.LEFT, padx=(6,4), pady=8)
            lbl = tk.Label(frm, text=label, font=FONT_BODY,
                           bg=BG2, fg=TEXT2, anchor="w", justify="left", wraplength=120)
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            def _activate(e=None):
                for k, b in self._nav_buttons.items():
                    b[0].configure(bg=BG2); b[1].configure(bg=BG2, fg=TEXT2); b[2].configure(bg=BG2, fg=TEXT2)
                frm.configure(bg="#1e2235"); ic.configure(bg="#1e2235", fg=ACCENT); lbl.configure(bg="#1e2235", fg=TEXT)
                self._nav_active.set(key)
                def _do_scroll():
                    try:
                        anchors = {"generar": None, "excel": self._anchor_excel, "rndc": self._anchor_rndc}
                        anchor = anchors.get(key)
                        if anchor is None:
                            canvas.yview_moveto(0)
                        else:
                            canvas.update_idletasks()
                            y = anchor.winfo_y()
                            total = canvas.bbox("all")[3] if canvas.bbox("all") else 1
                            canvas.yview_moveto(max(0, (y - 10) / total))
                    except Exception:
                        pass
                self.root.after(20, _do_scroll)
            frm.bind("<Button-1>", _activate); ic.bind("<Button-1>", _activate); lbl.bind("<Button-1>", _activate)
            frm.bind("<Enter>", lambda e, f=frm,i=ic,l=lbl:
                (f.configure(bg="#1a1e30"),i.configure(bg="#1a1e30"),l.configure(bg="#1a1e30"))
                if self._nav_active.get()!=key else None)
            frm.bind("<Leave>", lambda e, f=frm,i=ic,l=lbl:
                (f.configure(bg="#1e2235" if self._nav_active.get()==key else BG2),
                 i.configure(bg="#1e2235" if self._nav_active.get()==key else BG2),
                 l.configure(bg="#1e2235" if self._nav_active.get()==key else BG2)))
            self._nav_buttons[key] = (frm, ic, lbl)
            return _activate

        # ── Grupo colapsable "Facturación" ────────────────────────────────────
        _fac_expanded = tk.BooleanVar(value=False)

        # Cabecera del grupo
        _grp_frm = tk.Frame(sidebar, bg=BG2, cursor="hand2")
        _grp_frm.pack(fill=tk.X, padx=6, pady=2)
        _grp_ic  = tk.Label(_grp_frm, text="🧾", font=("Segoe UI Emoji", 13),
                            bg=BG2, fg=TEXT2, width=2)
        _grp_ic.pack(side=tk.LEFT, padx=(6,4), pady=8)
        _grp_lbl = tk.Label(_grp_frm, text="Facturación", font=FONT_BODY,
                            bg=BG2, fg=TEXT2, anchor="w")
        _grp_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
        _grp_arr = tk.Label(_grp_frm, text="▶", font=("Segoe UI", 8),
                            bg=BG2, fg=TEXT2)
        _grp_arr.pack(side=tk.RIGHT, padx=(0,8))

        # Contenedor de los sub-ítems (oculto inicialmente)
        _sub_frame = tk.Frame(sidebar, bg=BG2)

        def _mk_sub_btn(key, icono, label):
            """Como _mk_nav_btn pero con indentación de submenú."""
            frm = tk.Frame(_sub_frame, bg=BG2, cursor="hand2")
            frm.pack(fill=tk.X, padx=6, pady=1)
            # Sangría visual
            tk.Frame(frm, bg=BG2, width=18).pack(side=tk.LEFT)
            ic  = tk.Label(frm, text=icono, font=("Segoe UI Emoji", 11),
                           bg=BG2, fg=TEXT2, width=2)
            ic.pack(side=tk.LEFT, padx=(2,3), pady=6)
            lbl = tk.Label(frm, text=label, font=("Segoe UI", 9),
                           bg=BG2, fg=TEXT2, anchor="w", justify="left", wraplength=110)
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._nav_buttons[key] = (frm, ic, lbl)
            return frm, ic, lbl

        _mk_sub_btn("generar",     "✏️",  "Generar XML")
        _mk_sub_btn("excel",       "📊",  "Generar facturas\nvía Excel")
        _mk_sub_btn("rndc",        "📤",  "Cargar Facturas\na RNDC")

        def _toggle_facturacion(e=None):
            if _fac_expanded.get():
                _sub_frame.pack_forget()
                _fac_expanded.set(False)
                _grp_arr.configure(text="▶")
            else:
                _sub_frame.pack(fill=tk.X, after=_grp_frm)
                _fac_expanded.set(True)
                _grp_arr.configure(text="▼")

        for w in (_grp_frm, _grp_ic, _grp_lbl, _grp_arr):
            w.bind("<Button-1>", _toggle_facturacion)
            w.bind("<Enter>", lambda e: (
                _grp_frm.configure(bg="#1a1e30"),
                _grp_ic.configure(bg="#1a1e30"),
                _grp_lbl.configure(bg="#1a1e30"),
                _grp_arr.configure(bg="#1a1e30"),
            ))
            w.bind("<Leave>", lambda e: (
                _grp_frm.configure(bg=BG2),
                _grp_ic.configure(bg=BG2),
                _grp_lbl.configure(bg=BG2),
                _grp_arr.configure(bg=BG2),
            ))

        # ── Grupo colapsable "Remesas" ────────────────────────────────────────
        _rem_expanded = tk.BooleanVar(value=False)

        _rem_grp_frm = tk.Frame(sidebar, bg=BG2, cursor="hand2")
        _rem_grp_frm.pack(fill=tk.X, padx=6, pady=2)
        _rem_grp_ic  = tk.Label(_rem_grp_frm, text="📋", font=("Segoe UI Emoji", 13),
                                bg=BG2, fg=TEXT2, width=2)
        _rem_grp_ic.pack(side=tk.LEFT, padx=(6,4), pady=8)
        _rem_grp_lbl = tk.Label(_rem_grp_frm, text="Remesas", font=FONT_BODY,
                                bg=BG2, fg=TEXT2, anchor="w")
        _rem_grp_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
        _rem_grp_arr = tk.Label(_rem_grp_frm, text="▶", font=("Segoe UI", 8),
                                bg=BG2, fg=TEXT2)
        _rem_grp_arr.pack(side=tk.RIGHT, padx=(0,8))

        _rem_sub_frame = tk.Frame(sidebar, bg=BG2)

        def _mk_rem_sub_btn(key, icono, label):
            frm = tk.Frame(_rem_sub_frame, bg=BG2, cursor="hand2")
            frm.pack(fill=tk.X, padx=6, pady=1)
            tk.Frame(frm, bg=BG2, width=18).pack(side=tk.LEFT)
            ic  = tk.Label(frm, text=icono, font=("Segoe UI Emoji", 11),
                           bg=BG2, fg=TEXT2, width=2)
            ic.pack(side=tk.LEFT, padx=(2,3), pady=6)
            lbl = tk.Label(frm, text=label, font=("Segoe UI", 9),
                           bg=BG2, fg=TEXT2, anchor="w", justify="left", wraplength=110)
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._nav_buttons[key] = (frm, ic, lbl)
            return frm, ic, lbl

        _mk_rem_sub_btn("consultar_remesas", "🔍", "Consultar remesas")
        _mk_rem_sub_btn("corregir_remesa", "🛠", "Corregir remesa")
        _mk_rem_sub_btn("anular_cumplido", "🗑", "Anular cumplido remesa")
        _mk_rem_sub_btn("cumplir_remesa", "✅", "Cumplir remesa")
        _mk_rem_sub_btn("proceso_completo", "⚡", "Auto cambio-generador")

        def _toggle_remesas(e=None):
            if _rem_expanded.get():
                _rem_sub_frame.pack_forget()
                _rem_expanded.set(False)
                _rem_grp_arr.configure(text="▶")
            else:
                _rem_sub_frame.pack(fill=tk.X, after=_rem_grp_frm)
                _rem_expanded.set(True)
                _rem_grp_arr.configure(text="▼")

        for w in (_rem_grp_frm, _rem_grp_ic, _rem_grp_lbl, _rem_grp_arr):
            w.bind("<Button-1>", _toggle_remesas)
            w.bind("<Enter>", lambda e: (
                _rem_grp_frm.configure(bg="#1a1e30"),
                _rem_grp_ic.configure(bg="#1a1e30"),
                _rem_grp_lbl.configure(bg="#1a1e30"),
                _rem_grp_arr.configure(bg="#1a1e30"),
            ))
            w.bind("<Leave>", lambda e: (
                _rem_grp_frm.configure(bg=BG2),
                _rem_grp_ic.configure(bg=BG2),
                _rem_grp_lbl.configure(bg=BG2),
                _rem_grp_arr.configure(bg=BG2),
            ))

        # ── Grupo colapsable "Manifiesto" ─────────────────────────────────────
        _man_expanded = tk.BooleanVar(value=False)

        _man_grp_frm = tk.Frame(sidebar, bg=BG2, cursor="hand2")
        _man_grp_frm.pack(fill=tk.X, padx=6, pady=2)
        _man_grp_ic  = tk.Label(_man_grp_frm, text="📑", font=("Segoe UI Emoji", 13),
                                bg=BG2, fg=TEXT2, width=2)
        _man_grp_ic.pack(side=tk.LEFT, padx=(6,4), pady=8)
        _man_grp_lbl = tk.Label(_man_grp_frm, text="Manifiesto", font=FONT_BODY,
                                bg=BG2, fg=TEXT2, anchor="w")
        _man_grp_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
        _man_grp_arr = tk.Label(_man_grp_frm, text="▶", font=("Segoe UI", 8),
                                bg=BG2, fg=TEXT2)
        _man_grp_arr.pack(side=tk.RIGHT, padx=(0,8))

        _man_sub_frame = tk.Frame(sidebar, bg=BG2)

        def _mk_man_sub_btn(key, icono, label):
            frm = tk.Frame(_man_sub_frame, bg=BG2, cursor="hand2")
            frm.pack(fill=tk.X, padx=6, pady=1)
            tk.Frame(frm, bg=BG2, width=18).pack(side=tk.LEFT)
            ic  = tk.Label(frm, text=icono, font=("Segoe UI Emoji", 11),
                           bg=BG2, fg=TEXT2, width=2)
            ic.pack(side=tk.LEFT, padx=(2,3), pady=6)
            lbl = tk.Label(frm, text=label, font=("Segoe UI", 9),
                           bg=BG2, fg=TEXT2, anchor="w", justify="left", wraplength=110)
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._nav_buttons[key] = (frm, ic, lbl)
            return frm, ic, lbl

        _mk_man_sub_btn("anular_cumplido_manifiesto", "🗑", "Anular cumplido manifiesto")

        def _toggle_manifiesto(e=None):
            if _man_expanded.get():
                _man_sub_frame.pack_forget()
                _man_expanded.set(False)
                _man_grp_arr.configure(text="▶")
            else:
                _man_sub_frame.pack(fill=tk.X, after=_man_grp_frm)
                _man_expanded.set(True)
                _man_grp_arr.configure(text="▼")

        for w in (_man_grp_frm, _man_grp_ic, _man_grp_lbl, _man_grp_arr):
            w.bind("<Button-1>", _toggle_manifiesto)
            w.bind("<Enter>", lambda e: (
                _man_grp_frm.configure(bg="#1a1e30"),
                _man_grp_ic.configure(bg="#1a1e30"),
                _man_grp_lbl.configure(bg="#1a1e30"),
                _man_grp_arr.configure(bg="#1a1e30"),
            ))
            w.bind("<Leave>", lambda e: (
                _man_grp_frm.configure(bg=BG2),
                _man_grp_ic.configure(bg=BG2),
                _man_grp_lbl.configure(bg=BG2),
                _man_grp_arr.configure(bg=BG2),
            ))

        # ── Grupo colapsable "Otros" ──────────────────────────────────────────
        _otros_expanded = tk.BooleanVar(value=False)

        _otros_grp_frm = tk.Frame(sidebar, bg=BG2, cursor="hand2")
        _otros_grp_frm.pack(fill=tk.X, padx=6, pady=2)
        _otros_grp_ic  = tk.Label(_otros_grp_frm, text="🔩", font=("Segoe UI Emoji", 13),
                                  bg=BG2, fg=TEXT2, width=2)
        _otros_grp_ic.pack(side=tk.LEFT, padx=(6,4), pady=8)
        _otros_grp_lbl = tk.Label(_otros_grp_frm, text="Otros", font=FONT_BODY,
                                  bg=BG2, fg=TEXT2, anchor="w")
        _otros_grp_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
        _otros_grp_arr = tk.Label(_otros_grp_frm, text="▶", font=("Segoe UI", 8),
                                  bg=BG2, fg=TEXT2)
        _otros_grp_arr.pack(side=tk.RIGHT, padx=(0,8))

        _otros_sub_frame = tk.Frame(sidebar, bg=BG2)

        def _mk_otros_sub_btn(key, icono, label):
            frm = tk.Frame(_otros_sub_frame, bg=BG2, cursor="hand2")
            frm.pack(fill=tk.X, padx=6, pady=1)
            tk.Frame(frm, bg=BG2, width=18).pack(side=tk.LEFT)
            ic  = tk.Label(frm, text=icono, font=("Segoe UI Emoji", 11),
                           bg=BG2, fg=TEXT2, width=2)
            ic.pack(side=tk.LEFT, padx=(2,3), pady=6)
            lbl = tk.Label(frm, text=label, font=("Segoe UI", 9),
                           bg=BG2, fg=TEXT2, anchor="w", justify="left", wraplength=110)
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._nav_buttons[key] = (frm, ic, lbl)
            return frm, ic, lbl

        _mk_otros_sub_btn("editar",        "🖊",  "Editar XML")
        _mk_otros_sub_btn("reconstruir",   "🔧",  "Reconstruir XML")
        _mk_otros_sub_btn("extraer_rg",    "📄",  "Extraer datos RG")
        _mk_otros_sub_btn("cruzar_remesas", "🔀", "Cruzar remesas")

        def _toggle_otros(e=None):
            if _otros_expanded.get():
                _otros_sub_frame.pack_forget()
                _otros_expanded.set(False)
                _otros_grp_arr.configure(text="▶")
            else:
                _otros_sub_frame.pack(fill=tk.X, after=_otros_grp_frm)
                _otros_expanded.set(True)
                _otros_grp_arr.configure(text="▼")

        for w in (_otros_grp_frm, _otros_grp_ic, _otros_grp_lbl, _otros_grp_arr):
            w.bind("<Button-1>", _toggle_otros)
            w.bind("<Enter>", lambda e: (
                _otros_grp_frm.configure(bg="#1a1e30"),
                _otros_grp_ic.configure(bg="#1a1e30"),
                _otros_grp_lbl.configure(bg="#1a1e30"),
                _otros_grp_arr.configure(bg="#1a1e30"),
            ))
            w.bind("<Leave>", lambda e: (
                _otros_grp_frm.configure(bg=BG2),
                _otros_grp_ic.configure(bg=BG2),
                _otros_grp_lbl.configure(bg=BG2),
                _otros_grp_arr.configure(bg=BG2),
            ))

        tk.Frame(sidebar, bg=BORDER, height=1).pack(fill=tk.X, padx=10, pady=8)
        tk.Label(sidebar, text="V1.4", font=("Segoe UI", 8),
                 bg=BG2, fg=BORDER).pack(side=tk.BOTTOM, pady=8)

        # ── Área de contenido ─────────────────────────────────────────────────
        content_area = tk.Frame(main_area, bg=BG)
        content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ── Helper: activar panel (show/hide) ──────────────────────────────────
        def _show_panel(key):
            for k, p in self._nav_panels.items():
                if k == key:
                    p.pack(fill=tk.BOTH, expand=True)
                else:
                    p.pack_forget()
            # Resaltar botón sidebar
            for k, b in self._nav_buttons.items():
                active = (k == key)
                bg_btn = "#1e2235" if active else BG2
                fg_ic  = ACCENT   if active else TEXT2
                fg_lbl = TEXT     if active else TEXT2
                b[0].configure(bg=bg_btn)
                b[1].configure(bg=bg_btn, fg=fg_ic)
                b[2].configure(bg=bg_btn, fg=fg_lbl)
            self._nav_active.set(key)
            # Expandir el grupo Facturación automáticamente si estaba cerrado
            if key in ("generar","excel","rndc"):
                if not _fac_expanded.get():
                    _sub_frame.pack(fill=tk.X, after=_grp_frm)
                    _fac_expanded.set(True)
                    _grp_arr.configure(text="▼")
            # Expandir el grupo Remesas automáticamente si estaba cerrado
            if key in ("consultar_remesas", "corregir_remesa", "anular_cumplido", "cumplir_remesa", "proceso_completo"):
                if not _rem_expanded.get():
                    _rem_sub_frame.pack(fill=tk.X, after=_rem_grp_frm)
                    _rem_expanded.set(True)
                    _rem_grp_arr.configure(text="▼")
            # Expandir el grupo Manifiesto automáticamente si estaba cerrado
            if key in ("anular_cumplido_manifiesto",):
                if not _man_expanded.get():
                    _man_sub_frame.pack(fill=tk.X, after=_man_grp_frm)
                    _man_expanded.set(True)
                    _man_grp_arr.configure(text="▼")
            # Expandir el grupo Otros automáticamente si estaba cerrado
            if key in ("editar","reconstruir","extraer_rg","cruzar_remesas"):
                if not _otros_expanded.get():
                    _otros_sub_frame.pack(fill=tk.X, after=_otros_grp_frm)
                    _otros_expanded.set(True)
                    _otros_grp_arr.configure(text="▼")

        # Reasignar activadores del sidebar → show/hide
        self._nav_activate["generar"]            = lambda: _show_panel("generar")
        self._nav_activate["excel"]               = lambda: _show_panel("excel")
        self._nav_activate["rndc"]                = lambda: _show_panel("rndc")
        self._nav_activate["editar"]              = lambda: _show_panel("editar")
        self._nav_activate["reconstruir"]         = lambda: _show_panel("reconstruir")
        self._nav_activate["consultar_remesas"]   = lambda: _show_panel("consultar_remesas")
        self._nav_activate["corregir_remesa"]     = lambda: _show_panel("corregir_remesa")
        self._nav_activate["anular_cumplido"]     = lambda: _show_panel("anular_cumplido")
        self._nav_activate["cumplir_remesa"]      = lambda: _show_panel("cumplir_remesa")
        self._nav_activate["extraer_rg"]          = lambda: _show_panel("extraer_rg")
        self._nav_activate["cruzar_remesas"]      = lambda: _show_panel("cruzar_remesas")
        self._nav_activate["proceso_completo"]    = lambda: _show_panel("proceso_completo")
        self._nav_activate["anular_cumplido_manifiesto"] = lambda: _show_panel("anular_cumplido_manifiesto")
        for key in ("generar","excel","rndc","editar","reconstruir","consultar_remesas","corregir_remesa","anular_cumplido","cumplir_remesa","extraer_rg","cruzar_remesas","proceso_completo","anular_cumplido_manifiesto"):
            frm, ic, lbl = self._nav_buttons[key]
            act = self._nav_activate[key]
            for w in (frm, ic, lbl):
                w.bind("<Button-1>", lambda e, a=act: a())

        # ─── Panel 1: Generar XML ─────────────────────────────────────────────
        panel_gen = tk.Frame(content_area, bg=BG)
        self._nav_panels["generar"] = panel_gen

        wrapper = tk.Frame(panel_gen, bg=BG)
        wrapper.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(wrapper, bg=BG, highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(wrapper, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._scroll_canvas = canvas
        content = tk.Frame(canvas, bg=BG)
        cwin = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",  lambda e: canvas.itemconfig(cwin, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        pad = dict(padx=16, pady=6)

        self._section(content, "📄  Datos de la Factura", [
            ("Número de factura",   "ent_nf",    "",                          False),
            ("CUFE",                "ent_cufe",  "",                          False),
            ("Fecha de generación (DD-MM-YYYY)", "ent_fecha", datetime.today().strftime("%d-%m-%Y"), False),
            ("Valor total ($)",     "ent_total", "",                          False),
        ], content, **pad)

        self._section(content, "🏢  Datos del Cliente", [
            ("NIT cliente",         "ent_nit_cli", "800021308",   False),
            ("Dígito verificación", "ent_dig_cli", "5",           False),
            ("Nombre cliente",      "ent_nom_cli", "DRUMMOND LTD",False),
        ], content, **pad)

        rem_sec = self._card(content, "📦  Remesas", **pad)
        hdr_row = tk.Frame(rem_sec, bg=BG3)
        hdr_row.pack(fill=tk.X, pady=(0, 2))
        _COLS = [("#",3),("Consecutivo",14),("Radicado",14),("Valor ($)",12),("Peso KGM",9),("Descripción línea",0)]
        for i, (col, w) in enumerate(_COLS):
            tk.Label(hdr_row, text=col, font=FONT_SMALL, bg=BG3, fg=TEXT2,
                     width=w, anchor="w", padx=6 if i > 0 else 3
                     ).grid(row=0, column=i, sticky="ew", padx=1, pady=4)
        hdr_row.grid_columnconfigure(5, weight=1)
        self.rem_container = tk.Frame(rem_sec, bg=BG2)
        self.rem_container.pack(fill=tk.X)
        self.rem_container.grid_columnconfigure(5, weight=1)
        btn_rem = tk.Frame(rem_sec, bg=BG2)
        btn_rem.pack(fill=tk.X, pady=(8, 0))
        self._flat_btn(btn_rem, "＋  Agregar remesa", self._agregar_remesa,
                       ACCENT, HOVER_ADD).pack(side=tk.LEFT, padx=(0, 6))
        self._flat_btn(btn_rem, "－  Quitar última",  self._quitar_remesa,
                       DANGER, HOVER_DEL).pack(side=tk.LEFT)
        self._agregar_remesa()

        gen_frame = tk.Frame(content, bg=BG)
        gen_frame.pack(fill=tk.X, padx=16, pady=(10, 6))
        btn_wrap = tk.Frame(gen_frame, bg=BG)
        btn_wrap.pack(anchor="center")
        self.btn_gen = self._flat_btn(btn_wrap, "⚡  GENERAR XML",
                                      self._generar, ACCENT, "#2d5cbf",
                                      height=28, font=("Segoe UI", 9, "bold"))
        self.btn_gen.pack()

        # ─── Panel 2: Excel (con scroll) ─────────────────────────────────────
        panel_excel = tk.Frame(content_area, bg=BG)
        self._nav_panels["excel"] = panel_excel
        _wrap_ex = tk.Frame(panel_excel, bg=BG)
        _wrap_ex.pack(fill=tk.BOTH, expand=True)
        _cv_ex = tk.Canvas(_wrap_ex, bg=BG, highlightthickness=0)
        _sb_ex = ttk.Scrollbar(_wrap_ex, orient="vertical", command=_cv_ex.yview)
        _cv_ex.configure(yscrollcommand=_sb_ex.set)
        _sb_ex.pack(side=tk.RIGHT, fill=tk.Y)
        _cv_ex.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        _inner_ex = tk.Frame(_cv_ex, bg=BG)
        _cwin_ex = _cv_ex.create_window((0, 0), window=_inner_ex, anchor="nw")
        _inner_ex.bind("<Configure>", lambda e: _cv_ex.configure(scrollregion=_cv_ex.bbox("all")))
        _cv_ex.bind("<Configure>", lambda e: _cv_ex.itemconfig(_cwin_ex, width=e.width))
        _cv_ex.bind("<Enter>", lambda e: _cv_ex.bind_all("<MouseWheel>",
            lambda ev: _cv_ex.yview_scroll(int(-1*(ev.delta/120)), "units")))
        _cv_ex.bind("<Leave>", lambda e: _cv_ex.unbind_all("<MouseWheel>"))

        def _only_int(v):
            return v == "" or v.isdigit()
        _vcmd_max = (root.register(_only_int), "%P")
        self._max_facturas_var = tk.StringVar(value="200")

        def _on_excel_ok(msg):
            self._set_status(msg, SUCCESS)
        self._excel_loader = ExcelLoaderWindow.__new__(ExcelLoaderWindow)
        self._excel_loader.parent       = root
        self._excel_loader.perfil_fn    = self._perfil_activo
        self._excel_loader.on_success   = _on_excel_ok
        self._excel_loader.max_facturas = 200
        self._excel_loader.vars         = {}
        self._excel_loader.combos       = {}
        self._excel_loader.xl_file      = None
        self._excel_loader.hojas        = []
        self._excel_loader.df_raw       = None
        self._excel_loader.cols         = ["— No usar —"]
        self._excel_loader._cufe_map    = {}
        self._excel_loader._build(container=_inner_ex)

        def _sync_max(*_):
            raw = self._max_facturas_var.get().strip()
            try:
                self._excel_loader.max_facturas = max(1, int(raw)) if raw else 200
            except ValueError:
                pass
        self._max_facturas_var.trace_add("write", _sync_max)

        # ─── Panel 3: RNDC (con scroll) ──────────────────────────────────────
        panel_rndc = tk.Frame(content_area, bg=BG)
        self._nav_panels["rndc"] = panel_rndc
        _wrap_rn = tk.Frame(panel_rndc, bg=BG)
        _wrap_rn.pack(fill=tk.BOTH, expand=True)
        _cv_rn = tk.Canvas(_wrap_rn, bg=BG, highlightthickness=0)
        _sb_rn = ttk.Scrollbar(_wrap_rn, orient="vertical", command=_cv_rn.yview)
        _cv_rn.configure(yscrollcommand=_sb_rn.set)
        _sb_rn.pack(side=tk.RIGHT, fill=tk.Y)
        _cv_rn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        _inner_rn = tk.Frame(_cv_rn, bg=BG)
        _cwin_rn = _cv_rn.create_window((0, 0), window=_inner_rn, anchor="nw")
        _inner_rn.bind("<Configure>", lambda e: _cv_rn.configure(scrollregion=_cv_rn.bbox("all")))
        _cv_rn.bind("<Configure>", lambda e: _cv_rn.itemconfig(_cwin_rn, width=e.width))
        _cv_rn.bind("<Enter>", lambda e: _cv_rn.bind_all("<MouseWheel>",
            lambda ev: _cv_rn.yview_scroll(int(-1*(ev.delta/120)), "units")))
        _cv_rn.bind("<Leave>", lambda e: _cv_rn.unbind_all("<MouseWheel>"))

        self._rndc_uploader = RndcUploaderWindow.__new__(RndcUploaderWindow)
        self._rndc_uploader.parent    = root
        self._rndc_uploader.perfil_fn = self._perfil_activo
        self._rndc_uploader.archivos  = []
        self._rndc_uploader._cufe_map = {}
        self._rndc_uploader._build(container=_inner_rn)

        # ─── Panel 4: Editar XML ──────────────────────────────────────────────
        panel_editar = tk.Frame(content_area, bg=BG)
        self._nav_panels["editar"] = panel_editar
        _wrap_ed = tk.Frame(panel_editar, bg=BG)
        _wrap_ed.pack(fill=tk.BOTH, expand=True)
        _cv_ed = tk.Canvas(_wrap_ed, bg=BG, highlightthickness=0)
        _sb_ed = ttk.Scrollbar(_wrap_ed, orient="vertical", command=_cv_ed.yview)
        _cv_ed.configure(yscrollcommand=_sb_ed.set)
        _sb_ed.pack(side=tk.RIGHT, fill=tk.Y)
        _cv_ed.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        _inner_ed = tk.Frame(_cv_ed, bg=BG)
        _cwin_ed = _cv_ed.create_window((0, 0), window=_inner_ed, anchor="nw")
        _inner_ed.bind("<Configure>", lambda e: _cv_ed.configure(scrollregion=_cv_ed.bbox("all")))
        _cv_ed.bind("<Configure>", lambda e: _cv_ed.itemconfig(_cwin_ed, width=e.width))
        _cv_ed.bind("<Enter>", lambda e: _cv_ed.bind_all("<MouseWheel>",
            lambda ev: _cv_ed.yview_scroll(int(-1*(ev.delta/120)), "units")))
        _cv_ed.bind("<Leave>", lambda e: _cv_ed.unbind_all("<MouseWheel>"))

        self._xml_editor = EditarXMLModule(root, perfil_fn=self._perfil_activo)
        self._xml_editor._build(container=_inner_ed)

        # ─── Panel 6: Consultar Remesas ───────────────────────────────────────
        panel_cons_rem = tk.Frame(content_area, bg=BG)
        self._nav_panels["consultar_remesas"] = panel_cons_rem
        self._consultar_remesas_module = ConsultarRemesasModule(
            panel_cons_rem, perfil_fn=self._perfil_activo)
        self._consultar_remesas_module._build(panel_cons_rem)

        # ─── Panel 5: Reconstruir XML ─────────────────────────────────────────
        panel_rec = tk.Frame(content_area, bg=BG)
        self._nav_panels["reconstruir"] = panel_rec
        _wrap_rc = tk.Frame(panel_rec, bg=BG)
        _wrap_rc.pack(fill=tk.BOTH, expand=True)
        _cv_rc = tk.Canvas(_wrap_rc, bg=BG, highlightthickness=0)
        _sb_rc = ttk.Scrollbar(_wrap_rc, orient="vertical", command=_cv_rc.yview)
        _cv_rc.configure(yscrollcommand=_sb_rc.set)
        _sb_rc.pack(side=tk.RIGHT, fill=tk.Y)
        _cv_rc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        _inner_rc = tk.Frame(_cv_rc, bg=BG)
        _cwin_rc = _cv_rc.create_window((0, 0), window=_inner_rc, anchor="nw")
        _inner_rc.bind("<Configure>", lambda e: _cv_rc.configure(scrollregion=_cv_rc.bbox("all")))
        _cv_rc.bind("<Configure>", lambda e: _cv_rc.itemconfig(_cwin_rc, width=e.width))
        _cv_rc.bind("<Enter>", lambda e: _cv_rc.bind_all("<MouseWheel>",
            lambda ev: _cv_rc.yview_scroll(int(-1*(ev.delta/120)), "units")))
        _cv_rc.bind("<Leave>", lambda e: _cv_rc.unbind_all("<MouseWheel>"))

        self._reconstruir_module = ReconstruirXMLModule(self._perfil_activo)
        self._reconstruir_module._build(container=_inner_rc)

        # ─── Panel 7: Extraer datos RG ────────────────────────────────────────
        panel_rg = tk.Frame(content_area, bg=BG)
        self._nav_panels["extraer_rg"] = panel_rg
        _wrap_rg = tk.Frame(panel_rg, bg=BG)
        _wrap_rg.pack(fill=tk.BOTH, expand=True)
        _cv_rg = tk.Canvas(_wrap_rg, bg=BG, highlightthickness=0)
        _sb_rg = ttk.Scrollbar(_wrap_rg, orient="vertical", command=_cv_rg.yview)
        _cv_rg.configure(yscrollcommand=_sb_rg.set)
        _sb_rg.pack(side=tk.RIGHT, fill=tk.Y)
        _cv_rg.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        _inner_rg = tk.Frame(_cv_rg, bg=BG)
        _cwin_rg = _cv_rg.create_window((0, 0), window=_inner_rg, anchor="nw")
        _inner_rg.bind("<Configure>", lambda e: _cv_rg.configure(scrollregion=_cv_rg.bbox("all")))
        _cv_rg.bind("<Configure>", lambda e: _cv_rg.itemconfig(_cwin_rg, width=e.width))
        _cv_rg.bind("<Enter>", lambda e: _cv_rg.bind_all("<MouseWheel>",
            lambda ev: _cv_rg.yview_scroll(int(-1*(ev.delta/120)), "units")))
        _cv_rg.bind("<Leave>", lambda e: _cv_rg.unbind_all("<MouseWheel>"))
        self._extraer_rg_module = ExtraerDatosRGModule()
        self._extraer_rg_module._build(container=_inner_rg)

        # ─── Panel 8: Cruzar remesas (RG vs Excel externo) ─────────────────────
        panel_cruce = tk.Frame(content_area, bg=BG)
        self._nav_panels["cruzar_remesas"] = panel_cruce
        _wrap_cr = tk.Frame(panel_cruce, bg=BG)
        _wrap_cr.pack(fill=tk.BOTH, expand=True)
        _cv_cr = tk.Canvas(_wrap_cr, bg=BG, highlightthickness=0)
        _sb_cr = ttk.Scrollbar(_wrap_cr, orient="vertical", command=_cv_cr.yview)
        _cv_cr.configure(yscrollcommand=_sb_cr.set)
        _sb_cr.pack(side=tk.RIGHT, fill=tk.Y)
        _cv_cr.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        _inner_cr = tk.Frame(_cv_cr, bg=BG)
        _cwin_cr = _cv_cr.create_window((0, 0), window=_inner_cr, anchor="nw")
        _inner_cr.bind("<Configure>", lambda e: _cv_cr.configure(scrollregion=_cv_cr.bbox("all")))
        _cv_cr.bind("<Configure>", lambda e: _cv_cr.itemconfig(_cwin_cr, width=e.width))
        _cv_cr.bind("<Enter>", lambda e: _cv_cr.bind_all("<MouseWheel>",
            lambda ev: _cv_cr.yview_scroll(int(-1*(ev.delta/120)), "units")))
        _cv_cr.bind("<Leave>", lambda e: _cv_cr.unbind_all("<MouseWheel>"))
        self._cruzar_remesas_module = CruzarRemesasModule()
        self._cruzar_remesas_module._build(container=_inner_cr)

        # ─── Panel 9: Corregir remesa (RNDC proceso 38) ────────────────────────
        panel_corr = tk.Frame(content_area, bg=BG)
        self._nav_panels["corregir_remesa"] = panel_corr
        _wrap_co = tk.Frame(panel_corr, bg=BG)
        _wrap_co.pack(fill=tk.BOTH, expand=True)
        _cv_co = tk.Canvas(_wrap_co, bg=BG, highlightthickness=0)
        _sb_co = ttk.Scrollbar(_wrap_co, orient="vertical", command=_cv_co.yview)
        _cv_co.configure(yscrollcommand=_sb_co.set)
        _sb_co.pack(side=tk.RIGHT, fill=tk.Y)
        _cv_co.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        _inner_co = tk.Frame(_cv_co, bg=BG)
        _cwin_co = _cv_co.create_window((0, 0), window=_inner_co, anchor="nw")
        _inner_co.bind("<Configure>", lambda e: _cv_co.configure(scrollregion=_cv_co.bbox("all")))
        _cv_co.bind("<Configure>", lambda e: _cv_co.itemconfig(_cwin_co, width=e.width))
        _cv_co.bind("<Enter>", lambda e: _cv_co.bind_all("<MouseWheel>",
            lambda ev: _cv_co.yview_scroll(int(-1*(ev.delta/120)), "units")))
        _cv_co.bind("<Leave>", lambda e: _cv_co.unbind_all("<MouseWheel>"))
        self._corregir_remesa_module = CorregirRemesaModule(perfil_fn=self._perfil_activo)
        self._corregir_remesa_module._build(container=_inner_co)

        # ─── Panel 10: Anular cumplido remesa (RNDC proceso 28) ────────────────
        panel_anc = tk.Frame(content_area, bg=BG)
        self._nav_panels["anular_cumplido"] = panel_anc
        _wrap_an = tk.Frame(panel_anc, bg=BG)
        _wrap_an.pack(fill=tk.BOTH, expand=True)
        _cv_an = tk.Canvas(_wrap_an, bg=BG, highlightthickness=0)
        _sb_an = ttk.Scrollbar(_wrap_an, orient="vertical", command=_cv_an.yview)
        _cv_an.configure(yscrollcommand=_sb_an.set)
        _sb_an.pack(side=tk.RIGHT, fill=tk.Y)
        _cv_an.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        _inner_an = tk.Frame(_cv_an, bg=BG)
        _cwin_an = _cv_an.create_window((0, 0), window=_inner_an, anchor="nw")
        _inner_an.bind("<Configure>", lambda e: _cv_an.configure(scrollregion=_cv_an.bbox("all")))
        _cv_an.bind("<Configure>", lambda e: _cv_an.itemconfig(_cwin_an, width=e.width))
        _cv_an.bind("<Enter>", lambda e: _cv_an.bind_all("<MouseWheel>",
            lambda ev: _cv_an.yview_scroll(int(-1*(ev.delta/120)), "units")))
        _cv_an.bind("<Leave>", lambda e: _cv_an.unbind_all("<MouseWheel>"))
        self._anular_cumplido_module = AnularCumplidoRemesaModule(perfil_fn=self._perfil_activo)
        self._anular_cumplido_module._build(container=_inner_an)

        # ─── Panel 11: Cumplir remesa (RNDC proceso 5) ─────────────────────────
        panel_cum = tk.Frame(content_area, bg=BG)
        self._nav_panels["cumplir_remesa"] = panel_cum
        _wrap_cu = tk.Frame(panel_cum, bg=BG)
        _wrap_cu.pack(fill=tk.BOTH, expand=True)
        _cv_cu = tk.Canvas(_wrap_cu, bg=BG, highlightthickness=0)
        _sb_cu = ttk.Scrollbar(_wrap_cu, orient="vertical", command=_cv_cu.yview)
        _cv_cu.configure(yscrollcommand=_sb_cu.set)
        _sb_cu.pack(side=tk.RIGHT, fill=tk.Y)
        _cv_cu.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        _inner_cu = tk.Frame(_cv_cu, bg=BG)
        _cwin_cu = _cv_cu.create_window((0, 0), window=_inner_cu, anchor="nw")
        _inner_cu.bind("<Configure>", lambda e: _cv_cu.configure(scrollregion=_cv_cu.bbox("all")))
        _cv_cu.bind("<Configure>", lambda e: _cv_cu.itemconfig(_cwin_cu, width=e.width))
        _cv_cu.bind("<Enter>", lambda e: _cv_cu.bind_all("<MouseWheel>",
            lambda ev: _cv_cu.yview_scroll(int(-1*(ev.delta/120)), "units")))
        _cv_cu.bind("<Leave>", lambda e: _cv_cu.unbind_all("<MouseWheel>"))
        self._cumplir_remesa_module = CumplirRemesaModule(perfil_fn=self._perfil_activo)
        self._cumplir_remesa_module._build(container=_inner_cu)

        # ─── Panel 12: Proceso completo remesa (orquestador) ───────────────────
        panel_pc = tk.Frame(content_area, bg=BG)
        self._nav_panels["proceso_completo"] = panel_pc
        _wrap_pc = tk.Frame(panel_pc, bg=BG)
        _wrap_pc.pack(fill=tk.BOTH, expand=True)
        _cv_pc = tk.Canvas(_wrap_pc, bg=BG, highlightthickness=0)
        _sb_pc = ttk.Scrollbar(_wrap_pc, orient="vertical", command=_cv_pc.yview)
        _cv_pc.configure(yscrollcommand=_sb_pc.set)
        _sb_pc.pack(side=tk.RIGHT, fill=tk.Y)
        _cv_pc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        _inner_pc = tk.Frame(_cv_pc, bg=BG)
        _cwin_pc = _cv_pc.create_window((0, 0), window=_inner_pc, anchor="nw")
        _inner_pc.bind("<Configure>", lambda e: _cv_pc.configure(scrollregion=_cv_pc.bbox("all")))
        _cv_pc.bind("<Configure>", lambda e: _cv_pc.itemconfig(_cwin_pc, width=e.width))
        _cv_pc.bind("<Enter>", lambda e: _cv_pc.bind_all("<MouseWheel>",
            lambda ev: _cv_pc.yview_scroll(int(-1*(ev.delta/120)), "units")))
        _cv_pc.bind("<Leave>", lambda e: _cv_pc.unbind_all("<MouseWheel>"))
        self._proceso_completo_module = ProcesoCompletoRemesaModule(perfil_fn=self._perfil_activo)
        self._proceso_completo_module._build(container=_inner_pc)

        # ─── Panel 13: Anular cumplido manifiesto (RNDC proceso 29) ────────────
        panel_acm = tk.Frame(content_area, bg=BG)
        self._nav_panels["anular_cumplido_manifiesto"] = panel_acm
        _wrap_acm = tk.Frame(panel_acm, bg=BG)
        _wrap_acm.pack(fill=tk.BOTH, expand=True)
        _cv_acm = tk.Canvas(_wrap_acm, bg=BG, highlightthickness=0)
        _sb_acm = ttk.Scrollbar(_wrap_acm, orient="vertical", command=_cv_acm.yview)
        _cv_acm.configure(yscrollcommand=_sb_acm.set)
        _sb_acm.pack(side=tk.RIGHT, fill=tk.Y)
        _cv_acm.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        _inner_acm = tk.Frame(_cv_acm, bg=BG)
        _cwin_acm = _cv_acm.create_window((0, 0), window=_inner_acm, anchor="nw")
        _inner_acm.bind("<Configure>", lambda e: _cv_acm.configure(scrollregion=_cv_acm.bbox("all")))
        _cv_acm.bind("<Configure>", lambda e: _cv_acm.itemconfig(_cwin_acm, width=e.width))
        _cv_acm.bind("<Enter>", lambda e: _cv_acm.bind_all("<MouseWheel>",
            lambda ev: _cv_acm.yview_scroll(int(-1*(ev.delta/120)), "units")))
        _cv_acm.bind("<Leave>", lambda e: _cv_acm.unbind_all("<MouseWheel>"))
        self._anular_cumplido_manifiesto_module = AnularCumplidoManifiestoModule(perfil_fn=self._perfil_activo)
        self._anular_cumplido_manifiesto_module._build(container=_inner_acm)

        # Activar panel inicial
        root.after(50, lambda: _show_panel("generar"))

        # ── Barra de estado ───────────────────────────────────────────────────
        self.status_bar = tk.Label(root, text="  Listo.",
                                   font=FONT_SMALL, bg=BG2, fg=TEXT2,
                                   anchor="w", pady=5)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    # ── Helpers de construcción UI ────────────────────────────────────────────

    def _card(self, parent, title, **pack_kw):
        """Retorna el frame interior de una card con título."""
        outer = tk.Frame(parent, bg=BG2, bd=0)
        outer.pack(fill=tk.X, **pack_kw)
        title_row = tk.Frame(outer, bg=BG2)
        title_row.pack(fill=tk.X, padx=12, pady=(10, 4))
        tk.Label(title_row, text=title, font=FONT_H2,
                 bg=BG2, fg=TEXT).pack(side=tk.LEFT)
        tk.Frame(outer, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=(0, 8))
        inner = tk.Frame(outer, bg=BG2)
        inner.pack(fill=tk.X, padx=12, pady=(0, 12))
        return inner

    def _section(self, parent, title, fields, content_parent, **pack_kw):
        inner = self._card(parent, title, **pack_kw)
        for label, attr, default, is_pass in fields:
            row = tk.Frame(inner, bg=BG2)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=label, font=FONT_BODY, bg=BG2,
                     fg=TEXT2, width=28, anchor="w").pack(side=tk.LEFT)
            var = tk.StringVar(value=default)
            ent = tk.Entry(row, textvariable=var, font=FONT_BODY,
                           bg=BG3, fg=TEXT, insertbackground=TEXT,
                           relief="flat", highlightthickness=1,
                           highlightbackground=BORDER, highlightcolor=ACCENT,
                           show="*" if is_pass else "")
            ent.pack(side=tk.LEFT, fill=tk.X, expand=True)
            if attr:
                setattr(self, attr, ent)
                setattr(self, attr.replace("ent_", "var_", 1) if attr.startswith("ent_") else attr + "_var", var)

    def _flat_btn(self, parent, text, cmd, bg, hover_bg,
                  height=22, font=FONT_BODY):
        b = tk.Label(parent, text=text, font=font,
                     bg=bg, fg="white", cursor="hand2",
                     padx=12, pady=height // 4)
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>",    lambda e: b.configure(bg=hover_bg))
        b.bind("<Leave>",    lambda e: b.configure(bg=bg))
        return b

    # ── Remesas ───────────────────────────────────────────────────────────────

    def _make_numeric_validator(self):
        def _validate(new_val):
            return True
        return (self.root.register(_validate), '%P')

    def _agregar_remesa(self):
        idx = len(self.rem_rows) + 1
        row_bg = BG3 if idx % 2 == 0 else BG2
        frame = tk.Frame(self.rem_container, bg=row_bg)
        frame.grid(row=idx - 1, column=0, columnspan=6, sticky="ew", pady=1)
        self.rem_container.grid_columnconfigure(5, weight=1)

        tk.Label(frame, text=str(idx), font=FONT_SMALL, bg=row_bg,
                 fg=TEXT2, width=3, anchor="center").grid(row=0, column=0, padx=(4,2), pady=4)

        fields_rem = [
            ("consec", 14, False), ("radicado", 14, False),
            ("valor",  12, False), ("peso",      9, False),
        ]
        row_data = {"frame": frame}
        vcmd = self._vcmd_num

        for col_i, (fname, w, _is_pass) in enumerate(fields_rem, start=1):
            var = tk.StringVar()
            ent = tk.Entry(frame, textvariable=var, font=FONT_BODY, width=w,
                           bg=BG3 if row_bg == BG2 else BG2,
                           fg=TEXT, insertbackground=TEXT,
                           relief="flat", highlightthickness=1,
                           highlightbackground=BORDER, highlightcolor=ACCENT,
                           validate="key", validatecommand=vcmd if fname == "valor" else ("",))
            ent.grid(row=0, column=col_i, padx=2, pady=4, sticky="ew")
            row_data[fname] = var
            # Al salir del campo consecutivo, consultar radicado automáticamente
            if fname == "consec":
                ent.bind("<FocusOut>", lambda e, rd=row_data: self._autocompletar_radicado(rd))

        # Descripción línea
        desc_var = tk.StringVar(value="Servicio de transporte")
        desc_ent = tk.Entry(frame, textvariable=desc_var, font=FONT_BODY,
                            bg=BG3 if row_bg == BG2 else BG2,
                            fg=TEXT, insertbackground=TEXT,
                            relief="flat", highlightthickness=1,
                            highlightbackground=BORDER, highlightcolor=ACCENT)
        desc_ent.grid(row=0, column=5, padx=2, pady=4, sticky="ew")
        row_data["descripcion_linea"] = desc_var

        self.rem_rows.append(row_data)

    def _quitar_remesa(self):
        if len(self.rem_rows) > 1:
            row = self.rem_rows.pop()
            row["frame"].destroy()

    def _autocompletar_radicado(self, row_data):
        """
        Al salir del campo 'consec', consulta el INGRESOID y CANTIDADCARGADA
        en el RNDC y autorrellena 'radicado' y 'peso'.
        Siempre reconsulta (permite corrección si cambia perfil o consecutivo).
        """
        consec = row_data["consec"].get().strip()
        if not consec:
            return

        self._set_status(f"🔍 Consultando radicado para remesa {consec}…", TEXT2)
        self.root.update_idletasks()

        perfil = self._perfil_activo()
        ok, resultado = consultar_radicado_remesa(consec, perfil)
        if ok:
            radicado = resultado.get("radicado", "")
            peso     = resultado.get("peso", "")
            # Siempre sobreescribir ambos campos (limpia datos de perfil anterior)
            row_data["radicado"].set(radicado)
            row_data["peso"].set(peso)
            msg = f"✓ Remesa {consec}: radicado={radicado}"
            if peso != "":
                msg += f"  peso={peso} KGM"
            else:
                msg += "  (peso no disponible vía WS, ingréselo manualmente)"
            self._set_status(msg, SUCCESS)
        else:
            self._set_status(
                f"⚠ No se encontró radicado para remesa {consec}: {resultado}", WARNING)

    # ── Perfil ────────────────────────────────────────────────────────────────

    def _perfil_activo(self):
        return PERFILES.get(self._perfil_var.get(), PERFILES["ut_tsp"])

    def _sel_perfil(self, pid):
        self._perfil_var.set(pid)
        for k, b in self._prof_btns.items():
            b.configure(bg=ACCENT if k == pid else BG3)
        # Notificar módulos embebidos del cambio de perfil
        p = self._perfil_activo()
        # Módulo RNDC: actualizar NIT, usuario, contraseña y etiqueta empresa
        if hasattr(self, "_rndc_uploader"):
            ru = self._rndc_uploader
            if hasattr(ru, "_nit_var"):
                ru._nit_var.set(p.get("nit_socio", ""))
            if hasattr(ru, "_user_var"):
                ru._user_var.set(p.get("rndc_usuario", ""))
            if hasattr(ru, "_pass_var"):
                ru._pass_var.set(p.get("rndc_password", ""))
            if hasattr(ru, "_lbl_empresa"):
                ru._lbl_empresa.configure(
                    text=f"{p.get('nombre_socio','')}  ·  Perfil: {p.get('nombre','')}")
        # Módulo Excel: perfil_fn ya es un callable al activo, no necesita cambio explícito
        if hasattr(self, "_excel_loader"):
            self._excel_loader.perfil_fn = self._perfil_activo
        # Módulo Reconstruir: refrescar etiquetas del perfil
        if hasattr(self, "_reconstruir_module"):
            self._reconstruir_module._refrescar_perfil()
        # Módulo Generar XML: limpiar radicado/peso de remesas y re-consultar
        if hasattr(self, "rem_rows"):
            for rd in self.rem_rows:
                consec = rd.get("consec") and rd["consec"].get().strip()
                if consec:
                    if rd.get("radicado"):
                        rd["radicado"].set("")
                    if rd.get("peso"):
                        rd["peso"].set("")
                    self._autocompletar_radicado(rd)

    # ── Estado ────────────────────────────────────────────────────────────────

    def _set_status(self, msg, color=None):
        if color is None:
            color = TEXT2
        self.status_bar.configure(text=f"  {msg}", fg=color)

    # ── Cargar Excel ──────────────────────────────────────────────────────────

    def _cargar_excel(self):
        """Scroll al módulo Excel embebido."""
        self._nav_activate.get("excel", lambda: None)()

    # ── Subir al RNDC ─────────────────────────────────────────────────────────

    def _subir_rndc(self):
        """Scroll al módulo RNDC embebido."""
        self._nav_activate.get("rndc", lambda: None)()

    # ── Generar XML ───────────────────────────────────────────────────────────

    def _generar(self):
        try:
            nf        = self.ent_nf.get().strip()
            cufe      = self.ent_cufe.get().strip()
            fecha     = self.ent_fecha.get().strip()
            val_total = self.ent_total.get().strip()
            nit_cli   = self.ent_nit_cli.get().strip()
            dig_cli   = self.ent_dig_cli.get().strip() or "5"
            nom_cli   = self.ent_nom_cli.get().strip()

            if not all([nf, cufe, fecha, val_total, nit_cli, nom_cli]):
                messagebox.showwarning("Faltan datos",
                    "Completa: Número factura, CUFE, Fecha, Valor total, NIT y Nombre del cliente.")
                return

            # Validar fecha
            for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    fecha_iso = datetime.strptime(fecha, fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            else:
                messagebox.showwarning("Fecha inválida",
                    "Usa formato DD-MM-YYYY (ej: 13-06-2025)")
                return

            try:
                val_total_f = _parse_valor(val_total)
            except ValueError:
                messagebox.showwarning("Valor inválido", "El valor total debe ser numérico.\nFormatos aceptados: 611.111,00 · 611,111.00 · 611111")
                return

            remesas = []
            for r in self.rem_rows:
                consec  = r["consec"].get().strip()
                radicado= r["radicado"].get().strip()
                valor   = r["valor"].get().strip()
                peso    = r["peso"].get().strip() or "1"
                desc    = r["descripcion_linea"].get().strip() or "Servicio de transporte"
                if not all([consec, radicado, valor]):
                    messagebox.showwarning("Remesa incompleta",
                        "Cada remesa debe tener Consecutivo, Radicado y Valor.")
                    return
                try:
                    valor_f = _parse_valor(valor)
                except ValueError:
                    messagebox.showwarning("Valor inválido", f"Valor de remesa inválido: {valor}\nFormatos aceptados: 611.111,00 · 611,111.00 · 611111")
                    return
                remesas.append({
                    "consecutivo": consec,
                    "radicado": radicado,
                    "peso": peso,
                    "valor": valor_f,
                    "descripcion_linea": desc,
                })

            datos = {
                "numero_factura": nf, "cufe": cufe, "fecha": fecha_iso,
                "nit_cliente": nit_cli, "digito_cliente": dig_cli,
                "nombre_cliente": nom_cli,
                "valor_total": val_total_f, "remesas": remesas
            }

            perfil = self._perfil_activo()
            xml_content = generar_xml(datos, perfil=perfil)

            _carpeta = perfil["carpeta"]
            os.makedirs(_carpeta, exist_ok=True)
            ruta = os.path.join(_carpeta, f"FACTURA_{nf}.xml")
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(xml_content)

            self._set_status(f"✓ XML generado → {ruta}", SUCCESS)
            orig = self.btn_gen.cget("text")
            self.btn_gen.configure(text="GENERADO ✓", bg=SUCCESS)
            self.root.after(2500, lambda: self.btn_gen.configure(text=orig, bg=ACCENT))

        except Exception as e:
            import traceback
            messagebox.showerror("Error", f"{e}\n\n{traceback.format_exc()[:600]}")
