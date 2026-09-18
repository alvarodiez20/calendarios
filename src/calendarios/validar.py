"""Comprobación independiente de un calendario ya generado (no depende del solver)."""

from __future__ import annotations

import datetime as dt

from .datos import Parametros, Persona

TRABAJO = ("M", "T", "N")


def minutos(fila: list[str], p: Parametros) -> int:
    return sum(p.duracion[s] for s in fila if s in TRABAJO)


def validar(fechas: list[dt.date], turnos: list[list[str]], personas: list[Persona],
            p: Parametros, festivos: dict[dt.date, str]) -> list[str]:
    errores = []
    D = len(fechas)
    for d, f in enumerate(fechas):
        for s in TRABAJO:
            n = sum(t[d] == s for t in turnos)
            if n < p.minimos[s]:
                errores.append(f"{f:%d/%m}: solo {n} de {s} (mínimo {p.minimos[s]})")

    for k, fila in enumerate(turnos):
        nombre = personas[k].nombre
        h = minutos(fila, p)
        if abs(h - p.horas_anuales) > p.margen:
            errores.append(f"{nombre}: {h / 60:.2f} h fuera del margen")
        seguidos = 0
        for d in range(D):
            if d + 1 < D and fila[d] == "T" and fila[d + 1] == "M":
                errores.append(f"{nombre} {fechas[d]:%d/%m}: pasa de tarde a mañana")
            if fila[d] == "N" and d + 1 < D and fila[d + 1] != "N":
                for j in range(1, p.descansos_noche[fechas[d].weekday()] + 1):
                    if d + j < D and fila[d + j] in TRABAJO:
                        errores.append(f"{nombre} {fechas[d]:%d/%m}: no descansa tras la noche")
            seguidos = seguidos + 1 if fila[d] in TRABAJO else 0
            if seguidos > p.max_dias_seguidos:
                errores.append(f"{nombre} {fechas[d]:%d/%m}: más de {p.max_dias_seguidos} días seguidos")
            if seguidos == p.max_dias_seguidos:
                for j in range(1, p.libranzas_tras_max + 1):
                    if d + j < D and fila[d + j] in TRABAJO:
                        errores.append(f"{nombre} {fechas[d]:%d/%m}: sin libranzas tras {seguidos} días")
    return errores
