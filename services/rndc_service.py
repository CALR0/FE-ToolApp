# rndc_service v2
try:
    import requests as _requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

# ─────────────────────────────────────────────────────────────────────────────
# CONSULTA RNDC: radicado (INGRESOID) a partir de CONSECUTIVOREMESA
# ─────────────────────────────────────────────────────────────────────────────

_RNDC_CONSULTA_REMESA_TMPL = """<?xml version='1.0' encoding='ISO-8859-1' ?>
<root>
  <acceso>
    <username>{usuario}</username>
    <password>{password}</password>
  </acceso>
  <solicitud>
    <tipo>3</tipo>
    <procesoid>3</procesoid>
  </solicitud>
  <variables>INGRESOID,CONSECUTIVOREMESA,CANTIDADCARGADA,ESTADO,REMPROPIETARIO,REM_DESTI,REM_ORIG,NUMMANIFIESTOCARGA,NUMIDPROPIETARIO</variables>
  <documento>
    <NUMNITEMPRESATRANSPORTE>'{nit_empresa}'</NUMNITEMPRESATRANSPORTE>
    <CONSECUTIVOREMESA>'{consecutivo_remesa}'</CONSECUTIVOREMESA>
  </documento>
</root>"""

_RNDC_CONSULTA_SOAP_ENVELOPE = """<?xml version="1.0" encoding="UTF-8"?>
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

_RNDC_CONSULTA_ENDPOINT  = "http://rndcws2.mintransporte.gov.co:8080"
_RNDC_CONSULTA_SOAP_PATH = "/soap/IBPMServices"
_RNDC_CONSULTA_ACTION    = "urn:BPMServicesIntf-IBPMServices#AtenderMensajeRNDC"


def consultar_radicado_remesa(consecutivo_remesa, perfil):
    """
    Consulta el INGRESOID (radicado) y CANTIDADPRODUCTO (peso) de una remesa
    en el RNDC. Usa el proceso 3 (Remesa Terrestre) con tipo=3 (consulta).
    Escribe un log detallado en rndc_consulta_remesa.log junto al .py.

    Parámetros:
        consecutivo_remesa : str  — número de remesa a consultar
        perfil             : dict — perfil activo (ut_tsp o ut_elogia)

    Retorna:
        (encontrado: bool, datos_o_error)
        Si encontrado=True  → datos_o_error es dict {'radicado': str, 'peso': str}
        Si encontrado=False → datos_o_error es str con el mensaje de error
    """
    if not REQUESTS_OK:
        return False, "La librería 'requests' no está instalada."

    import html as _html, xml.etree.ElementTree as ET, re as _re
    from datetime import datetime as _dt

    usuario     = perfil.get("rndc_usuario", "")
    password    = perfil.get("rndc_password", "")
    nit_empresa = perfil.get("nit_socio", "")

    # ── Helper de log (desactivado) ───────────────────────────────────────────
    def _log(titulo, contenido=""):
        pass

    _log(f"INICIO consulta remesa={consecutivo_remesa}  nit={nit_empresa}  usuario={usuario}")

    # 1. Construir XML RNDC de consulta
    rndc_xml = _RNDC_CONSULTA_REMESA_TMPL.format(
        usuario=_html.escape(usuario),
        password=_html.escape(password),
        nit_empresa=_html.escape(nit_empresa),
        consecutivo_remesa=_html.escape(str(consecutivo_remesa)),
    )
    _log("XML RNDC enviado (sin escapar SOAP):", rndc_xml)

    # 2. Escapar y empaquetar en SOAP envelope
    soap_body = _RNDC_CONSULTA_SOAP_ENVELOPE.format(
        rndc_xml_escaped=_html.escape(rndc_xml)
    )
    _log("SOAP envelope completo:", soap_body)

    url     = _RNDC_CONSULTA_ENDPOINT + _RNDC_CONSULTA_SOAP_PATH
    headers = {
        "Content-Type": "text/xml; charset=UTF-8",
        "SOAPAction":   _RNDC_CONSULTA_ACTION,
    }
    _log(f"URL destino: {url}")
    _log(f"SOAPAction: {_RNDC_CONSULTA_ACTION}")

    try:
        resp = _requests.post(
            url,
            data=soap_body.encode("utf-8"),
            headers=headers,
            timeout=15,
        )
        _log(f"HTTP status: {resp.status_code}", resp.text)
    except _requests.exceptions.ConnectionError as e:
        _log(f"ERROR ConnectionError: {e}")
        return False, f"Sin conexión a {_RNDC_CONSULTA_ENDPOINT}"
    except _requests.exceptions.Timeout:
        _log("ERROR Timeout (15s)")
        return False, "Tiempo de espera agotado (15s)"
    except Exception as e:
        _log(f"ERROR inesperado: {e}")
        return False, str(e)[:180]

    # 3. Extraer <return> del SOAP envelope
    inner_raw = None
    m = _re.search(r'<[^>]*:?return[^>]*>(.*?)</[^>]*:?return>',
                   resp.text, _re.DOTALL | _re.IGNORECASE)
    if m:
        inner_raw = m.group(1).strip()
        _log("Extraído de <return>:", inner_raw)
    if not inner_raw:
        m2 = _re.search(r'(<root[^>]*>.*?</root>)', resp.text,
                        _re.DOTALL | _re.IGNORECASE)
        if m2:
            inner_raw = m2.group(1).strip()
            _log("Extraído de <root> (fallback):", inner_raw)
    if not inner_raw:
        _log("No se encontró <return> ni <root> en la respuesta.")
        return False, f"Respuesta no reconocida: {resp.text.strip()[:200]}"

    inner = _html.unescape(inner_raw)
    _log("inner después de unescape:", inner)

    # 4. Parsear XML de resultado
    def _parse(texto):
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

    root_el = _parse(inner)
    if root_el is None:
        _log("No se pudo parsear el XML interno.")
        return False, f"No se pudo parsear la respuesta: {inner[:200]}"

    # 5. Elegir el <documento> correcto y leer sus campos.
    #    Una remesa con historial puede devolver VARIOS <documento> con estados
    #    distintos (ej. AC y CE) y el ORDEN NO es determinista. Hay que elegir el
    #    estado más avanzado: se prefiere CE (cumplida); si ninguno es CE, el de
    #    mayor INGRESOID (registro más reciente). Esto evita el falso "AC/Pendiente"
    #    intermitente en la consulta masiva.
    def _doc_estado(d):
        e = d.find("estado")
        return (e.text or "").strip().upper() if e is not None and e.text else ""

    def _doc_ingresoid(d):
        x = d.find("ingresoid")
        try:
            return int((x.text or "0").strip())
        except Exception:
            return 0

    docs = root_el.findall(".//documento")
    if docs:
        ce_docs = [d for d in docs if _doc_estado(d) == "CE"]
        doc_el  = ce_docs[0] if ce_docs else max(docs, key=_doc_ingresoid)
        todos   = {child.tag: (child.text or "").strip() for child in doc_el}
        radicado = todos.get("ingresoid", "").strip()
        if radicado:
            cp          = todos.get("cantidadcargada", "").strip()
            peso        = cp
            estado      = todos.get("estado", "").strip().upper()
            propietario = todos.get("rempropietario", "").strip()
            destino     = todos.get("rem_desti", "").strip()
            origen      = todos.get("rem_orig", "").strip()
            manifiesto  = todos.get("nummanifiestocarga", "").strip()
            propietario_nit = todos.get("numidpropietario", "").strip()
            _log(f"docs={len(docs)} elegido INGRESOID={radicado} estado={estado!r} manifiesto={manifiesto!r}")
            return True, {"radicado": radicado, "peso": peso, "estado": estado,
                          "propietario": propietario, "origen": origen, "destino": destino,
                          "manifiesto": manifiesto, "propietario_nit": propietario_nit}

    # Capturar ErrorMSG (tag real del RNDC para errores)
    errmsg_el = root_el.find(".//ErrorMSG")
    if errmsg_el is not None and errmsg_el.text:
        _log(f"Elemento <ErrorMSG> encontrado: {errmsg_el.text.strip()}")
        return False, errmsg_el.text.strip()

    # Si hay texto de error en la respuesta
    error_el = root_el.find(".//error")
    if error_el is not None and error_el.text:
        _log(f"Elemento <error> encontrado: {error_el.text.strip()}")
        return False, error_el.text.strip()

    # Fallback: texto plano del root
    texto_root = (root_el.text or "").strip()
    if texto_root:
        _log(f"Texto plano del root: {texto_root}")
        return False, texto_root[:200]

    _log(f"Sin INGRESOID ni error reconocible. inner completo: {inner}")
    return False, f"Remesa no encontrada. Respuesta: {inner.strip()[:200]}"


# ─────────────────────────────────────────────────────────────────────────────
# CONSULTA COMPLETA DE REMESA — proceso 3, tipo 3, variables=* (todos los campos)
# ─────────────────────────────────────────────────────────────────────────────

_RNDC_CONSULTA_FULL_TMPL = """<?xml version='1.0' encoding='ISO-8859-1' ?>
<root>
  <acceso>
    <username>{usuario}</username>
    <password>{password}</password>
  </acceso>
  <solicitud>
    <tipo>3</tipo>
    <procesoid>{procesoid}</procesoid>
  </solicitud>
  <variables>*</variables>
  <documento>
    <NUMNITEMPRESATRANSPORTE>'{nit_empresa}'</NUMNITEMPRESATRANSPORTE>
    <CONSECUTIVOREMESA>'{consecutivo_remesa}'</CONSECUTIVOREMESA>
  </documento>
</root>"""


def consultar_remesa_completa(consecutivo_remesa, perfil, procesoid=3, timeout=20):
    """
    Consulta TODOS los campos de una remesa con `tipo=3` y `variables=*`.

    procesoid=3 → datos de la remesa (citas pactadas, generador, etc.).
    procesoid=5 → datos del CUMPLIDO (tiempos logísticos reales ya registrados).

    Parámetros:
        consecutivo_remesa : str  — consecutivo de la remesa (tal cual; el caller
                                    aplica prefijo si el perfil lo requiere).
        perfil             : dict — usa rndc_usuario / rndc_password / nit_socio.
        procesoid          : int  — 3 (remesa) o 5 (cumplido).
        timeout            : int  — segundos de espera.

    Retorna:
        (ok: bool, resultado)
        Si ok=True  → dict {tag: valor} con todos los campos del <documento>.
        Si ok=False → str con el mensaje de error.
    """
    if not REQUESTS_OK:
        return False, "La librería 'requests' no está instalada."

    import html as _html, xml.etree.ElementTree as ET, re as _re

    usuario     = perfil.get("rndc_usuario", "")
    password    = perfil.get("rndc_password", "")
    nit_empresa = perfil.get("nit_socio", "")

    rndc_xml = _RNDC_CONSULTA_FULL_TMPL.format(
        procesoid=procesoid,
        usuario=_html.escape(usuario),
        password=_html.escape(password),
        nit_empresa=_html.escape(nit_empresa),
        consecutivo_remesa=_html.escape(str(consecutivo_remesa)),
    )
    soap_body = _RNDC_CONSULTA_SOAP_ENVELOPE.format(
        rndc_xml_escaped=_html.escape(rndc_xml)
    )

    url     = _RNDC_CONSULTA_ENDPOINT + _RNDC_CONSULTA_SOAP_PATH
    headers = {
        "Content-Type": "text/xml; charset=UTF-8",
        "SOAPAction":   _RNDC_CONSULTA_ACTION,
    }

    try:
        resp = _requests.post(url, data=soap_body.encode("utf-8"),
                              headers=headers, timeout=timeout)
    except _requests.exceptions.ConnectionError:
        return False, f"Sin conexión a {_RNDC_CONSULTA_ENDPOINT}"
    except _requests.exceptions.Timeout:
        return False, f"Tiempo de espera agotado ({timeout}s)"
    except Exception as e:
        return False, str(e)[:180]

    inner_raw = None
    m = _re.search(r'<[^>]*:?return[^>]*>(.*?)</[^>]*:?return>',
                   resp.text, _re.DOTALL | _re.IGNORECASE)
    if m:
        inner_raw = m.group(1).strip()
    if not inner_raw:
        m2 = _re.search(r'(<root[^>]*>.*?</root>)', resp.text,
                        _re.DOTALL | _re.IGNORECASE)
        if m2:
            inner_raw = m2.group(1).strip()
    if not inner_raw:
        return False, f"Respuesta no reconocida: {resp.text.strip()[:200]}"

    inner = _html.unescape(inner_raw)

    def _parse(texto):
        for intento in (texto, texto.encode("iso-8859-1", errors="ignore"),
                        _re.sub(r'<\?xml[^?]*\?>', '', texto, count=1).strip()):
            try:
                return ET.fromstring(intento)
            except Exception:
                continue
        return None

    root_el = _parse(inner)
    if root_el is None:
        return False, f"No se pudo parsear la respuesta: {inner[:200]}"

    # Error reportado por el RNDC
    for tag in (".//ErrorMSG", ".//error"):
        el = root_el.find(tag)
        if el is not None and el.text and el.text.strip():
            return False, el.text.strip()

    # Éxito: leer todos los hijos del <documento>
    doc_el = root_el.find(".//documento")
    if doc_el is None:
        return False, f"Sin <documento> en la respuesta: {inner.strip()[:200]}"

    campos = {child.tag: (child.text or "").strip() for child in doc_el}
    if not campos:
        return False, "El <documento> no trajo campos."
    return True, campos


# ─────────────────────────────────────────────────────────────────────────────
# CONSULTA COMPLETA DE MANIFIESTO — proceso 4, tipo 3, variables=* (todos los campos)
# (El proceso 6 es CUMPLIR manifiesto; aquí se CONSULTA el manifiesto = proceso 4.)
# ─────────────────────────────────────────────────────────────────────────────

_RNDC_CONSULTA_MANIFIESTO_TMPL = """<?xml version='1.0' encoding='ISO-8859-1' ?>
<root>
  <acceso>
    <username>{usuario}</username>
    <password>{password}</password>
  </acceso>
  <solicitud>
    <tipo>3</tipo>
    <procesoid>{procesoid}</procesoid>
  </solicitud>
  <variables>*</variables>
  <documento>
    <NUMNITEMPRESATRANSPORTE>'{nit_empresa}'</NUMNITEMPRESATRANSPORTE>
    <NUMMANIFIESTOCARGA>'{num_manifiesto}'</NUMMANIFIESTOCARGA>
  </documento>
</root>"""


def _campos_documento_regex(inner):
    """Fallback: extrae los <tag>valor</tag> del <documento> por regex, sin exigir
    XML bien formado. Sirve cuando ET.fromstring falla por un carácter suelto
    (ej. un '&' sin escapar en un nombre/dirección) que rompe el parseo estricto."""
    import re as _re
    m = _re.search(r'<documento>(.*?)</documento>', inner, _re.DOTALL | _re.IGNORECASE)
    if not m:
        return None
    cuerpo = m.group(1)
    campos = {}
    for mm in _re.finditer(r'<([A-Za-z_][\w.]*)>(.*?)</\1>', cuerpo, _re.DOTALL):
        campos[mm.group(1)] = (mm.group(2) or "").strip()
    return campos or None


def consultar_manifiesto_completo(num_manifiesto, perfil, procesoid=4, timeout=20):
    """
    Consulta TODOS los campos de un manifiesto con `tipo=3` y `variables=*`
    (proceso 4 = consultar manifiesto). Devuelve dinámicamente todas las variables
    que arroje el RNDC, útil tanto para mostrar como para reutilizar en otros módulos.

    NOTA: el proceso 6 es CUMPLIR manifiesto (datos del cumplido), reservado para
    el futuro módulo de cumplir manifiesto. La CONSULTA del manifiesto es proceso 4.

    Parámetros:
        num_manifiesto : str  — número del manifiesto de carga.
        perfil         : dict — usa rndc_usuario / rndc_password / nit_socio.
        procesoid      : int  — 4 (consultar manifiesto); 6 sería el cumplido.
        timeout        : int  — segundos de espera.

    Retorna:
        (ok: bool, resultado)
        Si ok=True  → dict {tag: valor} con todos los campos del <documento>.
        Si ok=False → str con el mensaje de error.
    """
    if not REQUESTS_OK:
        return False, "La librería 'requests' no está instalada."

    import html as _html, xml.etree.ElementTree as ET, re as _re

    usuario     = perfil.get("rndc_usuario", "")
    password    = perfil.get("rndc_password", "")
    nit_empresa = perfil.get("nit_socio", "")

    rndc_xml = _RNDC_CONSULTA_MANIFIESTO_TMPL.format(
        procesoid=procesoid,
        usuario=_html.escape(usuario),
        password=_html.escape(password),
        nit_empresa=_html.escape(nit_empresa),
        num_manifiesto=_html.escape(str(num_manifiesto)),
    )
    soap_body = _RNDC_CONSULTA_SOAP_ENVELOPE.format(
        rndc_xml_escaped=_html.escape(rndc_xml)
    )

    url     = _RNDC_CONSULTA_ENDPOINT + _RNDC_CONSULTA_SOAP_PATH
    headers = {
        "Content-Type": "text/xml; charset=UTF-8",
        "SOAPAction":   _RNDC_CONSULTA_ACTION,
    }

    try:
        resp = _requests.post(url, data=soap_body.encode("utf-8"),
                              headers=headers, timeout=timeout)
    except _requests.exceptions.ConnectionError:
        return False, f"Sin conexión a {_RNDC_CONSULTA_ENDPOINT}"
    except _requests.exceptions.Timeout:
        return False, f"Tiempo de espera agotado ({timeout}s)"
    except Exception as e:
        return False, str(e)[:180]

    inner_raw = None
    m = _re.search(r'<[^>]*:?return[^>]*>(.*?)</[^>]*:?return>',
                   resp.text, _re.DOTALL | _re.IGNORECASE)
    if m:
        inner_raw = m.group(1).strip()
    if not inner_raw:
        m2 = _re.search(r'(<root[^>]*>.*?</root>)', resp.text,
                        _re.DOTALL | _re.IGNORECASE)
        if m2:
            inner_raw = m2.group(1).strip()
    if not inner_raw:
        return False, f"Respuesta no reconocida: {resp.text.strip()[:200]}"

    inner = _html.unescape(inner_raw)

    def _parse(texto):
        for intento in (texto, texto.encode("iso-8859-1", errors="ignore"),
                        _re.sub(r'<\?xml[^?]*\?>', '', texto, count=1).strip()):
            try:
                return ET.fromstring(intento)
            except Exception:
                continue
        return None

    root_el = _parse(inner)
    if root_el is None:
        # Fallback por regex: el XML puede traer un carácter que rompe ET pero los
        # datos del <documento> están ahí (frecuente en manifiestos de Elogia).
        campos = _campos_documento_regex(inner)
        if campos:
            return True, campos
        return False, f"No se pudo parsear la respuesta: {inner[:200]}"

    for tag in (".//ErrorMSG", ".//error"):
        el = root_el.find(tag)
        if el is not None and el.text and el.text.strip():
            return False, el.text.strip()

    doc_el = root_el.find(".//documento")
    if doc_el is None:
        campos = _campos_documento_regex(inner)
        if campos:
            return True, campos
        return False, f"Sin <documento> en la respuesta: {inner.strip()[:200]}"

    campos = {child.tag: (child.text or "").strip() for child in doc_el}
    if not campos:
        return False, "El <documento> no trajo campos."
    return True, campos


# ─────────────────────────────────────────────────────────────────────────────
# CONSULTA DE MANIFIESTO POR RADICADO — proceso 4, tipo 3. Filtra por INGRESOID
# (el radicado) en vez del número. Útil para el monitoreo por placa (proceso 60),
# cuyos documentos traen `ingresoidmanifiesto` pero NO `nummanifiestocarga`.
# Verificado: INGRESOID filtra; INGRESOIDMANIFIESTO/NUMRADICADO dan Error RNDC027.
# ─────────────────────────────────────────────────────────────────────────────

_RNDC_CONSULTA_MANIF_RADICADO_TMPL = """<?xml version='1.0' encoding='ISO-8859-1' ?>
<root>
  <acceso>
    <username>{usuario}</username>
    <password>{password}</password>
  </acceso>
  <solicitud>
    <tipo>3</tipo>
    <procesoid>4</procesoid>
  </solicitud>
  <variables>*</variables>
  <documento>
    <NUMNITEMPRESATRANSPORTE>'{nit_empresa}'</NUMNITEMPRESATRANSPORTE>
    <INGRESOID>'{radicado}'</INGRESOID>
  </documento>
</root>"""


def consultar_manifiesto_por_radicado(radicado, perfil, timeout=20):
    """
    Consulta un manifiesto (proceso 4, tipo=3, variables=*) por su RADICADO
    (INGRESOID) en vez de por su número. Retorna (ok, dict) con todos los campos
    del manifiesto — incluido `nummanifiestocarga` — o (False, error).
    """
    if not REQUESTS_OK:
        return False, "La librería 'requests' no está instalada."
    import html as _html
    rndc_xml = _RNDC_CONSULTA_MANIF_RADICADO_TMPL.format(
        usuario=_html.escape(perfil.get("rndc_usuario", "")),
        password=_html.escape(perfil.get("rndc_password", "")),
        nit_empresa=_html.escape(perfil.get("nit_socio", "")),
        radicado=_html.escape(str(radicado).strip()),
    )
    ok, docs = _post_consulta_multi(rndc_xml, timeout)
    if not ok:
        return False, docs
    if not docs:
        return False, "Manifiesto no encontrado por radicado."
    return True, docs[0]


# ─────────────────────────────────────────────────────────────────────────────
# CONSULTA DE FACTURA ELECTRÓNICA — proceso 86, tipo 3, variables=* (todos los campos)
# Filtra por NUMNITEMPRESATRANSPORTE (nit_socio) + NUMEROFACTURA. NO sube ningún XML:
# solo lee el estado y los datos de una factura YA cargada.
# ─────────────────────────────────────────────────────────────────────────────

_RNDC_CONSULTA_FACTURA_TMPL = """<?xml version='1.0' encoding='ISO-8859-1' ?>
<root>
  <acceso>
    <username>{usuario}</username>
    <password>{password}</password>
  </acceso>
  <solicitud>
    <tipo>3</tipo>
    <procesoid>86</procesoid>
  </solicitud>
  <variables>*</variables>
  <documento>
    <NUMNITEMPRESATRANSPORTE>'{nit_empresa}'</NUMNITEMPRESATRANSPORTE>
    <NUMEROFACTURA>'{num_factura}'</NUMEROFACTURA>
  </documento>
</root>"""


def consultar_factura(num_factura, perfil, timeout=20):
    """
    Consulta una factura electrónica YA cargada al RNDC (proceso 86, tipo=3,
    variables=*), filtrando por NUMEROFACTURA. NO envía ningún XML: solo lee el
    estado y los datos de la factura.

    Usa las credenciales NORMALES del perfil (rndc_usuario / rndc_password) y
    nit_socio como NUMNITEMPRESATRANSPORTE — funciona igual para ut_tsp y ut_elogia.

    Parámetros:
        num_factura : str  — número de la factura a consultar.
        perfil      : dict — perfil activo (usa rndc_usuario/password/nit_socio).
        timeout     : int  — segundos de espera.

    Retorna:
        (ok: bool, resultado)
        Si ok=True  → dict {tag: valor} con TODOS los campos del <documento>
                      (estado, cufe, subtotal, valorfletes, nitadquirente, etc.).
        Si ok=False → str con el mensaje de error.
    """
    if not REQUESTS_OK:
        return False, "La librería 'requests' no está instalada."

    import html as _html, xml.etree.ElementTree as ET, re as _re

    usuario     = perfil.get("rndc_usuario", "")
    password    = perfil.get("rndc_password", "")
    nit_empresa = perfil.get("nit_socio", "")

    rndc_xml = _RNDC_CONSULTA_FACTURA_TMPL.format(
        usuario=_html.escape(usuario),
        password=_html.escape(password),
        nit_empresa=_html.escape(nit_empresa),
        num_factura=_html.escape(str(num_factura).strip()),
    )
    soap_body = _RNDC_CONSULTA_SOAP_ENVELOPE.format(
        rndc_xml_escaped=_html.escape(rndc_xml)
    )

    url     = _RNDC_CONSULTA_ENDPOINT + _RNDC_CONSULTA_SOAP_PATH
    headers = {
        "Content-Type": "text/xml; charset=UTF-8",
        "SOAPAction":   _RNDC_CONSULTA_ACTION,
    }

    try:
        resp = _requests.post(url, data=soap_body.encode("utf-8"),
                              headers=headers, timeout=timeout)
    except _requests.exceptions.ConnectionError:
        return False, f"Sin conexión a {_RNDC_CONSULTA_ENDPOINT}"
    except _requests.exceptions.Timeout:
        return False, f"Tiempo de espera agotado ({timeout}s)"
    except Exception as e:
        return False, str(e)[:180]

    inner_raw = None
    m = _re.search(r'<[^>]*:?return[^>]*>(.*?)</[^>]*:?return>',
                   resp.text, _re.DOTALL | _re.IGNORECASE)
    if m:
        inner_raw = m.group(1).strip()
    if not inner_raw:
        m2 = _re.search(r'(<root[^>]*>.*?</root>)', resp.text,
                        _re.DOTALL | _re.IGNORECASE)
        if m2:
            inner_raw = m2.group(1).strip()
    if not inner_raw:
        return False, f"Respuesta no reconocida: {resp.text.strip()[:200]}"

    inner = _html.unescape(inner_raw)

    def _parse(texto):
        for intento in (texto, texto.encode("iso-8859-1", errors="ignore"),
                        _re.sub(r'<\?xml[^?]*\?>', '', texto, count=1).strip()):
            try:
                return ET.fromstring(intento)
            except Exception:
                continue
        return None

    root_el = _parse(inner)
    if root_el is None:
        campos = _campos_documento_regex(inner)
        if campos:
            return True, campos
        return False, f"No se pudo parsear la respuesta: {inner[:200]}"

    for tag in (".//ErrorMSG", ".//error"):
        el = root_el.find(tag)
        if el is not None and el.text and el.text.strip():
            return False, el.text.strip()

    doc_el = root_el.find(".//documento")
    if doc_el is None:
        campos = _campos_documento_regex(inner)
        if campos:
            return True, campos
        return False, (f"No se encontró la factura {num_factura} "
                       f"(¿está cargada con ese número y este perfil?).")

    campos = {child.tag: (child.text or "").strip() for child in doc_el}
    if not campos:
        return False, "El <documento> no trajo campos."
    return True, campos


# ─────────────────────────────────────────────────────────────────────────────
# CONSULTA DE FACTURA POR REMESA — proceso 34 (Tarifas Generador), tipo 3, variables=*.
# Devuelve la tarifa del generador para una remesa, que incluye la FACTURA ELECTRÓNICA
# asociada (`facturaelectronica`). Filtra por NUMIDEMPRESA (nit_socio) + NUMIDGENERADOR
# (lo digita el usuario) + CONSECUTIVOREMESA. Credenciales normales del perfil.
# ─────────────────────────────────────────────────────────────────────────────

_RNDC_CONSULTA_FACT_X_REMESA_TMPL = """<?xml version='1.0' encoding='ISO-8859-1' ?>
<root>
  <acceso>
    <username>{usuario}</username>
    <password>{password}</password>
  </acceso>
  <solicitud>
    <tipo>3</tipo>
    <procesoid>34</procesoid>
  </solicitud>
  <variables>*</variables>
  <documento>
    <NUMIDEMPRESA>'{nit_empresa}'</NUMIDEMPRESA>
    <NUMIDGENERADOR>'{nit_generador}'</NUMIDGENERADOR>
    <CONSECUTIVOREMESA>'{consecutivo}'</CONSECUTIVOREMESA>
  </documento>
</root>"""


def _doc_mas_reciente(docs):
    """De una lista de documentos del RNDC, devuelve el de **mayor INGRESOID** (el más
    reciente). Útil cuando una remesa tiene varios registros de tarifa (re-tarifada:
    uno viejo sin factura, otro reciente con la factura)."""
    def _ing(d):
        low = {str(k).lower(): v for k, v in d.items()}
        try:
            return int(str(low.get("ingresoid", "0")).strip() or 0)
        except Exception:
            return 0
    return max(docs, key=_ing) if docs else None


def consultar_factura_por_remesa(consecutivo_remesa, num_id_generador, perfil, timeout=20):
    """
    Consulta la tarifa del generador (proceso 34, tipo=3, variables=*) de una remesa.
    Incluye la **factura electrónica** asociada (`facturaelectronica`) y datos del
    generador/empresa/origen/destino/valores.

    Filtro: `NUMIDEMPRESA` = nit_socio del perfil, `NUMIDGENERADOR` = NIT del generador
    (lo digita el usuario), `CONSECUTIVOREMESA` = consecutivo de la remesa. Usa las
    credenciales normales del perfil (`rndc_usuario`/`rndc_password`).

    Si la remesa tiene **varios registros** (re-tarifada: uno viejo sin factura y otro
    reciente con la factura), devuelve el **más reciente** (mayor INGRESOID).

    Retorna:
        (ok: bool, resultado)
        Si ok=True  → dict {tag: valor} del documento más reciente.
        Si ok=False → str con el mensaje de error.
    """
    if not REQUESTS_OK:
        return False, "La librería 'requests' no está instalada."

    import html as _html
    rndc_xml = _RNDC_CONSULTA_FACT_X_REMESA_TMPL.format(
        usuario=_html.escape(perfil.get("rndc_usuario", "")),
        password=_html.escape(perfil.get("rndc_password", "")),
        nit_empresa=_html.escape(perfil.get("nit_socio", "")),
        nit_generador=_html.escape(str(num_id_generador).strip()),
        consecutivo=_html.escape(str(consecutivo_remesa).strip()),
    )
    ok, docs = _post_consulta_multi(rndc_xml, timeout)
    if not ok:
        return False, docs
    if not docs:
        return False, (f"No se encontró tarifa para la remesa {consecutivo_remesa} "
                       f"(¿generador/NIT correctos y perfil correcto?).")
    return True, _doc_mas_reciente(docs)


# ─────────────────────────────────────────────────────────────────────────────
# CONSULTA DE REMESAS DE UNA FACTURA — proceso 34 (Tarifas Generador), tipo 3.
# Filtra por FACTURAELECTRONICA y devuelve UN documento por cada remesa de la factura
# (la cantidad de remesas = número de documentos). Verificado en vivo.
# ─────────────────────────────────────────────────────────────────────────────

_RNDC_CONSULTA_REMESAS_X_FACTURA_TMPL = """<?xml version='1.0' encoding='ISO-8859-1' ?>
<root>
  <acceso>
    <username>{usuario}</username>
    <password>{password}</password>
  </acceso>
  <solicitud>
    <tipo>3</tipo>
    <procesoid>34</procesoid>
  </solicitud>
  <variables>*</variables>
  <documento>
    <NUMIDEMPRESA>'{nit_empresa}'</NUMIDEMPRESA>
    <NUMIDGENERADOR>'{nit_generador}'</NUMIDGENERADOR>
    <FACTURAELECTRONICA>'{factura}'</FACTURAELECTRONICA>
  </documento>
</root>"""


def consultar_remesas_por_factura(num_factura, num_id_generador, perfil, timeout=20):
    """
    Consulta TODAS las remesas de una factura (proceso 34, tipo=3, variables=*),
    filtrando por FACTURAELECTRONICA. Devuelve **un documento por remesa** de la
    factura (la cantidad de remesas = número de documentos).

    Filtro: NUMIDEMPRESA = nit_socio, NUMIDGENERADOR = NIT del generador (lo digita
    el usuario), FACTURAELECTRONICA = número de la factura. Credenciales normales.

    Retorna:
        (ok: bool, resultado)
        Si ok=True  → list[dict], una remesa por elemento (incluye consecutivoremesa,
                      radicadoremesa, valorfletelinea, linea, origen/destino, etc.).
        Si ok=False → str con el mensaje de error.
    """
    if not REQUESTS_OK:
        return False, "La librería 'requests' no está instalada."
    import html as _html
    rndc_xml = _RNDC_CONSULTA_REMESAS_X_FACTURA_TMPL.format(
        usuario=_html.escape(perfil.get("rndc_usuario", "")),
        password=_html.escape(perfil.get("rndc_password", "")),
        nit_empresa=_html.escape(perfil.get("nit_socio", "")),
        nit_generador=_html.escape(str(num_id_generador).strip()),
        factura=_html.escape(str(num_factura).strip()),
    )
    ok, docs = _post_consulta_multi(rndc_xml, timeout)
    if not ok:
        return False, docs
    if not docs:
        return False, (f"No se encontraron remesas para la factura {num_factura} "
                       f"(¿generador/NIT y perfil correctos?).")
    return True, docs


# ─────────────────────────────────────────────────────────────────────────────
# CONSULTA DE FACTURAS POR RANGO DE FECHA — proceso 86, tipo 3.
# El WS NO soporta rango nativo: solo filtra por FECHAFACTURA EXACTA (YYYY-MM-DD) y
# devuelve TODAS las facturas de ese día. Por eso el rango se hace consultando
# día por día y agregando (verificado empíricamente: operadores >=/<=/BETWEEN y los
# campos FECHAINICIAL*/FECHAFINAL* dan Error RNDC027).
# ─────────────────────────────────────────────────────────────────────────────

_RNDC_CONSULTA_FACTURA_FECHA_TMPL = """<?xml version='1.0' encoding='ISO-8859-1' ?>
<root>
  <acceso>
    <username>{usuario}</username>
    <password>{password}</password>
  </acceso>
  <solicitud>
    <tipo>3</tipo>
    <procesoid>86</procesoid>
  </solicitud>
  <variables>*</variables>
  <documento>
    <NUMNITEMPRESATRANSPORTE>'{nit_empresa}'</NUMNITEMPRESATRANSPORTE>
    <FECHAFACTURA>'{fecha}'</FECHAFACTURA>
  </documento>
</root>"""


def consultar_facturas_por_fecha(perfil, fecha_inicial, fecha_final,
                                 timeout=20, max_dias=93):
    """
    Lista las facturas electrónicas (proceso 86, tipo=3) cuya FECHAFACTURA cae en
    el rango [fecha_inicial, fecha_final] (inclusive). Como el WS solo filtra por
    fecha EXACTA, se consulta día por día y se agregan los resultados.

    fecha_inicial/fecha_final: date o str ('YYYY-MM-DD', 'YYYY/MM/DD', 'DD/MM/YYYY').
    max_dias: tope de días del rango (evita rangos gigantes).

    Retorna:
        (ok: bool, resultado)
        Si ok=True  → list[dict], un dict por factura (todos los campos del RNDC).
        Si ok=False → str con el mensaje de error.
    """
    if not REQUESTS_OK:
        return False, "La librería 'requests' no está instalada."

    import html as _html
    from datetime import datetime as _dt, timedelta as _td

    def _to_date(x):
        if x is None:
            return None
        if hasattr(x, "strftime") and not isinstance(x, str):
            return x
        s = str(x).strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return _dt.strptime(s, fmt).date()
            except Exception:
                continue
        return None

    d0, d1 = _to_date(fecha_inicial), _to_date(fecha_final)
    if not d0 or not d1:
        return False, "Fechas inválidas (usa AAAA-MM-DD)."
    if d1 < d0:
        d0, d1 = d1, d0
    dias = (d1 - d0).days + 1
    if dias > max_dias:
        return False, (f"El rango es de {dias} días; el máximo es {max_dias}. "
                       f"Acorta el rango de fechas.")

    usuario  = perfil.get("rndc_usuario", "")
    password = perfil.get("rndc_password", "")
    nit      = perfil.get("nit_socio", "")

    todos, errores = [], []
    d = d0
    while d <= d1:
        fecha = d.strftime("%Y-%m-%d")
        rndc_xml = _RNDC_CONSULTA_FACTURA_FECHA_TMPL.format(
            usuario=_html.escape(usuario), password=_html.escape(password),
            nit_empresa=_html.escape(nit), fecha=fecha)
        ok, docs = _post_consulta_multi(rndc_xml, timeout)
        if ok:
            todos.extend(docs)          # (True, []) si ese día no tiene facturas
        else:
            errores.append(f"{fecha}: {docs}")
        d += _td(days=1)

    if not todos and errores:
        return False, "; ".join(errores[:3])
    return True, todos


# ─────────────────────────────────────────────────────────────────────────────
# MONITOREO DE MANIFIESTO (tiempos logísticos) — RNDC proceso 60 (tipo 3 = consulta)
# ─────────────────────────────────────────────────────────────────────────────

def _post_consulta_multi(rndc_xml, timeout=20):
    """POST de una consulta RNDC (tipo=3) y parseo de TODOS los <documento> por
    regex (tolerante a XML mal formado). Retorna (ok, list[dict] | str_error).
    Si no hay documentos pero tampoco error, retorna (True, [])."""
    import html as _html, re as _re

    soap_body = _RNDC_CONSULTA_SOAP_ENVELOPE.format(
        rndc_xml_escaped=_html.escape(rndc_xml))
    url     = _RNDC_CONSULTA_ENDPOINT + _RNDC_CONSULTA_SOAP_PATH
    headers = {
        "Content-Type": "text/xml; charset=UTF-8",
        "SOAPAction":   _RNDC_CONSULTA_ACTION,
    }
    try:
        resp = _requests.post(url, data=soap_body.encode("utf-8"),
                              headers=headers, timeout=timeout)
    except _requests.exceptions.ConnectionError:
        return False, f"Sin conexión a {_RNDC_CONSULTA_ENDPOINT}"
    except _requests.exceptions.Timeout:
        return False, f"Tiempo de espera agotado ({timeout}s)"
    except Exception as e:
        return False, str(e)[:180]

    inner_raw = None
    m = _re.search(r'<[^>]*:?return[^>]*>(.*?)</[^>]*:?return>',
                   resp.text, _re.DOTALL | _re.IGNORECASE)
    if m:
        inner_raw = m.group(1).strip()
    if not inner_raw:
        m2 = _re.search(r'(<root[^>]*>.*?</root>)', resp.text,
                        _re.DOTALL | _re.IGNORECASE)
        if m2:
            inner_raw = m2.group(1).strip()
    if not inner_raw:
        return False, f"Respuesta no reconocida: {resp.text.strip()[:200]}"

    inner = _html.unescape(inner_raw)

    merr = _re.search(r'<ErrorMSG>(.*?)</ErrorMSG>', inner, _re.DOTALL | _re.IGNORECASE)
    if merr and merr.group(1).strip():
        return False, merr.group(1).strip()

    docs = []
    for md in _re.finditer(r'<documento>(.*?)</documento>', inner, _re.DOTALL | _re.IGNORECASE):
        cuerpo = md.group(1)
        campos = {}
        for mm in _re.finditer(r'<([A-Za-z_][\w.]*)>(.*?)</\1>', cuerpo, _re.DOTALL):
            campos[mm.group(1)] = (mm.group(2) or "").strip()
        if campos:
            docs.append(campos)
    return True, docs

_RNDC_MONITOREO_TMPL = """<?xml version='1.0' encoding='ISO-8859-1' ?>
<root>
  <acceso>
    <username>{usuario}</username>
    <password>{password}</password>
  </acceso>
  <solicitud>
    <tipo>3</tipo>
    <procesoid>60</procesoid>
  </solicitud>
  <variables>*</variables>
  <documento>
    <NUMIDGPS>'{nit_gps}'</NUMIDGPS>
    <NUMNITEMPRESATRANSPORTE>'{nit_empresa}'</NUMNITEMPRESATRANSPORTE>
{filtros}
  </documento>
</root>"""


def consultar_monitoreo_manifiesto(perfil, radicado_manifiesto="", placa="",
                                   fecha_inicial="", fecha_final="", timeout=20,
                                   max_dias=93):
    """
    Consulta los tiempos logísticos (monitoreo) de un manifiesto — proceso 60,
    tipo=3, variables=*. Filtra por radicado del manifiesto (INGRESOIDMANIFIESTO)
    y/o por placa del vehículo (NUMPLACA). Debe pasarse al menos uno de los dos.

    Rango de fecha OPCIONAL (fecha_inicial/fecha_final, date o str): útil sobre todo
    al buscar por placa (una placa SIN fecha trae TODO su historial de monitoreo). El
    WS no soporta rango nativo — solo filtra por FECHACREA EXACTA (YYYY-MM-DD) — así
    que el rango se consulta día por día y se agrega (tope `max_dias`). Verificado:
    FECHACREA/FECHALLEGADA/FECHASALIDA filtran en formato YYYY-MM-DD; DD/MM/YYYY y los
    operadores >=/<= dan Error RNDC027, y un día sin datos da Error RNDC11 (= vacío).

    Devuelve TODOS los puntos de control (el RNDC entrega un <documento> por cada
    punto de control monitoreado).

    Credenciales/empresa de monitoreo (usa del perfil, con fallback):
        - usuario/password: rndc_usuario_monitoreo / rndc_password_monitoreo
          (si no están, cae a rndc_usuario / rndc_password).
        - NUMIDGPS: nit_monitoreo (NIT de la empresa de monitoreo de flota).
        - NUMNITEMPRESATRANSPORTE: nit_socio (empresa de transporte del perfil).

    Retorna:
        (ok: bool, resultado)
        Si ok=True  → list[dict] con los campos de cada punto de control.
        Si ok=False → str con el mensaje de error.
    """
    if not REQUESTS_OK:
        return False, "La librería 'requests' no está instalada."

    import html as _html, xml.etree.ElementTree as ET, re as _re

    usuario  = perfil.get("rndc_usuario_monitoreo") or perfil.get("rndc_usuario", "")
    password = perfil.get("rndc_password_monitoreo") or perfil.get("rndc_password", "")
    nit_gps  = perfil.get("nit_monitoreo", "")
    nit_emp  = perfil.get("nit_socio", "")

    if not nit_gps:
        return False, ("El perfil no tiene configurado 'nit_monitoreo' (NIT de la "
                       "empresa de monitoreo). Configúralo para consultar tiempos.")

    radicado = str(radicado_manifiesto or "").strip()
    placa    = str(placa or "").strip()
    if not radicado and not placa:
        return False, "Debes indicar el radicado del manifiesto o la placa del vehículo."

    filtros_base = []
    if radicado:
        filtros_base.append(f"    <INGRESOIDMANIFIESTO>'{_html.escape(radicado)}'</INGRESOIDMANIFIESTO>")
    if placa:
        filtros_base.append(f"    <NUMPLACA>'{_html.escape(placa)}'</NUMPLACA>")

    def _run(filtros):
        rndc_xml = _RNDC_MONITOREO_TMPL.format(
            usuario=_html.escape(usuario), password=_html.escape(password),
            nit_gps=_html.escape(str(nit_gps)), nit_empresa=_html.escape(str(nit_emp)),
            filtros="\n".join(filtros))
        return _post_consulta_multi(rndc_xml, timeout)

    # ── Rango de fecha opcional (día por día; el WS solo filtra FECHACREA exacta) ──
    from datetime import datetime as _dt, timedelta as _td

    def _to_date(x):
        if not x:
            return None
        if hasattr(x, "strftime") and not isinstance(x, str):
            return x
        s = str(x).strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return _dt.strptime(s, fmt).date()
            except Exception:
                continue
        return None

    d0, d1 = _to_date(fecha_inicial), _to_date(fecha_final)
    if d0 and d1:
        if d1 < d0:
            d0, d1 = d1, d0
        dias = (d1 - d0).days + 1
        if dias > max_dias:
            return False, (f"El rango es de {dias} días; el máximo es {max_dias}. "
                           f"Acorta el rango de fechas.")
        todos, errores = [], []
        d = d0
        while d <= d1:
            f = filtros_base + [f"    <FECHACREA>'{d.strftime('%Y-%m-%d')}'</FECHACREA>"]
            ok, docs = _run(f)
            if ok:
                todos.extend(docs)
            elif ("RNDC11" in str(docs)) or ("no encontrad" in str(docs).lower()):
                pass                       # ese día no tiene monitoreo (normal)
            else:
                errores.append(f"{d.strftime('%Y-%m-%d')}: {docs}")
            d += _td(days=1)
        if not todos:
            return False, ("; ".join(errores[:3]) if errores
                           else "Sin datos de monitoreo en ese rango de fechas.")
        return True, todos

    # ── Sin rango: consulta única (comportamiento original) ──────────────────────
    ok, docs = _run(filtros_base)
    if not ok:
        return False, docs
    if not docs:
        return False, "Sin datos de monitoreo para ese manifiesto (¿aún no reportan tiempos?)."
    return True, docs


_RNDC_REMESAS_POR_MANIF_TMPL = """<?xml version='1.0' encoding='ISO-8859-1' ?>
<root>
  <acceso>
    <username>{usuario}</username>
    <password>{password}</password>
  </acceso>
  <solicitud>
    <tipo>3</tipo>
    <procesoid>3</procesoid>
  </solicitud>
  <variables>*</variables>
  <documento>
    <NUMNITEMPRESATRANSPORTE>'{nit_empresa}'</NUMNITEMPRESATRANSPORTE>
    <NUMMANIFIESTOCARGA>'{num_manifiesto}'</NUMMANIFIESTOCARGA>
  </documento>
</root>"""


def consultar_remesas_por_manifiesto(num_manifiesto, perfil, timeout=20):
    """
    Consulta las remesas asociadas a un manifiesto (proceso 3, tipo=3, variables=*),
    filtrando por NUMMANIFIESTOCARGA. Útil para leer las citas pactadas de
    cargue/descargue del viaje. Retorna (ok, list[dict]) — una remesa por documento.
    """
    if not REQUESTS_OK:
        return False, "La librería 'requests' no está instalada."

    import html as _html

    rndc_xml = _RNDC_REMESAS_POR_MANIF_TMPL.format(
        usuario=_html.escape(perfil.get("rndc_usuario", "")),
        password=_html.escape(perfil.get("rndc_password", "")),
        nit_empresa=_html.escape(perfil.get("nit_socio", "")),
        num_manifiesto=_html.escape(str(num_manifiesto)),
    )
    ok, docs = _post_consulta_multi(rndc_xml, timeout)
    if not ok:
        return False, docs
    if not docs:
        return False, "Sin remesas para ese manifiesto."
    return True, docs


# ─────────────────────────────────────────────────────────────────────────────
# CORREGIR REMESA — RNDC proceso 38 (tipo 1 = enviar/registrar)
# ─────────────────────────────────────────────────────────────────────────────

# Endpoint para CORREGIR remesa (proceso 38). Usa rndcws (sin "2"), que es el
# host al que apunta el WSDL del web service del RNDC.
_RNDC_REMESA_ENDPOINT  = "http://rndcws.mintransporte.gov.co:8080"
_RNDC_REMESA_SOAP_PATH = "/soap/IBPMServices"
_RNDC_REMESA_ACTION    = "urn:BPMServicesIntf-IBPMServices#AtenderMensajeRNDC"


def _enviar_proceso_rndc(procesoid, variables, perfil, timeout=20):
    """
    Envía información a un proceso del RNDC (tipo 1 = registrar/enviar), sin
    elemento <documento>. Usado por corregir_remesa (38) y anular_cumplido_remesa
    (28). Endpoint: rndcws (host del WSDL).

    Parámetros:
        procesoid : int|str — número de proceso del RNDC (ej. 38, 28).
        variables : dict    — {nombre_variable: valor}; el orden se respeta.
        perfil    : dict    — usa rndc_usuario / rndc_password.
        timeout   : int     — segundos de espera.

    Retorna:
        (ok, dict {'ingresoid','respuesta'})  o  (False, mensaje_error)
    """
    if not REQUESTS_OK:
        return False, "La librería 'requests' no está instalada."

    import html as _html, xml.etree.ElementTree as ET, re as _re

    usuario  = perfil.get("rndc_usuario", "")
    password = perfil.get("rndc_password", "")

    if not isinstance(variables, dict) or not variables:
        return False, "Debes pasar un dict de variables no vacío."

    # 1. Bloque <variables> respetando el orden del dict
    bloque_vars = "".join(
        f"    <{nombre}>{_html.escape('' if valor is None else str(valor))}</{nombre}>\n"
        for nombre, valor in variables.items()
    )

    rndc_xml = (
        "<?xml version='1.0' encoding='ISO-8859-1' ?>\n"
        "<root>\n"
        "  <acceso>\n"
        f"    <username>{_html.escape(usuario)}</username>\n"
        f"    <password>{_html.escape(password)}</password>\n"
        "  </acceso>\n"
        "  <solicitud>\n"
        "    <tipo>1</tipo>\n"
        f"    <procesoid>{procesoid}</procesoid>\n"
        "  </solicitud>\n"
        "  <variables>\n"
        f"{bloque_vars}"
        "  </variables>\n"
        "</root>"
    )

    soap_body = _RNDC_CONSULTA_SOAP_ENVELOPE.format(
        rndc_xml_escaped=_html.escape(rndc_xml)
    )
    url     = _RNDC_REMESA_ENDPOINT + _RNDC_REMESA_SOAP_PATH
    headers = {
        "Content-Type": "text/xml; charset=UTF-8",
        "SOAPAction":   _RNDC_REMESA_ACTION,
    }

    try:
        resp = _requests.post(url, data=soap_body.encode("utf-8"),
                              headers=headers, timeout=timeout)
    except _requests.exceptions.ConnectionError:
        return False, f"Sin conexión a {_RNDC_REMESA_ENDPOINT}"
    except _requests.exceptions.Timeout:
        return False, f"Tiempo de espera agotado ({timeout}s)"
    except Exception as e:
        return False, str(e)[:180]

    # Extraer XML de respuesta
    inner_raw = None
    m = _re.search(r'<[^>]*:?return[^>]*>(.*?)</[^>]*:?return>',
                   resp.text, _re.DOTALL | _re.IGNORECASE)
    if m:
        inner_raw = m.group(1).strip()
    if not inner_raw:
        m2 = _re.search(r'(<root[^>]*>.*?</root>)', resp.text,
                        _re.DOTALL | _re.IGNORECASE)
        if m2:
            inner_raw = m2.group(1).strip()
    if not inner_raw:
        return False, f"Respuesta no reconocida: {resp.text.strip()[:200]}"

    inner = _html.unescape(inner_raw)

    def _parse(texto):
        for intento in (texto, texto.encode("iso-8859-1", errors="ignore"),
                        _re.sub(r'<\?xml[^?]*\?>', '', texto, count=1).strip()):
            try:
                return ET.fromstring(intento)
            except Exception:
                continue
        return None

    root_el = _parse(inner)
    if root_el is None:
        return False, f"No se pudo parsear la respuesta: {inner[:200]}"

    ing = root_el.find(".//ingresoid")
    if ing is not None and ing.text and ing.text.strip():
        return True, {"ingresoid": ing.text.strip(), "respuesta": inner.strip()}

    for tag in (".//ErrorMSG", ".//error"):
        el = root_el.find(tag)
        if el is not None and el.text and el.text.strip():
            return False, el.text.strip()

    return False, f"Respuesta sin INGRESOID ni error: {inner.strip()[:200]}"


def corregir_remesa(variables, perfil, timeout=20):
    """
    Corrige una remesa en el RNDC usando el proceso 38 (tipo 1).
    `variables` es un dict {nombre: valor} según el Diccionario de Datos del
    proceso 38 (no incluye credenciales). Retorna (ok, {ingresoid}) o (False, err).
    """
    return _enviar_proceso_rndc(38, variables, perfil, timeout)


def anular_cumplido_remesa(consecutivo_remesa, cod_motivo, perfil, timeout=20):
    """
    Anula el cumplido de una remesa en el RNDC (proceso 28, tipo 1).

    Campos que exige el formulario del RNDC:
        NUMNITEMPRESATRANSPORTE    (del perfil: nit_socio)
        CONSECUTIVOREMESA          (consecutivo de la remesa)
        CODMOTIVOANULACIONCUMPLIDO ('D' = Error Digitación, 'O' = Otro)

    Parámetros:
        consecutivo_remesa : str
        cod_motivo         : str  — 'D' o 'O'
        perfil             : dict — usa rndc_usuario / rndc_password / nit_socio.

    Retorna (ok, {ingresoid}) o (False, mensaje_error).
    """
    variables = {
        "NUMNITEMPRESATRANSPORTE":    perfil.get("nit_socio", ""),
        "CONSECUTIVOREMESA":          str(consecutivo_remesa).strip(),
        "CODMOTIVOANULACIONCUMPLIDO": str(cod_motivo).strip(),
    }
    return _enviar_proceso_rndc(28, variables, perfil, timeout)


def anular_cumplido_manifiesto(num_manifiesto, cod_motivo, perfil, observaciones="", timeout=20):
    """
    Anula el cumplido de un manifiesto en el RNDC (proceso 29, tipo 1).

    Campos que exige el formulario del RNDC (AnularCumplidoManifiesto):
        NUMNITEMPRESATRANSPORTE    (del perfil: nit_socio)
        NUMMANIFIESTOCARGA         (número del manifiesto de carga)
        CODMOTIVOANULACIONCUMPLIDO ('D' = Error Digitación, 'O' = Otro)
        OBSERVACIONES              (opcional)

    Parámetros:
        num_manifiesto : str
        cod_motivo     : str  — 'D' o 'O'
        perfil         : dict — usa rndc_usuario / rndc_password / nit_socio.
        observaciones  : str  — opcional.

    Retorna (ok, {ingresoid}) o (False, mensaje_error).
    """
    variables = {
        "NUMNITEMPRESATRANSPORTE":    perfil.get("nit_socio", ""),
        "NUMMANIFIESTOCARGA":         str(num_manifiesto).strip(),
        "CODMOTIVOANULACIONCUMPLIDO": str(cod_motivo).strip(),
    }
    if str(observaciones).strip():
        variables["OBSERVACIONES"] = str(observaciones).strip()
    return _enviar_proceso_rndc(29, variables, perfil, timeout)


def cumplir_manifiesto(variables, perfil, timeout=20):
    """
    Cumple un manifiesto en el RNDC (proceso 6, tipo 1).
    `variables` es un dict {nombre: valor} con los campos del cumplido del manifiesto
    (NUMMANIFIESTOCARGA, TIPOCUMPLIDOMANIFIESTO, FECHAENTREGADOCUMENTOS, etc.).
    Mismo endpoint (rndcws) y credenciales que corregir/anular/cumplir remesa.
    Retorna (ok, {ingresoid}) o (False, mensaje_error).
    """
    return _enviar_proceso_rndc(6, variables, perfil, timeout)


def cumplir_remesa(variables, perfil, timeout=20):
    """
    Cumple una remesa en el RNDC (proceso 5, tipo 1).
    `variables` es un dict {nombre: valor} con los campos del cumplido
    (TIPOCUMPLIDOREMESA, cantidades, tiempos logísticos, etc.).
    Mismo endpoint (rndcws) y credenciales que corregir/anular.
    Retorna (ok, {ingresoid}) o (False, mensaje_error).
    """
    return _enviar_proceso_rndc(5, variables, perfil, timeout)
