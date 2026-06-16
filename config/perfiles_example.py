# Copia este archivo como perfiles.py y completa con los valores reales.
# NUNCA subas perfiles.py al repositorio (está en .gitignore).

NIT_UT        = "000000000"
NOMBRE_UT     = "NOMBRE DE LA UNION TEMPORAL"
PREFIJO       = "41"
UNIDAD_MEDIDA = "KGM"

PERFILES = {
    "ut_perfil1": {
        "nombre":                 "Nombre del perfil 1",
        "nit_socio":              "0000000000",
        "nombre_socio":           "NOMBRE EMPRESA SOCIO S.A.",
        "email_from":             "facturacion@empresa.com",
        "email_contact_supplier": "contacto@proveedor.com",
        "carpeta":                "FACTURAS_GENERADAS_PERFIL1",
        "rndc_usuario":           "USUARIO@0000",
        "rndc_password":          "contrasena123",
        "nit_ut":                 "000000000",
        "nombre_ut":              "NOMBRE DE LA UNION TEMPORAL",
        "carpeta_reconstruir":    "FACTURAS_RECONSTRUIDAS_PERFIL1",
        "nit_customer":           "000000000",
        "email_customer":         "cliente@empresa.com",
        "telefono_customer":      "3000000000",
        "prefijo_remesa":         False,
    },
    "ut_perfil2": {
        "nombre":                 "Nombre del perfil 2",
        "nit_socio":              "0000000000",
        "nombre_socio":           "NOMBRE EMPRESA SOCIO 2 S.A.S",
        "email_from":             "facturacion@empresa2.com",
        "email_contact_supplier": "contacto@proveedor2.com",
        "carpeta":                "FACTURAS_GENERADAS_PERFIL2",
        "rndc_usuario":           "USUARIO2@0000",
        "rndc_password":          "contrasena456",
        "nit_ut":                 "000000000",
        "nombre_ut":              "NOMBRE DE LA UNION TEMPORAL",
        "carpeta_reconstruir":    "FACTURAS_RECONSTRUIDAS_PERFIL2",
        "nit_customer":           "000000000",
        "email_customer":         "cliente2@empresa.com",
        "telefono_customer":      "3000000000",
        "prefijo_remesa":         True,  # True agrega "0" al consecutivo al consultar RNDC
    },
}
