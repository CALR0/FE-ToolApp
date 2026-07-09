#!/usr/bin/env python3
"""
Reconstruccion de facturas UBL (DIAN) - modulo de transformaciones.

Transformaciones sobre el Invoice embebido en el CDATA:
  1. Shareholders: inserta socio 50% + UT 50% en PartyLegalEntity del supplier
  2. ValueQuantity unitCode: 94 -> KGM  (InvoicedQuantity y BaseQuantity se respetan)
  3. PartyIdentification del Customer: agrega bloque si no existe
  4. Contact del Customer: reemplaza por version completa (Name, Telefax, Note)
  5. RegistrationAddress del Customer: elimina (range_data no lo tiene)
  6. NotificationPreferences: reemplaza por version del socio (correo + From)
  7. WithholdingTaxTotal / InvoiceLine: elimina namespace xmlns redundante
  8. PaymentMeansCode: ZZZ -> 31
  9. PayableRoundingAmount: agrega si no existe (antes de PayableAmount)
  10. PrepaidAmount: elimina
  11. Consecutivo remesa (Name=02): prefija con 0 si perfil lo requiere (UT Elogia)
"""

import re
from pathlib import Path


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def extraer_numero_factura(nombre):
    m = re.search(r'\;(\d+)\;', nombre)
    if m:
        return m.group(1)
    m = re.search(r'(\d{4,})', nombre)
    return m.group(1) if m else None


def _extraer_datos_customer_del_invoice(inv):
    """
    Lee del AccountingCustomerParty del Invoice original:
      - nit_customer:       CompanyID dentro de PartyTaxScheme
      - scheme_id_customer: schemeID del CompanyID
      - email_customer:     ElectronicMail dentro de Contact
      - telefono_customer:  Telephone dentro de Contact
    Retorna un dict (valores None si no se encuentran).
    """
    datos = {'nit_customer': None, 'scheme_id_customer': '31',
             'email_customer': None, 'telefono_customer': None}

    cust_start = inv.find('<cac:AccountingCustomerParty')
    cust_end   = inv.find('</cac:AccountingCustomerParty>', cust_start)
    if cust_start == -1:
        return datos
    cust = inv[cust_start:cust_end]

    m = re.search(r'<cbc:CompanyID[^>]*schemeID="([^"]*)"[^>]*>(\d+)</cbc:CompanyID>', cust)
    if m:
        datos['scheme_id_customer'] = m.group(1)
        datos['nit_customer']       = m.group(2)
    else:
        m = re.search(r'<cbc:CompanyID[^>]*>(\d+)</cbc:CompanyID>', cust)
        if m:
            datos['nit_customer'] = m.group(1)

    contact_start = cust.find('<cac:Contact>')
    contact_end   = cust.find('</cac:Contact>', contact_start)
    if contact_start != -1:
        contact = cust[contact_start:contact_end]
        m = re.search(r'<cbc:ElectronicMail>([^<]+)</cbc:ElectronicMail>', contact)
        if m:
            datos['email_customer'] = m.group(1)
        m = re.search(r'<cbc:Telephone>([^<]+)</cbc:Telephone>', contact)
        if m:
            datos['telefono_customer'] = m.group(1)

    return datos


def _reemplazar_invoice(contenido_xml, transformar_fn):
    """Extrae el Invoice del CDATA, aplica transformar_fn y reinserta el resultado."""
    m = re.search(r'(<!\[CDATA\[)(.*?)(\]\]>)', contenido_xml, re.DOTALL)
    if not m:
        return contenido_xml
    inv_nuevo = transformar_fn(m.group(2))
    return contenido_xml[:m.start(2)] + inv_nuevo + contenido_xml[m.end(2):]


# ------------------------------------------------------------------------------
# Transformaciones sobre el Invoice embebido
# ------------------------------------------------------------------------------

def _t_shareholders(inv, nit_sp, nombre_sp, nit_ut, nombre_ut):
    """Inserta ShareholderParty dentro del PartyLegalEntity del supplier."""
    if '<cac:ShareholderParty>' in inv:
        return inv
    bloque = (
        f'<cac:ShareholderParty>'
        f'<cbc:PartecipationPercent>50</cbc:PartecipationPercent>'
        f'<cac:Party><cac:PartyTaxScheme>'
        f'<cbc:RegistrationName>{nombre_sp}</cbc:RegistrationName>'
        f'<cbc:CompanyID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Direcci\u00f3n de Impuestos y Aduanas Nacionales)" schemeID="1">{nit_sp}</cbc:CompanyID>'
        f'<cbc:TaxLevelCode listName="04">R-99-PN</cbc:TaxLevelCode>'
        f'<cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>'
        f'</cac:PartyTaxScheme></cac:Party></cac:ShareholderParty>'
        f'<cac:ShareholderParty>'
        f'<cbc:PartecipationPercent>50</cbc:PartecipationPercent>'
        f'<cac:Party><cac:PartyTaxScheme>'
        f'<cbc:RegistrationName>{nombre_ut}</cbc:RegistrationName>'
        f'<cbc:CompanyID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Direcci\u00f3n de Impuestos y Aduanas Nacionales)" schemeID="1">{nit_ut}</cbc:CompanyID>'
        f'<cbc:TaxLevelCode listName="04">R-99-PN</cbc:TaxLevelCode>'
        f'<cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>'
        f'</cac:PartyTaxScheme></cac:Party></cac:ShareholderParty>'
    )
    ancla = '<cac:CorporateRegistrationScheme><cbc:ID>41</cbc:ID><cbc:Name /></cac:CorporateRegistrationScheme>'
    if ancla in inv:
        return inv.replace(ancla, ancla + bloque, 1)
    print("[!] Ancla para shareholders no encontrada")
    return inv


def _t_value_quantity(inv):
    """Corrige unitCode solo en ValueQuantity: 94 -> KGM."""
    return inv.replace('<cbc:ValueQuantity unitCode="94">', '<cbc:ValueQuantity unitCode="KGM">')


def _t_party_identification_customer(inv, nit_customer, scheme_id="31"):
    """Agrega PartyIdentification al Customer si no existe."""
    if '<cac:PartyIdentification>' in inv:
        return inv
    bloque = (
        f'<cac:PartyIdentification>'
        f'<cbc:ID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Direcci\u00f3n de Impuestos y Aduanas Nacionales)"'
        f' schemeName="31" schemeID="{scheme_id}">{nit_customer}</cbc:ID>'
        f'</cac:PartyIdentification>'
    )
    cust_start = inv.find('<cac:AccountingCustomerParty')
    if cust_start == -1:
        return inv
    pn_pos = inv.find('<cac:PartyName>', cust_start)
    if pn_pos == -1:
        return inv
    return inv[:pn_pos] + bloque + inv[pn_pos:]


def _t_contact_customer(inv, email_customer, telefono_customer):
    """Reemplaza Contact del Customer por version completa (Name, Telefax, Note)."""
    viejo = (
        f'<cac:Contact><cbc:Telephone>{telefono_customer}</cbc:Telephone>'
        f'<cbc:ElectronicMail>{email_customer}</cbc:ElectronicMail></cac:Contact>'
    )
    nuevo = (
        f'<cac:Contact>'
        f'<cbc:Name></cbc:Name>'
        f'<cbc:Telephone>{telefono_customer}</cbc:Telephone>'
        f'<cbc:Telefax></cbc:Telefax>'
        f'<cbc:ElectronicMail>{email_customer}</cbc:ElectronicMail>'
        f'<cbc:Note></cbc:Note>'
        f'</cac:Contact>'
    )
    if viejo in inv:
        return inv.replace(viejo, nuevo, 1)
    return re.sub(
        r'(<cac:AccountingCustomerParty>.*?)(<cac:Contact>)(.*?)(</cac:Contact>)',
        lambda m: m.group(1) + '<cac:Contact><cbc:Name></cbc:Name>' +
                  re.sub(r'<cbc:ElectronicMail>', '<cbc:Telefax></cbc:Telefax><cbc:ElectronicMail>', m.group(3)) +
                  '<cbc:Note></cbc:Note></cac:Contact>',
        inv, count=1, flags=re.DOTALL
    )


def _t_eliminar_registration_address_customer(inv):
    """Elimina el bloque RegistrationAddress del Customer."""
    cust_start = inv.find('<cac:AccountingCustomerParty')
    cust_end   = inv.find('</cac:AccountingCustomerParty>', cust_start)
    if cust_start == -1:
        return inv
    cust = inv[cust_start:cust_end]
    ra_start = cust.find('<cac:RegistrationAddress>')
    if ra_start == -1:
        return inv
    ra_end = cust.find('</cac:RegistrationAddress>') + len('</cac:RegistrationAddress>')
    return inv[:cust_start] + cust[:ra_start] + cust[ra_end:] + inv[cust_end:]


def _t_notification_preferences(inv, email_customer, email_from_sp):
    """Reemplaza NotificationPreferences por la version del socio."""
    np_start = inv.find('<NotificationPreferences>')
    np_end   = inv.find('</NotificationPreferences>') + len('</NotificationPreferences>')
    if np_start == -1:
        return inv
    nuevo = (
        f'<NotificationPreferences>'
        f'<NotifyPreferences>'
        f'<NotifyPreference>'
        f'<NotificationType>Mail</NotificationType>'
        f'<Destinations>'
        f'<Destination>'
        f'<Tos><To>{email_customer}</To></Tos>'
        f'</Destination>'
        f'</Destinations>'
        f'<From>{email_from_sp}</From>'
        f'</NotifyPreference>'
        f'</NotifyPreferences>'
        f'</NotificationPreferences>'
    )
    return inv[:np_start] + nuevo + inv[np_end:]


def _t_invoiceline_quitar_namespace(inv):
    """Elimina namespace xmlns redundante en InvoiceLine y WithholdingTaxTotal."""
    inv = re.sub(r'<cac:InvoiceLine xmlns="[^"]*" xmlns:sts="[^"]*">', '<cac:InvoiceLine>', inv)
    inv = re.sub(r'<cac:WithholdingTaxTotal xmlns="[^"]*" xmlns:sts="[^"]*">', '<cac:WithholdingTaxTotal>', inv)
    return inv


def _t_payment_means_code(inv):
    """Cambia PaymentMeansCode ZZZ -> 31."""
    return inv.replace('<cbc:PaymentMeansCode>ZZZ</cbc:PaymentMeansCode>',
                       '<cbc:PaymentMeansCode>31</cbc:PaymentMeansCode>')


def _t_payable_rounding_amount(inv):
    """Agrega PayableRoundingAmount antes de PayableAmount si no existe."""
    if '<cbc:PayableRoundingAmount' in inv:
        return inv
    ancla = '<cbc:PayableAmount'
    if ancla not in inv:
        return inv
    return inv.replace(ancla,
                       '<cbc:PayableRoundingAmount currencyID="COP">0</cbc:PayableRoundingAmount>' + ancla, 1)


def _t_eliminar_prepaid_amount(inv):
    """Elimina PrepaidAmount."""
    return re.sub(r'<cbc:PrepaidAmount[^>]*>[^<]*</cbc:PrepaidAmount>', '', inv)


def _t_prefijo_consecutivo_remesa(inv):
    """
    Agrega un '0' al inicio del consecutivo de remesa (Name=02) en cada
    AdditionalItemProperty, solo si aun no lo tiene. Solo para UT Elogia.
    """
    def _agregar_cero(m):
        valor = m.group(1)
        if valor.startswith('0'):
            return m.group(0)
        return f'<cbc:Name>02</cbc:Name><cbc:Value>0{valor}</cbc:Value>'

    return re.sub(r'<cbc:Name>02</cbc:Name><cbc:Value>(\d+)</cbc:Value>', _agregar_cero, inv)



def _t_corregir_scheme_id_invoiceline(inv):
    """
    Corrige cbc:ID con schemeID vacio o "0" en cada InvoiceLine.
    Si schemeID="" o schemeID="0" lo reemplaza por schemeID="1".
    Si ya tiene otro valor entre las comillas, no lo toca.
    """
    def _fix(m):
        val = m.group(1)
        if val and val != "0":   # ya tiene valor valido -> sin cambio
            return m.group(0)
        return '<cbc:ID schemeID="1">'   # vacio o "0" -> "1"

    return re.sub(r'<cbc:ID schemeID="([^"]*)">', _fix, inv)

# ------------------------------------------------------------------------------
# Funcion principal de reconstruccion
# ------------------------------------------------------------------------------

def reconstruir_factura(ruta_archivo, carpeta_salida,
                        nit_sp, nombre_sp, nit_ut, nombre_ut,
                        email_customer, telefono_customer,
                        email_from_sp, nit_customer,
                        prefijo_remesa=False):
    try:
        ruta_archivo = Path(ruta_archivo)
        if not ruta_archivo.exists():
            print(f"[X] Archivo no encontrado: {ruta_archivo}")
            return False

        carpeta_salida = Path(carpeta_salida)
        carpeta_salida.mkdir(exist_ok=True)

        numero = extraer_numero_factura(ruta_archivo.name)
        nombre_salida = f"FACTURA_{numero}.xml" if numero else ruta_archivo.name
        ruta_salida = carpeta_salida / nombre_salida

        with open(ruta_archivo, 'r', encoding='utf-8') as f:
            contenido = f.read()

        def aplicar_todo(inv):
            datos_orig     = _extraer_datos_customer_del_invoice(inv)
            nit_cust_real  = datos_orig['nit_customer']      or nit_customer
            scheme_id_real = datos_orig['scheme_id_customer']
            email_cust_real = datos_orig['email_customer']   or email_customer
            tel_cust_real  = datos_orig['telefono_customer']  or telefono_customer

            inv = _t_corregir_scheme_id_invoiceline(inv)
            inv = _t_shareholders(inv, nit_sp, nombre_sp, nit_ut, nombre_ut)
            inv = _t_value_quantity(inv)
            inv = _t_party_identification_customer(inv, nit_cust_real, scheme_id_real)
            inv = _t_contact_customer(inv, email_cust_real, tel_cust_real)
            inv = _t_eliminar_registration_address_customer(inv)
            inv = _t_notification_preferences(inv, email_cust_real, email_from_sp)
            inv = _t_invoiceline_quitar_namespace(inv)
            inv = _t_payment_means_code(inv)
            inv = _t_payable_rounding_amount(inv)
            inv = _t_eliminar_prepaid_amount(inv)
            if prefijo_remesa:
                inv = _t_prefijo_consecutivo_remesa(inv)
            return inv

        contenido_nuevo = _reemplazar_invoice(contenido, aplicar_todo)

        with open(ruta_salida, 'w', encoding='utf-8') as f:
            f.write(contenido_nuevo)

        print(f"[OK] Reconstruido: {ruta_salida}")
        return True

    except Exception as e:
        print(f"[X] Error: {e}")
        import traceback; traceback.print_exc()
        return False