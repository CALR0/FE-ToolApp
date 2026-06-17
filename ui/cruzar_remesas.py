import re
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
from core.xml_generator import _parse_valor


class CruzarRemesasModule:
    """
    Panel embebido que cruza el Excel exportado por "Extraer Datos RG"
    con otro Excel (que contiene remesas y valores unitarios por factura)
    y genera un tercer Excel con dos columnas de validación:
      - "¿Coinciden remesas?"            (Sí/No)
      - "¿Coincide valor factura con RG?" (Sí/No)

    No modifica nada del módulo ExtraerDatosRGModule existente.
    """

    # Columnas que se intentan mapear en cada uno de los dos archivos
    CAMPOS_RG = [
        ("rg_col_nf",      "N° Factura",            True),
        ("rg_col_val_fac", "Valor total factura",   True),
    ]
    CAMPOS_OTRO = [
        ("otro_col_nf",     "N° Factura",           True),
        ("otro_col_consec", "Consecutivo / Remesa", True),
        ("otro_col_val_un", "Valor unitario remesa", True),
    ]

    # Opciones de filtro para la exportación. El valor es una función que recibe
    # las 3 banderas por factura (remesas, valor, reconstruir) y devuelve True
    # si esa factura debe incluirse en el Excel exportado.
    FILTROS_EXPORT = [
        "Todas",
        "Solo Reconstruir = Sí",
        "Coinciden remesas, NO coincide valor",
        "Coincide valor, NO coinciden remesas",
        "NO coinciden remesas",
        "NO coincide valor",
        "Reconstruir = No (alguna no coincide)",
    ]

    HINTS = {
        "rg_col_nf":       ["factura", "nfactura", "num_fac", "n_factura", "numero_factura"],
        "rg_col_val_fac":  ["valor_total_factura", "valor_factura", "val_fac", "total_factura"],
        "otro_col_nf":     ["factura", "nfactura", "num_fac", "n_factura", "numero_factura"],
        "otro_col_consec": ["remesa", "consecutivo", "consec"],
        "otro_col_val_un": ["valor_unitario", "vr_unitario", "valor_remesa", "val_rem", "vunit"],
    }

    def __init__(self):
        self.df_rg = None
        self.df_otro = None
        self.cols_rg = ["— No usar —"]
        self.cols_otro = ["— No usar —"]
        self.vars = {}
        self.combos = {}
        # ExcelFile, selector de hoja y nombre de archivo por fuente ("rg"/"otro")
        self._xl_files   = {"rg": None, "otro": None}
        self._hoja_vars  = {}
        self._hoja_combos = {}
        self._nombre_archivo = {"rg": "", "otro": ""}
        self._filtro_var = None
        self._filas_resultado = []
        self._mapa_resultado = {}
        self._col_rg_nf = None
        self._consecutivos_otro_por_factura = {}

    # ── Construcción de la UI ────────────────────────────────────────────────

    def _build(self, container):
        self.win = container.winfo_toplevel()

        if not PANDAS_OK:
            tk.Label(container, text="⚠ La librería 'pandas' no está instalada.\n"
                                      "Ejecuta: pip install pandas openpyxl",
                     font=FONT_BODY, bg=BG, fg=DANGER, justify="left").pack(padx=20, pady=20)
            return

        hdr = tk.Frame(container, bg=BG2, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="🔀  Cruzar Remesas (RG vs Excel externo)",
                 font=FONT_H1, bg=BG2, fg=TEXT).pack(padx=20)
        tk.Label(hdr,
                 text="Compara las remesas extraídas de los PDF de RG con la información\n"
                      "de otro Excel (remesa + valor unitario) y valida ambas fuentes.",
                 font=FONT_SMALL, bg=BG2, fg=TEXT2, justify="left").pack(padx=20, pady=(2, 6))

        body = tk.Frame(container, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        # ── Carga de los dos archivos ────────────────────────────────────────
        carga_frame = tk.Frame(body, bg=BG2, padx=12, pady=10)
        carga_frame.pack(fill=tk.X, pady=(0, 10))

        fila_rg = tk.Frame(carga_frame, bg=BG2)
        fila_rg.pack(fill=tk.X, pady=4)
        btn_rg = tk.Label(fila_rg, text="📂  Cargar Excel de RG",
                          font=FONT_BODY, bg=ACCENT, fg="white",
                          cursor="hand2", padx=12, pady=5)
        btn_rg.pack(side=tk.LEFT, padx=(0, 10))
        btn_rg.bind("<Button-1>", lambda e: self._cargar_archivo("rg"))
        tk.Label(fila_rg, text="Hoja:", font=FONT_BODY, bg=BG2, fg=TEXT2
                 ).pack(side=tk.LEFT, padx=(0, 4))
        self._hoja_vars["rg"] = tk.StringVar(value="")
        self._hoja_combos["rg"] = ttk.Combobox(
            fila_rg, textvariable=self._hoja_vars["rg"], values=[],
            state="disabled", font=FONT_BODY, width=22)
        self._hoja_combos["rg"].pack(side=tk.LEFT, padx=(0, 10))
        self._hoja_combos["rg"].bind(
            "<<ComboboxSelected>>", lambda e: self._on_hoja_change("rg"))
        self._lbl_rg = tk.Label(fila_rg, text="Sin archivo cargado.",
                                font=FONT_BODY, bg=BG2, fg=TEXT2, anchor="w")
        self._lbl_rg.pack(side=tk.LEFT, fill=tk.X, expand=True)

        fila_otro = tk.Frame(carga_frame, bg=BG2)
        fila_otro.pack(fill=tk.X, pady=4)
        btn_otro = tk.Label(fila_otro, text="📂  Cargar otro Excel",
                            font=FONT_BODY, bg="#7c3aed", fg="white",
                            cursor="hand2", padx=12, pady=5)
        btn_otro.pack(side=tk.LEFT, padx=(0, 10))
        btn_otro.bind("<Button-1>", lambda e: self._cargar_archivo("otro"))
        tk.Label(fila_otro, text="Hoja:", font=FONT_BODY, bg=BG2, fg=TEXT2
                 ).pack(side=tk.LEFT, padx=(0, 4))
        self._hoja_vars["otro"] = tk.StringVar(value="")
        self._hoja_combos["otro"] = ttk.Combobox(
            fila_otro, textvariable=self._hoja_vars["otro"], values=[],
            state="disabled", font=FONT_BODY, width=22)
        self._hoja_combos["otro"].pack(side=tk.LEFT, padx=(0, 10))
        self._hoja_combos["otro"].bind(
            "<<ComboboxSelected>>", lambda e: self._on_hoja_change("otro"))
        self._lbl_otro = tk.Label(fila_otro, text="Sin archivo cargado.",
                                  font=FONT_BODY, bg=BG2, fg=TEXT2, anchor="w")
        self._lbl_otro.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Grid de mapeo de columnas ─────────────────────────────────────────
        tk.Label(body, text="Mapeo de columnas — Excel de RG",
                 font=FONT_H2, bg=BG, fg=TEXT2).pack(anchor="w", pady=(8, 2))
        self._grid_rg = tk.Frame(body, bg=BG2, padx=12, pady=8)
        self._grid_rg.pack(fill=tk.X, pady=(0, 10))
        self._build_grid(self._grid_rg, self.CAMPOS_RG)

        tk.Label(body, text="Mapeo de columnas — Otro Excel",
                 font=FONT_H2, bg=BG, fg=TEXT2).pack(anchor="w", pady=(4, 2))
        self._grid_otro = tk.Frame(body, bg=BG2, padx=12, pady=8)
        self._grid_otro.pack(fill=tk.X, pady=(0, 10))
        self._build_grid(self._grid_otro, self.CAMPOS_OTRO)

        # ── Acciones ──────────────────────────────────────────────────────────
        act_row = tk.Frame(body, bg=BG, pady=6)
        act_row.pack(fill=tk.X)

        self._btn_cruzar = tk.Label(act_row, text="⚙️  Cruzar información",
                                    font=FONT_BODY, bg="#7c3aed", fg="white",
                                    cursor="hand2", padx=14, pady=6)
        self._btn_cruzar.pack(side=tk.LEFT, padx=(0, 10))
        self._btn_cruzar.bind("<Button-1>", lambda e: self._cruzar())

        tk.Label(act_row, text="Filtro:", font=FONT_BODY, bg=BG, fg=TEXT2
                 ).pack(side=tk.LEFT, padx=(0, 4))
        self._filtro_var = tk.StringVar(value=self.FILTROS_EXPORT[0])
        ttk.Combobox(act_row, textvariable=self._filtro_var,
                     values=self.FILTROS_EXPORT, state="readonly",
                     font=FONT_BODY, width=34).pack(side=tk.LEFT, padx=(0, 10))

        self._btn_exportar = tk.Label(act_row, text="💾  Exportar Excel",
                                      font=FONT_BODY, bg=BG3, fg=TEXT2,
                                      cursor="hand2", padx=14, pady=6)
        self._btn_exportar.pack(side=tk.LEFT)
        self._btn_exportar.bind("<Button-1>", lambda e: self._exportar())

        self._lbl_estado = tk.Label(body, text="", font=FONT_BODY, bg=BG, fg=TEXT2, anchor="w")
        self._lbl_estado.pack(anchor="w", pady=(8, 4))

        # ── Tabla de resultados ──────────────────────────────────────────────
        tbl_frame = tk.Frame(body, bg=BG2)
        tbl_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        s = ttk.Style()
        s.configure("Cruce.Treeview",
                    background=BG2, fieldbackground=BG2, foreground=TEXT,
                    rowheight=24, font=FONT_BODY, borderwidth=0)
        s.configure("Cruce.Treeview.Heading",
                    background=BG3, foreground=TEXT2, font=FONT_SMALL, relief="flat")
        s.map("Cruce.Treeview",
              background=[("selected", ACCENT)],
              foreground=[("selected", "#ffffff")])

        cols = ("N° Factura", "Remesas RG", "Remesas Otro Excel",
                "¿Coinciden remesas?", "Valor Factura RG", "Suma valores Otro Excel",
                "¿Coincide valor factura con RG?", "Reconstruir")
        self._tree = ttk.Treeview(tbl_frame, columns=cols, show="headings",
                                  style="Cruce.Treeview", selectmode="browse")
        vsb = ttk.Scrollbar(tbl_frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(tbl_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._tree.pack(fill=tk.BOTH, expand=True)

        for c, w in zip(cols, (110, 90, 130, 130, 120, 150, 180, 100)):
            self._tree.heading(c, text=c)
            self._tree.column(c, width=w, anchor="center", stretch=False)

        self._tree.tag_configure("ok",  foreground="#4ade80", background=BG2)
        self._tree.tag_configure("err", foreground="#f87171", background=BG2)
        self._tree.tag_configure("alt", background=BG3)

    def _build_grid(self, grid, campos):
        for ci, txt in enumerate(("Campo", "Columna del Excel")):
            tk.Label(grid, text=txt, font=FONT_H2, bg=BG2, fg=TEXT2
                     ).grid(row=0, column=ci, sticky="w", padx=(0, 20), pady=(0, 6))
        for row_i, (clave, etiqueta, req) in enumerate(campos, start=1):
            row_bg = BG3 if row_i % 2 == 0 else BG2
            fila = tk.Frame(grid, bg=row_bg)
            fila.grid(row=row_i, column=0, columnspan=2, sticky="ew", pady=1)
            grid.grid_columnconfigure(0, weight=0)
            grid.grid_columnconfigure(1, weight=1)

            tk.Label(fila, text=f"{'*' if req else '○'}  {etiqueta}", font=FONT_BODY,
                     bg=row_bg, fg=TEXT, width=26, anchor="w").pack(side=tk.LEFT, padx=(8, 4), pady=5)

            var = tk.StringVar(value="— No usar —")
            self.vars[clave] = var
            combo = ttk.Combobox(fila, textvariable=var, values=["— No usar —"],
                                 state="readonly", font=FONT_BODY, width=30)
            combo.pack(side=tk.LEFT, padx=(0, 12), pady=5)
            self.combos[clave] = combo

    # ── Carga de archivos ────────────────────────────────────────────────────

    def _cargar_archivo(self, cual):
        ruta = filedialog.askopenfilename(
            title="Selecciona el archivo Excel",
            filetypes=[("Excel", "*.xlsx *.xls *.xlsm"), ("CSV", "*.csv"), ("Todos", "*.*")])
        if not ruta:
            return

        self._nombre_archivo[cual] = ruta.split("/")[-1].split(chr(92))[-1]
        combo_hoja = self._hoja_combos[cual]

        # CSV: no tiene hojas, se deshabilita el selector
        if ruta.lower().endswith(".csv"):
            try:
                df = pd.read_csv(ruta)
            except Exception as e:
                messagebox.showerror("Error al leer CSV", str(e))
                return
            self._xl_files[cual] = None
            self._hoja_vars[cual].set("")
            combo_hoja.configure(values=[], state="disabled")
            self._aplicar_df(cual, df)
            return

        # Excel: leer hojas y poblar el selector
        try:
            xl = pd.ExcelFile(ruta)
        except Exception as e:
            messagebox.showerror("Error al leer Excel", str(e))
            return
        hojas = xl.sheet_names
        if not hojas:
            messagebox.showwarning("Excel vacío", "El archivo no contiene hojas.")
            return

        self._xl_files[cual] = xl
        combo_hoja.configure(values=hojas, state="readonly")
        self._hoja_vars[cual].set(hojas[0])
        try:
            df = xl.parse(hojas[0])
        except Exception as e:
            messagebox.showerror("Error al leer la hoja", str(e))
            return
        self._aplicar_df(cual, df)

    def _on_hoja_change(self, cual):
        """Recarga el DataFrame de la hoja seleccionada y re-auto-mapea."""
        xl = self._xl_files.get(cual)
        if xl is None:
            return
        hoja = self._hoja_vars[cual].get()
        try:
            df = xl.parse(hoja)
        except Exception as e:
            messagebox.showerror("Error al leer la hoja", str(e))
            return
        self._aplicar_df(cual, df)

    def _aplicar_df(self, cual, df):
        """Asigna el df a la fuente indicada, actualiza la etiqueta de info,
        rellena los combos de columnas y aplica el auto-mapeo por HINTS."""
        cols = ["— No usar —"] + list(df.columns.astype(str))
        hoja = self._hoja_vars[cual].get()
        info_hoja = f"hoja '{hoja}'  ·  " if hoja else ""
        if cual == "rg":
            self.df_rg = df
            self.cols_rg = cols
            self._lbl_rg.configure(
                text=f"{self._nombre_archivo['rg']}  ·  {info_hoja}{len(df)} filas", fg=TEXT)
            campos = self.CAMPOS_RG
        else:
            self.df_otro = df
            self.cols_otro = cols
            self._lbl_otro.configure(
                text=f"{self._nombre_archivo['otro']}  ·  {info_hoja}{len(df)} filas", fg=TEXT)
            campos = self.CAMPOS_OTRO

        for clave, _, _ in campos:
            combo = self.combos[clave]
            combo.configure(values=cols)
            var = self.vars[clave]
            matched = False
            for col in df.columns.astype(str):
                col_norm = col.lower().replace(" ", "_").replace("°", "")
                if any(h in col_norm for h in self.HINTS.get(clave, [])):
                    var.set(col)
                    matched = True
                    break
            if not matched:
                var.set("— No usar —")

    @staticmethod
    def _fmt_consec(v):
        """
        Formatea un consecutivo de remesa para mostrarlo limpio:
        - NaN / vacío  → "" (cadena vacía)
        - float entero (11519464.0) → "11519464" (sin el .0 que añade pandas)
        - cualquier otro → su texto sin espacios
        """
        if pd.isna(v):
            return ""
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        s = str(v).strip()
        if s.endswith(".0") and s[:-2].isdigit():
            s = s[:-2]
        return s

    @staticmethod
    def _to_num(v):
        """
        Convierte un valor de celda a float de forma robusta. Acepta números
        puros, celdas con formato moneda de Excel (que pandas ya lee como número)
        y texto con símbolos de moneda o separadores ($, espacios, puntos, comas).
        """
        s = str(v).strip()
        # Quitar todo lo que no sea dígito, punto, coma o signo negativo
        s = re.sub(r"[^\d.,\-]", "", s)
        return _parse_valor(s)

    # ── Validación y cruce ───────────────────────────────────────────────────

    def _validar(self):
        if self.df_rg is None:
            return False, "Primero carga el Excel de RG."
        if self.df_otro is None:
            return False, "Primero carga el otro Excel."
        for clave, etiqueta, req in self.CAMPOS_RG + self.CAMPOS_OTRO:
            if req and self.vars[clave].get() == "— No usar —":
                return False, f"El campo obligatorio '{etiqueta}' no tiene columna asignada."
        return True, ""

    def _cruzar(self):
        ok, msg = self._validar()
        if not ok:
            messagebox.showwarning("Mapeo incompleto", msg)
            return

        c = {clave: self.vars[clave].get() for clave, _, _ in self.CAMPOS_RG + self.CAMPOS_OTRO}

        # Agrupar Excel de RG por número de factura: contar líneas y tomar valor total
        df_rg = self.df_rg.copy()
        df_rg["_nf"] = df_rg[c["rg_col_nf"]].astype(str).str.strip()
        grupos_rg = df_rg.groupby("_nf")

        # Agrupar el otro Excel por número de factura: contar remesas y sumar valor unitario
        df_otro = self.df_otro.copy()
        df_otro["_nf"] = df_otro[c["otro_col_nf"]].astype(str).str.strip()
        grupos_otro = df_otro.groupby("_nf")

        todas_facturas = sorted(set(grupos_rg.groups.keys()) | set(grupos_otro.groups.keys()))

        self._filas_resultado = []
        self._consecutivos_otro_por_factura = {}
        for nf in todas_facturas:
            if nf in grupos_rg.groups:
                g_rg = grupos_rg.get_group(nf)
                n_remesas_rg = len(g_rg)
                try:
                    valor_factura_rg = self._to_num(g_rg[c["rg_col_val_fac"]].iloc[0])
                except Exception:
                    valor_factura_rg = 0.0
            else:
                n_remesas_rg = 0
                valor_factura_rg = 0.0

            if nf in grupos_otro.groups:
                g_otro = grupos_otro.get_group(nf)
                n_remesas_otro = len(g_otro)
                suma_valor_otro = 0.0
                for v in g_otro[c["otro_col_val_un"]]:
                    try:
                        suma_valor_otro += self._to_num(v)
                    except Exception:
                        pass
                # Consecutivos en el orden en que aparecen en el otro Excel,
                # para asignarlos en ese mismo orden a las líneas del RG.
                consecutivos_otro = [self._fmt_consec(v) for v in g_otro[c["otro_col_consec"]]]
            else:
                n_remesas_otro = 0
                suma_valor_otro = 0.0
                consecutivos_otro = []

            self._consecutivos_otro_por_factura[nf] = consecutivos_otro

            coinciden_remesas = (n_remesas_rg == n_remesas_otro) and n_remesas_rg > 0
            coincide_valor = abs(valor_factura_rg - suma_valor_otro) < 1.0 and valor_factura_rg > 0
            reconstruir = coinciden_remesas and coincide_valor

            self._filas_resultado.append({
                "numero_factura":              nf,
                "remesas_rg":                  n_remesas_rg,
                "remesas_otro":                n_remesas_otro,
                "coinciden_remesas":           "Sí" if coinciden_remesas else "No",
                "valor_factura_rg":            valor_factura_rg,
                "suma_valor_otro":             suma_valor_otro,
                "coincide_valor_factura_rg":   "Sí" if coincide_valor else "No",
                "reconstruir":                 "Sí" if reconstruir else "No",
            })

        # Mapa nf → flags, usado luego para anexar las columnas a TODAS las filas
        # originales del Excel de RG (no solo al resumen por factura).
        self._mapa_resultado = {f["numero_factura"]: f for f in self._filas_resultado}
        self._col_rg_nf = c["rg_col_nf"]

        self._refrescar_tabla()
        n_ok_rem = sum(1 for f in self._filas_resultado if f["coinciden_remesas"] == "Sí")
        n_ok_val = sum(1 for f in self._filas_resultado if f["coincide_valor_factura_rg"] == "Sí")
        n_reconstruir = sum(1 for f in self._filas_resultado if f["reconstruir"] == "Sí")
        total = len(self._filas_resultado)
        self._lbl_estado.configure(
            text=(f"✓  {total} factura(s) cruzada(s)  ·  remesas OK: {n_ok_rem}/{total}  ·  "
                  f"valor OK: {n_ok_val}/{total}  ·  Reconstruir Sí: {n_reconstruir}/{total}"),
            fg=SUCCESS)
        if self._filas_resultado:
            self._btn_exportar.configure(bg=ACCENT2, fg="white")

    def _refrescar_tabla(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        for i, f in enumerate(self._filas_resultado):
            tag = "ok" if f["reconstruir"] == "Sí" else "err"
            self._tree.insert("", "end", values=(
                f["numero_factura"], f["remesas_rg"], f["remesas_otro"],
                f["coinciden_remesas"],
                f"$ {f['valor_factura_rg']:,.0f}".replace(",", "."),
                f"$ {f['suma_valor_otro']:,.0f}".replace(",", "."),
                f["coincide_valor_factura_rg"],
                f["reconstruir"],
            ), tags=(tag,))

    # ── Exportación ───────────────────────────────────────────────────────────

    @staticmethod
    def _pasa_filtro(filtro, rem, val, rec):
        """Devuelve True si una factura con esas banderas (Sí/No) debe incluirse
        según el filtro de exportación seleccionado."""
        r = rem == "Sí"
        v = val == "Sí"
        x = rec == "Sí"
        if filtro == "Todas":                                   return True
        if filtro == "Solo Reconstruir = Sí":                   return x
        if filtro == "Coinciden remesas, NO coincide valor":    return r and not v
        if filtro == "Coincide valor, NO coinciden remesas":    return v and not r
        if filtro == "NO coinciden remesas":                    return not r
        if filtro == "NO coincide valor":                       return not v
        if filtro == "Reconstruir = No (alguna no coincide)":   return not x
        return True

    def _exportar(self):
        if not self._filas_resultado:
            messagebox.showwarning("Sin datos", "Primero ejecuta el cruce de información.")
            return

        filtro = self._filtro_var.get() if self._filtro_var else "Todas"
        sufijo = "" if filtro == "Todas" else "_filtrado"
        ruta_out = filedialog.asksaveasfilename(
            title="Guardar Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")],
            initialfile=f"cruce_remesas{sufijo}.xlsx")
        if not ruta_out:
            return
        try:
            # Se parte del Excel de RG ORIGINAL completo (todas sus columnas y filas)
            # y se le anexan las 3 columnas nuevas del cruce, repetidas en cada fila
            # según el número de factura a la que pertenece esa fila.
            df = self.df_rg.copy()
            if "consecutivo_remesa" in df.columns:
                df = df.drop(columns=["consecutivo_remesa"])
            nf_serie = df[self._col_rg_nf].astype(str).str.strip()
            # Posición de cada línea dentro de su factura, en el orden original del RG.
            pos_serie = nf_serie.groupby(nf_serie).cumcount()

            def _consecutivo_en_pos(nf, pos):
                lst = self._consecutivos_otro_por_factura.get(nf, [])
                return lst[pos] if pos < len(lst) else ""

            df["Consecutivo Remesa (Otro Excel)"] = [
                _consecutivo_en_pos(nf, pos) for nf, pos in zip(nf_serie, pos_serie)
            ]
            df["¿Coinciden remesas?"] = nf_serie.map(
                lambda nf: self._mapa_resultado.get(nf, {}).get("coinciden_remesas", "No"))
            df["¿Coincide valor factura con RG?"] = nf_serie.map(
                lambda nf: self._mapa_resultado.get(nf, {}).get("coincide_valor_factura_rg", "No"))
            df["Reconstruir"] = nf_serie.map(
                lambda nf: self._mapa_resultado.get(nf, {}).get("reconstruir", "No"))

            # Aplicar el filtro de exportación seleccionado (fila a fila, según
            # las banderas de la factura a la que pertenece cada línea del RG).
            if filtro != "Todas":
                mask = [
                    self._pasa_filtro(filtro, r, v, x)
                    for r, v, x in zip(
                        df["¿Coinciden remesas?"],
                        df["¿Coincide valor factura con RG?"],
                        df["Reconstruir"])
                ]
                df = df[mask]

            if df.empty:
                messagebox.showinfo("Sin resultados",
                    f"Ninguna factura cumple el filtro '{filtro}'. No se generó archivo.")
                return

            if ruta_out.endswith(".csv"):
                df.to_csv(ruta_out, index=False, encoding="utf-8-sig")
            else:
                df.to_excel(ruta_out, index=False)
            n_fac = df[self._col_rg_nf].astype(str).str.strip().nunique()
            self._lbl_estado.configure(
                text=f"✓ Exportado ({filtro}): {len(df)} filas · {n_fac} factura(s) → {ruta_out}",
                fg=SUCCESS)
            messagebox.showinfo("Exportado",
                f"Archivo guardado ({filtro}):\n{ruta_out}\n\n{len(df)} filas · {n_fac} factura(s)")
        except Exception as ex:
            messagebox.showerror("Error al exportar", str(ex))
