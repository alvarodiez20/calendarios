"""Pruebas del generador de calendarios.

Las reglas del README se comprueban una a una sobre un calendario real (la rotación "3ª-4ª C" con
13 personas y la Navidad del año anterior ya en régimen normal). El cálculo se hace una sola vez.
"""

import datetime as dt
import json

import pytest

from calendarios import api
from calendarios.datos import (ROTACION_3_4_C, Datos, Grupo, Parametros, Persona, a_minutos,
                               dict_por_defecto, domingo_de_pascua, festivos_por_defecto)
from calendarios.modelo import DIAS_COLA, calcular_grupo, libranzas_obligadas
from calendarios.validar import bloques_libres, bloques_trabajo, minutos, validar

ANIO = 2027
TRABAJO = "MTN"

# Navidad del año anterior en régimen normal: 7 personas cada noche (3 M + 3 T + 1 N),
# la pareja de mañanas (P12 y P13) en las dos, y una persona (P11) que no hizo ninguna.
NAVIDAD_PREVIA = {1: ("M", ""), 2: ("T", ""), 3: ("T", ""), 4: ("T", ""), 5: ("N", ""),
                  6: ("", "M"), 7: ("", "T"), 8: ("", "T"), 9: ("", "T"), 10: ("", "N"),
                  11: ("", ""), 12: ("M", "M"), 13: ("M", "M")}


def _personas(previa: dict[int, tuple[str, str]] | None = None) -> list[Persona]:
    previa = previa or {}
    return [Persona(i, f"P{i}", previa.get(i, ("", ""))[0] or None, previa.get(i, ("", ""))[1] or None)
            for i in range(1, 14)]


def _datos(personas: list[Persona]) -> tuple[Datos, Grupo]:
    p = Parametros(anio=ANIO, tiempo_max_s=30)
    festivos = {f: n for f, n, _ in festivos_por_defecto(ANIO)}
    g = Grupo(1, "3ª-4ª C", 18, 2, ROTACION_3_4_C, personas)
    return Datos(p, festivos, [g]), g


@pytest.fixture(scope="module")
def calendario():
    personas = _personas(NAVIDAD_PREVIA)
    datos, g = _datos(personas)
    r = calcular_grupo(datos, g)
    assert r.turnos, f"no se ha podido calcular: {r.estado}"
    return datos, g, r


def _dia(r, k: int, mes: int, dia: int) -> str:
    return r.turnos[k][r.fechas.index(dt.date(ANIO, mes, dia))]


def _cuantos(r, i: int, turno: str) -> int:
    return sum(fila[i] == turno for fila in r.turnos)


# ---------------------------------------------------------------- sin solver

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


def test_excel_de_datos_ida_y_vuelta():
    estado = dict_por_defecto(ANIO)
    estado["grupos"][1]["semana_inicio"] = 5
    estado["grupos"][0]["personas"][0].update(nombre="Ana", nochebuena="T", mananas=True)
    vuelta = json.loads(api.importar_excel(api.plantilla(json.dumps(estado))))
    assert vuelta == estado
    vacia = json.loads(api.importar_excel(api.plantilla(vacia=True)))
    assert all(c == "" for g in vacia["grupos"] for fila in g["rotacion"] for c in fila)


def test_bloques_libres():
    assert bloques_libres(list("MMLLMFM")) == [(2, 4), (5, 6)]
    assert bloques_libres(list("LLMM")) == [(0, 2)]
    assert bloques_libres(list("MMLL")) == [(2, 4)]


def test_bloques_trabajo():
    assert bloques_trabajo(list("MMLLMFM")) == [(0, 2), (4, 5), (6, 7)]
    assert bloques_trabajo(list("LLMM")) == [(2, 4)]


def test_libranzas_obligadas():
    p = Parametros(anio=ANIO, descansos_noche=[3, 3, 3, 3, 2, 2, 3], max_dias_seguidos=7,
                   libranzas_tras_max=2)
    fechas = [dt.date(2027, 3, 1) + dt.timedelta(days=i) for i in range(14)]  # empieza en lunes
    # Noche el martes (índice 1): descansan los 3 días siguientes
    assert libranzas_obligadas(list("NNOOOMMMMMMMOO"), fechas, p) >= {2, 3, 4}
    # Noche el viernes (índice 4): solo 2 días
    obligadas = libranzas_obligadas(list("MMMMNOOMMMMMMM"), fechas, p)
    assert 5 in obligadas and 6 in obligadas and 7 not in obligadas
    # 7 días seguidos: las 2 libranzas siguientes son obligatorias
    assert libranzas_obligadas(list("MMMMMMMOOMMMMM"), fechas, p) >= {7, 8}


@pytest.mark.parametrize("fila,trozo", [
    ("NNLFMMMMMMM", "F pegada al descanso de las noches"),
    ("NNLLMMMLMMM", "día suelto"),
    ("NNLLMMMLLLFMM", "días libres seguidos"),  # el bloque solo se avisa si lo alarga una F
    ("NNLLMMMLFMFLLM", "trabajar 1 día suelto"),
    ("MMMMMMMMMMM", "días seguidos"),
    ("NNMMMMMMMMM", "no descansa tras la noche"),
    ("TMMMMMMLLMM", "de tarde a mañana"),
])
def test_validar_detecta_cada_fallo(fila, trozo):
    p = Parametros(anio=ANIO, minimos={"M": 0, "T": 0, "N": 0}, horas_anuales=0, margen=10 ** 9,
                   descansos_noche=[2] * 7, max_libranzas_seguidas=3)
    fechas = [dt.date(2027, 3, 1) + dt.timedelta(days=i) for i in range(len(fila))]
    errores = validar(fechas, [list(fila)], [Persona(1, "Ana")], p, {})
    assert any(trozo in e for e in errores), errores


def test_validar_acepta_una_fila_correcta():
    p = Parametros(anio=ANIO, minimos={"M": 0, "T": 0, "N": 0}, horas_anuales=0, margen=10 ** 9,
                   descansos_noche=[2] * 7)
    fila = list("NNLLMMMLLMMM")
    fechas = [dt.date(2027, 3, 1) + dt.timedelta(days=i) for i in range(len(fila))]
    assert validar(fechas, [fila], [Persona(1, "Ana")], p, {}) == []


# ---------------------------------------------------------------- reglas del calendario

def test_validar_no_encuentra_errores(calendario):
    datos, g, r = calendario
    assert validar(r.fechas, r.turnos, g.personas, datos.parametros, datos.festivos) == []


def test_minimos_diarios(calendario):
    datos, g, r = calendario
    p = datos.parametros
    for i in range(len(r.fechas)):
        for s in TRABAJO:
            assert _cuantos(r, i, s) >= p.minimos[s], (r.fechas[i], s)


def test_en_festivo_se_trabaja_justo_el_minimo(calendario):
    """En festivo no trabaja nadie por encima del mínimo: el resto libra."""
    datos, g, r = calendario
    p = datos.parametros
    assert r.avisos == [], r.avisos  # ningún festivo se ha tenido que pasar del mínimo
    for f in datos.festivos:
        i = r.fechas.index(f)
        for s in TRABAJO:
            assert _cuantos(r, i, s) == p.minimos[s], (f, s, [fila[i] for fila in r.turnos])


def test_horas_anuales_dentro_del_margen(calendario):
    datos, g, r = calendario
    p = datos.parametros
    for k, fila in enumerate(r.turnos):
        assert abs(minutos(fila, p) - p.horas_anuales) <= p.margen, g.personas[k].nombre


def test_no_se_pasa_de_tarde_a_manana(calendario):
    _, _, r = calendario
    for fila in r.turnos:
        assert not any(fila[d] == "T" and fila[d + 1] == "M" for d in range(len(fila) - 1))


def test_descansos_tras_la_noche_son_libranzas(calendario):
    """Tras la última noche se descansa lo que digan los parámetros, y siempre sale L, nunca F."""
    datos, _, r = calendario
    descansos = datos.parametros.descansos_noche
    assert descansos == [3, 3, 3, 3, 2, 2, 3]
    for fila in r.turnos:
        for d in range(len(fila) - 4):
            if fila[d] == "N" and fila[d + 1] != "N":
                R = descansos[r.fechas[d].weekday()]
                assert all(s == "L" for s in fila[d + 1:d + 1 + R]), (r.fechas[d], fila[d:d + R + 1])


def test_las_f_no_se_pegan_a_las_noches(calendario):
    """Ni dentro del descanso ni justo después (salvo que ese día sea festivo)."""
    datos, _, r = calendario
    for fila in r.turnos:
        for d in range(len(fila) - 5):
            if fila[d] == "N" and fila[d + 1] != "N":
                R = datos.parametros.descansos_noche[r.fechas[d].weekday()]
                assert "F" not in fila[d + 1:d + 1 + R]
                siguiente = fila[d + 1 + R]
                assert siguiente != "F" or r.fechas[d + 1 + R] in datos.festivos


def test_maximo_de_dias_seguidos(calendario):
    datos, _, r = calendario
    p = datos.parametros
    for fila in r.turnos:
        seguidos = 0
        for d, t in enumerate(fila):
            seguidos = seguidos + 1 if t in TRABAJO else 0
            assert seguidos <= p.max_dias_seguidos, r.fechas[d]
            if seguidos == p.max_dias_seguidos:
                libra = fila[d + 1:d + 1 + p.libranzas_tras_max]
                assert all(t not in TRABAJO for t in libra), (r.fechas[d], libra)


def test_los_dias_libres_van_en_bloques(calendario):
    """Ni libranzas sueltas ni más días libres seguidos de los que da la rotación."""
    datos, _, r = calendario
    p = datos.parametros
    for k, fila in enumerate(r.turnos):
        for a, b in bloques_libres(fila):
            if a == 0 or b == len(fila):
                continue  # bloque cortado por el cambio de año
            festivo = all(r.fechas[i] in datos.festivos for i in range(a, b))
            assert b - a >= p.min_libranzas_seguidas or festivo, (k, r.fechas[a], fila[a:b])
            assert b - a <= p.max_libranzas_seguidas or "F" not in fila[a:b], (k, r.fechas[a], fila[a:b])


def test_no_se_trabaja_un_dia_suelto(calendario):
    """Nadie libra, va un día a trabajar y vuelve a librar (salvo que ya lo ponga así la rotación)."""
    datos, _, r = calendario
    p = datos.parametros
    for k, fila in enumerate(r.turnos):
        for a, b in bloques_trabajo(fila):
            if a == 0 or b == len(fila) or b - a >= p.min_dias_trabajo_seguidos:
                continue
            base = r.base[k]
            assert base[a - 1] == "L" and base[b] == "L" and all(t != "L" for t in base[a:b]), \
                (k, r.fechas[a], fila[a - 2:b + 2], base[a - 2:b + 2])


def test_el_descanso_de_las_noches_no_se_corta_en_el_cambio_de_anio(calendario):
    """Diciembre se calcula con los primeros días de enero por delante (`r.cola`)."""
    datos, _, r = calendario
    p = datos.parametros
    assert DIAS_COLA >= max(p.descansos_noche) + 1
    for k, fila in enumerate(r.turnos):
        completa = fila + r.cola[k]
        for d in range(len(fila) - max(p.descansos_noche), len(fila)):
            if completa[d] == "N" and completa[d + 1] != "N":
                R = p.descansos_noche[r.fechas[d].weekday()]
                assert all(t not in TRABAJO for t in completa[d + 1:d + 1 + R]), (k, r.fechas[d])


def test_navidad(calendario):
    datos, g, r = calendario
    personas = g.personas
    assert len(r.pareja_mananas) == 2
    for k, pe in enumerate(personas):
        nb, nav, nv = _dia(r, k, 12, 24), _dia(r, k, 12, 25), _dia(r, k, 12, 31)
        if k in r.pareja_mananas:
            assert nb == nav == nv == "M"  # la pareja hace las dos de mañana
            assert not pe.mananas_navidad_prev  # nunca repite quien las hizo el año pasado
            continue
        assert not (nb in TRABAJO and nv in TRABAJO)  # nadie trabaja Nochebuena y Nochevieja
        assert (nav in TRABAJO) == (nb in TRABAJO)  # el 25, el mismo turno que el 24
        if nb in TRABAJO:
            assert nav == nb
        if pe.mananas_navidad_prev:
            assert _dia(r, k, 1, 6) not in TRABAJO  # libra Reyes
        elif pe.nochebuena_prev:
            assert nv in TRABAJO  # alternancia: el que hizo Nochebuena hace Nochevieja
        elif pe.nochevieja_prev:
            assert nb in TRABAJO
        if pe.nochevieja_prev:
            assert _dia(r, k, 1, 1) == pe.nochevieja_prev  # Año Nuevo, el turno de la Nochevieja anterior


def test_festivos_repartidos(calendario):
    datos, _, r = calendario
    trabajados = [sum(_dia(r, k, f.month, f.day) in TRABAJO for f in datos.festivos)
                  for k in range(len(r.turnos))]
    assert max(trabajados) - min(trabajados) <= 1, trabajados


def test_se_hacen_pocos_cambios_sobre_la_rotacion(calendario):
    """El calendario sale de la rotación: los cambios de turno de verdad son una minoría."""
    _, _, r = calendario
    dias = len(r.fechas) * len(r.turnos)
    cambios = sum(t != b and not (t in "LF" and b == "L")
                  for fila, base in zip(r.turnos, r.base) for t, b in zip(fila, base))
    de_turno = sum(t in TRABAJO and b in TRABAJO and t != b
                   for fila, base in zip(r.turnos, r.base) for t, b in zip(fila, base))
    assert cambios / dias < 0.10, cambios / dias
    assert de_turno / dias < 0.01, de_turno / dias


def test_sin_datos_de_navidad_se_avisa_y_se_calcula():
    datos, g = _datos(_personas())
    r = calcular_grupo(datos, g)
    assert r.turnos, r.estado
    assert any("No hay datos de la Navidad" in a for a in r.avisos), r.avisos
    assert validar(r.fechas, r.turnos, g.personas, datos.parametros, datos.festivos) == []
    assert len(r.pareja_mananas) == 2
