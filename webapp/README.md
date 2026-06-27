# FE-Tool — Versión Web (Streamlit)

Versión web **aditiva** de FE-Tool. **No modifica** la app de escritorio: reutiliza la
lógica de negocio existente (`core/`, `services/`, `config/`) sin tocarla y solo
re-implementa la interfaz con Streamlit.

## Módulos (fase 1)

- **Generar facturas vía Excel** — sube Excel, mapeo manual de columnas, filtros de
  generación (incluidas condiciones ideales), genera XML y los descarga en un `.zip`.
- **Cargar facturas a RNDC** — sube XMLs y los envía al RNDC (proceso 86).
- **Consultar remesas** — consulta individual o masiva, con descarga a CSV.

> Próximas fases: editar/reconstruir XML, extraer datos RG, cruzar remesas,
> corregir/anular/cumplir remesa, auto cambio-generador, anular cumplido manifiesto.

## Requisitos

```bash
pip install -r requirements.txt   # incluye streamlit
```

## Ejecutar localmente

Desde la **raíz del proyecto** (la carpeta que contiene `webapp/`, `core/`, etc.):

```bash
streamlit run webapp/app.py
```

Se abre en el navegador (por defecto `http://localhost:8501`). Para acceso desde otras
PC de la red local:

```bash
streamlit run webapp/app.py --server.address 0.0.0.0 --server.port 8501
```

…y entran a `http://IP-DE-ESTA-PC:8501`.

## Desplegar en Streamlit Community Cloud

El repo **no** incluye `config/perfiles.py` (está gitignored, tiene credenciales). En
despliegue, la app lo **genera automáticamente desde los Secrets** de Streamlit
(`webapp/bootstrap_perfiles.py`), así que no subes credenciales al repo.

Pasos:
1. **Push** del proyecto a GitHub (sin `config/perfiles.py`). El repo puede ser público.
2. En [share.streamlit.io](https://share.streamlit.io): *New app* → elige el repo y rama,
   **Main file path** = `webapp/app.py`.
3. En **Advanced settings → Secrets**, pega (con tus credenciales reales):

   ```toml
   [perfiles.ut_tsp]
   rndc_usuario           = "FELTSP@0137"
   rndc_password          = "TU_PASSWORD_TSP"
   rndc_usuario_corregir  = "CG_TSP@137"
   rndc_password_corregir = "TU_PASSWORD_CORREGIR"

   [perfiles.ut_elogia]
   rndc_usuario  = "FACURAE@2120"
   rndc_password = "TU_PASSWORD_ELOGIA"
   ```

4. **Deploy**. Las dependencias se instalan desde `requirements.txt`.

> Si cambias las credenciales, edita los Secrets en Streamlit Cloud y reinicia la app.
> En local nada cambia: la app usa tu `config/perfiles.py` y no toca los Secrets.

## Notas

- La lógica (generación de XML, llamadas al RNDC, filtros, parseos) es **idéntica** a la
  del escritorio: se importa de `core/`, `services/` y de `webapp/lib_*.py` (copias
  fieles de la lógica embebida en `ui/`).
- No usa tkinter, así que corre en servidores sin entorno gráfico.
