import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta

from config.theme import (
    BG, BG2, BG3, ACCENT, ACCENT2, SUCCESS, WARNING, DANGER,
    TEXT, TEXT2, BORDER, FONT_H1, FONT_H2, FONT_BODY, FONT_SMALL,
)
from services.rndc_service import consultar_remesa_completa, cumplir_remesa


class CumplirRemesaModule:
    """
    Panel embebido para cumplir una remesa en el RNDC (proceso 5).

    Es casi totalmente automático: se consulta la remesa, el usuario solo elige
    el "Tipo de Cumplido" (Normal o Suspensión) y todos los campos se calculan
    a partir de las citas pactadas de la consulta:

      - CANTIDADENTREGADA = CANTIDADCARGADA (normal) o 0 (suspensión).
      - Tiempos logísticos: por cada etapa (cargue / descargue) se usa la FECHA
        de la cita pactada y la HORA = cita + 1h (llegada), +2h (entrada),
        +3h (salida) → ~2 horas de operación.
      - Normal: llena cargue y descargue. Suspensión: solo cargue, motivo = "O".
    """

    TIPOS = [
        "C — Cumplido Normal",
        "S — Suspensión",
    ]

    def __init__(self, perfil_fn=None):
        self.perfil_fn = perfil_fn
        self._consulta = {}
        self._consultada = False

    # ── Credenciales de corrección (igual que corregir/anular) ────────────────

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

    # ── Helpers de hora ────────────────────────────────────────────────────────

    @staticmethod
    def _fecha_hora_mas(fecha_ddmmaaaa, hhmm, n):
        """
        Suma n horas a (fecha, hora). Devuelve (fecha 'DD/MM/AAAA', 'HH:MM'),
        avanzando el día si la hora pasa de medianoche.
        Ej: 31/12/2024 23:30 +3 → ('01/01/2025', '02:30').
        """
        try:
            dt = datetime.strptime(f"{fecha_ddmmaaaa.strip()} {hhmm.strip()}",
                                   "%d/%m/%Y %H:%M") + timedelta(hours=n)
            return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M")
        except Exception:
            return fecha_ddmmaaaa, ""

    # ── Construcción ──────────────────────────────────────────────────────────

    def _build(self, container):
        self.win = container.winfo_toplevel()

        hdr = tk.Frame(container, bg=BG2, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="✅  Cumplir Remesa",
                 font=FONT_H1, bg=BG2, fg=TEXT).pack(padx=20)
        tk.Label(hdr, text="Consulta la remesa, elige el tipo de cumplido y los tiempos se calculan solos.",
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

        # ── Tipo de cumplido ──────────────────────────────────────────────────
        sel = tk.Frame(body, bg=BG2, padx=12, pady=10)
        sel.pack(fill=tk.X, pady=(0, 10))
        tk.Label(sel, text="Tipo de Cumplido:", font=FONT_BODY, bg=BG2,
                 fg=TEXT).pack(side=tk.LEFT, padx=(0, 8))
        self.var_tipo = tk.StringVar(value=self.TIPOS[0])
        cmb = ttk.Combobox(sel, textvariable=self.var_tipo, values=self.TIPOS,
                           state="readonly", font=FONT_BODY, width=24)
        cmb.pack(side=tk.LEFT)
        cmb.bind("<<ComboboxSelected>>", lambda e: self._recalcular())

        # ── Vista previa (solo lectura) ───────────────────────────────────────
        card = tk.Frame(body, bg=BG2)
        card.pack(fill=tk.X, pady=(0, 10))
        tk.Label(card, text="📋  Cumplido a registrar (automático)",
                 font=FONT_H2, bg=BG2, fg=TEXT).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Frame(card, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=(0, 6))
        self._prev = tk.Frame(card, bg=BG2)
        self._prev.pack(fill=tk.X, padx=12, pady=(0, 12))
        self._prev_labels = {}

        # ── Enviar ────────────────────────────────────────────────────────────
        pie = tk.Frame(body, bg=BG)
        pie.pack(fill=tk.X, pady=(4, 10))
        self._btn_enviar = tk.Label(pie, text="✅  Guardar cumplido",
                                    font=("Segoe UI", 9, "bold"), bg=BG3, fg=TEXT2,
                                    cursor="hand2", padx=14, pady=7)
        self._btn_enviar.pack(side=tk.RIGHT)
        self._btn_enviar.bind("<Button-1>", lambda e: self._enviar())

    # ── Cálculo de variables ───────────────────────────────────────────────────

    def _tipo_codigo(self):
        return self.var_tipo.get().strip().split(" ")[0]   # "C — ..." → "C"

    def _construir_variables(self):
        """Construye el dict de variables del proceso 5 a partir de la consulta
        y el tipo de cumplido. Devuelve (variables, errores)."""
        c = self._consulta
        tipo = self._tipo_codigo()
        consec = self._consec_efectivo()
        perfil = self._perfil()

        cantidad = c.get("cantidadcargada", "") or c.get("cantidadinformacioncarga", "")
        f_carg = c.get("fechacitapactadacargue", "")
        h_carg = c.get("horacitapactadacargue", "")
        f_desc = c.get("fechacitapactadadescargue", "")
        h_desc = c.get("horacitapactadadescargueremesa", "")

        errores = []
        if not f_carg or not h_carg:
            errores.append("La remesa no tiene fecha/hora de cita de CARGUE.")

        # Cargue: llegada (+1h), entrada (+2h), salida (+3h), con avance de día
        cll_f, cll_h = self._fecha_hora_mas(f_carg, h_carg, 1)
        cen_f, cen_h = self._fecha_hora_mas(f_carg, h_carg, 2)
        csa_f, csa_h = self._fecha_hora_mas(f_carg, h_carg, 3)

        variables = {
            "NUMNITEMPRESATRANSPORTE":  perfil.get("nit_socio", ""),
            "CONSECUTIVOREMESA":        consec,
            "TIPOCUMPLIDOREMESA":       tipo,
            "CANTIDADINFORMACIONCARGA": cantidad,
            "CANTIDADENTREGADA":        cantidad if tipo == "C" else "0",
            # Tiempos de cargue (siempre)
            "FECHALLEGADACARGUE":       cll_f,
            "HORALLEGADACARGUEREMESA":  cll_h,
            "FECHAENTRADACARGUE":       cen_f,
            "HORAENTRADACARGUEREMESA":  cen_h,
            "FECHASALIDACARGUE":        csa_f,
            "HORASALIDACARGUEREMESA":   csa_h,
        }

        if tipo == "C":
            # Cumplido normal → también descargue
            if not f_desc or not h_desc:
                errores.append("La remesa no tiene fecha/hora de cita de DESCARGUE.")
            dll_f, dll_h = self._fecha_hora_mas(f_desc, h_desc, 1)
            den_f, den_h = self._fecha_hora_mas(f_desc, h_desc, 2)
            dsa_f, dsa_h = self._fecha_hora_mas(f_desc, h_desc, 3)
            variables.update({
                "FECHALLEGADADESCARGUE":        dll_f,
                "HORALLEGADADESCARGUECUMPLIDO": dll_h,
                "FECHAENTRADADESCARGUE":        den_f,
                "HORAENTRADADESCARGUECUMPLIDO": den_h,
                "FECHASALIDADESCARGUE":         dsa_f,
                "HORASALIDADESCARGUECUMPLIDO":  dsa_h,
            })
        else:
            # Suspensión → motivo "Otro", sin descargue
            variables["MOTIVOSUSPENSIONREMESA"] = "O"

        return variables, errores

    def _recalcular(self):
        """Refresca la vista previa con las variables que se enviarían."""
        for w in self._prev.winfo_children():
            w.destroy()
        self._prev_labels = {}
        if not self._consultada:
            return
        variables, errores = self._construir_variables()
        # No mostrar el identificador/credenciales, solo lo relevante
        ocultar = {"NUMNITEMPRESATRANSPORTE"}
        items = [(k, v) for k, v in variables.items() if k not in ocultar]
        for i, (k, v) in enumerate(items):
            r = i // 2
            cc = (i % 2) * 2
            tk.Label(self._prev, text=k + ":", font=FONT_SMALL, bg=BG2, fg=TEXT2,
                     anchor="w").grid(row=r, column=cc, sticky="w", padx=(4, 6), pady=2)
            tk.Label(self._prev, text=v or "—", font=FONT_BODY, bg=BG2, fg=TEXT,
                     anchor="w").grid(row=r, column=cc+1, sticky="w", padx=(0, 18), pady=2)
        if errores:
            tk.Label(self._prev, text="⚠ " + "  ".join(errores), font=FONT_SMALL,
                     bg=BG2, fg=DANGER, anchor="w").grid(
                     row=(len(items)+1)//2 + 1, column=0, columnspan=4, sticky="w", pady=(6, 0))

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
            self._recalcular()
            return

        self._consulta = res
        self._consultada = True
        self._btn_enviar.configure(bg=SUCCESS, fg="white")
        self._lbl_estado.configure(
            text=f"✓ Remesa {consec} cargada (cita cargue {res.get('fechacitapactadacargue','?')} "
                 f"{res.get('horacitapactadacargue','')}). Revisa y guarda el cumplido.", fg=SUCCESS)
        self._recalcular()

    # ── Enviar ────────────────────────────────────────────────────────────────

    def _enviar(self):
        if not self._consultada:
            messagebox.showwarning("Consulta primero",
                "Primero consulta la remesa para calcular el cumplido.")
            return
        variables, errores = self._construir_variables()
        if errores:
            messagebox.showwarning("Datos incompletos", "\n".join(errores))
            return
        perfil = self._perfil()
        consec = self._consec_efectivo()

        resumen = (
            f"¿Registrar el cumplido de la remesa {consec}?\n\n"
            f"Tipo: {self.var_tipo.get()}\n"
            f"Cantidad cargada/entregada: {variables['CANTIDADINFORMACIONCARGA']} / "
            f"{variables['CANTIDADENTREGADA']}\n\n"
            f"Cargue: llegada {variables['HORALLEGADACARGUEREMESA']}, "
            f"entrada {variables['HORAENTRADACARGUEREMESA']}, "
            f"salida {variables['HORASALIDACARGUEREMESA']} ({variables['FECHALLEGADACARGUE']})\n"
        )
        if self._tipo_codigo() == "C":
            resumen += (f"Descargue: llegada {variables['HORALLEGADADESCARGUECUMPLIDO']}, "
                        f"entrada {variables['HORAENTRADADESCARGUECUMPLIDO']}, "
                        f"salida {variables['HORASALIDADESCARGUECUMPLIDO']} "
                        f"({variables['FECHALLEGADADESCARGUE']})\n")
        resumen += "\nEsta operación registra el cumplido en el RNDC (datos reales)."

        if not messagebox.askyesno("Confirmar cumplido", resumen):
            return

        self._lbl_estado.configure(text=f"📤 Registrando cumplido de {consec}…", fg=TEXT2)
        try:
            self.win.update_idletasks()
        except Exception:
            pass

        ok, res = cumplir_remesa(variables, perfil)
        if ok:
            self._lbl_estado.configure(
                text=f"✓ Cumplido registrado. Radicado: {res.get('ingresoid','?')}", fg=SUCCESS)
            messagebox.showinfo("Cumplido registrado",
                f"Se registró el cumplido de la remesa {consec}.\nRadicado: {res.get('ingresoid','?')}")
        else:
            self._lbl_estado.configure(text=f"✗ {res}", fg=DANGER)
            messagebox.showerror("Error al cumplir", str(res))
