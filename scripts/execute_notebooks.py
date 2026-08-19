"""Ejecuta y guarda todos los notebooks de reproducción en orden."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "notebooks"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout",
        type=int,
        default=900,
        help="Tiempo máximo por celda, en segundos.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = sorted(NOTEBOOKS.glob("[0-9][0-9]_*.ipynb"))
    if not paths:
        raise SystemExit("No se encontraron notebooks para ejecutar.")

    for path in paths:
        print(f"Ejecutando: {path.relative_to(ROOT)}", flush=True)
        document = nbformat.read(path, as_version=4)
        client = NotebookClient(
            document,
            timeout=args.timeout,
            kernel_name="python3",
            resources={"metadata": {"path": str(ROOT)}},
            allow_errors=False,
        )
        client.execute()
        nbformat.write(document, path)
        print(f"Validado: {path.relative_to(ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
