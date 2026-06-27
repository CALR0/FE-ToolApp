"""
Lógica de Cruzar Remesas, PORTADA TAL CUAL desde ui/cruzar_remesas.py (incluye las
últimas actualizaciones: _to_num robusto, salto de consecutivos vacíos, comparación
por unitarios del RG, passthrough genérico, filas extra). No depende de tkinter.
"""
import re
import pandas as pd

NO_USAR = "— No usar —"

CAMPOS_RG = [
    ("rg_col_nf",      "N° Factura",                  True),
    ("rg_col_val_fac", "Valor total factura",         True),
    ("rg_col_val_un",  "Valor unitario remesa (RG)",  False),
]
CAMPOS_OTRO = [
    ("otro_col_nf",          "N° Factura",                    True),
    ("otro_col_consec",      "Consecutivo / Remesa",          True),
    ("otro_col_val_un",      "Valor unitario remesa",         True),
    ("otro_col_comp_gen",    "Comp. Generador Carga RNDC",    False),
    ("otro_col_novedad",     "Novedad remesa",                False),
    ("otro_col_rem_creada",  "Remesa creada RNDC",            False),
    ("otro_col_asoc_rem_man","Comp. Asociación Rem-Man RNDC", False),
    ("otro_col_cumplido_rem","Cumplido remesa RNDC",          False),
    ("otro_col_rem_facturada","Remesa facturada",             False),
]
PASSTHROUGH_OTRO = [
    ("otro_col_comp_gen",     "Comp. Generador Carga RNDC"),
    ("otro_col_novedad",      "Novedad remesa"),
    ("otro_col_rem_creada",   "Remesa creada RNDC"),
    ("otro_col_asoc_rem_man", "Comp. Asociación Rem-Man RNDC"),
    ("otro_col_cumplido_rem", "Cumplido remesa RNDC"),
    ("otro_col_rem_facturada","Remesa facturada"),
]
FILTROS_EXPORT = [
    "Todas", "Solo Reconstruir = Sí",
    "Coinciden remesas, NO coincide valor", "Coincide valor, NO coinciden remesas",
    "NO coinciden remesas", "NO coincide valor", "Reconstruir = No (alguna no coincide)",
]
HINTS = {
    "rg_col_nf":       ["factura", "nfactura", "num_fac", "n_factura", "numero_factura"],
    "rg_col_val_fac":  ["valor_total_factura", "valor_factura", "val_fac", "total_factura"],
    "rg_col_val_un":   ["valor_unitario", "vr_unitario", "valor_unit", "unitario", "val_un"],
    "otro_col_nf":     ["factura", "nfactura", "num_fac", "n_factura", "numero_factura"],
    "otro_col_consec": ["remesa", "consecutivo", "consec"],
    "otro_col_val_un":   ["valor_unitario", "vr_unitario", "valor_remesa", "val_rem", "vunit"],
    "otro_col_comp_gen": ["comp._generador", "comp_generador", "generador_carga", "generadorcarga", "generador"],
    "otro_col_novedad":  ["novedad"],
    "otro_col_rem_creada":   ["creada"],
    "otro_col_asoc_rem_man": ["asociaci", "rem-man", "rem_man", "remesa_manifiesto"],
    "otro_col_cumplido_rem": ["cumplido"],
    "otro_col_rem_facturada":["facturada"],
}


def auto_col(clave, df):
    """Auto-detecta la columna para una clave por HINTS (o None)."""
    if df is None:
        return None
    for col in df.columns.astype(str):
        col_norm = col.lower().replace(" ", "_").replace("°", "")
        if any(h in col_norm for h in HINTS.get(clave, [])):
            return col
    return None


def _usado(col):
    return bool(col and col != NO_USAR)


def fmt_consec(v):
    if pd.isna(v):
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    s = str(v).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def to_num(v):
    """Parser monetario robusto (colombiano y anglosajón). Idéntico a _to_num."""
    if v is None:
        return 0.0
    s = str(v).strip()
    s = re.sub(r"[^\d.,\-]", "", s)
    if not s or s in ("-", ".", ","):
        return 0.0
    has_dot = "." in s
    has_comma = "," in s
    if has_dot and has_comma:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_comma:
        frac = s.split(",")[-1]
        if s.count(",") == 1 and len(frac) in (1, 2):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_dot:
        frac = s.split(".")[-1]
        if not (s.count(".") == 1 and len(frac) in (1, 2)):
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def norm_factura(v):
    """Normaliza un N° de factura para comparar (sin .0 ni espacios)."""
    if pd.isna(v):
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    s = str(v).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def validar(df_rg, df_otro, mapping):
    if df_rg is None:
        return False, "Primero carga el Excel de RG."
    if df_otro is None:
        return False, "Primero carga el otro Excel."
    for clave, etq, req in CAMPOS_RG + CAMPOS_OTRO:
        if req and not _usado(mapping.get(clave)):
            return False, f"El campo obligatorio '{etq}' no tiene columna asignada."
    return True, ""


def cruzar(df_rg, df_otro, mapping):
    """Réplica de _cruzar. Retorna dict con filas, mapa, consecutivos, passthrough, col_rg_nf."""
    c = mapping
    df_rg = df_rg.copy()
    df_rg["_nf"] = df_rg[c["rg_col_nf"]].astype(str).str.strip()
    grupos_rg = df_rg.groupby("_nf")
    df_otro = df_otro.copy()
    df_otro["_nf"] = df_otro[c["otro_col_nf"]].astype(str).str.strip()
    grupos_otro = df_otro.groupby("_nf")
    todas = sorted(set(grupos_rg.groups.keys()) | set(grupos_otro.groups.keys()))

    rg_val_un_col = c.get("rg_col_val_un")
    usa_rg_unitarios = _usado(rg_val_un_col)

    filas = []
    consecutivos_por_factura = {}
    passthrough = {clave: {} for clave, _ in PASSTHROUGH_OTRO}

    for nf in todas:
        if nf in grupos_rg.groups:
            g_rg = grupos_rg.get_group(nf)
            n_remesas_rg = len(g_rg)
            try:
                valor_factura_rg = to_num(g_rg[c["rg_col_val_fac"]].iloc[0])
            except Exception:
                valor_factura_rg = 0.0
            suma_valor_rg = 0.0
            if usa_rg_unitarios and rg_val_un_col in g_rg.columns:
                for v in g_rg[rg_val_un_col]:
                    try:
                        suma_valor_rg += to_num(v)
                    except Exception:
                        pass
        else:
            n_remesas_rg = 0
            valor_factura_rg = 0.0
            suma_valor_rg = 0.0

        if nf in grupos_otro.groups:
            g_otro = grupos_otro.get_group(nf)
            consec_fmt = g_otro[c["otro_col_consec"]].map(fmt_consec)
            mask_valid = consec_fmt.astype(str).str.strip() != ""
            g_val = g_otro[mask_valid]
            n_remesas_otro = len(g_val)
            suma_valor_otro = 0.0
            if c["otro_col_val_un"] in g_val.columns:
                for v in g_val[c["otro_col_val_un"]]:
                    try:
                        suma_valor_otro += to_num(v)
                    except Exception:
                        pass
            consecutivos_otro = consec_fmt[mask_valid].tolist()
            for clave, _ in PASSTHROUGH_OTRO:
                col = c.get(clave)
                if _usado(col) and col in g_val.columns:
                    vals = [str(v) if not pd.isna(v) else "" for v in g_val[col]]
                else:
                    vals = []
                passthrough[clave][nf] = vals
        else:
            n_remesas_otro = 0
            suma_valor_otro = 0.0
            consecutivos_otro = []
            for clave, _ in PASSTHROUGH_OTRO:
                passthrough[clave][nf] = []

        consecutivos_por_factura[nf] = consecutivos_otro

        coinciden_remesas = (n_remesas_rg == n_remesas_otro) and n_remesas_rg > 0
        suma_comparada = suma_valor_rg if usa_rg_unitarios else suma_valor_otro
        coincide_valor = abs(valor_factura_rg - suma_comparada) < 1.0 and valor_factura_rg > 0
        reconstruir = coinciden_remesas and coincide_valor

        filas.append({
            "numero_factura": nf, "remesas_rg": n_remesas_rg, "remesas_otro": n_remesas_otro,
            "coinciden_remesas": "Sí" if coinciden_remesas else "No",
            "valor_factura_rg": valor_factura_rg, "suma_valor_otro": suma_valor_otro,
            "suma_valor_rg": suma_valor_rg, "suma_comparada": suma_comparada,
            "base_comparacion": "RG" if usa_rg_unitarios else "Otro Excel",
            "coincide_valor_factura_rg": "Sí" if coincide_valor else "No",
            "reconstruir": "Sí" if reconstruir else "No",
        })

    mapa = {f["numero_factura"]: f for f in filas}
    return {"filas": filas, "mapa": mapa, "consecutivos": consecutivos_por_factura,
            "passthrough": passthrough, "col_rg_nf": c["rg_col_nf"]}


def pasa_filtro(filtro, rem, val, rec):
    r = rem == "Sí"; v = val == "Sí"; x = rec == "Sí"
    if filtro == "Todas":                                   return True
    if filtro == "Solo Reconstruir = Sí":                   return x
    if filtro == "Coinciden remesas, NO coincide valor":    return r and not v
    if filtro == "Coincide valor, NO coinciden remesas":    return v and not r
    if filtro == "NO coinciden remesas":                    return not r
    if filtro == "NO coincide valor":                       return not v
    if filtro == "Reconstruir = No (alguna no coincide)":   return not x
    return True


def exportar(df_rg, mapping, cruce, filtro="Todas"):
    """Réplica de _exportar. Retorna el DataFrame final del reporte."""
    mapa = cruce["mapa"]
    consecutivos = cruce["consecutivos"]
    passthrough = cruce["passthrough"]
    col_rg_nf = cruce["col_rg_nf"]

    df = df_rg.copy()
    if "consecutivo_remesa" in df.columns:
        df = df.drop(columns=["consecutivo_remesa"])
    nf_serie = df[col_rg_nf].astype(str).str.strip()
    pos_serie = nf_serie.groupby(nf_serie).cumcount()

    def _consec_en_pos(nf, pos):
        lst = consecutivos.get(nf, [])
        return lst[pos] if pos < len(lst) else ""

    def _pass_en_pos(clave, nf, pos):
        lst = passthrough.get(clave, {}).get(nf, [])
        return lst[pos] if pos < len(lst) else ""

    df["Consecutivo Remesa (Otro Excel)"] = [
        _consec_en_pos(nf, pos) for nf, pos in zip(nf_serie, pos_serie)]
    passthrough_activas = []
    for clave, encabezado in PASSTHROUGH_OTRO:
        if _usado(mapping.get(clave)):
            df[encabezado] = [_pass_en_pos(clave, nf, pos) for nf, pos in zip(nf_serie, pos_serie)]
            passthrough_activas.append((clave, encabezado))
    df["¿Coinciden remesas?"] = nf_serie.map(lambda nf: mapa.get(nf, {}).get("coinciden_remesas", "No"))
    df["¿Coincide valor factura con RG?"] = nf_serie.map(lambda nf: mapa.get(nf, {}).get("coincide_valor_factura_rg", "No"))
    df["Reconstruir"] = nf_serie.map(lambda nf: mapa.get(nf, {}).get("reconstruir", "No"))

    fac_orden = {nf: i for i, nf in enumerate(dict.fromkeys(nf_serie))}
    n_rg_por_fac = nf_serie.value_counts().to_dict()
    df["_fo"] = nf_serie.map(lambda nf: fac_orden.get(nf, len(fac_orden))).values
    df["_pos"] = pos_serie.values

    extra = []
    for nf, lst in consecutivos.items():
        n_otro = len(lst)
        n_rg = int(n_rg_por_fac.get(nf, 0))
        for pos in range(n_rg, n_otro):
            rec = {col: "" for col in df.columns}
            rec[col_rg_nf] = nf
            rec["Consecutivo Remesa (Otro Excel)"] = _consec_en_pos(nf, pos)
            for clave, encabezado in passthrough_activas:
                rec[encabezado] = _pass_en_pos(clave, nf, pos)
            info = mapa.get(nf, {})
            rec["¿Coinciden remesas?"] = info.get("coinciden_remesas", "No")
            rec["¿Coincide valor factura con RG?"] = info.get("coincide_valor_factura_rg", "No")
            rec["Reconstruir"] = info.get("reconstruir", "No")
            rec["_fo"] = fac_orden.get(nf, len(fac_orden))
            rec["_pos"] = pos
            extra.append(rec)
    if extra:
        df = pd.concat([df, pd.DataFrame(extra)], ignore_index=True)
    df = df.sort_values(["_fo", "_pos"], kind="stable").drop(columns=["_fo", "_pos"]).reset_index(drop=True)

    if filtro != "Todas":
        mask = [pasa_filtro(filtro, r, v, x) for r, v, x in zip(
            df["¿Coinciden remesas?"], df["¿Coincide valor factura con RG?"], df["Reconstruir"])]
        df = df[mask].reset_index(drop=True)
    return df
