"""Uso desde el terminal (la web hace lo mismo en el navegador):

    uv run calendarios plantilla 2027 [--vacia]                        -> datos_2027.xlsx
    uv run calendarios generar datos_2027.xlsx                         -> calendario_2027.xlsx
    uv run calendarios siguiente datos_2027.xlsx calendario_2027.xlsx  -> datos_2028.xlsx
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import api
from .datos import ErrorDatos, hm


def _plantilla(args) -> int:
    ruta = Path(args.salida or f"datos_{args.anio}.xlsx")
    if ruta.exists() and not args.sobrescribir:
        print(f"Ya existe {ruta}. Usa --sobrescribir si quieres reemplazarlo.")
        return 1
    ruta.write_bytes(api.plantilla(anio=args.anio, vacia=args.vacia))
    print(f"Creado {ruta}")
    return 0


def _generar(args) -> int:
    estado = api.importar_excel(Path(args.datos).read_bytes())
    anio = json.loads(estado)["anio"]
    excel, resumen = api.generar(estado, lambda texto: print(texto, flush=True))
    for g in json.loads(resumen):
        if g["ok"]:
            print(f"· {g['grupo']}: ok en {g['segundos']} s · horas entre {hm(g['horas_min'])} y {hm(g['horas_max'])}")
        else:
            print(f"· {g['grupo']}: SIN SOLUCIÓN")
        for e in g["errores"]:
            print(f"  ⚠ {e}")
        for a in g["avisos"]:
            print(f"  ℹ {a}")
    if excel is None:
        return 1
    ruta = Path(args.salida or Path(args.datos).with_name(f"calendario_{anio}.xlsx"))
    ruta.write_bytes(excel)
    print(f"\nCreado {ruta}")
    return 0


def _siguiente(args) -> int:
    estado = api.importar_excel(Path(args.datos).read_bytes())
    nuevo = json.loads(api.siguiente(estado, Path(args.calendario).read_bytes()))
    ruta = Path(args.salida or Path(args.datos).with_name(f"datos_{nuevo['anio']}.xlsx"))
    ruta.write_bytes(api.plantilla(json.dumps(nuevo)))
    print(f"Creado {ruta}. Revisa los festivos del nuevo año.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="calendarios", description="Calendarios de turnos de la residencia")
    sub = ap.add_subparsers(dest="orden", required=True)

    a = sub.add_parser("plantilla", help="crea el Excel de datos para rellenar")
    a.add_argument("anio", type=int)
    a.add_argument("--vacia", action="store_true", help="sin la rotación del grupo 3ª-4ª C")
    a.add_argument("-o", "--salida")
    a.add_argument("--sobrescribir", action="store_true")
    a.set_defaults(func=_plantilla)

    a = sub.add_parser("generar", help="genera el calendario a partir del Excel de datos")
    a.add_argument("datos")
    a.add_argument("-o", "--salida")
    a.set_defaults(func=_generar)

    a = sub.add_parser("siguiente", help="prepara el Excel de datos del año siguiente")
    a.add_argument("datos")
    a.add_argument("calendario")
    a.add_argument("-o", "--salida")
    a.set_defaults(func=_siguiente)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except ErrorDatos as e:
        print(f"Error en los datos: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
