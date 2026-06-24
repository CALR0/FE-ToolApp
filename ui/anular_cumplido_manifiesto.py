import tkinter as tk
from tkinter import ttk, messagebox

from config.theme import (
    BG, BG2, BG3, ACCENT, ACCENT2, SUCCESS, WARNING, DANGER,
    TEXT, TEXT2, BORDER, FONT_H1, FONT_H2, FONT_BODY, FONT_SMALL,
)
from services.rndc_service import anular_cumplido_manifiesto


class AnularCumplidoManifiestoModule:
    """
    Panel embebido para anular el cumplido de un manifiesto en el RNDC (proceso 29).
    Flujo: escribir el N° de manifiesto → elegir Motivo de anulación →
    (observaciones opcionales) → Guardar (con confirmación).

    Usa las MISMAS credenciales de corrección del perfil (rndc_usuario_corregir)
    y el endpoint rndcws, igual que anular cumplido remesa / cumplir remesa.
    """

    # Motivo de anulación del cumplido (código → nombre), según el RNDC.
    MOTIVOS = [
        "D — Error Digitación",
        "O — Otro",
    ]

    def __init__(self, perfil_fn=None):
        self.perfil_fn = perfil_fn

    # ── Credenciales de corrección (igual que el módulo corregir/anular remesa) ─

    def _perfil(self):
        p = dict(self.perfil_fn()) if self.perfil_fn else {}
        u  = p.get("rndc_usuario_corregir")
        pw = p.get("rndc_password_corregir")
        if u and pw:
            p["rndc_usuario"]  = u
            p["rndc_password"] = pw
        return p

    # ── Construcción ──────────────────────────────────────────────────────────

    def _build(self, container):
        self.win = container.winfo_toplevel()

        hdr = tk.Frame(container, bg=BG2, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="🗑  Anular Cumplido Manifiesto",
                 font=FONT_H1, bg=BG2, fg=TEXT).pack(padx=20)
        tk.Label(hdr, text="Escribe el N° de manifiesto, elige el motivo y anula su cumplido en el RNDC.",
                 font=FONT_SMALL, bg=BG2, fg=TEXT2).pack(padx=20)

        body = tk.Frame(container, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        # ── N° de manifiesto ──────────────────────────────────────────────────
        top = tk.Frame(body, bg=BG2, padx=12, pady=10)
        top.pack(fill=tk.X, pady=(0, 10))
        tk.Label(top, text="N° Manifiesto de carga:", font=FONT_BODY, bg=BG2,
                 fg=TEXT).pack(side=tk.LEFT, padx=(0, 8))
        self.var_manifiesto = tk.StringVar()
        tk.Entry(top, textvariable=self.var_manifiesto, font=FONT_BODY, width=22,
                 bg=BG3, fg=TEXT, insertbackground=TEXT, relief="flat",
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side=tk.LEFT, padx=(0, 10))

        self._lbl_estado = tk.Label(body, text="", font=FONT_BODY, bg=BG,
                                    fg=TEXT2, anchor="w")
        self._lbl_estado.pack(anchor="w", pady=(0, 6))

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

        # ── Observaciones (opcional) ──────────────────────────────────────────
        obs = tk.Frame(body, bg=BG2)
        obs.pack(fill=tk.X, pady=(0, 10))
        tk.Label(obs, text="📝  Observaciones (opcional)",
                 font=FONT_H2, bg=BG2, fg=TEXT).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Frame(obs, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=(0, 6))
        orow = tk.Frame(obs, bg=BG2)
        orow.pack(fill=tk.X, padx=12, pady=(0, 12))
        self.var_obs = tk.StringVar()
        tk.Entry(orow, textvariable=self.var_obs, font=FONT_BODY,
                 bg=BG3, fg=TEXT, insertbackground=TEXT, relief="flat",
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Enviar ────────────────────────────────────────────────────────────
        pie = tk.Frame(body, bg=BG)
        pie.pack(fill=tk.X, pady=(4, 10))
        self._btn_enviar = tk.Label(pie, text="🗑  Guardar anulación cumplido",
                                    font=("Segoe UI", 9, "bold"), bg=DANGER, fg="white",
                                    cursor="hand2", padx=14, pady=7)
        self._btn_enviar.pack(side=tk.RIGHT)
        self._btn_enviar.bind("<Button-1>", lambda e: self._enviar())

        btn_limpiar = tk.Label(pie, text="🗑  Limpiar", font=FONT_BODY,
                               bg="#555e7a", fg="white", cursor="hand2", padx=12, pady=7)
        btn_limpiar.pack(side=tk.RIGHT, padx=(0, 8))
        btn_limpiar.bind("<Button-1>", lambda e: self._limpiar())

    def _limpiar(self):
        self.var_manifiesto.set("")
        self.var_motivo.set(self.MOTIVOS[0])
        self.var_obs.set("")
        self._lbl_estado.configure(text="", fg=TEXT2)

    # ── Enviar ────────────────────────────────────────────────────────────────

    def _enviar(self):
        manifiesto = self.var_manifiesto.get().strip()
        if not manifiesto:
            messagebox.showwarning("Sin manifiesto", "Escribe el N° del manifiesto de carga.")
            return
        if not self.perfil_fn:
            messagebox.showerror("Sin perfil", "No hay perfil activo.")
            return
        perfil = self._perfil()
        cod_motivo = self.var_motivo.get().strip().split(" ")[0]   # "D — ..." → "D"
        obs = self.var_obs.get().strip()

        resumen = (
            f"¿Anular el CUMPLIDO del manifiesto {manifiesto}?\n\n"
            f"Motivo: {self.var_motivo.get()}\n"
            + (f"Observaciones: {obs}\n" if obs else "")
            + "\nEsta operación anula el cumplido en el RNDC (datos reales)."
        )
        if not messagebox.askyesno("Confirmar anulación", resumen):
            return

        self._lbl_estado.configure(text=f"📤 Anulando cumplido del manifiesto {manifiesto}…", fg=TEXT2)
        try:
            self.win.update_idletasks()
        except Exception:
            pass

        ok, res = anular_cumplido_manifiesto(manifiesto, cod_motivo, perfil, obs)
        if ok:
            self._lbl_estado.configure(
                text=f"✓ Cumplido anulado. Radicado: {res.get('ingresoid','?')}", fg=SUCCESS)
            messagebox.showinfo("Cumplido anulado",
                f"Se anuló el cumplido del manifiesto {manifiesto}.\nRadicado: {res.get('ingresoid','?')}")
        else:
            self._lbl_estado.configure(text=f"✗ {res}", fg=DANGER)
            messagebox.showerror("Error al anular", str(res))
