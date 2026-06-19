import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import pandas as pd
    PANDAS_OK = True
except ImportError:
    PANDAS_OK = False

from config.theme import (
    BG, BG2, BG3, ACCENT, ACCENT2, SUCCESS, WARNING, DANGER,
    TEXT, TEXT2, BORDER, FONT_H1, FONT_H2, FONT_BODY, FONT_SMALL,
)
from services.rndc_service import consultar_radicado_remesa


class ConsultarRemesasModule:

    COLUMNAS = [
        ("Consecutivo",   13),
        ("Radicado",      14),
        ("Peso (KG)",      9),
        ("N° Manifiesto", 16),
        ("Propietario",   20),
        ("Origen",        18),
        ("Destino",       18),
        ("Estado",        24),
    ]

    def __init__(self, parent, perfil_fn):
        self.parent    = parent
        self.perfil_fn = perfil_fn

    # ── Copiar tabla al portapapeles ──────────────────────────────────────────

    @staticmethod
    def _copiar_tree(win, tree, headers):
        """Copia el contenido de un Treeview (encabezados + filas) al portapapeles
        como texto separado por tabulaciones (pegable en Excel)."""
        filas = [tree.item(i, "values") for i in tree.get_children()]
        if not filas:
            messagebox.showinfo("Sin datos", "No hay filas para copiar.")
            return
        lineas = ["\t".join(str(h) for h in headers)]
        for f in filas:
            lineas.append("\t".join("" if v is None else str(v) for v in f))
        win.clipboard_clear()
        win.clipboard_append("\n".join(lineas))
        messagebox.showinfo("Copiado", f"{len(filas)} fila(s) copiadas al portapapeles.")

    @staticmethod
    def _hacer_celda_copiable(tree):
        """Doble clic en una celda → campo con el texto seleccionado para copiar."""
        def _on_dbl(event):
            if tree.identify_region(event.x, event.y) != "cell":
                return
            col = tree.identify_column(event.x)
            row = tree.identify_row(event.y)
            if not row:
                return
            try:
                idx   = int(col.replace("#", "")) - 1
                valor = tree.item(row, "values")[idx]
            except Exception:
                return
            bbox = tree.bbox(row, col)
            if not bbox:
                return
            x, y, w, h = bbox
            var = tk.StringVar(value=str(valor))
            ent = tk.Entry(tree, textvariable=var, relief="flat",
                           font=FONT_BODY, bg="#fff7d6", fg="#111111",
                           insertbackground="#111111")
            ent.place(x=x, y=y, width=max(w, 120), height=h)
            ent.focus_set()
            ent.selection_range(0, tk.END)
            ent.icursor(tk.END)
            ent.bind("<FocusOut>", lambda e: ent.destroy())
            ent.bind("<Escape>",   lambda e: ent.destroy())
            ent.bind("<Return>",   lambda e: ent.destroy())
        tree.bind("<Double-1>", _on_dbl)

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _campo(self, parent, etiqueta, var, row, col_start=0, ancho=22):
        tk.Label(parent, text=etiqueta, font=FONT_SMALL, bg=BG2,
                 fg=TEXT2, anchor="w").grid(
                 row=row*2, column=col_start, sticky="w",
                 padx=(14, 4), pady=(8, 0))
        ent = tk.Entry(parent, textvariable=var, font=FONT_BODY,
                       width=ancho, bg=BG3, fg=TEXT,
                       disabledforeground=TEXT, disabledbackground=BG3,
                       relief="flat", bd=4, state="disabled")
        ent.grid(row=row*2+1, column=col_start, sticky="ew",
                 padx=(14, 8), pady=(2, 6))
        return ent

    def _mk_tree_style(self, name):
        s = ttk.Style()
        s.configure(f"{name}.Treeview",
                    background=BG2, fieldbackground=BG2, foreground=TEXT,
                    rowheight=26, font=FONT_BODY, borderwidth=0)
        s.configure(f"{name}.Treeview.Heading",
                    background=BG3, foreground=TEXT2,
                    font=FONT_SMALL, relief="flat")
        s.map(f"{name}.Treeview",
              background=[("selected", ACCENT)],
              foreground=[("selected", "#ffffff")])

    def _build(self, container):
        self.win = container.winfo_toplevel()

        # Header
        hdr = tk.Frame(container, bg=BG2, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="🔍  Consultar Remesas", font=FONT_H1,
                 bg=BG2, fg=TEXT).pack(padx=20)
        tk.Label(hdr, text="Consulta remesas y sus estados en el RNDC",
                 font=FONT_BODY, bg=BG2, fg=TEXT2).pack(padx=20, pady=(2, 4))

        # Fila de entrada
        inp_row = tk.Frame(container, bg=BG, pady=10)
        inp_row.pack(fill=tk.X, padx=18)
        tk.Label(inp_row, text="Consecutivo:", font=FONT_BODY,
                 bg=BG, fg=TEXT2).pack(side=tk.LEFT)

        self._var_consec = tk.StringVar()
        ent = tk.Entry(inp_row, textvariable=self._var_consec,
                       font=FONT_BODY, width=18,
                       bg=BG3, fg=TEXT, insertbackground=TEXT,
                       relief="flat", bd=4)
        ent.pack(side=tk.LEFT, padx=(8, 10))
        ent.bind("<Return>", lambda e: self._consultar())

        for txt, bg, cmd in [
            ("  Consultar  ", ACCENT,  self._consultar),
            ("  Limpiar  ",   BG3,     self._limpiar),
            ("  📋 Consulta masiva  ", ACCENT2, self._abrir_modal_excel),
        ]:
            b = tk.Label(inp_row, text=txt, font=FONT_BODY,
                         bg=bg, fg="white" if bg != BG3 else TEXT2,
                         cursor="hand2", padx=8, pady=4)
            b.pack(side=tk.LEFT, padx=(0, 6))
            b.bind("<Button-1>", lambda e, f=cmd: f())

        # Barra de estado
        self._lbl_status = tk.Label(container, text="", font=FONT_SMALL,
                                    bg=BG, fg=TEXT2, anchor="w")
        self._lbl_status.pack(fill=tk.X, padx=20, pady=(0, 2))

        # Ficha de resultado
        ficha_outer = tk.Frame(container, bg=BG2, padx=4, pady=4)
        ficha_outer.pack(fill=tk.X, padx=18, pady=(4, 8))
        tk.Label(ficha_outer, text="Datos de la remesa", font=FONT_H2,
                 bg=BG2, fg=TEXT2).pack(anchor="w", padx=10, pady=(4, 0))
        tk.Frame(ficha_outer, bg=BORDER, height=1).pack(fill=tk.X, padx=10, pady=(4, 0))

        ficha = tk.Frame(ficha_outer, bg=BG2)
        ficha.pack(fill=tk.X)

        self._v = {k: tk.StringVar() for k in
                   ("radicado", "propietario", "origen", "destino", "cantidad", "estado", "manifiesto")}

        self._campo(ficha, "Radicado",       self._v["radicado"],    row=0, col_start=0, ancho=20)
        self._campo(ficha, "Cantidad",       self._v["cantidad"],    row=0, col_start=2, ancho=12)
        self._campo(ficha, "N° Manifiesto",  self._v["manifiesto"],  row=0, col_start=4, ancho=16)
        self._campo(ficha, "Propietario",    self._v["propietario"], row=1, col_start=0, ancho=44)
        self._campo(ficha, "Origen",         self._v["origen"],      row=2, col_start=0, ancho=22)
        self._campo(ficha, "Destino",        self._v["destino"],     row=2, col_start=2, ancho=22)
        tk.Label(ficha, text="Estado", font=FONT_SMALL, bg=BG2,
                 fg=TEXT2, anchor="w").grid(row=6, column=0, sticky="w",
                 padx=(14, 4), pady=(8, 0))
        self._lbl_estado = tk.Label(ficha, textvariable=self._v["estado"],
                                    font=("Segoe UI", 9, "bold"),
                                    bg=BG2, fg=TEXT2, anchor="w")
        self._lbl_estado.grid(row=7, column=0, columnspan=4, sticky="w",
                              padx=(14, 8), pady=(2, 8))
        ficha.columnconfigure(0, weight=2)
        ficha.columnconfigure(2, weight=1)

        # Historial
        hist_hdr = tk.Frame(container, bg=BG2)
        hist_hdr.pack(fill=tk.X, padx=18)
        tk.Label(hist_hdr, text="Historial de consultas", font=FONT_H2,
                 bg=BG2, fg=TEXT).pack(side=tk.LEFT, padx=12, pady=6)
        _btn_copiar = tk.Label(hist_hdr, text="📋  Copiar tabla", font=FONT_SMALL,
                               bg=ACCENT2, fg="white", cursor="hand2", padx=10, pady=3)
        _btn_copiar.pack(side=tk.RIGHT, padx=12)
        _btn_copiar.bind("<Button-1>", lambda e: self._copiar_tree(
            self.win, self._tree, [c[0] for c in self.COLUMNAS]))
        tk.Frame(container, bg=BORDER, height=1).pack(fill=tk.X, padx=18)

        self._mk_tree_style("Cons")
        tbl_frame = tk.Frame(container, bg=BG2)
        tbl_frame.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 12))

        cols = [c[0] for c in self.COLUMNAS]
        self._tree = ttk.Treeview(tbl_frame, columns=cols, show="headings",
                                  style="Cons.Treeview", selectmode="browse")
        vsb = ttk.Scrollbar(tbl_frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(tbl_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._tree.pack(fill=tk.BOTH, expand=True)

        for nombre, ancho in self.COLUMNAS:
            self._tree.heading(nombre, text=nombre)
            self._tree.column(nombre, width=ancho*8, anchor="w", minwidth=60)

        self._tree.tag_configure("ok",    background=BG2, foreground="#4ade80")
        self._tree.tag_configure("warn",  background=BG2, foreground="#fbbf24")
        self._tree.tag_configure("error", background=BG2, foreground="#f87171")
        self._hacer_celda_copiable(self._tree)

        ent.focus_set()
        self._ent = ent

    # ── Helpers de estado ─────────────────────────────────────────────────────

    def _estado_txt_color(self, cod, manifiesto=""):
        # AC sin manifiesto asignado → pendiente de asignar manifiesto
        if cod == "AC" and not str(manifiesto).strip():
            return "📋 Pendiente de asignar manifiesto", "#fbbf24"
        if cod == "CE":
            return "✓ Cumplida", "#4ade80"
        elif cod == "AC":
            return "⏳ Pendiente por cumplir", "#fbbf24"
        elif cod:
            return cod, TEXT2
        return "—", TEXT2

    def _limpiar_ficha(self):
        for v in self._v.values():
            v.set("")
        self._lbl_estado.configure(fg=TEXT2)

    # ── Modal Excel ───────────────────────────────────────────────────────────

    def _abrir_modal_excel(self):
        try:
            import pandas as pd
        except ImportError:
            messagebox.showerror("Error", "pandas no está instalado.\nEjecuta: pip install pandas openpyxl")
            return

        import re as _re

        modal = tk.Toplevel(self.win)
        modal.title("Consulta masiva de remesas")
        modal.configure(bg=BG)
        modal.geometry("680x620")
        modal.resizable(True, True)
        modal.grab_set()
        modal.transient(self.win)

        var_status = tk.StringVar(value="Selecciona una fuente de datos para comenzar.")

        tk.Label(modal, text="📋  Consulta masiva de remesas", font=FONT_H2,
                 bg=BG, fg=TEXT, pady=12).pack(fill=tk.X, padx=20)
        tk.Frame(modal, bg=BORDER, height=1).pack(fill=tk.X, padx=20)

        # ── Pestañas: Pegar texto / Desde Excel ──────────────────────────────
        nb = ttk.Notebook(modal)
        nb.pack(fill=tk.X, padx=20, pady=(10, 0))

        # ── Tab 1: Pegar consecutivos ─────────────────────────────────────────
        tab_texto = tk.Frame(nb, bg=BG, padx=10, pady=10)
        nb.add(tab_texto, text="  ✏️  Pegar consecutivos  ")

        tk.Label(tab_texto,
                 text="Pega los consecutivos separados por comas, espacios o saltos de línea:",
                 font=FONT_SMALL, bg=BG, fg=TEXT2).pack(anchor="w")
        txt_frame = tk.Frame(tab_texto, bg=BG3)
        txt_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        txt_consec = tk.Text(txt_frame, font=FONT_BODY, width=60, height=5,
                             bg=BG3, fg=TEXT, insertbackground=TEXT,
                             relief="flat", bd=4, wrap="word")
        txt_consec.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb_txt = ttk.Scrollbar(txt_frame, orient="vertical", command=txt_consec.yview)
        vsb_txt.pack(side=tk.RIGHT, fill=tk.Y)
        txt_consec.configure(yscrollcommand=vsb_txt.set)

        # ── Tab 2: Desde Excel ────────────────────────────────────────────────
        tab_excel = tk.Frame(nb, bg=BG, padx=10, pady=10)
        nb.add(tab_excel, text="  📂  Desde Excel  ")

        state    = {"df": None, "ruta": None}
        var_hoja = tk.StringVar()
        var_col  = tk.StringVar()

        tk.Label(tab_excel, text="Archivo Excel:", font=FONT_BODY,
                 bg=BG, fg=TEXT2).pack(anchor="w")
        fila_arch = tk.Frame(tab_excel, bg=BG)
        fila_arch.pack(fill=tk.X, pady=(4, 6))
        lbl_ruta = tk.Label(fila_arch, text="Sin archivo cargado", font=FONT_SMALL,
                            bg=BG3, fg=TEXT2, anchor="w", padx=8, pady=5,
                            relief="flat", width=44)
        lbl_ruta.pack(side=tk.LEFT, fill=tk.X, expand=True)

        combo_hoja = None
        combo_col  = None

        def _cargar_archivo():
            ruta = filedialog.askopenfilename(
                title="Seleccionar Excel",
                filetypes=[("Excel", "*.xlsx *.xls *.xlsm"), ("Todos", "*.*")])
            if not ruta:
                return
            try:
                xl = pd.ExcelFile(ruta)
                state["ruta"] = ruta
                nombre = ruta.split("/")[-1].split("\\")[-1]
                lbl_ruta.configure(text=nombre, fg=TEXT)
                combo_hoja["values"] = xl.sheet_names
                combo_hoja.set(xl.sheet_names[0] if xl.sheet_names else "")
                _on_hoja()
                var_status.set(f"✓ Archivo cargado: {nombre}")
            except Exception as ex:
                var_status.set(f"✗ Error al cargar: {ex}")

        btn_arch = tk.Label(fila_arch, text=" Examinar ", font=FONT_BODY,
                            bg=ACCENT, fg="white", cursor="hand2", padx=8, pady=5)
        btn_arch.pack(side=tk.LEFT, padx=(8, 0))
        btn_arch.bind("<Button-1>", lambda e: _cargar_archivo())

        fila_hoja = tk.Frame(tab_excel, bg=BG)
        fila_hoja.pack(fill=tk.X, pady=(0, 6))
        tk.Label(fila_hoja, text="Hoja:", font=FONT_BODY,
                 bg=BG, fg=TEXT2, width=8, anchor="w").pack(side=tk.LEFT)
        combo_hoja = ttk.Combobox(fila_hoja, textvariable=var_hoja,
                                  state="readonly", font=FONT_BODY, width=32)
        combo_hoja.pack(side=tk.LEFT)

        def _on_hoja(e=None):
            if not state["ruta"] or not var_hoja.get():
                return
            try:
                df = pd.read_excel(state["ruta"], sheet_name=var_hoja.get(),
                                   header=0, nrows=0)
                cols = list(df.columns.astype(str))
                combo_col["values"] = cols
                combo_col.set(cols[0] if cols else "")
                state["df"] = None
            except Exception as ex:
                var_status.set(f"✗ Error leyendo hoja: {ex}")

        combo_hoja.bind("<<ComboboxSelected>>", _on_hoja)

        fila_col = tk.Frame(tab_excel, bg=BG)
        fila_col.pack(fill=tk.X)
        tk.Label(fila_col, text="Columna:", font=FONT_BODY,
                 bg=BG, fg=TEXT2, width=8, anchor="w").pack(side=tk.LEFT)
        combo_col = ttk.Combobox(fila_col, textvariable=var_col,
                                 state="readonly", font=FONT_BODY, width=32)
        combo_col.pack(side=tk.LEFT)

        # ── Estado + barra de progreso ────────────────────────────────────────
        tk.Frame(modal, bg=BORDER, height=1).pack(fill=tk.X, padx=20, pady=(10, 0))
        lbl_status_m = tk.Label(modal, textvariable=var_status, font=FONT_SMALL,
                                bg=BG, fg=TEXT2, anchor="w", wraplength=600)
        lbl_status_m.pack(fill=tk.X, padx=20, pady=(6, 2))
        pb_frame = tk.Frame(modal, bg=BG)
        pb_frame.pack(fill=tk.X, padx=20, pady=(0, 4))
        pb = ttk.Progressbar(pb_frame, orient="horizontal", mode="determinate")
        pb.pack(fill=tk.X)

        # ── Botones ───────────────────────────────────────────────────────────
        tk.Frame(modal, bg=BORDER, height=1).pack(fill=tk.X, padx=20)
        fila_btns = tk.Frame(modal, bg=BG, pady=8)
        fila_btns.pack(fill=tk.X, padx=20)

        btn_guardar = tk.Label(fila_btns, text="  💾 Guardar resultados  ",
                               font=FONT_BODY, bg=BG3, fg=TEXT2,
                               cursor="hand2", padx=8, pady=5)
        btn_guardar.pack(side=tk.RIGHT, padx=(8, 0))

        btn_consultar_m = tk.Label(fila_btns, text="  Consultar todas  ",
                                   font=FONT_BODY, bg=ACCENT, fg="white",
                                   cursor="hand2", padx=8, pady=5)
        btn_consultar_m.pack(side=tk.RIGHT)

        # ── Tabla de resultados ───────────────────────────────────────────────
        tbl_m_frame = tk.Frame(modal, bg=BG2)
        tbl_m_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

        cols_m = ("Consecutivo", "Radicado", "Peso", "N° Manifiesto",
                  "Propietario", "Origen", "Destino", "Estado")
        self._mk_tree_style("Modal")
        tree_m = ttk.Treeview(tbl_m_frame, columns=cols_m,
                              show="headings", height=7,
                              style="Modal.Treeview", selectmode="browse")
        vsb_m = ttk.Scrollbar(tbl_m_frame, orient="vertical", command=tree_m.yview)
        hsb_m = ttk.Scrollbar(tbl_m_frame, orient="horizontal", command=tree_m.xview)
        tree_m.configure(yscrollcommand=vsb_m.set, xscrollcommand=hsb_m.set)
        vsb_m.pack(side=tk.RIGHT, fill=tk.Y)
        hsb_m.pack(side=tk.BOTTOM, fill=tk.X)
        tree_m.pack(fill=tk.BOTH, expand=True)
        anchos = (13, 13, 8, 14, 18, 14, 14, 18)
        for nombre, ancho in zip(cols_m, anchos):
            tree_m.heading(nombre, text=nombre)
            tree_m.column(nombre, width=ancho * 7, anchor="w", minwidth=50)
        tree_m.tag_configure("ok",    background=BG2, foreground="#4ade80")
        tree_m.tag_configure("warn",  background=BG2, foreground="#fbbf24")
        tree_m.tag_configure("error", background=BG2, foreground="#f87171")
        self._hacer_celda_copiable(tree_m)

        btn_copiar_m = tk.Label(fila_btns, text="  📋 Copiar tabla  ",
                                font=FONT_BODY, bg=ACCENT2, fg="white",
                                cursor="hand2", padx=8, pady=5)
        btn_copiar_m.pack(side=tk.LEFT)
        btn_copiar_m.bind("<Button-1>", lambda e: self._copiar_tree(modal, tree_m, cols_m))

        resultados = []

        def _obtener_consecutivos():
            """Devuelve la lista de consecutivos según la pestaña activa."""
            tab_activa = nb.index(nb.select())
            if tab_activa == 0:
                # Pestaña "Pegar consecutivos"
                texto = txt_consec.get("1.0", tk.END)
                tokens = _re.split(r"[\s,;]+", texto)
                return [t.strip() for t in tokens if t.strip()]
            else:
                # Pestaña "Desde Excel"
                if not state["ruta"] or not var_hoja.get() or not var_col.get():
                    var_status.set("⚠ Selecciona archivo, hoja y columna primero.")
                    return []
                try:
                    df = pd.read_excel(state["ruta"], sheet_name=var_hoja.get(), dtype=str)
                    col = var_col.get()
                    items = df[col].dropna().astype(str).str.strip().tolist()
                    return [c for c in items if c]
                except Exception as ex:
                    var_status.set(f"✗ Error leyendo datos: {ex}")
                    return []

        def _consultar_masivo():
            consecutivos = _obtener_consecutivos()
            if not consecutivos:
                var_status.set("⚠ No hay consecutivos para consultar.")
                return

            for r in tree_m.get_children():
                tree_m.delete(r)
            resultados.clear()

            total = len(consecutivos)
            pb["maximum"] = total
            pb["value"]   = 0
            perfil = self.perfil_fn()

            for i, consec in enumerate(consecutivos, 1):
                var_status.set(f"  Consultando {i}/{total}: remesa {consec}…")
                lbl_status_m.configure(fg=TEXT2)
                modal.update_idletasks()

                ok, resultado = consultar_radicado_remesa(consec, perfil)
                if ok:
                    radicado    = resultado.get("radicado", "")
                    peso        = resultado.get("peso", "")
                    propietario = resultado.get("propietario", "")
                    origen      = resultado.get("origen", "")
                    destino     = resultado.get("destino", "")
                    manifiesto  = resultado.get("manifiesto", "")
                    cod_est     = resultado.get("estado", "")
                    estado_txt, _ = self._estado_txt_color(cod_est, manifiesto)
                    tag = "ok" if cod_est == "CE" else ("warn" if cod_est == "AC" else "ok")
                else:
                    radicado = peso = propietario = origen = destino = manifiesto = "—"
                    estado_txt = "No emitida o cerrada" if "RNDC11" in str(resultado) else str(resultado)[:50]
                    tag = "error"

                tree_m.insert("", "end",
                    values=(consec, radicado, peso, manifiesto,
                            propietario, origen, destino, estado_txt),
                    tags=(tag,))
                resultados.append({
                    "Consecutivo":    consec,
                    "Radicado":       radicado,
                    "Peso (KG)":      peso,
                    "N° Manifiesto":  manifiesto,
                    "Propietario":    propietario,
                    "Origen":         origen,
                    "Destino":        destino,
                    "Estado":         estado_txt,
                })
                pb["value"] = i
                modal.update_idletasks()

            var_status.set(f"  ✓ Consulta finalizada: {total} remesa(s) procesadas.")
            lbl_status_m.configure(fg=SUCCESS)
            btn_guardar.configure(bg=ACCENT2, fg="white")

        def _guardar_resultados():
            if not resultados:
                var_status.set("⚠ No hay resultados para guardar.")
                return
            ruta_out = filedialog.asksaveasfilename(
                title="Guardar resultados",
                defaultextension=".xlsx",
                filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")],
                initialfile="consulta_remesas.xlsx")
            if not ruta_out:
                return
            try:
                df_out = pd.DataFrame(resultados)
                if ruta_out.endswith(".csv"):
                    df_out.to_csv(ruta_out, index=False, encoding="utf-8-sig")
                else:
                    df_out.to_excel(ruta_out, index=False)
                var_status.set(f"  ✓ Guardado en: {ruta_out}")
                lbl_status_m.configure(fg=SUCCESS)
            except Exception as ex:
                var_status.set(f"  ✗ Error al guardar: {ex}")
                lbl_status_m.configure(fg=WARNING)

        btn_consultar_m.bind("<Button-1>", lambda e: _consultar_masivo())
        btn_guardar.bind("<Button-1>", lambda e: _guardar_resultados())

    # ── Lógica de consulta ────────────────────────────────────────────────────

    def _consultar(self):
        consec = self._var_consec.get().strip()
        if not consec:
            self._lbl_status.configure(
                text="  ⚠ Ingresa un consecutivo de remesa.", fg=WARNING)
            return

        self._lbl_status.configure(
            text=f"  🔍 Consultando remesa {consec}…", fg=TEXT2)
        self._limpiar_ficha()
        try:
            self.win.update_idletasks()
        except Exception:
            pass

        perfil = self.perfil_fn()
        ok, resultado = consultar_radicado_remesa(consec, perfil)

        if ok:
            radicado    = resultado.get("radicado", "")
            peso        = resultado.get("peso", "")
            propietario = resultado.get("propietario", "")
            origen      = resultado.get("origen", "")
            destino     = resultado.get("destino", "")
            cod_est     = resultado.get("estado", "")
            manifiesto  = resultado.get("manifiesto", "")
            estado_txt, color = self._estado_txt_color(cod_est, manifiesto)

            self._v["radicado"].set(radicado)
            self._v["propietario"].set(propietario)
            self._v["origen"].set(origen)
            self._v["destino"].set(destino)
            self._v["cantidad"].set(peso if peso != "" else "")
            self._v["estado"].set(estado_txt)
            self._v["manifiesto"].set(manifiesto)
            self._lbl_estado.configure(fg=color)

            tag = "ok" if cod_est == "CE" else ("warn" if cod_est == "AC" else "ok")
            self._tree.insert("", 0,
                values=(consec, radicado, peso, manifiesto, propietario, origen, destino, estado_txt),
                tags=(tag,))

            msg = f"  ✓ Remesa {consec}: radicado={radicado}  estado={estado_txt}"
            self._lbl_status.configure(text=msg, fg=SUCCESS)
        else:
            if "RNDC11" in str(resultado):
                estado_txt = "Remesa no ha sido emitida o ya está cerrada"
            else:
                estado_txt = str(resultado)

            self._limpiar_ficha()
            self._v["estado"].set(f"✗ {estado_txt}")
            self._lbl_estado.configure(fg="#f87171")

            self._tree.insert("", 0,
                values=(consec, "—", "—", "—", "—", "—", "—", f"✗ {estado_txt}"),
                tags=("error",))
            self._lbl_status.configure(
                text=f"  ✗ Remesa {consec}: {estado_txt}", fg=WARNING)

        self._var_consec.set("")
        self._ent.focus_set()

    def _limpiar(self):
        self._limpiar_ficha()
        for row in self._tree.get_children():
            self._tree.delete(row)
        self._lbl_status.configure(text="")
        self._var_consec.set("")
        self._ent.focus_set()
