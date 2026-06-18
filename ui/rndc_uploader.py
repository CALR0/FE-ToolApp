import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os as _os

try:
    import requests as _requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

from config.theme import (
    BG, BG2, BG3, ACCENT, ACCENT2, SUCCESS, WARNING, DANGER,
    TEXT, TEXT2, BORDER, FONT_H1, FONT_H2, FONT_BODY, FONT_SMALL,
)
from utils.helpers import resource_path
from services.rndc_service import consultar_radicado_remesa


class RndcUploaderWindow:
    """
    Cargue de Factura Electrónica al RNDC por WebService SOAP.

    Protocolo exacto (Guía V5 + Guía FE V11):
      - Método  : AtenderMensajeRNDC
      - SOAPAction: urn:BPMServicesIntf-IBPMServices#AtenderMensajeRNDC
      - Proceso  : 86  (Factura Electrónica de transporte)
      - Variable : ARCHIVOBASE64  →  el XML de la DIAN convertido a Base64
      - Variable : NUMNITEMPRESATRANSPORTE → NIT de la empresa (sin dígito)
      - Endpoint Pruebas   : rndcpruebas.mintransporte.gov.co:8080
      - Endpoint Producción: rndcws.mintransporte.gov.co:8080
      - Path SOAP          : /soap/IBPMServices
      - Encoding request   : ISO-8859-1
      - Un XML por solicitud (no acepta ZIP ni múltiples en una llamada)

    Respuesta exitosa:
      <?xml version="1.0" encoding="ISO-8859-1"?>
      <root><ingresoid>12345</ingresoid></root>

    El radicado de pruebas es > 900,000,000
    """

    ENDPOINTS = {
        "Pruebas  (rndcpruebas)":  "http://rndcpruebas.mintransporte.gov.co:8080",
        "Producción (rndcws)":     "http://rndcws.mintransporte.gov.co:8080",
    }
    SOAP_PATH   = "/soap/IBPMServices"
    PROCESO     = "86"
    SOAP_ACTION = "urn:BPMServicesIntf-IBPMServices#AtenderMensajeRNDC"

    RNDC_XML_TMPL = """<?xml version='1.0' encoding='ISO-8859-1' ?>
<root>
  <acceso>
    <username>{usuario}</username>
    <password>{password}</password>
  </acceso>
  <solicitud>
    <tipo>1</tipo>
    <procesoid>{proceso}</procesoid>
  </solicitud>
  <variables>
    <NUMNITEMPRESATRANSPORTE>{nit_empresa}</NUMNITEMPRESATRANSPORTE>
    <ARCHIVOBASE64>{base64_xml}</ARCHIVOBASE64>
  </variables>
</root>"""

    SOAP_ENVELOPE_TMPL = """<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:tns="http://tempuri.org/">
  <soapenv:Header/>
  <soapenv:Body>
    <tns:AtenderMensajeRNDC>
      <Request>{rndc_xml_escaped}</Request>
    </tns:AtenderMensajeRNDC>
  </soapenv:Body>
</soapenv:Envelope>"""

    def __init__(self, parent, perfil_fn):
        """
        parent    : ventana raíz tk
        perfil_fn : callable que retorna el perfil activo (dict con nit_socio)
        """
        if not REQUESTS_OK:
            messagebox.showerror("Dependencia faltante",
                "La librería 'requests' no está instalada.\n"
                "Ejecuta: pip install requests")
            return

        self.parent    = parent
        self.perfil_fn = perfil_fn
        self.archivos  = []   # lista de (nombre_archivo, bytes_contenido)
        self._cufe_map = {}   # iid → CUFE completo para el popup
        self._build()

    # ── Construcción UI ───────────────────────────────────────────────────────
    def _build(self, container=None):
        if container is None:
            win = tk.Toplevel(self.parent)
            self.win = win
            win.title("Subir al RNDC — Factura Electrónica (Proceso 86)")
            win.configure(bg=BG)
            win.resizable(True, True)
            win.wm_attributes("-toolwindow", False)
            try:
                win.iconbitmap(resource_path("icono.ico"))
            except Exception:
                pass
            root_frame = win
        else:
            self.win = container.winfo_toplevel()
            root_frame = container
        self.root_frame = root_frame  # guardar para uso en _enviar

        # Header
        hdr = tk.Frame(root_frame, bg=BG2, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="📤  Facturación Electrónica RNDC",
                 font=FONT_H1, bg=BG2, fg=TEXT).pack(padx=20)
        tk.Label(hdr,
                 text="WebService SOAP",
                 font=FONT_SMALL, bg=BG2, fg=TEXT2).pack(pady=(2, 0))
        tk.Frame(root_frame, bg=BORDER, height=1).pack(fill=tk.X)

        # Barra inferior anclada al fondo ANTES de body para que siempre sea visible
        bot = tk.Frame(root_frame, bg=BG2, pady=8)
        bot.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Frame(root_frame, bg=BORDER, height=1).pack(side=tk.BOTTOM, fill=tk.X)

        self._prog_var = tk.DoubleVar(value=0)
        self._prog = ttk.Progressbar(bot, variable=self._prog_var,
                                      maximum=100, length=300)
        self._prog.pack(side=tk.LEFT, padx=(20, 10))
        self._lbl_prog = tk.Label(bot, text="", font=FONT_SMALL, bg=BG2, fg=TEXT2)
        self._lbl_prog.pack(side=tk.LEFT, padx=(0, 16))
        self._btn_env = tk.Label(bot, text="📤  Enviar al RNDC",
                                  font=("Segoe UI", 9, "bold"),
                                  bg=ACCENT, fg="white", cursor="hand2", padx=16, pady=7)
        self._btn_env.bind("<Button-1>", lambda e: self._enviar())
        self._btn_env.bind("<Enter>",    lambda e: self._btn_env.configure(bg="#2d5cbf"))
        self._btn_env.bind("<Leave>",    lambda e: self._btn_env.configure(bg=ACCENT))
        self._btn_env.pack(side=tk.LEFT)

        body = tk.Frame(root_frame, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=14)

        # ── Credenciales + configuración ──────────────────────────────────────
        cred = tk.Frame(body, bg=BG2, padx=14, pady=10)
        cred.pack(fill=tk.X, pady=(0, 10))
        tk.Label(cred, text="📋  FACTURACIÓN ELECTRÓNICA — DIAN",
                 font=FONT_H2, bg=BG2, fg=TEXT).grid(
                     row=0, column=0, columnspan=6, sticky="w", pady=(0, 8))

        def _lbl(text, row, col):
            tk.Label(cred, text=text, font=FONT_BODY, bg=BG2, fg=TEXT2
                     ).grid(row=row, column=col, sticky="w", padx=(0, 6), pady=3)

        def _entry(var, row, col, w=18, show=""):
            e = tk.Entry(cred, textvariable=var, font=FONT_BODY, width=w,
                         bg=BG3, fg=TEXT, insertbackground=TEXT, relief="flat",
                         highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT, show=show)
            e.grid(row=row, column=col, sticky="w", padx=(0, 16), pady=3)
            return e

        self._ep_var = tk.StringVar(value="Producción (rndcws)")

        _lbl("Usuario:", 1, 0)
        perfil_creds = self.perfil_fn()
        self._user_var = tk.StringVar(value=perfil_creds.get("rndc_usuario", ""))
        tk.Entry(cred, textvariable=self._user_var, font=FONT_BODY, width=18,
                 bg=BG3, fg=TEXT2, relief="flat",
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=BORDER, readonlybackground=BG3,
                 disabledforeground=TEXT2, disabledbackground=BG3,
                 state="readonly"
                 ).grid(row=1, column=1, sticky="w", padx=(0, 16), pady=3)

        self._pass_var = tk.StringVar(value=perfil_creds.get("rndc_password", ""))

        _lbl("NIT empresa transporte:", 2, 0)
        perfil = self.perfil_fn()
        self._nit_var = tk.StringVar(value=perfil.get("nit_socio", ""))
        tk.Entry(cred, textvariable=self._nit_var, font=FONT_BODY, width=14,
                 bg=BG3, fg=TEXT2, relief="flat",
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=BORDER, readonlybackground=BG3,
                 disabledforeground=TEXT2, disabledbackground=BG3,
                 state="readonly"
                 ).grid(row=2, column=1, sticky="w", padx=(0, 16), pady=3)

        self._lbl_empresa = tk.Label(
            cred,
            text=f"{perfil.get('nombre_socio', '')}  ·  Perfil: {perfil.get('nombre', '')}",
            font=FONT_SMALL, bg=BG2, fg=ACCENT)
        self._lbl_empresa.grid(row=2, column=2, columnspan=4, sticky="w", padx=(4, 0))

        def _sync_nit(*_):
            p = self.perfil_fn()
            self._nit_var.set(p.get("nit_socio", ""))
            self._user_var.set(p.get("rndc_usuario", ""))
            self._pass_var.set(p.get("rndc_password", ""))
            self._lbl_empresa.configure(
                text=f"{p.get('nombre_socio', '')}  ·  Perfil: {p.get('nombre', '')}")

        # ── Cargar archivos ──────────────────────────────────────────────────
        file_row = tk.Frame(body, bg=BG)
        file_row.pack(fill=tk.X, pady=(0, 6))

        def _btn(parent, txt, cmd, bg, hover, side=tk.LEFT):
            b = tk.Label(parent, text=txt, font=FONT_BODY, bg=bg, fg="white",
                         cursor="hand2", padx=12, pady=5)
            b.bind("<Button-1>", lambda e: cmd())
            b.bind("<Enter>",    lambda e: b.configure(bg=hover))
            b.bind("<Leave>",    lambda e: b.configure(bg=bg))
            b.pack(side=side, padx=(0, 8))
            return b

        _btn(file_row, "📁  Cargar XML(s)", self._cargar_archivos, "#5b4fcf", "#3d35a0")
        _btn(file_row, "🗑  Limpiar",       self._limpiar,          "#555e7a", "#3a4060")

        self._lbl_arch = tk.Label(body, text="Sin archivos cargados.",
                                   font=FONT_SMALL, bg=BG, fg=TEXT2, anchor="w")
        self._lbl_arch.pack(anchor="w", pady=(0, 6))

        # ── Estilos modernos para las tablas ──────────────────────────────────
        _sty = ttk.Style()
        try:
            _sty.theme_use("clam")
        except Exception:
            pass
        _sty.configure("RNDC.Treeview",
                        background=BG2, foreground=TEXT, fieldbackground=BG2,
                        rowheight=26, borderwidth=0, relief="flat", font=FONT_BODY)
        _sty.configure("RNDC.Treeview.Heading",
                        background=BG3, foreground=TEXT2,
                        font=FONT_H2, relief="flat", borderwidth=0)
        _sty.map("RNDC.Treeview",
                 background=[("selected", "#263555")],
                 foreground=[("selected", "#ffffff")])
        _sty.map("RNDC.Treeview.Heading",
                 background=[("active", BORDER)])

        def _make_table(parent, cols, widths, height, expand=False):
            border_frame = tk.Frame(parent, bg=BORDER, bd=0)
            border_frame.pack(fill=tk.BOTH if expand else tk.X,
                              expand=expand, pady=(0, 4))
            inner = tk.Frame(border_frame, bg=BG2)
            inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

            tree = ttk.Treeview(inner, columns=cols, show="headings",
                                 height=height, style="RNDC.Treeview",
                                 selectmode="extended")
            for i, (col, w) in enumerate(zip(cols, widths)):
                tree.heading(col, text=col,
                             command=lambda c=col, t=tree: _sort_col(t, c))
                is_last = (i == len(cols) - 1)
                tree.column(col, width=w,
                            minwidth=260 if is_last else max(w, 55),
                            stretch=is_last,
                            anchor="w")

            vsb = ttk.Scrollbar(inner, orient="vertical",  command=tree.yview)
            hsb = ttk.Scrollbar(inner, orient="horizontal", command=tree.xview)
            tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
            tree.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            inner.grid_rowconfigure(0, weight=1)
            inner.grid_columnconfigure(0, weight=1)

            def _dbl_click(event, t=tree):
                region = t.identify_region(event.x, event.y)
                if region == "heading":
                    cid   = t.identify_column(event.x)
                    cname = t.column(cid, "id")
                    max_w = max(
                        (len(str(t.set(i, cname))) * 7 + 20
                         for i in t.get_children()),
                        default=80
                    )
                    t.column(cid, width=min(max_w, 700))
                elif region == "cell":
                    iid = t.identify_row(event.y)
                    if not iid:
                        return
                    vals = t.item(iid, "values")
                    col_ids = t["columns"]

                    popup = tk.Toplevel(self.win)
                    popup.title("Detalle de fila")
                    popup.configure(bg=BG)
                    popup.resizable(True, True)
                    try:
                        popup.iconbitmap(resource_path("icono.ico"))
                    except Exception:
                        pass

                    tk.Label(popup, text="Haz clic en cualquier campo y copia con Ctrl+A / Ctrl+C",
                             font=FONT_SMALL, bg=BG, fg=TEXT2
                             ).pack(anchor="w", padx=16, pady=(10, 4))

                    cufe_completo = getattr(self, "_cufe_map", {}).get(iid)

                    for col_id, val in zip(col_ids, vals):
                        col_upper = str(col_id).upper()
                        if cufe_completo and "CUFE" in col_upper:
                            val = cufe_completo

                        row_f = tk.Frame(popup, bg=BG)
                        row_f.pack(fill=tk.X, padx=16, pady=3)
                        tk.Label(row_f, text=str(col_id) + ":",
                                 font=FONT_H2, bg=BG, fg=TEXT2,
                                 width=22, anchor="w"
                                 ).pack(side=tk.LEFT)
                        var = tk.StringVar(value=str(val))
                        ent = tk.Entry(row_f, textvariable=var,
                                       font=FONT_BODY, bg=BG3, fg=TEXT,
                                       insertbackground=TEXT, relief="flat",
                                       highlightthickness=1,
                                       highlightbackground=BORDER,
                                       highlightcolor=ACCENT,
                                       readonlybackground=BG3,
                                       state="readonly")
                        ent.pack(side=tk.LEFT, fill=tk.X, expand=True)
                        ent.bind("<FocusIn>",
                                 lambda e, w=ent: (w.configure(state="normal"),
                                                   w.select_range(0, "end"),
                                                   w.configure(state="readonly")))

                    tk.Frame(popup, bg=BORDER, height=1).pack(fill=tk.X, padx=16, pady=(10,4))
                    tk.Label(popup, text="Ctrl+A = seleccionar todo  ·  Ctrl+C = copiar",
                             font=FONT_SMALL, bg=BG, fg=BORDER).pack(pady=(0,10))

                    popup.update_idletasks()
                    w_pop = max(520, popup.winfo_reqwidth() + 40)
                    h_pop = popup.winfo_reqheight() + 20
                    popup.geometry(f"{w_pop}x{h_pop}")
                    popup.grab_set()

            tree.bind("<Double-Button-1>", _dbl_click)

            def _copiar(event, t=tree):
                sel = t.selection()
                if not sel:
                    return
                lineas = []
                for iid in sel:
                    vals = t.item(iid, "values")
                    lineas.append("\t".join(str(v) for v in vals))
                texto = "\n".join(lineas)
                root_frame.winfo_toplevel().clipboard_clear()
                root_frame.winfo_toplevel().clipboard_append(texto)
                root_frame.winfo_toplevel().update()
            tree.bind("<Control-c>", _copiar)
            tree.bind("<Control-C>", _copiar)

            return tree

        def _sort_col(tree, col, _state={}):
            key = id(tree), col
            rev = _state.get(key, False)
            try:
                data = [(tree.set(k, col), k) for k in tree.get_children("")]
                try:
                    data.sort(key=lambda x: float(x[0].replace("$","").replace(",","")), reverse=rev)
                except Exception:
                    data.sort(reverse=rev)
                for i, (_, k) in enumerate(data):
                    tree.move(k, "", i)
                _state[key] = not rev
            except Exception:
                pass

        hdr_fac = tk.Frame(body, bg=BG)
        hdr_fac.pack(fill=tk.X, pady=(4, 2))
        tk.Label(hdr_fac, text="📄  Facturas detectadas",
                 font=FONT_H2, bg=BG, fg=TEXT2).pack(side=tk.LEFT)
        self._lbl_fac_count = tk.Label(hdr_fac, text="",
                                        font=FONT_SMALL, bg=BG, fg=TEXT2)
        self._lbl_fac_count.pack(side=tk.LEFT, padx=(6, 0))
        tk.Label(hdr_fac, text="· doble clic fila = detalle · doble clic col = ancho · clic = ordena",
                 font=FONT_SMALL, bg=BG, fg=BORDER).pack(side=tk.LEFT, padx=(10, 0))

        def _copy_tree(tree, cols):
            filas = ["\t".join(str(c) for c in cols)]
            for iid in tree.get_children():
                vals = tree.item(iid, "values")
                vals_list = list(vals)
                cufe_full = self._cufe_map.get(iid)
                if cufe_full:
                    for i, col in enumerate(cols):
                        if "CUFE" in str(col).upper():
                            vals_list[i] = cufe_full
                filas.append("\t".join(str(v) for v in vals_list))
            texto = "\n".join(filas)
            root_frame.winfo_toplevel().clipboard_clear()
            root_frame.winfo_toplevel().clipboard_append(texto)
            root_frame.winfo_toplevel().update()
            return len(filas) - 1

        def _mk_copy_btn(parent, tree_ref, cols_ref, label_ref):
            def _do_copy():
                n = _copy_tree(tree_ref[0], cols_ref[0])
                orig = btn.cget("text")
                btn.configure(text=f"✓ {n} fil.", bg=SUCCESS)
                root_frame.winfo_toplevel().after(1800, lambda: btn.configure(text=orig, bg="#334155"))
            btn = tk.Label(parent, text="📋 Copiar todo",
                           font=FONT_SMALL, bg="#334155", fg="white",
                           cursor="hand2", padx=8, pady=3)
            btn.bind("<Button-1>", lambda e: _do_copy())
            btn.bind("<Enter>",    lambda e: btn.configure(bg="#475569"))
            btn.bind("<Leave>",    lambda e: btn.configure(bg="#334155"))
            btn.pack(side=tk.RIGHT)
            return btn

        _fac_ref  = [None]
        _fac_cols = [("Archivo XML", "N° Factura", "Cliente", "CUFE", "Remesas", "Estado RNDC")]
        _mk_copy_btn(hdr_fac, _fac_ref, _fac_cols, None)

        cols_fac = ("Archivo XML", "N° Factura", "Cliente", "CUFE", "Remesas", "Estado RNDC")
        self._tree_fac = _make_table(body, cols_fac, [120, 75, 160, 145, 70, 560], height=4)
        _fac_ref[0] = self._tree_fac

        hdr_rem = tk.Frame(body, bg=BG)
        hdr_rem.pack(fill=tk.X, pady=(6, 2))
        tk.Label(hdr_rem, text="📦  Remesas / líneas de factura",
                 font=FONT_H2, bg=BG, fg=TEXT2).pack(side=tk.LEFT)
        self._lbl_rem_count = tk.Label(hdr_rem, text="",
                                        font=FONT_SMALL, bg=BG, fg=TEXT2)
        self._lbl_rem_count.pack(side=tk.LEFT, padx=(6, 0))

        _rem_ref  = [None]
        _rem_cols = [("N° Factura", "Consecutivo", "Radicado", "Valor ($)", "Cantidad Entregada", "Estado RNDC")]
        _mk_copy_btn(hdr_rem, _rem_ref, _rem_cols, None)

        cols_rem = ("N° Factura", "Consecutivo", "Radicado", "Valor ($)", "Cantidad Entregada", "Estado RNDC")
        self._tree_rem = _make_table(body, cols_rem, [70, 80, 90, 95, 110, 600],
                                      height=8, expand=True)
        _rem_ref[0] = self._tree_rem

        for t in (self._tree_fac, self._tree_rem):
            t.tag_configure("ok",   background="#0e2a18", foreground="#22c55e")
            t.tag_configure("err",  background="#2a0e0e", foreground="#ef4444")
            t.tag_configure("pend", background=BG2,       foreground=TEXT2)
            t.tag_configure("alt",  background="#13162a", foreground=TEXT2)

        root_frame.update_idletasks()
        if container is None:
            root_frame.winfo_toplevel().geometry("1000x720")
            root_frame.winfo_toplevel().minsize(820, 580)

    # ── Cargar XMLs ───────────────────────────────────────────────────────────
    def _cargar_archivos(self):
        rutas = filedialog.askopenfilenames(
            parent=self.win,
            title="Selecciona XML(s) de respuesta DIAN",
            filetypes=[("XML", "*.xml"), ("Todos", "*.*")]
        )
        if not rutas:
            return
        self._limpiar()
        for ruta in rutas:
            try:
                with open(ruta, "rb") as f:
                    contenido_bytes = f.read()
                self.archivos.append((_os.path.basename(ruta), contenido_bytes))
            except Exception as e:
                messagebox.showerror("Error leyendo archivo", f"{ruta}\n{e}")

        n = len(self.archivos)
        self._lbl_arch.configure(
            text=f"{n} archivo{'s' if n!=1 else ''} cargado{'s' if n!=1 else ''}",
            fg=SUCCESS if n > 0 else TEXT2)
        self._poblar_tablas()

    # ── Parsear y mostrar en tablas ───────────────────────────────────────────
    def _poblar_tablas(self):
        import xml.etree.ElementTree as ET
        for t in (self._tree_fac, self._tree_rem):
            for item in t.get_children():
                t.delete(item)

        NS = {
            "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
            "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
        }

        for nombre, contenido_bytes in self.archivos:
            try:
                root_el = ET.fromstring(contenido_bytes.decode("utf-8", errors="replace"))

                nf   = self._xml_text(root_el, [
                    ".//cbc:ParentDocumentID",
                    ".//cbc:ID",
                ], NS)
                cufe = self._xml_text(root_el, [".//cbc:UUID"], NS)

                cliente = self._xml_text(root_el, [
                    ".//cac:ReceiverParty//cbc:RegistrationName",
                ], NS)
                if not cliente:
                    invoice_xml_pre = self._extraer_invoice_xml(root_el, contenido_bytes)
                    if invoice_xml_pre:
                        try:
                            inv_pre = ET.fromstring(invoice_xml_pre)
                            cliente = self._xml_text(inv_pre, [
                                ".//cac:AccountingCustomerParty//cbc:RegistrationName",
                                ".//cac:AccountingCustomerParty//cbc:Name",
                            ], NS)
                        except Exception:
                            pass

                cufe_short = (cufe[:25] + "…") if len(cufe) > 25 else cufe
                fac_iid = f"fac::{nombre}"
                self._cufe_map[fac_iid] = cufe
                self._tree_fac.insert("", "end",
                    values=(nombre, nf, cliente, cufe_short, "0", "⏳ Pendiente de envío"),
                    tags=("pend",), iid=fac_iid)
                n_fac = len(self._tree_fac.get_children())
                self._lbl_fac_count.configure(text=f"({n_fac})")

                n_rem_fac = 0   # remesas de ESTA factura
                invoice_xml = self._extraer_invoice_xml(root_el, contenido_bytes)
                if invoice_xml:
                    try:
                        inv_root = ET.fromstring(invoice_xml)
                        lineas = inv_root.findall(
                            ".//{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}InvoiceLine")
                        for linea in lineas:
                            props = {}
                            for prop in linea.findall(".//cac:AdditionalItemProperty", NS):
                                pname  = self._xml_text(prop, ["cbc:Name"],  NS)
                                pvalue = self._xml_text(prop, ["cbc:Value"], NS)
                                if pname:
                                    props[pname] = pvalue

                            radicado = props.get("01", "")
                            consec   = props.get("02", "")
                            valor_raw = props.get("03") or self._xml_text(
                                linea, [".//cbc:LineExtensionAmount"], NS) or "0"
                            try:
                                valor = f"${float(valor_raw):,.2f}"
                            except Exception:
                                valor = valor_raw
                            peso_raw = props.get("PESO", "")
                            if not peso_raw:
                                vq = linea.find(
                                    ".//cac:AdditionalItemProperty/cbc:ValueQuantity[@unitCode='KGM']",
                                    NS)
                                if vq is not None and vq.text:
                                    peso_raw = vq.text.strip()
                            try:
                                peso = str(int(float(peso_raw))) if peso_raw else ""
                            except Exception:
                                peso = peso_raw

                            rem_idx  = len(self._tree_rem.get_children())
                            rem_iid  = f"rem::{nombre}::{rem_idx}"
                            tag_fila = "alt" if rem_idx % 2 == 0 else "pend"
                            self._tree_rem.insert("", "end", iid=rem_iid,
                                values=(nf, consec, radicado, valor, peso, "⏳ Pendiente de envío"),
                                tags=(tag_fila,))
                            n_rem = len(self._tree_rem.get_children())
                            self._lbl_rem_count.configure(text=f"({n_rem})")
                            n_rem_fac += 1
                    except Exception:
                        pass

                # Actualizar el conteo de remesas de la factura
                if self._tree_fac.exists(fac_iid):
                    vf = list(self._tree_fac.item(fac_iid, "values"))
                    vf[4] = str(n_rem_fac)
                    self._tree_fac.item(fac_iid, values=vf)

            except ET.ParseError as e:
                self._tree_fac.insert("", "end",
                    values=(nombre, "—", "—", "—", "—", f"⚠ XML inválido: {e}"),
                    tags=("err",))

        # ── Consultar el estado actual de cada remesa en el RNDC (antes de enviar) ──
        self._consultar_estados_remesas()

    # ── Estado de remesa (igual criterio que Consultar Remesas) ────────────────

    @staticmethod
    def _estado_remesa_txt(cod, manifiesto=""):
        if cod == "AC" and not str(manifiesto).strip():
            return "📋 Pendiente de asignar manifiesto"
        if cod == "CE":
            return "✓ Cumplida"
        if cod == "AC":
            return "⏳ Pendiente por cumplir"
        return cod or "—"

    def _consultar_estados_remesas(self):
        """Consulta en el RNDC el estado actual de cada remesa cargada y lo
        muestra en la columna 'Estado RNDC' (antes del envío de la factura)."""
        perfil = self.perfil_fn() if self.perfil_fn else None
        if not perfil:
            return
        filas = self._tree_rem.get_children()
        total = len(filas)
        for i, item_id in enumerate(filas, 1):
            vals = list(self._tree_rem.item(item_id, "values"))
            consec = str(vals[1]).strip()
            if not consec:
                continue
            self._lbl_rem_count.configure(text=f"(consultando {i}/{total}…)")
            try:
                self.win.update_idletasks()
            except Exception:
                pass
            try:
                ok, res = consultar_radicado_remesa(consec, perfil)
            except Exception:
                ok, res = False, {}
            if ok:
                estado = self._estado_remesa_txt(res.get("estado", ""), res.get("manifiesto", ""))
                # Completar radicado si vino vacío del XML
                if (not str(vals[2]).strip() or str(vals[2]).strip() in ("0", "—")) and res.get("radicado"):
                    vals[2] = res.get("radicado")
                vals[5] = estado
                self._tree_rem.item(item_id, values=vals)
        self._lbl_rem_count.configure(text=f"({total})")

    def _xml_text(self, root, paths, ns):
        for p in paths:
            el = root.find(p, ns)
            if el is not None and el.text and el.text.strip():
                return el.text.strip()
        return ""

    def _extraer_invoice_xml(self, root_el, contenido_bytes):
        import re as _re
        tag = root_el.tag.lower()
        if "attacheddocument" in tag:
            texto = contenido_bytes.decode("utf-8", errors="replace")
            match = _re.search(r'<!\[CDATA\[(.*?)\]\]>', texto, _re.DOTALL)
            if match:
                cdata = match.group(1).strip()
                return cdata
        elif "invoice" in tag:
            return contenido_bytes.decode("utf-8", errors="replace")
        return None

    # ── Limpiar ───────────────────────────────────────────────────────────────
    def _limpiar(self):
        self.archivos = []
        self._cufe_map = {}
        self._lbl_arch.configure(text="Sin archivos cargados.", fg=TEXT2)
        for t in (self._tree_fac, self._tree_rem):
            for item in t.get_children():
                t.delete(item)
        self._lbl_fac_count.configure(text="")
        self._lbl_rem_count.configure(text="")
        self._prog_var.set(0)
        self._lbl_prog.configure(text="")

    # ── Enviar al RNDC ────────────────────────────────────────────────────────
    def _enviar(self):
        if not self.archivos:
            messagebox.showwarning("Sin archivos", "Carga primero al menos un XML.")
            return
        usuario  = self._user_var.get().strip()
        password = self._pass_var.get().strip()
        nit      = self._nit_var.get().strip()
        endpoint = self.ENDPOINTS.get("Producción (rndcws)", "http://rndcws.mintransporte.gov.co:8080")

        if not all([usuario, password, nit]):
            messagebox.showwarning("Faltan datos",
                "Completa usuario, contraseña y NIT de la empresa.")
            return

        self._btn_env.configure(text="⏳  Enviando…", bg="#555e7a")
        self.win.update_idletasks()

        total = len(self.archivos)
        ok_count = err_count = 0

        for idx, (nombre, contenido_bytes) in enumerate(self.archivos):
            self._lbl_prog.configure(text=f"{idx+1}/{total}  {nombre}")
            self._prog_var.set((idx / total) * 100)
            self.win.update_idletasks()

            exito, mensaje = self._soap_call(endpoint, usuario, password, nit, contenido_bytes)
            icono = "✓" if exito else "✗"
            tag   = "ok" if exito else "err"

            fac_id = f"fac::{nombre}"
            if self._tree_fac.exists(fac_id):
                vals = self._tree_fac.item(fac_id, "values")
                # vals[4] = nº de remesas de la factura (se conserva)
                self._tree_fac.item(fac_id,
                    values=(vals[0], vals[1], vals[2], vals[3], vals[4], f"{icono} {mensaje}"),
                    tags=(tag,))

            if exito:
                estado_rem = "✓ Aceptada por el RNDC"
                tag_rem    = "ok"
            else:
                estado_rem = f"✗ {mensaje}"
                tag_rem    = "err"

            for item_id in self._tree_rem.get_children():
                if item_id.startswith(f"rem::{nombre}::"):
                    vals_rem = self._tree_rem.item(item_id, "values")
                    self._tree_rem.item(item_id,
                        values=(vals_rem[0], vals_rem[1], vals_rem[2],
                                vals_rem[3], vals_rem[4], estado_rem),
                        tags=(tag_rem,))

            if exito:
                ok_count += 1
            else:
                err_count += 1

        self._prog_var.set(100)
        self._btn_env.configure(text="📤  Enviar al RNDC", bg=ACCENT)

        if err_count == 0:
            msg_res  = (f"✓  {ok_count} factura{'s' if ok_count!=1 else ''} "
                        f"enviada{'s' if ok_count!=1 else ''} correctamente al RNDC.")
            color_res = SUCCESS
        elif ok_count == 0:
            msg_res  = (f"✗  {err_count} factura{'s' if err_count!=1 else ''} "
                        f"con error. Revisa la columna Estado RNDC.")
            color_res = DANGER
        else:
            msg_res  = (f"✓ {ok_count} enviadas  ✗ {err_count} con error. "
                        f"Revisa la columna Estado RNDC.")
            color_res = "#f59e0b"

        self._lbl_prog.configure(text=msg_res, fg=color_res)

    # ── Llamada SOAP ──────────────────────────────────────────────────────────
    def _soap_call(self, endpoint, usuario, password, nit_empresa, contenido_bytes):
        import base64, html, xml.etree.ElementTree as ET

        b64 = base64.b64encode(contenido_bytes).decode("ascii")

        rndc_xml = self.RNDC_XML_TMPL.format(
            usuario=html.escape(usuario),
            password=html.escape(password),
            proceso=self.PROCESO,
            nit_empresa=html.escape(nit_empresa),
            base64_xml=b64,
        )

        rndc_escaped = html.escape(rndc_xml)

        soap_body = self.SOAP_ENVELOPE_TMPL.format(
            rndc_xml_escaped=rndc_escaped,
        )

        url = endpoint + self.SOAP_PATH
        headers = {
            "Content-Type": "text/xml; charset=UTF-8",
            "SOAPAction":   self.SOAP_ACTION,
        }

        try:
            resp = _requests.post(
                url,
                data=soap_body.encode("utf-8"),
                headers=headers,
                timeout=45,
            )
            try:
                import os as _os2
                log_path = _os2.path.join(
                    _os2.path.dirname(_os2.path.abspath(__file__)), "..", "rndc_debug.log")
                with open(log_path, "a", encoding="utf-8", errors="replace") as _lf:
                    _lf.write(f"\n--- RESPUESTA HTTP {resp.status_code} ---\n")
                    _lf.write(resp.text[:4000])
                    _lf.write("\n")
            except Exception:
                pass
            return self._parsear_respuesta(resp.text)
        except _requests.exceptions.ConnectionError:
            return False, f"Sin conexión a {endpoint}"
        except _requests.exceptions.Timeout:
            return False, "Tiempo de espera agotado (45s)"
        except Exception as e:
            return False, str(e)[:180]

    # ── Parsear respuesta SOAP del RNDC ───────────────────────────────────────
    def _parsear_respuesta(self, resp_text):
        import xml.etree.ElementTree as ET, re as _re, html as _html

        inner_raw = None
        m = _re.search(r'<[^>]*:?return[^>]*>(.*?)</[^>]*:?return>',
                        resp_text, _re.DOTALL | _re.IGNORECASE)
        if m:
            inner_raw = m.group(1).strip()

        if not inner_raw:
            m2 = _re.search(r'(<root[^>]*>.*?</root>)', resp_text, _re.DOTALL | _re.IGNORECASE)
            if m2:
                inner_raw = m2.group(1).strip()

        if not inner_raw:
            return False, f"Respuesta no reconocida: {resp_text.strip()[:200]}"

        inner = _html.unescape(inner_raw)

        def _parse_xml(texto):
            try:
                return ET.fromstring(texto)
            except ET.ParseError:
                pass
            try:
                return ET.fromstring(texto.encode("iso-8859-1"))
            except Exception:
                pass
            sin_decl = _re.sub(r'<\?xml[^?]*\?>', '', texto, count=1).strip()
            try:
                return ET.fromstring(sin_decl)
            except Exception:
                return None

        root_el = _parse_xml(inner)

        if root_el is None:
            texto_plano = inner.strip()[:250]
            exito = any(p in texto_plano.upper() for p in
                        ("INGRESOID", "EXITOSO", "CORRECTO", "ACEPTADO"))
            return exito, texto_plano

        def _limpiar_msg(texto):
            import re as _re2
            texto = _re2.sub(
                r'Paso\s*\d+\s*[Ee]jecutando\s+solicitud\.?\s*ProcesoId:\s*\d+\s*',
                '', texto
            ).strip()
            m_err = _re2.search(r'(Error\s+[A-Z]{2,}\d+\s*:.*)', texto, _re2.DOTALL)
            if m_err:
                texto = m_err.group(1).strip()
            texto = _re2.sub(r'\s*;Linea:\d+\s*', '', texto).strip()
            texto = _re2.sub(r' {2,}', ' ', texto).strip()
            partes = _re2.split(r'(?=Error\s+[A-Z]{2,}\d+\s*:)', texto)
            partes = [p.strip() for p in partes if p.strip()]
            if len(partes) > 1:
                vistos = []
                for p in partes:
                    p_clean = _re2.sub(r'\s+', ' ', p).strip().rstrip('.')
                    if p_clean not in vistos:
                        vistos.append(p_clean)
                texto = '  |  '.join(vistos)
            return texto

        for tag_ok in ("ingresoid", "INGRESOID", "IngresoId"):
            ing = root_el.find(tag_ok)
            if ing is not None and ing.text and ing.text.strip():
                radicado = ing.text.strip()
                es_prueba = radicado.isdigit() and int(radicado) > 900_000_000
                sufijo = " · Ambiente de pruebas" if es_prueba else ""
                return True, f"Radicado RNDC: {radicado}{sufijo}"

        for tag_err in ("ErrorMSG", "errorMSG", "errormsg", "error", "Error",
                        "ERROR", "mensaje", "Mensaje", "message", "respuesta"):
            el = root_el.find(tag_err)
            if el is not None:
                hijo = el.find(tag_err)
                texto_err = (hijo.text if hijo is not None and hijo.text
                             else el.text) or ""
                texto_err = texto_err.strip()
                if texto_err:
                    return False, _limpiar_msg(texto_err)[:280]

        texto_root = (root_el.text or "").strip()
        if texto_root:
            return False, _limpiar_msg(texto_root)[:280]

        xml_str = ET.tostring(root_el, encoding="unicode")
        return False, _limpiar_msg(xml_str)[:280]
