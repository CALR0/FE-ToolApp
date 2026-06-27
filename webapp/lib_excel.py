"""
Lógica de parseo y filtros de "Generar facturas vía Excel", PORTADA TAL CUAL desde
ui/excel_loader.py (mismo comportamiento, mismos filtros a nivel de factura).
Reutiliza core.xml_generator (_parse_valor) sin tocarlo. No depende de tkinter.
"""
import re
from datetime import datetime

import pandas as pd

from core.xml_generator import _parse_valor

# ── Constantes (idénticas a ExcelLoaderWindow) ───────────────────────────────
FILTROS_GEN = [
    "Todas (sin filtro)",
    "Solo Reconstruir = Sí",
    "Reconstruir = Sí y Novedad vacía",
    "Reconstruir Sí / condiciones ideales",
    "Coinciden remesas, NO coincide valor",
    "Coincide valor, NO coinciden remesas",
    "NO coinciden remesas",
    "NO coincide valor",
]
FILTRO_COND_IDEAL = "Reconstruir Sí / condiciones ideales"
FILTROS_NOVEDAD = {"Reconstruir = Sí y Novedad vacía", "Reconstruir Sí / condiciones ideales"}

# (clave, etiqueta, valor_default_sugerido)
COND_COLS = [
    ("col_comp_gen",      "Comp. Generador Carga RNDC",    "SI"),
    ("col_rem_creada",    "Remesa creada RNDC",            "SI EXISTE"),
    ("col_asoc_rem_man",  "Comp. Asociación Rem-Man RNDC", "SI"),
    ("col_cumplido_rem",  "Cumplido remesa RNDC",          "SI"),
    ("col_rem_facturada", "Remesa facturada",              "NO"),
]

# Campos de mapeo: (clave, etiqueta, requerido)
CAMPOS = [
    ("col_nf",         "Número de factura",          True),
    ("col_cufe",       "CUFE",                       True),
    ("col_fecha",      "Fecha de generación",        True),
    ("col_consec",     "Consecutivo / Remesa",       True),
    ("col_radicado",   "Radicado (opcional)",        False),
    ("col_val_rem",    "Valor unitario remesa ($)",  True),
    ("col_val_fac",    "Valor total factura ($)",    True),
    ("col_peso",       "Peso KGM (opcional)",        False),
    ("col_desc_lin",   "Descripción línea (opcional)", False),
    ("col_nit_cli",    "NIT cliente (opcional)",     False),
    ("col_nom_cli",    "Nombre cliente (opcional)",  False),
    ("col_novedad",    "Novedad remesa (opcional)",  False),
    ("col_comp_gen",   "Comp. Generador Carga RNDC (opcional)", False),
    ("col_rem_creada", "Remesa creada RNDC (opcional)", False),
    ("col_asoc_rem_man", "Comp. Asociación Rem-Man RNDC (opcional)", False),
    ("col_cumplido_rem", "Cumplido remesa RNDC (opcional)", False),
    ("col_rem_facturada", "Remesa facturada (opcional)", False),
    ("col_estado",     "Estado (opcional)",          False),
]


# ── Helpers (idénticos a ExcelLoaderWindow) ──────────────────────────────────
def _es_si(v):
    return str(v).strip().lower() in ("sí", "si", "s", "true", "1", "yes")


def _es_vacio(v):
    return str(v).strip().lower() in ("", "nan", "none")


def _cols_cruce(df):
    if df is None:
        return None
    rem = val = rec = None
    for col in df.columns.astype(str):
        cn = col.lower()
        if "coinciden" in cn and "remesa" in cn:
            rem = col
        elif "coincide" in cn and "valor" in cn:
            val = col
        elif "reconstruir" in cn:
            rec = col
    if rem and val and rec:
        return {"rem": rem, "val": val, "rec": rec}
    return None


def _col_novedad(df):
    if df is None:
        return None
    for col in df.columns.astype(str):
        if "novedad" in col.lower():
            return col
    return None


def _pasa_filtro(filtro, rem, val, rec, novedad=""):
    r = _es_si(rem); v = _es_si(val); x = _es_si(rec)
    if filtro == "Todas (sin filtro)":                      return True
    if filtro == "Solo Reconstruir = Sí":                   return x
    if filtro == "Reconstruir = Sí y Novedad vacía":        return x and _es_vacio(novedad)
    if filtro == FILTRO_COND_IDEAL:                         return x and _es_vacio(novedad)
    if filtro == "Coinciden remesas, NO coincide valor":    return r and not v
    if filtro == "Coincide valor, NO coinciden remesas":    return v and not r
    if filtro == "NO coinciden remesas":                    return not r
    if filtro == "NO coincide valor":                       return not v
    return True


def valores_unicos_columna(df, col):
    """Valores únicos no vacíos de una columna (para los combos de valor-condición)."""
    if df is None or col not in df.columns:
        return []
    return sorted({str(v).strip() for v in df[col].dropna() if str(v).strip()})


def validar(df, mapping, filtro):
    """Equivalente a _validar. Retorna (ok, mensaje)."""
    if df is None:
        return False, "Carga primero un archivo Excel."
    for clave, etq, req in CAMPOS:
        if req and not mapping.get(clave):
            return False, f"El campo obligatorio '{etq}' no tiene columna asignada."
    if filtro != "Todas (sin filtro)" and _cols_cruce(df) is None:
        return False, ("El filtro seleccionado necesita las columnas de validación del cruce "
                       "(¿Coinciden remesas?, ¿Coincide valor factura con RG?, Reconstruir).")
    if filtro in FILTROS_NOVEDAD:
        nov = mapping.get("col_novedad") or _col_novedad(df)
        if not nov:
            return False, "Este filtro necesita la columna 'Novedad remesa' (mapéala)."
    return True, ""


def parsear(df, mapping, filtro, cond_values, nit_cli_fijo="800021308",
            dig_cli_fijo="5", nom_cli_fijo="DRUMMOND LTD"):
    """Réplica fiel de ExcelLoaderWindow._parsear. Retorna lista de dicts compatibles
    con generar_xml(). `mapping` = {clave: nombre_col o None}. `cond_values` =
    {clave: valor_elegido} para las columnas-condición."""
    df = df.copy()

    if filtro != "Todas (sin filtro)":
        cc = _cols_cruce(df)
        if cc is not None:
            nov_col = mapping.get("col_novedad") or _col_novedad(df)
            nov_serie = df[nov_col] if nov_col and nov_col in df.columns else [""] * len(df)

            if filtro in FILTROS_NOVEDAD:
                c_nf_col = mapping.get("col_nf")
                if c_nf_col and c_nf_col in df.columns:
                    fila_pasa = [
                        _pasa_filtro(filtro, r, v, x, n)
                        for r, v, x, n in zip(df[cc["rem"]], df[cc["val"]], df[cc["rec"]], nov_serie)
                    ]
                    df["_fila_pasa"] = fila_pasa
                    fac_ok = df.groupby(df[c_nf_col].astype(str))["_fila_pasa"].all()
                    nf_ok = set(fac_ok[fac_ok].index)
                    df = df[df[c_nf_col].astype(str).isin(nf_ok)]
                    df = df.drop(columns=["_fila_pasa"])

                    cond_aplicables = COND_COLS if filtro == FILTRO_COND_IDEAL \
                        else [t for t in COND_COLS if t[0] == "col_comp_gen"]
                    for clave, _etq, _def in cond_aplicables:
                        cond_col = mapping.get(clave)
                        cond_val = cond_values.get(clave, "— No usar —")
                        if cond_col and cond_col in df.columns and cond_val not in ("— No usar —", "Todas"):
                            df["_cond_pasa"] = [
                                str(v).strip().upper() == cond_val.strip().upper()
                                for v in df[cond_col]
                            ]
                            o = df.groupby(df[c_nf_col].astype(str))["_cond_pasa"].all()
                            keep = set(o[o].index)
                            df = df[df[c_nf_col].astype(str).isin(keep)]
                            df = df.drop(columns=["_cond_pasa"])
                else:
                    mask = [
                        _pasa_filtro(filtro, r, v, x, n)
                        for r, v, x, n in zip(df[cc["rem"]], df[cc["val"]], df[cc["rec"]], nov_serie)
                    ]
                    df = df[mask]
            else:
                mask = [
                    _pasa_filtro(filtro, r, v, x, n)
                    for r, v, x, n in zip(df[cc["rem"]], df[cc["val"]], df[cc["rec"]], nov_serie)
                ]
                df = df[mask]

    # Filtro por Estado (omitir ya generadas)
    est_col = mapping.get("col_estado")
    if est_col and est_col in df.columns:
        c_nf_e = mapping.get("col_nf")
        if c_nf_e and c_nf_e in df.columns:
            df = df.copy()
            df["_est_vacio"] = [_es_vacio(v) for v in df[est_col]]
            o = df.groupby(df[c_nf_e].astype(str))["_est_vacio"].all()
            keep = set(o[o].index)
            df = df[df[c_nf_e].astype(str).isin(keep)]
            df = df.drop(columns=["_est_vacio"])
        else:
            df = df[[_es_vacio(v) for v in df[est_col]]]

    c_nf       = mapping.get("col_nf")
    c_cufe     = mapping.get("col_cufe")
    c_fecha    = mapping.get("col_fecha")
    c_consec   = mapping.get("col_consec")
    c_radicado = mapping.get("col_radicado")
    c_val_rem  = mapping.get("col_val_rem")
    c_val_fac  = mapping.get("col_val_fac")
    c_peso     = mapping.get("col_peso")
    c_desc_lin = mapping.get("col_desc_lin")
    c_nit_cli  = mapping.get("col_nit_cli")
    c_nom_cli  = mapping.get("col_nom_cli")

    datos_list = []
    for nf, grupo in df.groupby(df[c_nf].astype(str)):
        primera = grupo.iloc[0]
        cufe = str(primera[c_cufe]).strip()
        fecha_raw = grupo[c_fecha].iloc[0]
        if hasattr(fecha_raw, "strftime"):
            fecha = fecha_raw.strftime("%Y-%m-%d")
        else:
            fecha_str = str(fecha_raw).strip()
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
                try:
                    fecha = datetime.strptime(fecha_str, fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            else:
                fecha = fecha_str
        try:
            val_fac = _parse_valor(str(primera[c_val_fac]))
        except Exception:
            val_fac = 0.0

        remesas = []
        for _, fila in grupo.iterrows():
            _cv = fila[c_consec]
            if pd.isna(_cv):
                consec = ""
            elif isinstance(_cv, float) and _cv.is_integer():
                consec = str(int(_cv))
            else:
                consec = str(_cv).strip()
                if consec.endswith(".0") and consec[:-2].isdigit():
                    consec = consec[:-2]
            radicado = str(fila[c_radicado]).strip() if c_radicado else ""
            try:
                valor = _parse_valor(str(fila[c_val_rem]))
            except Exception:
                valor = 0.0
            peso = str(fila[c_peso]).strip() if c_peso else "1"
            desc_lin = str(fila[c_desc_lin]).strip() if c_desc_lin else "Servicio de transporte"
            if not desc_lin or desc_lin.lower() in ("nan", "none", ""):
                desc_lin = "Servicio de transporte"
            remesas.append({"consecutivo": consec, "radicado": radicado,
                            "peso": peso, "valor": valor, "descripcion_linea": desc_lin})

        nit_cli, dig_cli, nom_cli = nit_cli_fijo, dig_cli_fijo, nom_cli_fijo
        if c_nit_cli:
            _vnit = primera[c_nit_cli]
            # Limpiar el .0 que pandas añade al leer enteros como float, ANTES de
            # extraer dígitos (si no, '8000213085.0' → nit erróneo y dígito '0').
            if isinstance(_vnit, float) and _vnit.is_integer():
                _snit = str(int(_vnit))
            else:
                _snit = str(_vnit).strip()
                if _snit.endswith(".0") and _snit[:-2].isdigit():
                    _snit = _snit[:-2]
            solo = re.sub(r"\D", "", _snit)
            if len(solo) >= 2:
                nit_cli, dig_cli = solo[:-1], solo[-1]
        if c_nom_cli:
            v = str(primera[c_nom_cli]).strip()
            if v and v.lower() not in ("nan", "none", ""):
                nom_cli = v

        datos_list.append({
            "numero_factura": nf, "cufe": cufe, "fecha": fecha,
            "nit_cliente": nit_cli, "digito_cliente": dig_cli, "nombre_cliente": nom_cli,
            "valor_total": val_fac, "remesas": remesas,
        })
    return datos_list
