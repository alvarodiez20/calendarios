import datetime as dt

import pytest

import json

from calendarios import api
from calendarios.datos import (ROTACION_3_4_C, Datos, Grupo, Parametros, Persona, a_minutos, dict_por_defecto,
                               domingo_de_pascua, festivos_por_defecto)
from calendarios.modelo import calcular_grupo
from calendarios.validar import bloques_libres, validar


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
    assert descansos == [3, 3, 3, 3, 2, 2, 3]
    for fila in r.turnos:
        for d in range(len(fila) - 4):
            if fila[d] == "N" and fila[d + 1] != "N":
                R = descansos[r.fechas[d].weekday()]
                # Después de las noches van libranzas: nunca una F, ni en el descanso ni pegada a él
                assert all(s == "L" for s in fila[d + 1:d + 1 + R])
                assert fila[d + 1 + R] != "F" or r.fechas[d + 1 + R] in datos.festivos


def test_los_dias_libres_van_en_bloques():
    """Ni libranzas sueltas ni bloques más largos que los de la rotación: nada de «7 días y 1 libranza»."""
    personas = [Persona(i + 1, f"P{i + 1}") for i in range(13)]
    datos, g = _datos(personas)
    p = datos.parametros
    r = calcular_grupo(datos, g)
    assert r.turnos, r.estado
    for k, fila in enumerate(r.turnos):
        for a, b in bloques_libres(fila):
            if a == 0 or b == len(fila):
                continue  # bloque cortado por el cambio de año
            festivo = all(r.fechas[i] in datos.festivos for i in range(a, b))
            assert b - a >= p.min_libranzas_seguidas or festivo, (k, r.fechas[a], fila[a:b])
            assert b - a <= p.max_libranzas_seguidas or "F" not in fila[a:b], (k, r.fechas[a], fila[a:b])


def test_validar_detecta_libranzas_sueltas_y_f_pegada_a_las_noches():
    p = Parametros(anio=2027, minimos={"M": 0, "T": 0, "N": 0}, horas_anuales=0, margen=10 ** 9,
                   descansos_noche=[2] * 7)
    fechas = [dt.date(2027, 3, 1) + dt.timedelta(days=i) for i in range(12)]
    fila = list("NNLFMMMLMMMM")  # F pegada al descanso de la noche, y una libranza suelta
    errores = validar(fechas, [fila], [Persona(1, "Ana")], p, {})
    assert any("F pegada al descanso de las noches" in e for e in errores), errores
    assert any("día suelto" in e for e in errores), errores
    assert validar(fechas, [list("NNLLMMMLLMMM")], [Persona(1, "Ana")], p, {}) == []


def test_excel_de_datos_ida_y_vuelta():
    estado = dict_por_defecto(2027)
    estado["grupos"][1]["semana_inicio"] = 5
    estado["grupos"][0]["personas"][0].update(nombre="Ana", nochebuena="T", mananas=True)
    vuelta = json.loads(api.importar_excel(api.plantilla(json.dumps(estado))))
    assert vuelta == estado
    vacia = json.loads(api.importar_excel(api.plantilla(vacia=True)))
    assert all(c == "" for g in vacia["grupos"] for fila in g["rotacion"] for c in fila)
