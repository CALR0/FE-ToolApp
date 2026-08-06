"""
Ajustes globales de negocio de FE-Tool (NO credenciales — esos van en perfiles.py).

Este archivo SÍ se versiona (no está en .gitignore) para que los valores de negocio
queden documentados y fáciles de cambiar.
"""
from datetime import date

# ─────────────────────────────────────────────────────────────────────────────
# FOPAT (0,1%) — fecha de inicio de aplicación.
#
# El FOPAT solo aplica a manifiestos cuya FECHA DE EXPEDICIÓN sea EN O DESPUÉS de
# esta fecha. Para manifiestos expedidos ANTES, en el cumplido:
#   - NO se envía la etiqueta RETENCIONFOPAT (ni siquiera en 0).
#   - En su lugar el RNDC exige RETENCIONFUENTEMANIFIESTO (retención en la fuente),
#     con el valor que trae la consulta del manifiesto.
#
# Cambia esta fecha aquí si la normativa cambia. En la app se puede ajustar por
# sesión desde la barra lateral (⚙️ Ajustes); este valor es el predeterminado.
# ─────────────────────────────────────────────────────────────────────────────
FOPAT_FECHA_INICIO = date(2026, 4, 1)
