"""Comprobación independiente de un calendario ya generado (no depende del solver)."""

from __future__ import annotations

import datetime as dt

from .datos import Parametros, Persona

TRABAJO = ("M", "T", "N")


def minutos(fila: list[str], p: Parametros) -> int:
    return sum(p.duracion[s] for s in fila if s in TRABAJO)


def bloques_libres(fila: list[str]) -> list[tuple[int, int]]:
    """Tramos [a, b) de días sin trabajar."""
    bloques, a = [], None
    for d, t in enumerate(fila):
        if t in TRABAJO:
            if a is not None:
                bloques.append((a, d))
            a = None
        elif a is None:
            a = d
    if a is not None:
        bloques.append((a, len(fila)))
    return bloques


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

            # Las F no se pegan al descanso de las noches: después de las noches van libranzas (L)
            if fila[d] == "N" and d + 1 < D and fila[d + 1] != "N":
                b = d + 1
                while b < D and fila[b] not in TRABAJO:
                    b += 1
                for i in range(d + 1, b):
                    if fila[i] == "F" and fechas[i] not in festivos:
                        errores.append(f"{nombre} {fechas[i]:%d/%m}: F pegada al descanso de las noches")

        # Los días libres van en bloques: ni libranzas sueltas ni bloques más largos de la cuenta
        for a, b in bloques_libres(fila):
            if a == 0 or b == D:
                continue  # el bloque se corta con el cambio de año: no se puede juzgar
            festivo_entero = all(fechas[i] in festivos for i in range(a, b))
            if b - a < p.min_libranzas_seguidas and not festivo_entero:
                cuantos = "un día suelto" if b - a == 1 else f"solo {b - a} días seguidos"
                errores.append(f"{nombre} {fechas[a]:%d/%m}: libra {cuantos} "
                               f"(el mínimo son {p.min_libranzas_seguidas})")
            if b - a > p.max_libranzas_seguidas and "F" in fila[a:b]:
                errores.append(f"{nombre} {fechas[a]:%d/%m}: {b - a} días libres seguidos "
                               f"(el máximo son {p.max_libranzas_seguidas})")
    return errores
