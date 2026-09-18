"""Prepara los datos del año siguiente a partir de los datos y el calendario (ya retocado) del año actual."""

from __future__ import annotations

import datetime as dt
import io
from pathlib import Path

from .datos import SEMANAS_ROTACION, ErrorDatos, abrir_excel, festivos_dict, lunes_de
from .excel_salida import FILA_FECHA, FILA_PRIMERA_PERSONA, nombre_hoja


def dict_siguiente(datos: dict, calendario: str | Path | bytes) -> dict:
    """Devuelve el diccionario de datos del año siguiente: nuevo año, festivos, semana de arranque
    de cada grupo, y quién hizo Nochebuena/Nochevieja (leído del calendario, con los retoques a mano)."""
    anio = int(datos["anio"])
    nuevo = anio + 1
    semanas = (lunes_de(dt.date(nuevo, 1, 1)) - lunes_de(dt.date(anio, 1, 1))).days // 7
    origen = io.BytesIO(calendario) if isinstance(calendario, (bytes, bytearray)) else calendario
    wb = abrir_excel(origen)

    grupos = []
    for g in datos["grupos"]:
        g = {**g, "personas": [dict(pe) for pe in g["personas"]]}
        g["semana_inicio"] = (int(g["semana_inicio"]) - 1 + semanas) % SEMANAS_ROTACION + 1
        for pe in g["personas"]:
            pe["mananas"] = False
        hoja = nombre_hoja(g["nombre"])
        if hoja in wb.sheetnames:
            ws = wb[hoja]
            cols = {}
            for c in ws[FILA_FECHA]:
                v = c.value.date() if isinstance(c.value, dt.datetime) else c.value
                if v in (dt.date(anio, 12, 24), dt.date(anio, 12, 31)):
                    cols[v.day] = c.column
            if len(cols) != 2:
                raise ErrorDatos(f"No encuentro el 24 y el 31 de diciembre en la hoja «{hoja}» del calendario")
            filas = {str(ws.cell(f, 2).value).strip(): f for f in range(FILA_PRIMERA_PERSONA, ws.max_row + 1)
                     if ws.cell(f, 2).value}
            for pe in g["personas"]:
                f = filas.get(str(pe.get("nombre") or "").strip())
                if f is None:
                    continue
                turno = lambda col: str(ws.cell(f, col).value or "").strip().upper()  # noqa: E731
                pe["nochebuena"] = turno(cols[24]) if turno(cols[24]) in ("M", "T", "N") else ""
                pe["nochevieja"] = turno(cols[31]) if turno(cols[31]) in ("M", "T", "N") else ""
        grupos.append(g)
    return {**datos, "anio": nuevo, "festivos": festivos_dict(nuevo), "grupos": grupos}
