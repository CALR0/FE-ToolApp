"""
Extraer Datos RG para la web. Porta la extracción de PDFs de ui/extraer_datos_rg.py
(misma lógica de regex, expansión de líneas y reparto de VR.TOTAL), operando sobre
bytes (los archivos subidos). No depende de tkinter.

Eficiencia: procesa los PDFs en paralelo con ProcessPoolExecutor cuando es posible,
y cae a procesamiento secuencial si el entorno no lo permite (ej. algunos despliegues
web). El worker está a nivel de módulo para ser picklable (arranque 'spawn').
"""
import io
import re

from core.xml_generator import _parse_valor

MAX_CANTIDAD_EXPANSION = 100

COLUMNAS_EXPORT = [
    "numero_factura", "fecha_generacion", "cufe", "nit", "nombre_cliente",
    "descripcion", "consecutivo_remesa", "radicado",
    "valor_unitario", "valor_total_factura", "cantidad_remesas_rg",
]


def _extraer_pdf_bytes(contenido):
    """Extrae los datos de un PDF (bytes). Réplica de _extraer_pdf sobre BytesIO."""
    import pdfplumber
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        texto = "\n".join(p.extract_text() or "" for p in pdf.pages)

    m = re.search(r"No\.\s*(\d+)[-](\d+)", texto)
    numero_factura = (m.group(1) + m.group(2)) if m else ""

    m = re.search(
        r"FECHA\s*Y\s*HORA\s*DE\s*GENERACI[OÓ]N[:\s]*(\d{1,2})[./](\d{1,2})[./](\d{4})",
        texto, re.IGNORECASE)
    fecha_generacion = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""

    m = re.search(r"CUFE[:\s]*([a-f0-9]{80,})", texto, re.IGNORECASE)
    cufe = m.group(1).strip() if m else ""

    m = re.search(r"CLIENTE\s*:.*?NIT:\s*([\d.\-]+)", texto, re.IGNORECASE | re.DOTALL)
    if not m:
        m = re.search(r"NOMBRE:.*?NIT:\s*([\d.\-]+)", texto, re.IGNORECASE | re.DOTALL)
    nit_cliente = m.group(1).strip() if m else ""

    m = re.search(r"CLIENTE\s*:\s*(.+)", texto, re.IGNORECASE)
    if not m:
        m = re.search(r"NOMBRE:\s*(.+)", texto, re.IGNORECASE)
    nombre_cliente = ""
    if m:
        nombre_cliente = re.split(r"\s{2,}|ORDEN\s+DE\s+COMPRA|NIT:", m.group(1),
                                  maxsplit=1, flags=re.IGNORECASE)[0].strip()

    m = re.search(r"SUBTOTAL\s+([\d.,]+)", texto, re.IGNORECASE)
    if not m:
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
            m_lin = re.match(r"(\S+)\s+(.+?)\s+([\d.,]+)\s+\S+\s+([\d.,]+)\s+([\d.,]+)\s*$", linea)
            if not m_lin:
                m_lin = re.match(r"(\S+)\s+(.+?)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s*$", linea)
                if not m_lin:
                    continue
                ref, desc, cant_s, vru_s, vrt_s = m_lin.groups()
            else:
                ref, desc, cant_s, vru_s, vrt_s = m_lin.group(1, 2, 3, 4, 5)
            try:
                cantidad = _parse_valor(cant_s)
                vr_unitario = _parse_valor(vru_s)
                vr_total = _parse_valor(vrt_s)
            except Exception:
                continue
            lineas.append({"referencia": ref.strip(), "descripcion": desc.strip(),
                           "cantidad": cantidad, "vr_unitario": vr_unitario, "vr_total": vr_total})

    return {"numero_factura": numero_factura, "fecha_generacion": fecha_generacion,
            "cufe": cufe, "nit_cliente": nit_cliente, "nombre_cliente": nombre_cliente,
            "total_factura": total_factura, "lineas": lineas}


def _expandir_lineas(datos, usar_ref_como_consec=False):
    """Réplica de _expandir_lineas (expansión por conteo y reparto de VR.TOTAL)."""
    filas = []
    for lin in datos["lineas"]:
        cant = lin["cantidad"]
        vr_unit_orig = lin["vr_unitario"]
        vr_total_lin = lin.get("vr_total", vr_unit_orig)
        consec = lin["referencia"] if usar_ref_como_consec else ""
        es_entero = abs(cant - round(cant)) < 1e-9
        es_conteo = es_entero and (1 <= cant <= MAX_CANTIDAD_EXPANSION)
        if es_conteo:
            n_remesas = int(round(cant))
            vr_unit_ind = round(vr_total_lin / n_remesas, 2) if n_remesas > 1 else vr_total_lin
        else:
            n_remesas = 1
            vr_unit_ind = vr_total_lin
        for _ in range(n_remesas):
            filas.append({
                "numero_factura": datos["numero_factura"], "fecha_generacion": datos["fecha_generacion"],
                "cufe": datos["cufe"], "nit": datos.get("nit_cliente", ""),
                "nombre_cliente": datos.get("nombre_cliente", ""), "descripcion": lin["descripcion"],
                "consecutivo_remesa": consec, "radicado": "", "valor_unitario": vr_unit_ind,
                "valor_total_factura": datos["total_factura"], "cantidad_remesas_rg": n_remesas})
    total_remesas = len(filas)
    for f in filas:
        f["cantidad_remesas_rg"] = total_remesas
    return filas


def _procesar_pdf_worker(args):
    """Worker picklable (a nivel de módulo). args = (nombre, contenido_bytes, usar_ref)."""
    nombre, contenido, usar_ref = args
    try:
        datos = _extraer_pdf_bytes(contenido)
        filas = _expandir_lineas(datos, usar_ref)
        return {"nombre": nombre, "nf": datos["numero_factura"], "fecha": datos["fecha_generacion"],
                "nlin": len(datos["lineas"]), "total": datos["total_factura"],
                "filas": filas, "error": ""}
    except Exception as e:
        return {"nombre": nombre, "nf": "", "fecha": "", "nlin": 0, "total": 0.0,
                "filas": [], "error": str(e)}


def procesar_pdfs(files, usar_ref, on_progress=None):
    """Procesa una lista de (nombre, bytes). Intenta ProcessPool; si no es posible,
    procesa secuencialmente. Retorna la lista de resultados en el ORDEN original.
    `on_progress(hechos, total)` se llama tras cada PDF (opcional)."""
    args = [(nombre, b, usar_ref) for nombre, b in files]
    total = len(args)
    resultados = [None] * total
    hechos = 0

    usar_pool = total > 1
    if usar_pool:
        try:
            import concurrent.futures as cf
            import os
            max_workers = min(os.cpu_count() or 4, 8)
            with cf.ProcessPoolExecutor(max_workers=max_workers) as ex:
                futs = {ex.submit(_procesar_pdf_worker, a): i for i, a in enumerate(args)}
                for fut in cf.as_completed(futs):
                    i = futs[fut]
                    resultados[i] = fut.result()
                    hechos += 1
                    if on_progress:
                        on_progress(hechos, total)
        except Exception:
            usar_pool = False   # cae a secuencial abajo para los que falten

    if not usar_pool or any(r is None for r in resultados):
        for i, a in enumerate(args):
            if resultados[i] is None:
                resultados[i] = _procesar_pdf_worker(a)
                hechos += 1
                if on_progress:
                    on_progress(min(hechos, total), total)
    return resultados
