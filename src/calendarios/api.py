"""Funciones de alto nivel que usan la web (vía Pyodide) y el terminal. Todo entra y sale como JSON o bytes."""

from __future__ import annotations

import io
import json
import time
from typing import Callable

from .datos import ErrorDatos, datos_desde_dict, dict_desde_excel, dict_por_defecto, festivos_dict
from .excel_salida import escribir_calendario
from .modelo import calcular_grupo, diagnosticar
from .plantilla import escribir_datos
from .siguiente import dict_siguiente
from .validar import minutos, validar


def _bytes(contenido) -> bytes:
    """Acepta bytes o un Uint8Array de JavaScript (Pyodide)."""
    return contenido.to_bytes() if hasattr(contenido, "to_bytes") else bytes(contenido)


def estado_inicial(anio: int) -> str:
    return json.dumps(dict_por_defecto(anio))


def festivos(anio: int) -> str:
    return json.dumps(festivos_dict(anio))


def plantilla(estado_json: str | None = None, anio: int = 2027, vacia: bool = False) -> bytes:
    """Excel de datos: vacío (solo la estructura) o con los datos actuales."""
    datos = json.loads(estado_json) if estado_json else None
    if vacia:
        datos = dict_por_defecto(int(datos["anio"]) if datos else anio, vacia=True)
    buf = io.BytesIO()
    escribir_datos(buf, datos, anio=anio)
    return buf.getvalue()


def importar_excel(contenido: bytes) -> str:
    return json.dumps(dict_desde_excel(_bytes(contenido)))


def siguiente(estado_json: str, calendario: bytes) -> str:
    return json.dumps(dict_siguiente(json.loads(estado_json), _bytes(calendario)))


def generar(estado_json: str, progreso: Callable[[str], None] | None = None) -> tuple[bytes | None, str]:
    """Calcula todos los grupos. Devuelve (excel del calendario o None, resumen JSON)."""
    aviso = progreso or (lambda _texto: None)
    datos = datos_desde_dict(json.loads(estado_json))
    p = datos.parametros
    resumen, resultados = [], []
    for i, g in enumerate(datos.grupos, start=1):
        aviso(f"Calculando {g.nombre} ({i} de {len(datos.grupos)})…")
        t = time.time()
        r = calcular_grupo(datos, g)
        info = {"grupo": g.nombre, "ok": bool(r.turnos), "segundos": round(time.time() - t, 1),
                "avisos": list(r.avisos), "errores": []}
        if r.turnos:
            horas = [minutos(f, p) for f in r.turnos]
            info.update(horas_min=min(horas), horas_max=max(horas),
                        errores=validar(r.fechas, r.turnos, g.personas, p, datos.festivos))
            resultados.append(r)
        else:
            info["errores"] = ["No se ha podido calcular el calendario de este grupo. " + diagnosticar(datos, g)]
        resumen.append(info)
    if not resultados:
        return None, json.dumps(resumen)
    aviso("Preparando el Excel…")
    buf = io.BytesIO()
    escribir_calendario(buf, datos, resultados)
    return buf.getvalue(), json.dumps(resumen)


__all__ = ["ErrorDatos", "estado_inicial", "festivos", "plantilla", "importar_excel", "siguiente", "generar"]
