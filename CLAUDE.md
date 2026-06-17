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
├── main.py                        ← Punto de entrada: python main.py (llama multiprocessing.freeze_support())
├── CLAUDE.md                      ← Este archivo
├── FE-Tool.spec                   ← Spec de PyInstaller (compilación oficial)
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
│   ├── cruzar_remesas.py          ← CruzarRemesasModule: cruza el Excel de "Extraer Datos RG" con otro Excel externo
│   ├── corregir_remesa.py         ← CorregirRemesaModule: consulta y corrige una remesa en el RNDC (proceso 38)
│   └── anular_cumplido_remesa.py  ← AnularCumplidoRemesaModule: anula el cumplido de una remesa (proceso 28)
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
- **10 paneles** de contenido (uno por módulo), mostrados/ocultados con `pack/pack_forget`
- **Barra de estado** inferior

Al cambiar de perfil notifica activamente a `_rndc_uploader`, `_excel_loader` y `_reconstruir_module`.

### `ui/excel_loader.py` — ExcelLoaderWindow
Carga un archivo Excel (con **selector de hoja**), mapea columnas a campos de factura (consecutivo, radicado, valor, peso, descripción, CUFE, fecha) y genera XMLs en lote. Consulta el RNDC automáticamente si hay consecutivos.

Mapeo **opcional de cliente por columna**: campos `NIT cliente` y `Nombre cliente`. Si se mapean, cada factura usa su propio NIT/nombre del Excel; **el dígito de verificación se toma del último dígito del NIT** (ej. `8000213085` → NIT `800021308`, dígito `5`, limpiando cualquier formato). Si no se mapean, usa los valores fijos de la sección "Datos del Cliente". Auto-mapea las columnas `nit`/`nombre_cliente` que exporta `extraer_datos_rg.py` (con guard para que `nit` no colisione con `valor_unitario`).

**Filtro de generación** (`FILTROS_GEN`): combobox que permite generar solo un subconjunto cuando el Excel trae las columnas de validación del cruce (`¿Coinciden remesas?`, `¿Coincide valor factura con RG?`, `Reconstruir`). Opciones: Todas / Solo Reconstruir=Sí / Coinciden remesas NO valor / Coincide valor NO remesas / NO coinciden remesas / NO coincide valor. Es **opcional**: por defecto "Todas (sin filtro)" y funciona con cualquier Excel normal; solo si se elige un filtro y faltan esas columnas, avisa y no genera (helpers `_cols_cruce`, `_pasa_filtro`, `_es_si`).

**Consecutivos sin `.0`**: en `_parsear()`, al leer la columna de consecutivo/remesa se aplica limpieza explícita de float entero (pandas lee enteros como `float64` → `"11519464.0"`). Lógica: si `isinstance(v, float) and v.is_integer()` → `str(int(v))`; si el string termina en `.0` y el resto es dígitos → se recorta. Esto es crítico cuando el Excel de entrada viene del módulo de cruce de remesas.

**Radicados automáticos**: en `_generar_todos()`, antes de generar los XML se itera cada remesa y si el radicado viene vacío, `"nan"`, `"none"` o `"0"`, se llama a `consultar_radicado_remesa(consec, perfil)` contra el RNDC. El radicado se llena automáticamente; si la consulta falla queda `"0"`. Solo funciona si el consecutivo está bien formateado (garantizado por la limpieza anterior).

### `ui/rndc_uploader.py` — RndcUploaderWindow
Sube archivos XML al portal web del RNDC mediante requests HTTP. Registra logs en `rndc_debug.log` en la raíz del proyecto.

### `ui/consultar_remesas.py` — ConsultarRemesasModule
Interfaz para consultar remesas individuales o en lote al RNDC SOAP WS. Muestra consecutivo, radicado, peso, **N° Manifiesto** (`nummanifiestocarga`), propietario, origen, destino y estado.

**Consulta masiva** — modal con dos pestañas:
- **Pegar consecutivos**: cuadro de texto libre; acepta números separados por comas, espacios, punto y coma o saltos de línea (cualquier combinación).
- **Desde Excel**: carga un `.xlsx`, selecciona hoja y columna de consecutivos.

Ambas pestañas comparten la misma tabla de resultados y el botón "Guardar resultados" que exporta a Excel/CSV incluyendo la columna "N° Manifiesto".

### `ui/editar_xml.py` — EditarXMLModule
Abre un XML de factura existente, parsea sus remesas (InvoiceLine) y permite edición inline (doble clic en celda). Actualiza N° factura, CUFE, fecha, valor total, **Cliente (nombre), NIT cliente y dígito de verificación** (todos editables, ver convención abajo), y por remesa: consecutivo, radicado, valor, peso, descripción. Al cargar consulta el RNDC automáticamente.

Botones **`+` / `−`** para añadir o quitar remesas: `+` clona el primer `InvoiceLine` del XML con campos editables; `−` elimina la fila seleccionada (mínimo 1). Al guardar se reconstruye la lista completa de `InvoiceLine`, se renumeran los `<cbc:ID>` y se actualiza `<cbc:LineCountNumeric>`.

Al editar **nombre/NIT/dígito del cliente**, el reemplazo se aplica tanto al `AccountingCustomerParty` (dentro del CDATA) como al `<cac:ReceiverParty>` externo del AttachedDocument (el que está **antes del primer CDATA**, para no tocar el ReceiverParty de la ApplicationResponse que es la UT). Esto evita el error DIAN **FAC025** (identificación del adquirente no coincide entre la factura y el AttachedDocument). La edición de fecha solo se dispara si el usuario realmente cambió el valor (acepta entrada en `DD-MM-YYYY` o `YYYY-MM-DD`).

### `ui/reconstruir_xml.py` — ReconstruirXMLModule
Aplica las 11 transformaciones DIAN definidas en `core/xml_transformer.py` a XMLs originales. Hace preprocesamiento (limpia ShareholderParty anteriores), llama a `reconstruir_factura()` sobre un archivo temporal, renombra el output al nombre original, y actualiza radicado/peso desde el RNDC. Checkbox **"Peso por defecto = 1 KGM"**: si está marcado, ignora el peso devuelto por el RNDC y fuerza `1` en todas las remesas del XML reconstruido (el radicado sigue consultándose normalmente).

### `ui/extraer_datos_rg.py` — ExtraerDatosRGModule
Extrae datos estructurados de PDFs de facturas electrónicas usando `pdfplumber` y exporta a Excel/CSV. Procesa los PDFs **en paralelo** con `ProcessPoolExecutor` (worker a nivel de módulo `_procesar_pdf_worker`, tope de 8 procesos) — por eso `main.py` llama `multiprocessing.freeze_support()`. Los resultados llegan desordenados y se reensamblan por índice para **preservar el orden de los archivos** (necesario para el cruce posicional).

**Valor total de la factura = SUBTOTAL** del PDF (antes de retenciones), con fallback a "TOTAL A PAGAR".

**Lógica de cantidad/expansión** (`_expandir_lineas`, constante `MAX_CANTIDAD_EXPANSION = 100`):
- Si la columna CANTIDAD es un **entero entre 1 y 100** → se interpreta como conteo de remesas y la línea se **expande** en esas N filas, repartiendo el **VR.TOTAL** de la línea entre ellas (`vr_total / N`).
- Si es **decimal** (ej. `12,350` = 12.35, un peso) o un **entero > 100** → es **una sola remesa** con valor = VR.TOTAL de la línea.
- La columna `cantidad_remesas_rg` refleja el **total de remesas de la factura** (mismo valor en todas sus filas), no el conteo por línea.

Columnas exportadas: `numero_factura, fecha_generacion, cufe, nit, nombre_cliente, descripcion, consecutivo_remesa, radicado, valor_unitario, valor_total_factura, cantidad_remesas_rg`. El `nit` es el del **cliente/adquirente** (tras "CLIENTE :", con fallback "NOMBRE:"); no el de la UT emisora. La columna `consecutivo_remesa` suele quedar vacía (los PDF de RG no la traen). Campo opcional: usar Referencia del PDF como consecutivo_remesa.

### `ui/cruzar_remesas.py` — CruzarRemesasModule
Cruza el Excel exportado por "Extraer Datos RG" con otro Excel externo (que sí tiene consecutivos de remesa reales y valores unitarios), agrupando ambos por **N° Factura**. Ambos archivos tienen **selector de hoja** independiente. Mapeo de columnas estilo `excel_loader.py` (combobox con auto-detección). Por factura compara:
- `¿Coinciden remesas?` — **cantidad de filas** del RG vs cantidad de filas del otro Excel (solo cuenta, no identidad). Igualdad exacta → Sí; cualquier diferencia (más o menos) → No.
- `¿Coincide valor factura con RG?` — suma de valores unitarios del otro Excel vs valor total de factura del RG (tolerancia $1).
- `Reconstruir` — `Sí` solo si ambas anteriores son `Sí`.

Valores monetarios robustos vía `_to_num` (quita `$`, espacios y separadores antes de parsear, así una columna en texto con `$` no rompe la suma). Consecutivos limpios vía `_fmt_consec` (NaN→vacío, quita el `.0` que pandas añade a enteros leídos como float).

**Filtro de exportación** (`FILTROS_EXPORT`, helper `_pasa_filtro`): Todas / Solo Reconstruir=Sí / Coinciden remesas NO valor / Coincide valor NO remesas / NO coinciden remesas / NO coincide valor / Reconstruir=No. Genera solo el subconjunto elegido (con todas las columnas del RG), evitando filtrar a mano en Excel.

Al exportar, parte del Excel de RG **completo** (todas sus columnas/filas originales, sin la columna `consecutivo_remesa` que se descarta por venir vacía) y le anexa las 3 columnas de validación más `Consecutivo Remesa (Otro Excel)` — este último se asigna **posicionalmente** (línea N del RG ↔ remesa N del otro Excel, en orden de aparición); si el otro Excel tiene menos remesas que líneas el RG, las líneas sobrantes quedan vacías; si tiene **más**, los consecutivos sobrantes no se muestran. (No es un cruce por valor, es por orden de aparición.)

**Columna opcional `Comp. Generador Carga RNDC`** (`otro_col_comp_gen`): campo opcional del otro Excel. Si se mapea en la UI, sus valores se recogen en `_comp_gen_otro_por_factura` (por factura, en orden posicional) y el Excel exportado incluye la columna `"Comp. Generador Carga RNDC"` alineada a cada remesa del RG. Si no se mapea, la columna no aparece en el reporte. Auto-detección por hints: `"comp. generador"`, `"comp_generador"`, `"generador carga"`, `"generadorcarga"`, `"rndc"`.

> Nota sobre conteos: como `¿Coinciden remesas?` cuenta **filas**, si el otro Excel trae remesas duplicadas o filas con consecutivo en blanco, el conteo puede no cuadrar con los consecutivos únicos visibles.

### `ui/corregir_remesa.py` — CorregirRemesaModule
Corrige una remesa en el RNDC vía **proceso 38** (`tipo=1`), replicando el formulario web del RNDC. Flujo:
1. Escribir consecutivo → **Consultar remesa** (`consultar_remesa_completa`, proceso 3 / `tipo=3` / `variables=*`).
2. Se muestran los **datos actuales** (solo lectura) y se prellena internamente el conjunto base de variables (`BASE_FIELDS`).
3. Elegir **"Opción a Corregir"** (`CODIGOCAMBIO`) → el formulario es **dinámico**: solo aparecen los campos editables de esa opción (igual que la web). Mapeo `OPCION_CAMPOS`:
   - `1` Cambio Cita Cargue → fecha + hora cargue
   - `2` Cambio Cita Descargue → fecha + hora descargue
   - `3` Cambio Sede Descargue → tipo/núm ID + sede destinatario
   - `4` Cambio de Generador → tipo/núm ID + sede propietario
   - `5` Cambio Serial Contenedor → `contenedorSerial`
4. Elegir **"Motivo del Cambio"** (`MOTIVOCAMBIO`): 1=Incumpl. Generador, 2=Incumpl. Titular Manifiesto, 3=Decisión Generador, 4=Decisión Patio/Puerto.
5. **Guardar remesa corregida** (`corregir_remesa`) con **confirmación previa**. Se envía el **conjunto base completo** (prellenado del consult) con los campos de la opción sobrescritos + `MOTIVOCAMBIO` + `CODIGOCAMBIO`.

Detalles importantes:
- El usuario **solo edita los campos de la opción elegida**; el resto de la remesa se reenvía tal cual vino del consult (el proceso 38 espera el conjunto completo, no solo los campos cambiados).
- Solo se envían **códigos** (`codOperacionTransporte=G`), no las descripciones legibles (`operaciontransporte=General`).
- Mapeo de nombre distinto consulta→envío: consulta devuelve `horacitapactadadescargueremesa`, el proceso 38 espera `HORACITAPACTADADESCARGUE`.
- En el `<documento>` de la consulta los valores van **entre comillas simples** (`'8901031611'`); omitirlas causa `ORA-01722: invalid number`.
- Respeta `prefijo_remesa` del perfil (antepone `0` al consecutivo en ut_elogia).

### `ui/anular_cumplido_remesa.py` — AnularCumplidoRemesaModule
Anula el cumplido de una remesa en el RNDC vía **proceso 28** (`tipo=1`). Flujo: escribir consecutivo → **Consultar remesa** (`consultar_remesa_completa`, muestra datos para confirmar) → elegir **Motivo de anulación** → **Guardar anulación** con confirmación. Campos enviados: `NUMNITEMPRESATRANSPORTE`, `CONSECUTIVOREMESA`, `CODMOTIVOANULACIONCUMPLIDO` (`D`=Error Digitación, `O`=Otro). Usa las **mismas credenciales de corrección** (`rndc_usuario_corregir`) y el endpoint `rndcws`, igual que corregir remesa.

### Nota — credenciales de corrección/anulación
Los perfiles pueden definir `rndc_usuario_corregir` / `rndc_password_corregir`. Los módulos de **corregir** y **anular cumplido** usan un helper `_perfil()` que sustituye las credenciales normales por estas (si existen) **solo en esos módulos**; el resto de la app sigue con `rndc_usuario`/`rndc_password`. Si el perfil no las define, hace fallback a las normales. Actualmente `ut_tsp` las tiene (`CG_TSP@137`).

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
| `consultar_radicado_remesa(consecutivo, perfil)` | `services/rndc_service.py` | Retorna `(ok: bool, resultado: dict)` con `radicado`, `peso`, `estado`, `propietario`, `origen`, `destino`, `manifiesto` (`nummanifiestocarga`) |
| `consultar_remesa_completa(consecutivo, perfil)` | `services/rndc_service.py` | Proceso 3 / `tipo=3` / `variables=*`. Retorna `(ok, dict)` con TODOS los campos de la remesa |
| `corregir_remesa(variables, perfil)` | `services/rndc_service.py` | Proceso 38 / `tipo=1`. Envía a `rndcws.mintransporte.gov.co:8080` (sin "2"). `variables` es dict (orden respetado). Retorna `(ok, {ingresoid})` |
| `anular_cumplido_remesa(consecutivo, cod_motivo, perfil)` | `services/rndc_service.py` | Proceso 28 / `tipo=1`. Anula cumplido. `cod_motivo`: `D`=Error Digitación, `O`=Otro. Mismo endpoint que corregir |
| `_enviar_proceso_rndc(procesoid, variables, perfil)` | `services/rndc_service.py` | Envío genérico tipo=1 a `rndcws` (usado por corregir 38 y anular 28) |
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
- **NIT cliente / dígito de verificación en `AccountingCustomerParty`**: no todos los XML tienen la misma estructura. Los generados por `xml_generator.py` incluyen `<cac:PartyIdentification><cbc:ID schemeID="{dig}">{nit}</cbc:ID></cac:PartyIdentification>`; los XML reconstruidos/respuesta del RNDC (ej. `AttachedDocument`) **no la tienen** y el dato solo existe en `PartyTaxScheme`/`PartyLegalEntity` (`<cbc:CompanyID schemeID="{dig}">{nit}</cbc:CompanyID>`). `editar_xml.py` intenta `PartyIdentification` primero y cae a `PartyTaxScheme`/`PartyLegalEntity` si no la encuentra. Al guardar, el reemplazo de NIT/dígito/nombre se hace por substitución de texto **acotada a bloques** (nunca global en todo el XML), para no afectar NITs/nombres iguales en otras secciones (UT, socio, etc.). Se reemplaza en **dos** lugares: (1) el `AccountingCustomerParty` dentro del CDATA, y (2) el `<cac:ReceiverParty>` externo del AttachedDocument (acotado a lo que está **antes del primer `<![CDATA[`** para no tocar el ReceiverParty de la ApplicationResponse, que corresponde a la UT). Mantener ambos sincronizados es lo que evita el error DIAN **FAC025**.

- **NIT con dígito embebido**: en los Excel/PDF el NIT suele venir con el dígito de verificación pegado (ej. `8000213085`). Para separarlo: limpiar a solo dígitos y tomar el último como dígito (`nit = s[:-1]`, `digito = s[-1]`). Así lo hace `excel_loader.py` cuando se mapea la columna NIT.

---

## Compatibilidad PyInstaller

La app está pensada para distribuirse como `.exe` con PyInstaller `--onefile`. Por esto:
- `resource_path()` usa `sys._MEIPASS` si existe, o el directorio del módulo si no
- La función sube un nivel (`"..", "icono.ico"`) porque vive en `utils/` pero el recurso está en la raíz
- No usar `__file__` directamente en módulos UI para rutas de recursos
- **`main.py` llama `multiprocessing.freeze_support()`** como primera instrucción del `if __name__ == "__main__"`: es **obligatorio** porque `extraer_datos_rg.py` usa `ProcessPoolExecutor`. Sin esto, el `.exe` `--onefile` relanzaría la ventana principal por cada proceso hijo.
- Los workers de multiprocessing deben ser funciones **a nivel de módulo** (no métodos), para ser picklables en Windows (arranque `spawn`). Por eso `_procesar_pdf_worker` está fuera de la clase.

---

## Cómo ejecutar

```bash
# Desarrollo
python main.py

# Compilar con PyInstaller (usar el .spec oficial — ya incluye freeze_support, icono y deps)
# IMPORTANTE: ejecutar desde dentro de FE-ToolApp\ (pathex=['.'] en el spec)
C:\Users\clizarazo\AppData\Local\Python\pythoncore-3.14-64\Scripts\pyinstaller.exe FE-Tool.spec
```

El `.exe` queda en `FE-ToolApp\dist\FE-Tool.exe`.

**Notas sobre la compilación:**
- Python 3.14 + PyInstaller 6.20.0 funciona correctamente con este proyecto.
- No usar `python -m pyinstaller` en esta instalación — falla. Usar la ruta absoluta al `.exe` de PyInstaller como se muestra arriba.
- El spec no necesita `threading` en hiddenimports — PyInstaller lo detecta como stdlib automáticamente.
- UPX está desactivado (`upx=False`) para evitar falsos positivos de antivirus.

## Dependencias principales

```
tkinter       # incluido en Python estándar
requests      # RNDC HTTP uploader
pandas        # Excel loader (opcional, degrada con gracia si no está)
openpyxl      # lectura/escritura Excel
pdfplumber    # extracción de datos de PDFs (extraer_datos_rg)
```
