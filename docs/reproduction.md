# Manual de reproducción local

## Requisitos

- Python 3.11 o posterior.
- Dependencias del extra `modeling`.
- Datos raw ya descargados en `data/raw/`.
- `.env` local para nuevas descargas; nunca se necesita mostrar sus valores.

Desde la raíz del repositorio:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[modeling,dev,deliverables]"
$env:PYTHONPATH = "src"
python -m morosidad_bancaria run-all-local
```

`run-all-local` no accede a internet. Reconstruye las capas interim y processed
desde los archivos raw locales y ejecuta, en orden:

1. auditorías CMF, calendario de publicación y Banco Central;
2. dataset point-in-time y feature set;
3. benchmarks y modelos ML;
4. parsimonia, explicabilidad y robustez por horizonte;
5. alerta de estrés;
6. cierre técnico, model card y manifiesto SHA-256.

La selección anidada de la alerta es la etapa más lenta. En el entorno de
referencia, la ejecución completa puede tardar varios minutos en CPU.

## Ejecución parcial

El cierre técnico puede regenerarse sin reentrenar modelos cuando sus tablas ya
existen:

```powershell
python -m morosidad_bancaria close-technical
```

Las pruebas se ejecutan por separado:

```powershell
python -m unittest discover -s tests -v
```

## Artefactos del hito 10

El análisis reproducible termina en las tablas, figuras y documentos técnicos.
El informe editable puede regenerarse con:

```powershell
python scripts/build_final_report.py
```

El script genera `deliverables/informe_final_morosidad_bancaria.docx`. La
versión PDF se obtiene exportando ese DOCX con Microsoft Word o LibreOffice; la
versión validada ya se incluye en `deliverables/`. La presentación final también
se entrega ya construida porque su composición visual no interviene en los
cálculos ni en la selección de modelos.

## Verificación

Al finalizar, revise:

- `data/metadata/technical_acceptance_v001.json`;
- `data/metadata/reproduction_manifest_v001.json`;
- `docs/model_card_v1.md`;
- `docs/technical_closure_v1.md`.
- `deliverables/informe_final_morosidad_bancaria.pdf`;
- `deliverables/presentacion_final_morosidad_bancaria.pptx`.

El manifiesto excluye `.env`. Los datos macro corresponden al vintage vigente
en la descarga, limitación que puede impedir reproducir valores idénticos si se
vuelven a descargar después de revisiones oficiales. La reproducción exacta
requiere conservar los archivos raw cuyos hashes figuran en el manifiesto.
