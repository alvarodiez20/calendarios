import datetime as dt

import pytest

import json

from calendarios import api
from calendarios.datos import (ROTACION_3_4_C, Datos, Grupo, Parametros, Persona, a_minutos, dict_por_defecto,
                               domingo_de_pascua, festivos_por_defecto)
from calendarios.modelo import calcular_grupo
from calendarios.validar import validar


def _datos(personas: list[Persona]) -> tuple[Datos, Grupo]:
    p = Parametros(anio=2027, tiempo_max_s=30)
    festivos = {f: n for f, n, _ in festivos_por_defecto(2027)}
    g = Grupo(1, "3ª-4ª C", 18, 2, ROTACION_3_4_C, personas)
    return Datos(p, festivos, [g]), g


def _turno(r, k, mes, dia):
    return r.turnos[k][r.fechas.index(dt.date(2027, mes, dia))]


def test_rotacion_cubre_minimos():
    for par in (0, 1):
        for d in range(7):
            dia = [ROTACION_3_4_C[s][d] for s in range(par, 26, 2)]
            assert dia.count("M") >= 3 and dia.count("T") >= 3 and dia.count("N") >= 1


@pytest.mark.parametrize("valor,esperado", [("7:00", 420), ("11:22", 682), ("3:30", 210), (1715, 102900),
                                            (dt.time(11, 22), 682), ("3h 30min", 210), (3.5, 210)])
def test_a_minutos(valor, esperado):
    assert a_minutos(valor, "x") == esperado


def test_festivos_2027():
    assert domingo_de_pascua(2027) == dt.date(2027, 3, 28)
    fechas = {n: f for f, n, _ in festivos_por_defecto(2027)}
    assert fechas["Curpillos"] == dt.date(2027, 6, 4)
    assert fechas["Jueves Santo"] == dt.date(2027, 3, 25)


def test_calendario_cumple_todas_las_reglas_con_historia_de_navidad():
    # Año anterior: 0-4 Nochebuena, 5-10 Nochevieja, 11-12 las dos de mañana
    personas = []
    for i in range(13):
        nb = "T" if i < 5 else None
        nv = "N" if i == 5 else ("M" if 5 < i < 11 else None)
        if i >= 11:
            nb = nv = "M"
        personas.append(Persona(i + 1, f"P{i + 1}", nb, nv))
    datos, g = _datos(personas)
    r = calcular_grupo(datos, g)
    assert r.turnos, r.estado
    assert validar(r.fechas, r.turnos, personas, datos.parametros, datos.festivos) == []

    for k, pe in enumerate(personas):
        nb, nav, nv = _turno(r, k, 12, 24), _turno(r, k, 12, 25), _turno(r, k, 12, 31)
        if k in r.pareja_mananas:
            assert nb == nav == nv == "M"
            continue
        assert (nb in "MTN") != (nv in "MTN")  # exactamente una de las dos
        if nb in "MTN":
            assert nav == nb  # Navidad con el mismo turno que Nochebuena
        if pe.mananas_navidad_prev:
            assert _turno(r, k, 1, 6) in ("L", "F")  # libra Reyes
            assert k not in r.pareja_mananas
        elif pe.nochebuena_prev:
            assert nv in "MTN"
        elif pe.nochevieja_prev:
            assert nb in "MTN"
            assert _turno(r, k, 1, 1) == pe.nochevieja_prev  # Año Nuevo con el turno de Nochevieja
    assert len(r.pareja_mananas) == 2

    # Festivos repartidos lo más igualado posible
    trabajados = [sum(_turno(r, k, f.month, f.day) in "MTN" for f in datos.festivos) for k in range(13)]
    assert max(trabajados) - min(trabajados) <= 1


def test_descansos_tras_la_noche_segun_el_dia():
    personas = [Persona(i + 1, f"P{i + 1}") for i in range(13)]
    datos, g = _datos(personas)
    r = calcular_grupo(datos, g)
    descansos = datos.parametros.descansos_noche
    for fila in r.turnos:
        for d in range(len(fila) - 4):
            if fila[d] == "N" and fila[d + 1] != "N":
                R = descansos[r.fechas[d].weekday()]
                assert all(s in "LF" for s in fila[d + 1:d + 1 + R])
    # Noches de lunes-martes: miércoles y jueves L, y el viernes (M en la rotación) pasa a F
    assert descansos == [3, 3, 3, 3, 2, 2, 3]


def test_excel_de_datos_ida_y_vuelta():
    estado = dict_por_defecto(2027)
    estado["grupos"][1]["semana_inicio"] = 5
    estado["grupos"][0]["personas"][0].update(nombre="Ana", nochebuena="T", mananas=True)
    vuelta = json.loads(api.importar_excel(api.plantilla(json.dumps(estado))))
    assert vuelta == estado
    vacia = json.loads(api.importar_excel(api.plantilla(vacia=True)))
    assert all(c == "" for g in vacia["grupos"] for fila in g["rotacion"] for c in fila)
