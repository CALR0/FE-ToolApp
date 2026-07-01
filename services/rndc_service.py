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
        return False, f"No se pudo parsear la respuesta: {inner[:200]}"

    for tag in (".//ErrorMSG", ".//error"):
        el = root_el.find(tag)
        if el is not None and el.text and el.text.strip():
            return False, el.text.strip()

    doc_el = root_el.find(".//documento")
    if doc_el is None:
        return False, f"Sin <documento> en la respuesta: {inner.strip()[:200]}"

    campos = {child.tag: (child.text or "").strip() for child in doc_el}
    if not campos:
        return False, "El <documento> no trajo campos."
    return True, campos


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
