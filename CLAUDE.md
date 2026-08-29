# CLAUDE.md — Contexto del proyecto FE-Tool

## ¿Qué es esta aplicación?

**FE-Tool** es una aplicación de escritorio en Python (tkinter) para la gestión de **facturación electrónica colombiana (DIAN UBL 2.1)** usada por la empresa **Unión Temporal American Logistic UT**, que opera con dos perfiles:

- **UT TSP** (Transportes Sánchez Polo S.A.)
- **UT Elogia** (Elogia Soluciones Logísticas S.A.S.)

Ambos perfiles facturan servicios de transporte de carga al cliente **Drummond Ltd** (NIT 800021308).

La app fue refactorizada de un monolito de ~5700 líneas (`generador_xml_tsp.py`) a una arquitectura modular de paquetes Python. **Los archivos originales no se modificaron** — solo se crearon archivos nuevos.

> **⚠️ Estado actual del desarrollo (línea activa = WEB).** La **app de escritorio (tkinter, `ui/`) está descontinuada**: ya no se desarrolla ni se compila a `.exe`. El desarrollo activo es la **versión web Streamlit** en `webapp/` — cualquier módulo o cambio nuevo se hace ahí. El escritorio se conserva como referencia (la lógica de `core/`, `services/`, `config/` se sigue reutilizando y es la fuente de verdad de la lógica de negocio). **Credenciales:** viven en `config/perfiles.py` (gitignored, dict `PERFILES`) para uso local, y en los **Secrets TOML de Streamlit** (`st.secrets["perfiles"]`, regenerados a `perfiles.py` por `webapp/bootstrap_perfiles.py`) para el despliegue. **No hay archivo `.env`** — si alguien menciona "el .env", se refiere a este mecanismo de `perfiles.py` + Secrets. Ejecutar en local: `streamlit run webapp/app.py` desde la raíz `testap/`.

## 🗺️ Mapa de la webapp (onboarding rápido — leer esto primero)

**La webapp es la línea activa.** Todo vive bajo `testap/`. Para trabajar en ella:

**Ejecutar (local):** `streamlit run webapp/app.py` desde `testap/`. Requiere `config/perfiles.py` (credenciales, gitignored). Deploy: Streamlit Cloud, main file `webapp/app.py`, credenciales en Secrets (ver `webapp/README.md`).

**Capas (quién llama a quién):**
```
webapp/app.py  ── UI Streamlit: TODOS los módulos como funciones modulo_*(perfil)
     │           (~19 módulos inline en este único archivo) + helpers
     ├── llama a → services/rndc_service.py   ← TODA la comunicación con el RNDC (WS SOAP)
     ├── llama a → core/xml_generator.py, core/xml_transformer.py  ← generar/transformar XML
     ├── llama a → webapp/lib_*.py  ← lógica pesada portada (excel, rndc86, editar, reconstruir, cruce, extraer, remesas)
     └── lee     → config/perfiles.py (PERFILES: credenciales/NITs por perfil) y config/ajustes.py (FOPAT_FECHA_INICIO)
```
Regla: **cambios de UI/flujo → `webapp/app.py`**; **nueva llamada al RNDC → `services/rndc_service.py`**; **credenciales/NITs → `config/perfiles.py`**; **parámetros de negocio → `config/ajustes.py`**. La carpeta `ui/` (tkinter) está **descontinuada** — no tocar salvo como referencia de lógica.

**Anatomía de `webapp/app.py`:**
- `main()` — construye la barra lateral (selector de perfil → `_selector_perfil`, expander **⚙️ Ajustes** con la **fecha FOPAT** (`fopat_fecha`) y el **máx. facturas por cargue** (`max_facturas`), y los grupos de módulos como botones) y renderiza el **módulo activo** (`st.session_state["modulo_activo"]`).
- `_grupos(perfil)` — **el registro**: dict `{grupo: {nombre_visible: funcion_modulo}}`. Aquí se **registran** los módulos y se define en qué grupo/orden aparecen.
- Cada módulo es una función `modulo_x(perfil)` que dibuja su UI y hace las llamadas. Su estado se guarda en `st.session_state` con un **prefijo propio** (ej. `cm_`=consultar manifiesto, `cmf_`=cumplir manifiesto, `cfp_`=corregir FOPAT, `fxr_`=factura por remesa, `cf2_`=consultar factura, `tl_`=tiempos logísticos, `cq_`=consultar remesas, `gm_`=generar XML). Cada módulo suele tener un botón **"🗑 Limpiar módulo"** que borra sus claves.

**Módulos actuales (registro en `_grupos`):**
- **🧾 Facturación:** Generar XML · Generar facturas vía Excel · Cargar facturas a RNDC (86) · Consultar factura (86, tipo 3) · Consultar factura por remesa (34)
- **📋 Remesas:** Consultar remesas · Corregir remesa (38) · Anular cumplido remesa (28) · Cumplir remesa (5) · Auto cambio-generador
- **📑 Manifiesto:** Consultar manifiesto (4) · Consultar tiempos logísticos (60) · Cumplir manifiesto (6) · Corregir FOPAT manifiesto · Anular cumplido manifiesto (29)
- **🔩 Otros:** Editar XML · Reconstruir XML · Extraer datos RG · Cruzar remesas

**Helpers clave en `app.py`:** `_perfil_corregir(perfil)` (sustituye credenciales por `rndc_usuario_corregir`, para corregir/anular/cumplir) · `_perfil_monitoreo(perfil)` (credenciales de monitoreo, proceso 60) · `_consec_efectivo`/`_consec` (prefijo `0` de ut_elogia) · `_fact_card` (tarjetas UI) · `_copiar_tabla` (botón copiar TSV) · `_cmf_get`/`_cmf_num` (leer/normalizar campos del cumplido) · `_aplica_fopat` (regla FOPAT por fecha de expedición).

**Para agregar un módulo nuevo:** (1) escribe `def modulo_x(perfil):` en `app.py` con su UI y su prefijo de `session_state`; (2) si necesita una consulta/envío nuevo al RNDC, agrega la función en `services/rndc_service.py` (clona una existente: consulta = `tipo=3` con `<documento>` y comillas simples; envío = `tipo=1` vía `_enviar_proceso_rndc` sin comillas); (3) regístralo en `_grupos(perfil)` en el grupo que corresponda. Envuelve cada operación en `try/except` y usa confirmación (checkbox) antes de operaciones reales.

> El resto de este documento detalla cada módulo, función y convención a fondo. Los detalles de cada `services/rndc_service.py` están en la **tabla de funciones** más abajo.

### Versión WEB (`webapp/`) — aditiva, no toca el escritorio
Existe una versión web con **Streamlit** en `webapp/`, pensada para **desplegarse** y usarse por navegador desde cualquier PC (evita el bloqueo de Smart App Control del `.exe`). **No modifica** la app de escritorio: reutiliza `core/`, `services/`, `config/` sin tocarlos, y re-implementa la UI (lo de `ui/` en tkinter) en Streamlit. Archivos: `webapp/app.py` (entrada, sidebar + perfil + módulos), `webapp/lib_excel.py` (port fiel de la lógica de parseo/filtros de `excel_loader._parsear`), `webapp/lib_rndc86.py` (port del envío SOAP proceso 86 de `rndc_uploader`). El sidebar replica los **grupos colapsables del desktop** (Facturación / Remesas / Manifiesto / Otros) con `st.sidebar.expander` por sección, y dentro los módulos como **botones** (`st.button` full-width). El módulo activo se guarda en `st.session_state["modulo_activo"]`; al hacer clic se actualiza y `st.rerun()`. La sección que contiene el módulo activo se muestra **desplegada** (las demás colapsadas), igual que el auto-expand del desktop. El activo lleva un prefijo `▶` y los no portados un sufijo `🚧` (muestran placeholder "Próximamente"). **Portados hasta ahora**: **Generar XML** (manual), Generar facturas vía Excel, Cargar facturas a RNDC, Consultar remesas, **Anular cumplido remesa** (28), **Anular cumplido manifiesto** (29), **Corregir remesa** (38), **Cumplir remesa** (5), **Auto cambio-generador**, **Editar XML** (Facturación + Remesas + Manifiesto completos + 1 de Otros). **Migración web COMPLETA (13/13 módulos)**. **Extraer datos RG** (web): `webapp/lib_extraer.py` porta `_extraer_pdf_bytes` (pdfplumber sobre `BytesIO`; junta el texto de **todas** las páginas), `_expandir_lineas` (conteo entero 1–100 → reparte VR.TOTAL; decimal/grande → 1 remesa; `cantidad_remesas_rg` = total de filas) y `procesar_pdfs` que intenta **ProcessPoolExecutor** (worker `_procesar_pdf_worker` a nivel de módulo, picklable) y **cae a secuencial** si el entorno no lo permite — preservando el orden de los archivos. La UI sube PDFs, checkbox "usar Referencia como consecutivo", barra de progreso, tabla por archivo (Archivo/N° Factura/Fecha/Líneas/Total/Estado), vista previa y descarga `datos_rg.xlsx`. **Extracción multipágina (arreglado):** la extracción de líneas procesa **todos los bloques de ítems** (no solo el primero) — encuentra cada header `REFERENCIA DESCRIPCION CANTIDAD UND VR.UNITARIO VR.TOTAL` (`header_re`) y toma las líneas hasta su footer (`Observaciones`/`SUBTOTAL`, `footer_re`) **o** hasta el siguiente header, lo que llegue primero. Así los PDFs de **2+ páginas** cuentan las remesas de todas las páginas (antes se perdían las de la página 2+ porque solo se leía el bloque entre el primer header y el primer `SUBTOTAL`). `cantidad_remesas_rg` = total de filas de todas las páginas. Helper `_parsear_linea` para el parseo por línea (mismos dos regex de siempre). Solo cambió `_extraer_pdf_bytes`; PDFs de una página se comportan igual. **Dígito de verificación (auto):** las RG traen el NIT **sin** dígito de verificación; `_extraer_pdf_bytes` lo calcula (módulo 11 DIAN, pesos `_DV_PESOS`, helpers `_digito_verificacion`/`_nit_con_dv`) y lo anexa al NIT del `datos_rg` (ej. `800021308`→`8000213085`). Si el número **ya trae un DV válido** como último dígito, lo **respeta** (no duplica) — detecta comparando `_digito_verificacion(s[:-1])==s[-1]`. Sin tabla por cliente. **Prefijo Elogia + columna `perfil` (auto):** `_perfil_por_consecutivo(consec)` detecta el perfil por el formato del consecutivo de la RG y normaliza el número: **Elogia** empieza en `101` → antepone `0` (`101203057`→`0101203057`; si ya trae `0101…` lo respeta); **TSP** empieza en `300` (ej. `30016958`) o `120` (ej. `12063370`); si no cae en ninguna regla → `('', consec)` (no se adivina, queda con `perfil` **vacío** para revisión). Se agrega la columna **`perfil`** (tsp/elogia) a `COLUMNAS_EXPORT`/`datos_rg`. Aplica cuando `usar_ref_como_consec` está activo.

**Generar facturas vía Excel (web) — auto-mapeo + split de perfil.** (1) **Auto-mapeo:** al cargar un archivo/hoja nuevo, los combos de mapeo se siembran solos con las columnas detectadas por nombre (`lib_excel.auto_mapear(df)` — match normalizado **exacto** contra `_AUTO_HINTS`, sin substring para no confundir `nit` con `valor_unitario`; los campos sin match quedan en "— No usar —"). Como `datos_rg` tiene nombres fijos, queda **todo mapeado solo** (incl. la nueva columna `perfil`), **excepto `radicado`** que a propósito NO se auto-mapea (queda "— No usar —"): en datos_rg siempre viene vacío y el radicado se consulta solo al RNDC por consecutivo (fase 1 del generado). El usuario puede cambiar cualquier mapeo y persiste hasta que cambie archivo/hoja/columnas (guard `gx_map_sig`). (2) **Columna `perfil` opcional** (nuevo campo `col_perfil` en `lib_excel.CAMPOS`; `parsear` la lee y pone `perfil` en cada factura: `tsp`/`elogia` o `""`). (3) **Split de perfil** — el módulo genera TSP con perfil TSP y Elogia con perfil Elogia **en una sola pasada** (fase de radicados y de generación usan el perfil de cada factura vía helper local `_pf`). Regla **estricta**: si la columna `perfil` trae `tsp`/`elogia` → ese perfil; **si el Excel no trae la columna `perfil` (o la fila viene vacía) → el perfil seleccionado arriba** (sin mirar el consecutivo). Vista previa y resumen muestran el desglose (TSP / Elogia / perfil seleccionado); zip único `facturas_generadas.zip`. Helper `_perfil_de_factura` (detección por consecutivo) queda disponible pero ya no se usa en la resolución estricta. Compatible con `datos_rg` sin columna `perfil` (todo con el perfil activo). (4) **Máx. facturas por cargue configurable:** el tope (antes fijo en 100) vive en `config/ajustes.py` (`MAX_FACTURAS_GENERAR=100`) y es ajustable por sesión en **⚙️ Ajustes** (key `max_facturas`); helper `_max_facturas()` (leído por `_get_cantidad_web` y la etiqueta del campo "Cuántas generar").

**Cargar facturas a RNDC (web) — soporte de `.zip`.** El uploader acepta `.xml` **y `.zip`** (varios, mezclados). Helper `_cr_expandir(archivos)` deja la lista `(nombre, bytes)` en `cr_data`: los `.xml` tal cual y, de cada `.zip`, **todos sus miembros `.xml`** (ignora no-XML y carpetas, usa el nombre base). Así se sube directo el `facturas_generadas.zip` de "Generar facturas vía Excel" sin descomprimir. El resto del módulo (tabla de facturas detectadas, envío proceso 86 vía `lib_rndc86`) no cambia — solo itera `cr_data`.

**Cruzar remesas** (web): `webapp/lib_cruce.py` porta verbatim toda la lógica (`to_num`, `fmt_consec`, `norm_factura`, `cruzar`, `exportar`, `pasa_filtro`, constantes `CAMPOS_*`/`PASSTHROUGH_OTRO`/`FILTROS_EXPORT`/`HINTS`) con las últimas actualizaciones: salto de consecutivos vacíos del otro Excel, comparación de valor por unitarios del RG (`rg_col_val_un`) o del otro Excel, passthrough genérico de las 6 columnas opcionales, y filas extra para remesas sobrantes. La UI: dos uploaders (RG/otro) con selector de hoja, mapeo con auto-detección sembrada una vez (se limpia al cambiar archivo), tabla de resultados (9 columnas incl. "Suma unitarios comparada"/"Base"), filtro de exportación + descarga `.xlsx`, y un expander **"Consultar facturas (Excel)"** (busca facturas por número pegado, exporta encontradas). **Reconstruir XML** (web): `webapp/lib_reconstruir.py` reutiliza `core.xml_transformer.reconstruir_factura` (file-based) vía **archivos temporales** y porta `preprocesar_str` (limpia ShareholderParty + normaliza ancla), `actualizar_radicados_str` (consulta RNDC por consecutivo, sobrescribe radicado/peso, con `peso_fijo` del checkbox) y `leer_cabecera_str`. La UI sube XMLs, muestra perfil/cabeceras y la tabla de **remesas leídas del XML** (`leer_remesas_str`: consecutivo/radicado/peso) ya al cargar (estado "Pendiente", una fila por remesa), checkbox "Peso por defecto = 1 KGM", reconstruye en lote (la tabla se reemplaza por los resultados con radicado/peso del RNDC) y descarga los resultados en un `.zip`. **Editar XML**: la lógica de parseo/guardado por regex (CDATA, InvoiceLine, N°/CUFE/cliente/NIT-dígito anti-FAC025, fecha+vencimiento, total+retención, +/− remesas) se porta verbatim a `webapp/lib_editar.py` (`parse_xml`, `guardar_xml`); la UI usa filas +/− para remesas, auto-consulta RNDC al cargar, y descarga el XML modificado (no sobrescribe archivo local). Añade un **checkbox "Peso por defecto = 1 KGM"** (que el desktop solo tiene en Reconstruir XML): si se marca, bloquea el campo peso y fuerza `1` en todas las remesas al guardar. El módulo Generar XML maneja las remesas con **filas +/−** (no `st.data_editor`, que se bugea con sus controles nativos): cada remesa se guarda en `st.session_state["gm_remesas"]` (lista de dicts con `_id` único para keys estables), se muestra con su **N°**, sus campos (`text_input` con key `gm_f_{id}_{campo}` sembrado desde el dict) y un botón **−** para quitar esa remesa (mín. 1); un botón **＋ Agregar remesa** añade una con defaults (Peso=1, Descripción=Servicio de transporte) — sin "None". Botón de auto-consulta de radicados/pesos al RNDC (actualiza el dict y el `session_state` del widget). Valida igual que `GeneradorApp._generar` (fecha multi-formato, `_parse_valor`) y descarga el XML. Las constantes de los módulos de remesas (`CORREGIR_BASE_FIELDS`, `CUMPLIR_CARGUE_ROWS/DESCARGUE_ROWS`, `fecha_hora_mas`, `plan_cumplido`, `AUTO_*`, etc.) se copian a `webapp/lib_remesas.py` para no importar tkinter. Auto cambio-generador replica `_procesar_remesa` (5 pasos: consultar 5 → consultar 3 → anular 28 con fallback a manifiesto 29 → corregir 38 generador → re-cumplir 5), procesamiento en lote con resumen, sin abortar todo si una falla. **Restauración del cumplido del manifiesto**: cuando la anulación del cumplido de la remesa falla porque el **manifiesto está cumplido**, ANTES de anular el manifiesto (proceso 29) se **captura su cumplido** con `consultar_manifiesto_completo(manifiesto, perfil, procesoid=6)`; al final del proceso (tras re-cumplir la remesa, o en la ruta sin cumplido) se **vuelve a cumplir el manifiesto** (`_recumplir_manifiesto`) con un set fijo de campos tomados del snapshot (tipo, fecha, valores) vía `cumplir_manifiesto`, respetando la **regla FOPAT** (ver abajo: si es pre-FOPAT, sin `RETENCIONFOPAT` y con `RETENCIONFUENTEMANIFIESTO`). Esto solo ocurre en ese caso específico (manifiesto cumplido que bloquea la anulación); si la remesa se anuló normalmente, no se toca el manifiesto.

**Consultar manifiesto (web)**: módulo en el grupo Manifiesto que usa `consultar_manifiesto_completo` (proceso 4 = consultar manifiesto, `tipo=3`, `variables=*`; el proceso 6 es cumplir manifiesto, futuro). La consulta **trae todas las variables** (sin cambios), pero la UI muestra **solo los campos de "Información General"** con nombres amigables (`_MANIF_CAMPOS`: N° Radicado, Fecha Expedición, Placa, Semirremolque, Conductor, Identificación, Origen, Destino, Observaciones). `_manif_curado` mapea cada etiqueta a varios nombres candidatos de variable del RNDC y usa el primero presente (case-insensitive). Muestra: ficha vertical Campo/Valor (si es uno solo) + tabla de los manifiestos consultados (columnas = Info General) + descarga CSV. Las variables crudas completas quedan en un expander colapsado "🔧 ver todas las variables (avanzado)" por si hay que ajustar el mapeo. Reutilizable para futuros módulos sobre manifiestos. **Remesas del manifiesto (sección añadida):** el proceso 4 **no** trae las remesas ni sus citas — solo el conteo (`mancantidadremesas`). Por eso, por cada manifiesto **encontrado**, el módulo llama además a `consultar_remesas_por_manifiesto(man, _perfil_corregir(perfil))` (**proceso 3** filtrado por `NUMMANIFIESTOCARGA`, `variables=*`) y muestra una sección **"📦 Remesas de los manifiestos (N)"**: tabla con una fila por remesa (helper `_manif_remesa_curada` + `_MANIF_REMESA_CAMPOS`: **N° Remesa** (`consecutivoremesa`), Radicado, Estado, Fecha/Hora cita cargue, Fecha/Hora cita descargue, Origen, Destino, Propietario, Producto, Peso/Cant.), con "📋 Copiar tabla", descarga CSV propia, y un **segundo expander "🔧 Ver todas las variables crudas de las remesas (avanzado)"** (por remesa, encabezado "Manifiesto {N°} · Remesa {consec}"). Estado en `session_state["cm_remesas"]` (dict `{man: [remesas]}`), limpiado por `_cm_limpiar`; la consulta va en `try/except` (si falla, no se muestran remesas y el resto sigue igual). No toca el módulo Consultar remesas ni ningún otro.

**Cumplir manifiesto (web)**: módulo en el grupo Manifiesto. Consulta **proceso 4** (datos generales) **y proceso 6** (formulario del cumplido pre-llenado: valores pactados/finales del viaje, horas reales/pactadas, fletes, etc.) y **combina** ambos (`{**res4, **res6}`, el 6 tiene prioridad) para tener todos los campos del cumplido. (Proceso 6 = cumplir manifiesto = el envío; proceso 4 = consultar manifiesto.) El **estado** se lee del campo `estado`: `CE`=ya cumplido (bloquea), `AC`=pendiente por cumplir (permite). La UI muestra info general + expander con todos los campos, y solo pide **Tipo de Cumplido** (`C`=Normal / `S`=Suspensión, verificados contra el RNDC) y **Fecha de entrega documentos** (`st.date_input`, DD/MM/AAAA). Al cumplir arma un **set fijo de campos** (no passthrough) vía `cumplir_manifiesto` (proceso 6, `tipo=1`): `NUMNITEMPRESATRANSPORTE`, `NUMMANIFIESTOCARGA`, `TIPOCUMPLIDOMANIFIESTO`, `FECHAENTREGADOCUMENTOS`, `VALORADICIONALHORASCARGUE`, `VALORDESCUENTOFLETE`, `MOTIVOVALORDESCUENTOMANIFIESTO="F"`, `VALORSOBREANTICIPO`, y **siempre ambas** `RETENCIONFOPAT` **y** `RETENCIONFUENTEMANIFIESTO` (el FOPAT en 0 para manifiestos pre-FOPAT — ver regla FOPAT abajo). Los valores monetarios se sembraban de la consulta (proceso 6 si CE, si no proceso 4) y son editables; `_cmf_num` normaliza (vacío→"0", formato colombiano). Credenciales de corrección (`_perfil_corregir`).

**Regla FOPAT (0,1%) — módulos Cumplir manifiesto y Auto cambio-generador.** El FOPAT solo aplica a manifiestos cuya **fecha de expedición** (`fechaexpedicionmanifiesto`) sea **en o después** de `FOPAT_FECHA_INICIO` (config `config/ajustes.py`, default **2026-04-01**; ajustable por sesión en la barra lateral → **⚙️ Ajustes**, key `fopat_fecha`). Helper `_aplica_fopat(fecha_exp)` (usa `_parse_fecha_manif`; si no parsea la fecha → True, mantiene comportamiento previo). **Enfoque final (uniforme): el cumplido SIEMPRE envía las dos etiquetas** `RETENCIONFOPAT` **y** `RETENCIONFUENTEMANIFIESTO`:

- **Pre-FOPAT** (fecha < umbral): `RETENCIONFOPAT` se fuerza a **`0`** y en la UI del módulo Cumplir manifiesto el campo "Retención FOPAT" queda **deshabilitado** (no editable); `RETENCIONFUENTEMANIFIESTO` = valor del consult (o 0).
- **FOPAT vigente** (fecha ≥ umbral): `RETENCIONFOPAT` = valor real (editable); `RETENCIONFUENTEMANIFIESTO` = valor del consult.

**Combos verificados en vivo contra el RNDC** (manifiesto 11512532, exp 3/01/2024): (a) `RETENCIONFOPAT`=valor sin retefuente → OK; (b) `RETENCIONFOPAT=0` **o** omitir la etiqueta, **sin** retefuente → **`Error CMA262: Hace falta el valor de Retención en la Fuente. Es un dato obligatorio.`**; (c) `RETENCIONFOPAT=0` **+ con** `RETENCIONFUENTEMANIFIESTO` → **OK** (cumplido queda con `retencionfopat=0`, saldo sin descuento del 0,1%); (d) `RETENCIONFOPAT`=valor + retefuente → OK. Conclusión: **cuando el FOPAT es 0, el RNDC obliga a mandar la retención en la fuente** — por eso se envían siempre las dos. (Se descartó "omitir FOPAT" en favor de "FOPAT=0 + retefuente" por ser más uniforme; ambos dan el mismo resultado.)

UI Cumplir manifiesto: muestra **ambos** campos (Retención en la Fuente + Retención FOPAT, en 5 columnas); el de FOPAT bloqueado en 0 si es pre-FOPAT. Sembrado: `cmf_rfopat`="0" si pre-FOPAT (si no, valor del consult), `cmf_refte`=retención fuente del consult. **Auto cambio-generador** (`_recumplir_manifiesto`) lee `fechaexpedicionmanifiesto` del snapshot (proceso 6) y aplica la misma regla. Nota: el `retencionfopat` que muestra la **consulta proceso 4** es un valor **calculado a nivel de manifiesto** (informativo); lo real del cumplido está en **proceso 6** (ahí queda en 0). Los manifiestos FOPAT-vigentes ahora también envían `RETENCIONFUENTEMANIFIESTO` (el RNDC lo acepta junto con el FOPAT — verificado).

**Corregir FOPAT manifiesto (web)** — módulo `modulo_corregir_fopat_manifiesto` (grupo Manifiesto, entre Cumplir y Anular cumplido) + helper `_corregir_fopat_manifiesto`. Corrige **en lote** manifiestos **pre-FOPAT que quedaron cumplidos CON FOPAT**: recibe varios N° de manifiesto (coma/espacio/salto, dedup), motivo de anulación (selectbox, default `O`) y observaciones. Por cada manifiesto: consulta proceso 4 (fecha exp + estado); **omite** si es FOPAT-vigente (`_aplica_fopat`) o no está cumplido (estado ≠ CE); si es pre-FOPAT y CE → captura el cumplido (proceso 6: tipo, fecha, retención fuente, valores, y el fopat original para restaurar), **anula** el cumplido (proceso 29), y **re-cumple** con `RETENCIONFOPAT=0` + `RETENCIONFUENTEMANIFIESTO` (conservando tipo/fecha/valores del snapshot). **Red de seguridad:** si el re-cumplido sin FOPAT falla, restaura el cumplido original (con su FOPAT) para no dejar el manifiesto descumplido. Muestra un **log paso a paso** + resumen (corregidos / FOPAT vigente / no cumplidos / errores). Credenciales de corrección (`_perfil_corregir`). Verificado en vivo (manifiesto 11512532).

**Consultar factura (web)** — módulo `modulo_consultar_factura` en `webapp/app.py`, grupo **Facturación** (después de "Cargar facturas a RNDC"). Consulta una factura electrónica **ya cargada** al RNDC por su **número**, **sin subir XML**, vía `consultar_factura` (proceso 86, `tipo=3`, `variables=*`, filtro `NUMEROFACTURA` + `NUMNITEMPRESATRANSPORTE=nit_socio`). Aclaración clave: en proceso 86 `tipo=1`=cargar (el `ARCHIVOBASE64` es el XML en base64) y `tipo=3`=consultar (el `<documento>` lleva el filtro `NUMEROFACTURA`, **no** `ARCHIVOBASE64`). Usa las **credenciales normales** del perfil (`rndc_usuario`/`rndc_password`) — funciona igual para ut_tsp y ut_elogia. Acepta **uno o varios** números (coma/espacio/salto de línea, dedup). La UI muestra: **ficha "Datos de la factura"** (si hay un solo resultado) con campos curados (`_FACT_CAMPOS`, `_fact_curado`): N° Factura, **Estado** (`_estado_factura_txt`: `CE`→"Cumplida electrónicamente", `AC`→"No aprobada / rechazada"), Tipo documento, N° Radicado (`ingresoid`), Fecha creación (`fechacrea`), Fecha+Hora factura, **Aprobado** (`_fact_limpio` convierte el marcador `"."` del RNDC en vacío), NIT mandatario, CUFE, Tipo operación, Valor fletes, Subtotal, NIT facturador, NIT adquirente, Líneas, Remesas, Kilogramos; **tabla** de todas las consultadas con "📋 Copiar tabla" + descarga CSV; y expander **"🔧 Ver todas las variables crudas del RNDC (avanzado)"** con las ~35 variables tal cual. Estado en `session_state` con prefijo **`cf2_`** (deliberadamente distinto del `cf_` que usa el modal "Consultar facturas (Excel)" de Cruzar remesas, para no colisionar). Mismo patrón/UI que "Consultar manifiesto". **Filtro por rango de fecha (opcional)**: checkbox "📅 Filtrar por rango de fecha de la factura" con dos `date_input`. Si escribes N° de factura → **modo número** (el rango se ignora, avisa). Si NO escribes número pero activas el rango → **modo rango**: trae **todas** las facturas del rango vía `consultar_facturas_por_fecha`. Descubrimiento empírico: el WS del proceso 86 **NO soporta rango nativo** — solo filtra por `FECHAFACTURA` **exacta** (formato `YYYY-MM-DD`; `DD/MM/YYYY`, operadores `>=`/`<=`/`BETWEEN` y campos `FECHAINICIAL*`/`FECHAFINAL*` dan `Error RNDC027`) y sin número devuelve todas las facturas de ese día — por eso el rango se consulta **día por día** y se agrega (tope 93 días). La vista avanzada de variables crudas escala: ficha vertical si ≤3 facturas, tabla combinada si son más.

**Consultar factura por remesa (web)** — módulo `modulo_consultar_factura_por_remesa` en `webapp/app.py`, grupo **Facturación** (después de "Consultar factura"). Busca la **factura electrónica asociada a una remesa** vía `consultar_factura_por_remesa` (**proceso 34** = Tarifas Generador, `tipo=3`, `variables=*`). Filtro: `NUMIDEMPRESA` = `nit_socio` del perfil (automático), `NUMIDGENERADOR` = NIT del generador (lo digita el usuario, ej. `8000213085` = Drummond) y `CONSECUTIVOREMESA`. Credenciales **normales** del perfil. **Multi-remesa:** el consecutivo es un `text_area` que acepta varias remesas (coma/espacio/salto de línea, dedup), con un solo generador para todas; consulta en lote con barra de progreso (una remesa que falle no detiene el resto). UI: **tarjetas** (reutiliza `_fact_card`/`_fact_limpio`) con la **factura electrónica destacada en verde** + grid del resto (`_FXR_CAMPOS`/`_fxr_curado`: N° Remesa, Tipo factura, Radicado remesa, Estado, Fecha, Generador/NIT, Empresa/NIT, Origen, Destino, Operación, Configuración, Valor tarifa, Valor flete línea, Cantidad remesas, N° Manifiesto, Radicado manifiesto, Aprobado) **solo cuando hay una sola encontrada**; siempre una **tabla "📑 Remesas consultadas"** (`_FXR_COLS_TABLA`) con "📋 Copiar tabla" + CSV; y expander de variables crudas (ficha vertical si ≤3, tabla combinada si más). El campo clave de la respuesta es `facturaelectronica` (ej. `42-1022936`). Estado en `session_state` con prefijo **`fxr_`**. No toca ningún otro módulo/servicio. **Segundo modo — por número de factura:** el módulo tiene además un `text_area` "…o Número(s) de factura" que consulta **todas las remesas de una(s) factura(s)** vía `consultar_remesas_por_factura` (proceso 34 filtrando por `FACTURAELECTRONICA`, devuelve **un documento por remesa**; la cantidad = nº de documentos). Si escribes facturas **tiene precedencia** sobre las remesas (avisa). Por cada factura muestra (`_fxr_render_facturas`): ficha con tarjetas (Factura destacada, Generador, NIT generador, Empresa, Estado, Tipo factura, **Cantidad remesas**), una tarjeta **"Consecutivos de remesa"** con todos los números, una **tabla de remesas** (`_FXR_REM_COLS`: N° Remesa, Radicado, Origen, Destino, Configuración, Valor flete, Línea, Estado; ordenada por línea con `_fxr_int`) con Copiar/CSV, y expander de variables crudas. Modo factura usa `session_state["fxr_fact_res"]`; cada consulta limpia el estado del otro modo. Verificado en vivo (factura 421023269 → 6 remesas).

**Consultar tiempos logísticos (web)** — módulo `modulo_consultar_tiempos` en `webapp/app.py` (grupo Manifiesto/Otros): consulta los **tiempos de monitoreo de flota** de un manifiesto vía **proceso 60** (`tipo=3`, `variables=*`) del RNDC. Se consulta por **N° de manifiesto** (uno o varios, pegables separados por coma/espacio/salto de línea; dedup preservando orden) y/o por **placa** (opcional). Flujo por manifiesto: (1) `consultar_manifiesto_completo(man, procesoid=4)` para obtener el **radicado** (`ingresoidmanifiesto`/`ingresoid`); (2) `consultar_monitoreo_manifiesto(_perfil_monitoreo(perfil), radicado_manifiesto=radicado, placa=placa)` → devuelve **un `<documento>` por punto de control** monitoreado; (3) `consultar_remesas_por_manifiesto` (proceso 3) para leer las **citas pactadas** de cargue/descargue y contrastarlas con los tiempos reales. La UI separa **tiempos de origen (cargue, punto de control 1)** y **destino (descargue, último punto > 1)**, con campos amigables (`_MONITOREO_CAMPOS`: punto de control, placa, fecha/hora llegada, fecha/hora salida, minutos en punto, minutos monitoreo, latitud, longitud, estado), tabla consolidada y estado global del monitoreo. **Credenciales especiales:** usa `_perfil_monitoreo(perfil)` que sustituye por `rndc_usuario_monitoreo`/`rndc_password_monitoreo` (fallback a las normales); requiere que el perfil tenga `nit_monitoreo` (NIT de la empresa de monitoreo de flota / EMF, va como `NUMIDGPS`), si no, bloquea con error. `NUMNITEMPRESATRANSPORTE` = `nit_socio` del perfil.

**Modelo de puntos de control (proceso 60):** cada viaje/manifiesto tiene puntos identificados por `codpuntocontrol`: **`1`=origen (cargue)**, **`2`=destino (descargue)** — en la práctica solo existen esos dos (no hay intermedios). Un manifiesto normal tiene ambos. Los documentos de monitoreo traen `ingresoidmanifiesto` (el radicado) pero **NO** `nummanifiestocarga`.

**Rango de fecha opcional (modo placa):** una placa **sin** fecha trae **todo** su historial (descontrolado). Checkbox "📅 Acotar por rango de fecha" + dos `date_input`; se pasa a `consultar_monitoreo_manifiesto(fecha_inicial, fecha_final)` **solo en modo placa** (en modo por N° de manifiesto la fecha no aplica: ya viene acotado, y filtrar por fecha partiría los puntos del viaje). El WS del proceso 60 tampoco soporta rango nativo: solo filtra por `FECHACREA` **exacta** (`YYYY-MM-DD`; verificado que `FECHACREA`/`FECHALLEGADA`/`FECHASALIDA` filtran, `DD/MM/YYYY` y operadores dan `RNDC027`, día sin datos da `RNDC11`), así que el rango se consulta **día por día** (tope 93).

**Enriquecimiento por radicado + viaje completo (modo placa):** como los docs de monitoreo no traen el N° de manifiesto ni las citas, en modo placa se **agrupan los puntos por `ingresoidmanifiesto` (radicado)** y por cada grupo (tope **25** manifiestos, para no lanzar demasiadas peticiones): (1) se trae el **viaje completo** con `consultar_monitoreo_manifiesto(pm, radicado_manifiesto=rad)` (todos los puntos, **sin** filtro de fecha — así el rango sirve solo para *descubrir* qué viajes estuvieron activos, y no "parte" un viaje cuyo otro punto se radicó fuera del rango); (2) se resuelve el **N° de manifiesto** con `consultar_manifiesto_por_radicado(rad, _perfil_corregir(perfil))` (proceso 4 filtrando por `INGRESOID` — verificado que `INGRESOID` sí filtra, `INGRESOIDMANIFIESTO`/`NUMRADICADO` dan `RNDC027`); (3) se leen las **citas pactadas** con `consultar_remesas_por_manifiesto`. Con **fallback**: si el viaje completo falla/viene vacío se usan los puntos del filtro (`grupos[rad]`); si hay >25 manifiestos se omite el enriquecimiento y se muestra solo el radicado con los puntos del rango. Cada grupo produce el mismo "item" `{man, radicado, docs, citas, error}` que el modo por N° de manifiesto, así que la tabla/fichas se renderizan igual. Aclaración sobre "solo origen"/"solo destino": tras esta mejora, un viaje solo aparece incompleto si de verdad no ha reportado el otro punto (ej. descargue aún sin reportar); ya no por el corte del filtro (`fechacrea` de radicación ≠ `fechallegada` real, y los dos puntos de un viaje se radican en días distintos).

**Color de estado en Consultar remesas (web)**: la tabla colorea la columna Estado con un `pandas Styler` (`_style_estado`, vía `df.style.map` con fallback `applymap` para pandas<2.1): verde=Cumplida, rojo=no existe/no radicada (`✗`), amarillo=Pendiente (asignar manifiesto / por cumplir) — mismo criterio que `_estado_txt_color` del desktop. No altera la lógica de consulta ni el CSV exportado.

**Variables crudas en Consultar remesas (web)**: el módulo consulta por **consecutivo** con `consultar_radicado_remesa` (proceso 3, **NO** pide `variables=*` — solo 9 variables: `INGRESOID, CONSECUTIVOREMESA, CANTIDADCARGADA, ESTADO, REMPROPIETARIO, REM_DESTI, REM_ORIG, NUMMANIFIESTOCARGA, NUMIDPROPIETARIO`; consulta "ligera" para ver muchas remesas rápido, con su lógica de multi-documento CE/mayor-INGRESOID para el estado correcto). Para ver **todas** las variables hay un checkbox **opt-in** "🔧 Traer variables crudas (avanzado, más lento)" (`cq_raw`, off por defecto): si se activa, por cada remesa hace **1 consulta extra** con `consultar_remesa_completa(consec, perfil)` (proceso 3, `variables=*`, ~124 variables) usando el **mismo consecutivo** (el módulo no aplica prefijo), y las muestra en un expander "🔧 Ver todas las variables crudas del RNDC (avanzado)". Estado en `session_state["cq_full"]`; la tabla curada (`consultar_radicado_remesa`) queda intacta; consulta raw en `try/except`. Se deja opt-in para que las consultas masivas sigan rápidas por defecto.

**Caché de estado y botones Limpiar (web)**: para imitar al desktop (los paneles conservan su estado al cambiar de módulo), los archivos subidos se cachean en `st.session_state` con claves dedicadas (no de widget): Excel→`gx_bytes`/`gx_name`, XMLs→`cr_data` (lista `(nombre, bytes)`), resultados de consulta→`cq_filas`, consultas RNDC→`cor_res`/`acr_res`/`cum_res`. Así persisten al navegar entre módulos. Cada módulo tiene un botón **"🗑 Limpiar módulo"** que llama `_limpiar_modulo([prefijo])` (borra de session_state las claves con ese prefijo y hace `st.rerun()`). Helpers en `app.py`: `_perfil_corregir` (sustituye credenciales `rndc_usuario_corregir`, igual que `_perfil()` del desktop) y `_consec_efectivo` (prefijo `0` de ut_elogia). Confirmación de operaciones reales vía checkbox antes del botón. No depende de tkinter. Ejecutar: `streamlit run webapp/app.py` desde la raíz. Mapeo desktop→web: `filedialog`→`st.file_uploader`; guardar en carpeta→`st.download_button`/`.zip`; tablas→`st.dataframe`; confirmación modal→checkbox. Las credenciales salen de `config/perfiles.py` local (gitignored — nunca subir a repo público). **Despliegue**: `webapp/bootstrap_perfiles.py` (`asegurar_perfiles`, llamado al inicio de `app.py` ANTES de importar config/core/services) genera `config/perfiles.py` desde `st.secrets["perfiles"]` si el archivo no existe (Streamlit Cloud); en local no toca nada. Solo las credenciales RNDC vienen del secreto; el resto de la estructura (NITs, nombres) está hardcodeada en la plantilla (no es sensible). Deploy: push a GitHub sin `perfiles.py`, main file `webapp/app.py`, y pegar los Secrets TOML (ver `webapp/README.md`).

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
│   ├── anular_cumplido_manifiesto.py ← AnularCumplidoManifiestoModule: anula el cumplido de un manifiesto (proceso 29)
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

> Convenciones de UI comunes: los módulos con tabla (`consultar_remesas` incl. modal masivo, `editar_xml`, `rndc_uploader`) tienen botón **"📋 Copiar tabla"** que vuelca encabezados+filas al portapapeles como TSV (pegable en Excel). En `consultar_remesas` (tabla + modal) y `rndc_uploader` (facturas + remesas), **doble clic en una celda** abre un campo con el texto seleccionado para copiar (helper `_hacer_celda_copiable`). Los módulos de remesa RNDC (`corregir_remesa`, `anular_cumplido_remesa`, `cumplir_remesa`, `proceso_completo_remesa`) tienen botón **"🗑 Limpiar"** que resetea consecutivo, campos, combos a default y estado. La versión de la app (header y sidebar de `app.py`) es **V1.5**.

### `ui/app.py` — GeneradorApp
Ventana principal. Construye:
- **Header** con logo FE-Tool
- **Pill bar** de selección de perfil (ut_tsp / ut_elogia)
- **Sidebar** con grupos colapsables: Facturación / Remesas / Manifiesto / Otros
- **13 paneles** de contenido (uno por módulo), mostrados/ocultados con `pack/pack_forget`
- **Barra de estado** inferior

Al cambiar de perfil notifica activamente a `_rndc_uploader`, `_excel_loader` y `_reconstruir_module`.

### `ui/excel_loader.py` — ExcelLoaderWindow
Carga un archivo Excel (con **selector de hoja**), mapea columnas a campos de factura (consecutivo, radicado, valor, peso, descripción, CUFE, fecha) y genera XMLs en lote. Consulta el RNDC automáticamente si hay consecutivos.

**SIN auto-mapeo de columnas (todo manual)**: el módulo **no adivina ni asigna columnas automáticamente** en ningún momento. Al cargar el archivo, todos los combos de mapeo quedan en "— No usar —" y el usuario elige cada columna a mano; su elección **se queda fija** y nada la re-selecciona después. `_on_hoja_change` (cambio de hoja) solo refresca las **listas** de los combos y limpia una selección únicamente si su columna **ya no existe** en la hoja nueva. Cambiar el filtro de generación o mapear cualquier campo **no altera** otros mapeos. Los combos de valores-condición (`_actualizar_cond_valores(solo_clave, sugerir_default)`) solo **pueblan su lista** desde la columna que el usuario mapeó (vía trace `solo_clave=clave`, que toca **solo ese** combo); nunca eligen un valor por su cuenta (`sugerir_default` quedó en False en todos los llamados). Se eliminaron el auto-match por hints, el método `_auto_mapear` y `_mapeo_manual`. Razón: el auto-mapeo re-seleccionaba columnas (ej. NIT) al cambiar filtros/criterios, corrompiendo la generación. La columna `Novedad remesa` (y todas las opcionales) se pueden mapear con **cualquier** filtro, no solo con "Reconstruir = Sí y Novedad vacía".

Mapeo **opcional de cliente por columna**: campos `NIT cliente` y `Nombre cliente`. Si se mapean, cada factura usa su propio NIT/nombre del Excel; **el dígito de verificación se toma del último dígito del NIT** (ej. `8000213085` → NIT `800021308`, dígito `5`, limpiando cualquier formato). Si no se mapean, usa los valores fijos de la sección "Datos del Cliente". Auto-mapea las columnas `nit`/`nombre_cliente` que exporta `extraer_datos_rg.py` (con guard para que `nit` no colisione con `valor_unitario`).

**Filtro de generación** (`FILTROS_GEN`): combobox que permite generar solo un subconjunto cuando el Excel trae las columnas de validación del cruce (`¿Coinciden remesas?`, `¿Coincide valor factura con RG?`, `Reconstruir`). Opciones: Todas / Solo Reconstruir=Sí / **Reconstruir=Sí y Novedad vacía** / **Reconstruir Sí / condiciones ideales** / Coinciden remesas NO valor / Coincide valor NO remesas / NO coinciden remesas / NO coincide valor. Es **opcional**: por defecto "Todas (sin filtro)" y funciona con cualquier Excel normal; solo si se elige un filtro y faltan esas columnas, avisa y no genera (helpers `_cols_cruce`, `_pasa_filtro`, `_es_si`). El filtro **"Reconstruir=Sí y Novedad vacía"** además exige la columna `Novedad remesa` y opera a **nivel de factura** (no de fila): una factura solo se incluye si **todas** sus remesas tienen Reconstruir=Sí **y** novedad vacía — si aunque sea una remesa tiene novedad con datos, la factura completa se excluye (no se genera con las remesas restantes). Implementación en `_parsear()`: evalúa cada fila con `_pasa_filtro`, agrupa por N° Factura con `groupby(...).all()`, y descarta las facturas donde alguna fila no pase (`_es_vacio`). La columna de novedad es un **campo de mapeo opcional** (`col_novedad`, "Novedad remesa (opcional)") que NO se usa para el XML, solo para este filtro; `_novedad_col_activa` usa la columna mapeada por el usuario si la eligió, o cae a auto-detección por nombre (`_col_novedad`). Conjunto `FILTROS_NOVEDAD` (incluye ambos filtros de novedad).

**Filtros por valor de columnas-condición** (`COND_COLS`, helper `_actualizar_cond_valores`): lista `[(clave, etiqueta, valor_default)]` con las columnas opcionales cuyo **valor exacto** se exige por factura. Columnas: `col_comp_gen` (default `SI`), `col_rem_creada` (`SI EXISTE`), `col_asoc_rem_man` (`SI`), `col_cumplido_rem` (`SI`), `col_rem_facturada` (`NO`). Por cada una, un combobox de valor (`_cond_valor_combos[clave]`) se puebla dinámicamente con los valores únicos de esa columna + "Todas" + "— No usar —", preseleccionando el default sugerido si existe. **Aplicación por filtro:** en **"Reconstruir=Sí y Novedad vacía"** solo aplica `col_comp_gen` (comportamiento previo); en **"Reconstruir Sí / condiciones ideales"** (`FILTRO_COND_IDEAL`) aplican **todas** las columnas-condición. Cada una filtra a **nivel de factura** (`groupby(...).all()` sobre `_cond_pasa`): la factura pasa solo si **todas** sus remesas tienen el valor elegido en esa columna; es opt-in (solo si la columna está mapeada y el valor ≠ "Todas"/"— No usar —"). El filtro "condiciones ideales" hereda la base de novedad (Reconstruir=Sí + novedad vacía) y le suma estas condiciones. Las 4 columnas nuevas son las mismas que exporta el módulo de cruce (Remesa creada RNDC, Comp. Asociación Rem-Man RNDC, Cumplido remesa RNDC, Remesa facturada). Auto-detección por hints (`"creada"`, `"asociaci"`, `"cumplido"`, `"facturada"`, etc.).

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
Cruza el Excel exportado por "Extraer Datos RG" con otro Excel externo (que sí tiene consecutivos de remesa reales y valores unitarios), agrupando ambos por **N° Factura**. Ambos archivos tienen **selector de hoja** independiente. Mapeo de columnas estilo `excel_loader.py` (combobox con auto-detección). **Selecciones manuales preservadas** (igual que `excel_loader`): cada combo marca su clave en `self._mapeo_manual` vía `<<ComboboxSelected>>`; `_aplicar_df` omite el auto-match de las claves manuales cuya columna siga existiendo. Al cargar un archivo nuevo se descartan solo las marcas de las claves de esa fuente (`rg`/`otro`). Por factura compara:
- `¿Coinciden remesas?` — **cantidad de líneas** del RG vs cantidad de **consecutivos NO vacíos** del otro Excel (solo cuenta, no identidad). Igualdad exacta → Sí; cualquier diferencia → No. En `_cruzar`, las filas del otro Excel cuyo **consecutivo venga vacío se descartan** (`mask_valid` con `_fmt_consec` ≠ ""): no cuentan como remesa, no suman valor, no aparecen en el reporte y no dejan espacios en blanco intercalados. La suma de valores y las columnas passthrough se recogen de esas **mismas filas válidas** (`g_val`) para mantener la alineación posicional. Esto corrige el caso de consecutivos reales salteados entre celdas vacías (ej. 14 consecutivos dispersos en 28 filas → cuenta 14, coincide con 14 líneas RG).
- `¿Coincide valor factura con RG?` — compara una **suma de unitarios** vs el **valor total de factura del RG** (tolerancia $1). **Fuente de la suma según el mapeo:** si se mapea la columna **`rg_col_val_un` ("Valor unitario remesa (RG)")**, se usa la **suma de los unitarios del propio RG** (consistencia interna del RG — que es lo que se ve en el reporte exportado; normalmente da Sí porque `extraer_datos_rg` reparte el subtotal entre las líneas). Si **no** se mapea, cae al comportamiento anterior: suma de los unitarios del **otro Excel**. La tabla de resultados muestra la columna **"Suma unitarios (comparada)"** (el valor efectivamente usado) y **"Base"** (`RG` u `Otro Excel`) para saber contra qué se comparó. Campos del resultado: `suma_valor_rg`, `suma_valor_otro`, `suma_comparada`, `base_comparacion`. Auto-detección de `rg_col_val_un` por hint `"valor_unitario"`, `"unitario"`, etc.
- `Reconstruir` — `Sí` solo si ambas anteriores son `Sí`.

Valores monetarios robustos vía `_to_num` (parser **autónomo**, no usa `_parse_valor`): quita `$`/espacios, distingue separador de miles vs decimal en formato colombiano (`1.585.960` / `611.111,00`) **y** anglosajón (`1,585,960` / `611,111.00`), y cae a `0.0` si no parsea. Esto corrige el bug donde un valor con **coma de miles** (ej. `1,585,960`) hacía que `_parse_valor` lanzara `ValueError` → el valor sumaba 0 → la factura daba "No coincide valor" aunque la suma fuera exacta. Consecutivos limpios vía `_fmt_consec` (NaN→vacío, quita el `.0` que pandas añade a enteros leídos como float).

**Filtro de exportación** (`FILTROS_EXPORT`, helper `_pasa_filtro`): Todas / Solo Reconstruir=Sí / Coinciden remesas NO valor / Coincide valor NO remesas / NO coinciden remesas / NO coincide valor / Reconstruir=No. Genera solo el subconjunto elegido (con todas las columnas del RG), evitando filtrar a mano en Excel.

Al exportar, parte del Excel de RG **completo** (todas sus columnas/filas originales, sin la columna `consecutivo_remesa` que se descarta por venir vacía) y le anexa las 3 columnas de validación más `Consecutivo Remesa (Otro Excel)` — este último se asigna **posicionalmente** (línea N del RG ↔ remesa N del otro Excel, en orden de aparición). Si el otro Excel tiene **menos** remesas que líneas el RG, las líneas sobrantes quedan vacías. Si tiene **más**, las remesas sobrantes del otro Excel se añaden como **filas extra** (columnas del RG vacías, con su consecutivo/comp.gen/novedad y las banderas de validación de su factura), reubicadas justo **después** de las líneas RG de su factura — antes se perdían. La reubicación usa columnas auxiliares `_fo` (orden de aparición de la factura en el RG) y `_pos` (posición de la remesa) con `sort_values(..., kind="stable")`, que se descartan antes de guardar. Las facturas presentes solo en el otro Excel (sin líneas RG) también emiten sus remesas como filas extra al final. (No es un cruce por valor, es por orden de aparición.)

**Columnas opcionales del otro Excel (passthrough)** — mecanismo genérico vía la lista `PASSTHROUGH_OTRO` `[(clave_mapeo, encabezado_export)]`. Columnas soportadas: `otro_col_comp_gen`→`"Comp. Generador Carga RNDC"`, `otro_col_novedad`→`"Novedad remesa"`, `otro_col_rem_creada`→`"Remesa creada RNDC"`, `otro_col_asoc_rem_man`→`"Comp. Asociación Rem-Man RNDC"`, `otro_col_cumplido_rem`→`"Cumplido remesa RNDC"`, `otro_col_rem_facturada`→`"Remesa facturada"`. Si se mapean en la UI, sus valores se recogen por factura en orden posicional en un dict-de-dicts único `_passthrough_por_factura[clave][nf] = [valores]`, y el Excel exportado incluye esas columnas alineadas a cada remesa del RG (incluidas las **filas extra** de remesas sobrantes). Si no se mapean, no aparecen. **Se copian tal cual, sin filtro** (son informativas; no afectan las banderas de validación). Auto-detección por hints (el `col_norm` reemplaza espacios por `_`): generador → `"generador"`; novedad → `"novedad"`; creada → `"creada"`; asociación rem-man → `"asociaci"`/`"rem_man"`; cumplido → `"cumplido"`; facturada → `"facturada"`. Se quitó el hint genérico `"rndc"` de comp. generador para que no colisione con las nuevas columnas que también dicen RNDC.

> Sobre `Reconstruir` y las nuevas columnas: `Reconstruir = coinciden_remesas AND coincide_valor`. Las columnas passthrough NO cambian esa lógica — si el otro Excel y las líneas RG tienen **igual cantidad** de remesas y los valores suman igual (con el `_to_num` robusto), Reconstruir=Sí; si la cantidad difiere, `coinciden_remesas`=No → Reconstruir=No aunque los valores coincidan.

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

### `ui/anular_cumplido_manifiesto.py` — AnularCumplidoManifiestoModule
Anula el cumplido de un **manifiesto** en el RNDC vía **proceso 29** (`tipo=1`), bajo el grupo de sidebar **"Manifiesto"**. Flujo simple (sin paso de consulta): escribir **N° de manifiesto** → elegir **Motivo de anulación** (`D`=Error Digitación, `O`=Otro) → **Observaciones** (opcional) → **Guardar** con confirmación. Campos enviados: `NUMNITEMPRESATRANSPORTE` (del perfil), `NUMMANIFIESTOCARGA`, `CODMOTIVOANULACIONCUMPLIDO`, y `OBSERVACIONES` (solo si se llena). Usa las **mismas credenciales de corrección** (`rndc_usuario_corregir`) y el endpoint `rndcws`, igual que anular cumplido remesa. Botón **"🗑 Limpiar"**.

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
**Orquestador** bajo "Remesas" (título e ítem del sidebar: "Auto cambio-generador"): ejecuta toda la cadena de una vez. Entrada: **uno o varios consecutivos** (campo `Text` multilínea `_txt_consec`, separados por coma, espacio, punto y coma o salto de línea — pegable desde una columna; `_consecutivos_lista` parsea, aplica prefijo de perfil y elimina duplicados) + nuevo NIT generador (combobox `8000213085`/`9007867123` o manual) + código sede (default `1`) + Tipo ID (default `N`) + motivos por defecto (anulación `O`, cambio `3`). Botón **Ejecutar proceso** con confirmación y **log paso a paso**. **Procesamiento en lote**: `_ejecutar` parsea la lista, confirma una vez, y recorre cada remesa llamando a `_procesar_remesa(consec, ...)` (el cuerpo de los 5 pasos, que devuelve `'ok'`|`'ok_sin_cumplido'`|`'error'` en vez de abortar todo); al final muestra un **resumen** (completas / generador cambiado sin cumplido / con error + lista de fallidas). Una remesa con error **no detiene** las demás. Secuencia por remesa:
1. Consultar cumplido (proceso 5) → captura tiempos reales **antes de anular**.
2. Consultar remesa (proceso 3) → captura `BASE_FIELDS` para corregir (aborta si falla).
3. Anular cumplido (proceso 28) **solo si estaba cumplida** (motivo `O`).
4. Corregir generador (proceso 38, `CODIGOCAMBIO=4`): base + `numIdPropietario`=NIT nuevo + sede + motivo.
5. Re-cumplir (proceso 5).

**Árbol de re-cumplido** (`_plan_cumplido`): si el proceso 5 trae tiempos reales → Normal (cargue+descargue) o Suspensión (solo cargue); si no, calcula de citas (proceso 3) → Normal si hay cita cargue+descargue, Suspensión si solo cargue.

**Cumplido condicional (no aborta):** el objetivo principal es **corregir el generador**, así que el corregir SIEMPRE se intenta. El cumplido (paso 5) se **omite con gracia** cuando no es posible: si la remesa está **Pendiente de asignar manifiesto** (`nummanifiestocarga` vacío en proceso 3 → `sin_manifiesto`), o si no hay tiempos ni citas (`_plan_cumplido` devuelve None). En esos casos corrige y termina informando que el cumplido quedó omitido.

**Anulación con fallback al manifiesto (paso 3):** si la anulación del cumplido de la remesa (proceso 28) falla —caso típico: el **manifiesto asociado está cumplido**— y la remesa tiene `nummanifiestocarga`, se **anula primero el cumplido del manifiesto** (`anular_cumplido_manifiesto`, proceso 29, mismo `cod_anul`) y se **reintenta** la anulación de la remesa. Si el reintento o la anulación del manifiesto fallan, se aborta. Si la remesa no tiene manifiesto asociado, se aborta directamente. El resto del proceso (corregir + re-cumplir) sigue igual.

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
- `rndc_usuario`, `rndc_password` — credenciales RNDC (consulta/envío normal)
- `rndc_usuario_corregir`, `rndc_password_corregir` — credenciales para corregir/anular/cumplir (proceso 38/28/29/5/6); helper `_perfil_corregir`
- `rndc_usuario_monitoreo`, `rndc_password_monitoreo`, `nit_monitoreo` — credenciales y NIT de la **empresa de monitoreo de flota (EMF)** para consultar tiempos logísticos (proceso 60); helper `_perfil_monitoreo`. `nit_monitoreo` va como `NUMIDGPS`
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
| `consultar_manifiesto_completo(num_manifiesto, perfil, procesoid=4)` | `services/rndc_service.py` | `tipo=3` / `variables=*` / **proceso 4 = consultar manifiesto**. Filtro `NUMMANIFIESTOCARGA`. Retorna `(ok, dict)` con TODAS las variables del manifiesto (dinámico). Usado por el módulo web "Consultar manifiesto". (El **proceso 6** es CUMPLIR manifiesto, reservado para el futuro módulo de cumplir manifiesto.) |
| `consultar_factura(num_factura, perfil, timeout=20)` | `services/rndc_service.py` | **Proceso 86** / `tipo=3` / `variables=*` — **consulta una factura ya cargada por su número** (`NUMEROFACTURA`), sin subir XML. Filtro `NUMNITEMPRESATRANSPORTE=nit_socio`. Usa credenciales **normales** (`rndc_usuario`/`rndc_password`). Retorna `(ok, dict)` con TODOS los campos del `<documento>` (estado, cufe, subtotal, valorfletes, nitadquirente, remesas, etc.). Fallback por regex si el XML viene mal formado |
| `consultar_factura_por_remesa(consecutivo_remesa, num_id_generador, perfil, timeout=20)` | `services/rndc_service.py` | **Proceso 34** (Tarifas Generador) / `tipo=3` / `variables=*`. Devuelve la tarifa del generador de una remesa, que incluye la **factura electrónica** asociada (`facturaelectronica`). Filtro `NUMIDEMPRESA=nit_socio` + `NUMIDGENERADOR` (NIT del generador) + `CONSECUTIVOREMESA`. Credenciales **normales**. Si la remesa tiene **varios registros** (re-tarifada: uno viejo sin factura, otro reciente con factura), devuelve el **más reciente por `INGRESOID`** (helper `_doc_mas_reciente`, vía `_post_consulta_multi`). Retorna `(ok, dict)` |
| `consultar_remesas_por_factura(num_factura, num_id_generador, perfil, timeout=20)` | `services/rndc_service.py` | **Proceso 34** / `tipo=3` / `variables=*`. Devuelve **TODAS las remesas de una factura** filtrando por `FACTURAELECTRONICA` (+ `NUMIDEMPRESA`/`NUMIDGENERADOR`). Retorna `(ok, list[dict])` — una remesa por elemento (cantidad = nº de documentos). Vía `_post_consulta_multi` |
| `consultar_facturas_por_fecha(perfil, fecha_inicial, fecha_final, timeout=20, max_dias=93)` | `services/rndc_service.py` | **Proceso 86** / `tipo=3`. Lista todas las facturas cuya `FECHAFACTURA` cae en el rango. El WS no soporta rango → consulta **día por día** (`FECHAFACTURA` exacta `YYYY-MM-DD`) y agrega. Acepta `date` o str; invierte fechas al revés; tope `max_dias`. Retorna `(ok, list[dict])` |
| `consultar_manifiesto_por_radicado(radicado, perfil, timeout=20)` | `services/rndc_service.py` | **Proceso 4** / `tipo=3` / `variables=*`. Consulta un manifiesto por su **radicado** (`INGRESOID`) en vez del número. Usado por el monitoreo por placa (los docs del proceso 60 solo traen `ingresoidmanifiesto`). Retorna `(ok, dict)` con todos los campos, incl. `nummanifiestocarga` |
| `consultar_monitoreo_manifiesto(perfil, radicado_manifiesto="", placa="", fecha_inicial="", fecha_final="", timeout=20, max_dias=93)` | `services/rndc_service.py` | **Proceso 60** / `tipo=3` / `variables=*` — **tiempos logísticos (monitoreo)**. Filtra por `INGRESOIDMANIFIESTO` (radicado) y/o `NUMPLACA`; hay que pasar al menos uno. **Rango de fecha opcional** (`fecha_inicial`/`fecha_final`): día por día vía `FECHACREA` exacta (el WS no soporta rango; tope `max_dias`; días vacíos dan `RNDC11` y se ignoran). Usa credenciales de monitoreo (`rndc_usuario_monitoreo`, fallback normales), `NUMIDGPS=nit_monitoreo`, `NUMNITEMPRESATRANSPORTE=nit_socio`. Retorna `(ok, list[dict])` con **un documento por punto de control** |
| `consultar_remesas_por_manifiesto(num_manifiesto, perfil, timeout=20)` | `services/rndc_service.py` | Proceso 3 / `tipo=3` / `variables=*`, filtra por `NUMMANIFIESTOCARGA`. Lee las remesas del manifiesto (citas pactadas cargue/descargue). Retorna `(ok, list[dict])` |
| `corregir_remesa(variables, perfil)` | `services/rndc_service.py` | Proceso 38 / `tipo=1`. Envía a `rndcws.mintransporte.gov.co:8080` (sin "2"). `variables` es dict (orden respetado). Retorna `(ok, {ingresoid})` |
| `anular_cumplido_remesa(consecutivo, cod_motivo, perfil)` | `services/rndc_service.py` | Proceso 28 / `tipo=1`. Anula cumplido. `cod_motivo`: `D`=Error Digitación, `O`=Otro. Mismo endpoint que corregir |
| `anular_cumplido_manifiesto(num_manifiesto, cod_motivo, perfil, observaciones="")` | `services/rndc_service.py` | Proceso 29 / `tipo=1`. Anula cumplido de manifiesto. Variables: `NUMNITEMPRESATRANSPORTE`, `NUMMANIFIESTOCARGA`, `CODMOTIVOANULACIONCUMPLIDO`, `OBSERVACIONES` (opcional). Mismo endpoint/credenciales que corregir |
| `cumplir_remesa(variables, perfil)` | `services/rndc_service.py` | Proceso 5 / `tipo=1`. Registra cumplido; `variables` dict. Mismo endpoint/credenciales que corregir |
| `cumplir_manifiesto(variables, perfil)` | `services/rndc_service.py` | **Proceso 6** / `tipo=1`. Registra el cumplido de un manifiesto; `variables` dict (`NUMMANIFIESTOCARGA`, `TIPOCUMPLIDOMANIFIESTO`, `FECHAENTREGADOCUMENTOS`, …). Mismo endpoint/credenciales que corregir |
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
- **Scroll del mouse sobre `ttk.Combobox` (bug que cambia el valor)**: por defecto, al hacer scroll con la rueda encima de un `ttk.Combobox`, este **cambia su valor** (cicla por las opciones), lo que en paneles con scroll corrompe las selecciones de mapeo. Solución: el helper `_anti_wheel_combo(combo)` (en `excel_loader.py` y `cruzar_remesas.py`) intercepta `<MouseWheel>` (y `<Button-4/5>`), retorna `"break"` para que el combo NO cambie de valor, y en su lugar desplaza el `Canvas` ancestro (subiendo por `master` hasta encontrarlo) para que la página siga haciendo scroll normal. Aplicarlo a **todos** los comboboxes de un panel scrollable (mapeo, hoja, filtro, valores-condición, modal).
- **Instanciación con `__new__` en `app.py`**: los módulos embebidos como panel (ej. `RndcUploaderWindow`, `ExcelLoaderWindow`) se crean con `ClassName.__new__(ClassName)` para poder pasar un `container` a `_build()` sin abrir un `Toplevel`. Esto **bypass `__init__`**, así que cualquier atributo de instancia que se inicialice en `__init__` **no existirá** al llamar `_build`. Regla: inicializar todos los atributos de estado en `_build()` con guards `if not hasattr(self, "attr"):` en lugar de solo en `__init__`. De lo contrario, llamadas como `self._mi_dict.clear()` en métodos posteriores lanzan `AttributeError` que Tkinter traga silenciosamente, dejando la UI sin datos sin ningún mensaje de error visible.
- **NIT cliente / dígito de verificación en `AccountingCustomerParty`**: no todos los XML tienen la misma estructura. Los generados por `xml_generator.py` incluyen `<cac:PartyIdentification><cbc:ID schemeID="{dig}">{nit}</cbc:ID></cac:PartyIdentification>`; los XML reconstruidos/respuesta del RNDC (ej. `AttachedDocument`) **no la tienen** y el dato solo existe en `PartyTaxScheme`/`PartyLegalEntity` (`<cbc:CompanyID schemeID="{dig}">{nit}</cbc:CompanyID>`). `editar_xml.py` intenta `PartyIdentification` primero y cae a `PartyTaxScheme`/`PartyLegalEntity` si no la encuentra. Al guardar, el reemplazo de NIT/dígito/nombre se hace por substitución de texto **acotada a bloques** (nunca global en todo el XML), para no afectar NITs/nombres iguales en otras secciones (UT, socio, etc.). Se reemplaza en **dos** lugares: (1) el `AccountingCustomerParty` dentro del CDATA, y (2) el `<cac:ReceiverParty>` externo del AttachedDocument (acotado a lo que está **antes del primer `<![CDATA[`** para no tocar el ReceiverParty de la ApplicationResponse, que corresponde a la UT). Mantener ambos sincronizados es lo que evita el error DIAN **FAC025**.

- **NIT con dígito embebido**: en los Excel/PDF el NIT suele venir con el dígito de verificación pegado (ej. `8000213085`). Para separarlo: limpiar a solo dígitos y tomar el último como dígito (`nit = s[:-1]`, `digito = s[-1]`). Así lo hace `excel_loader.py` (y `webapp/lib_excel.py`) cuando se mapea la columna NIT. **Importante:** antes de extraer dígitos hay que limpiar el `.0` que pandas añade al leer enteros como float (`8000213085.0`) — si no, el `.0` deja un `0` pegado y el dígito sale `0` con el NIT corrido. Se aplica la misma limpieza float-entero que en consecutivos (`int(v)` si `v.is_integer()`, o recortar `.0` final) **antes** del `re.sub(r"\D","",...)`.

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

---

## 🤖 Automatización RPA de carga de facturas (PLANEADO — futuro)

Automatizar el flujo diario de **carga de facturas RG** que hoy se hace a mano con fe-tool web. **Corre 1×/día**; hay días **sin facturas** → si no hay, **no hace nada** (skip, sin desgaste).

**Flujo manual actual (lo que se automatiza):**
1. **facture.co** (`plataforma.facture.co`) → login → filtrar por **fecha = ayer** (día actual − 1) → descargar documentos en **PDF**.
2. La plataforma pide un correo y envía un **link de descarga**; abrir el correo → clic al link → baja un **zip con los PDFs (RG)**.
3. fe-tool → **Extraer datos RG** → adjuntar PDFs → check "usar Referencia como consecutivo" → procesar → `datos_rg.xlsx`.
4. fe-tool → **Generar facturas vía Excel** → cargar `datos_rg` (auto-mapeo) → **Generar XML (.zip)**.
5. fe-tool → **Cargar facturas a RNDC** → subir el zip → enviar (**proceso 86**).

**Datos confirmados (para el diseño):**
- facture.co **NO tiene CAPTCHA** (login ni descarga) → automatizable por navegador (Playwright).
- El **RNDC responde bien desde IP de EE.UU.** (fe-tool Streamlit está desplegado allá y funciona) → una nube/US-runner sirve.

### ✅ HALLAZGO CLAVE: facture.co SÍ tiene API REST (verificado 2026-08-29, en vivo sobre la cuenta UT)

Host: **`https://api.facture.co`**. Auth: header **`Authorization: Bearer <JWT>`**. El JWT vive en `localStorage['JWT']`, **dura 24 h** (claim `total_lifetime = 1440 min`, `iss=api.facture.co`) → la automatización **loguea 1×/corrida** y le sobra. Probado: llamando los endpoints yo mismo con solo el JWT (fuera del navegador de la app) **responden 200** — o sea es consumible por HTTP puro (requests/httpx), **sin Playwright ni correo para la consulta**.

**Endpoints mapeados (todos POST, body JSON):**
- **Listar facturas emitidas** (= pantalla "Descarga masiva"):
  `POST /PLColab.Documents/Documents/GetDocumentsDescargaMasiva?pageIndex=1&pageSize=10&includeCreditNoteStatus=true`
  Body: `{issueDateBegin, issueDateEnd, documentTypeCodes:["FACTURA-UBL"], branches:[], processes:[], source:"Outbound", isSoporteAdquisicion:false}`. **Fechas en formato `MM/DD/YYYY`**. `source:"Outbound"`=Emitidos. Respuesta paginada `{items[], totalItemCount, pageNumber, pageSize, totalPages}`. Cada item: `number, DocumentOnlyPrefix, documentType, statusDian, status, issueDate, receiver{name,identification=NIT,identificationType}, amount, LDF, documentId(GUID), processCode, branchCode, UUID_CUFE, ...`. **Con esto se resuelve el "skip si no hay facturas": si `totalItemCount==0` no hace nada.**
- **Listar (pantalla "Consulta documentos")**: `POST /PLColab.Documents/Documents/GetDocumentsWeb` (body similar + `documentSubType`, `tituloValorCheck`). Ojo UI: en ese form la **fecha final debe ser POSTERIOR a la inicial** (rango 25→26 para traer el día 25; igual-igual lo marca inválido).
- **Datos estructurados de UNA factura (UBL en JSON)**: `POST /PLColab.Documents/Document/Content3` body `{documentLdf}` → `{DocumentCurrencyCode, UUID, UblVersion, CustomizationID, AccountingSupplierParty, AccountingCustomerParty, InvoiceLines, ...}`. **⭐ Esto entrega NIT, cliente, líneas y valores directamente → la automatización podría saltarse el parseo de PDF (`lib_extraer`) por completo y armar el `datos_rg` desde JSON.**
- **Metadatos ricos de una factura**: `POST /PLColab.Documents/Document/GetDocumentAsync` body `{documentLdf}` → `{numero_cd, LDF, UUID, receiver, issuer, amount, taxTotal, retentionTotal, status, URI, UBL, viewer, relatedDocuments, ...}`.
- **Adjuntos**: `POST /PLColab.Documents/Document/Attachments/ListUrlV2` body `{documentLdf}` (0 items para facturas normales).

**`documentLdf` (identificador de documento)** = string `"FACTURA-UBL(<NIT_emisor>;<numero>;<fecha YYYY-MM-DD>;<sucursal>;<proceso>)"`, p.ej. `FACTURA-UBL(901101271;412049;2026-08-26;PRINCIPAL;PRINCIPAL)`. La URL del visor web es ese LDF en **base64** (`/documents/viewer/<b64(LDF)>/1`).

**Descarga de PDF/XML**: `GetDocumentAsync` devuelve `URI` (PDF) y `UBL` (XML) — endpoints con forma `/PLColab.Documents/Document/<ldf-encoded>/<code>/Binario`. Desde el app cargan bien (el botón ⬇ del visor descarga un blob ya traído). Llamados en standalone con solo `Authorization` dan **500** → les falta replicar algún header extra del interceptor Angular (probable tenant/`x-` header). **Pendiente de afinar al construir** (o usar la ruta de correo como respaldo). Para el objetivo real (obtener datos → generar XML → RNDC), **Content3 en JSON hace innecesario el PDF**.

- **Descarga masiva por correo (respaldo)**: en "Descarga masiva", seleccionar + ⬇ abre modal (PDF/XML/Contenedor/Aceptación DIAN) que **pide un correo y envía un link** (zip). Es el flujo manual actual; se puede replicar + IMAP si se necesitara el PDF real.

**Login (verificado 2026-08-29, capturando el login real):** el flujo de autenticación **NO es un POST simple** — pasa por un gateway aparte (`urlMicrologin`/`apiManagmentUrl`, no `api.facture.co` directo) y usa una capa de **cifrado/seguridad** (`Auth/GetMasterKey`, `Auth/MigrateToNewSecurityModel`, `masterKey` en localStorage). Endpoints de auth en el bundle: `PLColab.Identity/Auth/{GetMasterKey, IsMainContract, Login, LoginAuth, LoginExpirate, MigrateToNewSecurityModel}`. El único POST en claro que se ve es `Auth/IsMainContract` (body `{u, p, ft}`) que solo valida; el JWT lo emite el gateway y la app lo deja en **`localStorage['JWT']`** (dura **24 h**, `iss=api.facture.co`).

→ **Decisión: NO reversar el login en Python (frágil, cifrado). Arquitectura HÍBRIDA:**
1. **Playwright headless SOLO para el login** (facture no tiene CAPTCHA): abrir `plataforma.facture.co/plataforma/login` → escribir usuario/clave (de Secrets) → submit → esperar `/home` → leer `localStorage['JWT']`.
2. **Todo lo demás en HTTP puro** (`requests`/`httpx`) con ese `Authorization: Bearer <JWT>`: `GetDocumentsDescargaMasiva` (fecha=ayer) → por factura `Content3` (consecutivo de `"02"`) → `consultar_radicado_remesa` → `generar_xml` → `enviar_factura_rndc` (proceso 86).

Como el token dura 24 h y el job corre 1×/día, es **un login por corrida**. Verificado end-to-end: el `localStorage['JWT']` recién emitido por el login funciona para llamar la API (probado con `GetDocumentsDescargaMasiva` y `Content3`).

### 🗂️ Separación de proyectos (DECISIÓN del usuario 2026-08-29)

**La automatización NO va dentro de fe-tool.** fe-tool sigue siendo **solo la webapp manual de Streamlit** (sin cron, sin pipeline, intacto). La tarea diaria vive en un **repo aparte**.

> **✅ CREADO (2026-08-29): `C:\Users\Lizarazo\Desktop\plcolab-rpa`.** Bot que importa fe-tool (mismos módulos que `webapp/app.py`) y hace login(Playwright, selectores reales `usernameField`/`passwordField`/`button[type=submit]`) → `GetDocumentsDescargaMasiva` → `Content3` (consec `"02"`) → `lib_excel.parsear` → `consultar_radicado_remesa` → `generar_xml` → `enviar_factura_rndc`. Archivos: `pipeline.py`, `facture_client.py`, `fetool_bridge.py`, `settings.py` (NO `config.py`, para no chocar con el paquete `config/` de fe-tool), `.github/workflows/diario.yml`, `docs/DESPLIEGUE.md`.
>
> **✅ PROBADO end-to-end (2026-08-29)** con las 3 facturas del 25/08 (411929/30/31, 35 remesas). Login OK, datos OK (NIT+dígito, CUFE 96, radicados resueltos), XML generado y **enviado al RNDC de verdad**. Resultado (esperado, ya estaban cargadas): el XML del bot es **estructuralmente válido** (llega a "Paso3" y el RNDC lo valida a nivel de negocio). Nota: `PLAYWRIGHT_HEADLESS=1` y forzar `sys.stdout.reconfigure(utf-8)` (la consola Windows cp1252 rompe con ✓/✗).
>
> **Códigos de respuesta RNDC proceso 86** (`AtenderMensajeRNDC`): el webservice **normalmente devuelve el mensaje completo** con descripción (`lib_rndc86._limpiar_msg` lo extrae, igual que fe-tool); **ocasionalmente responde escueto** solo con el código (sin `:` ni texto) — es transitorio del RNDC, no del cliente. NO hace falta diccionario de códigos en el bot (se quitó); se muestra el mensaje real tal cual.
> - **FAC038**: "El xml reportado tiene un numero de factura que ya está reportado previamente…: <nº>" → **duplicado** (ya cargada). Corta antes de validar remesas.
> - **FAC080**: "El xml reportado tiene una **remesa sin cumplir**: <radicado>" → esa remesa aún no está cumplida en el RNDC (estado de negocio, no error de XML).
> - **FAC081**: "El xml reportado **no tiene numero de factura de referencia en la remesa**." → error **por remesa** (real, confirmado en el portal RNDC: sale en cada remesa afectada). En la 411931 salió en 10 de 11 remesas + FAC080 en la restante.
> - Éxito real → `<ingresoid>` (radicado de la factura), que `lib_rndc86` formatea como "Radicado RNDC: <n>".
>
> **⚠️ Dos rarezas del RNDC (webservice proceso 86), verificadas:**
> 1. **Alterna respuesta escueta vs completa**: a veces devuelve solo "Error FAC080" (sin `:` ni descripción ni líneas), a veces el detalle completo con `;Linea:N` por remesa. Inconsistente, del lado del RNDC.
> 2. **Numeración de línea poco fiable**: el `;Linea:N` no siempre corresponde al orden real de la remesa (ej. FAC080 vino con `;Linea:1` pero su radicado `159602487` es la remesa #11). Por eso, para cruzar error→remesa hay que mapear **por radicado cuando el mensaje lo cita** (FAC080), y solo por línea cuando no (FAC081).
>
> **✅ NUEVO en la webapp (2026-08-29) — "Cargar facturas a RNDC" ahora muestra DETALLE POR REMESA** (como el portal RNDC), para que no sea confuso ver un solo error por factura cuando el rechazo es por remesa:
> - `webapp/lib_rndc86.enviar_factura_rndc(..., detallado=True)` → 3-tupla `(exito, mensaje, detalle)`; `parse_detalle_errores(resp_text)` extrae `[{codigo, mensaje, linea, radicado}]` de la respuesta cruda.
> - `webapp/app.py::modulo_cargar_rndc`: además de la tabla por factura (Estado+Mensaje), arma **"Detalle por remesa"** cruzando cada remesa (consec/radicado/valor de `parse_factura_xml`) con su mensaje (por radicado, si no por línea). Los errores de **nivel factura** (ej. FAC038 duplicado, que no mapean a una remesa) se muestran en TODAS las filas de remesa de esa factura (para que no queden en blanco).
> - **Enriquecimiento de código escueto** (`lib_rndc86.FAC_DESCRIPCIONES` + `_enriquecer_codigos`): cuando el RNDC devuelve solo "Error FACxxx" sin descripción, se le anexa la descripción conocida; si el RNDC YA manda su texto (con `:`), se respeta el suyo (no se pisa). Resuelve el caso "el mensaje salía vacío/solo el código" para FAC038.
> - El parámetro `detallado` es opcional (default False) → otros llamadores no se afectan. (El bot `plcolab-rpa` también hereda el enriquecimiento vía `lib_rndc86`.)
>
> ⚠️ El bot usa el MISMO `generar_xml` que la webapp manual (que sube facturas válidas y devuelve ingresoid) → el template es correcto; FAC080/FAC081 en 411931 vienen del estado de esa factura (remesa sin cumplir), no del bot. **Pendiente clave: corrida de ÉXITO real** sobre una factura con TODAS las remesas cumplidas y no duplicada → si da ingresoid, bot 100% validado; si diera FAC081, habría un campo real por ajustar. (Submodule fe-tool también pendiente.)

Layout del repo del bot:

```
facture-rndc-bot/                 ← REPO NUEVO (automatización)
├── .github/workflows/diario.yml  ← el "cron" (corre en la nube de GitHub, 1×/día; NO en el server de fe-tool ni en el PC)
├── pipeline.py                   ← login(Playwright) → listar → Content3 → radicado → generar_xml → RNDC 86
├── fe-tool/                       ← fe-tool como GIT SUBMODULE (se importa, no se copia)
├── requirements.txt              ← playwright, requests, + deps de fe-tool
└── estado.json                   ← idempotencia
```

**Reutilización (decisión: "el bot importa fe-tool", una sola fuente de verdad):** el bot trae fe-tool como **git submodule** y lo importa vía `sys.path` — **cero cambios en fe-tool** (no hay que empaquetarlo):
```python
import sys; sys.path.insert(0, "fe-tool")
from core.xml_generator import generar_xml
from services.rndc_service import consultar_radicado_remesa
from webapp.lib_rndc86 import enviar_factura_rndc
```
Si se mejora `generar_xml` en fe-tool, el bot lo hereda actualizando el submodule. **Credenciales** (facture + RNDC) en los **Secrets del repo del bot**, inyectadas en runtime (mismo patrón que `bootstrap_perfiles.py`); nunca en fe-tool, nunca commiteadas.

**Arquitectura (gratis + nube):** — **como SÍ hay API, el camino feliz es HTTP puro (sin navegador ni correo).**
- **Opción A (recomendada):** **GitHub Actions** programado (cron 1×/día) en el repo del bot que corre `pipeline.py`: **login con Playwright** (leer `localStorage['JWT']`) → luego **HTTP puro** (`requests`): `GetDocumentsDescargaMasiva` (fecha=ayer) → si hay items, por cada factura `Content3` (datos UBL, consecutivo de `"02"`) → `consultar_radicado_remesa` → `generar_xml` → `enviar_factura_rndc` (proceso 86). Credenciales en **GitHub Secrets**. Gratis (2000 min/mes; job diario de minutos). Playwright solo para el login; **sin IMAP ni parseo de PDF**.
- **Opción B:** **Oracle Cloud Free VM** + **n8n** self-hosted orquestando un script Playwright + Execute Command (pipeline Python). Nota: n8n **no** hace scraping solo — igual llama a Playwright; n8n solo orquesta + notifica + reintenta.
- Alternativa sin nube: el **PC del usuario** con Task Scheduler (gratis, evita temas de IP).

**El pipeline de fe-tool YA es headless (funciones puras, sin UI — la automatización las encadena):**
- `webapp/lib_extraer.procesar_pdfs(pdfs, usar_ref)` → filas `datos_rg` (ya con **NIT+DV**, consecutivo Elogia con `0`, columna **`perfil`** tsp/elogia; multipágina).
- `webapp/lib_excel.auto_mapear(df)` + `webapp/lib_excel.parsear(df, mapping, filtro, ...)` → agrupa en facturas con remesas (incluye `perfil` por factura).
- `services.rndc_service.consultar_radicado_remesa(consec, perfil)` → radicado por consecutivo.
- `core.xml_generator.generar_xml(datos, perfil)` → XML por factura (perfil = `PERFILES['ut_tsp'|'ut_elogia']` según la columna `perfil`; TSP `300`/`120`, Elogia `101`).
- `webapp.lib_rndc86.enviar_factura_rndc(xml_bytes, usuario, password, nit_empresa)` → carga proceso 86.

**Reglas de negocio ya resueltas en fe-tool (dejan la automatización trivial):** DV auto del NIT (módulo 11), prefijo `0` de Elogia, detección/split de perfil por consecutivo (columna `perfil`), extracción **multipágina**, radicado auto por consecutivo, **zip** en Cargar facturas (`_cr_expandir`), y máx. facturas configurable (⚙️ Ajustes).

**Pendientes al construir la automatización:**
1. ~~Confirmar API de facture.co~~ ✅ **HECHO** (ver hallazgo arriba: API REST confirmada, consulta+datos por HTTP puro).
2. ~~Capturar el endpoint de login~~ ✅ **RESUELTO**: login cifrado vía gateway → **no se reversa**; se hace con **Playwright** (login → leer `localStorage['JWT']`, 24 h) y el resto en HTTP puro. Ver "Login" arriba.
3. ✅ **Confirmado: `Content3` trae TODO lo que hoy saca el PDF** → la automatización arma el `datos_rg` **directo del JSON, sin descargar ni parsear PDF** (`lib_extraer` deja de ser necesario en el camino API). **Verificado sobre factura 411930 (12 remesas): las 12 líneas traen consecutivo, y Σ de valores de línea = `amount` exacto (28.789.948).** Mapeo columna RG → ruta en `Content3`/listado:
   - `numero_factura` → **listado** `number` (+`DocumentOnlyPrefix`, `DocumentOnlyNumber`). *No está en Content3.*
   - `fecha_generacion` → **listado** `issueDate`. *No está en Content3.*
   - `cufe` → `Content3.UUID` (96 chars).
   - `nit` → `Content3.AccountingCustomerParty.PartyIdentification_ID` (base **sin DV**, igual que el PDF → aplicar `_nit_con_dv`). `nombre_cliente` → `...Party_Name`.
   - `descripcion` → `Content3.InvoiceLines[i].Item.Description`.
   - `consecutivo_remesa` → **usar la propiedad `Name=="02"`** de `InvoiceLines[i].Item.AdditionalItemProperty[]`, **NO `CodigoItem`**. Motivo (verificado en 411930): `CodigoItem` a veces trae el **radicado** en vez del consecutivo (remesa placa WLT112: `CodigoItem=163661861` que es el radicado, cuando el consecutivo real es `30013623`). La propiedad `"02"` dio el consecutivo correcto en las 12/12 líneas (`30xxxxx`, sin anomalías). `ConsecutivoItem`=índice de línea; `ValorTotalItem`(=prop `"03"`)=valor.
   - `valor_unitario` → `InvoiceLines[i].PriceAmount` (o `ValorTotalItem`). `valor_total_factura` → **listado** `amount`. `cantidad_remesas_rg` → `InvoiceLines.length`.
   - `perfil` → derivado del consecutivo `"02"` (regla `_perfil_por_consecutivo`). Con `"02"` como fuente, los `163661861` (radicados) ya **no** contaminan el split de perfil.
   - `radicado` → **SIEMPRE se consulta** con `consultar_radicado_remesa(consecutivo, perfil)` a partir del consecutivo (`"02"`). NO usar la propiedad `"01"` de facture: por decisión del usuario, el radicado del origen a veces viene mal puesto (igual que el `CodigoItem`), así que la fuente confiable es la consulta al RNDC. (Contexto: en el XML de fe-tool `"01"`=radicado y `"02"`=consecutivo por diseño — ver `core/xml_generator.generar_invoice_line`: consecutivo en `StandardItemIdentification` schemeID 999 + prop `"02"`; radicado en `SellersItemIdentification` + prop `"01"`. Es el mismo estándar que el UBL de facture, por eso `"02"` es canónico para leer el consecutivo.)
   - **⚠️ OJO flujo manual actual (PDF)**: el PDF se genera del mismo UBL; es probable que la REFERENCIA del PDF muestre `CodigoItem` (el radicado `163661861`) en esa remesa → revisar si alguna factura ya cargada quedó con el radicado en lugar del consecutivo. La ruta API con `"02"` **corrige** ese error.
   - Emisor bajo `AccountingSupplierParty` (`Party_Identification` + `Party_IdentificationDigitVerification`), retenciones en `WithholdingTaxTotal`.
4. **Orquestador headless** `pipeline.py` (login → listar → Content3 → generar_xml → enviar proceso 86) para que GitHub Actions lo invoque en un paso.
5. **Idempotencia:** registrar qué facturas ya se subieron (no duplicar si corre dos veces / reintentos).
6. **Reporte diario** (cargadas / fallidas) por correo o notificación.
7. Lógica **"ayer"** (día − 1, formato `MM/DD/YYYY`) y **skip si `totalItemCount==0`**.
