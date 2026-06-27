"""
Reconstruir XML para la web. Reutiliza core.xml_transformer.reconstruir_factura
(que es file-based) mediante archivos temporales, y porta el pre/post-procesamiento
de ui/reconstruir_xml.py operando sobre strings (no depende de tkinter).
"""
import io
import re
import sys
import tempfile
from pathlib import Path

from services.rndc_service import consultar_radicado_remesa

try:
    from core.xml_transformer import reconstruir_factura
    RECONSTRUIR_OK = True
    _RECONSTRUIR_ERR = ""
except Exception:
    import traceback as _tb
    RECONSTRUIR_OK = False
    _RECONSTRUIR_ERR = _tb.format_exc()
    def reconstruir_factura(*a, **kw):  # noqa
        return False


def leer_cabecera_str(contenido):
    """(numero_factura, nombre_cliente) — réplica de _leer_cabecera_xml sobre string."""
    try:
        m_cdata = re.search(r"<!\[CDATA\[(.*?)\]\]>", contenido, re.DOTALL)
        inv = m_cdata.group(1) if m_cdata else contenido
        m_num = re.search(r"<cbc:ID>([^<]+)</cbc:ID>", inv)
        nf = m_num.group(1).strip() if m_num else "—"
        nombre_cli = "—"
        cs = inv.find("<cac:AccountingCustomerParty")
        ce = inv.find("</cac:AccountingCustomerParty>", cs)
        if cs != -1:
            bloque = inv[cs:ce]
            mc = re.search(r"<cbc:RegistrationName>([^<]+)</cbc:RegistrationName>", bloque)
            if not mc:
                mc = re.search(r"<cac:PartyName>\s*<cbc:Name>([^<]+)</cbc:Name>", bloque)
            nombre_cli = mc.group(1).strip() if mc else "—"
        return nf, nombre_cli
    except Exception:
        return "—", "—"


def leer_remesas_str(contenido):
    """Lee las remesas del XML: lista de {consecutivo, radicado, peso}.
    Réplica de _leer_remesas_xml sobre string."""
    try:
        m = re.search(r"<!\[CDATA\[(.*?)\]\]>", contenido, re.DOTALL)
        inv = m.group(1) if m else contenido
        inv = re.sub(
            r'<cac:InvoiceLine\s+xmlns="[^"]*"(?:\s+xmlns:[^=]+="[^"]*")*\s*>',
            "<cac:InvoiceLine>", inv)
        lineas = re.findall(r"<cac:InvoiceLine.*?</cac:InvoiceLine>", inv, re.DOTALL)
        remesas = []
        for linea in lineas:
            def _prop(name):
                m2 = re.search(
                    rf"<cac:AdditionalItemProperty>\s*<cbc:Name>\s*{re.escape(name)}\s*</cbc:Name>\s*"
                    rf"<cbc:Value>([^<]*)</cbc:Value>", linea)
                return m2.group(1).strip() if m2 else ""
            m_peso = re.search(
                r"<cac:AdditionalItemProperty>\s*<cbc:Name>\s*03\s*</cbc:Name>\s*"
                r"<cbc:Value>[^<]*</cbc:Value>\s*<cbc:ValueQuantity[^>]*>([^<]+)</cbc:ValueQuantity>",
                linea)
            peso = m_peso.group(1).strip() if m_peso else ""
            if not peso:
                m_iq = re.search(r"<cbc:InvoicedQuantity[^>]*>([^<]+)</cbc:InvoicedQuantity>", linea)
                peso = m_iq.group(1).strip() if m_iq else ""
            remesas.append({"consecutivo": _prop("02"), "radicado": _prop("01"), "peso": peso})
        return remesas
    except Exception:
        return []


def preprocesar_str(contenido):
    """Limpia ShareholderParty y normaliza el ancla. Réplica de _preprocesar_xml."""
    m_cdata = re.search(r"(<!\[CDATA\[)(.*?)(\]\]>)", contenido, re.DOTALL)
    if not m_cdata:
        return contenido
    inv = m_cdata.group(2)
    inv = re.sub(r"<cac:ShareholderParty>.*?</cac:ShareholderParty>", "", inv, flags=re.DOTALL)
    inv = re.sub(
        r"<cac:CorporateRegistrationScheme>\s*<cbc:ID>41</cbc:ID>\s*<cbc:Name\s*/>\s*</cac:CorporateRegistrationScheme>",
        "<cac:CorporateRegistrationScheme><cbc:ID>41</cbc:ID><cbc:Name /></cac:CorporateRegistrationScheme>",
        inv)
    return contenido[:m_cdata.start(2)] + inv + contenido[m_cdata.end(2):]


def actualizar_radicados_str(contenido, perfil, prefijo_remesa=False, peso_fijo=None):
    """Consulta el RNDC por cada consecutivo y sobreescribe radicado (01) y peso.
    Réplica de _actualizar_radicados_en_xml operando sobre string.
    Retorna (contenido_nuevo, resultados)."""
    m_cdata = re.search(r"(<!\[CDATA\[)(.*?)(\]\]>)", contenido, re.DOTALL)
    inv = m_cdata.group(2) if m_cdata else contenido
    inv_norm = re.sub(
        r'<cac:InvoiceLine\s+xmlns="[^"]*"(?:\s+xmlns:[^=]+="[^"]*")*\s*>',
        "<cac:InvoiceLine>", inv)
    lineas = re.findall(r"<cac:InvoiceLine.*?</cac:InvoiceLine>", inv_norm, re.DOTALL)

    def _get_prop(linea, name):
        m = re.search(
            rf"<cac:AdditionalItemProperty>\s*<cbc:Name>\s*{re.escape(name)}\s*</cbc:Name>\s*"
            rf"<cbc:Value>([^<]*)</cbc:Value>", linea)
        return m.group(1).strip() if m else ""

    def _set_prop(linea, name, valor):
        patron = (rf"(<cac:AdditionalItemProperty>\s*<cbc:Name>\s*{re.escape(name)}\s*</cbc:Name>\s*"
                  rf"<cbc:Value>)[^<]*(</cbc:Value>)")
        return re.sub(patron, rf"\g<1>{valor}\g<2>", linea)

    def _set_peso(linea, peso):
        pat = (r"(<cac:AdditionalItemProperty>\s*<cbc:Name>\s*03\s*</cbc:Name>\s*"
               r"<cbc:Value>[^<]*</cbc:Value>\s*<cbc:ValueQuantity[^>]*>)[^<]*(</cbc:ValueQuantity>)")
        nueva, n = re.subn(pat, rf"\g<1>{peso}\g<2>", linea)
        if n:
            return nueva
        return re.sub(r"(<cbc:InvoicedQuantity[^>]*>)[^<]*(</cbc:InvoicedQuantity>)",
                      rf"\g<1>{peso}\g<2>", linea)

    resultados = []
    inv_actualizado = inv_norm
    for linea_orig in lineas:
        consec_raw = _get_prop(linea_orig, "02").strip()
        if not consec_raw:
            continue
        consec_rndc = ("0" + consec_raw) if prefijo_remesa else consec_raw
        try:
            ok, res = consultar_radicado_remesa(consec_rndc, perfil)
        except Exception:
            ok, res = False, {}
        radicado = res.get("radicado", "") if ok else ""
        peso = peso_fijo if peso_fijo is not None else (res.get("peso", "") if ok else "")
        if not radicado and peso == "":
            resultados.append({"consecutivo": consec_raw, "radicado": "", "peso": ""})
            continue
        linea_nueva = linea_orig
        if radicado:
            linea_nueva = _set_prop(linea_nueva, "01", radicado)
        if peso != "":
            linea_nueva = _set_peso(linea_nueva, peso)
        inv_actualizado = inv_actualizado.replace(linea_orig, linea_nueva, 1)
        resultados.append({"consecutivo": consec_raw, "radicado": radicado, "peso": peso})

    if m_cdata:
        contenido_nuevo = contenido[:m_cdata.start(2)] + inv_actualizado + contenido[m_cdata.end(2):]
    else:
        contenido_nuevo = inv_actualizado
    return contenido_nuevo, resultados


def reconstruir_uno(contenido, nombre, perfil, peso_fijo=None):
    """Orquesta la reconstrucción de UN XML (string). Usa archivos temporales para
    llamar a reconstruir_factura. Retorna (ok, contenido_final, resultados, error)."""
    if not RECONSTRUIR_OK:
        return False, "", [], "No se pudo importar xml_transformer:\n" + _RECONSTRUIR_ERR
    pre = preprocesar_str(contenido)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        in_path = td / (nombre or "factura.xml")
        in_path.write_text(pre, encoding="utf-8")
        out_dir = td / "salida"
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            exito = reconstruir_factura(
                ruta_archivo=in_path, carpeta_salida=out_dir,
                nit_sp=perfil.get("nit_socio", ""), nombre_sp=perfil.get("nombre_socio", ""),
                nit_ut=perfil.get("nit_ut", "901101271"),
                nombre_ut=perfil.get("nombre_ut", "UNION TEMPORAL AMERICAN LOGISTIC UT"),
                email_customer=perfil.get("email_customer", "facturacion@drummondltd.com"),
                telefono_customer=perfil.get("telefono_customer", "3135398327"),
                email_from_sp=perfil.get("email_from", "emisionfe@sanchezpolo.com"),
                nit_customer=perfil.get("nit_customer", "800021308"),
                prefijo_remesa=perfil.get("prefijo_remesa", False))
        except Exception:
            import traceback as _tb
            sys.stdout = old
            return False, "", [], _tb.format_exc()
        finally:
            sys.stdout = old
        printed = buf.getvalue().strip()
        if not exito:
            return False, "", [], printed or "reconstruir_factura devolvió False"
        outs = list(out_dir.glob("*.xml"))
        if not outs:
            return False, "", [], "No se generó archivo de salida"
        out_content = outs[0].read_text(encoding="utf-8")
        out_content, resultados = actualizar_radicados_str(
            out_content, perfil, perfil.get("prefijo_remesa", False), peso_fijo)
        return True, out_content, resultados, ""
