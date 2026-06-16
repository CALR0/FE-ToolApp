import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import re
from pathlib import Path

from config.theme import (
    BG, BG2, BG3, ACCENT, ACCENT2, SUCCESS, WARNING, DANGER,
    TEXT, TEXT2, BORDER, FONT_H1, FONT_H2, FONT_BODY, FONT_SMALL,
)
from services.rndc_service import consultar_radicado_remesa

try:
    from core.xml_transformer import reconstruir_factura
    RECONSTRUIR_OK = True
    _RECONSTRUIR_ERR = ""
except Exception as _e_rec:
    import traceback as _tb_rec
    RECONSTRUIR_OK = False
    _RECONSTRUIR_ERR = f"No se pudo importar xml_transformer:\n{_tb_rec.format_exc()}"
    def reconstruir_factura(*a, **kw): return False


class ReconstruirXMLModule:
    """
    Panel embebido que reconstruye facturas UBL aplicando las transformaciones
    de cambiar_nit_factura.py según el perfil activo (ut_tsp / ut_elogia).

    Transformaciones aplicadas:
      1. Shareholders 50%/50% en PartyLegalEntity del supplier
      2. ValueQuantity unitCode: 94 → KGM
      3. PartyIdentification del Customer (si no existe)
      4. Contact del Customer: versión completa (Name, Telefax, Note)
      5. RegistrationAddress del Customer: eliminar
      6. NotificationPreferences: reemplazar por versión del socio
      7. Namespaces xmlns redundantes en InvoiceLine/WithholdingTaxTotal
      8. PaymentMeansCode: ZZZ → 31
      9. PayableRoundingAmount: agregar si no existe
      10. PrepaidAmount: eliminar
      11. Consecutivo remesa (Name=02): prefijo 0 solo para UT Elogia
    """

    def __init__(self, perfil_fn):
        """perfil_fn : callable que retorna el dict del perfil activo."""
        self.perfil_fn           = perfil_fn
        self.archivos            = []   # lista de Path seleccionados
        self._carpeta_salida     = None

    # ── Construcción del panel ────────────────────────────────────────────────

    def _build(self, container):
        self.win = container.winfo_toplevel()

        # Header
        hdr = tk.Frame(container, bg=BG2, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="🔧  Reconstruir XML",
                 font=FONT_H1, bg=BG2, fg=TEXT).pack(padx=20)
        tk.Label(hdr,
                 text="Aplica transformaciones DIAN al XML original según el perfil activo.",
                 font=FONT_SMALL, bg=BG2, fg=TEXT2).pack(padx=20)

        body = tk.Frame(container, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        # ── Card: perfil activo (informativa) ─────────────────────────────────
        info_outer = tk.Frame(body, bg=BG2)
        info_outer.pack(fill=tk.X, pady=(0, 8))
        tk.Label(info_outer, text="⚙️  Perfil activo",
                 font=FONT_H2, bg=BG2, fg=TEXT).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Frame(info_outer, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=(0, 8))
        info_inner = tk.Frame(info_outer, bg=BG2)
        info_inner.pack(fill=tk.X, padx=12, pady=(0, 12))

        self._lbl_perfil_nombre  = tk.Label(info_inner, text="—",
                                            font=("Segoe UI", 9, "bold"), bg=BG2, fg=ACCENT)
        self._lbl_perfil_nombre.pack(anchor="w")

        det_frame = tk.Frame(info_inner, bg=BG2)
        det_frame.pack(fill=tk.X, pady=(4, 0))

        def _det(label, attr):
            row = tk.Frame(det_frame, bg=BG2)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label, font=FONT_SMALL, bg=BG2, fg=TEXT2,
                     width=22, anchor="w").pack(side=tk.LEFT)
            lbl = tk.Label(row, text="—", font=FONT_SMALL, bg=BG2, fg=TEXT, anchor="w")
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            setattr(self, attr, lbl)

        _det("Socio:",     "_lbl_socio")
        _det("NIT socio:", "_lbl_nit_socio")

        # Botón refrescar perfil
        btn_ref = tk.Label(info_inner, text="↻  Actualizar perfil",
                           font=FONT_SMALL, bg=BG3, fg=TEXT2,
                           cursor="hand2", padx=8, pady=3)
        btn_ref.pack(anchor="w", pady=(6, 0))
        btn_ref.bind("<Button-1>", lambda e: self._refrescar_perfil())
        btn_ref.bind("<Enter>",    lambda e: btn_ref.configure(bg=BORDER))
        btn_ref.bind("<Leave>",    lambda e: btn_ref.configure(bg=BG3))

        # ── Card: carga de archivos ───────────────────────────────────────────
        arch_outer = tk.Frame(body, bg=BG2)
        arch_outer.pack(fill=tk.X, pady=(0, 8))
        tk.Label(arch_outer, text="📂  Archivos XML a reconstruir",
                 font=FONT_H2, bg=BG2, fg=TEXT).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Frame(arch_outer, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=(0, 8))

        btn_row = tk.Frame(arch_outer, bg=BG2)
        btn_row.pack(fill=tk.X, padx=12, pady=(0, 8))

        def _mk_btn(parent, txt, cmd, bg, hover, side=tk.LEFT):
            b = tk.Label(parent, text=txt, font=FONT_BODY,
                         bg=bg, fg="white", cursor="hand2", padx=12, pady=5)
            b.bind("<Button-1>", lambda e: cmd())
            b.bind("<Enter>",    lambda e: b.configure(bg=hover))
            b.bind("<Leave>",    lambda e: b.configure(bg=bg))
            b.pack(side=side, padx=(0, 8))
            return b

        _mk_btn(btn_row, "📁  Cargar XML(s)", self._cargar_archivos, ACCENT,     "#2d5cbf")
        _mk_btn(btn_row, "🗑  Limpiar",        self._limpiar,         "#555e7a", "#3a4060")

        self._lbl_arch = tk.Label(arch_outer, text="Sin archivos cargados.",
                                  font=FONT_SMALL, bg=BG2, fg=TEXT2, anchor="w")
        self._lbl_arch.pack(anchor="w", padx=12, pady=(0, 4))

        # Lista de archivos cargados
        list_frame = tk.Frame(arch_outer, bg=BG2)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

        _sty = ttk.Style()
        _sty.configure("Rec.Treeview",
                        background=BG2, foreground=TEXT, fieldbackground=BG2,
                        rowheight=24, borderwidth=0, font=FONT_SMALL)
        _sty.configure("Rec.Treeview.Heading",
                        background=BG3, foreground=TEXT2,
                        font=FONT_SMALL, relief="flat")
        _sty.map("Rec.Treeview",
                 background=[("selected", ACCENT)],
                 foreground=[("selected", "#ffffff")])

        cols_arch = ("Archivo", "N° Factura", "Cliente", "Remesa", "Radicado", "Peso", "Estado")
        self._tree_arch = ttk.Treeview(list_frame, columns=cols_arch,
                                       show="headings", style="Rec.Treeview", height=7)
        for col, w in zip(cols_arch, (170, 80, 150, 90, 100, 60, 160)):
            self._tree_arch.heading(col, text=col)
            self._tree_arch.column(col, width=w,
                                   anchor="w" if col in ("Archivo", "Cliente", "Estado") else "center",
                                   stretch=(col in ("Cliente", "Estado")))

        _sb_arch = ttk.Scrollbar(list_frame, orient="vertical", command=self._tree_arch.yview)
        self._tree_arch.configure(yscrollcommand=_sb_arch.set)
        _sb_arch.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree_arch.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._tree_arch.tag_configure("alt",     background=BG3)
        self._tree_arch.tag_configure("norm",    background=BG2)
        self._tree_arch.tag_configure("ok",      foreground=SUCCESS)
        self._tree_arch.tag_configure("err",     foreground=DANGER)
        self._tree_arch.tag_configure("proc",    foreground=ACCENT)

        # ── Card: carpeta de salida ───────────────────────────────────────────
        sal_outer = tk.Frame(body, bg=BG2)
        sal_outer.pack(fill=tk.X, pady=(0, 8))
        tk.Label(sal_outer, text="📁  Carpeta de salida",
                 font=FONT_H2, bg=BG2, fg=TEXT).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Frame(sal_outer, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=(0, 8))
        sal_inner = tk.Frame(sal_outer, bg=BG2)
        sal_inner.pack(fill=tk.X, padx=12, pady=(0, 12))

        sal_row = tk.Frame(sal_inner, bg=BG2)
        sal_row.pack(fill=tk.X)
        self._var_carpeta = tk.StringVar()
        ent_sal = tk.Entry(sal_row, textvariable=self._var_carpeta, font=FONT_BODY,
                           bg=BG3, fg=TEXT, insertbackground=TEXT, relief="flat",
                           highlightthickness=1, highlightbackground=BORDER,
                           highlightcolor=ACCENT)
        ent_sal.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        btn_sal = tk.Label(sal_row, text="Examinar…", font=FONT_SMALL,
                           bg=BG3, fg=TEXT, cursor="hand2", padx=8, pady=4)
        btn_sal.pack(side=tk.LEFT)
        btn_sal.bind("<Button-1>", lambda e: self._seleccionar_carpeta())
        btn_sal.bind("<Enter>",    lambda e: btn_sal.configure(bg=BORDER))
        btn_sal.bind("<Leave>",    lambda e: btn_sal.configure(bg=BG3))

        self._lbl_carpeta_hint = tk.Label(sal_inner, text="",
                                          font=FONT_SMALL, bg=BG2, fg=TEXT2, anchor="w")
        self._lbl_carpeta_hint.pack(anchor="w", pady=(4, 0))
        # Mostrar carpeta por defecto del perfil como referencia
        self._var_carpeta.trace_add("write", self._on_carpeta_changed)

        # ── Botón principal Reconstruir ───────────────────────────────────────
        pie = tk.Frame(body, bg=BG)
        pie.pack(fill=tk.X, pady=(0, 8))

        self._btn_rec = tk.Label(pie, text="🔧  Reconstruir facturas",
                                 font=("Segoe UI", 9, "bold"),
                                 bg="#7c3aed", fg="white", cursor="hand2",
                                 padx=16, pady=8)
        self._btn_rec.pack(side=tk.LEFT)
        self._btn_rec.bind("<Button-1>", lambda e: self._reconstruir())
        self._btn_rec.bind("<Enter>",    lambda e: self._btn_rec.configure(bg="#5b21b6"))
        self._btn_rec.bind("<Leave>",    lambda e: self._btn_rec.configure(bg="#7c3aed"))

        self._lbl_prog = tk.Label(pie, text="", font=FONT_SMALL,
                                  bg=BG, fg=TEXT2, anchor="w")
        self._lbl_prog.pack(side=tk.LEFT, padx=(12, 0), fill=tk.X, expand=True)

        # ── Barra de progreso ─────────────────────────────────────────────────
        prog_frame = tk.Frame(body, bg=BG)
        prog_frame.pack(fill=tk.X, pady=(0, 4))
        self._prog_var = tk.DoubleVar(value=0)
        self._progressbar = ttk.Progressbar(prog_frame, variable=self._prog_var,
                                            maximum=100, mode="determinate")
        self._progressbar.pack(fill=tk.X)

        # Inicializar con perfil actual
        self._refrescar_perfil()

    # ── Perfil ────────────────────────────────────────────────────────────────

    def _on_carpeta_changed(self, *_):
        """Actualiza el hint bajo el campo carpeta."""
        val = self._var_carpeta.get().strip()
        p   = self.perfil_fn()
        def_carpeta = p.get("carpeta_reconstruir", "FACTURAS_RECONSTRUIDAS")
        if val:
            self._lbl_carpeta_hint.configure(
                text=f"Carpeta personalizada seleccionada.", fg=ACCENT)
        else:
            self._lbl_carpeta_hint.configure(
                text=f"Por defecto: {def_carpeta}", fg=TEXT2)

    def _refrescar_perfil(self):
        """Lee el perfil activo y actualiza las etiquetas informativas."""
        p = self.perfil_fn()
        self._lbl_perfil_nombre.configure(text=p.get("nombre", "—"))
        self._lbl_socio.configure(    text=p.get("nombre_socio", "—"))
        self._lbl_nit_socio.configure(text=p.get("nit_socio", "—"))
        # Actualizar hint de carpeta con el perfil nuevo
        self._var_carpeta.set("")   # limpiar selección anterior al cambiar perfil
        self._on_carpeta_changed()

    # ── Archivos ──────────────────────────────────────────────────────────────

    def _cargar_archivos(self):
        rutas = filedialog.askopenfilenames(
            title="Selecciona XML(s) a reconstruir",
            filetypes=[("XML", "*.xml"), ("Todos", "*.*")],
        )
        if not rutas:
            return
        for ruta in rutas:
            p = Path(ruta)
            if any(str(a) == str(p) for a in self.archivos):
                continue   # no duplicar
            self.archivos.append(p)

        self._refrescar_lista()

    def _refrescar_lista(self):
        for item in self._tree_arch.get_children():
            self._tree_arch.delete(item)

        for i, ruta in enumerate(self.archivos):
            nf, cli = self._leer_cabecera_xml(ruta)
            tag = "alt" if i % 2 == 0 else "norm"
            self._tree_arch.insert("", "end", iid=str(i),
                                   values=(ruta.name, nf, cli, "", "", "", "⏳ Pendiente"),
                                   tags=(tag,))

        n = len(self.archivos)
        self._lbl_arch.configure(
            text=f"{n} archivo{'s' if n != 1 else ''} cargado{'s' if n != 1 else ''}." if n else "Sin archivos cargados.",
            fg=TEXT if n else TEXT2)

    def _limpiar(self):
        self.archivos = []
        for item in self._tree_arch.get_children():
            self._tree_arch.delete(item)
        self._lbl_arch.configure(text="Sin archivos cargados.", fg=TEXT2)
        self._prog_var.set(0)
        self._lbl_prog.configure(text="")
        self._btn_rec.configure(text="🔧  Reconstruir facturas", bg="#7c3aed")

    def _seleccionar_carpeta(self):
        carpeta = filedialog.askdirectory(title="Selecciona carpeta de salida")
        if carpeta:
            self._var_carpeta.set(carpeta)

    # ── Leer cabecera del XML ─────────────────────────────────────────────────

    @staticmethod
    def _leer_cabecera_xml(ruta):
        """Devuelve (numero_factura, nombre_cliente) del XML."""
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read()
            m_cdata = re.search(r"<!\[CDATA\[(.*?)\]\]>", contenido, re.DOTALL)
            inv = m_cdata.group(1) if m_cdata else contenido
            m_num = re.search(r"<cbc:ID>([^<]+)</cbc:ID>", inv)
            nf = m_num.group(1).strip() if m_num else "—"
            nombre_cli = "—"
            cs = inv.find("<cac:AccountingCustomerParty")
            ce = inv.find("</cac:AccountingCustomerParty>", cs)
            if cs != -1:
                bloque = inv[cs:ce]
                mc = re.search(r"<cbc:RegistrationName>([^<]+)</cbc:RegistrationName>", bloque)
                if not mc:
                    mc = re.search(r"<cac:PartyName>\s*<cbc:Name>([^<]+)</cbc:Name>", bloque)
                nombre_cli = mc.group(1).strip() if mc else "—"
            return nf, nombre_cli
        except Exception:
            return "—", "—"

    # ── Pre-procesamiento ─────────────────────────────────────────────────────

    @staticmethod
    def _leer_remesas_xml(ruta):
        """
        Lee todas las remesas del XML.
        Retorna lista de dicts con 'consecutivo', 'radicado', 'peso'.
        """
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read()
            m = re.search(r"<!\[CDATA\[(.*?)\]\]>", contenido, re.DOTALL)
            inv = m.group(1) if m else contenido
            inv = re.sub(
                r'<cac:InvoiceLine\s+xmlns="[^"]*"(?:\s+xmlns:[^=]+="[^"]*")*\s*>',
                "<cac:InvoiceLine>", inv)
            lineas = re.findall(r"<cac:InvoiceLine.*?</cac:InvoiceLine>", inv, re.DOTALL)
            remesas = []
            for linea in lineas:
                def _prop(name):
                    m2 = re.search(
                        rf"<cac:AdditionalItemProperty>\s*<cbc:Name>\s*{re.escape(name)}\s*</cbc:Name>\s*"
                        rf"<cbc:Value>([^<]*)</cbc:Value>", linea)
                    return m2.group(1).strip() if m2 else ""
                m_peso = re.search(
                    r"<cac:AdditionalItemProperty>\s*<cbc:Name>\s*03\s*</cbc:Name>\s*"
                    r"<cbc:Value>[^<]*</cbc:Value>\s*"
                    r"<cbc:ValueQuantity[^>]*>([^<]+)</cbc:ValueQuantity>", linea)
                peso = m_peso.group(1).strip() if m_peso else ""
                if not peso:
                    m_iq = re.search(r"<cbc:InvoicedQuantity[^>]*>([^<]+)</cbc:InvoicedQuantity>", linea)
                    peso = m_iq.group(1).strip() if m_iq else ""
                remesas.append({
                    "consecutivo": _prop("02"),
                    "radicado":    _prop("01"),
                    "peso":        peso,
                })
            return remesas
        except Exception:
            return []

    @staticmethod
    def _actualizar_radicados_en_xml(ruta_xml, perfil, prefijo_remesa=False):
        """
        Abre el XML reconstruido, consulta el RNDC por cada consecutivo de remesa
        (Name=02), y sobreescribe el radicado (Name=01) y el peso (ValueQuantity)
        directamente en el archivo.
        Retorna lista de dicts {consecutivo, radicado, peso} con los valores aplicados.
        """
        try:
            with open(ruta_xml, "r", encoding="utf-8") as f:
                contenido = f.read()
        except Exception:
            return []

        # Extraer Invoice del CDATA si existe
        m_cdata = re.search(r"(<!\[CDATA\[)(.*?)(\]\]>)", contenido, re.DOTALL)
        if m_cdata:
            inv = m_cdata.group(2)
        else:
            inv = contenido

        # Normalizar namespaces en InvoiceLine para el regex
        inv_norm = re.sub(
            r'<cac:InvoiceLine\s+xmlns="[^"]*"(?:\s+xmlns:[^=]+="[^"]*")*\s*>',
            "<cac:InvoiceLine>", inv)

        lineas = re.findall(r"<cac:InvoiceLine.*?</cac:InvoiceLine>", inv_norm, re.DOTALL)

        def _get_prop(linea, name):
            m = re.search(
                rf"<cac:AdditionalItemProperty>\s*<cbc:Name>\s*{re.escape(name)}\s*</cbc:Name>\s*"
                rf"<cbc:Value>([^<]*)</cbc:Value>", linea)
            return m.group(1).strip() if m else ""

        def _set_prop(linea, name, valor):
            patron = (
                rf"(<cac:AdditionalItemProperty>\s*<cbc:Name>\s*{re.escape(name)}\s*</cbc:Name>\s*"
                rf"<cbc:Value>)[^<]*(</cbc:Value>)"
            )
            return re.sub(patron, rf"\g<1>{valor}\g<2>", linea)

        def _set_peso(linea, peso):
            pat = (
                r"(<cac:AdditionalItemProperty>\s*<cbc:Name>\s*03\s*</cbc:Name>\s*"
                r"<cbc:Value>[^<]*</cbc:Value>\s*"
                r"<cbc:ValueQuantity[^>]*>)[^<]*(</cbc:ValueQuantity>)"
            )
            nueva, n = re.subn(pat, rf"\g<1>{peso}\g<2>", linea)
            if n:
                return nueva
            return re.sub(
                r"(<cbc:InvoicedQuantity[^>]*>)[^<]*(</cbc:InvoicedQuantity>)",
                rf"\g<1>{peso}\g<2>", linea)

        resultados = []
        inv_actualizado = inv_norm

        for linea_orig in lineas:
            consec_raw = _get_prop(linea_orig, "02").strip()
            if not consec_raw:
                continue
            consec_rndc = ("0" + consec_raw) if prefijo_remesa else consec_raw
            ok, resultado = consultar_radicado_remesa(consec_rndc, perfil)
            if not ok:
                resultados.append({"consecutivo": consec_raw, "radicado": "", "peso": ""})
                continue

            radicado = resultado.get("radicado", "")
            peso     = resultado.get("peso", "")

            linea_nueva = linea_orig
            if radicado:
                linea_nueva = _set_prop(linea_nueva, "01", radicado)
            if peso != "":
                linea_nueva = _set_peso(linea_nueva, peso)

            inv_actualizado = inv_actualizado.replace(linea_orig, linea_nueva, 1)
            resultados.append({"consecutivo": consec_raw, "radicado": radicado, "peso": peso})

        # Reconstruir el contenido completo
        if m_cdata:
            contenido_nuevo = (
                contenido[:m_cdata.start(2)]
                + inv_actualizado
                + contenido[m_cdata.end(2):]
            )
        else:
            contenido_nuevo = inv_actualizado

        try:
            with open(ruta_xml, "w", encoding="utf-8") as f:
                f.write(contenido_nuevo)
        except Exception:
            pass

        return resultados

    @staticmethod
    def _preprocesar_xml(ruta_entrada, ruta_tmp):
        """
        Prepara el XML antes de pasarlo a reconstruir_factura:
          1. Elimina todos los bloques <cac:ShareholderParty> existentes
          2. Normaliza el ancla de CorporateRegistrationScheme a una sola línea.
        Escribe el resultado en ruta_tmp y retorna True si OK.
        """
        try:
            with open(ruta_entrada, "r", encoding="utf-8") as f:
                contenido = f.read()

            m_cdata = re.search(r"(<!\[CDATA\[)(.*?)(\]\]>)", contenido, re.DOTALL)
            if not m_cdata:
                import shutil
                shutil.copy2(str(ruta_entrada), str(ruta_tmp))
                return True

            inv = m_cdata.group(2)

            # 1. Eliminar todos los ShareholderParty existentes
            inv = re.sub(
                r"<cac:ShareholderParty>.*?</cac:ShareholderParty>",
                "", inv, flags=re.DOTALL
            )

            # 2. Normalizar ancla CorporateRegistrationScheme a formato compacto
            inv = re.sub(
                r"<cac:CorporateRegistrationScheme>\s*<cbc:ID>41</cbc:ID>\s*<cbc:Name\s*/>\s*</cac:CorporateRegistrationScheme>",
                "<cac:CorporateRegistrationScheme><cbc:ID>41</cbc:ID><cbc:Name /></cac:CorporateRegistrationScheme>",
                inv
            )

            contenido_nuevo = (
                contenido[:m_cdata.start(2)]
                + inv
                + contenido[m_cdata.end(2):]
            )

            with open(ruta_tmp, "w", encoding="utf-8") as f:
                f.write(contenido_nuevo)
            return True

        except Exception as e:
            import traceback
            print(f"[X] Error en preprocesamiento: {e}\n{traceback.format_exc()}")
            return False

    # ── Reconstrucción ────────────────────────────────────────────────────────

    def _reconstruir(self):
        if not RECONSTRUIR_OK:
            messagebox.showerror(
                "Módulo no disponible",
                "No se pudo importar el módulo de transformación XML.\n\n"
                + _RECONSTRUIR_ERR
            )
            return

        if not self.archivos:
            messagebox.showwarning("Sin archivos", "Carga primero al menos un XML.")
            return

        carpeta_sal = self._var_carpeta.get().strip()
        if not carpeta_sal:
            p = self.perfil_fn()
            carpeta_sal = p.get("carpeta_reconstruir", "FACTURAS_RECONSTRUIDAS")

        p = self.perfil_fn()
        total     = len(self.archivos)
        ok_count  = 0
        err_count = 0

        self._btn_rec.configure(text="⏳  Procesando…", bg="#555e7a")
        self.win.update_idletasks()

        for idx, ruta in enumerate(self.archivos):
            self._lbl_prog.configure(text=f"{idx + 1}/{total}  {ruta.name}")
            self._prog_var.set((idx / total) * 100)
            self.win.update_idletasks()

            # Marcar como procesando
            if self._tree_arch.exists(str(idx)):
                vals = self._tree_arch.item(str(idx), "values")
                self._tree_arch.item(str(idx),
                    values=(vals[0], vals[1], vals[2], "⏳ Procesando…"),
                    tags=("proc",))
            self.win.update_idletasks()

            _exc_msg = ""
            try:
                import io, sys as _sys, traceback as _tb, tempfile as _tmp

                # Preprocesar: limpiar shareholders anteriores y normalizar ancla
                _fd, _ruta_tmp = _tmp.mkstemp(suffix=".xml")
                import os as _os
                _os.close(_fd)
                _ruta_tmp = Path(_ruta_tmp)
                _pre_ok = self._preprocesar_xml(ruta, _ruta_tmp)
                if not _pre_ok:
                    _ruta_tmp.unlink(missing_ok=True)
                    raise RuntimeError("Falló el preprocesamiento del XML")

                # Llamar a reconstruir_factura con el XML preprocesado
                _buf = io.StringIO()
                _old_stdout = _sys.stdout
                _sys.stdout = _buf
                exito = reconstruir_factura(
                    ruta_archivo    = _ruta_tmp,
                    carpeta_salida  = carpeta_sal,
                    nit_sp          = p.get("nit_socio", ""),
                    nombre_sp       = p.get("nombre_socio", ""),
                    nit_ut          = p.get("nit_ut", "901101271"),
                    nombre_ut       = p.get("nombre_ut", "UNION TEMPORAL AMERICAN LOGISTIC UT"),
                    email_customer  = p.get("email_customer", "facturacion@drummondltd.com"),
                    telefono_customer=p.get("telefono_customer", "3135398327"),
                    email_from_sp   = p.get("email_from", "emisionfe@sanchezpolo.com"),
                    nit_customer    = p.get("nit_customer", "800021308"),
                    prefijo_remesa  = p.get("prefijo_remesa", False),
                )
                _sys.stdout = _old_stdout
                _printed = _buf.getvalue().strip()

                # Renombrar el output al nombre original
                if exito:
                    import shutil as _sh
                    _carpeta = Path(carpeta_sal)
                    _carpeta.mkdir(parents=True, exist_ok=True)
                    _nombre_orig = ruta.name
                    _nombre_tmp  = _ruta_tmp.name
                    _out_tmp  = _carpeta / _nombre_tmp
                    _out_orig = _carpeta / _nombre_orig
                    if _out_tmp.exists() and _out_tmp != _out_orig:
                        _sh.move(str(_out_tmp), str(_out_orig))

                _ruta_tmp.unlink(missing_ok=True)

                if not exito:
                    _exc_msg = _printed or "reconstruir_factura devolvió False"
                    messagebox.showerror(
                        f"Error al reconstruir: {ruta.name}",
                        f"La función de reconstrucción falló.\n\nDetalle:\n{_exc_msg}"
                    )
            except Exception as exc:
                try:
                    _sys.stdout = _old_stdout
                except Exception:
                    pass
                try:
                    _ruta_tmp.unlink(missing_ok=True)
                except Exception:
                    pass
                exito = False
                _exc_msg = _tb.format_exc()
                messagebox.showerror(
                    f"Excepción al reconstruir: {ruta.name}",
                    f"{_exc_msg[-800:]}"
                )

            if self._tree_arch.exists(str(idx)):
                vals = self._tree_arch.item(str(idx), "values")
                if exito:
                    estado   = "✓ Reconstruido"
                    tag      = "ok"
                    ok_count += 1

                    # ── Actualizar radicado y peso en el XML reconstruido ─────
                    ruta_reconstruida = Path(carpeta_sal) / ruta.name
                    self._tree_arch.item(str(idx),
                        values=(vals[0], vals[1], vals[2], "", "🔍…", "", "✓ Reconstruido"),
                        tags=(tag,))
                    self.win.update_idletasks()

                    resultados_rndc = self._actualizar_radicados_en_xml(
                        ruta_reconstruida, p,
                        prefijo_remesa=p.get("prefijo_remesa", False))

                    primera = True
                    for rem in resultados_rndc:
                        consec_raw   = rem.get("consecutivo", "")
                        radicado_val = rem.get("radicado", "")
                        peso_val     = rem.get("peso", "")

                        if primera:
                            self._tree_arch.item(str(idx),
                                values=(vals[0], vals[1], vals[2], consec_raw, radicado_val, peso_val, estado),
                                tags=(tag,))
                            primera = False
                        else:
                            iid_extra = f"{idx}_r{consec_raw}"
                            if not self._tree_arch.exists(iid_extra):
                                self._tree_arch.insert("", "end", iid=iid_extra,
                                    values=(vals[0], vals[1], vals[2], consec_raw, radicado_val, peso_val, estado),
                                    tags=(tag,))

                    if not resultados_rndc:
                        self._tree_arch.item(str(idx),
                            values=(vals[0], vals[1], vals[2], "", "", "", estado),
                            tags=(tag,))
                else:
                    motivo = _exc_msg.replace("\n", " ").strip()
                    if not motivo:
                        motivo = "reconstruir_factura devolvió False"
                    estado = f"✗ {motivo[:100]}"
                    tag    = "err"
                    err_count += 1
                    self._tree_arch.item(str(idx),
                        values=(vals[0], vals[1], vals[2], "", "", "", estado),
                        tags=(tag,))

        self._prog_var.set(100)
        self._btn_rec.configure(text="🔧  Reconstruir facturas", bg="#7c3aed")

        if err_count == 0:
            msg  = f"✓  {ok_count} factura{'s' if ok_count != 1 else ''} reconstruida{'s' if ok_count != 1 else ''} → {carpeta_sal}"
            color = SUCCESS
        elif ok_count == 0:
            msg  = f"✗  {err_count} archivo{'s' if err_count != 1 else ''} con error. Revisa los archivos."
            color = DANGER
        else:
            msg  = f"✓ {ok_count} OK  ✗ {err_count} con error → {carpeta_sal}"
            color = WARNING

        self._lbl_prog.configure(text=msg, fg=color)
