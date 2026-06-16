from datetime import datetime, timedelta
from config.perfiles import NIT_UT, NOMBRE_UT, PREFIJO, UNIDAD_MEDIDA, PERFILES


def _parse_valor(texto):
    """
    Convierte un string numérico con formato libre a float.
    Soporta: 611.111,00 / 1.629.028 / 611,111.00 / 611111 / 611111.00
    """
    s = texto.strip().replace(" ", "")
    if not s:
        raise ValueError("Valor vacío")
    last_dot   = s.rfind(".")
    last_comma = s.rfind(",")
    if last_comma > last_dot:
        s = s.replace(".", "").replace(",", ".")
    elif last_comma == -1 and s.count(".") > 1:
        s = s.replace(".", "")
    elif last_dot != -1 and last_comma == -1 and (len(s) - 1 - last_dot) == 3:
        s = s.replace(".", "")
    else:
        s = s.replace(",", "")
    return float(s)


def _fmt_valor(v):
    """Formatea un valor monetario: entero si no tiene centavos, decimal si los tiene.
    1777777.0 → '1777777'   /   1777777.50 → '1777777.5'
    Se usa en el XML para no escribir puntos ni comas en los montos.
    """
    f = float(v)
    return str(int(f)) if f == int(f) else str(f)


def generar_invoice_line(idx, consecutivo_remesa, radicado,
                         descripcion_linea, peso, valor_unitario):
    """Genera un bloque <cac:InvoiceLine> para una remesa."""
    retencion = round(float(valor_unitario) * 0.01, 2)
    retencion_fmt = _fmt_valor(retencion)
    return f"""<cac:InvoiceLine>
<cbc:ID schemeID="1">{idx}</cbc:ID>
<cbc:Note>Servicio de transporte</cbc:Note>
<cbc:InvoicedQuantity unitCode="{UNIDAD_MEDIDA}">1.0</cbc:InvoicedQuantity>
<cbc:LineExtensionAmount currencyID="COP">{_fmt_valor(valor_unitario)}</cbc:LineExtensionAmount>
<cac:WithholdingTaxTotal>
<cbc:TaxAmount currencyID="COP">{retencion_fmt}</cbc:TaxAmount>
<cac:TaxSubtotal>
<cbc:TaxableAmount currencyID="COP">{_fmt_valor(valor_unitario)}</cbc:TaxableAmount>
<cbc:TaxAmount currencyID="COP">{retencion}</cbc:TaxAmount>
<cac:TaxCategory>
<cbc:Percent>1.00</cbc:Percent>
<cac:TaxScheme>
<cbc:ID>06</cbc:ID>
<cbc:Name>RFTE</cbc:Name>
</cac:TaxScheme>
</cac:TaxCategory>
</cac:TaxSubtotal>
</cac:WithholdingTaxTotal>
<cac:Item>
<cbc:Description>{descripcion_linea}</cbc:Description>
<cac:BuyersItemIdentification>
<cbc:ID schemeAgencyID=""></cbc:ID>
</cac:BuyersItemIdentification>
<cac:SellersItemIdentification>
<cbc:ID>{radicado}</cbc:ID>
<cbc:ExtendedID></cbc:ExtendedID>
</cac:SellersItemIdentification>
<cac:StandardItemIdentification>
<cbc:ID schemeID="999" schemeName="Estándar de adopción del contribuyente" schemeAgencyID="">{consecutivo_remesa}</cbc:ID>
</cac:StandardItemIdentification>
<cac:AdditionalItemProperty>
<cbc:Name>ValorTotalItem</cbc:Name>
<cbc:Value>{_fmt_valor(valor_unitario)}</cbc:Value>
</cac:AdditionalItemProperty>
<cac:AdditionalItemProperty>
<cbc:Name>NumeroLinea</cbc:Name>
<cbc:Value>{idx}</cbc:Value>
</cac:AdditionalItemProperty>
<cac:AdditionalItemProperty>
<cbc:Name>CantidadxPrecioU</cbc:Name>
<cbc:Value>{_fmt_valor(valor_unitario)}</cbc:Value>
</cac:AdditionalItemProperty>
<cac:AdditionalItemProperty>
<cbc:Name>PESO</cbc:Name>
<cbc:Value>{peso}</cbc:Value>
</cac:AdditionalItemProperty>
<cac:AdditionalItemProperty>
<cbc:Name>Unidad</cbc:Name>
<cbc:Value>{UNIDAD_MEDIDA}</cbc:Value>
</cac:AdditionalItemProperty>
<cac:AdditionalItemProperty>
<cbc:Name>01</cbc:Name>
<cbc:Value>{radicado}</cbc:Value>
</cac:AdditionalItemProperty>
<cac:AdditionalItemProperty>
<cbc:Name>02</cbc:Name>
<cbc:Value>{consecutivo_remesa}</cbc:Value>
</cac:AdditionalItemProperty>
<cac:AdditionalItemProperty>
<cbc:Name>03</cbc:Name>
<cbc:Value>{_fmt_valor(valor_unitario)}</cbc:Value>
<cbc:ValueQuantity unitCode="{UNIDAD_MEDIDA}">{peso}</cbc:ValueQuantity>
</cac:AdditionalItemProperty>
</cac:Item>
<cac:Price>
<cbc:PriceAmount currencyID="COP">{_fmt_valor(valor_unitario)}</cbc:PriceAmount>
<cbc:BaseQuantity unitCode="{UNIDAD_MEDIDA}">1.0</cbc:BaseQuantity>
</cac:Price>
</cac:InvoiceLine>"""


def generar_xml(datos, perfil=None):
    """
    Construye el XML completo a partir del diccionario de datos.
    datos = {
        'numero_factura': str,
        'cufe': str,
        'fecha': str  (YYYY-MM-DD),
        'nit_cliente': str,
        'digito_cliente': str,
        'nombre_cliente': str,
        'valor_total': float,
        'fecha_vencimiento': str (YYYY-MM-DD, se calcula automáticamente +30 días),
        'remesas': list of {
            'consecutivo': str,
            'radicado': str,
            'peso': str,
            'valor': float,
            'descripcion_linea': str  (opcional, default: 'Servicio de transporte')
        }
    }
    """
    p          = perfil or PERFILES["ut_tsp"]
    NIT_TSP_11 = p["nit_socio"]
    NOMBRE_TSP = p["nombre_socio"]
    EMAIL_FROM = p["email_from"]
    EMAIL_CONTACT_SUPPLIER = p["email_contact_supplier"]
    CARPETA_SALIDA = p["carpeta"]

    nf         = datos['numero_factura']
    cufe       = datos['cufe']
    fecha      = datos['fecha']
    nit_cli    = datos['nit_cliente']
    dig_cli    = datos['digito_cliente']
    nom_cli    = datos['nombre_cliente']
    email_cli  = "facturacion@drummondltd.com"
    val_total  = datos['valor_total']
    fec_venc   = (datetime.strptime(datos['fecha'], "%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d")
    remesas    = datos['remesas']

    retencion_total = round(val_total * 0.01, 2)
    num_lineas      = len(remesas)

    # Generar bloques InvoiceLine
    lines_xml = "\n".join(
        generar_invoice_line(
            i + 1,
            r['consecutivo'],
            r['radicado'],
            r.get('descripcion_linea', 'Servicio de transporte'),
            r['peso'],
            r['valor'],
        )
        for i, r in enumerate(remesas)
    )

    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2" xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" xmlns:ccts="urn:un:unece:uncefact:data:specification:CoreComponentTypeSchemaModule:2" xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#">
<ext:UBLExtensions>
<ext:UBLExtension>
<ext:ExtensionContent>
<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Id="xmldsig-f21d2ebd-f63e-4025-b5c8-ee7460a38788">
<ds:SignedInfo>
<ds:CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
<ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
<ds:Reference Id="xmldsig-f21d2ebd-f63e-4025-b5c8-ee7460a38788-ref0" URI="">
<ds:Transforms>
<ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
</ds:Transforms>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>7RyuXlB0bUBhKFwbGwoovDGce0WmNKBse0wTUwT0DLM=</ds:DigestValue>
</ds:Reference>
<ds:Reference URI="#xmldsig-f21d2ebd-f63e-4025-b5c8-ee7460a38788-keyinfo">
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>TstDpK3Iu0es302PghLgt8foP0UF5v3rq8IuW84EbPQ=</ds:DigestValue>
</ds:Reference>
<ds:Reference Type="http://uri.etsi.org/01903#SignedProperties" URI="#xmldsig-f21d2ebd-f63e-4025-b5c8-ee7460a38788-signedprops">
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>UuA1UhCn/fszaRNZXN1uZZHx5/j8cGWNAU9qDAERLug=</ds:DigestValue>
</ds:Reference>
</ds:SignedInfo>
<ds:SignatureValue Id="xmldsig-f21d2ebd-f63e-4025-b5c8-ee7460a38788-sigvalue">
QzO9tM3Fhm3fgpftPhUMHtvfzyvhAeO97jd6UqK9aEnjoZHvJVfVfHznD2uidOLq+ZyQMAGDHVEY
rVV5eUdTH/gNNFZL4TTDpk7DZR0QL8SmE98mIcqO/HXTnSmQ0SzmbtXRkMGa57xCP4+HPC24YwsL
hGWyiBuRMYG3c75uqzS5cim2heSlzPtyV3iqAGVB0JwBr1WcJytFjKCCnwh1d3glEPS4XDDL7o22
edSwPp0TUI6MLv1n+J07Ad/wZKAT6WFDn6Iri4wg9Ajf0WP/wtsSJY7jjrw7Ix8DwUfdSlnwNI2o
Pw0cw8RRuLWDitNwt7baMoVjp5A+hFApezbvgg==
</ds:SignatureValue>
<ds:KeyInfo Id="xmldsig-f21d2ebd-f63e-4025-b5c8-ee7460a38788-keyinfo">
<ds:X509Data>
<ds:X509Certificate>
MIIH+zCCBeOgAwIBAgISQ0MxMDQ3NDMwNzAyLTAwMDE0MA0GCSqGSIb3DQEBCwUAMIIBJDEUMBIG
A1UEBQwLOTAwMDMyNzc0LTQxFDASBgNVBC0MCzkwMDAzMjc3NC00MUMwQQYDVQQJDDpTZWUgY3Vy
cmVudCBhZGRyZXNzIGF0IGh0dHBzOi8vbWljZXJ0aWZpY2Fkby5vbGltcGlhaXQuY29tMRUwEwYD
VQQHDAxCb2dvdMOhIEQuQy4xFTATBgNVBAgMDEJvZ290w6EgRC5DLjELMAkGA1UEBhMCQ08xLjAs
BgkqhkiG9w0BCQEMH3NlcnZpY2lvYWxjbGllbnRlQG9saW1waWFpdC5jb20xFjAUBgNVBAsMDU9s
aW1waWFJVCBFQ0QxEjAQBgNVBAoMCU9saW1waWFJVDEaMBgGA1UEAwwRT2xpbXBpYUlUIEVDRCBT
dWIwHhcNMjUwMzI3MTQxMDA2WhcNMjcwMzI3MTQwOTA2WjCCARExCzAJBgNVBAYTAkNPMRYwFAYD
VQQDDAxGQUNUVVJFIFMuQS5TMS4wLAYJKoZIhvcNAQkBFh9mYWN0dXJhY2lvbkBmYWN0dXJlY29s
b21iaWEuY29tMRIwEAYDVQQHDAlDYXJ0YWdlbmExOzA5BgNVBAkMMkJSUiBNQU5HQSBFRCBUT1JS
RSBERU8gUFVFUlRPIEsgMjYgTiAyOCA0NSBPRiAyMjA1MREwDwYDVQQIDAhCb2zDrXZhcjEaMBgG
A1UEDAwRUGVyc29uYSBKdXLDrWRpY2ExEjAQBgNVBC0MCTkwMDM5OTc0MTESMBAGA1UEBQwJOTAw
Mzk5NzQxMRIwEAYDVQRhDAk5MDAzOTk3NDEwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIB
AQCKW6v9iA4aVaffh/G+gDGPE3cdwCyZF3L22KatXFlVYhzLtad9EV/qz6/b5Qdc5VMwRm5JqDJo
YawCS53+Kn9dObKnHwHtSGJYfEbYp7nm5QNvypoNhu0rWtfFqfaR1d/cr6ym2LFsHM1k5spDsFH0
ZbqdyKsqFE908HjIEM28JdoKUm6C2/Qg7VMLyuOjRYiJhXpfZ02oca0AJlGHsOnxmggggWK4DHPb
/3BiSVlG8w4TuJ9PZsqsWFwgPWN3zqWPkruUGmB92NMOg8cMoC1qjFN9JEY2h0dWBDk+PWDWWimd
LDxQvQre3dI5MrfzUjqz/knqxWjdBwA1VfyDlhlJAgMBAAGjggI0MIICMDAfBgNVHSMEGDAWgBTu
tbqLxFW1t7H3c/MgefP+q2eoXjAdBgNVHQ4EFgQUytnharcvQS92YlMmtq2yMBx8O/owCQYDVR0T
BAIwADAPBgNVHQ8BAf8EBQMDANAAMIGIBgNVHSAEgYAwfjB8BgsrBgEEAYONSgIBAjBtMGsGCCsG
AQUFBwIBFl9odHRwczovL21pY2VydGlmaWNhZG8ub2xpbXBpYWl0LmNvbS9yZWN1cnNvcy9hcmNo
aXZvcy9kZWNsYXJhY2lvbmRlcHJhY3RpY2FzZGVjZXJ0aWZpY2FjaW9uLnBkZjApBgNVHREEIjAg
gR5nZXN0aW9uLmNlcnRpZmljYWRvQGVzdGVsYS5jb20wFQYDVR0SBA4wDIIKMjEtRUNELTAwMTA9
BgNVHR8ENjA0MDKgMKAuhixodHRwOi8vY3JsLm9saW1waWFpdC5jb20vb2xpbXBpYWl0ZWNkc3Vi
LmNybDCBxQYIKwYBBQUHAQEEgbgwgbUwNwYIKwYBBQUHMAGGK2h0dHBzOi8vb2NzcGVjZC5vbGlt
cGlhaXQuY29tOjgzNzIvYXBpL29jc3AwegYIKwYBBQUHMAKGbmh0dHBzOi8vbWljZXJ0aWZpY2Fk
by5vbGltcGlhaXQuY29tL2NvbnRlbnQvcmVjdXJzb3MvaG9tZS9pbmljaWFsL2NlcnRpZmljYWRv
cy9TdWJvcmRpbmFkYS9vbGltcGlhaXRlY2RzdWIuY3J0MA0GCSqGSIb3DQEBCwUAA4ICAQCvd4TV
71SCx3uDhzP0WjawRFa7i4rkGgfelSBZi+eOrKPXLYIL/Bv/La4BwDdFOCWNkX9s/OEabTpthrMN
TCuCtDMHgTbzD78j28cJ5dAUbraVX7yv7AURPg3FSRXs/1FbZLRB52GsIAG9B9JHSGp7rl8fOsyL
R0J9FgxV8GFsLl27pUYppnTGVuZtRAZjufvBz6dkftrjgx3SoufG09k7sP3K0Y34M+MLkn9u9LeG
Yl70G+QvLOx3dpTiXbJGDtcPg6ZQ5aeOi7E+SiUmAkJ5baPtvvX1TK+AIrL7arvdi9pWvS9Jz92z
a02GREcS1bZhB4LRHa1V/6swZ/pDUjxs7oKlFcN5zeSQfLtYL9sisBJuY1ueZ4moQWrqBuUVM/Mz
QnUunWYP7paebUltbDuYl8UbwjCZCTco+/KL4zCemZieFGVHomCX4iAMDhxfbr+57LuvgbewKKxu
CfhSM3CEP1x63vPmzDlUcnJRA0uz4bpPiIZkt6f0qLKlIZZJ0XEg4LO5H9r6u7ATQHzqkMSCldGI
KwI1e+khqVsJ/LfAVnZKZlCDrPLrZvElSLXDF7spZpyuaQTrMBocTz9YF++H6ujhwxxgQw==
</ds:X509Certificate>
</ds:X509Data>
</ds:KeyInfo>
<ds:Object>
<xades:QualifyingProperties xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#" Target="#xmldsig-f21d2ebd-f63e-4025-b5c8-ee7460a38788">
<xades:SignedProperties Id="xmldsig-f21d2ebd-f63e-4025-b5c8-ee7460a38788-signedprops">
<xades:SignedSignatureProperties>
<xades:SigningTime>{fecha}T09:38:59.4100753-05:00</xades:SigningTime>
<xades:SigningCertificate>
<xades:Cert>
<xades:CertDigest>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>VKkER7uquxka6rDtbvL+QAohjGVnxmAxMSSTzSog60I=</ds:DigestValue>
</xades:CertDigest>
<xades:IssuerSerial>
<ds:X509IssuerName>CN=OlimpiaIT ECD Sub,O=OlimpiaIT,OU=OlimpiaIT ECD,1.2.840.113549.1.9.1=#0c1f736572766963696f616c636c69656e7465406f6c696d70696169742e636f6d,C=CO,ST=Bogotá D.C.,L=Bogotá D.C.,STREET=See current address at https://micertificado.olimpiait.com,2.5.4.45=#0c0b3930303033323737342d34,2.5.4.5=#0c0b3930303033323737342d34</ds:X509IssuerName>
<ds:X509SerialNumber>5859387458472741076356936367269702597095732</ds:X509SerialNumber>
</xades:IssuerSerial>
</xades:Cert>
</xades:SigningCertificate>
<xades:SignaturePolicyIdentifier>
<xades:SignaturePolicyId>
<xades:SigPolicyId>
<xades:Identifier>https://facturaelectronica.dian.gov.co/politicadefirma/v2/politicadefirmav2.pdf</xades:Identifier>
<xades:Description>Política de firma para facturas electrónicas de la República de Colombia.</xades:Description>
</xades:SigPolicyId>
<xades:SigPolicyHash>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>dMoMvtcG5aIzgYo0tIsSQeVJBDnUnfSOfBpxXrmor0Y=</ds:DigestValue>
</xades:SigPolicyHash>
</xades:SignaturePolicyId>
</xades:SignaturePolicyIdentifier>
<xades:SignerRole>
<xades:ClaimedRoles>
<xades:ClaimedRole>supplier</xades:ClaimedRole>
</xades:ClaimedRoles>
</xades:SignerRole>
</xades:SignedSignatureProperties>
</xades:SignedProperties>
</xades:QualifyingProperties>
</ds:Object>
</ds:Signature>
</ext:ExtensionContent>
</ext:UBLExtension>
</ext:UBLExtensions>
<cbc:UBLVersionID>UBL 2.1</cbc:UBLVersionID>
<cbc:CustomizationID>Documentos adjuntos</cbc:CustomizationID>
<cbc:ProfileID>Factura Electrónica de Venta</cbc:ProfileID>
<cbc:ProfileExecutionID>1</cbc:ProfileExecutionID>
<cbc:ID>{nf}</cbc:ID>
<cbc:IssueDate>{fecha}</cbc:IssueDate>
<cbc:IssueTime>09:38:59-05:00</cbc:IssueTime>
<cbc:DocumentType>Contenedor de Factura Electrónica</cbc:DocumentType>
<cbc:ParentDocumentID>{nf}</cbc:ParentDocumentID>
<cac:SenderParty>
<cac:PartyTaxScheme>
<cbc:RegistrationName>{NOMBRE_UT}</cbc:RegistrationName>
<cbc:CompanyID schemeAgencyID="195" schemeID="1" schemeName="31">{NIT_UT}</cbc:CompanyID>
<cbc:TaxLevelCode listName="No aplica">R-99-PN</cbc:TaxLevelCode>
<cac:TaxScheme>
<cbc:ID>06</cbc:ID>
<cbc:Name>ReteFuente</cbc:Name>
</cac:TaxScheme>
</cac:PartyTaxScheme>
</cac:SenderParty>
<cac:ReceiverParty>
<cac:PartyTaxScheme>
<cbc:RegistrationName>{nom_cli}</cbc:RegistrationName>
<cbc:CompanyID schemeAgencyID="195" schemeID="{dig_cli}" schemeName="31">{nit_cli}</cbc:CompanyID>
<cbc:TaxLevelCode listName="No aplica">R-99-PN</cbc:TaxLevelCode>
<cac:TaxScheme>
<cbc:ID>01</cbc:ID>
<cbc:Name>IVA</cbc:Name>
</cac:TaxScheme>
</cac:PartyTaxScheme>
</cac:ReceiverParty>
<cac:Attachment>
<cac:ExternalReference>
<cbc:MimeCode>text/xml</cbc:MimeCode>
<cbc:EncodingCode>UTF-8</cbc:EncodingCode>
<cbc:Description><![CDATA[<?xml version="1.0" encoding="utf-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" xmlns:ipt="pt:co:facturaelectronica:InteroperabilidadPT-2-1" xmlns:sts="dian:gov:co:facturaelectronica:Structures-2-1" xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2 http://docs.oasis-open.org/ubl/os-UBL-2.1/xsd/maindoc/UBL-Invoice-2.1.xsd">
<ext:UBLExtensions>
<ext:UBLExtension>
<ext:ExtensionContent>
<sts:DianExtensions>
<sts:InvoiceControl>
<sts:InvoiceAuthorization>18764092002504</sts:InvoiceAuthorization>
<sts:AuthorizationPeriod>
<cbc:StartDate>2025-04-15</cbc:StartDate>
<cbc:EndDate>2027-04-15</cbc:EndDate>
</sts:AuthorizationPeriod>
<sts:AuthorizedInvoices>
<sts:Prefix>{PREFIJO}</sts:Prefix>
<sts:From>1</sts:From>
<sts:To>1000</sts:To>
</sts:AuthorizedInvoices>
</sts:InvoiceControl>
<sts:InvoiceSource>
<cbc:IdentificationCode listAgencyID="6" listAgencyName="United Nations Economic Commission for Europe" listSchemeURI="urn:oasis:names:specification:ubl:codelist:gc:CountryIdentificationCode-2.1">CO</cbc:IdentificationCode>
</sts:InvoiceSource>
<sts:SoftwareProvider>
<sts:ProviderID schemeID="7" schemeName="31" schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)">900399741</sts:ProviderID>
<sts:SoftwareID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)">483f5378-e228-440a-b7ed-4942af30dbd7</sts:SoftwareID>
</sts:SoftwareProvider>
<sts:SoftwareSecurityCode schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)">11685e374ff7e8223750f80109947e240a38bdc67b935967b63b5f077b43829a875a4f246f68ae043717919b7a37acff</sts:SoftwareSecurityCode>
<sts:AuthorizationProvider>
<sts:AuthorizationProviderID schemeID="4" schemeName="31" schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)">800197268</sts:AuthorizationProviderID>
</sts:AuthorizationProvider>
<sts:QRCode>https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey={cufe}</sts:QRCode>
</sts:DianExtensions>
</ext:ExtensionContent>
</ext:UBLExtension>
<ext:UBLExtension>
<ext:ExtensionContent>
<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Id="xmldsig-05200dfc-fa80-463b-886a-9498e1dfbcbe">
<ds:SignedInfo>
<ds:CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315" />
<ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256" />
<ds:Reference Id="xmldsig-05200dfc-fa80-463b-886a-9498e1dfbcbe-ref0" URI="">
<ds:Transforms>
<ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature" />
</ds:Transforms>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" />
<ds:DigestValue>PPfGnvbzx2wGyQAd6F22OljaQ9UUFeM3wG4NHfwFZGw=</ds:DigestValue>
</ds:Reference>
<ds:Reference URI="#xmldsig-05200dfc-fa80-463b-886a-9498e1dfbcbe-keyinfo">
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" />
<ds:DigestValue>0wzM9b3mwIoRPrG+YIhtVCudn38rIiITZb8nEAFUuhU=</ds:DigestValue>
</ds:Reference>
<ds:Reference Type="http://uri.etsi.org/01903#SignedProperties" URI="#xmldsig-05200dfc-fa80-463b-886a-9498e1dfbcbe-signedprops">
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" />
<ds:DigestValue>bwCBvs/Qd3ZpKqqyaUzMfXAmWEGlBzAVFvqroIWj5iI=</ds:DigestValue>
</ds:Reference>
</ds:SignedInfo>
<ds:SignatureValue Id="xmldsig-05200dfc-fa80-463b-886a-9498e1dfbcbe-sigvalue">
RRrnd78cwZLOnwqh0S07e0l0QVwFRfyabrUyb1LzWpZ2gSzrZjKmPZPIVbjLiU1lhMdDEs7sBNWV
EGabjGwLV7VtMP8EY8SnAymVj7UK43PvsT+8AGKWr5haFXeHgit5yc6XCNrWYBIe/z3U3iXCRAPI
oYqDLYyCdsutDtCWrWCxAhd37twaIwy5HetVGSKJR3r8xMl8zBZMxQmc00zzNbK4kZoNONXpZ2Lh
vmqU/BzMpFfIsCyWB8ZTUyt5rwqLAilIFaqigFpjndqmyI3YYOtfZQP63z746FW0YXs8EOTg+wY+
KSLzVFkgvsfAmpGTCEbhpDthfyFQC0wLUEViHg==
</ds:SignatureValue>
<ds:KeyInfo Id="xmldsig-05200dfc-fa80-463b-886a-9498e1dfbcbe-keyinfo">
<ds:X509Data>
<ds:X509Certificate>
MIIH+zCCBeOgAwIBAgISQ0MxMDQ3NDMwNzAyLTAwMDE0MA0GCSqGSIb3DQEBCwUAMIIBJDEUMBIG
A1UEBQwLOTAwMDMyNzc0LTQxFDASBgNVBC0MCzkwMDAzMjc3NC00MUMwQQYDVQQJDDpTZWUgY3Vy
cmVudCBhZGRyZXNzIGF0IGh0dHBzOi8vbWljZXJ0aWZpY2Fkby5vbGltcGlhaXQuY29tMRUwEwYD
VQQHDAxCb2dvdMOhIEQuQy4xFTATBgNVBAgMDEJvZ290w6EgRC5DLjELMAkGA1UEBhMCQ08xLjAs
BgkqhkiG9w0BCQEMH3NlcnZpY2lvYWxjbGllbnRlQG9saW1waWFpdC5jb20xFjAUBgNVBAsMDU9s
aW1waWFJVCBFQ0QxEjAQBgNVBAoMCU9saW1waWFJVDEaMBgGA1UEAwwRT2xpbXBpYUlUIEVDRCBT
dWIwHhcNMjUwMzI3MTQxMDA2WhcNMjcwMzI3MTQwOTA2WjCCARExCzAJBgNVBAYTAkNPMRYwFAYD
VQQDDAxGQUNUVVJFIFMuQS5TMS4wLAYJKoZIhvcNAQkBFh9mYWN0dXJhY2lvbkBmYWN0dXJlY29s
b21iaWEuY29tMRIwEAYDVQQHDAlDYXJ0YWdlbmExOzA5BgNVBAkMMkJSUiBNQU5HQSBFRCBUT1JS
RSBERU8gUFVFUlRPIEsgMjYgTiAyOCA0NSBPRiAyMjA1MREwDwYDVQQIDAhCb2zDrXZhcjEaMBgG
A1UEDAwRUGVyc29uYSBKdXLDrWRpY2ExEjAQBgNVBC0MCTkwMDM5OTc0MTESMBAGA1UEBQwJOTAw
Mzk5NzQxMRIwEAYDVQRhDAk5MDAzOTk3NDEwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIB
AQCKW6v9iA4aVaffh/G+gDGPE3cdwCyZF3L22KatXFlVYhzLtad9EV/qz6/b5Qdc5VMwRm5JqDJo
YawCS53+Kn9dObKnHwHtSGJYfEbYp7nm5QNvypoNhu0rWtfFqfaR1d/cr6ym2LFsHM1k5spDsFH0
ZbqdyKsqFE908HjIEM28JdoKUm6C2/Qg7VMLyuOjRYiJhXpfZ02oca0AJlGHsOnxmggggWK4DHPb
/3BiSVlG8w4TuJ9PZsqsWFwgPWN3zqWPkruUGmB92NMOg8cMoC1qjFN9JEY2h0dWBDk+PWDWWimd
LDxQvQre3dI5MrfzUjqz/knqxWjdBwA1VfyDlhlJAgMBAAGjggI0MIICMDAfBgNVHSMEGDAWgBTu
tbqLxFW1t7H3c/MgefP+q2eoXjAdBgNVHQ4EFgQUytnharcvQS92YlMmtq2yMBx8O/owCQYDVR0T
BAIwADAPBgNVHQ8BAf8EBQMDANAAMIGIBgNVHSAEgYAwfjB8BgsrBgEEAYONSgIBAjBtMGsGCCsG
AQUFBwIBFl9odHRwczovL21pY2VydGlmaWNhZG8ub2xpbXBpYWl0LmNvbS9yZWN1cnNvcy9hcmNo
aXZvcy9kZWNsYXJhY2lvbmRlcHJhY3RpY2FzZGVjZXJ0aWZpY2FjaW9uLnBkZjApBgNVHREEIjAg
gR5nZXN0aW9uLmNlcnRpZmljYWRvQGVzdGVsYS5jb20wFQYDVR0SBA4wDIIKMjEtRUNELTAwMTA9
BgNVHR8ENjA0MDKgMKAuhixodHRwOi8vY3JsLm9saW1waWFpdC5jb20vb2xpbXBpYWl0ZWNkc3Vi
LmNybDCBxQYIKwYBBQUHAQEEgbgwgbUwNwYIKwYBBQUHMAGGK2h0dHBzOi8vb2NzcGVjZC5vbGlt
cGlhaXQuY29tOjgzNzIvYXBpL29jc3AwegYIKwYBBQUHMAKGbmh0dHBzOi8vbWljZXJ0aWZpY2Fk
by5vbGltcGlhaXQuY29tL2NvbnRlbnQvcmVjdXJzb3MvaG9tZS9pbmljaWFsL2NlcnRpZmljYWRv
cy9TdWJvcmRpbmFkYS9vbGltcGlhaXRlY2RzdWIuY3J0MA0GCSqGSIb3DQEBCwUAA4ICAQCvd4TV
71SCx3uDhzP0WjawRFa7i4rkGgfelSBZi+eOrKPXLYIL/Bv/La4BwDdFOCWNkX9s/OEabTpthrMN
TCuCtDMHgTbzD78j28cJ5dAUbraVX7yv7AURPg3FSRXs/1FbZLRB52GsIAG9B9JHSGp7rl8fOsyL
R0J9FgxV8GFsLl27pUYppnTGVuZtRAZjufvBz6dkftrjgx3SoufG09k7sP3K0Y34M+MLkn9u9LeG
Yl70G+QvLOx3dpTiXbJGDtcPg6ZQ5aeOi7E+SiUmAkJ5baPtvvX1TK+AIrL7arvdi9pWvS9Jz92z
a02GREcS1bZhB4LRHa1V/6swZ/pDUjxs7oKlFcN5zeSQfLtYL9sisBJuY1ueZ4moQWrqBuUVM/Mz
QnUunWYP7paebUltbDuYl8UbwjCZCTco+/KL4zCemZieFGVHomCX4iAMDhxfbr+57LuvgbewKKxu
CfhSM3CEP1x63vPmzDlUcnJRA0uz4bpPiIZkt6f0qLKlIZZJ0XEg4LO5H9r6u7ATQHzqkMSCldGI
KwI1e+khqVsJ/LfAVnZKZlCDrPLrZvElSLXDF7spZpyuaQTrMBocTz9YF++H6ujhwxxgQw==
</ds:X509Certificate>
</ds:X509Data>
</ds:KeyInfo>
<ds:Object>
<xades:QualifyingProperties xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#" Target="#xmldsig-05200dfc-fa80-463b-886a-9498e1dfbcbe">
<xades:SignedProperties Id="xmldsig-05200dfc-fa80-463b-886a-9498e1dfbcbe-signedprops">
<xades:SignedSignatureProperties>
<xades:SigningTime>{fecha}T18:30:11.724273-05:00</xades:SigningTime>
<xades:SigningCertificate>
<xades:Cert>
<xades:CertDigest>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" />
<ds:DigestValue>VKkER7uquxka6rDtbvL+QAohjGVnxmAxMSSTzSog60I=</ds:DigestValue>
</xades:CertDigest>
<xades:IssuerSerial>
<ds:X509IssuerName>CN=OlimpiaIT ECD Sub,O=OlimpiaIT,OU=OlimpiaIT ECD,1.2.840.113549.1.9.1=#0c1f736572766963696f616c636c69656e7465406f6c696d70696169742e636f6d,C=CO,ST=Bogotá D.C.,L=Bogotá D.C.,STREET=See current address at https://micertificado.olimpiait.com,2.5.4.45=#0c0b3930303033323737342d34,2.5.4.5=#0c0b3930303033323737342d34</ds:X509IssuerName>
<ds:X509SerialNumber>5859387458472741076356936367269702597095732</ds:X509SerialNumber>
</xades:IssuerSerial>
</xades:Cert>
</xades:SigningCertificate>
<xades:SignaturePolicyIdentifier>
<xades:SignaturePolicyId>
<xades:SigPolicyId>
<xades:Identifier>https://facturaelectronica.dian.gov.co/politicadefirma/v2/politicadefirmav2.pdf</xades:Identifier>
<xades:Description>Política de firma para facturas electrónicas de la República de Colombia.</xades:Description>
</xades:SigPolicyId>
<xades:SigPolicyHash>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" />
<ds:DigestValue>dMoMvtcG5aIzgYo0tIsSQeVJBDnUnfSOfBpxXrmor0Y=</ds:DigestValue>
</xades:SigPolicyHash>
</xades:SignaturePolicyId>
</xades:SignaturePolicyIdentifier>
<xades:SignerRole>
<xades:ClaimedRoles>
<xades:ClaimedRole>supplier</xades:ClaimedRole>
</xades:ClaimedRoles>
</xades:SignerRole>
</xades:SignedSignatureProperties>
</xades:SignedProperties>
</xades:QualifyingProperties>
</ds:Object>
</ds:Signature>
</ext:ExtensionContent>
</ext:UBLExtension>
<ext:UBLExtension>
<ext:ExtensionContent>
<NotificationPreferences>
<NotifyPreferences>
<NotifyPreference>
<NotificationType>Mail</NotificationType>
<Destinations>
<Destination>
<Tos>
<To>{email_cli}</To>
</Tos>
</Destination>
</Destinations>
<From>{EMAIL_FROM}</From>
</NotifyPreference>
</NotifyPreferences>
</NotificationPreferences>
</ext:ExtensionContent>
</ext:UBLExtension>
<ext:UBLExtension>
<ext:ExtensionContent>
<CustomFieldRowsExtension />
</ext:ExtensionContent>
</ext:UBLExtension>
<ext:UBLExtension>
<ext:ExtensionContent>
<CustomFieldExtension>
<CustomField Name="SubtoAmount" Value="{_fmt_valor(val_total)}" />
<CustomField Name="AllowanceAmount" Value="" />
<CustomField Name="ChargeAmount" Value="" />
<CustomField Name="TotalDescuentos" Value="0" />
<CustomField Name="TotalRetenciones" Value="{_fmt_valor(retencion_total)}" />
<CustomField Name="TotalImpuestos" Value="0" />
<CustomField Name="MonedaFacturada" Value="COP" />
<CustomField Name="Prefijo" Value="{PREFIJO}" />
<CustomField Name="NombreCiudadEmisor" Value="Barranquilla" />
<CustomField Name="NombreDepartamentoEmisor" Value="Atlantico" />
<CustomField Name="FORMATOIMPRESION" Value="1" />
<CustomField Name="lugarExpedicion" Value="SANTAMARTA_TSP" />
<CustomField Name="tituloValorFactura" Value="ESTA FACTURA ES UN TITULO VALOR. CUMPLIENDO REQUISITOS DE LA LEY 1231 DE 2008. " />
</CustomFieldExtension>
</ext:ExtensionContent>
</ext:UBLExtension>
</ext:UBLExtensions>
<cbc:UBLVersionID>UBL 2.1</cbc:UBLVersionID>
<cbc:CustomizationID>12</cbc:CustomizationID>
<cbc:ProfileID>DIAN 2.1: Factura Electrónica de Venta</cbc:ProfileID>
<cbc:ProfileExecutionID>1</cbc:ProfileExecutionID>
<cbc:ID>{nf}</cbc:ID>
<cbc:UUID schemeID="1" schemeName="CUFE-SHA384">{cufe}</cbc:UUID>
<cbc:IssueDate>{fecha}</cbc:IssueDate>
<cbc:IssueTime>18:00:12-05:00</cbc:IssueTime>
<cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode>
<cbc:Note>Servicio de transporte</cbc:Note>
<cbc:DocumentCurrencyCode>COP</cbc:DocumentCurrencyCode>
<cbc:LineCountNumeric>{num_lineas}</cbc:LineCountNumeric>
<cac:OrderReference>
<cbc:ID>NA</cbc:ID>
</cac:OrderReference>
<cac:AccountingSupplierParty>
<cbc:AdditionalAccountID schemeAgencyID="195">1</cbc:AdditionalAccountID>
<cac:Party>
<cbc:IndustryClassificationCode>4923</cbc:IndustryClassificationCode>
<cac:PartyName>
<cbc:Name>{NOMBRE_UT}</cbc:Name>
</cac:PartyName>
<cac:PhysicalLocation>
<cac:Address>
<cbc:ID>47001</cbc:ID>
<cbc:CityName>SANTA MARTA</cbc:CityName>
<cbc:PostalZone />
<cbc:CountrySubentity>Magdalena</cbc:CountrySubentity>
<cbc:CountrySubentityCode>47</cbc:CountrySubentityCode>
<cac:AddressLine>
<cbc:Line>CR 1 C 22 58 P 11 ED BAHIA CENTRO SANTA MARTA  </cbc:Line>
</cac:AddressLine>
<cac:Country>
<cbc:IdentificationCode>CO</cbc:IdentificationCode>
<cbc:Name languageID="es">COLOMBIA</cbc:Name>
</cac:Country>
</cac:Address>
</cac:PhysicalLocation>
<cac:PartyTaxScheme>
<cbc:RegistrationName>{NOMBRE_UT}</cbc:RegistrationName>
<cbc:CompanyID schemeID="1" schemeName="31" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeAgencyID="195">{NIT_UT}</cbc:CompanyID>
<cbc:TaxLevelCode listName="No aplica">R-99-PN</cbc:TaxLevelCode>
<cac:RegistrationAddress>
<cbc:ID>47001</cbc:ID>
<cbc:CityName>SANTA MARTA</cbc:CityName>
<cbc:CountrySubentity>Magdalena</cbc:CountrySubentity>
<cbc:CountrySubentityCode>47</cbc:CountrySubentityCode>
<cac:AddressLine>
<cbc:Line>CR 1 C 22 58 P 11 ED BAHIA CENTRO SANTA MARTA  </cbc:Line>
</cac:AddressLine>
<cac:Country>
<cbc:IdentificationCode>CO</cbc:IdentificationCode>
<cbc:Name languageID="es">COLOMBIA</cbc:Name>
</cac:Country>
</cac:RegistrationAddress>
<cac:TaxScheme>
<cbc:ID>06</cbc:ID>
<cbc:Name>ReteFuente</cbc:Name>
</cac:TaxScheme>
</cac:PartyTaxScheme>
<cac:PartyLegalEntity>
<cbc:RegistrationName>{NOMBRE_UT}</cbc:RegistrationName>
<cbc:CompanyID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="1" schemeName="31">{NIT_UT}</cbc:CompanyID>
<cac:CorporateRegistrationScheme>
<cbc:ID>{PREFIJO}</cbc:ID>
<cbc:Name />
</cac:CorporateRegistrationScheme>
<cac:ShareholderParty>
<cbc:PartecipationPercent>50</cbc:PartecipationPercent>
<cac:Party>
<cac:PartyTaxScheme>
<cbc:RegistrationName>{NOMBRE_TSP}</cbc:RegistrationName>
<cbc:CompanyID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="1">{NIT_TSP_11}</cbc:CompanyID>
<cbc:TaxLevelCode listName="04">R-99-PN</cbc:TaxLevelCode>
<cac:TaxScheme>
<cbc:ID>01</cbc:ID>
<cbc:Name>IVA</cbc:Name>
</cac:TaxScheme>
</cac:PartyTaxScheme>
</cac:Party>
</cac:ShareholderParty>
<cac:ShareholderParty>
<cbc:PartecipationPercent>50</cbc:PartecipationPercent>
<cac:Party>
<cac:PartyTaxScheme>
<cbc:RegistrationName>{NOMBRE_UT}</cbc:RegistrationName>
<cbc:CompanyID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="1">{NIT_UT}</cbc:CompanyID>
<cbc:TaxLevelCode listName="04">R-99-PN</cbc:TaxLevelCode>
<cac:TaxScheme>
<cbc:ID>01</cbc:ID>
<cbc:Name>IVA</cbc:Name>
</cac:TaxScheme>
</cac:PartyTaxScheme>
</cac:Party>
</cac:ShareholderParty>
</cac:PartyLegalEntity>
<cac:Contact>
<cbc:Name>VANESSA  CELIS</cbc:Name>
<cbc:Telephone>3216208110</cbc:Telephone>
<cbc:ElectronicMail>{EMAIL_CONTACT_SUPPLIER}</cbc:ElectronicMail>
</cac:Contact>
</cac:Party>
</cac:AccountingSupplierParty>
<cac:AccountingCustomerParty>
<cbc:AdditionalAccountID>1</cbc:AdditionalAccountID>
<cac:Party>
<cac:PartyIdentification>
<cbc:ID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeName="31" schemeID="{dig_cli}">{nit_cli}</cbc:ID>
</cac:PartyIdentification>
<cac:PartyName>
<cbc:Name>{nom_cli}</cbc:Name>
</cac:PartyName>
<cac:PhysicalLocation>
<cac:Address>
<cbc:ID>11001000</cbc:ID>
<cbc:CityName>BOGOTA</cbc:CityName>
<cbc:PostalZone></cbc:PostalZone>
<cbc:CountrySubentity>CUN</cbc:CountrySubentity>
<cbc:CountrySubentityCode>11</cbc:CountrySubentityCode>
<cac:AddressLine>
<cbc:Line>CALLE 72 N 10 07 OF 1302</cbc:Line>
</cac:AddressLine>
<cac:Country>
<cbc:IdentificationCode>CO</cbc:IdentificationCode>
<cbc:Name languageID="es">COLOMBIA</cbc:Name>
</cac:Country>
</cac:Address>
</cac:PhysicalLocation>
<cac:PartyTaxScheme>
<cbc:RegistrationName>{nom_cli}</cbc:RegistrationName>
<cbc:CompanyID schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeAgencyID="195" schemeName="31" schemeID="{dig_cli}">{nit_cli}</cbc:CompanyID>
<cbc:TaxLevelCode listName="">R-99-PN</cbc:TaxLevelCode>
<cac:TaxScheme>
<cbc:ID>01</cbc:ID>
<cbc:Name>IVA</cbc:Name>
</cac:TaxScheme>
</cac:PartyTaxScheme>
<cac:PartyLegalEntity>
<cbc:RegistrationName>{nom_cli}</cbc:RegistrationName>
<cbc:CompanyID schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeAgencyID="195" schemeName="31" schemeID="{dig_cli}">{nit_cli}</cbc:CompanyID>
<cac:CorporateRegistrationScheme>
<cbc:ID>{PREFIJO}</cbc:ID>
<cbc:Name></cbc:Name>
</cac:CorporateRegistrationScheme>
</cac:PartyLegalEntity>
<cac:Contact>
<cbc:Name></cbc:Name>
<cbc:Telephone></cbc:Telephone>
<cbc:Telefax></cbc:Telefax>
<cbc:ElectronicMail>{email_cli}</cbc:ElectronicMail>
<cbc:Note></cbc:Note>
</cac:Contact>
</cac:Party>
</cac:AccountingCustomerParty>
<cac:PaymentMeans>
<cbc:ID>2</cbc:ID>
<cbc:PaymentMeansCode>31</cbc:PaymentMeansCode>
<cbc:PaymentDueDate>{fec_venc}</cbc:PaymentDueDate>
</cac:PaymentMeans>
<cac:WithholdingTaxTotal>
<cbc:TaxAmount currencyID="COP">{_fmt_valor(retencion_total)}</cbc:TaxAmount>
<cac:TaxSubtotal>
<cbc:TaxableAmount currencyID="COP">{_fmt_valor(val_total)}</cbc:TaxableAmount>
<cbc:TaxAmount currencyID="COP">{_fmt_valor(retencion_total)}</cbc:TaxAmount>
<cac:TaxCategory>
<cbc:Percent>1.00</cbc:Percent>
<cac:TaxScheme>
<cbc:ID>06</cbc:ID>
<cbc:Name>RFTE</cbc:Name>
</cac:TaxScheme>
</cac:TaxCategory>
</cac:TaxSubtotal>
</cac:WithholdingTaxTotal>
<cac:LegalMonetaryTotal>
<cbc:LineExtensionAmount currencyID="COP">{_fmt_valor(val_total)}</cbc:LineExtensionAmount>
<cbc:TaxExclusiveAmount currencyID="COP">0</cbc:TaxExclusiveAmount>
<cbc:TaxInclusiveAmount currencyID="COP">{_fmt_valor(val_total)}</cbc:TaxInclusiveAmount>
<cbc:AllowanceTotalAmount currencyID="COP">0.00</cbc:AllowanceTotalAmount>
<cbc:ChargeTotalAmount currencyID="COP">0.00</cbc:ChargeTotalAmount>
<cbc:PayableRoundingAmount currencyID="COP">0</cbc:PayableRoundingAmount>
<cbc:PayableAmount currencyID="COP">{_fmt_valor(val_total)}</cbc:PayableAmount>
</cac:LegalMonetaryTotal>
{lines_xml}
</Invoice>]]></cbc:Description>
</cac:ExternalReference>
</cac:Attachment>
<cac:ParentDocumentLineReference>
<cbc:LineID>1</cbc:LineID>
<cac:DocumentReference>
<cbc:ID>{nf}</cbc:ID>
<cbc:UUID schemeName="CUFE-SHA384">{cufe}</cbc:UUID>
<cbc:IssueDate>{fecha}</cbc:IssueDate>
<cbc:DocumentType>ApplicationResponse</cbc:DocumentType>
<cac:Attachment>
<cac:ExternalReference>
<cbc:MimeCode>text/xml</cbc:MimeCode>
<cbc:EncodingCode>UTF-8</cbc:EncodingCode>
<cbc:Description><![CDATA[<?xml version="1.0" encoding="utf-8" standalone="no"?>
<ApplicationResponse xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" xmlns:sts="dian:gov:co:facturaelectronica:Structures-2-1" xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns="urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2">
<cbc:UBLVersionID>UBL 2.1</cbc:UBLVersionID>
<cbc:CustomizationID>1</cbc:CustomizationID>
<cbc:ProfileID>DIAN 2.1</cbc:ProfileID>
<cbc:ProfileExecutionID>1</cbc:ProfileExecutionID>
<cbc:IssueDate>{fecha}</cbc:IssueDate>
<cbc:IssueTime>18:30:12-05:00</cbc:IssueTime>
<cac:SenderParty>
<cac:PartyTaxScheme>
<cbc:RegistrationName>Unidad Especial Dirección de Impuestos y Aduanas Nacionales</cbc:RegistrationName>
<cbc:CompanyID schemeID="4" schemeName="31">800197268</cbc:CompanyID>
<cac:TaxScheme>
<cbc:ID>01</cbc:ID>
<cbc:Name>IVA</cbc:Name>
</cac:TaxScheme>
</cac:PartyTaxScheme>
</cac:SenderParty>
<cac:ReceiverParty>
<cac:PartyTaxScheme>
<cbc:RegistrationName>{NOMBRE_UT}</cbc:RegistrationName>
<cbc:CompanyID schemeID="1" schemeName="31">{NIT_UT}</cbc:CompanyID>
<cac:TaxScheme>
<cbc:ID>01</cbc:ID>
<cbc:Name>IVA</cbc:Name>
</cac:TaxScheme>
</cac:PartyTaxScheme>
</cac:ReceiverParty>
<cac:DocumentResponse>
<cac:Response>
<cbc:ResponseCode>02</cbc:ResponseCode>
<cbc:Description>Documento validado por la DIAN</cbc:Description>
</cac:Response>
<cac:DocumentReference>
<cbc:ID>{nf}</cbc:ID>
<cbc:UUID schemeName="CUFE-SHA384">{cufe}</cbc:UUID>
</cac:DocumentReference>
<cac:LineResponse>
<cac:LineReference>
<cbc:LineID>1</cbc:LineID>
</cac:LineReference>
<cac:Response>
<cbc:ResponseCode>0000</cbc:ResponseCode>
<cbc:Description>0</cbc:Description>
</cac:Response>
</cac:LineResponse>
</cac:DocumentResponse>
</ApplicationResponse>]]></cbc:Description>
</cac:ExternalReference>
</cac:Attachment>
<cac:ResultOfVerification>
<cbc:ValidatorID>Unidad Especial Dirección de Impuestos y Aduanas Nacionales</cbc:ValidatorID>
<cbc:ValidationResultCode>02</cbc:ValidationResultCode>
<cbc:ValidationDate>{fecha}</cbc:ValidationDate>
<cbc:ValidationTime>13:30:12-05:00</cbc:ValidationTime>
</cac:ResultOfVerification>
</cac:DocumentReference>
</cac:ParentDocumentLineReference>
</AttachedDocument>"""

    return xml
