"""
Envío de Factura Electrónica al RNDC (proceso 86) por WebService SOAP.

Lógica PORTADA TAL CUAL desde ui/rndc_uploader.py (mismo protocolo, mismas
plantillas, mismo parseo de respuesta). No modifica el módulo de escritorio:
es una copia funcional para la versión web. No depende de tkinter.
"""
import base64
import html as _html
import re as _re
import xml.etree.ElementTree as ET

import requests as _requests

ENDPOINTS = {
    "Pruebas  (rndcpruebas)":  "http://rndcpruebas.mintransporte.gov.co:8080",
    "Producción (rndcws)":     "http://rndcws.mintransporte.gov.co:8080",
}
SOAP_PATH   = "/soap/IBPMServices"
PROCESO     = "86"
SOAP_ACTION = "urn:BPMServicesIntf-IBPMServices#AtenderMensajeRNDC"

RNDC_XML_TMPL = """<?xml version='1.0' encoding='ISO-8859-1' ?>
<root>
  <acceso>
    <username>{usuario}</username>
    <password>{password}</password>
  </acceso>
  <solicitud>
    <tipo>1</tipo>
    <procesoid>{proceso}</procesoid>
  </solicitud>
  <variables>
    <NUMNITEMPRESATRANSPORTE>{nit_empresa}</NUMNITEMPRESATRANSPORTE>
    <ARCHIVOBASE64>{base64_xml}</ARCHIVOBASE64>
  </variables>
</root>"""

SOAP_ENVELOPE_TMPL = """<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:tns="http://tempuri.org/">
  <soapenv:Header/>
  <soapenv:Body>
    <tns:AtenderMensajeRNDC>
      <Request>{rndc_xml_escaped}</Request>
    </tns:AtenderMensajeRNDC>
  </soapenv:Body>
</soapenv:Envelope>"""


def enviar_factura_rndc(contenido_bytes, usuario, password, nit_empresa,
                        endpoint=None, timeout=45):
    """Envía un XML (bytes) al RNDC como Factura Electrónica (proceso 86).
    Retorna (exito: bool, mensaje: str). Equivalente a _soap_call del desktop."""
    if endpoint is None:
        endpoint = ENDPOINTS["Producción (rndcws)"]

    b64 = base64.b64encode(contenido_bytes).decode("ascii")
    rndc_xml = RNDC_XML_TMPL.format(
        usuario=_html.escape(usuario),
        password=_html.escape(password),
        proceso=PROCESO,
        nit_empresa=_html.escape(nit_empresa),
        base64_xml=b64,
    )
    soap_body = SOAP_ENVELOPE_TMPL.format(rndc_xml_escaped=_html.escape(rndc_xml))
    url = endpoint + SOAP_PATH
    headers = {
        "Content-Type": "text/xml; charset=UTF-8",
        "SOAPAction":   SOAP_ACTION,
    }
    try:
        resp = _requests.post(url, data=soap_body.encode("utf-8"),
                              headers=headers, timeout=timeout)
        return _parsear_respuesta(resp.text)
    except _requests.exceptions.ConnectionError:
        return False, f"Sin conexión a {endpoint}"
    except _requests.exceptions.Timeout:
        return False, f"Tiempo de espera agotado ({timeout}s)"
    except Exception as e:
        return False, str(e)[:180]


def _parsear_respuesta(resp_text):
    """Parsea la respuesta SOAP del RNDC. Idéntico a _parsear_respuesta del desktop."""
    inner_raw = None
    m = _re.search(r'<[^>]*:?return[^>]*>(.*?)</[^>]*:?return>',
                   resp_text, _re.DOTALL | _re.IGNORECASE)
    if m:
        inner_raw = m.group(1).strip()
    if not inner_raw:
        m2 = _re.search(r'(<root[^>]*>.*?</root>)', resp_text, _re.DOTALL | _re.IGNORECASE)
        if m2:
            inner_raw = m2.group(1).strip()
    if not inner_raw:
        return False, f"Respuesta no reconocida: {resp_text.strip()[:200]}"

    inner = _html.unescape(inner_raw)

    def _parse_xml(texto):
        try:
            return ET.fromstring(texto)
        except ET.ParseError:
            pass
        try:
            return ET.fromstring(texto.encode("iso-8859-1"))
        except Exception:
            pass
        sin_decl = _re.sub(r'<\?xml[^?]*\?>', '', texto, count=1).strip()
        try:
            return ET.fromstring(sin_decl)
        except Exception:
            return None

    root_el = _parse_xml(inner)
    if root_el is None:
        texto_plano = inner.strip()[:250]
        exito = any(p in texto_plano.upper() for p in
                    ("INGRESOID", "EXITOSO", "CORRECTO", "ACEPTADO"))
        return exito, texto_plano

    def _limpiar_msg(texto):
        texto = _re.sub(
            r'Paso\s*\d+\s*[Ee]jecutando\s+solicitud\.?\s*ProcesoId:\s*\d+\s*',
            '', texto).strip()
        m_err = _re.search(r'(Error\s+[A-Z]{2,}\d+\s*:.*)', texto, _re.DOTALL)
        if m_err:
            texto = m_err.group(1).strip()
        texto = _re.sub(r'\s*;Linea:\d+\s*', '', texto).strip()
        texto = _re.sub(r' {2,}', ' ', texto).strip()
        partes = _re.split(r'(?=Error\s+[A-Z]{2,}\d+\s*:)', texto)
        partes = [p.strip() for p in partes if p.strip()]
        if len(partes) > 1:
            vistos = []
            for p in partes:
                p_clean = _re.sub(r'\s+', ' ', p).strip().rstrip('.')
                if p_clean not in vistos:
                    vistos.append(p_clean)
            texto = '  |  '.join(vistos)
        return texto

    for tag_ok in ("ingresoid", "INGRESOID", "IngresoId"):
        ing = root_el.find(tag_ok)
        if ing is not None and ing.text and ing.text.strip():
            radicado = ing.text.strip()
            es_prueba = radicado.isdigit() and int(radicado) > 900_000_000
            sufijo = " · Ambiente de pruebas" if es_prueba else ""
            return True, f"Radicado RNDC: {radicado}{sufijo}"

    for tag_err in ("ErrorMSG", "errorMSG", "errormsg", "error", "Error",
                    "ERROR", "mensaje", "Mensaje", "message", "respuesta"):
        el = root_el.find(tag_err)
        if el is not None:
            hijo = el.find(tag_err)
            texto_err = (hijo.text if hijo is not None and hijo.text else el.text) or ""
            texto_err = texto_err.strip()
            if texto_err:
                return False, _limpiar_msg(texto_err)[:280]

    texto_root = (root_el.text or "").strip()
    if texto_root:
        return False, _limpiar_msg(texto_root)[:280]

    xml_str = ET.tostring(root_el, encoding="unicode")
    return False, _limpiar_msg(xml_str)[:280]


# ── Parseo de XML de factura (para mostrar facturas/remesas antes de enviar) ──

NS = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}
_NS_NORM = _re.compile(
    r'<cac:InvoiceLine\s+xmlns="[^"]*"(?:\s+xmlns:[^=]+="[^"]*")*\s*>')


def _xml_text(root, paths):
    for p in paths:
        el = root.find(p, NS)
        if el is not None and el.text and el.text.strip():
            return el.text.strip()
    return ""


def _extraer_invoice_xml(root_el, contenido_bytes):
    tag = root_el.tag.lower()
    if "attacheddocument" in tag:
        texto = contenido_bytes.decode("utf-8", errors="replace")
        match = _re.search(r'<!\[CDATA\[(.*?)\]\]>', texto, _re.DOTALL)
        if match:
            return match.group(1).strip()
    elif "invoice" in tag:
        return contenido_bytes.decode("utf-8", errors="replace")
    return None


def parse_factura_xml(nombre, contenido_bytes):
    """Extrae datos de un XML de factura: N° factura, CUFE, cliente, remesas.
    Réplica fiel de _poblar_tablas del desktop (sin la consulta RNDC de estado)."""
    info = {"archivo": nombre, "nf": "", "cufe": "", "cliente": "",
            "cliente_nit": "", "remesas": [], "error": ""}
    try:
        root_el = ET.fromstring(contenido_bytes.decode("utf-8", errors="replace"))
        info["nf"]   = _xml_text(root_el, [".//cbc:ParentDocumentID", ".//cbc:ID"])
        info["cufe"] = _xml_text(root_el, [".//cbc:UUID"])
        cliente = _xml_text(root_el, [".//cac:ReceiverParty//cbc:RegistrationName"])
        invoice_xml = _extraer_invoice_xml(root_el, contenido_bytes)
        if not cliente and invoice_xml:
            try:
                inv_pre = ET.fromstring(_NS_NORM.sub("<cac:InvoiceLine>", invoice_xml))
                cliente = _xml_text(inv_pre, [
                    ".//cac:AccountingCustomerParty//cbc:RegistrationName",
                    ".//cac:AccountingCustomerParty//cbc:Name"])
            except Exception:
                pass
        info["cliente"] = cliente
        info["cliente_nit"] = _xml_text(root_el, [".//cac:ReceiverParty//cbc:CompanyID"])

        if invoice_xml:
            try:
                inv_root = ET.fromstring(_NS_NORM.sub("<cac:InvoiceLine>", invoice_xml))
                lineas = inv_root.findall(
                    ".//{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}InvoiceLine")
                for linea in lineas:
                    props = {}
                    for prop in linea.findall(".//cac:AdditionalItemProperty", NS):
                        pname  = _xml_text(prop, ["cbc:Name"])
                        pvalue = _xml_text(prop, ["cbc:Value"])
                        if pname:
                            props[pname] = pvalue
                    radicado = props.get("01", "")
                    consec   = props.get("02", "")
                    valor_raw = props.get("03") or _xml_text(
                        linea, [".//cbc:LineExtensionAmount"]) or "0"
                    try:
                        valor = f"${float(valor_raw):,.2f}"
                    except Exception:
                        valor = valor_raw
                    info["remesas"].append(
                        {"consecutivo": consec, "radicado": radicado, "valor": valor})
            except Exception:
                pass
    except Exception as e:
        info["error"] = str(e)
    return info
