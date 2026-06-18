import tkinter as tk
from tkinter import ttk, messagebox

from config.theme import (
    BG, BG2, BG3, ACCENT, ACCENT2, SUCCESS, WARNING, DANGER,
    TEXT, TEXT2, BORDER, FONT_H1, FONT_H2, FONT_BODY, FONT_SMALL,
)
from services.rndc_service import consultar_remesa_completa, anular_cumplido_remesa


class AnularCumplidoRemesaModule:
    """
    Panel embebido para anular el cumplido de una remesa en el RNDC (proceso 28).
    Flujo: escribir consecutivo → Consultar (muestra datos para confirmar que es
    la remesa correcta) → elegir Motivo de anulación → Guardar (con confirmación).

    Usa las MISMAS credenciales de corrección del perfil (rndc_usuario_corregir)
    y el endpoint rndcws, igual que el módulo de corregir remesa.
    """

    # Motivo de anulación del cumplido (código → nombre), según el RNDC.
    MOTIVOS = [
        "D — Error Digitación",
        "O — Otro",
    ]

    # Campos de la consulta a mostrar como contexto (solo lectura).
    CONTEXTO = [
        ("remempresa",      "Empresa"),
        ("rem_orig",        "Origen"),
        ("rem_desti",       "Destino"),
        ("rempropietario",  "Generador"),
        ("remdestinatario", "Destinatario"),
        ("descripcioncortaproducto", "Producto"),
        ("cantidadcargada", "Cantidad cargada"),
        ("estado",          "Estado"),
        ("nummanifiestocarga", "N° Manifiesto"),
    ]

    def __init__(self, perfil_fn=None):
        self.perfil_fn = perfil_fn
        self._consultada = False

    # ── Credenciales de corrección (igual que el módulo corregir) ─────────────

    def _perfil(self):
        p = dict(self.perfil_fn()) if self.perfil_fn else {}
        u  = p.get("rndc_usuario_corregir")
        pw = p.get("rndc_password_corregir")
        if u and pw:
            p["rndc_usuario"]  = u
            p["rndc_password"] = pw
        return p

    def _consec_efectivo(self):
        consec = self.var_consec.get().strip()
        perfil = self._perfil()
        if perfil.get("prefijo_remesa") and consec and not consec.startswith("0"):
            consec = "0" + consec
        return consec

    # ── Construcción ──────────────────────────────────────────────────────────

    def _build(self, container):
        self.win = container.winfo_toplevel()

        hdr = tk.Frame(container, bg=BG2, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="🗑  Anular Cumplido Remesa",
                 font=FONT_H1, bg=BG2, fg=TEXT).pack(padx=20)
        tk.Label(hdr, text="Consulta la remesa, elige el motivo y anula su cumplido en el RNDC.",
                 font=FONT_SMALL, bg=BG2, fg=TEXT2).pack(padx=20)

        body = tk.Frame(container, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        # ── Consultar ─────────────────────────────────────────────────────────
        top = tk.Frame(body, bg=BG2, padx=12, pady=10)
        top.pack(fill=tk.X, pady=(0, 10))
        tk.Label(top, text="Consecutivo remesa:", font=FONT_BODY, bg=BG2,
                 fg=TEXT).pack(side=tk.LEFT, padx=(0, 8))
        self.var_consec = tk.StringVar()
        tk.Entry(top, textvariable=self.var_consec, font=FONT_BODY, width=20,
                 bg=BG3, fg=TEXT, insertbackground=TEXT, relief="flat",
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side=tk.LEFT, padx=(0, 10))
        btn = tk.Label(top, text="🔍  Consultar remesa", font=FONT_BODY,
                       bg=ACCENT, fg="white", cursor="hand2", padx=12, pady=5)
        btn.pack(side=tk.LEFT)
        btn.bind("<Button-1>", lambda e: self._consultar())

        self._lbl_estado = tk.Label(body, text="", font=FONT_BODY, bg=BG,
                                    fg=TEXT2, anchor="w")
        self._lbl_estado.pack(anchor="w", pady=(0, 6))

        # ── Contexto (solo lectura) ───────────────────────────────────────────
        card = tk.Frame(body, bg=BG2)
        card.pack(fill=tk.X, pady=(0, 10))
        tk.Label(card, text="📋  Datos de la remesa",
                 font=FONT_H2, bg=BG2, fg=TEXT).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Frame(card, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=(0, 6))
        grid = tk.Frame(card, bg=BG2)
        grid.pack(fill=tk.X, padx=12, pady=(0, 12))
        self._ctx_labels = {}
        for i, (clave, etq) in enumerate(self.CONTEXTO):
            r = i // 2
            c = (i % 2) * 2
            tk.Label(grid, text=etq + ":", font=FONT_SMALL, bg=BG2, fg=TEXT2,
                     anchor="w").grid(row=r, column=c, sticky="w", padx=(4, 6), pady=2)
            v = tk.Label(grid, text="—", font=FONT_BODY, bg=BG2, fg=TEXT, anchor="w")
            v.grid(row=r, column=c+1, sticky="w", padx=(0, 18), pady=2)
            self._ctx_labels[clave] = v

        # ── Motivo de anulación ───────────────────────────────────────────────
        mot = tk.Frame(body, bg=BG2)
        mot.pack(fill=tk.X, pady=(0, 10))
        tk.Label(mot, text="🔁  Motivo de la anulación",
                 font=FONT_H2, bg=BG2, fg=TEXT).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Frame(mot, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=(0, 6))
        mr = tk.Frame(mot, bg=BG2)
        mr.pack(fill=tk.X, padx=12, pady=(0, 12))
        tk.Label(mr, text="Motivo anulación cumplido", font=FONT_SMALL, bg=BG2,
                 fg=TEXT2, anchor="w").pack(side=tk.LEFT, padx=(0, 8))
        self.var_motivo = tk.StringVar(value=self.MOTIVOS[0])
        ttk.Combobox(mr, textvariable=self.var_motivo, values=self.MOTIVOS,
                     state="readonly", font=FONT_BODY, width=30).pack(side=tk.LEFT)

        # ── Enviar ────────────────────────────────────────────────────────────
        pie = tk.Frame(body, bg=BG)
        pie.pack(fill=tk.X, pady=(4, 10))
        self._btn_enviar = tk.Label(pie, text="🗑  Guardar anulación cumplido",
                                    font=("Segoe UI", 9, "bold"), bg=BG3, fg=TEXT2,
                                    cursor="hand2", padx=14, pady=7)
        self._btn_enviar.pack(side=tk.RIGHT)
        self._btn_enviar.bind("<Button-1>", lambda e: self._enviar())

        btn_limpiar = tk.Label(pie, text="🗑  Limpiar", font=FONT_BODY,
                               bg="#555e7a", fg="white", cursor="hand2", padx=12, pady=7)
        btn_limpiar.pack(side=tk.RIGHT, padx=(0, 8))
        btn_limpiar.bind("<Button-1>", lambda e: self._limpiar())

    def _limpiar(self):
        self.var_consec.set("")
        self._consultada = False
        for lbl in self._ctx_labels.values():
            lbl.configure(text="—")
        self.var_motivo.set(self.MOTIVOS[0])
        self._btn_enviar.configure(bg=BG3, fg=TEXT2)
        self._lbl_estado.configure(text="", fg=TEXT2)

    # ── Consultar ─────────────────────────────────────────────────────────────

    def _consultar(self):
        consec = self._consec_efectivo()
        if not consec:
            messagebox.showwarning("Sin consecutivo", "Escribe el consecutivo de la remesa.")
            return
        if not self.perfil_fn:
            messagebox.showerror("Sin perfil", "No hay perfil activo.")
            return
        perfil = self._perfil()

        self._lbl_estado.configure(text=f"🔍 Consultando remesa {consec}…", fg=TEXT2)
        try:
            self.win.update_idletasks()
        except Exception:
            pass

        ok, res = consultar_remesa_completa(consec, perfil)
        if not ok:
            self._consultada = False
            self._btn_enviar.configure(bg=BG3, fg=TEXT2)
            self._lbl_estado.configure(text=f"✗ {res}", fg=DANGER)
            return

        for clave, lbl in self._ctx_labels.items():
            lbl.configure(text=res.get(clave, "") or "—")
        self._consultada = True
        self._btn_enviar.configure(bg=DANGER, fg="white")
        self._lbl_estado.configure(
            text=f"✓ Remesa {consec} cargada (radicado {res.get('ingresoid','?')}). "
                 f"Elige el motivo y anula el cumplido.", fg=SUCCESS)

    # ── Enviar ────────────────────────────────────────────────────────────────

    def _enviar(self):
        if not self._consultada:
            messagebox.showwarning("Consulta primero",
                "Primero consulta la remesa para confirmar que es la correcta.")
            return
        perfil = self._perfil()
        consec = self._consec_efectivo()
        cod_motivo = self.var_motivo.get().strip().split(" ")[0]   # "D — ..." → "D"

        resumen = (
            f"¿Anular el CUMPLIDO de la remesa {consec}?\n\n"
            f"Motivo: {self.var_motivo.get()}\n\n"
            "Esta operación anula el cumplido en el RNDC (datos reales)."
        )
        if not messagebox.askyesno("Confirmar anulación", resumen):
            return

        self._lbl_estado.configure(text=f"📤 Anulando cumplido de {consec}…", fg=TEXT2)
        try:
            self.win.update_idletasks()
        except Exception:
            pass

        ok, res = anular_cumplido_remesa(consec, cod_motivo, perfil)
        if ok:
            self._lbl_estado.configure(
                text=f"✓ Cumplido anulado. Radicado: {res.get('ingresoid','?')}", fg=SUCCESS)
            messagebox.showinfo("Cumplido anulado",
                f"Se anuló el cumplido de la remesa {consec}.\nRadicado: {res.get('ingresoid','?')}")
        else:
            self._lbl_estado.configure(text=f"✗ {res}", fg=DANGER)
            messagebox.showerror("Error al anular", str(res))
