"""
Constantes de los módulos de remesas RNDC, COPIADAS TAL CUAL desde los módulos de
escritorio (ui/corregir_remesa.py) para reutilizarlas en la web sin importar tkinter.
"""

# ── Corregir remesa (proceso 38) — de CorregirRemesaModule ───────────────────
# Conjunto base que SIEMPRE se envía al proceso 38. (nombre_envio, nombre_consulta)
CORREGIR_BASE_FIELDS = [
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
    ("CODIGOARANCEL_CODE",        "codigoarancel_code"),
    ("NOMBRENEP",                 "nombrenep"),
    ("DESCRIPCIONDETALLADARESIDUO", "descripciondetalladaresiduo"),
    ("RESIDUO",                   "residuo"),
    ("RESIDUODESAGREGACION",      "residuodesagregacion"),
    ("PELIGROSIDAD",              "peligrosidad"),
]

# Opción a corregir (CODIGOCAMBIO) → campos editables. (nombre_envio, etiqueta)
CORREGIR_OPCION_CAMPOS = {
    "1": [("fechaCitaPactadaCargue",    "Fecha cargue (DD/MM/AAAA)"),
          ("horaCitaPactadaCargue",     "Hora cargue (HH:MM)")],
    "2": [("fechaCitaPactadaDescargue", "Fecha descargue (DD/MM/AAAA)"),
          ("HORACITAPACTADADESCARGUE",  "Hora descargue (HH:MM)")],
    "3": [("codTipoIdDestinatario",     "Tipo ID destinatario"),
          ("numIdDestinatario",         "Identificación destinatario"),
          ("codSedeDestinatario",       "Código sede destinatario")],
    "4": [("codTipoIdPropietario",      "Tipo ID generador"),
          ("numIdPropietario",          "Identificación generador"),
          ("codSedePropietario",        "Código sede generador")],
    "5": [("contenedorSerial",          "Serial contenedor")],
}

CORREGIR_TIPOID_OPCIONES = [
    ("C", "Cédula Ciudadanía"), ("D", "Carné Diplomático"), ("N", "NIT"),
    ("P", "Pasaporte"), ("T", "Tarjeta Identidad"), ("E", "Cédula Extranjería"),
    ("U", "NUIP"), ("X", "Identificación Extranjera"),
]
CORREGIR_CAMPOS_TIPOID = {"codTipoIdPropietario", "codTipoIdDestinatario"}

CORREGIR_OPCIONES = [
    "1 — Cambio Cita de Cargue",
    "2 — Cambio Cita de Descargue",
    "3 — Cambio Sede Descargue",
    "4 — Cambio de Generador",
    "5 — Cambio de Serial del Contenedor",
]
CORREGIR_MOTIVOS = [
    "1 — Incumplimiento Generador de Carga",
    "2 — Incumplimiento Titular de Manifiesto",
    "3 — Decisión del Generador de Carga",
    "4 — Decisión del Patio o Puerto que entrega el Contenedor",
]
CORREGIR_CONTEXTO = [
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


def tipoid_label(code):
    for c, n in CORREGIR_TIPOID_OPCIONES:
        if c == code:
            return f"{c} - {n}"
    return ""


def tipoid_code(label):
    return label.split(" ")[0].strip() if label else ""


# ── Cumplir remesa (proceso 5) — de CumplirRemesaModule ──────────────────────
from datetime import datetime as _dt, timedelta as _td

CUMPLIR_TIPOS = ["C — Cumplido Normal", "S — Suspensión"]

# (etiqueta, campo_fecha, campo_hora)
CUMPLIR_CARGUE_ROWS = [
    ("Llegada", "FECHALLEGADACARGUE", "HORALLEGADACARGUEREMESA"),
    ("Entrada", "FECHAENTRADACARGUE", "HORAENTRADACARGUEREMESA"),
    ("Salida",  "FECHASALIDACARGUE",  "HORASALIDACARGUEREMESA"),
]
CUMPLIR_DESCARGUE_ROWS = [
    ("Llegada", "FECHALLEGADADESCARGUE", "HORALLEGADADESCARGUECUMPLIDO"),
    ("Entrada", "FECHAENTRADADESCARGUE", "HORAENTRADADESCARGUECUMPLIDO"),
    ("Salida",  "FECHASALIDADESCARGUE",  "HORASALIDADESCARGUECUMPLIDO"),
]


def fecha_hora_mas(fecha_ddmmaaaa, hhmm, n):
    """Suma n horas a (fecha, hora) → ('DD/MM/AAAA', 'HH:MM'), avanzando el día si
    pasa de medianoche. Idéntico a CumplirRemesaModule._fecha_hora_mas."""
    try:
        dt = _dt.strptime(f"{fecha_ddmmaaaa.strip()} {hhmm.strip()}",
                          "%d/%m/%Y %H:%M") + _td(hours=n)
        return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M")
    except Exception:
        return fecha_ddmmaaaa, ""


# ── Auto cambio-generador — de ProcesoCompletoRemesaModule ───────────────────
AUTO_NITS_GENERADOR = ["8000213085", "9007867123"]
AUTO_MOTIVOS_ANULACION = ["O — Otro", "D — Error Digitación"]
AUTO_MOTIVOS_CAMBIO = [
    "3 — Decisión del Generador de Carga",
    "1 — Incumplimiento Generador de Carga",
    "2 — Incumplimiento Titular de Manifiesto",
    "4 — Decisión del Patio o Puerto",
]
AUTO_TIPOID = ["N — NIT", "C — Cédula Ciudadanía", "E — Cédula Extranjería"]


def plan_cumplido(res5, res3):
    """Decide tipo de cumplido y tiempos. Réplica de ProcesoCompletoRemesaModule._plan_cumplido.
    Devuelve (tipo, dict_tiempos, descripcion) o (None, {}, motivo)."""
    times = {}
    CR, DR = CUMPLIR_CARGUE_ROWS, CUMPLIR_DESCARGUE_ROWS
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
    f_carg = res3.get("fechacitapactadacargue", ""); h_carg = res3.get("horacitapactadacargue", "")
    f_desc = res3.get("fechacitapactadadescargue", ""); h_desc = res3.get("horacitapactadadescargueremesa", "")
    if f_carg and h_carg:
        for n, (_e, fc, hc) in enumerate(CR, 1):
            fe, ho = fecha_hora_mas(f_carg, h_carg, n); times[fc] = fe; times[hc] = ho
        if f_desc and h_desc:
            for n, (_e, fc, hc) in enumerate(DR, 1):
                fe, ho = fecha_hora_mas(f_desc, h_desc, n); times[fc] = fe; times[hc] = ho
            return "C", times, "Normal (calculado de citas)"
        return "S", times, "Suspensión (calculado, sin cita descargue)"
    return None, {}, "La remesa no tiene tiempos ni citas para cumplir"
