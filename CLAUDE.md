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
│   ├── proceso_completo_remesa.py ← ProcesoCompletoRemesaModule: orquesta anular+corregir generador+cumplir
│   ├── cruzar_remesas.py          ← CruzarRemesasModule: cruza el Excel de "Extraer Datos RG" con otro Excel externo
│   ├── corregir_remesa.py         ← CorregirRemesaModule: consulta y corrige una remesa en el RNDC (proceso 38)
│   ├── anular_cumplido_remesa.py  ← AnularCumplidoRemesaModule: anula el cumplido de una remesa (proceso 28)
│   └── cumplir_remesa.py          ← CumplirRemesaModule: cumple una remesa (proceso 5), tiempos automáticos
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

> Convenciones de UI comunes: los módulos con tabla (`consultar_remesas` incl. modal masivo, `editar_xml`, `rndc_uploader`) tienen botón **"📋 Copiar tabla"** que vuelca encabezados+filas al portapapeles como TSV (pegable en Excel). En `consultar_remesas` (tabla + modal) y `rndc_uploader` (facturas + remesas), **doble clic en una celda** abre un campo con el texto seleccionado para copiar (helper `_hacer_celda_copiable`). Los módulos de remesa RNDC (`corregir_remesa`, `anular_cumplido_remesa`, `cumplir_remesa`, `proceso_completo_remesa`) tienen botón **"🗑 Limpiar"** que resetea consecutivo, campos, combos a default y estado. La versión de la app (header y sidebar de `app.py`) es **V1.4**.

### `ui/app.py` — GeneradorApp
Ventana principal. Construye:
- **Header** con logo FE-Tool
- **Pill bar** de selección de perfil (ut_tsp / ut_elogia)
- **Sidebar** con grupos colapsables: Facturación / Remesas / Otros
- **12 paneles** de contenido (uno por módulo), mostrados/ocultados con `pack/pack_forget`
- **Barra de estado** inferior

Al cambiar de perfil notifica activamente a `_rndc_uploader`, `_excel_loader` y `_reconstruir_module`.

### `ui/excel_loader.py` — ExcelLoaderWindow
Carga un archivo Excel (con **selector de hoja**), mapea columnas a campos de factura (consecutivo, radicado, valor, peso, descripción, CUFE, fecha) y genera XMLs en lote. Consulta el RNDC automáticamente si hay consecutivos.

Mapeo **opcional de cliente por columna**: campos `NIT cliente` y `Nombre cliente`. Si se mapean, cada factura usa su propio NIT/nombre del Excel; **el dígito de verificación se toma del último dígito del NIT** (ej. `8000213085` → NIT `800021308`, dígito `5`, limpiando cualquier formato). Si no se mapean, usa los valores fijos de la sección "Datos del Cliente". Auto-mapea las columnas `nit`/`nombre_cliente` que exporta `extraer_datos_rg.py` (con guard para que `nit` no colisione con `valor_unitario`).

**Filtro de generación** (`FILTROS_GEN`): combobox que permite generar solo un subconjunto cuando el Excel trae las columnas de validación del cruce (`¿Coinciden remesas?`, `¿Coincide valor factura con RG?`, `Reconstruir`). Opciones: Todas / Solo Reconstruir=Sí / **Reconstruir=Sí y Novedad vacía** / Coinciden remesas NO valor / Coincide valor NO remesas / NO coinciden remesas / NO coincide valor. Es **opcional**: por defecto "Todas (sin filtro)" y funciona con cualquier Excel normal; solo si se elige un filtro y faltan esas columnas, avisa y no genera (helpers `_cols_cruce`, `_pasa_filtro`, `_es_si`). El filtro **"Reconstruir=Sí y Novedad vacía"** además exige la columna `Novedad remesa` y opera a **nivel de factura** (no de fila): una factura solo se incluye si **todas** sus remesas tienen Reconstruir=Sí **y** novedad vacía — si aunque sea una remesa tiene novedad con datos, la factura completa se excluye (no se genera con las remesas restantes). Implementación en `_parsear()`: evalúa cada fila con `_pasa_filtro`, agrupa por N° Factura con `groupby(...).all()`, y descarta las facturas donde alguna fila no pase (`_es_vacio`). La columna de novedad es un **campo de mapeo opcional** (`col_novedad`, "Novedad remesa (opcional)") que NO se usa para el XML, solo para este filtro; `_novedad_col_activa` usa la columna mapeada por el usuario si la eligió, o cae a auto-detección por nombre (`_col_novedad`). Conjunto `FILTROS_NOVEDAD`.

**Filtro adicional de Comp. Generador Carga RNDC** (activo solo dentro de `FILTROS_NOVEDAD`): campo de mapeo opcional `col_comp_gen` ("Comp. Generador Carga RNDC (opcional)"). Al mapearlo, un combobox de valor (`_comp_gen_valor_combo`) se puebla dinámicamente con los valores únicos de esa columna (ej. "SI", "NO") más "— No usar —" y "Todas". Si el usuario elige un valor específico (ej. "SI"), se aplica un segundo filtro a nivel de factura: la factura solo pasa si **todas** sus remesas tienen ese valor en la columna. Implementación en `_parsear()` tras el filtro de novedad, usando `groupby(...).all()` sobre `_cg_pasa`. Auto-detección por hints: `"comp. generador"`, `"generador carga"`, etc. Método `_actualizar_comp_gen_valores()` actualiza el combo de valores al cambiar la columna mapeada y propone "SI" como default si existe.

**Filtro por Estado (omitir ya generadas)** — campo de mapeo opcional `col_estado` ("Estado (opcional)"), **independiente** del filtro de generación (aplica con cualquier filtro, incluso "Todas (sin filtro)"). Si se mapea, se asume que las facturas con Estado lleno (ej. `CARGADA`, `PENDIENTE`) **ya fueron generadas** y se omiten: solo se generan las facturas cuyas remesas tengan **todas** el Estado vacío (`_es_vacio`). Opera a **nivel de factura** vía `groupby(...).all()` sobre `_est_vacio` (mismo criterio que novedad: si cualquier remesa tiene Estado, la factura completa se excluye). No hardcodea valores — solo distingue vacío vs no-vacío. Implementación en `_parsear()` tras el bloque de filtros de cruce, antes del `def col(...)`. Auto-detección por hint `"estado"`.

**Consecutivos sin `.0`**: en `_parsear()`, al leer la columna de consecutivo/remesa se aplica limpieza explícita de float entero (pandas lee enteros como `float64` → `"11519464.0"`). Lógica: si `isinstance(v, float) and v.is_integer()` → `str(int(v))`; si el string termina en `.0` y el resto es dígitos → se recorta. Esto es crítico cuando el Excel de entrada viene del módulo de cruce de remesas.

**Radicados automáticos**: en `_generar_todos()`, antes de generar los XML se itera cada remesa y si el radicado viene vacío, `"nan"`, `"none"` o `"0"`, se llama a `consultar_radicado_remesa(consec, perfil)` contra el RNDC. El radicado se llena automáticamente; si la consulta falla queda `"0"`. Solo funciona si el consecutivo está bien formateado (garantizado por la limpieza anterior).

### `ui/rndc_uploader.py` — RndcUploaderWindow
Sube archivos XML (Factura Electrónica, proceso 86) al RNDC mediante SOAP. Registra logs en `rndc_debug.log`. Dos tablas: **Facturas** (columnas: Archivo, N° Factura, Cliente, CUFE, **Remesas** = cantidad de remesas, **Estado RNDC**; la cantidad se conserva tras el envío) y **Remesas** (incluye columna **"Propietario"** = generador de cada remesa, traído de la consulta). Al cargar el XML, **consulta el estado real de cada remesa** (`_consultar_estados_remesas` → `consultar_radicado_remesa`) y lo muestra antes del envío, con el criterio **"Pendiente de asignar manifiesto"** (estado `AC` sin `nummanifiestocarga`); también guarda el NIT del propietario de cada remesa.

**Atribución de error por NIT:** al enviar, si la factura es rechazada, el error completo va en la fila de la factura; en las remesas, el detalle se muestra **solo en la(s) remesa(s) culpables** — las que tienen un **NIT de propietario distinto al del cliente de la factura** (`_nit_coincide` compara ignorando el dígito de verificación: coinciden si uno es prefijo del otro) o cuyo consecutivo aparezca en el mensaje del RNDC. Las demás muestran "Factura rechazada (ver fila de la factura)". Esto evita repetir el mismo error en todas las remesas (el RNDC normalmente no devuelve el consecutivo). Helper `_estado_remesa_txt` (mismo criterio que ConsultarRemesasModule).

### `ui/consultar_remesas.py` — criterio de estado
`_estado_txt_color(cod, manifiesto)`: si `cod == "AC"` y el manifiesto viene vacío → **"Pendiente de asignar manifiesto"**; `CE` → Cumplida; `AC` con manifiesto → Pendiente por cumplir.

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

**Columnas opcionales del otro Excel** (`otro_col_comp_gen` → `"Comp. Generador Carga RNDC"`; `otro_col_novedad` → `"Novedad remesa"`): campos opcionales del otro Excel. Si se mapean en la UI, sus valores se recogen por factura en orden posicional (`_comp_gen_otro_por_factura`, `_novedad_otro_por_factura`) y el Excel exportado incluye esas columnas alineadas a cada remesa del RG. Si no se mapean, no aparecen en el reporte. Auto-detección por hints: comp. generador → `"comp. generador"`, `"generador carga"`, `"rndc"`, etc.; novedad → `"novedad"`.

> Nota sobre conteos: como `¿Coinciden remesas?` cuenta **filas**, si el otro Excel trae remesas duplicadas o filas con consecutivo en blanco, el conteo puede no cuadrar con los consecutivos únicos visibles.

**Modal "🔎 Consultar facturas (Excel)"** (`_abrir_modal_consulta`): herramienta **independiente del cruce** dentro del mismo módulo. Permite cargar un Excel cualquiera (ej. el archivo final del cruce), **con selector de hoja**, mapear la columna de N° Factura (auto-detección por hints de factura), y **pegar una lista de números de factura** (separados por coma, espacio, punto y coma o saltos de línea) en un cuadro de texto. Al buscar, normaliza cada número con `_norm_factura` (quita `.0` y espacios), filtra las filas del Excel cuyo N° Factura coincida, y muestra: cuántas se **encontraron** y cuáles **no se encontraron**, más una **tabla de previsualización de columnas dinámicas** con todas las columnas originales del Excel. Botón **"💾 Exportar encontradas"** guarda solo esas filas (todos sus datos tal cual) a Excel/CSV. Botón **"📋 Copiar tabla"** vuelca encabezados+filas de la previsualización al portapapeles como TSV (pegable en Excel) sin exportar. Botón **"🗑 Limpiar"** resetea archivo, hoja, columna, texto pegado, tabla y estado. Estado del modal aislado con prefijo `_cf_` (`_cf_xl`, `_cf_df`, `_cf_nombre`, `_cf_df_encontradas`) para no interferir con el estado del cruce.

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

### `ui/cumplir_remesa.py` — CumplirRemesaModule
Cumple una remesa en el RNDC vía **proceso 5** (`tipo=1`). Consultar → elegir **Tipo de Cumplido** → los tiempos se **auto-calculan** y quedan en campos **editables** (por si el usuario tiene los datos reales) → guardar (con confirmación). Cantidades siempre automáticas.

Dos formas de llenar los tiempos:
- **🔍 Consultar remesa** (`consultar_remesa_completa` proceso 3): trae las citas pactadas y **auto-calcula** los tiempos (cita +1/+2/+3).
- **📥 Traer tiempos del cumplido** (`consultar_remesa_completa` proceso 5, helper `_traer_tiempos_cumplido`): trae los **tiempos reales ya registrados** del cumplido y los vuelca a los campos editables. Sirve para el flujo **descumplir → corregir → re-cumplir**: se capturan los tiempos **antes de anular** (después el proceso 5 ya no los devuelve); como el panel conserva su estado entre pestañas, al volver basta con **Guardar**. Ajusta también el Tipo de Cumplido según lo que devuelve el proceso 5.

Lógica de cálculo automático (botón Consultar):
- **Cantidades**: `CANTIDADENTREGADA` = `CANTIDADCARGADA` (Normal `C`) o `0` (Suspensión `S`).
- **Tiempos logísticos**: por etapa, se parte de la cita pactada (fecha+hora) y se suma +1h (llegada), +2h (entrada), +3h (salida) → ~2h de operación. Helper `_fecha_hora_mas` usa aritmética real de `datetime`: si la hora pasa de medianoche, **avanza el día** (ej. `31/12 23:30 +3 → 01/01 02:30`), por eso cada campo lleva su propia fecha+hora.
- **Normal (`C`)**: llena cargue **y** descargue (campos `...CARGUE...` y `...DESCARGUE...`).
- **Suspensión (`S`)**: solo cargue + `MOTIVOSUSPENSIONREMESA="O"` (Otro); `CANTIDADENTREGADA=0`.

Nombres de variables del proceso 5: `TIPOCUMPLIDOREMESA` (`C`/`S`), `CANTIDADINFORMACIONCARGA`, `CANTIDADENTREGADA`, cargue: `FECHALLEGADACARGUE/HORALLEGADACARGUEREMESA`, `FECHAENTRADACARGUE/HORAENTRADACARGUEREMESA`, `FECHASALIDACARGUE/HORASALIDACARGUEREMESA`; descargue: `FECHALLEGADADESCARGUE/HORALLEGADADESCARGUECUMPLIDO`, `FECHAENTRADADESCARGUE/HORAENTRADADESCARGUECUMPLIDO`, `FECHASALIDADESCARGUE/HORASALIDADESCARGUECUMPLIDO`. Las fechas vienen en `DD/MM/AAAA` de la consulta (sin conversión).

### `ui/proceso_completo_remesa.py` — ProcesoCompletoRemesaModule ("Auto cambio-generador")
**Orquestador** bajo "Remesas" (título e ítem del sidebar: "Auto cambio-generador"): ejecuta toda la cadena de una vez. Entrada: consecutivo + nuevo NIT generador (combobox `8000213085`/`9007867123` o manual) + código sede (default `1`) + Tipo ID (default `N`) + motivos por defecto (anulación `O`, cambio `3`). Botón **Ejecutar proceso** con confirmación y **log paso a paso**. Secuencia:
1. Consultar cumplido (proceso 5) → captura tiempos reales **antes de anular**.
2. Consultar remesa (proceso 3) → captura `BASE_FIELDS` para corregir (aborta si falla).
3. Anular cumplido (proceso 28) **solo si estaba cumplida** (motivo `O`).
4. Corregir generador (proceso 38, `CODIGOCAMBIO=4`): base + `numIdPropietario`=NIT nuevo + sede + motivo.
5. Re-cumplir (proceso 5).

**Árbol de re-cumplido** (`_plan_cumplido`): si el proceso 5 trae tiempos reales → Normal (cargue+descargue) o Suspensión (solo cargue); si no, calcula de citas (proceso 3) → Normal si hay cita cargue+descargue, Suspensión si solo cargue.

**Cumplido condicional (no aborta):** el objetivo principal es **corregir el generador**, así que el corregir SIEMPRE se intenta. El cumplido (paso 5) se **omite con gracia** cuando no es posible: si la remesa está **Pendiente de asignar manifiesto** (`nummanifiestocarga` vacío en proceso 3 → `sin_manifiesto`), o si no hay tiempos ni citas (`_plan_cumplido` devuelve None). En esos casos corrige y termina informando que el cumplido quedó omitido.

**Sin rollback**: si un paso falla, **se detiene** y el log indica en qué punto quedó (para terminar a mano con los módulos paso-a-paso). **Reutiliza** funciones de servicio y constantes (`CorregirRemesaModule.BASE_FIELDS`, `CumplirRemesaModule.CARGUE_ROWS/DESCARGUE_ROWS/_fecha_hora_mas`) sin modificar esos módulos.

### Nota — credenciales de corrección/anulación
Los perfiles pueden definir `rndc_usuario_corregir` / `rndc_password_corregir`. Los módulos de **corregir**, **anular cumplido** y **cumplir remesa** usan un helper `_perfil()` que sustituye las credenciales normales por estas (si existen) **solo en esos módulos**; el resto de la app sigue con `rndc_usuario`/`rndc_password`. Si el perfil no las define, hace fallback a las normales. Actualmente `ut_tsp` las tiene (`CG_TSP@137`).

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
| `consultar_radicado_remesa(consecutivo, perfil)` | `services/rndc_service.py` | Retorna `(ok: bool, resultado: dict)` con `radicado`, `peso`, `estado`, `propietario`, `propietario_nit` (`numidpropietario`), `origen`, `destino`, `manifiesto` (`nummanifiestocarga`). Si el RNDC devuelve **varios `<documento>`** (remesa con historial), elige el de estado `CE` o, si no hay, el de mayor INGRESOID → evita el falso "AC/Pendiente" intermitente en consulta masiva |
| `consultar_remesa_completa(consecutivo, perfil, procesoid=3)` | `services/rndc_service.py` | `tipo=3` / `variables=*`. `procesoid=3`→datos de la remesa (citas); `procesoid=5`→datos del cumplido (tiempos reales). Retorna `(ok, dict)` con todos los campos |
| `corregir_remesa(variables, perfil)` | `services/rndc_service.py` | Proceso 38 / `tipo=1`. Envía a `rndcws.mintransporte.gov.co:8080` (sin "2"). `variables` es dict (orden respetado). Retorna `(ok, {ingresoid})` |
| `anular_cumplido_remesa(consecutivo, cod_motivo, perfil)` | `services/rndc_service.py` | Proceso 28 / `tipo=1`. Anula cumplido. `cod_motivo`: `D`=Error Digitación, `O`=Otro. Mismo endpoint que corregir |
| `cumplir_remesa(variables, perfil)` | `services/rndc_service.py` | Proceso 5 / `tipo=1`. Registra cumplido; `variables` dict. Mismo endpoint/credenciales que corregir |
| `_enviar_proceso_rndc(procesoid, variables, perfil)` | `services/rndc_service.py` | Envío genérico tipo=1 a `rndcws` (usado por corregir 38, anular 28, cumplir 5) |
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
- **Instanciación con `__new__` en `app.py`**: los módulos embebidos como panel (ej. `RndcUploaderWindow`, `ExcelLoaderWindow`) se crean con `ClassName.__new__(ClassName)` para poder pasar un `container` a `_build()` sin abrir un `Toplevel`. Esto **bypass `__init__`**, así que cualquier atributo de instancia que se inicialice en `__init__` **no existirá** al llamar `_build`. Regla: inicializar todos los atributos de estado en `_build()` con guards `if not hasattr(self, "attr"):` en lugar de solo en `__init__`. De lo contrario, llamadas como `self._mi_dict.clear()` en métodos posteriores lanzan `AttributeError` que Tkinter traga silenciosamente, dejando la UI sin datos sin ningún mensaje de error visible.
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
# IMPORTANTE: ejecutar desde dentro de testap\ (pathex=['.'] en el spec)
pyinstaller FE-Tool.spec
# o si pyinstaller no está en el PATH:
python -m pyinstaller FE-Tool.spec
```

El `.exe` queda en `dist\FE-Tool.exe`.

**Notas sobre la compilación:**
- Comando general: `pyinstaller FE-Tool.spec` o `python -m pyinstaller FE-Tool.spec` desde la carpeta `testap\`.
- Verificado con Python 3.13.2 + PyInstaller 6.14.1 (`pip show pyinstaller` para confirmar versión).
- En equipos con instalación no estándar de Python (ej. pythoncore-3.14), puede ser necesario usar la ruta absoluta al ejecutable: `C:\...\Scripts\pyinstaller.exe FE-Tool.spec`.
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
