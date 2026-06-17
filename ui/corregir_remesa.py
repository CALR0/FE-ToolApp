import tkinter as tk
from tkinter import ttk, messagebox

from config.theme import (
    BG, BG2, BG3, ACCENT, ACCENT2, SUCCESS, WARNING, DANGER,
    TEXT, TEXT2, BORDER, FONT_H1, FONT_H2, FONT_BODY, FONT_SMALL,
)
from services.rndc_service import consultar_remesa_completa, corregir_remesa


class CorregirRemesaModule:
    """
    Panel embebido para corregir una remesa en el RNDC (proceso 38), replicando
    el formulario web del RNDC:
      1. Consultar el consecutivo → trae todos los datos (solo lectura).
      2. Elegir "Opción a Corregir" (CODIGOCAMBIO) → aparecen SOLO los campos de
         esa opción, prellenados con el valor actual.
      3. Elegir "Motivo del Cambio" (MOTIVOCAMBIO).
      4. Enviar (con confirmación). Se manda el conjunto completo de variables
         (prellenado del consult) con los campos editados sobrescritos.
    """

    # Conjunto base que SIEMPRE se envía al proceso 38, prellenado desde la
    # consulta. (nombre_envio, nombre_consulta)
    BASE_FIELDS = [
        ("codOperacionTransporte",    "codoperaciontransporte"),
        ("codNaturalezaCarga",        "codnaturalezacarga"),
        ("codTipoEmpaque",            "codtipoempaque"),
        ("descripcionCortaProducto",  "descripcioncortaproducto"),
        ("mercanciaRemesa",           "mercanciaremesa"),
        ("cantidadCargada",           "cantidadcargada"),
        ("unidadMedidaCapacidad",     "unidadmedidacapacidad"),
        ("pesoContenedorVacio",       "pesocontenedorvacio"),
        ("codTipoIdDestinatario",     "codtipoiddestinatario"),
        ("numIdDestinatario",         "numiddestinatario"),
        ("codSedeDestinatario",       "codsededestinatario"),
        ("codTipoIdPropietario",      "codtipoidpropietario"),
        ("numIdPropietario",          "numidpropietario"),
        ("codSedePropietario",        "codsedepropietario"),
        ("duenoPoliza",               "duenopoliza"),
        ("horasPactoCarga",           "horaspactocarga"),
        ("minutospactocarga",         "minutospactocarga"),
        ("fechaCitaPactadaCargue",    "fechacitapactadacargue"),
        ("horaCitaPactadaCargue",     "horacitapactadacargue"),
        ("horasPactoDescargue",       "horaspactodescargue"),
        ("minutosPactoDescargue",     "minutospactodescargue"),
        ("fechaCitaPactadaDescargue", "fechacitapactadadescargue"),
        ("HORACITAPACTADADESCARGUE",  "horacitapactadadescargueremesa"),
        ("observaciones",             "observaciones"),
        ("contenedorSerial",          "contenedorserial"),
        # Residuos / arancel (passthrough, normalmente vacíos)
        ("CODIGOARANCEL_CODE",        "codigoarancel_code"),
        ("NOMBRENEP",                 "nombrenep"),
        ("DESCRIPCIONDETALLADARESIDUO", "descripciondetalladaresiduo"),
        ("RESIDUO",                   "residuo"),
        ("RESIDUODESAGREGACION",      "residuodesagregacion"),
        ("PELIGROSIDAD",              "peligrosidad"),
    ]

    # Opción a corregir → campos editables que aparecen. (nombre_envio, etiqueta)
    OPCION_CAMPOS = {
        "1": [("fechaCitaPactadaCargue",    "Fecha cargue (DD/MM/AAAA)"),
              ("horaCitaPactadaCargue",     "Hora cargue (HH:MM)")],
        "2": [("fechaCitaPactadaDescargue", "Fecha descargue (DD/MM/AAAA)"),
              ("HORACITAPACTADADESCARGUE",  "Hora descargue (HH:MM)")],
        "3": [("codTipoIdDestinatario",     "Tipo ID destinatario (C/N/E/…)"),
              ("numIdDestinatario",         "Identificación destinatario"),
              ("codSedeDestinatario",       "Código sede destinatario")],
        "4": [("codTipoIdPropietario",      "Tipo ID generador (C/N/E/…)"),
              ("numIdPropietario",          "Identificación generador"),
              ("codSedePropietario",        "Código sede generador")],
        "5": [("contenedorSerial",          "Serial contenedor")],
    }

    # Tipos de identificación (código → nombre) según el RNDC.
    TIPOID_OPCIONES = [
        ("C", "Cédula Ciudadanía"),
        ("D", "Carné Diplomático"),
        ("N", "NIT"),
        ("P", "Pasaporte"),
        ("T", "Tarjeta Identidad"),
        ("E", "Cédula Extranjería"),
        ("U", "NUIP"),
        ("X", "Identificación Extranjera"),
    ]
    # Campos que se renderizan como combobox de tipo de identificación
    CAMPOS_TIPOID = {"codTipoIdPropietario", "codTipoIdDestinatario"}

    OPCIONES = [
        "1 — Cambio Cita de Cargue",
        "2 — Cambio Cita de Descargue",
        "3 — Cambio Sede Descargue",
        "4 — Cambio de Generador",
        "5 — Cambio de Serial del Contenedor",
    ]
    MOTIVOS = [
        "1 — Incumplimiento Generador de Carga",
        "2 — Incumplimiento Titular de Manifiesto",
        "3 — Decisión del Generador de Carga",
        "4 — Decisión del Patio o Puerto que entrega el Contenedor",
    ]

    # Campos a mostrar como contexto (solo lectura) tras consultar.
    CONTEXTO = [
        ("remempresa",        "Empresa"),
        ("rem_orig",          "Origen"),
        ("rem_desti",         "Destino"),
        ("rempropietario",    "Generador (propietario)"),
        ("remdestinatario",   "Destinatario"),
        ("descripcioncortaproducto", "Producto"),
        ("cantidadcargada",   "Cantidad cargada"),
        ("fechacitapactadacargue",   "Cita cargue"),
        ("fechacitapactadadescargue", "Cita descargue"),
        ("estado",            "Estado"),
    ]

    def __init__(self, perfil_fn=None):
        self.perfil_fn = perfil_fn
        self.vars      = {}      # nombre_envio → StringVar (conjunto base)
        self._consulta = {}      # respuesta cruda del RNDC
        self._consultada = False

    # ── Construcción ──────────────────────────────────────────────────────────

    def _build(self, container):
        self.win = container.winfo_toplevel()

        hdr = tk.Frame(container, bg=BG2, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="🛠  Corregir Remesa (RNDC proceso 38)",
                 font=FONT_H1, bg=BG2, fg=TEXT).pack(padx=20)
        tk.Label(hdr, text="Consulta una remesa, elige qué corregir y envía la corrección al RNDC.",
                 font=FONT_SMALL, bg=BG2, fg=TEXT2).pack(padx=20)

        body = tk.Frame(container, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        # StringVars del conjunto base
        for envio, _consulta in self.BASE_FIELDS:
            self.vars[envio] = tk.StringVar()

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
        self._card_ctx = tk.Frame(body, bg=BG2)
        self._card_ctx.pack(fill=tk.X, pady=(0, 10))
        tk.Label(self._card_ctx, text="📋  Datos actuales de la remesa",
                 font=FONT_H2, bg=BG2, fg=TEXT).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Frame(self._card_ctx, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=(0, 6))
        self._ctx_grid = tk.Frame(self._card_ctx, bg=BG2)
        self._ctx_grid.pack(fill=tk.X, padx=12, pady=(0, 12))
        self._ctx_labels = {}
        for i, (clave, etq) in enumerate(self.CONTEXTO):
            r = i // 2
            c = (i % 2) * 2
            tk.Label(self._ctx_grid, text=etq + ":", font=FONT_SMALL, bg=BG2,
                     fg=TEXT2, anchor="w").grid(row=r, column=c, sticky="w",
                                                padx=(4, 6), pady=2)
            v = tk.Label(self._ctx_grid, text="—", font=FONT_BODY, bg=BG2,
                         fg=TEXT, anchor="w")
            v.grid(row=r, column=c+1, sticky="w", padx=(0, 18), pady=2)
            self._ctx_labels[clave] = v

        # ── Opciones para corregir ────────────────────────────────────────────
        card = tk.Frame(body, bg=BG2)
        card.pack(fill=tk.X, pady=(0, 10))
        tk.Label(card, text="🔁  Opciones para corregir la remesa",
                 font=FONT_H2, bg=BG2, fg=TEXT).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Frame(card, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=(0, 6))
        sel = tk.Frame(card, bg=BG2)
        sel.pack(fill=tk.X, padx=12, pady=(0, 6))

        tk.Label(sel, text="Opción a Corregir", font=FONT_SMALL, bg=BG2, fg=TEXT2,
                 anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=3)
        self.var_opcion = tk.StringVar(value=self.OPCIONES[0])
        cmb_op = ttk.Combobox(sel, textvariable=self.var_opcion, values=self.OPCIONES,
                              state="readonly", font=FONT_BODY, width=40)
        cmb_op.grid(row=0, column=1, sticky="w", padx=(0, 20), pady=3)
        cmb_op.bind("<<ComboboxSelected>>", lambda e: self._on_opcion_change())

        tk.Label(sel, text="Motivo del Cambio", font=FONT_SMALL, bg=BG2, fg=TEXT2,
                 anchor="w").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=3)
        self.var_motivo = tk.StringVar(value=self.MOTIVOS[0])
        ttk.Combobox(sel, textvariable=self.var_motivo, values=self.MOTIVOS,
                     state="readonly", font=FONT_BODY, width=52).grid(
                     row=1, column=1, sticky="w", padx=(0, 20), pady=3)

        # Frame dinámico: campos según la opción
        self._dyn = tk.Frame(card, bg=BG2)
        self._dyn.pack(fill=tk.X, padx=12, pady=(4, 12))

        # ── Enviar ────────────────────────────────────────────────────────────
        pie = tk.Frame(body, bg=BG)
        pie.pack(fill=tk.X, pady=(4, 10))
        self._btn_enviar = tk.Label(pie, text="💾  Guardar remesa corregida",
                                    font=("Segoe UI", 9, "bold"), bg=BG3, fg=TEXT2,
                                    cursor="hand2", padx=14, pady=7)
        self._btn_enviar.pack(side=tk.RIGHT)
        self._btn_enviar.bind("<Button-1>", lambda e: self._enviar())

        self._on_opcion_change()   # render inicial de campos dinámicos

    # ── Campos dinámicos por opción ───────────────────────────────────────────

    def _codigo_opcion(self):
        return self.var_opcion.get().strip().split(" ")[0]   # "4 — ..." → "4"

    @classmethod
    def _tipoid_label(cls, code):
        """Código ('N') → etiqueta ('N - NIT'). '' si no se reconoce."""
        for c, n in cls.TIPOID_OPCIONES:
            if c == code:
                return f"{c} - {n}"
        return ""

    @staticmethod
    def _tipoid_code(label):
        """Etiqueta ('N - NIT') → código ('N')."""
        return label.split(" ")[0].strip() if label else ""

    def _on_opcion_change(self):
        for w in self._dyn.winfo_children():
            w.destroy()
        codigo = self._codigo_opcion()
        campos = self.OPCION_CAMPOS.get(codigo, [])
        for i, (envio, etiqueta) in enumerate(campos):
            tk.Label(self._dyn, text=etiqueta, font=FONT_SMALL, bg=BG2, fg=TEXT2,
                     anchor="w").grid(row=i // 2, column=(i % 2) * 2, sticky="w",
                                      padx=(4, 6), pady=4)

            if envio in self.CAMPOS_TIPOID:
                # Combobox de tipo de identificación. El combo muestra etiquetas
                # pero self.vars[envio] mantiene el CÓDIGO (lo que se envía).
                disp = tk.StringVar(value=self._tipoid_label(self.vars[envio].get().strip()))
                cb = ttk.Combobox(self._dyn, textvariable=disp,
                                  values=[f"{c} - {n}" for c, n in self.TIPOID_OPCIONES],
                                  state="readonly", font=FONT_BODY, width=26)
                cb.grid(row=i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=(0, 18), pady=4)

                def _sync(_e=None, env=envio, d=disp):
                    self.vars[env].set(self._tipoid_code(d.get()))
                cb.bind("<<ComboboxSelected>>", _sync)
            else:
                tk.Entry(self._dyn, textvariable=self.vars[envio], font=FONT_BODY, width=28,
                         bg=BG3, fg=TEXT, insertbackground=TEXT, relief="flat",
                         highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT).grid(row=i // 2, column=(i % 2) * 2 + 1,
                                                     sticky="w", padx=(0, 18), pady=4)

    # ── Consultar ─────────────────────────────────────────────────────────────

    def _perfil(self):
        """
        Perfil activo pero con las credenciales de CORRECCIÓN si el perfil las
        define (rndc_usuario_corregir / rndc_password_corregir). Así el módulo de
        corregir usa un usuario distinto al del resto de la app, sin alterar los
        demás módulos. Si no hay credenciales de corrección, usa las normales.
        """
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

        self._consulta = res
        # Prellenar el conjunto base
        for envio, consulta in self.BASE_FIELDS:
            self.vars[envio].set(res.get(consulta, ""))
        # Contexto solo lectura
        for clave, lbl in self._ctx_labels.items():
            lbl.configure(text=res.get(clave, "") or "—")

        self._consultada = True
        self._btn_enviar.configure(bg=SUCCESS, fg="white")
        self._lbl_estado.configure(
            text=f"✓ Remesa {consec} cargada (radicado {res.get('ingresoid','?')}). "
                 f"Elige la opción a corregir.", fg=SUCCESS)
        self._on_opcion_change()

    # ── Enviar ────────────────────────────────────────────────────────────────

    def _enviar(self):
        if not self._consultada:
            messagebox.showwarning("Consulta primero",
                "Primero consulta una remesa para cargar sus datos.")
            return
        perfil = self._perfil()
        consec = self._consec_efectivo()
        codigo = self._codigo_opcion()
        motivo = self.var_motivo.get().strip().split(" ")[0]

        # Construir variables: identificador + conjunto base (prellenado/editado)
        variables = {
            "NUMNITEMPRESATRANSPORTE": perfil.get("nit_socio", ""),
            "consecutivoRemesa":       consec,
        }
        for envio, _consulta in self.BASE_FIELDS:
            variables[envio] = self.vars[envio].get().strip()
        variables["MOTIVOCAMBIO"] = motivo
        variables["CODIGOCAMBIO"] = codigo

        # Validar que los campos de la opción no queden vacíos
        faltantes = [etq for env, etq in self.OPCION_CAMPOS.get(codigo, [])
                     if not self.vars[env].get().strip()]
        if faltantes:
            messagebox.showwarning("Campos requeridos",
                "Completa los campos de la opción seleccionada:\n• " + "\n• ".join(faltantes))
            return

        # Resumen de cambios para confirmar
        detalle = "\n".join(f"   {etq}: {self.vars[env].get().strip()}"
                            for env, etq in self.OPCION_CAMPOS.get(codigo, []))
        resumen = (
            f"¿Guardar la corrección de la remesa {consec}?\n\n"
            f"Opción: {self.var_opcion.get()}\n"
            f"Motivo: {self.var_motivo.get()}\n\n"
            f"{detalle}\n\n"
            "Esta operación modifica datos reales en el RNDC."
        )
        if not messagebox.askyesno("Confirmar corrección", resumen):
            return

        self._lbl_estado.configure(text=f"📤 Enviando corrección de {consec}…", fg=TEXT2)
        try:
            self.win.update_idletasks()
        except Exception:
            pass

        ok, res = corregir_remesa(variables, perfil)
        if ok:
            self._lbl_estado.configure(
                text=f"✓ Corrección enviada. Radicado: {res.get('ingresoid','?')}", fg=SUCCESS)
            messagebox.showinfo("Corrección enviada",
                f"La remesa {consec} fue corregida.\nRadicado: {res.get('ingresoid','?')}")
        else:
            self._lbl_estado.configure(text=f"✗ {res}", fg=DANGER)
            messagebox.showerror("Error al corregir", str(res))
