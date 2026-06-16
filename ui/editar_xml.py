import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import re
from pathlib import Path
from datetime import datetime, timedelta

from config.theme import (
    BG, BG2, BG3, ACCENT, ACCENT2, SUCCESS, WARNING, DANGER,
    TEXT, TEXT2, BORDER, FONT_H1, FONT_H2, FONT_BODY, FONT_SMALL,
)
from core.xml_generator import _fmt_valor, _parse_valor
from services.rndc_service import consultar_radicado_remesa


class EditarXMLModule:
    """
    Panel embebido en el sidebar para editar campos de un XML de factura DIAN:
      - Número de factura y CUFE (campos globales)
      - Por remesa: Consecutivo, Radicado, Valor, Peso  (edición inline)
    Compatible con AttachedDocument (Invoice en CDATA) e Invoice directo.
    """

    COLUMNAS = [
        ("#",                4,   False),
        ("Consecutivo",      16,  True),
        ("Radicado",         18,  True),
        ("Valor ($)",        14,  True),
        ("Peso",             10,  True),
        ("Descripción línea",28,  True),
    ]

    def __init__(self, parent, perfil_fn=None):
        self.parent = parent
        self.perfil_fn      = perfil_fn  # callable → dict perfil activo
        self.ruta_xml       = None
        self.contenido_xml  = ""
        self.remesas        = []

        self.var_numero   = tk.StringVar()
        self.var_cufe     = tk.StringVar()
        self.var_cliente  = tk.StringVar()
        self.var_fecha    = tk.StringVar()
        self.var_total    = tk.StringVar()
        self._numero_orig    = ""
        self._cufe_orig      = ""
        self._fecha_orig     = ""  # valor literal en el XML (puede ser DD-MM-YYYY o YYYY-MM-DD)
        self._fecha_orig_iso = ""  # siempre YYYY-MM-DD
        self._total_orig     = ""  # valor tal como está en el XML

    # ── Construcción del panel (embebido en container) ────────────────────────

    def _build(self, container):
        self.win = container.winfo_toplevel()

        # ── Header de sección ─────────────────────────────────────────────────
        hdr = tk.Frame(container, bg=BG2, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="✏️  Editor de XML — Remesas y Datos",
                 font=FONT_H1, bg=BG2, fg=TEXT).pack(padx=20)
        tk.Label(hdr, text="Carga un XML, edita los campos y guarda directamente sobre el archivo.",
                 font=FONT_SMALL, bg=BG2, fg=TEXT2).pack(padx=20)

        body = tk.Frame(container, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        # ── Fila: abrir archivo ───────────────────────────────────────────────
        top = tk.Frame(body, bg=BG2, pady=10, padx=12)
        top.pack(fill=tk.X, pady=(0, 8))

        self._btn_abrir = tk.Label(top, text="📂  Abrir XML",
                                   font=FONT_BODY, bg=ACCENT, fg="white",
                                   cursor="hand2", padx=12, pady=5)
        self._btn_abrir.pack(side=tk.LEFT, padx=(0, 12))
        self._btn_abrir.bind("<Button-1>", lambda e: self._abrir_xml())
        self._btn_abrir.bind("<Enter>",    lambda e: self._btn_abrir.configure(bg="#2d5cbf"))
        self._btn_abrir.bind("<Leave>",    lambda e: self._btn_abrir.configure(bg=ACCENT))

        self._lbl_archivo = tk.Label(top, text="Ningún archivo cargado.",
                                     font=FONT_BODY, bg=BG2, fg=TEXT2, anchor="w")
        self._lbl_archivo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._btn_limpiar = tk.Label(top, text="🗑  Limpiar",
                                     font=FONT_BODY, bg="#555e7a", fg="white",
                                     cursor="hand2", padx=12, pady=5)
        self._btn_limpiar.pack(side=tk.RIGHT)
        self._btn_limpiar.bind("<Button-1>", lambda e: self._limpiar())
        self._btn_limpiar.bind("<Enter>",    lambda e: self._btn_limpiar.configure(bg="#3a4060"))
        self._btn_limpiar.bind("<Leave>",    lambda e: self._btn_limpiar.configure(bg="#555e7a"))

        # ── Card: Datos generales ─────────────────────────────────────────────
        gen_outer = tk.Frame(body, bg=BG2, bd=0)
        gen_outer.pack(fill=tk.X, pady=(0, 8))
        title_row = tk.Frame(gen_outer, bg=BG2)
        title_row.pack(fill=tk.X, padx=12, pady=(10, 4))
        tk.Label(title_row, text="📄  Datos Generales de la Factura",
                 font=FONT_H2, bg=BG2, fg=TEXT).pack(side=tk.LEFT)
        tk.Frame(gen_outer, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=(0, 8))
        gen_inner = tk.Frame(gen_outer, bg=BG2)
        gen_inner.pack(fill=tk.X, padx=12, pady=(0, 12))

        # Fila N° Factura + CUFE
        row_nf = tk.Frame(gen_inner, bg=BG2)
        row_nf.pack(fill=tk.X, pady=3)
        tk.Label(row_nf, text="N° Factura", font=FONT_BODY, bg=BG2,
                 fg=TEXT2, width=14, anchor="w").pack(side=tk.LEFT)
        tk.Entry(row_nf, textvariable=self.var_numero, font=FONT_BODY, width=18,
                 bg=BG3, fg=TEXT, insertbackground=TEXT, relief="flat",
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side=tk.LEFT, padx=(0, 16))
        tk.Label(row_nf, text="CUFE", font=FONT_BODY, bg=BG2,
                 fg=TEXT2, width=6, anchor="w").pack(side=tk.LEFT)
        tk.Entry(row_nf, textvariable=self.var_cufe, font=FONT_BODY,
                 bg=BG3, fg=TEXT, insertbackground=TEXT, relief="flat",
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Fila Cliente (solo lectura)
        row_cli = tk.Frame(gen_inner, bg=BG2)
        row_cli.pack(fill=tk.X, pady=3)
        tk.Label(row_cli, text="Cliente", font=FONT_BODY, bg=BG2,
                 fg=TEXT2, width=14, anchor="w").pack(side=tk.LEFT)
        ent_cli = tk.Entry(row_cli, textvariable=self.var_cliente, font=FONT_BODY,
                           bg=BG3, fg=TEXT2, relief="flat",
                           highlightthickness=1, highlightbackground=BORDER,
                           state="readonly")
        ent_cli.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Fila Fecha de generación (editable) + Fecha de vencimiento (calculada, solo lectura)
        row_fec = tk.Frame(gen_inner, bg=BG2)
        row_fec.pack(fill=tk.X, pady=3)
        tk.Label(row_fec, text="Fecha de generación", font=FONT_BODY, bg=BG2,
                 fg=TEXT2, width=20, anchor="w").pack(side=tk.LEFT)
        ent_fecha = tk.Entry(row_fec, textvariable=self.var_fecha, font=FONT_BODY, width=14,
                             bg=BG3, fg=TEXT, insertbackground=TEXT, relief="flat",
                             highlightthickness=1, highlightbackground=BORDER,
                             highlightcolor=ACCENT)
        ent_fecha.pack(side=tk.LEFT, padx=(0, 16))
        tk.Label(row_fec, text="DD-MM-YYYY / YYYY-MM-DD", font=FONT_SMALL, bg=BG2, fg=TEXT2).pack(side=tk.LEFT, padx=(0, 20))
        tk.Label(row_fec, text="Vencimiento (+30 días):", font=FONT_BODY, bg=BG2,
                 fg=TEXT2).pack(side=tk.LEFT, padx=(0, 6))
        self._lbl_vencimiento = tk.Label(row_fec, text="—", font=FONT_BODY,
                                         bg=BG2, fg=ACCENT)
        self._lbl_vencimiento.pack(side=tk.LEFT)
        # Actualizar etiqueta de vencimiento al editar la fecha
        self.var_fecha.trace_add("write", self._on_fecha_changed)

        # Fila Valor total factura ($)
        row_tot = tk.Frame(gen_inner, bg=BG2)
        row_tot.pack(fill=tk.X, pady=3)
        tk.Label(row_tot, text="Total valor factura ($)", font=FONT_BODY, bg=BG2,
                 fg=TEXT2, width=22, anchor="w").pack(side=tk.LEFT)
        tk.Entry(row_tot, textvariable=self.var_total, font=FONT_BODY, width=20,
                 bg=BG3, fg=TEXT, insertbackground=TEXT, relief="flat",
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side=tk.LEFT, padx=(0, 10))
        self._lbl_total_fmt = tk.Label(row_tot, text="", font=FONT_BODY,
                                       bg=BG2, fg=ACCENT, anchor="w")
        self._lbl_total_fmt.pack(side=tk.LEFT)
        self.var_total.trace_add("write", self._on_total_changed)

        # ── Card: Tabla de remesas ────────────────────────────────────────────
        rem_outer = tk.Frame(body, bg=BG2, bd=0)
        rem_outer.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        tr = tk.Frame(rem_outer, bg=BG2)
        tr.pack(fill=tk.X, padx=12, pady=(10, 4))
        tk.Label(tr, text="📦  Remesas",
                 font=FONT_H2, bg=BG2, fg=TEXT).pack(side=tk.LEFT)
        self._lbl_count = tk.Label(tr, text="", font=FONT_SMALL, bg=BG2, fg=TEXT2)
        self._lbl_count.pack(side=tk.LEFT, padx=8)
        tk.Label(tr, text="💡 Doble clic para editar",
                 font=FONT_SMALL, bg=BG2, fg=TEXT2).pack(side=tk.RIGHT, padx=4)
        tk.Frame(rem_outer, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=(0, 4))

        # Treeview de remesas
        tree_frame = tk.Frame(rem_outer, bg=BG2)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 4))

        s = ttk.Style()
        s.configure("Edit.Treeview",
                    background=BG2, fieldbackground=BG2, foreground=TEXT,
                    rowheight=26, font=FONT_BODY, borderwidth=0)
        s.configure("Edit.Treeview.Heading",
                    background=BG3, foreground=TEXT2,
                    font=FONT_SMALL, relief="flat")
        s.map("Edit.Treeview",
              background=[("selected", ACCENT)],
              foreground=[("selected", "#ffffff")])

        cols = [c[0] for c in self.COLUMNAS]
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                  style="Edit.Treeview", height=14)
        for nombre, ancho, _ in self.COLUMNAS:
            self._tree.heading(nombre, text=nombre)
            stretch = nombre in ("Radicado", "Descripción línea")
            self._tree.column(nombre, width=ancho * 7, anchor="center", stretch=stretch)

        _sb_tree = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=_sb_tree.set)
        _sb_tree.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._tree.tag_configure("alt",  background=BG3)
        self._tree.tag_configure("norm", background=BG2)
        self._tree.bind("<Double-1>", self._editar_celda)

        # ── Pie: botón guardar ────────────────────────────────────────────────
        pie = tk.Frame(body, bg=BG)
        pie.pack(fill=tk.X, pady=(4, 8))

        self._btn_guardar = tk.Label(pie, text="💾  Guardar XML",
                                     font=("Segoe UI", 9, "bold"),
                                     bg=SUCCESS, fg="white", cursor="hand2",
                                     padx=14, pady=7)
        self._btn_guardar.pack(side=tk.RIGHT)
        self._btn_guardar.bind("<Button-1>", lambda e: self._guardar())
        self._btn_guardar.bind("<Enter>",    lambda e: self._btn_guardar.configure(bg="#16a34a"))
        self._btn_guardar.bind("<Leave>",    lambda e: self._btn_guardar.configure(bg=SUCCESS))

        self._lbl_status = tk.Label(pie, text="", font=FONT_SMALL,
                                    bg=BG, fg=TEXT2, anchor="w")
        self._lbl_status.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # ── Lógica de archivo ─────────────────────────────────────────────────────

    def _limpiar(self):
        self.ruta_xml      = None
        self.contenido_xml = ""
        self.remesas       = []
        self._numero_orig     = ""
        self._cufe_orig       = ""
        self._fecha_orig      = ""
        self._fecha_orig_iso  = ""
        self._total_orig      = ""
        self.var_numero.set("")
        self.var_cufe.set("")
        self.var_cliente.set("")
        self.var_fecha.set("")
        self.var_total.set("")
        self._lbl_archivo.configure(text="Ningún archivo cargado.", fg=TEXT2)
        self._lbl_count.configure(text="")
        self._lbl_status.configure(text="")
        self._lbl_vencimiento.configure(text="—", fg=TEXT2)
        self._lbl_total_fmt.configure(text="")
        for row in self._tree.get_children():
            self._tree.delete(row)

    def _abrir_xml(self):
        ruta = filedialog.askopenfilename(
            title="Selecciona XML a editar",
            filetypes=[("XML", "*.xml"), ("Todos", "*.*")],
        )
        if not ruta:
            return
        self.ruta_xml = Path(ruta)
        self._lbl_archivo.configure(text=f"✓  {self.ruta_xml.name}", fg=SUCCESS)
        self._lbl_status.configure(text="")
        self._parsear()

    def _parsear(self):
        try:
            with open(self.ruta_xml, "r", encoding="utf-8") as f:
                self.contenido_xml = f.read()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el archivo:\n{e}")
            return

        # Extraer Invoice del CDATA si existe
        m = re.search(r"<!\[CDATA\[(.*?)\]\]>", self.contenido_xml, re.DOTALL)
        inv = m.group(1) if m else self.contenido_xml

        # Normalizar namespaces redundantes en InvoiceLine
        inv_norm = re.sub(
            r'<cac:InvoiceLine\s+xmlns="[^"]*"(?:\s+xmlns:[^=]+="[^"]*")*\s*>',
            "<cac:InvoiceLine>",
            inv,
        )

        # Parsear remesas
        lineas = re.findall(r"<cac:InvoiceLine.*?</cac:InvoiceLine>", inv_norm, re.DOTALL)
        self.remesas = []
        for i, linea in enumerate(lineas):
            self.remesas.append({
                "idx":         i,
                "radicado":    self._prop(linea, "01"),
                "consecutivo": self._prop(linea, "02"),
                "valor":       self._normalizar_valor(self._prop(linea, "03")),
                "peso":        self._invoiced_qty(linea),
                "descripcion": self._descripcion(linea),
            })

        # N° factura y CUFE
        m_num  = re.search(r"<cbc:ID>([^<]+)</cbc:ID>", inv_norm)
        m_cufe = re.search(r"<cbc:UUID[^>]*>([^<]+)</cbc:UUID>", self.contenido_xml)
        num_orig  = m_num.group(1).strip()  if m_num  else ""
        cufe_orig = m_cufe.group(1).strip() if m_cufe else ""
        self.var_numero.set(num_orig)
        self.var_cufe.set(cufe_orig)
        self._numero_orig = num_orig
        self._cufe_orig   = cufe_orig

        # Fecha de generación (IssueDate dentro del Invoice — puede ser YYYY-MM-DD o DD-MM-YYYY)
        m_fecha = re.search(r"<cbc:IssueDate>(\d{2,4}[-/]\d{2}[-/]\d{2,4})</cbc:IssueDate>", inv_norm)
        fecha_raw  = m_fecha.group(1).strip() if m_fecha else ""
        fecha_iso  = EditarXMLModule._to_iso(fecha_raw)  # normalizado para cálculos internos
        self.var_fecha.set(fecha_raw)          # muestra el valor tal como está en el XML
        self._fecha_orig     = fecha_raw   # valor literal del XML (para el reemplazo exacto)
        self._fecha_orig_iso = fecha_iso   # normalizado, para cálculo de vencimiento

        # Cliente
        cust_start = inv_norm.find("<cac:AccountingCustomerParty")
        cust_end   = inv_norm.find("</cac:AccountingCustomerParty>", cust_start)
        nombre_cli = ""
        if cust_start != -1:
            bloque = inv_norm[cust_start:cust_end]
            mc = re.search(r"<cbc:RegistrationName>([^<]+)</cbc:RegistrationName>", bloque)
            if not mc:
                mc = re.search(r"<cac:PartyName>\s*<cbc:Name>([^<]+)</cbc:Name>", bloque)
            nombre_cli = mc.group(1).strip() if mc else ""
        self.var_cliente.set(nombre_cli)

        # Valor total (PayableAmount dentro del Invoice)
        m_total = re.search(r"<cbc:PayableAmount[^>]*>([^<]+)</cbc:PayableAmount>", inv_norm)
        total_raw = m_total.group(1).strip() if m_total else ""
        total_fmt = self._normalizar_valor(total_raw)
        self.var_total.set(total_fmt)
        self._total_orig = total_raw

        self._lbl_count.configure(text=f"({len(self.remesas)} remesas)")
        self._refrescar_tabla()
        self._lbl_status.configure(
            text=f"  XML cargado · {len(self.remesas)} remesa(s) encontrada(s).", fg=TEXT2)

        # ── Autocompletar radicado y peso desde el RNDC ───────────────────────
        self._consultar_radicados_rndc()

    # ── Consulta RNDC para radicado y peso ────────────────────────────────────

    def _consultar_radicados_rndc(self):
        """
        Para cada remesa con consecutivo, consulta el INGRESOID y CANTIDADCARGADA
        en el RNDC y actualiza la fila de la tabla.
        Se ejecuta automáticamente al cargar el XML.
        """
        if not self.perfil_fn:
            return
        if not self.remesas:
            return

        perfil = self.perfil_fn()
        total  = len(self.remesas)
        actualizados = 0

        for i, rem in enumerate(self.remesas):
            consec = rem.get("consecutivo", "").strip()
            if not consec:
                continue

            self._lbl_status.configure(
                text=f"  🔍 Consultando RNDC remesa {i+1}/{total} ({consec})…", fg=TEXT2)
            try:
                self.win.update_idletasks()
            except Exception:
                pass

            ok, resultado = consultar_radicado_remesa(consec, perfil)
            if ok:
                rem["radicado"] = resultado.get("radicado", rem.get("radicado", ""))
                rem["peso"]     = resultado.get("peso",     rem.get("peso", ""))
                actualizados += 1

        # Refrescar tabla con los nuevos valores
        self._refrescar_tabla()
        if actualizados:
            self._lbl_status.configure(
                text=f"  ✓ XML cargado · {total} remesa(s) · radicado/peso actualizados desde RNDC.",
                fg=SUCCESS)
        else:
            self._lbl_status.configure(
                text=f"  XML cargado · {total} remesa(s) · sin consecutivos para consultar RNDC.",
                fg=TEXT2)

    # ── Helpers de parseo ────────────────────────────────────────────────────

    @staticmethod
    def _normalizar_valor(texto):
        """Normaliza un valor leído del XML al mismo formato limpio que usa _fmt_valor.
        1.777.777,00 → '1777777'  /  1777777.00 → '1777777'  /  1777777 → '1777777'
        Si no parsea, devuelve el texto original.
        """
        try:
            return _fmt_valor(_parse_valor(texto))
        except Exception:
            return texto

    @staticmethod
    def _prop(linea, name):
        m = re.search(
            rf"<cac:AdditionalItemProperty>\s*<cbc:Name>\s*{re.escape(name)}\s*</cbc:Name>\s*"
            rf"<cbc:Value>([^<]*)</cbc:Value>",
            linea,
        )
        return m.group(1) if m else ""

    @staticmethod
    def _invoiced_qty(linea):
        m = re.search(
            r"<cac:AdditionalItemProperty>\s*<cbc:Name>\s*03\s*</cbc:Name>\s*"
            r"<cbc:Value>[^<]*</cbc:Value>\s*"
            r"<cbc:ValueQuantity[^>]*>([^<]+)</cbc:ValueQuantity>",
            linea,
        )
        if m and m.group(1).strip():
            return m.group(1).strip()
        m = re.search(r"<cbc:InvoicedQuantity[^>]*>([^<]+)</cbc:InvoicedQuantity>", linea)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _descripcion(linea):
        """Extrae cbc:Description dentro de cac:Item."""
        m = re.search(r"<cac:Item>\s*<cbc:Description>([^<]*)</cbc:Description>", linea)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _to_iso(fecha_str):
        """Convierte cualquier fecha DD-MM-YYYY o YYYY-MM-DD a YYYY-MM-DD. Devuelve el original si no reconoce."""
        s = fecha_str.strip()
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return s  # devuelve tal cual si no reconoce ningún formato

    def _on_total_changed(self, *_):
        """Muestra el valor formateado con $ y puntos al lado del campo."""
        try:
            val = _parse_valor(self.var_total.get().strip())
            self._lbl_total_fmt.configure(
                text=f"  $ {val:,.0f}".replace(",", "."), fg=ACCENT)
        except Exception:
            self._lbl_total_fmt.configure(text="", fg=TEXT2)

    def _on_fecha_changed(self, *_):
        """Actualiza la etiqueta de vencimiento (+30 días) al cambiar la fecha."""
        try:
            iso = self._to_iso(self.var_fecha.get().strip())
            nueva = datetime.strptime(iso, "%Y-%m-%d")
            venc  = (nueva + timedelta(days=30)).strftime("%Y-%m-%d")
            self._lbl_vencimiento.configure(text=venc, fg=ACCENT)
        except ValueError:
            self._lbl_vencimiento.configure(text="fecha inválida", fg=DANGER)

    # ── Tabla ─────────────────────────────────────────────────────────────────

    def _refrescar_tabla(self):
        for row in self._tree.get_children():
            self._tree.delete(row)
        for r in self.remesas:
            tag = "alt" if r["idx"] % 2 == 0 else "norm"
            self._tree.insert("", tk.END, iid=str(r["idx"]),
                              values=(r["idx"] + 1, r["consecutivo"],
                                      r["radicado"], r["valor"], r["peso"],
                                      r.get("descripcion", "")),
                              tags=(tag,))

    # ── Edición inline ────────────────────────────────────────────────────────

    def _editar_celda(self, event):
        region = self._tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        col_id  = self._tree.identify_column(event.x)
        item_id = self._tree.identify_row(event.y)
        if not item_id:
            return

        col_idx  = int(col_id.lstrip("#")) - 1
        editable = self.COLUMNAS[col_idx][2]
        if not editable:
            return

        # Mapa explícito: encabezado → clave del dict de remesa
        _col_key_map = {
            "consecutivo":      "consecutivo",
            "radicado":         "radicado",
            "valor ($)":        "valor",
            "peso":             "peso",
            "descripción línea":"descripcion",
        }
        col_name   = _col_key_map.get(self.COLUMNAS[col_idx][0].lower(), self.COLUMNAS[col_idx][0].lower())
        valores    = self._tree.item(item_id, "values")
        valor_actual = valores[col_idx]

        x, y, w, h = self._tree.bbox(item_id, col_id)
        entry_var = tk.StringVar(value=valor_actual)
        entry = tk.Entry(self._tree, textvariable=entry_var,
                         bg=ACCENT, fg="#ffffff", insertbackground="#ffffff",
                         relief="flat", font=FONT_BODY,
                         highlightthickness=1, highlightbackground="#2d5cbf",
                         highlightcolor="#2d5cbf")
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()
        entry.select_range(0, tk.END)

        def confirmar(e=None):
            nuevo = entry_var.get().strip()
            entry.destroy()
            idx = int(item_id)
            self.remesas[idx][col_name] = nuevo
            self._refrescar_tabla()

        def cancelar(e=None):
            entry.destroy()

        entry.bind("<Return>",   confirmar)
        entry.bind("<Tab>",      confirmar)
        entry.bind("<Escape>",   cancelar)
        entry.bind("<FocusOut>", confirmar)

    # ── Guardar ───────────────────────────────────────────────────────────────

    def _guardar(self):
        if not self.ruta_xml or not self.remesas:
            messagebox.showwarning("Sin archivo", "Primero carga un XML.")
            return
        try:
            m_cdata = re.search(r"(<!\[CDATA\[)(.*?)(\]\]>)", self.contenido_xml, re.DOTALL)
            if not m_cdata:
                messagebox.showerror("Error", "No se encontró bloque CDATA en el XML.")
                return

            inv = m_cdata.group(2)
            lineas_orig = re.findall(r"<cac:InvoiceLine.*?</cac:InvoiceLine>", inv, re.DOTALL)
            inv_nuevo = inv

            for r in self.remesas:
                if r["idx"] >= len(lineas_orig):
                    continue
                linea_orig  = lineas_orig[r["idx"]]
                linea_nueva = linea_orig
                # Normalizar valor: acepta 1.777.777,00 / 1,777,777.00 / 1777777 → "1777777"
                try:
                    _val_fmt = _fmt_valor(_parse_valor(r["valor"]))
                except Exception:
                    _val_fmt = r["valor"]  # si no parsea, dejar como está
                linea_nueva = self._set_prop(linea_nueva, "01", r["radicado"])
                linea_nueva = self._set_prop(linea_nueva, "02", r["consecutivo"])
                linea_nueva = self._set_prop_03(linea_nueva, _val_fmt, r["peso"])
                linea_nueva = self._set_invoiced_qty(linea_nueva, r["peso"])
                linea_nueva = self._set_descripcion(linea_nueva, r.get("descripcion", ""))
                inv_nuevo   = inv_nuevo.replace(linea_orig, linea_nueva, 1)

            contenido_nuevo = (
                self.contenido_xml[: m_cdata.start(2)]
                + inv_nuevo
                + self.contenido_xml[m_cdata.end(2):]
            )

            # ── N° Factura ────────────────────────────────────────────────────
            num_nuevo = self.var_numero.get().strip()
            if num_nuevo and self._numero_orig and num_nuevo != self._numero_orig:
                contenido_nuevo = re.sub(
                    rf"(<cbc:ID>){re.escape(self._numero_orig)}(</cbc:ID>)",
                    rf"\g<1>{num_nuevo}\g<2>", contenido_nuevo,
                )
                contenido_nuevo = re.sub(
                    rf"(<cbc:ParentDocumentID>){re.escape(self._numero_orig)}(</cbc:ParentDocumentID>)",
                    rf"\g<1>{num_nuevo}\g<2>", contenido_nuevo,
                )

            # ── CUFE ──────────────────────────────────────────────────────────
            cufe_nuevo = self.var_cufe.get().strip()
            if cufe_nuevo and self._cufe_orig and cufe_nuevo != self._cufe_orig:
                contenido_nuevo = re.sub(
                    rf"(<cbc:UUID[^>]*>){re.escape(self._cufe_orig)}(</cbc:UUID>)",
                    rf"\g<1>{cufe_nuevo}\g<2>", contenido_nuevo,
                )
                contenido_nuevo = contenido_nuevo.replace(
                    f"documentkey={self._cufe_orig}", f"documentkey={cufe_nuevo}"
                )

            # ── Valor total factura ───────────────────────────────────────────
            total_nuevo_raw = self.var_total.get().strip()
            if total_nuevo_raw and self._total_orig:
                try:
                    total_nuevo = _fmt_valor(_parse_valor(total_nuevo_raw))
                    # Calcular retención = 1% del total
                    retencion_nueva = _fmt_valor(round(_parse_valor(total_nuevo_raw) * 0.01, 2))
                    # LegalMonetaryTotal: LineExtensionAmount, TaxInclusiveAmount, PayableAmount
                    for tag in ("LineExtensionAmount", "TaxInclusiveAmount", "PayableAmount"):
                        contenido_nuevo = re.sub(
                            rf'(<cbc:{tag}[^>]*>){re.escape(self._total_orig)}(</cbc:{tag}>)',
                            rf'\g<1>{total_nuevo}\g<2>', contenido_nuevo
                        )
                    # WithholdingTaxTotal: TaxableAmount y TaxAmount (retención 1%)
                    contenido_nuevo = re.sub(
                        rf'(<cbc:TaxableAmount[^>]*>){re.escape(self._total_orig)}(</cbc:TaxableAmount>)',
                        rf'\g<1>{total_nuevo}\g<2>', contenido_nuevo
                    )
                    contenido_nuevo = re.sub(
                        r'(<cbc:TaxAmount[^>]*>)[^<]+(</cbc:TaxAmount>)',
                        rf'\g<1>{retencion_nueva}\g<2>', contenido_nuevo
                    )
                    self._total_orig = total_nuevo
                    self.var_total.set(total_nuevo)
                except Exception as _e_tot:
                    messagebox.showwarning("Valor total inválido",
                        f"No se pudo parsear el valor '{total_nuevo_raw}': {_e_tot}\n"
                        "Formatos aceptados: 1.777.777,00 · 1777777")

            # ── Fecha de generación + Vencimiento (+30 días) ─────────────────
            fecha_nueva = self.var_fecha.get().strip()
            fecha_orig_xml = self._fecha_orig
            fecha_orig_iso = self._fecha_orig_iso
            if fecha_nueva and fecha_orig_xml and fecha_nueva != fecha_orig_iso:
                try:
                    dt_nueva   = datetime.strptime(fecha_nueva, "%Y-%m-%d")
                    venc_nueva = (dt_nueva + timedelta(days=30)).strftime("%Y-%m-%d")
                    # IssueDate: reemplaza el valor literal del XML
                    contenido_nuevo = re.sub(
                        rf"(<cbc:IssueDate>){re.escape(fecha_orig_xml)}(</cbc:IssueDate>)",
                        rf"\g<1>{fecha_nueva}\g<2>", contenido_nuevo,
                    )
                    # SigningTime: actualizar solo la parte de fecha (antes de T)
                    contenido_nuevo = re.sub(
                        rf"(<xades:SigningTime>){re.escape(fecha_orig_iso)}(T)",
                        rf"\g<1>{fecha_nueva}\g<2>", contenido_nuevo,
                    )
                    # ValidationDate
                    contenido_nuevo = re.sub(
                        rf"(<cbc:ValidationDate>){re.escape(fecha_orig_iso)}(</cbc:ValidationDate>)",
                        rf"\g<1>{fecha_nueva}\g<2>", contenido_nuevo,
                    )
                    # DueDate
                    contenido_nuevo = re.sub(
                        r"(<cbc:DueDate>)[\d/-]+(</cbc:DueDate>)",
                        rf"\g<1>{venc_nueva}\g<2>", contenido_nuevo,
                    )
                    # PaymentDueDate
                    contenido_nuevo = re.sub(
                        r"(<cbc:PaymentDueDate>)[\d/-]+(</cbc:PaymentDueDate>)",
                        rf"\g<1>{venc_nueva}\g<2>", contenido_nuevo,
                    )
                except ValueError:
                    messagebox.showwarning("Fecha inválida",
                        f"La fecha '{fecha_nueva}' no tiene el formato YYYY-MM-DD.\n"
                        "Las fechas no fueron actualizadas.")

            with open(self.ruta_xml, "w", encoding="utf-8") as f:
                f.write(contenido_nuevo)

            self.contenido_xml   = contenido_nuevo
            self._numero_orig    = self.var_numero.get().strip()
            self._cufe_orig      = self.var_cufe.get().strip()
            _f_guardada          = self.var_fecha.get().strip()
            self._fecha_orig     = _f_guardada
            self._fecha_orig_iso = _f_guardada

            self._lbl_status.configure(text=f"  ✓ Guardado correctamente: {self.ruta_xml.name}", fg=SUCCESS)
            # Flash del botón
            self._btn_guardar.configure(text="✓  Guardado", bg="#16a34a")
            self.win.after(2000, lambda: self._btn_guardar.configure(text="💾  Guardar XML", bg=SUCCESS))

        except Exception as e:
            import traceback
            messagebox.showerror("Error al guardar", f"{e}\n\n{traceback.format_exc()[:500]}")

    # ── Helpers de transformación XML ─────────────────────────────────────────

    @staticmethod
    def _set_descripcion(linea, valor):
        """Reemplaza cbc:Description dentro de cac:Item."""
        return re.sub(
            r"(<cac:Item>\s*<cbc:Description>)[^<]*(</cbc:Description>)",
            rf"\g<1>{valor}\g<2>", linea,
        )

    @staticmethod
    def _set_prop(linea, name, valor):
        patron = (
            rf"(<cac:AdditionalItemProperty>\s*<cbc:Name>\s*{re.escape(name)}\s*</cbc:Name>\s*"
            rf"<cbc:Value>)[^<]*(</cbc:Value>)"
        )
        return re.sub(patron, rf"\g<1>{valor}\g<2>", linea)

    @staticmethod
    def _set_prop_03(linea, valor, peso):
        patron = (
            r"(<cac:AdditionalItemProperty>\s*<cbc:Name>\s*03\s*</cbc:Name>\s*"
            r"<cbc:Value>)[^<]*(</cbc:Value>\s*"
            r"<cbc:ValueQuantity[^>]*>)[^<]*(</cbc:ValueQuantity>)"
        )
        return re.sub(patron, rf"\g<1>{valor}\g<2>{peso}\g<3>", linea)

    @staticmethod
    def _set_invoiced_qty(linea, peso):
        return re.sub(
            r"(<cbc:InvoicedQuantity[^>]*>)[^<]*(</cbc:InvoicedQuantity>)",
            rf"\g<1>{peso}\2", linea,
        )
