import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from pathlib import Path
try:
    import pandas as pd
    PANDAS_OK = True
except ImportError:
    PANDAS_OK = False
from config.theme import *
from config.perfiles import PERFILES
from core.xml_generator import generar_xml, _parse_valor
from services.rndc_service import consultar_radicado_remesa
from utils.helpers import resource_path


# ─────────────────────────────────────────────────────────────────────────────
# CARGADOR DE EXCEL — ventana de mapeo de columnas y generación masiva
# ─────────────────────────────────────────────────────────────────────────────

class ExcelLoaderWindow:
    """
    Ventana modal que:
      1. Lee el Excel cargado
      2. Muestra los encabezados para que el usuario los mapee a los campos XML
      3. Muestra resumen (facturas / remesas)
      4. Genera todos los XML de una vez
    """

    # Opciones de filtro de generación. Funcionan solo si el Excel cargado trae
    # las columnas de validación del cruce de remesas.
    FILTROS_GEN = [
        "Todas (sin filtro)",
        "Solo Reconstruir = Sí",
        "Reconstruir = Sí y Novedad vacía",
        "Coinciden remesas, NO coincide valor",
        "Coincide valor, NO coinciden remesas",
        "NO coinciden remesas",
        "NO coincide valor",
    ]

    # Campos requeridos y opcionales para el mapeo
    CAMPOS = [
        # (clave_interna, etiqueta_UI, requerido, default_si_no_mapeado)
        ("col_nf",        "Número de factura",        True,  None),
        ("col_cufe",      "CUFE",                     True,  None),
        ("col_fecha",     "Fecha de generación (única por factura)",  True,  None),
        ("col_consec",    "Consecutivo / Remesa",      True,  None),
        ("col_radicado",  "Radicado",                  False, "Opcional — aunque no se seleccione columna, el radicado se consultará automáticamente en el RNDC. Si no existe → 0"),
        ("col_val_rem",   "Valor unitario remesa ($)",  True,  None),
        ("col_val_fac",   "Valor total factura ($)",    True,  None),
        ("col_peso",      "Peso KGM",                  False, "1"),
        ("col_desc_lin",  "Descripción línea remesa",  False, "Servicio de transporte"),
        ("col_nit_cli",   "NIT cliente (opcional)",    False, "Usa 'Datos del Cliente'. El dígito = último número del NIT"),
        ("col_nom_cli",   "Nombre cliente (opcional)", False, "Usa 'Datos del Cliente'"),
        ("col_novedad",   "Novedad remesa (opcional)",             False, "Solo se usa para el filtro 'Reconstruir=Sí y Novedad vacía'"),
        ("col_comp_gen",  "Comp. Generador Carga RNDC (opcional)", False, "Solo se usa junto al filtro 'Reconstruir=Sí y Novedad vacía'"),
        ("col_estado",    "Estado (opcional)",                     False, "Si se mapea, omite las facturas ya generadas (con Estado lleno, ej. CARGADA/PENDIENTE)"),
    ]

    def __init__(self, parent, perfil_fn, on_success, max_facturas=200):
        """
        parent        : ventana raíz (GeneradorApp.root)
        perfil_fn     : callable que retorna el perfil activo
        on_success    : callback(msg) cuando termina OK
        max_facturas  : límite de facturas por cargue (configurable desde UI)
        """
        if not PANDAS_OK:
            messagebox.showerror("Dependencia faltante",
                "La librería 'pandas' no está instalada.\n"
                "Ejecuta: pip install pandas openpyxl")
            return

        self.parent       = parent
        self.perfil_fn    = perfil_fn
        self.on_success   = on_success
        self.max_facturas = max_facturas
        self.vars         = {}   # clave → StringVar
        self.combos       = {}   # clave → Combobox widget
        self.xl_file      = None
        self.hojas        = []
        self.df_raw       = None
        self.cols         = ["— No usar —"]
        self._filtro_gen_var = None

        self._build()


    def _cargar_archivo_excel(self):
        """Abre el explorador de archivos y carga el Excel seleccionado."""
        ruta = filedialog.askopenfilename(
            title="Selecciona el archivo Excel",
            filetypes=[("Excel", "*.xlsx *.xls *.xlsm"), ("Todos", "*.*")]
        )
        if not ruta:
            return
        try:
            self.xl_file = pd.ExcelFile(ruta)
            self.hojas   = self.xl_file.sheet_names
        except Exception as e:
            messagebox.showerror("Error al leer Excel", str(e), parent=self.win)
            return
        if not self.hojas:
            messagebox.showwarning("Excel vacío", "El archivo no contiene hojas.",
                                   parent=self.win)
            return
        # Actualizar combo de hojas
        self._hoja_combo.configure(values=self.hojas, state="readonly")
        self._hoja_var.set(self.hojas[0])
        # Cargar primera hoja y actualizar UI
        self._cargar_hoja(self.hojas[0])
        self._lbl_info.configure(
            text=f"Hoja: '{self.hojas[0]}'  ·  {len(self.df_raw)} filas  ·  "
                 f"columnas: {', '.join(self.df_raw.columns.astype(str))}")
        # Actualizar combos de mapeo
        for clave, var in self.vars.items():
            combo = self.combos[clave]
            combo.configure(values=self.cols)
            var.set("— No usar —")
        # Re-auto-mapear
        self._on_hoja_change()
        # Limpiar resumen (puede no existir aún si se llama antes de _build completo)
        if hasattr(self, "lbl_resumen") and self.lbl_resumen is not None:
            self.lbl_resumen.configure(text="", fg=TEXT2)

    def _cargar_hoja(self, nombre_hoja):
        """Carga el DataFrame de la hoja indicada y actualiza cols."""
        self.df_raw = self.xl_file.parse(nombre_hoja)
        self.cols   = ["— No usar —"] + list(self.df_raw.columns.astype(str))

    def _on_hoja_change(self, event=None):
        """Callback al cambiar de hoja: recarga df, actualiza combos y auto-mapea."""
        nombre = self._hoja_var.get()
        if not nombre or self.xl_file is None:
            return
        self._cargar_hoja(nombre)

        # Actualizar label de info en el header
        self._lbl_info.configure(
            text=f"Hoja: '{nombre}'  ·  {len(self.df_raw)} filas  ·  "
                 f"columnas: {', '.join(self.df_raw.columns.astype(str))}")

        # Actualizar valores de cada combo y re-auto-mapear
        for clave, var in self.vars.items():
            combo = self.combos[clave]
            combo.configure(values=self.cols)
            # Intentar auto-match con las nuevas columnas
            matched = False
            for col in self.df_raw.columns.astype(str):
                col_norm = col.lower().replace(" ", "_").replace("°", "").replace("n", "n")
                hints = {
                    "col_nf":       ["factura", "nfactura", "num_fac", "n_factura", "nfac"],
                    "col_cufe":     ["cufe"],
                    "col_fecha":    ["fecha"],
                    "col_consec":   ["remesa", "consecutivo", "consec"],
                    "col_radicado": ["radicado", "rad"],
                    "col_val_rem":  ["valor_remesa", "valor_rem", "vrem", "val_rem"],
                    "col_val_fac":  ["valor_factura", "valor fac", "val_fac", "vfac"],
                    "col_peso":     ["peso", "kg", "kgm"],
                    "col_desc_lin": ["descripcion", "desc", "descripcion_linea"],
                    "col_nit_cli":  ["nit"],
                    "col_nom_cli":  ["nombre_cliente", "nombre cli", "nom_cli", "cliente"],
                    "col_novedad":  ["novedad"],
                    "col_comp_gen": ["comp. generador", "generador carga", "comp_generador",
                                     "generador_carga", "comp generador"],
                    "col_estado":   ["estado"],
                }
                if any(h in col_norm for h in hints.get(clave, [])) \
                   and not (clave == "col_nit_cli" and "unitar" in col_norm):
                    var.set(col)
                    matched = True
                    break
            if not matched:
                var.set("— No usar —")
        # Actualizar valores del combo Comp. Generador si estaba mapeado
        self._actualizar_comp_gen_valores()

        # Limpiar resumen
        if hasattr(self, "lbl_resumen") and self.lbl_resumen is not None:
            self.lbl_resumen.configure(text="", fg=TEXT2)

    # ── Construcción de la ventana ────────────────────────────────────────────

    def _build(self, container=None):
        if container is None:
            win = tk.Toplevel(self.parent)
            self.win = win
            win.title("Cargar Excel — Mapeo de columnas")
            win.configure(bg=BG)
            win.resizable(True, True)
            win.grab_set()
            try:
                win.iconbitmap(resource_path("icono.ico"))
            except Exception:
                pass
            root_frame = win
        else:
            # Embebido en el panel del sidebar
            self.win = container.winfo_toplevel()
            root_frame = container

        # ── Header ───────────────────────────────────────────────────────────
        hdr = tk.Frame(root_frame, bg=BG2, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="📊  Mapeo de columnas Excel  →  Campos XML",
                 font=FONT_H1, bg=BG2, fg=TEXT).pack(padx=20)

        # Fila: botón cargar archivo + selector de hoja + info
        hoja_row = tk.Frame(hdr, bg=BG2)
        hoja_row.pack(pady=(6, 2), padx=20, anchor="w")

        # Botón Cargar archivo Excel
        btn_cargar = tk.Label(hoja_row, text="📂  Cargar archivo Excel",
                              font=FONT_BODY, bg=ACCENT, fg="white",
                              cursor="hand2", padx=12, pady=4)
        btn_cargar.pack(side=tk.LEFT, padx=(0, 16))
        btn_cargar.bind("<Button-1>", lambda e: self._cargar_archivo_excel())
        btn_cargar.bind("<Enter>",    lambda e: btn_cargar.configure(bg="#2d5cbf"))
        btn_cargar.bind("<Leave>",    lambda e: btn_cargar.configure(bg=ACCENT))

        # Selector de hoja (vacío hasta que se cargue un archivo)
        tk.Label(hoja_row, text="Hoja:", font=FONT_BODY, bg=BG2, fg=TEXT2
                 ).pack(side=tk.LEFT, padx=(0, 6))
        self._hoja_var = tk.StringVar(value="")
        self._hoja_combo = ttk.Combobox(hoja_row, textvariable=self._hoja_var,
                                        values=[], state="disabled",
                                        font=FONT_BODY, width=28)
        self._hoja_combo.pack(side=tk.LEFT)
        self._hoja_combo.bind("<<ComboboxSelected>>", self._on_hoja_change)

        # Info dinámica (se actualiza al cargar archivo y al cambiar hoja)
        self._lbl_info = tk.Label(hdr,
                 text="Sin archivo cargado. Haz clic en 'Cargar archivo Excel'.",
                 font=FONT_SMALL, bg=BG2, fg=TEXT2, wraplength=740)
        self._lbl_info.pack(padx=20, pady=(2, 0))

        sep = tk.Frame(root_frame, bg=BORDER, height=1)
        sep.pack(fill=tk.X)

        # ── Cuerpo scrollable ─────────────────────────────────────────────────
        body = tk.Frame(root_frame, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=14)

        # ── Card: Datos del cliente ───────────────────────────────────────────
        cli_outer = tk.Frame(body, bg=BG2, pady=0)
        cli_outer.pack(fill=tk.X, pady=(0, 10))
        tk.Label(cli_outer, text="🏢  Datos del Cliente",
                 font=FONT_H2, bg=BG2, fg=TEXT).pack(anchor="w", padx=12, pady=(10,4))
        tk.Frame(cli_outer, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=(0,6))
        cli_inner = tk.Frame(cli_outer, bg=BG2)
        cli_inner.pack(fill=tk.X, padx=12, pady=(0,10))

        for label, attr, default in [
            ("NIT cliente",         "xl_ent_nit_cli", "800021308"),
            ("Dígito verificación", "xl_ent_dig_cli", "5"),
            ("Nombre cliente",      "xl_ent_nom_cli", "DRUMMOND LTD"),
        ]:
            row_c = tk.Frame(cli_inner, bg=BG2)
            row_c.pack(fill=tk.X, pady=2)
            tk.Label(row_c, text=label, font=FONT_BODY, bg=BG2,
                     fg=TEXT2, width=22, anchor="w").pack(side=tk.LEFT)
            ent_c = tk.Entry(row_c, font=FONT_BODY, width=30,
                             bg=BG3, fg=TEXT, insertbackground=TEXT,
                             relief="flat", highlightthickness=1,
                             highlightbackground=BORDER, highlightcolor=ACCENT)
            ent_c.insert(0, default)
            ent_c.pack(side=tk.LEFT, fill=tk.X, expand=True)
            setattr(self, attr, ent_c)

        # Instrucción
        tk.Label(body,
                 text="Asigna cada campo a la columna del Excel que le corresponde.\n"
                      "Los campos marcados con * son obligatorios. Los opcionales tienen valor por defecto.",
                 font=FONT_BODY, bg=BG, fg=TEXT2, justify="left").pack(anchor="w", pady=(0,10))

        # Grid de mapeo
        grid = tk.Frame(body, bg=BG2, padx=16, pady=12)
        grid.pack(fill=tk.X)

        # Cabecera de tabla
        for ci, txt in enumerate(("Campo XML", "Columna del Excel", "Valor por defecto si no se mapea")):
            tk.Label(grid, text=txt, font=FONT_H2, bg=BG2, fg=TEXT2
                     ).grid(row=0, column=ci, sticky="w", padx=(0,20), pady=(0,8))

        self.vars = {}
        for row_i, (clave, etiqueta, req, default) in enumerate(self.CAMPOS, start=1):
            row_bg = BG3 if row_i % 2 == 0 else BG2
            fila = tk.Frame(grid, bg=row_bg)
            fila.grid(row=row_i, column=0, columnspan=3, sticky="ew", pady=1)
            grid.grid_columnconfigure(0, weight=0)
            grid.grid_columnconfigure(1, weight=1)
            grid.grid_columnconfigure(2, weight=0)

            # Etiqueta campo
            lbl_text = f"{'*' if req else '○'}  {etiqueta}"
            tk.Label(fila, text=lbl_text, font=FONT_BODY, bg=row_bg,
                     fg=TEXT if req else TEXT2, width=30, anchor="w"
                     ).pack(side=tk.LEFT, padx=(8,4), pady=5)

            # Combo columnas
            var = tk.StringVar(value="— No usar —")
            self.vars[clave] = var
            combo = ttk.Combobox(fila, textvariable=var,
                                 values=self.cols, state="readonly",
                                 font=FONT_BODY, width=30)
            combo.pack(side=tk.LEFT, padx=(0,12), pady=5)
            self.combos[clave] = combo

            # Auto-match por nombre similar (solo si hay archivo cargado)
            if self.df_raw is not None:
                for col in self.df_raw.columns.astype(str):
                    col_norm = col.lower().replace(" ", "_").replace("°", "").replace("n", "n")
                    hints = {
                        "col_nf":       ["factura", "nfactura", "num_fac", "n_factura", "nfac"],
                        "col_cufe":     ["cufe"],
                        "col_fecha":    ["fecha"],
                        "col_consec":   ["remesa", "consecutivo", "consec"],
                        "col_radicado": ["radicado", "rad"],
                        "col_val_rem":  ["valor_remesa", "valor_rem", "vrem", "val_rem"],
                        "col_val_fac":  ["valor_factura", "valor fac", "val_fac", "vfac"],
                        "col_peso":     ["peso", "kg", "kgm"],
                        "col_desc_lin": ["descripcion", "desc", "descripcion_linea"],
                        "col_nit_cli":  ["nit"],
                        "col_nom_cli":  ["nombre_cliente", "nombre cli", "nom_cli", "cliente"],
                        "col_novedad":  ["novedad"],
                        "col_comp_gen": ["comp. generador", "generador carga", "comp_generador",
                                         "generador_carga", "comp generador"],
                        "col_estado":   ["estado"],
                    }
                    if any(h in col_norm for h in hints.get(clave, [])) \
                       and not (clave == "col_nit_cli" and "unitar" in col_norm):
                        var.set(col)
                        break

            # Default label
            def_txt = default if default else "—  (obligatorio)"
            tk.Label(fila, text=def_txt, font=FONT_SMALL, bg=row_bg,
                     fg=TEXT2 if default else DANGER,
                     anchor="w", wraplength=320, justify="left"
                     ).pack(side=tk.LEFT, padx=(0,8), fill=tk.X, expand=True)

            # Al cambiar la columna Comp. Generador, actualizar valores disponibles
            if clave == "col_comp_gen":
                var.trace_add("write", lambda *_: self._actualizar_comp_gen_valores())

        # ── Resumen ───────────────────────────────────────────────────────────
        self.lbl_resumen = tk.Label(body, text="", font=FONT_BODY,
                                    bg=BG, fg=ACCENT, anchor="w")
        self.lbl_resumen.pack(anchor="w", pady=(12, 4))

        # ── Campo: cantidad de facturas a generar ─────────────────────────────
        cant_frame = tk.Frame(body, bg=BG2, padx=12, pady=10)
        cant_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(cant_frame,
                 text=f"Cantidad de facturas a generar  (máx. 200 por cargue):",
                 font=FONT_BODY, bg=BG2, fg=TEXT).pack(side=tk.LEFT, padx=(0, 10))

        # Validador: solo dígitos
        def _only_digits(new_val):
            return new_val == "" or new_val.isdigit()
        vcmd = (root_frame.winfo_toplevel().register(_only_digits), "%P")

        self._cant_var = tk.StringVar(value="")
        ent_cant = tk.Entry(cant_frame, textvariable=self._cant_var,
                            font=FONT_BODY, width=6,
                            bg=BG3, fg=TEXT, insertbackground=TEXT,
                            relief="flat", highlightthickness=1,
                            highlightbackground=BORDER, highlightcolor=ACCENT,
                            validate="key", validatecommand=vcmd)
        ent_cant.pack(side=tk.LEFT)

        self._lbl_cant_hint = tk.Label(cant_frame,
                                       text="  (deja vacío para generar todas)",
                                       font=FONT_SMALL, bg=BG2, fg=TEXT2)
        self._lbl_cant_hint.pack(side=tk.LEFT, padx=(6, 0))

        # ── Filtro de generación (usa columnas del cruce de remesas) ──────────
        filtro_frame = tk.Frame(body, bg=BG2, padx=12, pady=10)
        filtro_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(filtro_frame, text="Filtro de generación:",
                 font=FONT_BODY, bg=BG2, fg=TEXT).pack(side=tk.LEFT, padx=(0, 10))
        self._filtro_gen_var = tk.StringVar(value=self.FILTROS_GEN[0])
        ttk.Combobox(filtro_frame, textvariable=self._filtro_gen_var,
                     values=self.FILTROS_GEN, state="readonly",
                     font=FONT_BODY, width=38).pack(side=tk.LEFT)
        tk.Label(filtro_frame,
                 text="  (requiere Excel del cruce con sus columnas de validación)",
                 font=FONT_SMALL, bg=BG2, fg=TEXT2).pack(side=tk.LEFT, padx=(6, 0))

        # ── Filtro adicional: valor de Comp. Generador Carga RNDC ────────────
        compgen_frame = tk.Frame(body, bg=BG2, padx=12, pady=6)
        compgen_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(compgen_frame, text="Comp. Generador RNDC (valor requerido):",
                 font=FONT_BODY, bg=BG2, fg=TEXT).pack(side=tk.LEFT, padx=(0, 10))
        self._comp_gen_valor_var = tk.StringVar(value="— No usar —")
        self._comp_gen_valor_combo = ttk.Combobox(
            compgen_frame, textvariable=self._comp_gen_valor_var,
            values=["— No usar —", "Todas"], state="readonly",
            font=FONT_BODY, width=22)
        self._comp_gen_valor_combo.pack(side=tk.LEFT)
        tk.Label(compgen_frame,
                 text="  (activo solo con filtro 'Reconstruir=Sí y Novedad vacía' y columna mapeada)",
                 font=FONT_SMALL, bg=BG2, fg=TEXT2).pack(side=tk.LEFT, padx=(6, 0))

        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(fill=tk.X, pady=(4, 0))

        MAX_FAC = self.max_facturas

        def _get_cantidad(total_disponible):
            """
            Retorna (n, error_msg).
            n = cuántas facturas generar, error_msg = None si OK.
            """
            raw = self._cant_var.get().strip()
            if raw == "":
                # Sin límite explícito → todas, pero respetando MAX_FAC
                if total_disponible > MAX_FAC:
                    return None, (
                        f"El Excel contiene {total_disponible} facturas, "
                        f"que supera el límite de {MAX_FAC} por cargue.\n"
                        f"Indica cuántas deseas generar (1 – {MAX_FAC})."
                    )
                return total_disponible, None
            n = int(raw)
            if n == 0:
                return None, "La cantidad debe ser al menos 1."
            if n > MAX_FAC:
                return None, (
                    f"El límite máximo por cargue es {MAX_FAC} facturas.\n"
                    f"Escribe un número entre 1 y {MAX_FAC}."
                )
            if n > total_disponible:
                return None, (
                    f"Solo hay {total_disponible} factura{'s' if total_disponible != 1 else ''} "
                    f"en el Excel.\nCambia el valor a {total_disponible} o menos."
                )
            return n, None

        def _preview():
            ok, msg = self._validar()
            if not ok:
                self.lbl_resumen.configure(text=f"⚠  {msg}", fg=DANGER)
                return
            datos_list = self._parsear()
            total_disp = len(datos_list)
            n, err = _get_cantidad(total_disp)
            if err:
                self.lbl_resumen.configure(text=f"⚠  {err}", fg=DANGER)
                return
            subset   = datos_list[:n]
            n_rem    = sum(len(d["remesas"]) for d in subset)
            nombre_perfil = self.perfil_fn()["nombre"]
            self.lbl_resumen.configure(
                text=(f"✓  {n} de {total_disp} factura{'s' if total_disp!=1 else ''}  ·  "
                      f"{n_rem} remesas  ·  Perfil: {nombre_perfil}"),
                fg=SUCCESS)

        def _set_generando(activo):
            """Bloquea/desbloquea el botón de generar y muestra u oculta la barra."""
            if activo:
                _btn_gen.configure(bg=BG3, fg=TEXT2, cursor="")
                _btn_gen.unbind("<Button-1>")
                self._prog_frame.pack(fill=tk.X, pady=(6, 0))
            else:
                _btn_gen.configure(bg=ACCENT, fg="white", cursor="hand2")
                _btn_gen.bind("<Button-1>", lambda e: _generar_todos())
                self._prog_frame.pack_forget()
                self._prog_bar["value"] = 0
                self._prog_label.configure(text="")

        def _generar_todos():
            ok, msg = self._validar()
            if not ok:
                messagebox.showwarning("Mapeo incompleto", msg)
                return
            datos_list = self._parsear()
            if not datos_list:
                messagebox.showwarning("Sin datos", "No se encontraron facturas válidas.")
                return
            n, err = _get_cantidad(len(datos_list))
            if err:
                messagebox.showwarning("Cantidad inválida", err)
                return
            datos_list = datos_list[:n]
            carpeta = filedialog.askdirectory(title="Selecciona carpeta de destino para los XML")
            if not carpeta:
                return
            perfil = self.perfil_fn()
            nombre_perfil = perfil["nombre"]
            total_rem = sum(len(d["remesas"]) for d in datos_list)
            total_pasos = total_rem + len(datos_list)  # consultas RNDC + generaciones XML

            _set_generando(True)
            self._prog_bar["maximum"] = total_pasos
            self._prog_label.configure(text="Iniciando…")

            def _progreso(valor, texto):
                """Actualiza la barra desde el hilo de trabajo de forma thread-safe."""
                self.win.after(0, lambda: (
                    self._prog_bar.configure(value=valor),
                    self._prog_label.configure(text=texto),
                ))

            def _worker():
                paso = 0
                errores = []
                generados = 0

                # ── Fase 1: consultar radicados faltantes en el RNDC ─────────
                for datos in datos_list:
                    for rem in datos["remesas"]:
                        consec = rem.get("consecutivo", "").strip()
                        radicado_actual = rem.get("radicado", "").strip()
                        if consec and radicado_actual.lower() in ("", "nan", "none", "0"):
                            ok_r, resultado = consultar_radicado_remesa(consec, perfil)
                            rem["radicado"] = resultado.get("radicado", "0") if ok_r else "0"
                        elif not radicado_actual or radicado_actual.lower() in ("nan", "none"):
                            rem["radicado"] = "0"
                        paso += 1
                        _progreso(paso, f"Consultando RNDC… remesa {paso}/{total_rem}")

                # ── Fase 2: generar XML ───────────────────────────────────────
                for i, datos in enumerate(datos_list, start=1):
                    try:
                        xml = generar_xml(datos, perfil=perfil)
                        nf = datos["numero_factura"]
                        ruta_out = Path(carpeta) / f"FACTURA_{nf}.xml"
                        with open(ruta_out, "w", encoding="utf-8") as fout:
                            fout.write(xml)
                        generados += 1
                    except Exception as e:
                        errores.append(f"Factura {datos.get('numero_factura', '?')}: {e}")
                    paso += 1
                    _progreso(paso, f"Generando XML… {i}/{len(datos_list)}")

                # ── Fin: volver al hilo principal para UI ────────────────────
                def _fin():
                    _set_generando(False)
                    msg_ok = (f"✓  {generados} XML generado{'s' if generados != 1 else ''} "
                              f"[{nombre_perfil}]\n{carpeta}")
                    if errores:
                        msg_ok += "\n\n⚠  Errores:\n" + "\n".join(errores)
                        messagebox.showwarning("Generación parcial", msg_ok)
                    else:
                        messagebox.showinfo("¡Listo!", msg_ok)
                    if self.on_success:
                        self.on_success(
                            f"✓  {generados} facturas generadas [{nombre_perfil}] → {carpeta}")

                self.win.after(0, _fin)

            threading.Thread(target=_worker, daemon=True).start()

        # botones
        _btn_prev = tk.Label(btn_row, text="🔍  Vista previa / contar", font=FONT_BODY,
                             bg=BG3, fg=TEXT, cursor="hand2", padx=14, pady=5)
        _btn_prev.pack(side=tk.LEFT, padx=(0,8))
        _btn_prev.bind("<Button-1>", lambda e: _preview())
        _btn_prev.bind("<Enter>", lambda e: _btn_prev.configure(bg=BORDER))
        _btn_prev.bind("<Leave>", lambda e: _btn_prev.configure(bg=BG3))

        _btn_gen = tk.Label(btn_row, text="⚡  Generar XML", font=("Segoe UI", 9, "bold"),
                            bg=ACCENT, fg="white", cursor="hand2", padx=14, pady=5)
        _btn_gen.pack(side=tk.LEFT)
        _btn_gen.bind("<Button-1>", lambda e: _generar_todos())
        _btn_gen.bind("<Enter>", lambda e: _btn_gen.configure(bg="#2d5cbf"))
        _btn_gen.bind("<Leave>", lambda e: _btn_gen.configure(bg=ACCENT))

        def _limpiar_excel():
            self.xl_file   = None
            self.df_raw    = None
            self.cols      = ["— No usar —"]
            self._hoja_var.set("")
            self._hoja_combo.configure(values=[], state="disabled")
            self._lbl_info.configure(text="Sin archivo cargado. Haz clic en 'Cargar archivo Excel'.")
            for clave, var in self.vars.items():
                var.set("— No usar —")
                self.combos[clave].configure(values=[self.cols[0]])
            if hasattr(self, "lbl_resumen") and self.lbl_resumen:
                self.lbl_resumen.configure(text="", fg=TEXT2)

        _btn_limpiar_ex = tk.Label(btn_row, text="🗑  Limpiar",
                                   font=FONT_BODY, bg="#555e7a", fg="white",
                                   cursor="hand2", padx=12, pady=5)
        _btn_limpiar_ex.pack(side=tk.LEFT, padx=(8, 0))
        _btn_limpiar_ex.bind("<Button-1>", lambda e: _limpiar_excel())
        _btn_limpiar_ex.bind("<Enter>",    lambda e: _btn_limpiar_ex.configure(bg="#3a4060"))
        _btn_limpiar_ex.bind("<Leave>",    lambda e: _btn_limpiar_ex.configure(bg="#555e7a"))

        # ── Barra de progreso (oculta hasta que se inicia la generación) ──────
        self._prog_frame = tk.Frame(body, bg=BG)
        # No se hace pack aquí; _set_generando lo muestra/oculta dinámicamente
        s2 = ttk.Style()
        s2.configure("Gen.Horizontal.TProgressbar",
                      troughcolor=BG3, background=ACCENT, thickness=14)
        self._prog_bar = ttk.Progressbar(
            self._prog_frame, style="Gen.Horizontal.TProgressbar",
            orient="horizontal", mode="determinate", length=500)
        self._prog_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self._prog_label = tk.Label(
            self._prog_frame, text="", font=FONT_SMALL, bg=BG, fg=TEXT2, width=36, anchor="w")
        self._prog_label.pack(side=tk.LEFT)

        # Tamaño dinámico (solo en modo ventana, no embebido)
        if container is None:
            root_frame.update_idletasks()
            w = max(800, root_frame.winfo_reqwidth() + 40)
            h = max(560, root_frame.winfo_reqheight() + 20)
            root_frame.winfo_toplevel().geometry(f"{w}x{h}")
            root_frame.winfo_toplevel().minsize(750, 500)

    # ── Filtro por columnas del cruce ─────────────────────────────────────────

    @staticmethod
    def _es_si(v):
        """True si el valor de celda representa 'Sí' (tolerante a acento/formato)."""
        return str(v).strip().lower() in ("sí", "si", "s", "true", "1", "yes")

    @staticmethod
    def _cols_cruce(df):
        """
        Localiza las columnas de validación del cruce en el DataFrame.
        Retorna dict {rem, val, rec} con los nombres reales, o None si faltan.
        """
        if df is None:
            return None
        rem = val = rec = None
        for col in df.columns.astype(str):
            cn = col.lower()
            if "coinciden" in cn and "remesa" in cn:
                rem = col
            elif "coincide" in cn and "valor" in cn:
                val = col
            elif "reconstruir" in cn:
                rec = col
        if rem and val and rec:
            return {"rem": rem, "val": val, "rec": rec}
        return None

    @staticmethod
    def _col_novedad(df):
        """Localiza la columna 'Novedad remesa' en el DataFrame (o None)."""
        if df is None:
            return None
        for col in df.columns.astype(str):
            if "novedad" in col.lower():
                return col
        return None

    @staticmethod
    def _es_vacio(v):
        """True si la celda está vacía (None/NaN/''/'nan')."""
        s = str(v).strip().lower()
        return s in ("", "nan", "none")

    def _novedad_col_activa(self, df):
        """Columna de novedad a usar en el filtro: la mapeada por el usuario
        (col_novedad) si la eligió; si no, la auto-detectada por nombre."""
        v = self.vars.get("col_novedad")
        if v and v.get() and v.get() != "— No usar —":
            return v.get()
        return self._col_novedad(df)

    def _actualizar_comp_gen_valores(self):
        """Puebla el combo de valor de Comp. Generador con los valores únicos
        de la columna mapeada (+ 'Todas' y '— No usar —')."""
        combo = getattr(self, "_comp_gen_valor_combo", None)
        if combo is None:
            return
        cg_var = self.vars.get("col_comp_gen")
        col = cg_var.get() if cg_var else None
        if not col or col == "— No usar —" or self.df_raw is None or col not in self.df_raw.columns:
            combo.configure(values=["— No usar —", "Todas"])
            self._comp_gen_valor_var.set("— No usar —")
            return
        vals_uniq = sorted({str(v).strip() for v in self.df_raw[col].dropna() if str(v).strip()})
        opciones = ["— No usar —", "Todas"] + vals_uniq
        combo.configure(values=opciones)
        # Si el valor actual no es válido, poner el primer valor real o "SI" si existe
        cur = self._comp_gen_valor_var.get()
        if cur not in opciones:
            default = "SI" if "SI" in vals_uniq else (vals_uniq[0] if vals_uniq else "Todas")
            self._comp_gen_valor_var.set(default)

    # Filtros que además exigen la columna 'Novedad remesa'
    FILTROS_NOVEDAD = {"Reconstruir = Sí y Novedad vacía"}

    @classmethod
    def _pasa_filtro(cls, filtro, rem, val, rec, novedad=""):
        """True si una fila con esas banderas debe incluirse según el filtro."""
        r = cls._es_si(rem)
        v = cls._es_si(val)
        x = cls._es_si(rec)
        if filtro == "Todas (sin filtro)":                      return True
        if filtro == "Solo Reconstruir = Sí":                   return x
        if filtro == "Reconstruir = Sí y Novedad vacía":        return x and cls._es_vacio(novedad)
        if filtro == "Coinciden remesas, NO coincide valor":    return r and not v
        if filtro == "Coincide valor, NO coinciden remesas":    return v and not r
        if filtro == "NO coinciden remesas":                    return not r
        if filtro == "NO coincide valor":                       return not v
        return True

    # ── Validación ────────────────────────────────────────────────────────────

    def _validar(self):
        """Verifica que todos los campos obligatorios tengan columna asignada."""
        if self.xl_file is None or self.df_raw is None:
            return False, "Primero carga un archivo Excel con el botón 'Cargar archivo Excel'."
        for clave, etiqueta, req, _ in self.CAMPOS:
            if req and self.vars[clave].get() == "— No usar —":
                return False, f"El campo obligatorio '{etiqueta}' no tiene columna asignada."
        # Si hay un filtro de cruce activo, el Excel debe traer sus columnas
        filtro = self._filtro_gen_var.get() if self._filtro_gen_var else "Todas (sin filtro)"
        if filtro != "Todas (sin filtro)" and self._cols_cruce(self.df_raw) is None:
            return False, ("El filtro seleccionado necesita las columnas de validación del cruce "
                           "(¿Coinciden remesas?, ¿Coincide valor factura con RG?, Reconstruir). "
                           "El Excel cargado no las tiene: usa 'Todas (sin filtro)' o carga el "
                           "Excel generado por el módulo de cruce de remesas.")
        # El filtro de novedad además exige la columna 'Novedad remesa'
        if filtro in self.FILTROS_NOVEDAD and self._novedad_col_activa(self.df_raw) is None:
            return False, ("El filtro 'Reconstruir = Sí y Novedad vacía' necesita la columna "
                           "'Novedad remesa'. El Excel cargado no la tiene: mapéala al cruzar "
                           "remesas o usa otro filtro.")
        return True, ""

    # ── Parseo del DataFrame → lista de datos por factura ────────────────────

    def _parsear(self):
        """
        Lee el DataFrame y agrupa por número de factura.
        Retorna lista de dicts compatibles con generar_xml().
        """
        df = self.df_raw.copy()

        # Filtrar filas según las columnas de validación del cruce (si aplica)
        filtro = self._filtro_gen_var.get() if self._filtro_gen_var else "Todas (sin filtro)"
        if filtro != "Todas (sin filtro)":
            cc = self._cols_cruce(df)
            if cc is not None:
                nov_col = self._novedad_col_activa(df)
                nov_serie = df[nov_col] if nov_col and nov_col in df.columns else [""] * len(df)

                if filtro in self.FILTROS_NOVEDAD:
                    # Filtro a nivel de FACTURA: solo incluir facturas donde TODAS las
                    # remesas tienen Reconstruir=Sí y novedad vacía.
                    c_nf_col = self.vars.get("col_nf")
                    c_nf_col = c_nf_col.get() if c_nf_col else None
                    if c_nf_col and c_nf_col != "— No usar —" and c_nf_col in df.columns:
                        fila_pasa = [
                            self._pasa_filtro(filtro, r, v, x, n)
                            for r, v, x, n in zip(df[cc["rem"]], df[cc["val"]], df[cc["rec"]], nov_serie)
                        ]
                        # Agrupar por N° factura: la factura pasa solo si TODAS sus filas pasan
                        df["_fila_pasa"] = fila_pasa
                        facturas_ok = df.groupby(df[c_nf_col].astype(str))["_fila_pasa"].all()
                        nf_ok = set(facturas_ok[facturas_ok].index)
                        df = df[df[c_nf_col].astype(str).isin(nf_ok)]
                        df = df.drop(columns=["_fila_pasa"])

                        # Filtro adicional: Comp. Generador Carga RNDC (a nivel de factura)
                        cg_col_var = self.vars.get("col_comp_gen")
                        cg_col = cg_col_var.get() if cg_col_var and cg_col_var.get() != "— No usar —" else None
                        cg_val = getattr(self, "_comp_gen_valor_var", None)
                        cg_val = cg_val.get() if cg_val else "— No usar —"
                        if cg_col and cg_col in df.columns and cg_val not in ("— No usar —", "Todas"):
                            df["_cg_pasa"] = [
                                str(v).strip().upper() == cg_val.strip().upper()
                                for v in df[cg_col]
                            ]
                            facturas_ok_cg = df.groupby(df[c_nf_col].astype(str))["_cg_pasa"].all()
                            nf_ok_cg = set(facturas_ok_cg[facturas_ok_cg].index)
                            df = df[df[c_nf_col].astype(str).isin(nf_ok_cg)]
                            df = df.drop(columns=["_cg_pasa"])
                    else:
                        # Sin columna de N° factura: caer a filtro fila por fila
                        mask = [
                            self._pasa_filtro(filtro, r, v, x, n)
                            for r, v, x, n in zip(df[cc["rem"]], df[cc["val"]], df[cc["rec"]], nov_serie)
                        ]
                        df = df[mask]
                else:
                    mask = [
                        self._pasa_filtro(filtro, r, v, x, n)
                        for r, v, x, n in zip(df[cc["rem"]], df[cc["val"]], df[cc["rec"]], nov_serie)
                    ]
                    df = df[mask]

        # Filtro por Estado (independiente del filtro de generación): si la columna
        # está mapeada, se omiten las facturas YA generadas — las que tienen algún
        # valor en Estado (ej. CARGADA/PENDIENTE). Se genera solo la factura cuyas
        # remesas tengan TODAS el Estado vacío (mismo criterio a nivel de factura).
        est_var = self.vars.get("col_estado")
        est_col = est_var.get() if est_var and est_var.get() != "— No usar —" else None
        if est_col and est_col in df.columns:
            c_nf_e = self.vars.get("col_nf")
            c_nf_e = c_nf_e.get() if c_nf_e else None
            if c_nf_e and c_nf_e != "— No usar —" and c_nf_e in df.columns:
                df = df.copy()
                df["_est_vacio"] = [self._es_vacio(v) for v in df[est_col]]
                fac_ok_e = df.groupby(df[c_nf_e].astype(str))["_est_vacio"].all()
                nf_ok_e = set(fac_ok_e[fac_ok_e].index)
                df = df[df[c_nf_e].astype(str).isin(nf_ok_e)]
                df = df.drop(columns=["_est_vacio"])
            else:
                df = df[[self._es_vacio(v) for v in df[est_col]]]

        def col(clave):
            v = self.vars[clave].get()
            return v if v != "— No usar —" else None

        c_nf       = col("col_nf")
        c_cufe     = col("col_cufe")
        c_fecha    = col("col_fecha")
        c_consec   = col("col_consec")
        c_radicado = col("col_radicado")
        c_val_rem  = col("col_val_rem")
        c_val_fac  = col("col_val_fac")
        c_peso     = col("col_peso")
        c_desc_lin = col("col_desc_lin")
        c_nit_cli  = col("col_nit_cli")
        c_nom_cli  = col("col_nom_cli")

        datos_list = []
        grupos = df.groupby(df[c_nf].astype(str))

        for nf, grupo in grupos:
            # Datos de cabecera: primera fila del grupo
            primera = grupo.iloc[0]

            cufe  = str(primera[c_cufe]).strip()
            # Fecha de generación: siempre se toma de la PRIMERA fila del grupo.
            # Es única por factura; si hay distintos valores en otras filas se ignoran.
            fecha_raw = grupo[c_fecha].iloc[0]
            if hasattr(fecha_raw, "strftime"):
                fecha = fecha_raw.strftime("%Y-%m-%d")
            else:
                fecha_str = str(fecha_raw).strip()
                for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
                    try:
                        fecha = datetime.strptime(fecha_str, fmt).strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        continue
                else:
                    fecha = fecha_str

            # Valor total: primera fila (es el mismo para todo el grupo)
            try:
                val_fac = _parse_valor(str(primera[c_val_fac]))
            except Exception:
                val_fac = 0.0

            remesas = []
            for _, fila in grupo.iterrows():
                _cv = fila[c_consec]
                if pd.isna(_cv):
                    consec = ""
                elif isinstance(_cv, float) and _cv.is_integer():
                    consec = str(int(_cv))
                else:
                    consec = str(_cv).strip()
                    if consec.endswith(".0") and consec[:-2].isdigit():
                        consec = consec[:-2]
                radicado = str(fila[c_radicado]).strip() if c_radicado else ""
                try:
                    valor = _parse_valor(str(fila[c_val_rem]))
                except Exception:
                    valor = 0.0
                peso     = str(fila[c_peso]).strip() if c_peso else "1"
                desc_lin = str(fila[c_desc_lin]).strip() if c_desc_lin else "Servicio de transporte"
                if not desc_lin or desc_lin.lower() in ("nan", "none", ""):
                    desc_lin = "Servicio de transporte"

                remesas.append({
                    "consecutivo":       consec,
                    "radicado":          radicado,
                    "peso":              peso,
                    "valor":             valor,
                    "descripcion_linea": desc_lin,
                })

            # Datos del cliente: por columna mapeada (opcional) o los valores fijos
            # de 'Datos del Cliente'. Si se mapea el NIT, el dígito de verificación
            # se toma del ÚLTIMO dígito del NIT (ej. 8000213085 → NIT 800021308, díg 5).
            nit_cli = self.xl_ent_nit_cli.get().strip() or "800021308"
            dig_cli = self.xl_ent_dig_cli.get().strip() or "5"
            nom_cli = self.xl_ent_nom_cli.get().strip() or "DRUMMOND LTD"

            if c_nit_cli:
                solo_digitos = re.sub(r"\D", "", str(primera[c_nit_cli]))
                if len(solo_digitos) >= 2:
                    nit_cli, dig_cli = solo_digitos[:-1], solo_digitos[-1]
            if c_nom_cli:
                v = str(primera[c_nom_cli]).strip()
                if v and v.lower() not in ("nan", "none", ""):
                    nom_cli = v

            datos_list.append({
                "numero_factura": nf,
                "cufe":           cufe,
                "fecha":          fecha,
                "nit_cliente":    nit_cli,
                "digito_cliente": dig_cli,
                "nombre_cliente": nom_cli,
                "valor_total":    val_fac,
                "remesas":        remesas,
            })

        return datos_list
