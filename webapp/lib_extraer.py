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

    # Extracción de líneas robusta para PDFs de VARIAS PÁGINAS. El bloque de ítems
    # puede repetirse por página (el header "REFERENCIA…" reaparece) y/o traer un
    # subtotal por página. Se procesan TODOS los bloques: cada header va hasta su
    # footer (Observaciones/SUBTOTAL) o hasta el siguiente header, lo que llegue
    # primero. Así no se pierden las remesas de las páginas 2+.
    header_re = re.compile(
        r"REFERENCIA\s+DESCRIPCION\s+CANTIDAD\s+UND\s+VR\.\s*UNITARIO\s+VR\.\s*TOTAL",
        re.IGNORECASE)
    footer_re = re.compile(r"\bObservaciones\b|\bSUBTOTAL\b", re.IGNORECASE)

    def _parsear_linea(linea):
        linea = linea.strip()
        if not linea:
            return None
        m_lin = re.match(r"(\S+)\s+(.+?)\s+([\d.,]+)\s+\S+\s+([\d.,]+)\s+([\d.,]+)\s*$", linea)
        if m_lin:
            ref, desc, cant_s, vru_s, vrt_s = m_lin.group(1, 2, 3, 4, 5)
        else:
            m_lin = re.match(r"(\S+)\s+(.+?)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s*$", linea)
            if not m_lin:
                return None
            ref, desc, cant_s, vru_s, vrt_s = m_lin.groups()
        try:
            return {"referencia": ref.strip(), "descripcion": desc.strip(),
                    "cantidad": _parse_valor(cant_s), "vr_unitario": _parse_valor(vru_s),
                    "vr_total": _parse_valor(vrt_s)}
        except Exception:
            return None

    lineas = []
    headers = list(header_re.finditer(texto))
    for idx, hm in enumerate(headers):
        inicio = hm.end()
        fin = len(texto)
        fm = footer_re.search(texto, inicio)
        if fm:
            fin = min(fin, fm.start())
        if idx + 1 < len(headers):
            fin = min(fin, headers[idx + 1].start())
        for linea in texto[inicio:fin].split("\n"):
            item = _parsear_linea(linea)
            if item:
                lineas.append(item)

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
