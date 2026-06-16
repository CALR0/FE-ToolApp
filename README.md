# FE-Tool — Facturación Electrónica Colombia (DIAN)

Aplicación de escritorio para la gestión de facturación electrónica UBL 2.1 bajo la normativa DIAN colombiana.

## ¿Qué hace?

- Genera XMLs de facturas electrónicas compatibles con DIAN UBL 2.1
- Consulta y autocompleta radicados desde el RNDC (Ministerio de Transporte)
- Sube facturas al portal RNDC
- Genera facturas en lote desde un archivo Excel
- Edita campos de XMLs existentes (remesas, radicados, valores, fechas)
- Reconstruye XMLs aplicando transformaciones DIAN según el perfil activo
- Extrae datos de facturas en PDF y exporta a Excel

## Estructura del proyecto

```
FE-ToolApp/
├── main.py               # Punto de entrada
├── config/               # Perfiles de empresa y constantes de tema visual
├── core/                 # Lógica de negocio: generación y transformación de XML
├── services/             # Integración con el RNDC (WebService SOAP)
├── ui/                   # Módulos de interfaz gráfica (tkinter)
└── utils/                # Utilidades (compatibilidad con PyInstaller)
```

## Requisitos

```
Python 3.10+
requests
pandas
openpyxl
pdfplumber
```

```bash
pip install requests pandas openpyxl pdfplumber
```

## Uso

```bash
python main.py
```

## Distribución

Compilable como ejecutable Windows con PyInstaller:

```bash
pyinstaller --onefile --windowed --icon=icono.ico main.py
```

Todos los derechos reservados © 2026