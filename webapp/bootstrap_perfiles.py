"""
Asegura que exista config/perfiles.py ANTES de que core/services/config lo importen.

- En local: si config/perfiles.py existe (gitignored, con credenciales reales), no
  hace nada.
- En despliegue (Streamlit Cloud, sin perfiles.py en el repo): lo genera a partir de
  los Secrets de Streamlit (st.secrets["perfiles"]). Solo las CREDENCIALES vienen del
  secreto; el resto de la estructura (NITs, nombres, emails) no es sensible y va aquí.

Secrets esperados (.streamlit/secrets.toml en Streamlit Cloud):

    [perfiles.ut_tsp]
    rndc_usuario          = "..."
    rndc_password         = "..."
    rndc_usuario_corregir = "..."
    rndc_password_corregir= "..."

    [perfiles.ut_elogia]
    rndc_usuario          = "..."
    rndc_password         = "..."
    rndc_usuario_corregir = "..."
    rndc_password_corregir= "..."
"""
import os


def _plantilla_perfiles(cr):
    """Genera el contenido de config/perfiles.py. `cr` = dict de credenciales por perfil."""
    def g(perfil, clave):
        return str(cr.get(perfil, {}).get(clave, "")).replace('"', '\\"')

    return f'''NIT_UT        = "901101271"
NOMBRE_UT     = "UNION TEMPORAL AMERICAN LOGISTIC UT"
PREFIJO       = "41"
UNIDAD_MEDIDA = "KGM"

PERFILES = {{
    "ut_tsp": {{
        "nombre":        "UT Transportes Sánchez Polo",
        "nit_socio":     "8901031611",
        "nombre_socio":  "TRANSPORTES SANCHEZ POLO S.A.",
        "email_from":    "emisionfe@sanchezpolo.com",
        "email_contact_supplier": "facturacionelogia@daabon.com.co",
        "carpeta":       "FACTURAS_GENERADAS_TSP",
        "rndc_usuario":  "{g("ut_tsp", "rndc_usuario")}",
        "rndc_password": "{g("ut_tsp", "rndc_password")}",
        "rndc_usuario_corregir":  "{g("ut_tsp", "rndc_usuario_corregir")}",
        "rndc_password_corregir": "{g("ut_tsp", "rndc_password_corregir")}",
        "rndc_usuario_monitoreo":  "{g("ut_tsp", "rndc_usuario_monitoreo")}",
        "rndc_password_monitoreo": "{g("ut_tsp", "rndc_password_monitoreo")}",
        "nit_monitoreo":           "{g("ut_tsp", "nit_monitoreo")}",
        "nit_ut":              "901101271",
        "nombre_ut":           "UNION TEMPORAL AMERICAN LOGISTIC UT",
        "carpeta_reconstruir": "FACTURAS_RECONSTRUIDAS_TSP",
        "nit_customer":        "800021308",
        "email_customer":      "facturacion@drummondltd.com",
        "telefono_customer":   "3135398327",
        "prefijo_remesa":      False,
    }},
    "ut_elogia": {{
        "nombre":        "UT Elogia",
        "nit_socio":     "8190041165",
        "nombre_socio":  "ELOGIA SOLUCIONES LOGISTICAS S.A.S",
        "email_from":    "emisionfe@sanchezpolo.com",
        "email_contact_supplier": "facturacionelogia@daabon.com.co",
        "carpeta":       "FACTURAS_GENERADAS_ELOGIA",
        "rndc_usuario":  "{g("ut_elogia", "rndc_usuario")}",
        "rndc_password": "{g("ut_elogia", "rndc_password")}",
        "rndc_usuario_corregir":  "{g("ut_elogia", "rndc_usuario_corregir")}",
        "rndc_password_corregir": "{g("ut_elogia", "rndc_password_corregir")}",
        "rndc_usuario_monitoreo":  "{g("ut_elogia", "rndc_usuario_monitoreo")}",
        "rndc_password_monitoreo": "{g("ut_elogia", "rndc_password_monitoreo")}",
        "nit_monitoreo":           "{g("ut_elogia", "nit_monitoreo")}",
        "nit_ut":              "901101271",
        "nombre_ut":           "UNION TEMPORAL AMERICAN LOGISTIC UT",
        "carpeta_reconstruir": "FACTURAS_RECONSTRUIDAS_ELOGIA",
        "nit_customer":        "800021308",
        "email_customer":      "facturacion@drummondltd.com",
        "telefono_customer":   "3135398327",
        "prefijo_remesa":      True,
    }},
}}
'''


def asegurar_perfiles(root):
    """Si falta config/perfiles.py, lo genera desde st.secrets. Llamar ANTES de
    importar config/core/services. Lanza RuntimeError si no hay forma de obtenerlo."""
    ruta = os.path.join(root, "config", "perfiles.py")
    if os.path.exists(ruta):
        return  # local: ya está

    try:
        import streamlit as st
        secretos = st.secrets.get("perfiles", None)
    except Exception:
        secretos = None

    if not secretos:
        raise RuntimeError(
            "No existe config/perfiles.py y no se encontraron Secrets de Streamlit "
            "('perfiles'). Configura los Secrets en Streamlit Cloud (ver "
            "webapp/bootstrap_perfiles.py) o incluye config/perfiles.py.")

    # st.secrets es tipo Mapping anidado; lo paso a dict normal
    cr = {perfil: dict(vals) for perfil, vals in dict(secretos).items()}
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(_plantilla_perfiles(cr))
