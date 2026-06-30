"""
FE-Tool — versión WEB (Streamlit).

Reutiliza la lógica de negocio del proyecto de escritorio SIN modificarla
(core/, services/, config/). Solo re-implementa la capa visual.
Ejecutar:  streamlit run webapp/app.py   (desde la raíz del proyecto)
"""
import io
import os
import re
import sys
import zipfile
from datetime import datetime

# Hacer importables core/ services/ config/ (viven en la raíz del proyecto)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st

# En despliegue (sin config/perfiles.py en el repo) se genera desde st.secrets.
# DEBE ir antes de importar config/core/services.
from webapp.bootstrap_perfiles import asegurar_perfiles
try:
    asegurar_perfiles(_ROOT)
except Exception as _e_perf:
    st.error(f"⚠ Configuración de perfiles faltante.\n\n{_e_perf}")
    st.stop()

import pandas as pd

from config.perfiles import PERFILES
from core.xml_generator import generar_xml, _parse_valor
from services.rndc_service import (
    consultar_radicado_remesa, consultar_remesa_completa,
    anular_cumplido_remesa, anular_cumplido_manifiesto, corregir_remesa,
    cumplir_remesa, consultar_manifiesto_completo, cumplir_manifiesto,
)

from webapp import lib_excel
from webapp import lib_rndc86
from webapp import lib_remesas
from webapp import lib_editar
from webapp import lib_reconstruir
from webapp import lib_cruce
from webapp import lib_extraer

MOTIVOS_ANULACION = ["D — Error Digitación", "O — Otro"]

st.set_page_config(page_title="FE-Tool Web", page_icon="⚡", layout="wide")


# ── Perfil activo (en la barra lateral) ──────────────────────────────────────
def _selector_perfil():
    st.sidebar.markdown("### ⚡ FE-Tool **Web**")
    ids = list(PERFILES.keys())
    pid = st.sidebar.selectbox(
        "Perfil", ids, format_func=lambda k: PERFILES[k]["nombre"],
        key="perfil_id")
    p = PERFILES[pid]
    st.sidebar.caption(f"{p['nombre_socio']} · NIT {p['nit_socio']}")
    return p


def _estado_remesa_txt(cod, manifiesto=""):
    """Mismo criterio que ConsultarRemesasModule._estado_txt_color."""
    if cod == "AC" and not str(manifiesto).strip():
        return "📋 Pendiente de asignar manifiesto"
    if cod == "CE":
        return "✓ Cumplida"
    if cod == "AC":
        return "⏳ Pendiente por cumplir"
    return cod or "—"


def _style_estado(val):
    """Color de la celda Estado: verde=cumplida, rojo=no existe/no radicada,
    amarillo=pendiente (asignar manifiesto / por cumplir). Mismo criterio de color
    que el desktop (_estado_txt_color)."""
    s = str(val).lower().strip()
    if "cumplida" in s or s.startswith("✓"):
        return "background-color:#dcfce7; color:#166534; font-weight:600"   # verde
    if (s.startswith("✗") or "no existe" in s or "no radic" in s
            or "no encontr" in s or "no se encontr" in s):
        return "background-color:#fee2e2; color:#991b1b; font-weight:600"   # rojo
    if "pendiente" in s:
        return "background-color:#fef9c3; color:#854d0e; font-weight:600"   # amarillo
    return ""


def _perfil_corregir(perfil):
    """Sustituye credenciales por las de corrección (rndc_usuario_corregir) si existen.
    Igual que _perfil() de los módulos corregir/anular/cumplir del desktop."""
    p = dict(perfil)
    u, pw = p.get("rndc_usuario_corregir"), p.get("rndc_password_corregir")
    if u and pw:
        p["rndc_usuario"], p["rndc_password"] = u, pw
    return p


def _consec_efectivo(consec, perfil):
    """Aplica el prefijo '0' del perfil (ut_elogia) al consecutivo, igual que el desktop."""
    consec = str(consec).strip()
    if perfil.get("prefijo_remesa") and consec and not consec.startswith("0"):
        consec = "0" + consec
    return consec


def _placeholder(nombre):
    st.header(nombre)
    st.info("🚧 Este módulo aún no está portado a la versión web. Próximamente.")


def _limpiar_modulo(prefijos):
    """Borra de session_state todas las claves que empiecen por alguno de los
    prefijos (resetea ese módulo) y vuelve a renderizar. Equivale al botón Limpiar."""
    for k in list(st.session_state.keys()):
        if any(str(k).startswith(p) for p in prefijos):
            del st.session_state[k]
    st.rerun()


_REM_CAMPOS = ["Consecutivo", "Radicado", "Valor", "Peso", "Descripción"]


def _gm_nueva_remesa():
    """Crea una remesa nueva con los valores por defecto (Peso=1, Descripción).
    Cada remesa lleva un _id único para que sus widgets sean estables aunque se
    quiten/agreguen filas."""
    st.session_state["gm_rid"] = st.session_state.get("gm_rid", 0) + 1
    return {"_id": st.session_state["gm_rid"], "Consecutivo": "", "Radicado": "",
            "Valor": "", "Peso": "1", "Descripción": "Servicio de transporte"}


def _gm_init_remesas():
    if "gm_rid" not in st.session_state:
        st.session_state["gm_rid"] = 0
    if "gm_remesas" not in st.session_state:
        st.session_state["gm_remesas"] = [_gm_nueva_remesa()]


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: Generar XML (factura manual) — réplica de GeneradorApp._generar
# ─────────────────────────────────────────────────────────────────────────────
def modulo_generar_xml(perfil):
    st.header("⚡ Generar XML")
    st.caption("Crea una factura electrónica (UBL 2.1) manualmente y descarga el XML.")

    if st.button("🗑 Limpiar módulo", key="gm_clear"):
        _limpiar_modulo(["gm_"])

    st.subheader("📄 Datos de la Factura")
    c1, c2 = st.columns(2)
    nf        = c1.text_input("Número de factura", key="gm_nf")
    cufe      = c2.text_input("CUFE", key="gm_cufe")
    c3, c4 = st.columns(2)
    fecha     = c3.text_input("Fecha de generación (DD-MM-YYYY)",
                              value=datetime.today().strftime("%d-%m-%Y"), key="gm_fecha")
    val_total = c4.text_input("Valor total ($)", key="gm_total")

    st.subheader("🏢 Datos del Cliente")
    d1, d2, d3 = st.columns(3)
    nit_cli = d1.text_input("NIT cliente", "800021308", key="gm_nit")
    dig_cli = d2.text_input("Dígito verificación", "5", key="gm_dig")
    nom_cli = d3.text_input("Nombre cliente", "DRUMMOND LTD", key="gm_nom")

    st.subheader("📦 Remesas")
    _gm_init_remesas()
    remesas_st = st.session_state["gm_remesas"]

    if st.button("🔍 Consultar radicados/pesos faltantes en el RNDC", key="gm_consult"):
        with st.spinner("Consultando RNDC…"):
            for rem in remesas_st:
                consec = str(rem.get("Consecutivo", "")).strip()
                rad = str(rem.get("Radicado", "")).strip()
                if consec and rad.lower() in ("", "nan", "none", "0"):
                    ok, res = consultar_radicado_remesa(consec, perfil)
                    if ok:
                        rem["Radicado"] = res.get("radicado", "")
                        st.session_state[f"gm_f_{rem['_id']}_Radicado"] = rem["Radicado"]
                        if res.get("peso"):
                            rem["Peso"] = res.get("peso")
                            st.session_state[f"gm_f_{rem['_id']}_Peso"] = rem["Peso"]
        st.rerun()

    # Encabezados
    anchos = [0.5, 2.2, 2.2, 1.8, 1.2, 3.2, 0.7]
    hc = st.columns(anchos)
    for h, c in zip(["N°", "Consecutivo", "Radicado", "Valor ($)", "Peso KGM",
                     "Descripción línea", ""], hc):
        c.markdown(f"**{h}**")

    # Filas: cada remesa con su número, sus campos y su botón − (quitar esta).
    for idx, rem in enumerate(remesas_st, 1):
        rid = rem["_id"]
        cols = st.columns(anchos)
        cols[0].markdown(f"#### {idx}")
        for col_w, campo in zip(cols[1:6], _REM_CAMPOS):
            k = f"gm_f_{rid}_{campo}"
            if k not in st.session_state:        # sembrar con el valor actual/default
                st.session_state[k] = rem[campo]
            rem[campo] = col_w.text_input(campo, key=k, label_visibility="collapsed")
        if cols[6].button("−", key=f"gm_del_{rid}", help="Quitar esta remesa"):
            if len(remesas_st) > 1:
                for campo in _REM_CAMPOS:
                    st.session_state.pop(f"gm_f_{rid}_{campo}", None)
                st.session_state["gm_remesas"] = [r for r in remesas_st if r["_id"] != rid]
                st.rerun()

    if st.button("＋ Agregar remesa", key="gm_add"):
        st.session_state["gm_remesas"].append(_gm_nueva_remesa())
        st.rerun()

    if st.button("⚡ Generar XML", type="primary", key="gm_gen"):
        nf_, cufe_, fecha_, val_ = nf.strip(), cufe.strip(), fecha.strip(), val_total.strip()
        nit_, dig_, nom_ = nit_cli.strip(), (dig_cli.strip() or "5"), nom_cli.strip()
        if not all([nf_, cufe_, fecha_, val_, nit_, nom_]):
            st.warning("Completa: Número factura, CUFE, Fecha, Valor total, NIT y Nombre del cliente.")
            return
        # Fecha → ISO (mismos formatos que el desktop)
        fecha_iso = None
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                fecha_iso = datetime.strptime(fecha_, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue
        if fecha_iso is None:
            st.warning("Fecha inválida. Usa formato DD-MM-YYYY (ej: 13-06-2025).")
            return
        try:
            val_total_f = _parse_valor(val_)
        except ValueError:
            st.warning("El valor total debe ser numérico (611.111,00 · 611,111.00 · 611111).")
            return
        remesas = []
        for rem in st.session_state.get("gm_remesas", []):
            consec = str(rem.get("Consecutivo", "") or "").strip()
            radicado = str(rem.get("Radicado", "") or "").strip()
            valor = str(rem.get("Valor", "") or "").strip()
            peso = str(rem.get("Peso", "") or "").strip() or "1"
            desc = str(rem.get("Descripción", "") or "").strip() or "Servicio de transporte"
            if not (consec or radicado or valor):
                continue   # fila totalmente vacía → ignorar
            if not all([consec, radicado, valor]):
                st.warning("Cada remesa debe tener Consecutivo, Radicado y Valor.")
                return
            try:
                valor_f = _parse_valor(valor)
            except ValueError:
                st.warning(f"Valor de remesa inválido: {valor}")
                return
            remesas.append({"consecutivo": consec, "radicado": radicado, "peso": peso,
                            "valor": valor_f, "descripcion_linea": desc})
        if not remesas:
            st.warning("Agrega al menos una remesa con Consecutivo, Radicado y Valor.")
            return
        datos = {"numero_factura": nf_, "cufe": cufe_, "fecha": fecha_iso,
                 "nit_cliente": nit_, "digito_cliente": dig_, "nombre_cliente": nom_,
                 "valor_total": val_total_f, "remesas": remesas}
        try:
            xml = generar_xml(datos, perfil=perfil)
        except Exception as e:
            st.error(f"Error al generar el XML: {e}")
            return
        st.success(f"✓ XML generado [{perfil['nombre']}] · {len(remesas)} remesa(s).")
        st.download_button("⬇️ Descargar XML", xml.encode("utf-8"),
                           file_name=f"FACTURA_{nf_}.xml", mime="application/xml", key="gm_dl")


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 1: Generar facturas vía Excel
# ─────────────────────────────────────────────────────────────────────────────
def modulo_generar_excel(perfil):
    st.header("📊 Generar facturas vía Excel")
    st.caption("Sube el Excel, mapea las columnas a mano y genera los XML (descarga en .zip).")

    archivo = st.file_uploader("Archivo Excel", type=["xlsx", "xls", "xlsm"], key="gx_file")
    if archivo is not None:   # cachear bytes para que persista al cambiar de módulo
        st.session_state["gx_bytes"] = archivo.getvalue()
        st.session_state["gx_name"] = archivo.name

    if st.button("🗑 Limpiar módulo", key="gx_clear"):
        _limpiar_modulo(["gx_"])

    xls_bytes = st.session_state.get("gx_bytes")
    if not xls_bytes:
        st.info("Carga un archivo para comenzar.")
        return
    st.caption(f"📄 Archivo cargado: {st.session_state.get('gx_name','')}")

    xl = pd.ExcelFile(io.BytesIO(xls_bytes))
    hoja = st.selectbox("Hoja", xl.sheet_names, key="gx_hoja")
    df = xl.parse(hoja)
    st.caption(f"Hoja '{hoja}' · {len(df)} filas · {len(df.columns)} columnas")

    cols_opt = ["— No usar —"] + list(df.columns.astype(str))

    st.subheader("Mapeo de columnas")
    mapping = {}
    cols_grid = st.columns(2)
    for i, (clave, etq, req) in enumerate(lib_excel.CAMPOS):
        with cols_grid[i % 2]:
            sel = st.selectbox(("* " if req else "") + etq, cols_opt, key=f"gx_map_{clave}")
            mapping[clave] = None if sel == "— No usar —" else sel

    st.subheader("Datos del Cliente (si no se mapea NIT/Nombre)")
    c1, c2, c3 = st.columns(3)
    nit_cli = c1.text_input("NIT cliente", "800021308", key="gx_nit")
    dig_cli = c2.text_input("Dígito verificación", "5", key="gx_dig")
    nom_cli = c3.text_input("Nombre cliente", "DRUMMOND LTD", key="gx_nom")

    st.subheader("Filtro de generación")
    filtro = st.selectbox("Filtro", lib_excel.FILTROS_GEN, key="gx_filtro")

    cond_values = {}
    if filtro in lib_excel.FILTROS_NOVEDAD:
        st.caption("Valores requeridos por columna (a nivel de factura). Solo aplican si mapeas la columna.")
        cc = st.columns(2)
        for i, (clave, etq, default_val) in enumerate(lib_excel.COND_COLS):
            with cc[i % 2]:
                col = mapping.get(clave)
                if col:
                    vals = lib_excel.valores_unicos_columna(df, col)
                    opciones = ["— No usar —", "Todas"] + vals
                    idx = opciones.index(default_val) if default_val in opciones else 0
                    cond_values[clave] = st.selectbox(f"{etq} =", opciones, index=idx,
                                                      key=f"gx_cv_{clave}")
                else:
                    cond_values[clave] = "— No usar —"

    ok, msg = lib_excel.validar(df, mapping, filtro)
    if not ok:
        st.warning(msg)
        return

    col_a, col_b = st.columns([1, 1])
    if col_a.button("🔍 Vista previa / contar", key="gx_prev"):
        datos = lib_excel.parsear(df, mapping, filtro, cond_values, nit_cli, dig_cli, nom_cli)
        n_rem = sum(len(d["remesas"]) for d in datos)
        st.success(f"{len(datos)} factura(s) · {n_rem} remesas · Perfil: {perfil['nombre']}")
        if datos:
            st.dataframe(pd.DataFrame([{
                "N° Factura": d["numero_factura"], "CUFE": d["cufe"][:25] + "…" if len(d["cufe"]) > 25 else d["cufe"],
                "Fecha": d["fecha"], "Remesas": len(d["remesas"]),
                "Valor total": d["valor_total"]} for d in datos]),
                use_container_width=True, hide_index=True)

    if col_b.button("⚡ Generar XML (.zip)", key="gx_gen", type="primary"):
        datos = lib_excel.parsear(df, mapping, filtro, cond_values, nit_cli, dig_cli, nom_cli)
        if not datos:
            st.warning("No hay facturas que cumplan el filtro.")
            return
        prog = st.progress(0.0, text="Consultando radicados en el RNDC…")
        total = sum(len(d["remesas"]) for d in datos) or 1
        hecho = 0
        # Fase 1: radicados faltantes (igual que _generar_todos)
        for d in datos:
            for rem in d["remesas"]:
                consec = rem.get("consecutivo", "").strip()
                rad = rem.get("radicado", "").strip()
                if consec and rad.lower() in ("", "nan", "none", "0"):
                    okr, res = consultar_radicado_remesa(consec, perfil)
                    rem["radicado"] = res.get("radicado", "0") if okr else "0"
                elif not rad or rad.lower() in ("nan", "none"):
                    rem["radicado"] = "0"
                hecho += 1
                prog.progress(min(hecho / total, 1.0),
                              text=f"Consultando RNDC… {hecho}/{total}")
        # Fase 2: generar XML → zip
        buf = io.BytesIO()
        errores = []
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for d in datos:
                try:
                    xml = generar_xml(d, perfil=perfil)
                    zf.writestr(f"FACTURA_{d['numero_factura']}.xml", xml)
                except Exception as e:
                    errores.append(f"Factura {d.get('numero_factura','?')}: {e}")
        prog.empty()
        st.success(f"✓ {len(datos) - len(errores)} XML generados [{perfil['nombre']}].")
        if errores:
            st.error("Errores:\n" + "\n".join(errores))
        st.download_button("⬇️ Descargar XML (.zip)", buf.getvalue(),
                           file_name=f"facturas_{perfil['nombre'].replace(' ', '_')}.zip",
                           mime="application/zip", key="gx_dl")


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 2: Cargar facturas a RNDC
# ─────────────────────────────────────────────────────────────────────────────
def modulo_cargar_rndc(perfil):
    st.header("📤 Cargar facturas a RNDC")
    st.caption("Sube los XML de factura y envíalos al RNDC (proceso 86).")

    archivos = st.file_uploader("XML(s) de factura", type=["xml"],
                                accept_multiple_files=True, key="cr_files")
    if archivos:   # cachear contenido para que persista al cambiar de módulo
        st.session_state["cr_data"] = [(a.name, a.getvalue()) for a in archivos]

    if st.button("🗑 Limpiar módulo", key="cr_clear"):
        _limpiar_modulo(["cr_"])

    files_data = st.session_state.get("cr_data", [])
    if not files_data:
        st.info("Carga uno o varios XML.")
        return

    datos = [lib_rndc86.parse_factura_xml(nombre, b) for nombre, b in files_data]

    st.subheader("Facturas detectadas")
    st.dataframe(pd.DataFrame([{
        "Archivo": d["archivo"], "N° Factura": d["nf"], "Cliente": d["cliente"],
        "CUFE": d["cufe"], "Remesas": len(d["remesas"]),
        "Estado": ("⚠ " + d["error"]) if d["error"] else "⏳ Pendiente de envío"}
        for d in datos]), use_container_width=True, hide_index=True)

    filas_rem = []
    for d in datos:
        for r in d["remesas"]:
            filas_rem.append({"N° Factura": d["nf"], "Consecutivo": r["consecutivo"],
                              "Radicado": r["radicado"], "Valor ($)": r["valor"]})
    if filas_rem:
        st.subheader("Remesas / líneas")
        st.dataframe(pd.DataFrame(filas_rem), use_container_width=True, hide_index=True)

    st.markdown("---")
    if st.button("📤 Enviar al RNDC", type="primary", key="cr_send"):
        usuario = perfil.get("rndc_usuario", "")
        password = perfil.get("rndc_password", "")
        nit = perfil.get("nit_socio", "")
        prog = st.progress(0.0, text="Enviando…")
        resultados = []
        for i, ((nombre, b), d) in enumerate(zip(files_data, datos), 1):
            exito, mensaje = lib_rndc86.enviar_factura_rndc(b, usuario, password, nit)
            resultados.append({"Archivo": d["archivo"], "N° Factura": d["nf"],
                               "Resultado": ("✓ " if exito else "✗ ") + mensaje})
            prog.progress(i / len(files_data), text=f"{i}/{len(files_data)} {d['archivo']}")
        prog.empty()
        st.subheader("Resultado del envío")
        st.dataframe(pd.DataFrame(resultados), use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 3: Consultar remesas
# ─────────────────────────────────────────────────────────────────────────────
def modulo_consultar_remesas(perfil):
    st.header("🔍 Consultar remesas")
    st.caption("Consulta una o varias remesas en el RNDC (separadas por coma, espacio o salto de línea).")

    def _cq_limpiar():
        # Callback (corre antes de instanciar los widgets) → limpieza confiable
        st.session_state["cq_txt"] = ""
        st.session_state.pop("cq_filas", None)

    txt = st.text_area("Consecutivo(s) de remesa", height=120, key="cq_txt")
    cbtn1, cbtn2 = st.columns([1, 1])
    cbtn2.button("🗑 Limpiar módulo", key="cq_clear", on_click=_cq_limpiar)
    if cbtn1.button("🔍 Consultar", type="primary", key="cq_btn"):
        import re
        consecutivos = [t for t in re.split(r"[\s,;]+", txt.strip()) if t]
        if not consecutivos:
            st.warning("Escribe al menos un consecutivo.")
            return
        vistos, lista = set(), []
        for c in consecutivos:
            if c not in vistos:
                vistos.add(c); lista.append(c)
        prog = st.progress(0.0, text="Consultando…")
        filas = []
        for i, consec in enumerate(lista, 1):
            try:
                ok, res = consultar_radicado_remesa(consec, perfil)
            except Exception as e:
                ok, res = False, str(e)
            if ok:
                filas.append({
                    "Consecutivo": consec, "Radicado": res.get("radicado", ""),
                    "Peso (KG)": res.get("peso", ""), "N° Manifiesto": res.get("manifiesto", ""),
                    "Propietario": res.get("propietario", ""), "Origen": res.get("origen", ""),
                    "Destino": res.get("destino", ""),
                    "Estado": _estado_remesa_txt(res.get("estado", ""), res.get("manifiesto", "")),
                })
            else:
                filas.append({"Consecutivo": consec, "Radicado": "", "Peso (KG)": "",
                              "N° Manifiesto": "", "Propietario": "", "Origen": "",
                              "Destino": "", "Estado": f"✗ {res}"})
            prog.progress(i / len(lista), text=f"{i}/{len(lista)}")
        prog.empty()
        st.session_state["cq_filas"] = filas   # persistir resultados

    # Render de los resultados (persisten al cambiar de módulo)
    filas = st.session_state.get("cq_filas")
    if filas:
        df_res = pd.DataFrame(filas)
        # Colorear la columna Estado según el estado de la remesa (verde/rojo/amarillo)
        try:
            styler = df_res.style.map(_style_estado, subset=["Estado"])
        except AttributeError:   # pandas < 2.1 usa applymap
            styler = df_res.style.applymap(_style_estado, subset=["Estado"])
        st.dataframe(styler, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Descargar resultados (.csv)",
                           df_res.to_csv(index=False).encode("utf-8-sig"),
                           file_name="consulta_remesas.csv", mime="text/csv", key="cq_dl")


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: Anular cumplido remesa (proceso 28)
# ─────────────────────────────────────────────────────────────────────────────
_CTX_REMESA = [
    ("remempresa", "Empresa"), ("rem_orig", "Origen"), ("rem_desti", "Destino"),
    ("rempropietario", "Generador"), ("remdestinatario", "Destinatario"),
    ("descripcioncortaproducto", "Producto"), ("cantidadcargada", "Cantidad cargada"),
    ("estado", "Estado"), ("nummanifiestocarga", "N° Manifiesto"),
]


def modulo_anular_cumplido_remesa(perfil):
    st.header("🗑 Anular Cumplido Remesa")
    st.caption("Consulta la remesa, elige el motivo y anula su cumplido en el RNDC (proceso 28).")

    consec_in = st.text_input("Consecutivo remesa", key="acr_in")
    bcol1, bcol2 = st.columns([1, 1])
    if bcol2.button("🗑 Limpiar módulo", key="acr_clear"):
        _limpiar_modulo(["acr_"])
    if bcol1.button("🔍 Consultar remesa", key="acr_consult"):
        p = _perfil_corregir(perfil)
        consec = _consec_efectivo(consec_in, p)
        with st.spinner(f"Consultando remesa {consec}…"):
            ok, res = consultar_remesa_completa(consec, p)
        if ok:
            st.session_state["acr_res"] = res
            st.session_state["acr_consec"] = consec
        else:
            st.session_state.pop("acr_res", None)
            st.error(f"✗ {res}")

    res = st.session_state.get("acr_res")
    if res:
        consec = st.session_state.get("acr_consec", "")
        st.success(f"Remesa {consec} cargada. Revisa los datos antes de anular.")
        st.dataframe(pd.DataFrame(
            [{"Campo": etq, "Valor": res.get(k, "") or "—"} for k, etq in _CTX_REMESA]),
            use_container_width=True, hide_index=True)
        motivo = st.selectbox("Motivo de la anulación", MOTIVOS_ANULACION, key="acr_motivo")
        confirma = st.checkbox("Confirmo que quiero anular este cumplido (operación real)", key="acr_ok")
        if st.button("🗑 Guardar anulación cumplido", type="primary", disabled=not confirma, key="acr_send"):
            p = _perfil_corregir(perfil)
            cod = motivo.split(" ")[0]
            with st.spinner("Anulando…"):
                ok, r = anular_cumplido_remesa(consec, cod, p)
            if ok:
                st.success(f"✓ Cumplido anulado. Radicado: {r.get('ingresoid','?')}")
                st.session_state.pop("acr_res", None)
            else:
                st.error(f"✗ {r}")


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: Corregir remesa (proceso 38)
# ─────────────────────────────────────────────────────────────────────────────
def modulo_corregir_remesa(perfil):
    st.header("🛠 Corregir Remesa")
    st.caption("Consulta una remesa, elige qué corregir y envía la corrección al RNDC (proceso 38).")

    consec_in = st.text_input("Consecutivo remesa", key="cor_in")
    bcol1, bcol2 = st.columns([1, 1])
    if bcol2.button("🗑 Limpiar módulo", key="cor_clear"):
        _limpiar_modulo(["cor_"])
    if bcol1.button("🔍 Consultar remesa", key="cor_consult"):
        p = _perfil_corregir(perfil)
        consec = _consec_efectivo(consec_in, p)
        with st.spinner(f"Consultando remesa {consec}…"):
            ok, res = consultar_remesa_completa(consec, p)
        if ok:
            st.session_state["cor_res"] = res
            st.session_state["cor_consec"] = consec
            # Prellenar el conjunto base desde la consulta (igual que el desktop)
            st.session_state["cor_base"] = {
                envio: res.get(consulta, "") for envio, consulta in lib_remesas.CORREGIR_BASE_FIELDS}
        else:
            st.session_state.pop("cor_res", None)
            st.error(f"✗ {res}")

    res = st.session_state.get("cor_res")
    if not res:
        return
    consec = st.session_state.get("cor_consec", "")
    base = st.session_state.get("cor_base", {})
    st.success(f"Remesa {consec} cargada (radicado {res.get('ingresoid','?')}). Elige la opción a corregir.")

    st.subheader("Datos actuales de la remesa")
    st.dataframe(pd.DataFrame(
        [{"Campo": etq, "Valor": res.get(k, "") or "—"} for k, etq in lib_remesas.CORREGIR_CONTEXTO]),
        use_container_width=True, hide_index=True)

    st.subheader("Opciones para corregir")
    opcion = st.selectbox("Opción a Corregir", lib_remesas.CORREGIR_OPCIONES, key="cor_opcion")
    motivo = st.selectbox("Motivo del Cambio", lib_remesas.CORREGIR_MOTIVOS, key="cor_motivo")
    codigo = opcion.split(" ")[0]

    # Campos dinámicos de la opción elegida, prellenados con el valor base actual.
    campos = lib_remesas.CORREGIR_OPCION_CAMPOS.get(codigo, [])
    editados = {}
    cols = st.columns(2)
    for i, (envio, etiqueta) in enumerate(campos):
        with cols[i % 2]:
            actual = str(base.get(envio, "") or "")
            if envio in lib_remesas.CORREGIR_CAMPOS_TIPOID:
                ops = [f"{c} - {n}" for c, n in lib_remesas.CORREGIR_TIPOID_OPCIONES]
                lbl_actual = lib_remesas.tipoid_label(actual.strip())
                idx = ops.index(lbl_actual) if lbl_actual in ops else 0
                sel = st.selectbox(etiqueta, ops, index=idx, key=f"cor_f_{codigo}_{envio}")
                editados[envio] = lib_remesas.tipoid_code(sel)
            else:
                editados[envio] = st.text_input(etiqueta, value=actual, key=f"cor_f_{codigo}_{envio}")

    confirma = st.checkbox("Confirmo la corrección (modifica datos reales en el RNDC)", key="cor_ok")
    if st.button("💾 Guardar remesa corregida", type="primary", disabled=not confirma, key="cor_send"):
        faltantes = [etq for env, etq in campos if not str(editados.get(env, "")).strip()]
        if faltantes:
            st.warning("Completa los campos de la opción:\n• " + "\n• ".join(faltantes))
            return
        p = _perfil_corregir(perfil)
        variables = {
            "NUMNITEMPRESATRANSPORTE": p.get("nit_socio", ""),
            "consecutivoRemesa":       consec,
        }
        for envio, _consulta in lib_remesas.CORREGIR_BASE_FIELDS:
            variables[envio] = str(base.get(envio, "") or "").strip()
        for envio, valor in editados.items():     # sobrescribir con lo editado
            variables[envio] = str(valor).strip()
        variables["MOTIVOCAMBIO"] = motivo.split(" ")[0]
        variables["CODIGOCAMBIO"] = codigo
        with st.spinner("Enviando corrección…"):
            ok, r = corregir_remesa(variables, p)
        if ok:
            st.success(f"✓ Corrección enviada. Radicado: {r.get('ingresoid','?')}")
        else:
            st.error(f"✗ {r}")


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: Consultar manifiesto (proceso 6, tipo=3, variables=*)
# ─────────────────────────────────────────────────────────────────────────────
# Campos de "Información General" a mostrar (etiqueta amigable → posibles nombres
# de variable del RNDC; se usa el primero que exista en la respuesta).
_MANIF_CAMPOS = [
    ("N° Radicado",      ["INGRESOID", "NUMRADICADO", "RADICADO", "NUMRADICADOMANIFIESTO"]),
    ("Fecha Expedición", ["FECHAEXPEDICIONMANIFIESTO", "FECHAEXPEDICION"]),
    ("Placa",            ["NUMPLACA", "PLACA"]),
    ("Semirremolque",    ["NUMPLACAREMOLQUE", "NUMPLACASEMIRREMOLQUE", "PLACASEMIRREMOLQUE", "SEMIRREMOLQUE"]),
    ("Conductor",        ["MANNOMBRECONDUCTOR", "NOMBRECONDUCTOR", "NOMBRE_CONDUCTOR", "NOMCONDUCTOR"]),
    ("Identificación",   ["NUMIDCONDUCTOR", "NUMIDENTIFICACIONCONDUCTOR", "IDENTIFICACIONCONDUCTOR"]),
    ("Origen",           ["MANORIGEN", "NOMMUNICIPIOORIGEN", "MUNICIPIOORIGEN", "NOMORIGEN", "CODMUNICIPIOORIGENMANIFIESTO", "ORIGEN"]),
    ("Destino",          ["MANDESTINO", "NOMMUNICIPIODESTINO", "MUNICIPIODESTINO", "NOMDESTINO", "CODMUNICIPIODESTINOMANIFIESTO", "DESTINO"]),
    ("Observaciones",    ["OBSERVACIONES"]),
]


def _manif_curado(man, res):
    """Extrae solo los campos de Información General (con nombres amigables) del
    dict completo del RNDC. Prueba cada nombre candidato y usa el primero presente."""
    upper = {str(k).upper(): v for k, v in res.items()}
    fila = {"N° Manifiesto": man}
    for label, cands in _MANIF_CAMPOS:
        val = ""
        for c in cands:
            if c in upper and str(upper[c]).strip():
                val = upper[c]
                break
        fila[label] = val
    return fila


def modulo_consultar_manifiesto(perfil):
    st.header("🔍 Consultar Manifiesto")

    def _cm_limpiar():
        st.session_state["cm_txt"] = ""
        st.session_state.pop("cm_result", None)
        st.session_state.pop("cm_full", None)

    st.text_area("N° Manifiesto(s) de carga (coma, espacio o salto de línea)",
                 height=120, key="cm_txt")
    b1, b2 = st.columns([1, 1])
    b2.button("🗑 Limpiar módulo", key="cm_clear", on_click=_cm_limpiar)
    if b1.button("🔍 Consultar", type="primary", key="cm_btn"):
        manifiestos = [t for t in re.split(r"[\s,;]+", st.session_state.get("cm_txt", "").strip()) if t]
        vistos, lista = set(), []
        for m in manifiestos:
            if m not in vistos:
                vistos.add(m)
                lista.append(m)
        if not lista:
            st.warning("Escribe al menos un N° de manifiesto.")
        else:
            prog = st.progress(0.0, text="Consultando…")
            curados, full = [], {}
            for i, man in enumerate(lista, 1):
                try:
                    ok, res = consultar_manifiesto_completo(man, perfil)   # trae TODO (variables=*)
                except Exception as e:
                    ok, res = False, str(e)
                if ok:
                    fila = _manif_curado(man, res)
                    fila["Estado"] = "✓ Encontrado"
                    full[man] = res            # guardar el completo para vista avanzada
                else:
                    fila = {"N° Manifiesto": man}
                    for label, _ in _MANIF_CAMPOS:
                        fila[label] = ""
                    fila["Estado"] = f"✗ {res}"
                curados.append(fila)
                prog.progress(i / len(lista), text=f"{i}/{len(lista)}")
            prog.empty()
            st.session_state["cm_result"] = curados
            st.session_state["cm_full"] = full

    curados = st.session_state.get("cm_result")
    if curados:
        encontrados = [r for r in curados if r.get("Estado", "").startswith("✓")]
        st.success(f"{len(curados)} manifiesto(s) consultado(s) · {len(encontrados)} encontrado(s).")

        # Ficha de información general del último encontrado (si hay uno solo)
        if len(encontrados) == 1:
            f = encontrados[0]
            st.subheader("📋 Información general del manifiesto")
            kv = [{"Campo": k, "Valor": v} for k, v in f.items() if k != "Estado"]
            st.dataframe(pd.DataFrame(kv), use_container_width=True, hide_index=True)

        # Tabla de lo consultado (una fila por manifiesto, columnas = Info General)
        st.subheader("📑 Manifiestos consultados")
        cols = ["N° Manifiesto"] + [lbl for lbl, _ in _MANIF_CAMPOS] + ["Estado"]
        df = pd.DataFrame(curados, columns=cols)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Descargar resultados (.csv)",
                           df.to_csv(index=False).encode("utf-8-sig"),
                           file_name="consulta_manifiestos.csv", mime="text/csv", key="cm_dl")

        # Vista avanzada (colapsada) con TODAS las variables crudas, por si se requiere
        full = st.session_state.get("cm_full") or {}
        if full:
            with st.expander("🔧 Ver todas las variables crudas del RNDC (avanzado)"):
                for man, res in full.items():
                    st.markdown(f"**Manifiesto {man}**")
                    st.dataframe(pd.DataFrame([{"Variable": k, "Valor": v} for k, v in res.items()]),
                                 use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: Cumplir manifiesto (proceso 6, tipo=1)
# ─────────────────────────────────────────────────────────────────────────────
# Tipos de cumplido del manifiesto (código — etiqueta). ⚠ Confirmar valores reales
# del RNDC; se cambian fácilmente aquí.
TIPOS_CUMPLIDO_MANIFIESTO = [
    "C — Cumplido Normal",
    "S — Suspensión",
]

# Campos de metadata/solo-lectura del proceso 6 que NO se reenvían al cumplir
# (el resto se reenvía tal cual = valores pactados/finales del viaje, etc.).
_CMF_NO_ENVIAR = {
    "INGRESOID", "PROCESOID", "USUARIOINGR", "FECHACREA", "FECHAING", "FECHAMOD",
    "ESTADO", "CAUSAESTADO", "FINREAL", "ANOMES", "INTERACTIVO", "EMPRESA",
    "CODIGOEMPRESA", "USUARIORADICADOR", "INGRESOIDMANIFIESTO",
    "MANNUMERO_EMPRESALISTA", "MANNUMERO_EMPRESALISTA_CODE",
    # Descripciones legibles (se envían solo los códigos, no los nom*):
    "NOMTIPOCUMPLIDOMANIFIESTO", "NOMMOTIVOSUSPENSIONMANIFIESTO",
    "NOMCONSECUENCIASUSPENSION", "NOMMOTIVOVALORADICIONAL",
    "NOMMOTIVOVALORDESCUENTO", "NOMOPERACIONTRANSPORTE",
}


def modulo_cumplir_manifiesto(perfil):
    st.header("✅ Cumplir Manifiesto")

    def _cmf_limpiar():
        st.session_state["cmf_in"] = ""
        for k in ("cmf_full", "cmf_info", "cmf_man", "cmf_estado"):
            st.session_state.pop(k, None)

    st.text_input("N° Manifiesto de carga", key="cmf_in")
    b1, b2 = st.columns([1, 1])
    b2.button("🗑 Limpiar módulo", key="cmf_clear", on_click=_cmf_limpiar)

    # ── BOTÓN TEMPORAL: descubrir nombres reales de variables del cumplido (proceso 6)
    if st.button("🐞 (temporal) Ver variables del CUMPLIDO (proceso 6)", key="cmf_dbg"):
        man = st.session_state.get("cmf_in", "").strip()
        if not man:
            st.warning("Escribe el N° de manifiesto.")
        else:
            p = _perfil_corregir(perfil)
            with st.spinner(f"Consultando cumplido (proceso 6) de {man}…"):
                ok6, res6 = consultar_manifiesto_completo(man, p, procesoid=6)
            if ok6 and isinstance(res6, dict):
                st.success(f"Proceso 6 devolvió {len(res6)} variable(s) (manifiesto YA cumplido).")
                st.dataframe(pd.DataFrame([{"Variable": k, "Valor": v} for k, v in res6.items()]),
                             use_container_width=True, hide_index=True)
            else:
                st.info(f"Proceso 6 no devolvió datos: {res6}\n\n"
                        "(Si el manifiesto NO está cumplido, no hay cumplido que mostrar. "
                        "Usa un manifiesto YA cumplido para ver los nombres reales.)")

    if b1.button("🔍 Consultar manifiesto", key="cmf_consult"):
        man = st.session_state.get("cmf_in", "").strip()
        if not man:
            st.warning("Escribe el N° de manifiesto.")
        else:
            p = _perfil_corregir(perfil)
            with st.spinner(f"Consultando manifiesto {man}…"):
                # Proceso 4: datos generales del manifiesto. Proceso 6: formulario del
                # cumplido (valores pactados/finales, horas, fletes…). Se combinan: la
                # unión cubre TODOS los campos que el cumplido (proceso 6) necesita.
                ok4, res4 = consultar_manifiesto_completo(man, p, procesoid=4)
                ok6, res6 = consultar_manifiesto_completo(man, p, procesoid=6)
            if not ok4 and not ok6:
                for k in ("cmf_full", "cmf_info"):
                    st.session_state.pop(k, None)
                st.error(f"✗ No se pudo consultar el manifiesto: {res4 if not ok4 else res6}")
            else:
                combinado = {}
                if ok4 and isinstance(res4, dict):
                    combinado.update(res4)
                if ok6 and isinstance(res6, dict):
                    combinado.update(res6)   # el cumplido (6) tiene prioridad
                estado = ""
                for k, v in combinado.items():
                    if str(k).upper() == "ESTADO":
                        estado = str(v).strip().upper()
                        break
                st.session_state["cmf_man"] = man
                st.session_state["cmf_full"] = combinado      # todos los campos (4 + 6)
                st.session_state["cmf_info"] = _manif_curado(man, combinado)
                st.session_state["cmf_estado"] = estado

    info = st.session_state.get("cmf_info")
    if not info:
        return
    man = st.session_state.get("cmf_man", "")
    full = st.session_state.get("cmf_full", {})
    estado = st.session_state.get("cmf_estado", "")
    ya_cumplido = (estado == "CE")

    if ya_cumplido:
        st.warning(f"⚠ El manifiesto {man} ya está **CUMPLIDO** (estado CE).")
    elif estado == "AC":
        st.info(f"El manifiesto {man} está **pendiente por cumplir** (estado AC). Puedes cumplirlo.")
    else:
        st.info(f"Manifiesto {man} · estado: {estado or '—'}.")

    st.subheader("📋 Información general del manifiesto")
    st.dataframe(pd.DataFrame([{"Campo": k, "Valor": v} for k, v in info.items()]),
                 use_container_width=True, hide_index=True)

    with st.expander("📦 Todos los datos que se reenviarán al cumplir (traídos del manifiesto)"):
        st.dataframe(pd.DataFrame([{"Variable": k, "Valor": v} for k, v in full.items()]),
                     use_container_width=True, hide_index=True)

    st.subheader("✍️ Datos del cumplido")
    c1, c2 = st.columns(2)
    tipo_lbl = c1.selectbox("Tipo de Cumplido *", TIPOS_CUMPLIDO_MANIFIESTO, key="cmf_tipo")
    fecha = c2.date_input("Fecha de entrega documentos *", key="cmf_fecha", format="DD/MM/YYYY")
    tipo = tipo_lbl.split(" ")[0]
    fecha_str = fecha.strftime("%d/%m/%Y") if fecha else ""

    confirma = st.checkbox("Confirmo el cumplido (registra datos reales en el RNDC)",
                           key="cmf_ok", disabled=ya_cumplido)
    if st.button("✅ Guardar cumplido del manifiesto", type="primary",
                 disabled=(not confirma or ya_cumplido), key="cmf_send"):
        p = _perfil_corregir(perfil)
        # Passthrough: reenviar TODOS los campos del proceso 6 (valores pactados/finales
        # del viaje, horas, placa, conductor, etc.) excepto la metadata/solo-lectura;
        # + tipo de cumplido + fecha de entrega (los 2 editables).
        variables = {k: v for k, v in full.items() if str(k).upper() not in _CMF_NO_ENVIAR}
        # Sobrescribir con las MISMAS claves (minúscula) que devuelve el consult,
        # para no duplicar por casing. Estos 4 son los que mandan/edita el usuario.
        variables["numnitempresatransporte"] = p.get("nit_socio", "")
        variables["nummanifiestocarga"] = man
        variables["tipocumplidomanifiesto"] = tipo
        variables["fechaentregadocumentos"] = fecha_str
        with st.spinner("Registrando cumplido…"):
            ok, r = cumplir_manifiesto(variables, p)
        if ok:
            st.success(f"✓ Manifiesto {man} cumplido. Radicado: {r.get('ingresoid','?')}")
            st.session_state["cmf_estado"] = "CE"
        else:
            st.error(f"✗ {r}")


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: Anular cumplido manifiesto (proceso 29)
# ─────────────────────────────────────────────────────────────────────────────
def modulo_anular_cumplido_manifiesto(perfil):
    st.header("🗑 Anular Cumplido Manifiesto")
    st.caption("Escribe el N° de manifiesto, elige el motivo y anula su cumplido (proceso 29).")

    if st.button("🗑 Limpiar módulo", key="acm_clear"):
        _limpiar_modulo(["acm_"])
    manifiesto = st.text_input("N° Manifiesto de carga", key="acm_man")
    motivo = st.selectbox("Motivo de la anulación", MOTIVOS_ANULACION, key="acm_motivo")
    obs = st.text_input("Observaciones (opcional)", key="acm_obs")
    confirma = st.checkbox("Confirmo que quiero anular este cumplido (operación real)", key="acm_ok")
    if st.button("🗑 Guardar anulación cumplido", type="primary", disabled=not confirma, key="acm_send"):
        man = manifiesto.strip()
        if not man:
            st.warning("Escribe el N° del manifiesto.")
            return
        p = _perfil_corregir(perfil)
        cod = motivo.split(" ")[0]
        with st.spinner("Anulando…"):
            ok, r = anular_cumplido_manifiesto(man, cod, p, obs.strip())
        if ok:
            st.success(f"✓ Cumplido del manifiesto {man} anulado. Radicado: {r.get('ingresoid','?')}")
        else:
            st.error(f"✗ {r}")


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: Cumplir remesa (proceso 5)
# ─────────────────────────────────────────────────────────────────────────────
def _cumplir_autocalcular(res):
    """Tiempos automáticos a partir de las citas (igual que _autocalcular del desktop)."""
    f_carg = res.get("fechacitapactadacargue", ""); h_carg = res.get("horacitapactadacargue", "")
    f_desc = res.get("fechacitapactadadescargue", ""); h_desc = res.get("horacitapactadadescargueremesa", "")
    tv = {}
    for n, (_e, fc, hc) in enumerate(lib_remesas.CUMPLIR_CARGUE_ROWS, 1):
        fe, ho = lib_remesas.fecha_hora_mas(f_carg, h_carg, n); tv[fc] = fe; tv[hc] = ho
    for n, (_e, fc, hc) in enumerate(lib_remesas.CUMPLIR_DESCARGUE_ROWS, 1):
        fe, ho = lib_remesas.fecha_hora_mas(f_desc, h_desc, n); tv[fc] = fe; tv[hc] = ho
    return tv


def modulo_cumplir_remesa(perfil):
    st.header("✅ Cumplir Remesa")
    st.caption("Consulta la remesa, elige el tipo de cumplido; los tiempos se calculan solos y son editables (proceso 5).")

    consec_in = st.text_input("Consecutivo remesa", key="cum_in")
    b1, b2, b3 = st.columns([1.2, 1.4, 1])
    do_consult = b1.button("🔍 Consultar remesa", key="cum_consult")
    do_traer = b2.button("📥 Traer tiempos del cumplido", key="cum_traer")
    if b3.button("🗑 Limpiar módulo", key="cum_clear"):
        _limpiar_modulo(["cum_"])

    if do_consult:
        p = _perfil_corregir(perfil)
        consec = _consec_efectivo(consec_in, p)
        with st.spinner(f"Consultando remesa {consec}…"):
            ok, res = consultar_remesa_completa(consec, p)
        if ok:
            st.session_state["cum_res"] = res
            st.session_state["cum_consec"] = consec
            st.session_state["cum_times"] = _cumplir_autocalcular(res)
            st.session_state["cum_tipo"] = lib_remesas.CUMPLIR_TIPOS[0]
        else:
            st.session_state.pop("cum_res", None)
            st.error(f"✗ {res}")

    if do_traer:
        p = _perfil_corregir(perfil)
        consec = _consec_efectivo(consec_in, p)
        with st.spinner(f"Trayendo tiempos del cumplido de {consec}…"):
            ok, res = consultar_remesa_completa(consec, p, procesoid=5)
        if ok:
            st.session_state["cum_res"] = res
            st.session_state["cum_consec"] = consec
            tv = {}
            for _e, fc, hc in lib_remesas.CUMPLIR_CARGUE_ROWS + lib_remesas.CUMPLIR_DESCARGUE_ROWS:
                tv[fc] = res.get(fc.lower(), ""); tv[hc] = res.get(hc.lower(), "")
            st.session_state["cum_times"] = tv
            tcr = (res.get("tipocumplidoremesa", "") or "").strip().upper()
            if tcr in ("C", "S"):
                st.session_state["cum_tipo"] = "C — Cumplido Normal" if tcr == "C" else "S — Suspensión"
            if not (res.get("fechallegadacargue") or res.get("horallegadacargueremesa")):
                st.warning("⚠ La remesa no tiene tiempos de cumplido registrados (¿no está cumplida?).")
        else:
            st.error(f"✗ {res}")

    res = st.session_state.get("cum_res")
    if not res:
        return
    consec = st.session_state.get("cum_consec", "")
    times = st.session_state.get("cum_times", {})

    tipo_lbl = st.selectbox("Tipo de Cumplido", lib_remesas.CUMPLIR_TIPOS,
                            index=lib_remesas.CUMPLIR_TIPOS.index(st.session_state.get("cum_tipo", lib_remesas.CUMPLIR_TIPOS[0])),
                            key="cum_tipo_sel")
    tipo = tipo_lbl.split(" ")[0]
    cant = res.get("cantidadcargada", "") or res.get("cantidadinformacioncarga", "")
    st.caption(f"Remesa {consec} · Cantidad cargada: {cant or '—'} · entregada: "
               f"{cant if tipo == 'C' else '0'} (automático)")

    # Campos de tiempos editables (auto-rellenados). Cargue siempre; descargue si Normal.
    nuevos = dict(times)
    st.markdown("**🕒 Cargue (origen)**")
    for etq, fc, hc in lib_remesas.CUMPLIR_CARGUE_ROWS:
        c1, c2, c3 = st.columns([1, 2, 1])
        c1.markdown(f"{etq}")
        nuevos[fc] = c2.text_input(f"Fecha {etq} cargue", value=times.get(fc, ""), key=f"cum_t_{fc}",
                                   label_visibility="collapsed")
        nuevos[hc] = c3.text_input(f"Hora {etq} cargue", value=times.get(hc, ""), key=f"cum_t_{hc}",
                                   label_visibility="collapsed")
    if tipo == "C":
        st.markdown("**🕒 Descargue (destino)**")
        for etq, fc, hc in lib_remesas.CUMPLIR_DESCARGUE_ROWS:
            c1, c2, c3 = st.columns([1, 2, 1])
            c1.markdown(f"{etq}")
            nuevos[fc] = c2.text_input(f"Fecha {etq} descargue", value=times.get(fc, ""), key=f"cum_t_{fc}",
                                       label_visibility="collapsed")
            nuevos[hc] = c3.text_input(f"Hora {etq} descargue", value=times.get(hc, ""), key=f"cum_t_{hc}",
                                       label_visibility="collapsed")

    confirma = st.checkbox("Confirmo el cumplido (registra datos reales en el RNDC)", key="cum_ok")
    if st.button("✅ Guardar cumplido", type="primary", disabled=not confirma, key="cum_send"):
        p = _perfil_corregir(perfil)
        variables = {
            "NUMNITEMPRESATRANSPORTE":  p.get("nit_socio", ""),
            "CONSECUTIVOREMESA":        consec,
            "TIPOCUMPLIDOREMESA":       tipo,
            "CANTIDADINFORMACIONCARGA": cant,
            "CANTIDADENTREGADA":        cant if tipo == "C" else "0",
        }
        errores = []
        filas = lib_remesas.CUMPLIR_CARGUE_ROWS + (lib_remesas.CUMPLIR_DESCARGUE_ROWS if tipo == "C" else [])
        for etq, fc, hc in filas:
            fe = str(nuevos.get(fc, "")).strip(); ho = str(nuevos.get(hc, "")).strip()
            variables[fc] = fe; variables[hc] = ho
            if not fe or not ho:
                errores.append(f"Falta fecha/hora de {etq}.")
        if tipo == "S":
            variables["MOTIVOSUSPENSIONREMESA"] = "O"
        if errores:
            st.warning("\n".join(errores))
            return
        with st.spinner("Registrando cumplido…"):
            ok, r = cumplir_remesa(variables, p)
        if ok:
            st.success(f"✓ Cumplido registrado. Radicado: {r.get('ingresoid','?')}")
        else:
            st.error(f"✗ {r}")


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: Auto cambio-generador (orquestador)
# ─────────────────────────────────────────────────────────────────────────────
def modulo_auto_cambio_generador(perfil):
    st.header("⚡ Auto cambio-generador")
    st.caption("Descumple → cambia generador → vuelve a cumplir, en lote. Procesa una o varias remesas.")

    if st.button("🗑 Limpiar módulo", key="auto_clear"):
        _limpiar_modulo(["auto_"])

    txt = st.text_area("Consecutivo(s) de remesa (coma, espacio o salto de línea)",
                       height=100, key="auto_txt")
    c1, c2 = st.columns(2)
    nit_nuevo = c1.selectbox("Nuevo NIT generador", lib_remesas.AUTO_NITS_GENERADOR + ["(manual)"], key="auto_nit_sel")
    if nit_nuevo == "(manual)":
        nit_nuevo = c1.text_input("NIT manual", key="auto_nit_man")
    tipoid = c2.selectbox("Tipo ID", lib_remesas.AUTO_TIPOID, key="auto_tipoid").split(" ")[0]
    c3, c4, c5 = st.columns(3)
    sede = c3.text_input("Código sede generador", "1", key="auto_sede")
    cod_anul = c4.selectbox("Motivo anulación", lib_remesas.AUTO_MOTIVOS_ANULACION, key="auto_anul").split(" ")[0]
    cod_camb = c5.selectbox("Motivo cambio", lib_remesas.AUTO_MOTIVOS_CAMBIO, key="auto_camb").split(" ")[0]

    confirma = st.checkbox("Confirmo: son operaciones reales en el RNDC y NO se deshacen", key="auto_ok")
    if st.button("⚡ Ejecutar proceso completo", type="primary", disabled=not confirma, key="auto_run"):
        import re
        p = _perfil_corregir(perfil)
        raw = [t for t in re.split(r"[\s,;]+", txt.strip()) if t]
        vistos, consecutivos = set(), []
        for t in raw:
            c = _consec_efectivo(t, p)
            if c and c not in vistos:
                vistos.add(c); consecutivos.append(c)
        if not consecutivos:
            st.warning("Escribe al menos un consecutivo.")
            return
        if not (nit_nuevo and str(nit_nuevo).strip()):
            st.warning("Indica el NIT del nuevo generador.")
            return

        log = []
        resumen = {"ok": 0, "ok_sin_cumplido": 0, "error": 0}
        fallidas = []
        prog = st.progress(0.0, text="Procesando…")
        for i, consec in enumerate(consecutivos, 1):
            estado = _auto_procesar_remesa(consec, nit_nuevo, sede, tipoid, cod_anul, cod_camb, p, log)
            resumen[estado] = resumen.get(estado, 0) + 1
            if estado == "error":
                fallidas.append(consec)
            prog.progress(i / len(consecutivos), text=f"{i}/{len(consecutivos)} · remesa {consec}")
        prog.empty()
        st.success(f"Completas: {resumen['ok']} · Generador cambiado sin cumplido: "
                   f"{resumen['ok_sin_cumplido']} · Con error: {resumen['error']}")
        if fallidas:
            st.error("Remesas con error: " + ", ".join(fallidas))
        st.code("\n".join(log), language=None)


def _auto_procesar_remesa(consec, nit_nuevo, sede, tipoid, cod_anul, cod_camb, perfil, log):
    """Cuerpo de los 5 pasos (réplica de ProcesoCompletoRemesaModule._procesar_remesa).
    Devuelve 'ok' | 'ok_sin_cumplido' | 'error'. Acumula mensajes en `log`."""
    def put(m): log.append(m)
    put(f"═══ Remesa {consec} ═══")
    # 1. Cumplido actual (proceso 5)
    ok5, res5 = consultar_remesa_completa(consec, perfil, procesoid=5)
    res5 = res5 if ok5 else {}
    put("1) Cumplido consultado." if ok5 else f"1) ⚠ Sin cumplido: {res5}")
    # 2. Datos remesa (proceso 3)
    ok3, res3 = consultar_remesa_completa(consec, perfil, procesoid=3)
    if not ok3:
        put(f"2) ✗ No se pudo consultar la remesa: {res3}. Omitida."); return "error"
    put("2) Remesa consultada.")
    manifiesto = str(res3.get("nummanifiestocarga", "")).strip()
    estaba_cumplida = bool(res5.get("fechallegadacargue"))
    sin_manifiesto = not manifiesto
    tipo, times, desc_plan = lib_remesas.plan_cumplido(res5, res3)
    puede_cumplir = not (sin_manifiesto or tipo is None)
    # Datos del cumplido del manifiesto capturados ANTES de anularlo, para re-cumplirlo
    # al final SOLO si hubo que anular el cumplido del manifiesto.
    manif_recumplir = None

    def _recumplir_manifiesto():
        """Si se anuló el cumplido del manifiesto, lo vuelve a cumplir con sus datos
        originales (passthrough del proceso 6 capturado antes de anular)."""
        if manif_recumplir is None:
            return
        put(f"6) Re-cumpliendo el manifiesto {manifiesto} con sus datos originales…")
        variables = {k: v for k, v in manif_recumplir.items()
                     if str(k).upper() not in _CMF_NO_ENVIAR}
        variables["numnitempresatransporte"] = perfil.get("nit_socio", "")
        variables["nummanifiestocarga"] = manifiesto
        okRM, resRM = cumplir_manifiesto(variables, perfil)
        if okRM:
            put(f"   ✓ Manifiesto re-cumplido (radicado {resRM.get('ingresoid','?')}).")
        else:
            put(f"   ✗ Falló re-cumplir el manifiesto: {resRM}. Cúmplelo a mano.")

    if sin_manifiesto:
        put("   → PENDIENTE DE ASIGNAR MANIFIESTO: se omitirá el cumplido.")
    elif tipo is None:
        put(f"   → {desc_plan}: se omitirá el cumplido.")
    else:
        put(f"   → Re-cumplido planeado: {desc_plan}")
    # 3. Anular cumplido (28) si estaba cumplida, con fallback al manifiesto (29)
    if estaba_cumplida:
        okA, resA = anular_cumplido_remesa(consec, cod_anul, perfil)
        if not okA:
            put(f"3) ⚠ No se pudo anular cumplido remesa: {resA}")
            if manifiesto:
                # Capturar el cumplido del manifiesto ANTES de anularlo (proceso 6),
                # para restaurarlo al final con los mismos datos.
                put(f"   ↻ El manifiesto {manifiesto} está cumplido. Capturando su cumplido "
                    "(proceso 6) para restaurarlo luego…")
                ok6m, res6m = consultar_manifiesto_completo(manifiesto, perfil, procesoid=6)
                if ok6m and isinstance(res6m, dict):
                    manif_recumplir = res6m
                else:
                    put("   ⚠ No se pudo capturar el cumplido del manifiesto; se anulará igual "
                        "pero podría no restaurarse automáticamente.")
                put(f"   ↻ Anulando cumplido del manifiesto {manifiesto} (proceso 29)…")
                okM, resM = anular_cumplido_manifiesto(manifiesto, cod_anul, perfil)
                if not okM:
                    put(f"   ✗ Falló anulación manifiesto: {resM}. Omitida."); return "error"
                okA, resA = anular_cumplido_remesa(consec, cod_anul, perfil)
                if not okA:
                    put(f"   ✗ Aún falló anulación remesa: {resA}. Omitida."); return "error"
            else:
                put("   ✗ Sin manifiesto asociado para anular. Omitida."); return "error"
        put(f"3) Cumplido anulado (radicado {resA.get('ingresoid','?')}).")
    else:
        put("3) No estaba cumplida → se omite anulación.")
    # 4. Corregir generador (38, CODIGOCAMBIO=4)
    var_corr = {"NUMNITEMPRESATRANSPORTE": perfil.get("nit_socio", ""), "consecutivoRemesa": consec}
    for envio, consulta in lib_remesas.CORREGIR_BASE_FIELDS:
        var_corr[envio] = res3.get(consulta, "")
    var_corr["codTipoIdPropietario"] = tipoid
    var_corr["numIdPropietario"] = nit_nuevo
    var_corr["codSedePropietario"] = sede
    var_corr["MOTIVOCAMBIO"] = cod_camb
    var_corr["CODIGOCAMBIO"] = "4"
    okC, resC = corregir_remesa(var_corr, perfil)
    if not okC:
        put(f"4) ✗ Falló la corrección: {resC}. Omitida."); return "error"
    put(f"4) Generador cambiado (radicado {resC.get('ingresoid','?')}).")
    # 5. Re-cumplir (5) si es posible
    if not puede_cumplir:
        motivo = "no tiene manifiesto" if sin_manifiesto else "no hay tiempos ni citas"
        put(f"5) Cumplido de remesa OMITIDO: {motivo}.")
        _recumplir_manifiesto()   # restaurar el manifiesto si se anuló su cumplido
        put("✔ Generador cambiado.")
        return "ok_sin_cumplido"
    cant = res3.get("cantidadcargada", "") or res5.get("cantidadcargada", "") \
        or res3.get("cantidadinformacioncarga", "")
    var_cum = {
        "NUMNITEMPRESATRANSPORTE": perfil.get("nit_socio", ""),
        "CONSECUTIVOREMESA": consec, "TIPOCUMPLIDOREMESA": tipo,
        "CANTIDADINFORMACIONCARGA": cant, "CANTIDADENTREGADA": cant if tipo == "C" else "0",
    }
    var_cum.update(times)
    if tipo == "S":
        var_cum["MOTIVOSUSPENSIONREMESA"] = "O"
    okU, resU = cumplir_remesa(var_cum, perfil)
    if not okU:
        put(f"5) ✗ Falló el re-cumplido de la remesa: {resU}. Quedó con generador cambiado sin cumplir.")
        _recumplir_manifiesto()   # intentar restaurar el manifiesto igualmente
        return "error"
    put(f"5) Remesa re-cumplida (radicado {resU.get('ingresoid','?')}).")
    # 6. Re-cumplir el manifiesto si su cumplido fue anulado en el paso 3
    _recumplir_manifiesto()
    put("✔ COMPLETA.")
    return "ok"


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: Editar XML (grupo Otros)
# ─────────────────────────────────────────────────────────────────────────────
_EX_REM_CAMPOS = ["consecutivo", "radicado", "valor", "peso", "descripcion"]
_EX_REM_ETIQ = ["Consecutivo", "Radicado", "Valor ($)", "Peso", "Descripción línea"]


def _ex_cargar(contenido, nombre, perfil, consultar_rndc=True):
    """Parsea el XML y guarda en session_state los datos editables + originales."""
    # Limpiar keys de widgets de remesas de una carga previa (evita valores viejos)
    for k in [x for x in st.session_state.keys() if str(x).startswith("ex_f_")]:
        del st.session_state[k]
    d = lib_editar.parse_xml(contenido)
    st.session_state["ex_contenido"] = contenido
    st.session_state["ex_nombre"] = nombre
    st.session_state["ex_orig"] = {
        "numero": d["numero"], "cufe": d["cufe"], "cliente": d["cliente"],
        "fecha": d["fecha"], "fecha_iso": d["fecha_iso"],
        "total": d["total"], "total_orig": d["total_orig"], "nit": d["nit"], "dig": d["dig"],
    }
    # Valores editables (arrancan iguales al original)
    st.session_state["ex_numero"] = d["numero"]
    st.session_state["ex_cufe"] = d["cufe"]
    st.session_state["ex_cliente"] = d["cliente"]
    st.session_state["ex_fecha"] = d["fecha"]
    st.session_state["ex_total"] = d["total"]
    st.session_state["ex_nit"] = d["nit"]
    st.session_state["ex_dig"] = d["dig"]
    # Remesas con _id estable
    rid = 0
    remesas = []
    for r in d["remesas"]:
        rid += 1
        remesas.append({"_id": rid, "consecutivo": r["consecutivo"], "radicado": r["radicado"],
                        "valor": r["valor"], "peso": r["peso"], "descripcion": r["descripcion"],
                        "_nuevo": False})
    st.session_state["ex_rid"] = rid
    # Auto-consulta de radicado/peso al RNDC (como el desktop, una vez al cargar)
    if consultar_rndc and perfil and remesas:
        for rem in remesas:
            consec = str(rem.get("consecutivo", "")).strip()
            if not consec:
                continue
            try:
                ok, res = consultar_radicado_remesa(consec, perfil)
            except Exception:
                ok, res = False, {}
            if ok:
                rem["radicado"] = res.get("radicado", rem.get("radicado", ""))
                rem["peso"] = res.get("peso", rem.get("peso", ""))
    st.session_state["ex_remesas"] = remesas


def modulo_editar_xml(perfil):
    st.header("✏️ Editar XML")
    st.caption("Carga un XML de factura, edita datos y remesas, y descarga el XML modificado.")

    archivo = st.file_uploader("XML de factura", type=["xml"], key="ex_file")
    cargar = st.button("📂 Cargar / Recargar XML", key="ex_load")
    if st.button("🗑 Limpiar módulo", key="ex_clear"):
        _limpiar_modulo(["ex_"])

    if archivo is not None and cargar:
        with st.spinner("Cargando y consultando RNDC…"):
            _ex_cargar(archivo.getvalue().decode("utf-8", errors="replace"), archivo.name, perfil)
        st.rerun()

    if "ex_contenido" not in st.session_state:
        st.info("Carga un XML y pulsa 'Cargar / Recargar XML'.")
        return

    st.success(f"📄 {st.session_state.get('ex_nombre','')} · "
               f"{len(st.session_state.get('ex_remesas', []))} remesa(s)")

    st.subheader("Datos generales de la factura")
    c1, c2 = st.columns(2)
    c1.text_input("N° Factura", key="ex_numero")
    c2.text_input("CUFE", key="ex_cufe")
    c3, c4, c5 = st.columns([2, 1, 1])
    c3.text_input("Cliente", key="ex_cliente")
    c4.text_input("NIT cliente", key="ex_nit")
    c5.text_input("Dígito verif.", key="ex_dig")
    c6, c7 = st.columns(2)
    c6.text_input("Fecha de generación (DD-MM-YYYY / YYYY-MM-DD)", key="ex_fecha")
    c7.text_input("Total valor factura ($)", key="ex_total")
    # Vencimiento (+30) informativo
    try:
        iso = lib_editar._to_iso(str(st.session_state.get("ex_fecha", "")).strip())
        venc = (lib_editar.datetime.strptime(iso, "%Y-%m-%d") + lib_editar.timedelta(days=30)).strftime("%Y-%m-%d")
        c6.caption(f"Vencimiento (+30 días): {venc}")
    except Exception:
        pass

    st.subheader("📦 Remesas")
    remesas = st.session_state["ex_remesas"]

    peso1 = st.checkbox("Peso por defecto = 1 KGM (fuerza 1 en todas las remesas al guardar)",
                        key="ex_peso1")
    if peso1:   # forzar 1 antes de crear los widgets de peso
        for rem in remesas:
            rem["peso"] = "1"
            st.session_state[f"ex_f_{rem['_id']}_peso"] = "1"

    if st.button("🔍 Consultar radicados/pesos en el RNDC", key="ex_consult"):
        with st.spinner("Consultando RNDC…"):
            for rem in remesas:
                consec = str(rem.get("consecutivo", "")).strip()
                if not consec:
                    continue
                ok, res = consultar_radicado_remesa(consec, perfil)
                if ok:
                    rem["radicado"] = res.get("radicado", rem.get("radicado", ""))
                    rem["peso"] = res.get("peso", rem.get("peso", ""))
                    st.session_state[f"ex_f_{rem['_id']}_radicado"] = rem["radicado"]
                    st.session_state[f"ex_f_{rem['_id']}_peso"] = rem["peso"]
        st.rerun()

    anchos = [0.4, 2, 2, 1.6, 1, 3, 0.6]
    hc = st.columns(anchos)
    for h, c in zip(["N°"] + _EX_REM_ETIQ + [""], hc):
        c.markdown(f"**{h}**")
    for idx, rem in enumerate(remesas, 1):
        rid = rem["_id"]
        cols = st.columns(anchos)
        cols[0].markdown(f"#### {idx}")
        for col_w, campo in zip(cols[1:6], _EX_REM_CAMPOS):
            k = f"ex_f_{rid}_{campo}"
            if k not in st.session_state:
                st.session_state[k] = rem[campo]
            # El peso queda bloqueado en 1 si el checkbox está marcado
            dis = (campo == "peso" and peso1)
            rem[campo] = col_w.text_input(campo, key=k, label_visibility="collapsed", disabled=dis)
        if cols[6].button("−", key=f"ex_del_{rid}", help="Quitar esta remesa"):
            if len(remesas) > 1:
                for campo in _EX_REM_CAMPOS:
                    st.session_state.pop(f"ex_f_{rid}_{campo}", None)
                st.session_state["ex_remesas"] = [r for r in remesas if r["_id"] != rid]
                st.rerun()
    if st.button("＋ Agregar remesa", key="ex_add"):
        st.session_state["ex_rid"] = st.session_state.get("ex_rid", 0) + 1
        remesas.append({"_id": st.session_state["ex_rid"], "consecutivo": "", "radicado": "",
                        "valor": "", "peso": "", "descripcion": "", "_nuevo": True})
        st.rerun()

    st.markdown("---")
    if st.button("💾 Generar XML modificado", type="primary", key="ex_save"):
        if st.session_state.get("ex_peso1"):   # forzar peso 1 en el guardado
            for r in remesas:
                r["peso"] = "1"
        nuevos = {"numero": st.session_state["ex_numero"], "cufe": st.session_state["ex_cufe"],
                  "cliente": st.session_state["ex_cliente"], "fecha": st.session_state["ex_fecha"],
                  "total": st.session_state["ex_total"], "nit": st.session_state["ex_nit"],
                  "dig": st.session_state["ex_dig"]}
        try:
            nuevo, avisos = lib_editar.guardar_xml(
                st.session_state["ex_contenido"], st.session_state["ex_orig"], nuevos, remesas)
        except Exception as e:
            st.error(f"Error al guardar: {e}")
            return
        for a in avisos:
            st.warning(a)
        st.success("✓ XML modificado generado.")
        nombre = st.session_state.get("ex_nombre", "factura.xml")
        st.download_button("⬇️ Descargar XML modificado", nuevo.encode("utf-8"),
                           file_name=nombre, mime="application/xml", key="ex_dl")


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: Reconstruir XML (grupo Otros)
# ─────────────────────────────────────────────────────────────────────────────
def modulo_reconstruir_xml(perfil):
    st.header("🔧 Reconstruir XML")
    st.caption("Aplica las transformaciones DIAN al XML original según el perfil activo "
               "y actualiza radicado/peso desde el RNDC.")

    if not lib_reconstruir.RECONSTRUIR_OK:
        st.error("No se pudo importar el módulo de transformación XML:\n\n"
                 + lib_reconstruir._RECONSTRUIR_ERR)
        return

    st.info(f"⚙️ Perfil activo: **{perfil.get('nombre','')}** · "
            f"{perfil.get('nombre_socio','')} · NIT {perfil.get('nit_socio','')}")

    archivos = st.file_uploader("XML(s) a reconstruir", type=["xml"],
                                accept_multiple_files=True, key="rec_files")
    if archivos:
        nuevos = [(a.name, a.getvalue()) for a in archivos]
        if nuevos != st.session_state.get("rec_data"):
            st.session_state["rec_data"] = nuevos
            # Archivos nuevos → descartar resultados previos (mostrar tabla pendiente)
            st.session_state.pop("rec_tabla", None)
            st.session_state.pop("rec_salidas", None)
            st.session_state.pop("rec_resumen", None)
    if st.button("🗑 Limpiar módulo", key="rec_clear"):
        _limpiar_modulo(["rec_"])

    files_data = st.session_state.get("rec_data", [])
    if not files_data:
        st.info("Carga uno o varios XML.")
        return

    # Tabla de archivos cargados (7 columnas, igual que el desktop). Antes de
    # reconstruir muestra las remesas leídas del XML con estado "Pendiente";
    # tras reconstruir se reemplaza por los resultados.
    _COLS_REC = ["Archivo", "N° Factura", "Cliente", "Remesa", "Radicado", "Peso", "Estado"]
    if "rec_tabla" not in st.session_state:
        pend = []
        total_rem = 0
        for nombre, b in files_data:
            contenido = b.decode("utf-8", errors="replace")
            nf, cli = lib_reconstruir.leer_cabecera_str(contenido)
            remesas = lib_reconstruir.leer_remesas_str(contenido)
            total_rem += len(remesas)
            if remesas:
                for rem in remesas:
                    pend.append({"Archivo": nombre, "N° Factura": nf, "Cliente": cli,
                                 "Remesa": rem["consecutivo"], "Radicado": rem["radicado"],
                                 "Peso": rem["peso"], "Estado": "⏳ Pendiente"})
            else:
                pend.append({"Archivo": nombre, "N° Factura": nf, "Cliente": cli,
                             "Remesa": "", "Radicado": "", "Peso": "", "Estado": "⏳ Pendiente"})
        st.caption(f"{len(files_data)} archivo(s) · {total_rem} remesa(s) en total")
        st.dataframe(pd.DataFrame(pend, columns=_COLS_REC),
                     use_container_width=True, hide_index=True)

    peso1 = st.checkbox("Peso por defecto = 1 KGM", key="rec_peso1")

    if st.button("🔧 Reconstruir facturas", type="primary", key="rec_run"):
        peso_fijo = "1" if peso1 else None
        prog = st.progress(0.0, text="Reconstruyendo…")
        resultados_tabla = []
        salidas = []   # (nombre, contenido) para el zip
        ok_count = err_count = 0
        for i, (nombre, b) in enumerate(files_data, 1):
            contenido = b.decode("utf-8", errors="replace")
            nf, cli = lib_reconstruir.leer_cabecera_str(contenido)
            ok, salida, resultados, error = lib_reconstruir.reconstruir_uno(
                contenido, nombre, perfil, peso_fijo)
            if ok:
                ok_count += 1
                salidas.append((nombre, salida))
                if resultados:
                    for rem in resultados:
                        resultados_tabla.append({
                            "Archivo": nombre, "N° Factura": nf, "Cliente": cli,
                            "Remesa": rem.get("consecutivo", ""), "Radicado": rem.get("radicado", ""),
                            "Peso": rem.get("peso", ""), "Estado": "✓ Reconstruido"})
                else:
                    resultados_tabla.append({"Archivo": nombre, "N° Factura": nf, "Cliente": cli,
                                             "Remesa": "", "Radicado": "", "Peso": "",
                                             "Estado": "✓ Reconstruido"})
            else:
                err_count += 1
                resultados_tabla.append({"Archivo": nombre, "N° Factura": nf, "Cliente": cli,
                                         "Remesa": "", "Radicado": "", "Peso": "",
                                         "Estado": f"✗ {str(error)[:120]}"})
            prog.progress(i / len(files_data), text=f"{i}/{len(files_data)} · {nombre}")
        prog.empty()
        st.session_state["rec_tabla"] = resultados_tabla
        st.session_state["rec_salidas"] = salidas
        st.session_state["rec_resumen"] = (ok_count, err_count)

    # Render de resultados (persisten)
    if "rec_tabla" in st.session_state:
        ok_count, err_count = st.session_state.get("rec_resumen", (0, 0))
        if err_count == 0:
            st.success(f"✓ {ok_count} factura(s) reconstruida(s).")
        elif ok_count == 0:
            st.error(f"✗ {err_count} archivo(s) con error.")
        else:
            st.warning(f"✓ {ok_count} OK · ✗ {err_count} con error.")
        st.dataframe(pd.DataFrame(st.session_state["rec_tabla"], columns=_COLS_REC),
                     use_container_width=True, hide_index=True)
        salidas = st.session_state.get("rec_salidas", [])
        if salidas:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for nombre, contenido in salidas:
                    zf.writestr(nombre, contenido)
            st.download_button("⬇️ Descargar reconstruidos (.zip)", buf.getvalue(),
                               file_name="reconstruidos.zip", mime="application/zip", key="rec_dl")


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: Cruzar remesas (grupo Otros)
# ─────────────────────────────────────────────────────────────────────────────
def _cr_cargar(col, prefijo, label):
    """Carga un archivo (RG u otro), lo cachea y devuelve el DataFrame de la hoja."""
    archivo = col.file_uploader(label, type=["xlsx", "xls", "xlsm", "csv"],
                                key=f"crz_{prefijo}_file")
    if archivo is not None:
        b = archivo.getvalue()
        if b != st.session_state.get(f"crz_{prefijo}_bytes"):
            st.session_state[f"crz_{prefijo}_bytes"] = b
            st.session_state[f"crz_{prefijo}_name"] = archivo.name
            st.session_state.pop(f"crz_{prefijo}_hoja", None)
            campos = lib_cruce.CAMPOS_RG if prefijo == "rg" else lib_cruce.CAMPOS_OTRO
            for clave, _, _ in campos:
                st.session_state.pop(f"crz_map_{clave}", None)
            st.session_state.pop("crz_cruce", None)
    b = st.session_state.get(f"crz_{prefijo}_bytes")
    if not b:
        return None
    name = st.session_state.get(f"crz_{prefijo}_name", "")
    col.caption(f"📄 {name}")
    if name.lower().endswith(".csv"):
        try:
            return pd.read_csv(io.BytesIO(b))
        except Exception as e:
            col.error(str(e))
            return None
    try:
        xl = pd.ExcelFile(io.BytesIO(b))
    except Exception as e:
        col.error(str(e))
        return None
    hoja = col.selectbox("Hoja", xl.sheet_names, key=f"crz_{prefijo}_hoja")
    try:
        return xl.parse(hoja)
    except Exception as e:
        col.error(str(e))
        return None


def _cr_map_select(clave, etq, req, df):
    """Selectbox de mapeo con auto-detección por hints (sembrada una vez)."""
    key = f"crz_map_{clave}"
    cols = list(df.columns.astype(str))
    opts = [lib_cruce.NO_USAR] + cols
    if key not in st.session_state:
        st.session_state[key] = lib_cruce.auto_col(clave, df) or lib_cruce.NO_USAR
    if st.session_state[key] not in opts:
        st.session_state[key] = lib_cruce.NO_USAR
    sel = st.selectbox(("* " if req else "○ ") + etq, opts, key=key)
    return None if sel == lib_cruce.NO_USAR else sel


def _cr_consultar_facturas():
    """Herramienta independiente: busca facturas por número en un Excel."""
    archivo = st.file_uploader("Excel a consultar", type=["xlsx", "xls", "xlsm", "csv"], key="cf_file")
    if archivo is not None:
        b = archivo.getvalue()
        if b != st.session_state.get("cf_bytes"):
            st.session_state["cf_bytes"] = b
            st.session_state["cf_name"] = archivo.name
            st.session_state.pop("cf_hoja", None)
            st.session_state.pop("cf_col", None)
            st.session_state.pop("cf_result", None)
    b = st.session_state.get("cf_bytes")
    if not b:
        st.caption("Carga un Excel (ej. el del cruce) para buscar facturas por número.")
        return
    name = st.session_state.get("cf_name", "")
    if name.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(b))
    else:
        xl = pd.ExcelFile(io.BytesIO(b))
        hoja = st.selectbox("Hoja", xl.sheet_names, key="cf_hoja")
        df = xl.parse(hoja)
    cols = list(df.columns.astype(str))
    autocol = None
    for c in cols:
        cn = c.lower().replace(" ", "_").replace("°", "")
        if any(h in cn for h in ["factura", "nfactura", "num_fac", "n_factura", "numero_factura"]):
            autocol = c
            break
    idx = (cols.index(autocol) + 1) if autocol in cols else 0
    colf = st.selectbox("Columna N° Factura", [lib_cruce.NO_USAR] + cols, index=idx, key="cf_col")
    txt = st.text_area("Números de factura (coma, espacio o salto de línea)", key="cf_txt", height=100)
    if st.button("🔍 Buscar facturas", key="cf_buscar"):
        if colf == lib_cruce.NO_USAR:
            st.warning("Selecciona la columna de N° Factura.")
        else:
            tokens = [t for t in re.split(r"[\s,;]+", txt.strip()) if t]
            vistos, buscadas = set(), []
            for t in tokens:
                nm = lib_cruce.norm_factura(t)
                if nm and nm not in vistos:
                    vistos.add(nm)
                    buscadas.append(nm)
            nf_norm = df[colf].map(lib_cruce.norm_factura)
            mask = nf_norm.isin(set(buscadas))
            df_enc = df[mask]
            enc = set(nf_norm[mask])
            st.session_state["cf_result"] = df_enc
            st.session_state["cf_enc"] = len(enc)
            st.session_state["cf_total"] = len(buscadas)
            st.session_state["cf_noenc"] = [n for n in buscadas if n not in enc]
    if isinstance(st.session_state.get("cf_result"), pd.DataFrame):
        df_enc = st.session_state["cf_result"]
        msg = f"✓ Encontradas {st.session_state['cf_enc']}/{st.session_state['cf_total']} · {len(df_enc)} fila(s)."
        if st.session_state.get("cf_noenc"):
            msg += " · ✗ No encontradas: " + ", ".join(st.session_state["cf_noenc"])
        st.info(msg)
        st.dataframe(df_enc, use_container_width=True, hide_index=True)
        if not df_enc.empty:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as w:
                df_enc.to_excel(w, index=False)
            st.download_button("⬇️ Exportar encontradas", buf.getvalue(),
                               file_name="facturas_consultadas.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key="cf_dl")


def modulo_cruzar_remesas(perfil):
    st.header("🔀 Cruzar remesas")
    st.caption("Cruza el Excel de RG con el otro Excel (consecutivos + valores unitarios) por N° Factura.")

    if st.button("🗑 Limpiar módulo", key="crz_clear"):
        _limpiar_modulo(["crz_", "cf_"])

    col_rg, col_otro = st.columns(2)
    df_rg = _cr_cargar(col_rg, "rg", "Excel de RG")
    df_otro = _cr_cargar(col_otro, "otro", "Otro Excel")

    if df_rg is None or df_otro is None:
        st.info("Carga ambos archivos para mapear y cruzar.")
        st.markdown("---")
        with st.expander("🔎 Consultar facturas en un Excel (independiente del cruce)"):
            _cr_consultar_facturas()
        return

    st.subheader("Mapeo de columnas")
    mc1, mc2 = st.columns(2)
    mapping = {}
    with mc1:
        st.markdown("**Excel de RG**")
        for clave, etq, req in lib_cruce.CAMPOS_RG:
            mapping[clave] = _cr_map_select(clave, etq, req, df_rg)
    with mc2:
        st.markdown("**Otro Excel**")
        for clave, etq, req in lib_cruce.CAMPOS_OTRO:
            mapping[clave] = _cr_map_select(clave, etq, req, df_otro)

    if st.button("⚙️ Cruzar información", type="primary", key="crz_run"):
        ok, msg = lib_cruce.validar(df_rg, df_otro, mapping)
        if not ok:
            st.warning(msg)
        else:
            st.session_state["crz_cruce"] = lib_cruce.cruzar(df_rg, df_otro, mapping)
            st.session_state["crz_mapping"] = mapping

    if "crz_cruce" in st.session_state:
        cruce = st.session_state["crz_cruce"]
        filas = cruce["filas"]
        n = len(filas)
        ok_rem = sum(f["coinciden_remesas"] == "Sí" for f in filas)
        ok_val = sum(f["coincide_valor_factura_rg"] == "Sí" for f in filas)
        n_rec = sum(f["reconstruir"] == "Sí" for f in filas)
        st.success(f"{n} factura(s) cruzada(s) · remesas OK {ok_rem}/{n} · valor OK {ok_val}/{n} · "
                   f"Reconstruir Sí {n_rec}/{n}")
        tabla = [{
            "N° Factura": f["numero_factura"], "Remesas RG": f["remesas_rg"],
            "Remesas Otro Excel": f["remesas_otro"], "¿Coinciden remesas?": f["coinciden_remesas"],
            "Valor Factura RG": f"$ {f['valor_factura_rg']:,.0f}".replace(",", "."),
            "Suma unitarios (comparada)": f"$ {f['suma_comparada']:,.0f}".replace(",", "."),
            "Base": f["base_comparacion"],
            "¿Coincide valor factura con RG?": f["coincide_valor_factura_rg"],
            "Reconstruir": f["reconstruir"]} for f in filas]
        st.dataframe(pd.DataFrame(tabla), use_container_width=True, hide_index=True)

        filtro = st.selectbox("Filtro de exportación", lib_cruce.FILTROS_EXPORT, key="crz_filtro")
        if st.button("💾 Generar Excel del cruce", key="crz_export"):
            df_out = lib_cruce.exportar(df_rg, st.session_state["crz_mapping"], cruce, filtro)
            if df_out.empty:
                st.info(f"Ninguna factura cumple el filtro '{filtro}'.")
            else:
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as w:
                    df_out.to_excel(w, index=False)
                n_fac = df_out[cruce["col_rg_nf"]].astype(str).str.strip().nunique()
                st.success(f"Exportado ({filtro}): {len(df_out)} filas · {n_fac} factura(s).")
                suf = "" if filtro == "Todas" else "_filtrado"
                st.download_button("⬇️ Descargar Excel del cruce", buf.getvalue(),
                                   file_name=f"cruce_remesas{suf}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   key="crz_dl")

    st.markdown("---")
    with st.expander("🔎 Consultar facturas en un Excel (independiente del cruce)"):
        _cr_consultar_facturas()


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: Extraer datos RG (grupo Otros)
# ─────────────────────────────────────────────────────────────────────────────
def modulo_extraer_rg(perfil):
    st.header("📄 Extraer datos RG")
    st.caption("Extrae datos de facturas electrónicas en PDF y exporta a Excel.")

    archivos = st.file_uploader("PDF(s) de facturas", type=["pdf"],
                                accept_multiple_files=True, key="rg_files")
    if archivos:
        st.session_state["rg_data"] = [(a.name, a.getvalue()) for a in archivos]
    if st.button("🗑 Limpiar módulo", key="rg_clear"):
        _limpiar_modulo(["rg_"])

    files_data = st.session_state.get("rg_data", [])
    if not files_data:
        st.info("Carga uno o varios PDF.")
        return

    usar_ref = st.checkbox("Usar campo Referencia del PDF como consecutivo_remesa", key="rg_ref")

    if st.button("⚙️ Extraer datos", type="primary", key="rg_run"):
        prog = st.progress(0.0, text=f"Procesando {len(files_data)} PDF(s)…")
        def _cb(hechos, total):
            prog.progress(hechos / total, text=f"Procesando {hechos}/{total}…")
        resultados = lib_extraer.procesar_pdfs(files_data, usar_ref, on_progress=_cb)
        prog.empty()
        # Tabla por archivo + filas combinadas en orden
        tabla, filas = [], []
        for r in resultados:
            if r["error"]:
                estado = f"✗ {r['error'][:80]}"
            else:
                estado = "✓ Extraído"
                filas.extend(r["filas"])
            tabla.append({
                "Archivo": r["nombre"], "N° Factura": r["nf"], "Fecha": r["fecha"],
                "Líneas": r["nlin"], "Total Factura": f"$ {r['total']:,.0f}".replace(",", "."),
                "Estado": estado})
        st.session_state["rg_tabla"] = tabla
        st.session_state["rg_filas"] = filas

    if "rg_tabla" in st.session_state:
        st.dataframe(pd.DataFrame(st.session_state["rg_tabla"]),
                     use_container_width=True, hide_index=True)
        filas = st.session_state.get("rg_filas", [])
        st.success(f"✓ {len(filas)} fila(s) extraídas de {len(files_data)} PDF(s).")
        if filas:
            df = pd.DataFrame(filas, columns=lib_extraer.COLUMNAS_EXPORT)
            with st.expander("Vista previa de las filas extraídas"):
                st.dataframe(df, use_container_width=True, hide_index=True)
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as w:
                df.to_excel(w, index=False)
            st.download_button("⬇️ Descargar Excel (datos_rg.xlsx)", buf.getvalue(),
                               file_name="datos_rg.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key="rg_dl")


# ─────────────────────────────────────────────────────────────────────────────
# Estructura de grupos del sidebar (igual que el desktop). Cada módulo apunta a su
# función render, o a None si aún no está portado (muestra placeholder).
def _grupos(perfil):
    return {
        "🧾 Facturación": {
            "Generar XML": modulo_generar_xml,
            "Generar facturas vía Excel": modulo_generar_excel,
            "Cargar facturas a RNDC": modulo_cargar_rndc,
        },
        "📋 Remesas": {
            "Consultar remesas": modulo_consultar_remesas,
            "Corregir remesa": modulo_corregir_remesa,
            "Anular cumplido remesa": modulo_anular_cumplido_remesa,
            "Cumplir remesa": modulo_cumplir_remesa,
            "Auto cambio-generador": modulo_auto_cambio_generador,
        },
        "📑 Manifiesto": {
            "Consultar manifiesto": modulo_consultar_manifiesto,
            "Cumplir manifiesto": modulo_cumplir_manifiesto,
            "Anular cumplido manifiesto": modulo_anular_cumplido_manifiesto,
        },
        "🔩 Otros": {
            "Editar XML": modulo_editar_xml,
            "Reconstruir XML": modulo_reconstruir_xml,
            "Extraer datos RG": modulo_extraer_rg,
            "Cruzar remesas": modulo_cruzar_remesas,
        },
    }


def main():
    perfil = _selector_perfil()
    st.sidebar.markdown("---")
    grupos = _grupos(perfil)

    # Módulo activo (persistente). Por defecto, el primero de Facturación.
    if "modulo_activo" not in st.session_state:
        st.session_state["modulo_activo"] = "Generar facturas vía Excel"
    activo = st.session_state["modulo_activo"]
    # Grupo que contiene el activo → se muestra desplegado (los demás colapsados).
    grupo_activo = next((g for g, mods in grupos.items() if activo in mods),
                        next(iter(grupos)))

    # Secciones desplegables con los módulos como botones (como los grupos del desktop).
    for grupo, mods in grupos.items():
        with st.sidebar.expander(grupo, expanded=(grupo == grupo_activo)):
            for nombre, fn in mods.items():
                etiqueta = ("▶ " if nombre == activo else "") + nombre + ("" if fn else "  🚧")
                if st.button(etiqueta, key=f"btn_{nombre}", use_container_width=True):
                    st.session_state["modulo_activo"] = nombre
                    st.rerun()
    st.sidebar.markdown("---")
    st.sidebar.caption("V1.5 · versión web")

    # Render del módulo activo.
    fn = None
    for g, mods in grupos.items():
        if activo in mods:
            fn = mods[activo]
            break
    if fn is None:
        _placeholder(activo)
    else:
        fn(perfil)


if __name__ == "__main__":
    main()
