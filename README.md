# FE-Tool

Aplicación web (Streamlit) para la gestión de **facturación electrónica de transporte**
ante el **RNDC** (Ministerio de Transporte de Colombia), bajo el estándar **DIAN UBL 2.1**.
Concentra en una sola herramienta todo el ciclo: generar los XML de factura, consultarlos y
subirlos al RNDC, y operar remesas y manifiestos (consultar, cumplir, corregir, anular).

Trabaja sobre dos perfiles de una Unión Temporal (**TSP** y **Elogia**), cada uno con sus
propias credenciales y datos de socio; el perfil activo se elige en la barra lateral.

## Módulos

La app agrupa los módulos en cuatro secciones (`webapp/app.py`, registro `_grupos`):

### Facturación
| Módulo | Qué hace |
|---|---|
| **Generar XML** | Arma una factura electrónica (UBL 2.1) de forma manual y descarga el XML. |
| **Generar facturas vía Excel** | Genera facturas en lote desde un Excel (`datos_rg`): agrupa remesas por factura, reparte por perfil (TSP/Elogia) y produce un `.zip` de XML. |
| **Cargar facturas a RNDC** | Sube los XML al RNDC (proceso 86). Muestra el resultado por factura y el **detalle por remesa** (radicado si sube, o el motivo del rechazo). |
| **Consultar factura** | Consulta una factura en el RNDC por número (proceso 86, tipo consulta). |
| **Consultar factura por remesa** | Devuelve la factura asociada a una o varias remesas (proceso 34). |

### Remesas
| Módulo | Qué hace |
|---|---|
| **Consultar remesas** | Consulta una o varias remesas (proceso 3); estado, radicado, manifiesto y variables crudas opcionales. |
| **Corregir remesa** | Corrige datos de una remesa (proceso 38). |
| **Anular cumplido remesa** | Anula el cumplido de una remesa (proceso 28). |
| **Cumplir remesa** | Registra el cumplido de una remesa (proceso 5). |
| **Auto cambio-generador** | Automatiza el cambio de generador (descumplir + recumplir en lote). |

### Manifiesto
| Módulo | Qué hace |
|---|---|
| **Consultar manifiesto** | Consulta un manifiesto (proceso 4) y sus remesas asociadas. |
| **Consultar tiempos logísticos** | Consulta monitoreo/tiempos (proceso 60) por placa o radicado, con rango de fechas. |
| **Cumplir manifiesto** | Registra el cumplido de un manifiesto (proceso 6), aplicando la regla **FOPAT**. |
| **Corregir FOPAT manifiesto** | Corrige el FOPAT en manifiestos (descumplir + recumplir por lote). |
| **Anular cumplido manifiesto** | Anula el cumplido de un manifiesto (proceso 29). |

### Otros
| Módulo | Qué hace |
|---|---|
| **Editar XML** | Edita campos de XMLs existentes (remesas, radicados, valores, fechas). |
| **Reconstruir XML** | Reconstruye XMLs aplicando transformaciones DIAN según el perfil activo. |
| **Extraer datos RG** | Extrae los datos de facturas en PDF (RG) y los exporta a Excel (`datos_rg`), listos para "Generar facturas vía Excel". |
| **Cruzar remesas** | Cruza remesas entre distintas fuentes de datos. |

## Configuración (perfiles)

Todo lo específico de la empresa vive en `config/perfiles.py` (no versionado). Tiene dos partes:

**Constantes globales de la Unión Temporal:**
- `NIT_UT`, `NOMBRE_UT` — NIT y razón social de la UT (el emisor).
- `PREFIJO` — prefijo de facturación (ej. `41`).
- `UNIDAD_MEDIDA` — unidad de las remesas (ej. `KGM`).

**Diccionario `PERFILES`** con un perfil por socio (`ut_tsp`, `ut_elogia`). Campos relevantes:
- `nombre_socio`, `nit_socio` — razón social y NIT del socio (va como accionista al 50 % en el XML).
- `email_from`, `email_contact_supplier` — correo emisor y correo de contacto del proveedor (van en el XML).
- `rndc_usuario`, `rndc_password` — credenciales del RNDC de ese perfil (**solo** para consultar/subir; no aparecen en el XML).
- `prefijo_remesa` — si antepone `0` al consecutivo al consultar en el RNDC (Elogia).

---

## Generación del XML en detalle

El corazón es `core/xml_generator.py`, función **`generar_xml(datos, perfil)`**. Produce un
documento **`AttachedDocument` UBL 2.1** ("Contenedor de Factura Electrónica"): un XML que
envuelve la factura real más su firma y la respuesta de validación de la DIAN.

### De dónde salen los datos

El XML se arma combinando **tres fuentes**:

1. **Constantes de la UT** (`config/perfiles.py`): `NIT_UT`, `NOMBRE_UT`, `PREFIJO`, `UNIDAD_MEDIDA`.
2. **El perfil activo** (TSP o Elogia): `nit_socio`, `nombre_socio`, `email_from`, `email_contact_supplier`.
3. **Los datos de la factura** (`datos`, vengan de la interfaz o del Excel):
   ```
   numero_factura, cufe, fecha, valor_total,
   nit_cliente, digito_cliente, nombre_cliente,
   remesas: [ { consecutivo, radicado, peso, valor, descripcion_linea } ]
   ```

A partir de esos datos, `generar_xml` calcula automáticamente:
- **Retención en la fuente** total y por línea = **1 %** del valor (`retencion_total`).
- **Fecha de vencimiento** = fecha de la factura **+ 30 días**.
- **Cantidad de líneas** = número de remesas.

### Estructura del documento generado

El `AttachedDocument` se compone así (todo se rellena por interpolación de strings sobre una plantilla):

1. **Firma digital (XAdES)** — bloque `ext:UBLExtensions/ds:Signature`: método de firma, digest,
   `SignatureValue`, certificado `X509Certificate` y política de firma de la DIAN. Es una **plantilla
   fija** dentro del script (tomada de un documento real firmado); el generador no re-firma
   criptográficamente, arma el contenedor con ese bloque.

2. **Cabecera del contenedor**: `UBLVersionID`, `ProfileID` = *Factura Electrónica de Venta*,
   `ID` = número de factura, `IssueDate`, y las partes resumidas —**SenderParty** (la UT:
   `NOMBRE_UT` / `NIT_UT`) y **ReceiverParty** (el cliente: `nombre_cliente` / `nit_cliente` con su
   dígito de verificación).

3. **`cac:Attachment` → el `<Invoice>` real** (embebido como CDATA). Es la factura propiamente dicha:

   - **`sts:DianExtensions`**: la autorización DIAN — `InvoiceAuthorization`, período de vigencia,
     `Prefijo` + rango de numeración autorizado, `SoftwareProvider`, `SoftwareSecurityCode`, y el
     **`QRCode`** que incluye el **CUFE** (`...searchqr?documentkey={cufe}`).
   - **Firma XAdES del Invoice** (otra plantilla fija).
   - **`NotificationPreferences`**: correo de notificación → destino = correo del cliente,
     `From` = **`email_from`** del perfil.
   - **`CustomFieldExtension`**: totales y metadatos — `SubtoAmount` (valor total),
     `TotalRetenciones` (la retención del 1 %), `MonedaFacturada` = COP, `Prefijo`, ciudad y
     departamento del emisor, `lugarExpedicion`, y la nota de **título valor** (Ley 1231 de 2008).
   - **Cabecera del Invoice**: `UUID` = **CUFE**, `IssueDate`/`IssueTime`, `InvoiceTypeCode` = 01,
     `DocumentCurrencyCode` = COP, `LineCountNumeric` = nº de remesas.
   - **`AccountingSupplierParty`** (emisor = la UT): razón social `NOMBRE_UT`, dirección (Santa Marta),
     `NIT_UT`, y dentro **dos `ShareholderParty` al 50 %**:
       - el **socio del perfil** (`nombre_socio` / `nit_socio`), y
       - la propia UT (`NOMBRE_UT` / `NIT_UT`).
     Más un `Contact` con nombre, teléfono y **`email_contact_supplier`** del perfil.
   - **`AccountingCustomerParty`** (cliente): `nit_cliente` con `digito_cliente`, `nombre_cliente`,
     dirección y correo.
   - **`PaymentMeans`**: forma de pago y **`PaymentDueDate`** = fecha de vencimiento (+30 días).
   - **`WithholdingTaxTotal`**: la **retención en la fuente del 1 %** sobre el total (esquema 06 / RFTE).
   - **`LegalMonetaryTotal`**: `LineExtensionAmount`, `TaxInclusiveAmount` y `PayableAmount` = valor total.
   - **Las líneas** (`{lines_xml}`): una `InvoiceLine` por remesa (ver abajo).

4. **`ParentDocumentLineReference`**: un `ApplicationResponse` embebido (la **respuesta de validación
   de la DIAN**, plantilla), con la DIAN como `SenderParty` y la UT como `ReceiverParty`.

### La línea por remesa (`generar_invoice_line`)

Por cada remesa se genera un bloque `<cac:InvoiceLine>` con:

- `InvoicedQuantity` = 1.0 y `LineExtensionAmount` = **valor** de la remesa.
- **`WithholdingTaxTotal`**: retención del **1 %** de esa línea (esquema 06 / RFTE).
- **`cac:Item`**:
  - `Description` = descripción de la línea (por defecto *"Servicio de transporte"*).
  - **`SellersItemIdentification/ID`** = **radicado** de la remesa.
  - **`StandardItemIdentification/ID`** (schemeID 999) = **consecutivo** de la remesa.
  - `AdditionalItemProperty`: `ValorTotalItem`, `NumeroLinea`, `CantidadxPrecioU`, `PESO`,
    `Unidad` (= `UNIDAD_MEDIDA`), y el trío convencional **`01` = radicado**, **`02` = consecutivo**,
    **`03` = valor**.
- **`cac:Price/PriceAmount`** = valor unitario.

> El par `01`=radicado / `02`=consecutivo es el estándar del RNDC. (El bot RPA que lee facturas
> desde facture.co usa justo esas propiedades para recuperar el consecutivo.)

### En una frase

`generar_xml` toma la **cabecera de una factura** (emisor = UT + socio del perfil, cliente, CUFE,
totales, retención) y **N remesas**, y las vuelca en la plantilla UBL 2.1 de la DIAN, poniendo en
cada línea el consecutivo, el radicado y el valor de su remesa. El resultado es el XML que luego se
sube al RNDC por el proceso 86.

---

## Adaptar el generador a otra empresa: qué es variable y qué está fijo

El script actual está pensado para una UT específica (transporte, cliente Drummond). Buena parte
del XML se rellena con variables, **pero hay valores hardcodeados que otra empresa debe cambiar**.
Se dividen en tres niveles:

### A) Ya parametrizado (no se toca el código, solo los datos de entrada)

| Origen | Campos |
|---|---|
| **Datos de la factura** (`datos`) | `numero_factura`, `cufe`, `fecha`, `valor_total`, `nit_cliente`, `digito_cliente`, `nombre_cliente`, y las `remesas` (consecutivo, radicado, peso, valor, descripción). |
| **Perfil activo** (`config/perfiles.py`) | `nit_socio`, `nombre_socio`, `email_from`, `email_contact_supplier`. |
| **Constantes de la UT** (`config/perfiles.py`) | `NIT_UT`, `NOMBRE_UT`, `PREFIJO`, `UNIDAD_MEDIDA`. |
| **Calculado** | retención (1 % del valor), vencimiento (+30 días), nº de líneas. |

### B) Hardcodeado en `core/xml_generator.py` — **HAY que cambiarlo por empresa**

Esto es lo que un tercero debe editar para emitir con otra empresa/certificado/cliente:

| Qué | Dónde / valor actual | Nota |
|---|---|---|
| **Firma digital + certificado X509** | Dos bloques `ds:Signature` (contenedor e Invoice): `SignatureValue`, `X509Certificate`, digests, `IssuerSerial` | Es una **plantilla fija** de un documento real. Para otra empresa se necesita **su propio certificado/firma**. El script **no firma criptográficamente**, arma el contenedor con ese bloque. |
| **Autorización DIAN** | `sts:InvoiceAuthorization` (`18764092002504`), `AuthorizationPeriod` (2025-04-15 a 2027-04-15), rango `From`/`To` (1–1000) | Número de resolución, vigencia y rango de numeración: propios de cada empresa/prefijo. |
| **Proveedor de software** | `SoftwareProvider` (`ProviderID`, `SoftwareID`), `SoftwareSecurityCode` | Del proveedor tecnológico (aquí facture). Cambian si el proveedor es otro. |
| **Dirección y datos del emisor** | `AccountingSupplierParty`: `47001`/`SANTA MARTA`/`Magdalena`/`CR 1 C 22 58...`, `IndustryClassificationCode` `4923` | Dirección, códigos de ciudad/departamento y CIIU de la empresa emisora. |
| **Contacto del emisor** | `Contact`: nombre `VANESSA CELIS`, teléfono `3216208110` | El correo sí sale del perfil; el nombre y teléfono están fijos. |
| **CustomFields de emisor** | `NombreCiudadEmisor` `Barranquilla`, `NombreDepartamentoEmisor` `Atlantico`, `lugarExpedicion` `SANTAMARTA_TSP` | Revisar/uniformar por empresa. |
| **Cliente hardcodeado** | `AccountingCustomerParty`: dirección `11001000`/`BOGOTA`/`CALLE 72 N 10 07...` y `email_cli = "facturacion@drummondltd.com"` | El NIT y el nombre del cliente sí son variables, pero **la dirección y el correo del cliente están fijos a Drummond**. Para otro cliente hay que parametrizarlos. |
| **Estructura de accionistas** | Dos `ShareholderParty` al **50 %** (socio + UT) | Específico de una **Unión Temporal** de dos miembros. Otra empresa que no sea UT no lleva esto. |
| **Retención en la fuente** | `WithholdingTaxTotal` y por línea: **1 %**, esquema `06`/`RFTE` | Retención de transporte. Cambia si el tipo/porcentaje de impuesto es otro. |
| **Horas fijas** | `IssueTime`, `SigningTime` (ej. `18:00:12-05:00`) | Cosméticas; puede dejarse o parametrizarse. |

### C) Fijo del estándar DIAN — normalmente **no se cambia**

Espacios de nombres UBL, `ProfileID` (*Factura Electrónica de Venta*), `InvoiceTypeCode` `01`,
`CustomizationID`, el NIT de la DIAN como `AuthorizationProvider`/validador (`800197268`), la URL de
la política de firma, y la estructura del `ApplicationResponse` (respuesta de validación). Estos son
iguales para todos los emisores en Colombia (ver la guía oficial de la DIAN/RNDC).

> **Resumen para adaptar a otra empresa:** cambiar (1) el **certificado/firma**, (2) la **autorización
> DIAN** (resolución, vigencia, prefijo, rango), (3) los **datos y dirección del emisor**, (4) la
> **estructura de accionistas** si no es UT, (5) la **retención** si aplica otro impuesto, y (6)
> **parametrizar el cliente** (dirección y correo, hoy fijos a Drummond). Todo lo demás sale de los
> datos de la factura, del perfil o es estándar DIAN.

## Estructura del proyecto

```
FE-ToolApp/
├── webapp/          # La aplicación Streamlit (app.py) y su lógica (lib_*.py)
├── core/            # Generación y transformación de XML (xml_generator.py, ...)
├── services/        # Integración con el RNDC (WebService SOAP)
├── config/          # Perfiles de empresa y ajustes de negocio (perfiles.py, ajustes.py)
├── ui/              # Versión de escritorio (tkinter) — descontinuada
└── utils/           # Utilidades
```

## Requisitos y ejecución

```
Python 3.10+
streamlit, requests, pandas, openpyxl, pdfplumber
```

```bash
pip install streamlit requests pandas openpyxl pdfplumber
streamlit run webapp/app.py
```

## Automatización (RPA)

El cargue diario de facturas está automatizado en un proyecto aparte (**plcolab-rpa**), que
reutiliza estas mismas funciones de generación y cargue: obtiene las facturas emitidas desde la
API de facture.co, arma los datos en memoria y llama a `generar_xml` + el envío al RNDC, sin
intervención manual.

---

Todos los derechos reservados © 2026
