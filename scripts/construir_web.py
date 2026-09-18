"""Monta la web estática en _site/ (lo usa GitHub Actions para publicar en GitHub Pages).

    uv run python scripts/construir_web.py && python3 -m http.server -d _site 8000
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
from pathlib import Path

from calendarios.datos import dict_por_defecto, festivos_dict

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "_site"


def version() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return dt.datetime.now().strftime("%Y%m%d%H%M%S")


def main() -> None:
    v = version()
    shutil.rmtree(SALIDA, ignore_errors=True)
    shutil.copytree(RAIZ / "web", SALIDA)
    for nombre in ("index.html",):
        ruta = SALIDA / nombre
        ruta.write_text(ruta.read_text().replace("__VERSION__", v))

    # Código Python que ejecuta el navegador
    destino = SALIDA / "py" / "calendarios"
    destino.mkdir(parents=True)
    archivos = sorted(p.name for p in (RAIZ / "src" / "calendarios").glob("*.py") if p.name != "cli.py")
    for nombre in archivos:
        shutil.copy(RAIZ / "src" / "calendarios" / nombre, destino / nombre)
    (SALIDA / "py" / "archivos.json").write_text(json.dumps(archivos))

    # Datos iniciales (así la página se abre al instante, antes de que cargue Python)
    datos = SALIDA / "datos"
    datos.mkdir()
    anio = dt.date.today().year + 1
    (datos / "estado_inicial.json").write_text(json.dumps(dict_por_defecto(anio), ensure_ascii=False))
    festivos = {a: festivos_dict(a) for a in range(2024, 2051)}
    (datos / "festivos.json").write_text(json.dumps(festivos, ensure_ascii=False))
    (SALIDA / ".nojekyll").write_text("")
    print(f"Web montada en {SALIDA} (versión {v})")


if __name__ == "__main__":
    main()
