# CLAUDE.md — Contexto del proyecto FE-Tool

## ¿Qué es esta aplicación?

**FE-Tool** es una aplicación de escritorio en Python (tkinter) para la gestión de **facturación electrónica colombiana (DIAN UBL 2.1)** usada por la empresa **Unión Temporal American Logistic UT**, que opera con dos perfiles:

- **UT TSP** (Transportes Sánchez Polo S.A.)
- **UT Elogia** (Elogia Soluciones Logísticas S.A.S.)

Ambos perfiles facturan servicios de transporte de carga al cliente **Drummond Ltd** (NIT 800021308).

La app fue refactorizada de un monolito de ~5700 líneas (`generador_xml_tsp.py`) a una arquitectura modular de paquetes Python. **Los archivos originales no se modificaron** — solo se crearon archivos nuevos.

---

## Arquitectura modular

```
testap/
├── main.py                        ← Punto de entrada: python main.py
├── CLAUDE.md                      ← Este archivo
│
├── config/                        ← Constantes globales (sin dependencias internas)
│   ├── __init__.py
│   ├── perfiles.py                ← Dict PERFILES con ut_tsp y ut_elogia
│   └── theme.py                   ← Paleta de colores y fuentes (BG, ACCENT, FONT_*)
│
├── core/                          ← Lógica de negocio pura
│   ├── __init__.py
│   ├── xml_generator.py           ← Genera XML UBL 2.1 (generar_xml, _parse_valor, _fmt_valor, generar_invoice_line)
│   └── xml_transformer.py         ← Copia de cambiar_nit_factura.py: transforma XMLs según perfil (reconstruir_factura)
│
├── services/                      ← Integraciones externas
│   ├── __init__.py
│   └── rndc_service.py            ← SOAP WS al RNDC (Ministerio de Transporte): consultar_radicado_remesa()
│
├── ui/                            ← Módulos de interfaz gráfica (tkinter)
│   ├── __init__.py
│   ├── app.py                     ← GeneradorApp: ventana principal, sidebar, navegación entre paneles
│   ├── excel_loader.py            ← ExcelLoaderWindow: generación masiva de XMLs desde Excel
│   ├── rndc_uploader.py           ← RndcUploaderWindow: subida de facturas al portal RNDC
│   ├── consultar_remesas.py       ← ConsultarRemesasModule: consulta de remesas en el RNDC
│   ├── editar_xml.py              ← EditarXMLModule: edición inline de campos de un XML existente
│   ├── reconstruir_xml.py         ← ReconstruirXMLModule: aplica transformaciones DIAN a XMLs originales
│   ├── extraer_datos_rg.py        ← ExtraerDatosRGModule: extrae datos de PDFs de facturas y exporta a Excel
│   └── cruzar_remesas.py          ← CruzarRemesasModule: cruza el Excel de "Extraer Datos RG" con otro Excel externo
│
├── utils/                         ← Utilidades transversales
│   ├── __init__.py
│   └── helpers.py                 ← resource_path(): resuelve rutas compatible con PyInstaller (_MEIPASS)
│
└── (archivos originales, NO modificar)
    ├── generador_xml_tsp.py       ← Monolito original (5688 líneas) — conservado intacto
    └── cambiar_nit_factura.py     ← Módulo original de transformaciones — conservado intacto
```

---

## Mapa de dependencias

```
config/          → sin dependencias internas
utils/           → sin dependencias internas
core/            → importa de config/
services/        → sin dependencias internas (usa requests)
ui/              → importa de config/, core/, services/, utils/
main.py          → importa de ui/
```

---

## Módulos UI — qué hace cada uno

### `ui/app.py` — GeneradorApp
Ventana principal. Construye:
- **Header** con logo FE-Tool
- **Pill bar** de selección de perfil (ut_tsp / ut_elogia)
- **Sidebar** con grupos colapsables: Facturación / Remesas / Otros
- **8 paneles** de contenido (uno por módulo), mostrados/ocultados con `pack/pack_forget`
- **Barra de estado** inferior

Al cambiar de perfil notifica activamente a `_rndc_uploader`, `_excel_loader` y `_reconstruir_module`.

### `ui/excel_loader.py` — ExcelLoaderWindow
Carga un archivo Excel, mapea columnas a campos de factura (consecutivo, radicado, valor, peso, descripción, CUFE, fecha) y genera XMLs en lote. Consulta el RNDC automáticamente si hay consecutivos.

### `ui/rndc_uploader.py` — RndcUploaderWindow
Sube archivos XML al portal web del RNDC mediante requests HTTP. Registra logs en `rndc_debug.log` en la raíz del proyecto.

### `ui/consultar_remesas.py` — ConsultarRemesasModule
Interfaz para consultar remesas individuales o en lote al RNDC SOAP WS. Muestra consecutivo, radicado e INGRESOID.

### `ui/editar_xml.py` — EditarXMLModule
Abre un XML de factura existente, parsea sus remesas (InvoiceLine) y permite edición inline (doble clic en celda). Actualiza N° factura, CUFE, fecha, valor total, **NIT cliente y dígito de verificación** (editables, ver convención abajo), y por remesa: consecutivo, radicado, valor, peso, descripción. Al cargar consulta el RNDC automáticamente.

### `ui/reconstruir_xml.py` — ReconstruirXMLModule
Aplica las 11 transformaciones DIAN definidas en `core/xml_transformer.py` a XMLs originales. Hace preprocesamiento (limpia ShareholderParty anteriores), llama a `reconstruir_factura()` sobre un archivo temporal, renombra el output al nombre original, y actualiza radicado/peso desde el RNDC. Checkbox **"Peso por defecto = 1 KGM"**: si está marcado, ignora el peso devuelto por el RNDC y fuerza `1` en todas las remesas del XML reconstruido (el radicado sigue consultándose normalmente).

### `ui/extraer_datos_rg.py` — ExtraerDatosRGModule
Extrae datos estructurados de PDFs de facturas electrónicas usando `pdfplumber`. Expande líneas según cantidad de remesas y exporta a Excel/CSV. Campo opcional: usar Referencia del PDF como consecutivo_remesa. La columna `consecutivo_remesa` del export suele quedar vacía (los PDF de RG no la traen).

### `ui/cruzar_remesas.py` — CruzarRemesasModule
Cruza el Excel exportado por "Extraer Datos RG" con otro Excel externo (que sí tiene consecutivos de remesa reales y valores unitarios), agrupando ambos por **N° Factura**. Mapeo de columnas estilo `excel_loader.py` (combobox con auto-detección). Por factura compara:
- `¿Coinciden remesas?` — cantidad de líneas del RG vs cantidad de remesas del otro Excel (solo cuenta, no identidad).
- `¿Coincide valor factura con RG?` — suma de valores unitarios del otro Excel vs valor total de factura del RG (tolerancia $1).
- `Reconstruir` — `Sí` solo si ambas anteriores son `Sí`.

Al exportar, parte del Excel de RG **completo** (todas sus columnas/filas originales, sin la columna `consecutivo_remesa` que se descarta por venir vacía) y le anexa las 3 columnas de validación más `Consecutivo Remesa (Otro Excel)` — este último se asigna **posicionalmente** (línea N del RG ↔ remesa N del otro Excel, en orden de aparición); si el otro Excel tiene menos remesas que líneas el RG, las líneas sobrantes quedan vacías (no es un cruce por valor, es por orden de aparición).

---

## Perfiles — config/perfiles.py

Cada perfil tiene:
- `nombre`, `nit_socio`, `nombre_socio` — datos del socio facturador
- `email_from`, `email_contact_supplier` — emails del XML
- `carpeta` — carpeta de salida para XMLs generados
- `carpeta_reconstruir` — carpeta de salida para XMLs reconstruidos
- `rndc_usuario`, `rndc_password` — credenciales RNDC
- `nit_ut`, `nombre_ut` — datos de la UT emisora
- `nit_customer`, `email_customer`, `telefono_customer` — datos del cliente (Drummond)
- `prefijo_remesa` (bool) — si True (ut_elogia), añade "0" al consecutivo al consultar RNDC

---

## Funciones clave

| Función | Módulo | Descripción |
|---|---|---|
| `generar_xml(datos, perfil)` | `core/xml_generator.py` | Genera XML UBL 2.1 completo como string |
| `_parse_valor(texto)` | `core/xml_generator.py` | Convierte "1.777.777,00" / "1,777,777.00" / "1777777" → float |
| `_fmt_valor(valor)` | `core/xml_generator.py` | Convierte float → string sin decimales si es entero ("1777777") |
| `reconstruir_factura(...)` | `core/xml_transformer.py` | Aplica 11 transformaciones DIAN al XML |
| `consultar_radicado_remesa(consecutivo, perfil)` | `services/rndc_service.py` | Retorna `(ok: bool, resultado: dict)` con `radicado` y `peso` |
| `resource_path(relative)` | `utils/helpers.py` | Resuelve rutas para PyInstaller: sube un nivel desde `utils/` para encontrar archivos en la raíz |

---

## Convenciones importantes

- **`_parse_valor` / `_fmt_valor`**: siempre usar estas funciones para valores monetarios. Aceptan puntos y comas en cualquier formato (colombiano o anglosajón).
- **`resource_path`**: usar para cualquier recurso estático (ej: `icono.ico`). En el monolito original se llamaba `_resource_path` (privada); en la arquitectura modular es pública importada de `utils.helpers`.
- **CDATA**: los XMLs de DIAN tienen el Invoice embebido en `<![CDATA[...]]>` dentro de un AttachedDocument. Siempre extraer el bloque con `re.search(r"<!\[CDATA\[(.*?)\]\]>", contenido, re.DOTALL)` antes de parsear.
- **Namespaces en InvoiceLine**: normalizar con regex antes de parsear remesas:
  ```python
  re.sub(r'<cac:InvoiceLine\s+xmlns="[^"]*"(?:\s+xmlns:[^=]+="[^"]*")*\s*>', "<cac:InvoiceLine>", inv)
  ```
- **Perfiles**: siempre obtener el perfil activo mediante `self.perfil_fn()` (callable), nunca como valor estático, para respetar cambios en tiempo de ejecución.
- **NIT cliente / dígito de verificación en `AccountingCustomerParty`**: no todos los XML tienen la misma estructura. Los generados por `xml_generator.py` incluyen `<cac:PartyIdentification><cbc:ID schemeID="{dig}">{nit}</cbc:ID></cac:PartyIdentification>`; los XML reconstruidos/respuesta del RNDC (ej. `AttachedDocument`) **no la tienen** y el dato solo existe en `PartyTaxScheme`/`PartyLegalEntity` (`<cbc:CompanyID schemeID="{dig}">{nit}</cbc:CompanyID>`). `editar_xml.py` intenta `PartyIdentification` primero y cae a `PartyTaxScheme`/`PartyLegalEntity` si no la encuentra. Al guardar, el reemplazo de NIT/dígito se hace por substitución de texto **acotada al bloque `AccountingCustomerParty`** (nunca global en todo el XML), para no afectar NITs iguales en otras secciones (UT, socio, etc.).

---

## Compatibilidad PyInstaller

La app está pensada para distribuirse como `.exe` con PyInstaller `--onefile`. Por esto:
- `resource_path()` usa `sys._MEIPASS` si existe, o el directorio del módulo si no
- La función sube un nivel (`"..", "icono.ico"`) porque vive en `utils/` pero el recurso está en la raíz
- No usar `__file__` directamente en módulos UI para rutas de recursos

---

## Cómo ejecutar

```bash
# Desarrollo
python main.py

# Compilar con PyInstaller
pyinstaller --onefile --windowed --icon=icono.ico main.py
```

## Dependencias principales

```
tkinter       # incluido en Python estándar
requests      # RNDC HTTP uploader
pandas        # Excel loader (opcional, degrada con gracia si no está)
openpyxl      # lectura/escritura Excel
pdfplumber    # extracción de datos de PDFs (extraer_datos_rg)
```
