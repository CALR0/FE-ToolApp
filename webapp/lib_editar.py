"""
Lógica de Editar XML, PORTADA TAL CUAL desde ui/editar_xml.py (parseo y guardado
por regex sobre el string del XML). Reutiliza core.xml_generator (_fmt_valor,
_parse_valor) sin tocarlo. No depende de tkinter.

- parse_xml(contenido) → dict con datos generales + lista de remesas.
- guardar_xml(contenido, orig, nuevos, remesas) → (nuevo_contenido, avisos).
"""
import re
from datetime import datetime, timedelta

from core.xml_generator import _fmt_valor, _parse_valor


# ── Helpers de parseo (idénticos a EditarXMLModule) ──────────────────────────
def _normalizar_valor(texto):
    try:
        return _fmt_valor(_parse_valor(texto))
    except Exception:
        return texto


def _prop(linea, name):
    m = re.search(
        rf"<cac:AdditionalItemProperty>\s*<cbc:Name>\s*{re.escape(name)}\s*</cbc:Name>\s*"
        rf"<cbc:Value>([^<]*)</cbc:Value>",
        linea)
    return m.group(1) if m else ""


def _invoiced_qty(linea):
    m = re.search(
        r"<cac:AdditionalItemProperty>\s*<cbc:Name>\s*03\s*</cbc:Name>\s*"
        r"<cbc:Value>[^<]*</cbc:Value>\s*"
        r"<cbc:ValueQuantity[^>]*>([^<]+)</cbc:ValueQuantity>",
        linea)
    if m and m.group(1).strip():
        return m.group(1).strip()
    m = re.search(r"<cbc:InvoicedQuantity[^>]*>([^<]+)</cbc:InvoicedQuantity>", linea)
    return m.group(1).strip() if m else ""


def _descripcion(linea):
    m = re.search(r"<cac:Item>\s*<cbc:Description>([^<]*)</cbc:Description>", linea)
    return m.group(1).strip() if m else ""


def _to_iso(fecha_str):
    s = fecha_str.strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def parse_xml(contenido):
    """Réplica de EditarXMLModule._parsear. Retorna un dict con los datos."""
    m = re.search(r"<!\[CDATA\[(.*?)\]\]>", contenido, re.DOTALL)
    inv = m.group(1) if m else contenido
    inv_norm = re.sub(
        r'<cac:InvoiceLine\s+xmlns="[^"]*"(?:\s+xmlns:[^=]+="[^"]*")*\s*>',
        "<cac:InvoiceLine>", inv)

    lineas = re.findall(r"<cac:InvoiceLine.*?</cac:InvoiceLine>", inv_norm, re.DOTALL)
    remesas = []
    for i, linea in enumerate(lineas):
        remesas.append({
            "idx": i,
            "radicado":    _prop(linea, "01"),
            "consecutivo": _prop(linea, "02"),
            "valor":       _normalizar_valor(_prop(linea, "03")),
            "peso":        _invoiced_qty(linea),
            "descripcion": _descripcion(linea),
            "_nuevo": False,
        })

    m_num  = re.search(r"<cbc:ID>([^<]+)</cbc:ID>", inv_norm)
    m_cufe = re.search(r"<cbc:UUID[^>]*>([^<]+)</cbc:UUID>", contenido)
    numero = m_num.group(1).strip()  if m_num  else ""
    cufe   = m_cufe.group(1).strip() if m_cufe else ""

    m_fecha = re.search(r"<cbc:IssueDate>(\d{2,4}[-/]\d{2}[-/]\d{2,4})</cbc:IssueDate>", inv_norm)
    fecha_raw = m_fecha.group(1).strip() if m_fecha else ""
    fecha_iso = _to_iso(fecha_raw)

    cust_start = inv_norm.find("<cac:AccountingCustomerParty")
    cust_end   = inv_norm.find("</cac:AccountingCustomerParty>", cust_start)
    nombre_cli = ""
    nit_cli, dig_cli = "", ""
    if cust_start != -1:
        bloque = inv_norm[cust_start:cust_end]
        mc = re.search(r"<cbc:RegistrationName>([^<]+)</cbc:RegistrationName>", bloque)
        if not mc:
            mc = re.search(r"<cac:PartyName>\s*<cbc:Name>([^<]+)</cbc:Name>", bloque)
        nombre_cli = mc.group(1).strip() if mc else ""
        m_nit = re.search(
            r'<cac:PartyIdentification>\s*<cbc:ID[^>]*schemeID="([^"]*)"[^>]*>([^<]+)</cbc:ID>',
            bloque)
        if not m_nit:
            m_nit = re.search(
                r'<cac:PartyTaxScheme>.*?<cbc:CompanyID[^>]*schemeID="([^"]*)"[^>]*>([^<]+)</cbc:CompanyID>',
                bloque, re.DOTALL)
        if not m_nit:
            m_nit = re.search(
                r'<cac:PartyLegalEntity>.*?<cbc:CompanyID[^>]*schemeID="([^"]*)"[^>]*>([^<]+)</cbc:CompanyID>',
                bloque, re.DOTALL)
        if m_nit:
            dig_cli = m_nit.group(1).strip()
            nit_cli = m_nit.group(2).strip()

    m_total = re.search(r"<cbc:PayableAmount[^>]*>([^<]+)</cbc:PayableAmount>", inv_norm)
    total_raw = m_total.group(1).strip() if m_total else ""
    total_fmt = _normalizar_valor(total_raw)

    return {
        "numero": numero, "cufe": cufe, "cliente": nombre_cli,
        "fecha": fecha_raw, "fecha_iso": fecha_iso,
        "total": total_fmt, "total_orig": total_raw,
        "nit": nit_cli, "dig": dig_cli,
        "remesas": remesas,
    }


# ── Helpers de transformación (idénticos a EditarXMLModule) ──────────────────
def _set_descripcion(linea, valor):
    return re.sub(r"(<cac:Item>\s*<cbc:Description>)[^<]*(</cbc:Description>)",
                  rf"\g<1>{valor}\g<2>", linea)


def _set_prop(linea, name, valor):
    patron = (rf"(<cac:AdditionalItemProperty>\s*<cbc:Name>\s*{re.escape(name)}\s*</cbc:Name>\s*"
              rf"<cbc:Value>)[^<]*(</cbc:Value>)")
    return re.sub(patron, rf"\g<1>{valor}\g<2>", linea)


def _set_prop_03(linea, valor, peso):
    patron = (r"(<cac:AdditionalItemProperty>\s*<cbc:Name>\s*03\s*</cbc:Name>\s*"
              r"<cbc:Value>)[^<]*(</cbc:Value>\s*<cbc:ValueQuantity[^>]*>)[^<]*(</cbc:ValueQuantity>)")
    return re.sub(patron, rf"\g<1>{valor}\g<2>{peso}\g<3>", linea)


def _set_invoiced_qty(linea, peso):
    return re.sub(r"(<cbc:InvoicedQuantity[^>]*>)[^<]*(</cbc:InvoicedQuantity>)",
                  rf"\g<1>{peso}\2", linea)


def guardar_xml(contenido, orig, nuevos, remesas):
    """Réplica de EditarXMLModule._guardar. Retorna (nuevo_contenido, avisos).
    `orig` = valores originales del XML; `nuevos` = valores editados;
    `remesas` = lista en orden con consecutivo/radicado/valor/peso/descripcion/_nuevo."""
    avisos = []
    m_cdata = re.search(r"(<!\[CDATA\[)(.*?)(\]\]>)", contenido, re.DOTALL)
    if not m_cdata:
        raise ValueError("No se encontró bloque CDATA en el XML.")

    inv = m_cdata.group(2)
    lineas_orig = re.findall(r"<cac:InvoiceLine.*?</cac:InvoiceLine>", inv, re.DOTALL)
    _plantilla_line = lineas_orig[0] if lineas_orig else None

    lineas_resultado = []
    for pos, r in enumerate(remesas):
        try:
            _val_fmt = _fmt_valor(_parse_valor(r["valor"]))
        except Exception:
            _val_fmt = r["valor"]
        if r.get("_nuevo") and _plantilla_line:
            linea = re.sub(r'(<cbc:ID[^>]*>)\d+(</cbc:ID>)', rf'\g<1>{pos + 1}\g<2>',
                           _plantilla_line, count=1)
            linea = _set_prop(linea, "01", r["radicado"])
            linea = _set_prop(linea, "02", r["consecutivo"])
            linea = _set_prop_03(linea, _val_fmt or "0", r["peso"] or "0")
            linea = _set_invoiced_qty(linea, r["peso"] or "0")
            linea = _set_descripcion(linea, r.get("descripcion", ""))
        elif pos < len(lineas_orig):
            linea = lineas_orig[pos]
            linea = re.sub(r'(<cbc:ID[^>]*>)\d+(</cbc:ID>)', rf'\g<1>{pos + 1}\g<2>',
                           linea, count=1)
            linea = _set_prop(linea, "01", r["radicado"])
            linea = _set_prop(linea, "02", r["consecutivo"])
            linea = _set_prop_03(linea, _val_fmt, r["peso"])
            linea = _set_invoiced_qty(linea, r["peso"])
            linea = _set_descripcion(linea, r.get("descripcion", ""))
        else:
            continue
        lineas_resultado.append(linea)

    if lineas_orig:
        primer_inicio = inv.find(lineas_orig[0])
        ultimo_fin    = inv.rfind(lineas_orig[-1]) + len(lineas_orig[-1])
        inv_nuevo = inv[:primer_inicio] + "\n".join(lineas_resultado) + inv[ultimo_fin:]
    else:
        inv_nuevo = inv

    inv_nuevo = re.sub(r'(<cbc:LineCountNumeric>)\d+(</cbc:LineCountNumeric>)',
                       rf'\g<1>{len(lineas_resultado)}\g<2>', inv_nuevo)

    contenido_nuevo = contenido[:m_cdata.start(2)] + inv_nuevo + contenido[m_cdata.end(2):]

    # N° Factura
    num_nuevo = nuevos.get("numero", "").strip()
    if num_nuevo and orig.get("numero") and num_nuevo != orig["numero"]:
        contenido_nuevo = re.sub(rf"(<cbc:ID>){re.escape(orig['numero'])}(</cbc:ID>)",
                                 rf"\g<1>{num_nuevo}\g<2>", contenido_nuevo)
        contenido_nuevo = re.sub(
            rf"(<cbc:ParentDocumentID>){re.escape(orig['numero'])}(</cbc:ParentDocumentID>)",
            rf"\g<1>{num_nuevo}\g<2>", contenido_nuevo)

    # CUFE
    cufe_nuevo = nuevos.get("cufe", "").strip()
    if cufe_nuevo and orig.get("cufe") and cufe_nuevo != orig["cufe"]:
        contenido_nuevo = re.sub(rf"(<cbc:UUID[^>]*>){re.escape(orig['cufe'])}(</cbc:UUID>)",
                                 rf"\g<1>{cufe_nuevo}\g<2>", contenido_nuevo)
        contenido_nuevo = contenido_nuevo.replace(
            f"documentkey={orig['cufe']}", f"documentkey={cufe_nuevo}")

    # Valor total factura
    total_nuevo_raw = nuevos.get("total", "").strip()
    if total_nuevo_raw and orig.get("total_orig"):
        try:
            total_nuevo = _fmt_valor(_parse_valor(total_nuevo_raw))
            retencion_nueva = _fmt_valor(round(_parse_valor(total_nuevo_raw) * 0.01, 2))
            for tag in ("LineExtensionAmount", "TaxInclusiveAmount", "PayableAmount"):
                contenido_nuevo = re.sub(
                    rf'(<cbc:{tag}[^>]*>){re.escape(orig["total_orig"])}(</cbc:{tag}>)',
                    rf'\g<1>{total_nuevo}\g<2>', contenido_nuevo)
            contenido_nuevo = re.sub(
                rf'(<cbc:TaxableAmount[^>]*>){re.escape(orig["total_orig"])}(</cbc:TaxableAmount>)',
                rf'\g<1>{total_nuevo}\g<2>', contenido_nuevo)
            contenido_nuevo = re.sub(
                r'(<cbc:TaxAmount[^>]*>)[^<]+(</cbc:TaxAmount>)',
                rf'\g<1>{retencion_nueva}\g<2>', contenido_nuevo)
        except Exception as e:
            avisos.append(f"No se pudo parsear el valor total '{total_nuevo_raw}': {e}")

    # Fecha de generación + Vencimiento (+30 días)
    fecha_nueva = nuevos.get("fecha", "").strip()
    fecha_orig_xml = orig.get("fecha", "")
    fecha_orig_iso = orig.get("fecha_iso", "")
    if fecha_nueva and fecha_orig_xml and fecha_nueva != fecha_orig_iso and fecha_nueva != fecha_orig_xml:
        try:
            dt_nueva = datetime.strptime(_to_iso(fecha_nueva), "%Y-%m-%d")
            venc_nueva = (dt_nueva + timedelta(days=30)).strftime("%Y-%m-%d")
            contenido_nuevo = re.sub(
                rf"(<cbc:IssueDate>){re.escape(fecha_orig_xml)}(</cbc:IssueDate>)",
                rf"\g<1>{fecha_nueva}\g<2>", contenido_nuevo)
            contenido_nuevo = re.sub(
                rf"(<xades:SigningTime>){re.escape(fecha_orig_iso)}(T)",
                rf"\g<1>{fecha_nueva}\g<2>", contenido_nuevo)
            contenido_nuevo = re.sub(
                rf"(<cbc:ValidationDate>){re.escape(fecha_orig_iso)}(</cbc:ValidationDate>)",
                rf"\g<1>{fecha_nueva}\g<2>", contenido_nuevo)
            contenido_nuevo = re.sub(r"(<cbc:DueDate>)[\d/-]+(</cbc:DueDate>)",
                                     rf"\g<1>{venc_nueva}\g<2>", contenido_nuevo)
            contenido_nuevo = re.sub(r"(<cbc:PaymentDueDate>)[\d/-]+(</cbc:PaymentDueDate>)",
                                     rf"\g<1>{venc_nueva}\g<2>", contenido_nuevo)
        except ValueError:
            avisos.append(f"La fecha '{fecha_nueva}' no tiene formato válido; no se actualizó.")

    # Nombre cliente
    cliente_nuevo = nuevos.get("cliente", "").strip()
    if cliente_nuevo and orig.get("cliente") and cliente_nuevo != orig["cliente"]:
        co = orig["cliente"]
        cust_start_c = contenido_nuevo.find("<cac:AccountingCustomerParty")
        cust_end_c   = contenido_nuevo.find("</cac:AccountingCustomerParty>", cust_start_c)
        if cust_start_c != -1 and cust_end_c != -1:
            cust_end_c += len("</cac:AccountingCustomerParty>")
            bloque_c = contenido_nuevo[cust_start_c:cust_end_c]
            bloque_c = bloque_c.replace(f"<cbc:Name>{co}</cbc:Name>",
                                        f"<cbc:Name>{cliente_nuevo}</cbc:Name>")
            bloque_c = bloque_c.replace(f"<cbc:RegistrationName>{co}</cbc:RegistrationName>",
                                        f"<cbc:RegistrationName>{cliente_nuevo}</cbc:RegistrationName>")
            contenido_nuevo = contenido_nuevo[:cust_start_c] + bloque_c + contenido_nuevo[cust_end_c:]
        first_cdata_c = contenido_nuevo.find("<![CDATA[")
        outer_lim_c = first_cdata_c if first_cdata_c != -1 else len(contenido_nuevo)
        recv_s = contenido_nuevo.find("<cac:ReceiverParty", 0)
        if recv_s != -1 and recv_s < outer_lim_c:
            recv_e_tag = contenido_nuevo.find("</cac:ReceiverParty>", recv_s)
            if recv_e_tag != -1:
                recv_e = recv_e_tag + len("</cac:ReceiverParty>")
                bloque_r = contenido_nuevo[recv_s:recv_e]
                bloque_r = bloque_r.replace(f"<cbc:RegistrationName>{co}</cbc:RegistrationName>",
                                            f"<cbc:RegistrationName>{cliente_nuevo}</cbc:RegistrationName>")
                contenido_nuevo = contenido_nuevo[:recv_s] + bloque_r + contenido_nuevo[recv_e:]

    # NIT cliente + dígito de verificación (evita FAC025)
    nit_nuevo = nuevos.get("nit", "").strip()
    dig_nuevo = nuevos.get("dig", "").strip()
    nit_orig, dig_orig = orig.get("nit", ""), orig.get("dig", "")
    if nit_nuevo and dig_nuevo and (nit_nuevo != nit_orig or dig_nuevo != dig_orig):
        cust_start = contenido_nuevo.find("<cac:AccountingCustomerParty")
        cust_end_tag = contenido_nuevo.find("</cac:AccountingCustomerParty>", cust_start)
        if cust_start != -1 and cust_end_tag != -1:
            cust_end = cust_end_tag + len("</cac:AccountingCustomerParty>")
            bloque = contenido_nuevo[cust_start:cust_end]
            bloque_nuevo = bloque
            if dig_orig:
                bloque_nuevo = bloque_nuevo.replace(f'schemeID="{dig_orig}"', f'schemeID="{dig_nuevo}"')
            if nit_orig:
                bloque_nuevo = bloque_nuevo.replace(f">{nit_orig}<", f">{nit_nuevo}<")
            contenido_nuevo = contenido_nuevo[:cust_start] + bloque_nuevo + contenido_nuevo[cust_end:]
        first_cdata = contenido_nuevo.find("<![CDATA[")
        outer_limit = first_cdata if first_cdata != -1 else len(contenido_nuevo)
        recv_start = contenido_nuevo.find("<cac:ReceiverParty", 0)
        if recv_start != -1 and recv_start < outer_limit:
            recv_end_tag = contenido_nuevo.find("</cac:ReceiverParty>", recv_start)
            if recv_end_tag != -1:
                recv_end = recv_end_tag + len("</cac:ReceiverParty>")
                bloque_recv = contenido_nuevo[recv_start:recv_end]
                bloque_recv_nuevo = bloque_recv
                if dig_orig:
                    bloque_recv_nuevo = bloque_recv_nuevo.replace(
                        f'schemeID="{dig_orig}"', f'schemeID="{dig_nuevo}"')
                if nit_orig:
                    bloque_recv_nuevo = bloque_recv_nuevo.replace(f">{nit_orig}<", f">{nit_nuevo}<")
                contenido_nuevo = contenido_nuevo[:recv_start] + bloque_recv_nuevo + contenido_nuevo[recv_end:]

    return contenido_nuevo, avisos
