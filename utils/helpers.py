import sys as _sys
import os as _os


def resource_path(relative):
    """Devuelve la ruta absoluta al recurso, funciona en .py y en .exe (PyInstaller)."""
    base = getattr(_sys, '_MEIPASS', _os.path.dirname(_os.path.abspath(__file__)))
    # Sube un nivel desde utils/ para apuntar a la raíz del proyecto
    if not hasattr(_sys, '_MEIPASS'):
        base = _os.path.dirname(base)
    return _os.path.join(base, relative)
