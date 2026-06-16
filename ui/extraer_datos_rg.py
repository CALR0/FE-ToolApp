import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import re
from pathlib import Path

from config.theme import (
    BG, BG2, BG3, ACCENT, ACCENT2, SUCCESS, WARNING, DANGER,
    TEXT, TEXT2, BORDER, FONT_H1, FONT_H2, FONT_BODY, FONT_SMALL,
)
from core.xml_generator import _parse_valor


class ExtraerDatosRGModule:
    """
    Panel embebido que carga uno o varios PDFs de facturas electrónicas,
    extrae los datos relevantes y exporta a Excel.
    """

    def __init__(self):
        self.archivos = []   # lista de Path

    def _build(self, container):
        self.win = container.winfo_toplevel()

        hdr = tk.Frame(container, bg=BG2, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="📄  Extraer Datos RG",
                 font=FONT_H1, bg=BG2, fg=TEXT).pack(padx=20)
        tk.Label(hdr, text="Extrae datos de facturas electrónicas en PDF y exporta a Excel.",
                 font=FONT_SMALL, bg=BG2, fg=TEXT2).pack(padx=20)

        body = tk.Frame(container, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)
        top = tk.Frame(body, bg=BG2, pady=10, padx=12)
        top.pack(fill=tk.X, pady=(0, 8))

        btn_row = tk.Frame(top, bg=BG2)
        btn_row.pack(fill=tk.X)

        self._btn_cargar = tk.Label(btn_row, text="📂  Cargar PDF(s)",
                                    font=FONT_BODY, bg=ACCENT, fg="white",
                                    cursor="hand2", padx=12, pady=5)
        self._btn_cargar.pack(side=tk.LEFT, padx=(0, 8))
        self._btn_cargar.bind("<Button-1>", lambda e: self._cargar_pdfs())

        self._btn_limpiar = tk.Label(btn_row, text="🗑  Limpiar",
                                     font=FONT_BODY, bg="#555e7a", fg="white",
                                     cursor="hand2", padx=12, pady=5)
        self._btn_limpiar.pack(side=tk.LEFT)
        self._btn_limpiar.bind("<Button-1>", lambda e: self._limpiar())

        self._lbl_arch = tk.Label(top, text="Sin archivos cargados.",
                                  font=FONT_BODY, bg=BG2, fg=TEXT2, anchor="w")
        self._lbl_arch.pack(anchor="w", pady=(6, 0))

        tbl_frame = tk.Frame(body, bg=BG2)
        tbl_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        s = ttk.Style()
        s.configure("RG.Treeview",
                    background=BG2, fieldbackground=BG2, foreground=TEXT,
                    rowheight=24, font=FONT_BODY, borderwidth=0)
        s.configure("RG.Treeview.Heading",
                    background=BG3, foreground=TEXT2, font=FONT_SMALL, relief="flat")
        s.map("RG.Treeview",
              background=[("selected", ACCENT)],
              foreground=[("selected", "#ffffff")])

        cols = ("Archivo", "N° Factura", "Fecha", "Líneas", "Total Factura", "Estado")
        self._tree = ttk.Treeview(tbl_frame, columns=cols, show="headings",
                                  style="RG.Treeview", selectmode="browse")
        vsb = ttk.Scrollbar(tbl_frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(tbl_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._tree.pack(fill=tk.BOTH, expand=True)

        for col, w in zip(cols, (220, 90, 110, 60, 120, 160)):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="w" if col in ("Archivo","Estado") else "center",
                              stretch=(col in ("Archivo","Estado")))

        self._tree.tag_configure("ok",   foreground="#4ade80", background=BG2)
        self._tree.tag_configure("err",  foreground="#f87171", background=BG2)
        self._tree.tag_configure("proc", foreground=ACCENT,    background=BG2)
        self._tree.tag_configure("alt",  background=BG3)

        opt_row = tk.Frame(body, bg=BG, pady=4)
        opt_row.pack(fill=tk.X)
        self._var_usar_ref = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(opt_row, text="Usar campo Referencia del PDF como consecutivo_remesa",
                             variable=self._var_usar_ref, font=FONT_BODY,
                             bg=BG, fg=TEXT2, selectcolor=BG3,
                             activebackground=BG, activeforeground=TEXT,
                             cursor="hand2")
        chk.pack(side=tk.LEFT)

        act_row = tk.Frame(body, bg=BG, pady=6)
        act_row.pack(fill=tk.X)

        self._btn_extraer = tk.Label(act_row, text="⚙️  Extraer datos",
                                     font=FONT_BODY, bg="#7c3aed", fg="white",
                                     cursor="hand2", padx=14, pady=6)
        self._btn_extraer.pack(side=tk.LEFT, padx=(0, 10))
        self._btn_extraer.bind("<Button-1>", lambda e: self._extraer())

        self._btn_exportar = tk.Label(act_row, text="💾  Exportar Excel",
                                      font=FONT_BODY, bg=BG3, fg=TEXT2,
                                      cursor="hand2", padx=14, pady=6)
        self._btn_exportar.pack(side=tk.LEFT)
        self._btn_exportar.bind("<Button-1>", lambda e: self._exportar())

        self._lbl_prog = tk.Label(act_row, text="", font=FONT_SMALL,
                                  bg=BG, fg=TEXT2, anchor="w")
        self._lbl_prog.pack(side=tk.LEFT, padx=(14, 0))

        self._prog_var = tk.DoubleVar()
        pb_frame = tk.Frame(body, bg=BG)
        pb_frame.pack(fill=tk.X)
        self._pb = ttk.Progressbar(pb_frame, orient="horizontal",
                                   mode="determinate", variable=self._prog_var)
        self._pb.pack(fill=tk.X)

        self._filas_resultado = []

    def _cargar_pdfs(self):
        rutas = filedialog.askopenfilenames(
            title="Seleccionar PDF(s) de facturas",
            filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")])
        if not rutas:
            return
        for r in rutas:
            p = Path(r)
            if not any(str(a) == str(p) for a in self.archivos):
                self.archivos.append(p)
        self._refrescar_lista()

    def _refrescar_lista(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        for i, ruta in enumerate(self.archivos):
            tag = "alt" if i % 2 == 0 else "norm"
            self._tree.insert("", "end", iid=str(i),
                              values=(ruta.name, "", "", "", "", "⏳ Pendiente"),
                              tags=(tag,))
        n = len(self.archivos)
        self._lbl_arch.configure(
            text=f"{n} archivo{'s' if n != 1 else ''} cargado{'s' if n != 1 else ''}." if n else "Sin archivos cargados.",
            fg=TEXT if n else TEXT2)

    def _limpiar(self):
        self.archivos = []
        self._filas_resultado = []
        for item in self._tree.get_children():
            self._tree.delete(item)
        self._lbl_arch.configure(text="Sin archivos cargados.", fg=TEXT2)
        self._lbl_prog.configure(text="")
        self._prog_var.set(0)
        self._btn_exportar.configure(bg=BG3, fg=TEXT2)

    @staticmethod
    def _extraer_pdf(ruta):
        try:
            import pdfplumber
        except ImportError:
            raise ImportError("pdfplumber no instalado. Ejecuta: pip install pdfplumber")

        with pdfplumber.open(str(ruta)) as pdf:
            texto = "\n".join(p.extract_text() or "" for p in pdf.pages)

        m = re.search(r"No\.\s*(\d+)[-](\d+)", texto)
        numero_factura = (m.group(1) + m.group(2)) if m else ""

        m = re.search(
            r"FECHA\s*Y\s*HORA\s*DE\s*GENERACI[OÓ]N[:\s]*(\d{1,2})[./](\d{1,2})[./](\d{4})",
            texto, re.IGNORECASE)
        fecha_generacion = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""

        m = re.search(r"CUFE[:\s]*([a-f0-9]{80,})", texto, re.IGNORECASE)
        cufe = m.group(1).strip() if m else ""

        m = re.search(r"TOTAL\s*A\s*PAGAR\s+([\d.,]+)", texto, re.IGNORECASE)
        total_raw = m.group(1).strip() if m else "0"
        try:
            total_factura = _parse_valor(total_raw)
        except Exception:
            total_factura = 0.0

        m_inicio = re.search(
            r"REFERENCIA\s+DESCRIPCION\s+CANTIDAD\s+UND\s+VR\.\s*UNITARIO\s+VR\.\s*TOTAL",
            texto, re.IGNORECASE)
        m_fin = re.search(r"\bObservaciones\b|\bSUBTOTAL\b", texto, re.IGNORECASE)

        lineas = []
        if m_inicio and m_fin and m_fin.start() > m_inicio.end():
            bloque = texto[m_inicio.end():m_fin.start()].strip()
            for linea in bloque.split("\n"):
                linea = linea.strip()
                if not linea:
                    continue
                m_lin = re.match(
                    r"(\S+)\s+(.+?)\s+(\d+)\s+\S+\s+([\d.,]+)\s+([\d.,]+)\s*$",
                    linea)
                if not m_lin:
                    m_lin = re.match(
                        r"(\S+)\s+(.+?)\s+(\d+)\s+([\d.,]+)\s+([\d.,]+)\s*$",
                        linea)
                    if not m_lin:
                        continue
                    ref, desc, cant_s, vru_s, vrt_s = m_lin.groups()
                else:
                    ref, desc, cant_s, vru_s, vrt_s = m_lin.group(1,2,3,4,5)

                try:
                    cantidad    = int(cant_s)
                    vr_unitario = _parse_valor(vru_s)
                except Exception:
                    continue

                lineas.append({
                    "referencia":  ref.strip(),
                    "descripcion": desc.strip(),
                    "cantidad":    cantidad,
                    "vr_unitario": vr_unitario,
                })
        return {
            "numero_factura":   numero_factura,
            "fecha_generacion": fecha_generacion,
            "cufe":             cufe,
            "total_factura":    total_factura,
            "lineas":           lineas,
        }

    @staticmethod
    def _expandir_lineas(datos, usar_ref_como_consec=False):
        filas = []
        for lin in datos["lineas"]:
            cant         = lin["cantidad"]
            vr_unit_orig = lin["vr_unitario"]
            vr_unit_ind  = round(vr_unit_orig / cant, 2) if cant > 1 else vr_unit_orig
            consec       = lin["referencia"] if usar_ref_como_consec else ""
            for _ in range(cant):
                filas.append({
                    "numero_factura":      datos["numero_factura"],
                    "fecha_generacion":    datos["fecha_generacion"],
                    "cufe":                datos["cufe"],
                    "descripcion":         lin["descripcion"],
                    "consecutivo_remesa":  consec,
                    "radicado":            "",
                    "valor_unitario":      vr_unit_ind,
                    "valor_total_factura": datos["total_factura"],
                    "cantidad_remesas_rg": cant,
                })
        return filas

    def _extraer(self):
        if not self.archivos:
            messagebox.showwarning("Sin archivos", "Carga primero al menos un PDF.")
            return

        self._filas_resultado = []
        total = len(self.archivos)
        self._prog_var.set(0)
        self._pb["maximum"] = total

        for idx, ruta in enumerate(self.archivos):
            self._lbl_prog.configure(text=f"Procesando {idx+1}/{total}: {ruta.name}", fg=TEXT2)
            if self._tree.exists(str(idx)):
                vals = self._tree.item(str(idx), "values")
                self._tree.item(str(idx),
                    values=(vals[0], "", "", "", "", "⏳ Procesando…"),
                    tags=("proc",))
            self.win.update_idletasks()

            try:
                datos = self._extraer_pdf(ruta)
                filas = self._expandir_lineas(datos, usar_ref_como_consec=self._var_usar_ref.get())
                self._filas_resultado.extend(filas)

                nf      = datos["numero_factura"]
                fecha   = datos["fecha_generacion"]
                nlin    = len(datos["lineas"])
                total_f = f"$ {datos['total_factura']:,.0f}".replace(",",".")
                if self._tree.exists(str(idx)):
                    self._tree.item(str(idx),
                        values=(ruta.name, nf, fecha, nlin, total_f, "✓ Extraído"),
                        tags=("ok",))
            except Exception as ex:
                if self._tree.exists(str(idx)):
                    self._tree.item(str(idx),
                        values=(ruta.name, "", "", "", "", f"✗ {str(ex)[:80]}"),
                        tags=("err",))

            self._prog_var.set(idx + 1)
            self.win.update_idletasks()

        self._lbl_prog.configure(
            text=f"✓ {len(self._filas_resultado)} fila(s) extraídas de {total} PDF(s).",
            fg=SUCCESS)
        if self._filas_resultado:
            self._btn_exportar.configure(bg=ACCENT2, fg="white")

    def _exportar(self):
        if not self._filas_resultado:
            messagebox.showwarning("Sin datos", "Primero extrae los datos de los PDFs.")
            return
        ruta_out = filedialog.asksaveasfilename(
            title="Guardar Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")],
            initialfile="datos_rg.xlsx")
        if not ruta_out:
            return
        try:
            import pandas as pd
            df = pd.DataFrame(self._filas_resultado, columns=[
                "numero_factura", "fecha_generacion", "cufe",
                "descripcion", "consecutivo_remesa", "radicado",
                "valor_unitario", "valor_total_factura", "cantidad_remesas_rg",
            ])
            if ruta_out.endswith(".csv"):
                df.to_csv(ruta_out, index=False, encoding="utf-8-sig")
            else:
                df.to_excel(ruta_out, index=False)
            self._lbl_prog.configure(text=f"✓ Exportado: {ruta_out}", fg=SUCCESS)
            messagebox.showinfo("Exportado", f"Archivo guardado:\n{ruta_out}")
        except Exception as ex:
            messagebox.showerror("Error al exportar", str(ex))
