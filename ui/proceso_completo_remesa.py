import tkinter as tk
from tkinter import ttk, messagebox

from config.theme import (
    BG, BG2, BG3, ACCENT, ACCENT2, SUCCESS, WARNING, DANGER,
    TEXT, TEXT2, BORDER, FONT_H1, FONT_H2, FONT_BODY, FONT_SMALL,
)
from services.rndc_service import (
    consultar_remesa_completa, anular_cumplido_remesa,
    corregir_remesa, cumplir_remesa,
)
from ui.corregir_remesa import CorregirRemesaModule
from ui.cumplir_remesa import CumplirRemesaModule


class ProcesoCompletoRemesaModule:
    """
    Orquestador: ejecuta de una sola vez la cadena
        (1) capturar tiempos del cumplido (proceso 5)
        (2) capturar datos de la remesa   (proceso 3)
        (3) anular cumplido               (proceso 28)  [si estaba cumplida]
        (4) corregir generador            (proceso 38, CODIGOCAMBIO=4)
        (5) re-cumplir                    (proceso 5)

    Reutiliza las funciones de servicio y las constantes de los módulos
    paso-a-paso (no los modifica). Mismas credenciales de corrección.
    """

    NITS_GENERADOR = ["8000213085", "9007867123"]

    MOTIVOS_ANULACION = ["O — Otro", "D — Error Digitación"]
    MOTIVOS_CAMBIO = [
        "3 — Decisión del Generador de Carga",
        "1 — Incumplimiento Generador de Carga",
        "2 — Incumplimiento Titular de Manifiesto",
        "4 — Decisión del Patio o Puerto",
    ]
    TIPOID = ["N — NIT", "C — Cédula Ciudadanía", "E — Cédula Extranjería"]

    def __init__(self, perfil_fn=None):
        self.perfil_fn = perfil_fn

    # ── Credenciales de corrección (igual que corregir/anular/cumplir) ────────

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
        tk.Label(hdr, text="⚡  Auto cambio-generador",
                 font=FONT_H1, bg=BG2, fg=TEXT).pack(padx=20)
        tk.Label(hdr, text="Descumple → cambia generador → vuelve a cumplir, todo automático.",
                 font=FONT_SMALL, bg=BG2, fg=TEXT2).pack(padx=20)

        body = tk.Frame(container, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        # ── Parámetros ────────────────────────────────────────────────────────
        card = tk.Frame(body, bg=BG2, padx=12, pady=10)
        card.pack(fill=tk.X, pady=(0, 10))

        r1 = tk.Frame(card, bg=BG2); r1.pack(fill=tk.X, pady=4)
        tk.Label(r1, text="Consecutivo remesa:", font=FONT_BODY, bg=BG2, fg=TEXT,
                 width=22, anchor="w").pack(side=tk.LEFT)
        self.var_consec = tk.StringVar()
        tk.Entry(r1, textvariable=self.var_consec, font=FONT_BODY, width=22,
                 bg=BG3, fg=TEXT, insertbackground=TEXT, relief="flat",
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side=tk.LEFT)

        r2 = tk.Frame(card, bg=BG2); r2.pack(fill=tk.X, pady=4)
        tk.Label(r2, text="Nuevo NIT generador:", font=FONT_BODY, bg=BG2, fg=TEXT,
                 width=22, anchor="w").pack(side=tk.LEFT)
        self.var_nit = tk.StringVar(value=self.NITS_GENERADOR[0])
        ttk.Combobox(r2, textvariable=self.var_nit, values=self.NITS_GENERADOR,
                     font=FONT_BODY, width=20).pack(side=tk.LEFT)  # editable (manual)
        tk.Label(r2, text="Tipo ID:", font=FONT_SMALL, bg=BG2, fg=TEXT2).pack(side=tk.LEFT, padx=(12, 4))
        self.var_tipoid = tk.StringVar(value=self.TIPOID[0])
        ttk.Combobox(r2, textvariable=self.var_tipoid, values=self.TIPOID,
                     state="readonly", font=FONT_BODY, width=20).pack(side=tk.LEFT)

        r3 = tk.Frame(card, bg=BG2); r3.pack(fill=tk.X, pady=4)
        tk.Label(r3, text="Código sede generador:", font=FONT_BODY, bg=BG2, fg=TEXT,
                 width=22, anchor="w").pack(side=tk.LEFT)
        self.var_sede = tk.StringVar(value="1")
        tk.Entry(r3, textvariable=self.var_sede, font=FONT_BODY, width=10,
                 bg=BG3, fg=TEXT, insertbackground=TEXT, relief="flat",
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side=tk.LEFT)

        r4 = tk.Frame(card, bg=BG2); r4.pack(fill=tk.X, pady=4)
        tk.Label(r4, text="Motivo anulación:", font=FONT_SMALL, bg=BG2, fg=TEXT2,
                 width=22, anchor="w").pack(side=tk.LEFT)
        self.var_mot_anul = tk.StringVar(value=self.MOTIVOS_ANULACION[0])
        ttk.Combobox(r4, textvariable=self.var_mot_anul, values=self.MOTIVOS_ANULACION,
                     state="readonly", font=FONT_BODY, width=22).pack(side=tk.LEFT, padx=(0, 12))
        tk.Label(r4, text="Motivo cambio:", font=FONT_SMALL, bg=BG2, fg=TEXT2).pack(side=tk.LEFT, padx=(0, 4))
        self.var_mot_camb = tk.StringVar(value=self.MOTIVOS_CAMBIO[0])
        ttk.Combobox(r4, textvariable=self.var_mot_camb, values=self.MOTIVOS_CAMBIO,
                     state="readonly", font=FONT_BODY, width=34).pack(side=tk.LEFT)

        # ── Botón ejecutar ─────────────────────────────────────────────────────
        btn_row = tk.Frame(body, bg=BG); btn_row.pack(fill=tk.X, pady=(2, 8))
        self._btn = tk.Label(btn_row, text="⚡  Ejecutar proceso completo",
                             font=("Segoe UI", 10, "bold"), bg=ACCENT, fg="white",
                             cursor="hand2", padx=16, pady=8)
        self._btn.pack(side=tk.LEFT)
        self._btn.bind("<Button-1>", lambda e: self._ejecutar())

        _btn_limpiar = tk.Label(btn_row, text="🗑  Limpiar", font=FONT_BODY,
                                bg="#555e7a", fg="white", cursor="hand2", padx=12, pady=8)
        _btn_limpiar.pack(side=tk.LEFT, padx=(8, 0))
        _btn_limpiar.bind("<Button-1>", lambda e: self._limpiar())

        # ── Log ────────────────────────────────────────────────────────────────
        logcard = tk.Frame(body, bg=BG2)
        logcard.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        tk.Label(logcard, text="📜  Registro del proceso",
                 font=FONT_H2, bg=BG2, fg=TEXT).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Frame(logcard, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=(0, 6))
        lf = tk.Frame(logcard, bg=BG2); lf.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self._log = tk.Text(lf, height=14, bg=BG3, fg=TEXT, relief="flat",
                            font=("Consolas", 9), wrap="word", state="disabled")
        sb = ttk.Scrollbar(lf, orient="vertical", command=self._log.yview)
        self._log.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._log.tag_config("ok",   foreground="#4ade80")
        self._log.tag_config("err",  foreground="#f87171")
        self._log.tag_config("info", foreground=TEXT2)
        self._log.tag_config("step", foreground=ACCENT2)

    # ── Log helper ──────────────────────────────────────────────────────────────

    def _put(self, msg, tag="info"):
        self._log.configure(state="normal")
        self._log.insert(tk.END, msg + "\n", tag)
        self._log.see(tk.END)
        self._log.configure(state="disabled")
        try:
            self.win.update_idletasks()
        except Exception:
            pass

    def _limpiar(self):
        self.var_consec.set("")
        self.var_nit.set(self.NITS_GENERADOR[0])
        self.var_sede.set("1")
        self.var_tipoid.set(self.TIPOID[0])
        self.var_mot_anul.set(self.MOTIVOS_ANULACION[0])
        self.var_mot_camb.set(self.MOTIVOS_CAMBIO[0])
        self._limpiar_log()

    def _limpiar_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", tk.END)
        self._log.configure(state="disabled")

    # ── Plan de re-cumplido ─────────────────────────────────────────────────────

    @staticmethod
    def _plan_cumplido(res5, res3):
        """
        Decide el tipo de cumplido y los tiempos a usar:
          1. Si el proceso 5 trae tiempos reales → Normal (cargue+descargue) o
             Suspensión (solo cargue).
          2. Si no, calcula de las citas (proceso 3): Normal si hay cita
             cargue+descargue; Suspensión si solo cargue.
        Devuelve (tipo, dict_tiempos, descripcion) o (None, {}, motivo).
        """
        FH = CumplirRemesaModule._fecha_hora_mas
        CR = CumplirRemesaModule.CARGUE_ROWS
        DR = CumplirRemesaModule.DESCARGUE_ROWS
        times = {}

        real_carg = res5.get("fechallegadacargue") and res5.get("horallegadacargueremesa")
        real_desc = res5.get("fechallegadadescargue") and res5.get("horallegadadescarguecumplido")
        if real_carg:
            for _e, fc, hc in CR:
                times[fc] = res5.get(fc.lower(), ""); times[hc] = res5.get(hc.lower(), "")
            if real_desc:
                for _e, fc, hc in DR:
                    times[fc] = res5.get(fc.lower(), ""); times[hc] = res5.get(hc.lower(), "")
                return "C", times, "Normal (tiempos reales del cumplido)"
            return "S", times, "Suspensión (solo cargue real)"

        # Calcular de citas
        f_carg = res3.get("fechacitapactadacargue", ""); h_carg = res3.get("horacitapactadacargue", "")
        f_desc = res3.get("fechacitapactadadescargue", ""); h_desc = res3.get("horacitapactadadescargueremesa", "")
        if f_carg and h_carg:
            for n, (_e, fc, hc) in enumerate(CR, 1):
                fe, ho = FH(f_carg, h_carg, n); times[fc] = fe; times[hc] = ho
            if f_desc and h_desc:
                for n, (_e, fc, hc) in enumerate(DR, 1):
                    fe, ho = FH(f_desc, h_desc, n); times[fc] = fe; times[hc] = ho
                return "C", times, "Normal (calculado de citas)"
            return "S", times, "Suspensión (calculado, sin cita descargue)"

        return None, {}, "La remesa no tiene tiempos ni citas para cumplir"

    # ── Ejecutar ────────────────────────────────────────────────────────────────

    def _ejecutar(self):
        consec = self._consec_efectivo()
        if not consec:
            messagebox.showwarning("Sin consecutivo", "Escribe el consecutivo de la remesa.")
            return
        if not self.perfil_fn:
            messagebox.showerror("Sin perfil", "No hay perfil activo.")
            return
        nit_nuevo = self.var_nit.get().strip()
        if not nit_nuevo:
            messagebox.showwarning("Sin NIT", "Indica el NIT del nuevo generador.")
            return

        sede   = self.var_sede.get().strip() or "1"
        tipoid = self.var_tipoid.get().strip().split(" ")[0]   # "N — ..." → "N"
        cod_anul = self.var_mot_anul.get().strip().split(" ")[0]
        cod_camb = self.var_mot_camb.get().strip().split(" ")[0]
        perfil = self._perfil()

        if not messagebox.askyesno(
                "Confirmar proceso completo",
                f"¿Ejecutar TODO el proceso para la remesa {consec}?\n\n"
                f"1. Anular cumplido (si estaba cumplida, motivo {cod_anul})\n"
                f"2. Cambiar generador → NIT {nit_nuevo} (sede {sede}, motivo {cod_camb})\n"
                f"3. Volver a cumplir (si la remesa tiene manifiesto y datos)\n\n"
                "Son operaciones reales en el RNDC y NO se pueden deshacer."):
            return

        self._limpiar_log()
        self._put(f"▶ Proceso completo para remesa {consec}", "step")

        # 1. Capturar tiempos del cumplido (proceso 5) — ANTES de anular
        self._put("1) Consultando cumplido actual (proceso 5)…")
        ok5, res5 = consultar_remesa_completa(consec, perfil, procesoid=5)
        if not ok5:
            self._put(f"   ⚠ No se pudo consultar cumplido: {res5}", "err")
            res5 = {}
        else:
            self._put("   ✓ Cumplido consultado.", "ok")

        # 2. Capturar datos de la remesa (proceso 3) — necesario para corregir
        self._put("2) Consultando datos de la remesa (proceso 3)…")
        ok3, res3 = consultar_remesa_completa(consec, perfil, procesoid=3)
        if not ok3:
            self._put(f"   ✗ No se pudo consultar la remesa: {res3}. Proceso abortado.", "err")
            return
        self._put("   ✓ Remesa consultada.", "ok")

        # Estado de la remesa: ¿tiene manifiesto asignado? ¿estaba cumplida?
        manifiesto      = str(res3.get("nummanifiestocarga", "")).strip()
        estaba_cumplida = bool(res5.get("fechallegadacargue"))
        sin_manifiesto  = not manifiesto

        # Decidir el plan de cumplido AHORA (antes de anular). NO se aborta si no
        # se puede cumplir: el objetivo principal es CORREGIR el generador.
        tipo, times, desc_plan = self._plan_cumplido(res5, res3)
        if sin_manifiesto:
            puede_cumplir = False
            self._put("   → Remesa PENDIENTE DE ASIGNAR MANIFIESTO: se omitirá el "
                      "cumplido (no es posible sin manifiesto).", "info")
        elif tipo is None:
            puede_cumplir = False
            self._put(f"   → {desc_plan}: se omitirá el cumplido.", "info")
        else:
            puede_cumplir = True
            self._put(f"   → Re-cumplido planeado: {desc_plan}", "info")

        # 3. Anular cumplido (proceso 28) si estaba cumplida
        if estaba_cumplida:
            self._put(f"3) Anulando cumplido (proceso 28, motivo {cod_anul})…")
            okA, resA = anular_cumplido_remesa(consec, cod_anul, perfil)
            if not okA:
                self._put(f"   ✗ Falló la anulación: {resA}. Proceso abortado.", "err")
                return
            self._put(f"   ✓ Cumplido anulado (radicado {resA.get('ingresoid','?')}).", "ok")
        else:
            self._put("3) La remesa no estaba cumplida → se omite la anulación.", "info")

        # 4. Corregir generador (proceso 38, CODIGOCAMBIO=4)
        self._put(f"4) Corrigiendo generador → NIT {nit_nuevo} (proceso 38)…")
        var_corr = {
            "NUMNITEMPRESATRANSPORTE": perfil.get("nit_socio", ""),
            "consecutivoRemesa":       consec,
        }
        for envio, consulta in CorregirRemesaModule.BASE_FIELDS:
            var_corr[envio] = res3.get(consulta, "")
        var_corr["codTipoIdPropietario"] = tipoid
        var_corr["numIdPropietario"]     = nit_nuevo
        var_corr["codSedePropietario"]   = sede
        var_corr["MOTIVOCAMBIO"] = cod_camb
        var_corr["CODIGOCAMBIO"] = "4"   # Cambio de Generador
        okC, resC = corregir_remesa(var_corr, perfil)
        if not okC:
            self._put(f"   ✗ Falló la corrección: {resC}. Proceso abortado "
                      "(la remesa quedó descumplida; corrige/cumple a mano).", "err")
            return
        self._put(f"   ✓ Generador cambiado (radicado {resC.get('ingresoid','?')}).", "ok")

        # 5. Re-cumplir (proceso 5) — solo si es posible
        if not puede_cumplir:
            motivo = ("la remesa no tiene manifiesto asignado"
                      if sin_manifiesto else "no hay tiempos ni citas")
            self._put(f"5) Cumplido OMITIDO: {motivo}.", "info")
            self._put("✔ PROCESO FINALIZADO: generador cambiado (sin cumplido).", "ok")
            messagebox.showinfo("Proceso completo",
                f"Remesa {consec}:\n• Generador → {nit_nuevo}\n"
                f"• Cumplido omitido ({motivo}).")
            return

        self._put(f"5) Re-cumpliendo remesa ({desc_plan})…")
        cant = res3.get("cantidadcargada", "") or res5.get("cantidadcargada", "") \
            or res3.get("cantidadinformacioncarga", "")
        var_cum = {
            "NUMNITEMPRESATRANSPORTE":  perfil.get("nit_socio", ""),
            "CONSECUTIVOREMESA":        consec,
            "TIPOCUMPLIDOREMESA":       tipo,
            "CANTIDADINFORMACIONCARGA": cant,
            "CANTIDADENTREGADA":        cant if tipo == "C" else "0",
        }
        var_cum.update(times)
        if tipo == "S":
            var_cum["MOTIVOSUSPENSIONREMESA"] = "O"
        okU, resU = cumplir_remesa(var_cum, perfil)
        if not okU:
            self._put(f"   ✗ Falló el re-cumplido: {resU}. La remesa quedó con el "
                      "generador cambiado pero SIN cumplir (cúmplela a mano).", "err")
            return
        self._put(f"   ✓ Remesa cumplida de nuevo (radicado {resU.get('ingresoid','?')}).", "ok")

        self._put("✔ PROCESO COMPLETO FINALIZADO CORRECTAMENTE.", "ok")
        messagebox.showinfo("Proceso completo",
            f"Remesa {consec} procesada:\n"
            f"• Cumplido anulado\n• Generador → {nit_nuevo}\n• Re-cumplida ({tipo})")
