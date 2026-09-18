"use strict";

// ============================================================ utilidades
const $ = (sel, raiz = document) => raiz.querySelector(sel);
const DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const DIAS_CORTOS = ["L", "M", "X", "J", "V", "S", "D"];
const NOMBRE_TURNO = { M: "Mañana", T: "Tarde", N: "Noche", L: "Libre" };
const PIN = "1010";
const CLAVE_ESTADO = "calendarios:estado:v1";
const SEMANAS = 26;

function el(etiqueta, atributos = {}, ...hijos) {
  const e = document.createElement(etiqueta);
  for (const [k, v] of Object.entries(atributos)) {
    if (v === false || v == null) continue;
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "class") e.className = v;
    else if (k === "value") e.value = v;
    else if (k === "checked") e.checked = !!v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const h of hijos.flat()) if (h != null && h !== false) e.append(h instanceof Node ? h : String(h));
  return e;
}

const hm = (min) => `${Math.floor(min / 60)}:${String(Math.round(min % 60)).padStart(2, "0")}`;
function aMinutos(texto) {
  const t = String(texto).trim().replace(",", ".");
  let m = t.match(/^(\d+)\s*[:h]\s*(\d{1,2})?\s*(min)?$/i);
  if (m) return Number(m[1]) * 60 + Number(m[2] || 0);
  if (/^\d+(\.\d+)?$/.test(t)) return Math.round(Number(t) * 60);
  return null;
}
function lunesDe(fecha) {
  const d = new Date(fecha);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return d;
}
const fechaCorta = (d) => d.toLocaleDateString("es-ES", { day: "numeric", month: "long", year: "numeric" });
const diaSemana = (iso) => (iso ? DIAS[(new Date(iso + "T12:00").getDay() + 6) % 7].toLowerCase() : "");

function aviso(texto, error = false, ms = 4000) {
  const a = $("#aviso");
  a.textContent = texto;
  a.className = "aviso" + (error ? " error" : "");
  a.hidden = false;
  clearTimeout(aviso.t);
  aviso.t = setTimeout(() => (a.hidden = true), error ? ms * 2 : ms);
}

function descargar(bytes, nombre) {
  const blob = new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  const a = el("a", { href: URL.createObjectURL(blob), download: nombre });
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

// ============================================================ motor de cálculo (Python en un worker)
const motor = {
  worker: new Worker(`worker.js?v=${window.VERSION}`),
  listo: false,
  pendientes: new Map(),
  siguienteId: 1,
};
motor.worker.onmessage = (e) => {
  const m = e.data;
  if (m.tipo === "progreso") {
    if (m.texto) $("#cargando-texto").textContent = m.texto;
    if (!motor.listo && m.texto) pintarEstadoMotor(`⏳ ${m.texto} (solo tarda la primera vez)`);
  } else if (m.tipo === "listo") {
    motor.listo = true;
    pintarEstadoMotor("✅ Todo listo", "listo");
  } else if (m.tipo === "fallo") {
    pintarEstadoMotor("❌ No se ha podido preparar la herramienta. Revisa la conexión a internet y recarga la página.", "error");
    for (const { rechazar } of motor.pendientes.values()) rechazar(m.error);
  } else if (m.tipo === "respuesta") {
    const p = motor.pendientes.get(m.id);
    motor.pendientes.delete(m.id);
    if (m.ok) p.resolver(m.res); else p.rechazar(m.error);
  }
};
function pintarEstadoMotor(texto, clase = "") {
  const e = $("#estado-motor");
  e.textContent = texto;
  e.className = "estado-motor " + clase;
}
function llamar(orden, args = {}) {
  return new Promise((resolver, rechazar) => {
    const id = motor.siguienteId++;
    motor.pendientes.set(id, { resolver, rechazar });
    motor.worker.postMessage({ id, orden, args });
  });
}

// Muestra la capa "un momento…" mientras dura la tarea, y los errores de forma comprensible
async function conEspera(texto, tarea) {
  $("#cargando-texto").textContent = motor.listo ? texto : "Preparando la herramienta (solo la primera vez tarda un poco)…";
  $("#cargando").hidden = false;
  try {
    return await tarea();
  } catch (err) {
    console.error(err);
    const msg = err?.datos ? err.mensaje : `Ha habido un error inesperado: ${err?.mensaje || err}`;
    aviso(msg, true);
    return null;
  } finally {
    $("#cargando").hidden = true;
  }
}

// ============================================================ estado
let estado = null;
let festivosPorAnio = {};
let grupoActivo = 0;
let pincel = "M";

function guardar() {
  try { localStorage.setItem(CLAVE_ESTADO, JSON.stringify(estado)); } catch { /* sin almacenamiento */ }
}
async function cargarEstado() {
  const v = window.VERSION;
  const [inicial, festivos] = await Promise.all([
    fetch(`datos/estado_inicial.json?v=${v}`).then((r) => r.json()),
    fetch(`datos/festivos.json?v=${v}`).then((r) => r.json()),
  ]);
  festivosPorAnio = festivos;
  let guardado = null;
  try { guardado = JSON.parse(localStorage.getItem(CLAVE_ESTADO)); } catch { /* nada */ }
  estado = guardado?.grupos ? guardado : structuredClone(inicial);
  // Un estado guardado con una versión anterior puede no tener todos los ajustes: se completan.
  estado.parametros = { ...structuredClone(inicial.parametros), ...(estado.parametros || {}) };
  cargarEstado.inicial = inicial;
}

const g = () => estado.grupos[grupoActivo];
const rotacionVacia = (grupo) => grupo.rotacion.every((f) => f.every((c) => !c));
const rotacionCompleta = (grupo) => grupo.rotacion.every((f) => f.every((c) => "MTNL".includes(c) && c));

// ============================================================ PIN
function iniciarPin() {
  if (sessionStorage.getItem("calendarios:pin") === "ok") return entrar();
  let escrito = "";
  const puntos = document.querySelectorAll(".pin-puntos span");
  const teclado = $("#pin-teclado");
  const pintar = () => puntos.forEach((p, i) => p.classList.toggle("lleno", i < escrito.length));
  const pulsar = (tecla) => {
    $("#pin-error").hidden = true;
    if (tecla === "⌫") escrito = escrito.slice(0, -1);
    else if (escrito.length < 4) escrito += tecla;
    pintar();
    if (escrito.length === 4) {
      if (escrito === PIN) {
        sessionStorage.setItem("calendarios:pin", "ok");
        setTimeout(entrar, 150);
      } else {
        setTimeout(() => { escrito = ""; pintar(); $("#pin-error").hidden = false; }, 250);
      }
    }
  };
  for (const t of ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "⌫"]) {
    teclado.append(el("button", { type: "button", class: t ? "" : "vacio", onclick: () => t && pulsar(t),
      "aria-label": t === "⌫" ? "Borrar" : t }, t));
  }
  document.addEventListener("keydown", function teclas(e) {
    if ($("#pantalla-pin").hidden) return document.removeEventListener("keydown", teclas);
    if (/^\d$/.test(e.key)) pulsar(e.key);
    if (e.key === "Backspace") pulsar("⌫");
  });
}

async function entrar() {
  $("#pantalla-pin").hidden = true;
  $("#app").hidden = false;
  await cargarEstado();
  const primero = estado.grupos.findIndex((x) => !rotacionVacia(x));
  grupoActivo = primero >= 0 ? primero : 0;
  pintarTodo();
  if (!motor.listo && !$("#estado-motor").textContent) pintarEstadoMotor("⏳ Preparando la herramienta… (solo tarda la primera vez)");
}

// ============================================================ pintar
function pintarTodo() {
  $("#anio").textContent = estado.anio;
  document.querySelectorAll(".anio-txt").forEach((e) => (e.textContent = estado.anio));
  document.querySelectorAll(".anio-sig").forEach((e) => (e.textContent = estado.anio + 1));
  $("#festivos-anio").textContent = estado.anio;
  pintarPestanas();
  pintarGrupo();
  pintarFestivos();
  pintarParametros();
}

function pintarPestanas() {
  const cont = $("#pestanas");
  cont.replaceChildren();
  estado.grupos.forEach((grupo, i) => {
    const marca = rotacionVacia(grupo) ? "vacío" : rotacionCompleta(grupo) ? "✓" : "a medias";
    cont.append(el("button", {
      type: "button", role: "tab", "aria-selected": i === grupoActivo ? "true" : "false",
      onclick: () => { grupoActivo = i; pintarPestanas(); pintarGrupo(); },
    }, grupo.nombre || `Grupo ${i + 1}`, " ", el("span", { class: "marca" }, `(${marca})`)));
  });
}

function pintarGrupo() {
  const grupo = g();
  const cont = $("#grupo");
  const lunes = lunesDe(new Date(estado.anio, 0, 1));
  cont.replaceChildren(
    el("div", { class: "fila-campos" },
      el("label", { class: "campo" }, el("span", {}, "Nombre del grupo"),
        el("input", { type: "text", value: grupo.nombre, oninput: (e) => { grupo.nombre = e.target.value; guardar(); pintarPestanas(); } })),
      el("div", { class: "campo" }, el("span", {}, "Semana de arranque"),
        el("div", { class: "contador" },
          el("button", { type: "button", "aria-label": "Una semana menos", onclick: () => cambiarSemana(-1) }, "−"),
          el("strong", { id: "semana-inicio" }, grupo.semana_inicio),
          el("button", { type: "button", "aria-label": "Una semana más", onclick: () => cambiarSemana(1) }, "+")),
        el("small", {}, `Semana de la rotación (1 a 26) en la que está la persona 1 la semana del lunes ${fechaCorta(lunes)}. Sale marcada en azul.`)),
    ),
    el("h3", {}, "Rotación de 26 semanas"),
    el("p", { class: "ayuda" }, "Elige una letra y pulsa las casillas para pintarlas (puedes arrastrar). También puedes escribir M, T, N o L con el teclado y moverte con las flechas."),
    pintarPaleta(),
    el("div", { class: "rotacion-envoltura" }, pintarRotacion()),
    el("div", { class: "botones", style: "margin-top:12px" },
      el("button", { type: "button", class: "boton pequeno secundario", onclick: (e) => vaciarRotacion(e) }, "🗑 Vaciar la rotación")),
    el("div", { class: "comprobacion", id: "comprobacion" }),
    el("h3", {}, "Personas"),
    el("p", { class: "ayuda" }, `En orden: la persona 1 empieza en la semana de arranque, la 2 va ${grupo.salto} semanas por delante, y así.
      Apunta qué turno hizo cada una en Nochebuena y Nochevieja de ${estado.anio - 1}, y marca las 2 que harán las mañanas de Navidad en ${estado.anio} (si no marcas a nadie, las elige el programa).`),
    el("div", { class: "tabla-envoltura" }, pintarPersonas()),
  );
  pintarComprobacion();
}

function cambiarSemana(delta) {
  const grupo = g();
  grupo.semana_inicio = ((grupo.semana_inicio - 1 + delta + SEMANAS) % SEMANAS) + 1;
  guardar();
  $("#semana-inicio").textContent = grupo.semana_inicio;
  document.querySelectorAll(".rotacion tr[data-semana]").forEach((tr) =>
    tr.classList.toggle("inicio", Number(tr.dataset.semana) === grupo.semana_inicio));
}

function pintarPaleta() {
  const cont = el("div", { class: "paleta", role: "toolbar", "aria-label": "Letra para pintar" });
  const actualizar = () => cont.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.letra === pincel));
  for (const letra of ["M", "T", "N", "L"]) {
    cont.append(el("button", { type: "button", class: `c-${letra}`, "data-letra": letra, title: NOMBRE_TURNO[letra],
      onclick: () => { pincel = letra; actualizar(); } }, letra));
  }
  cont.append(el("button", { type: "button", class: "borrar", "data-letra": "", onclick: () => { pincel = ""; actualizar(); } }, "Borrar"));
  actualizar();
  return cont;
}

let pintando = false;
document.addEventListener("pointerup", () => (pintando = false));

function pintarRotacion() {
  const grupo = g();
  const tabla = el("table", { class: "rotacion" });
  tabla.append(el("tr", {}, el("th"), ...DIAS.map((d) => el("th", {}, d.slice(0, 3)))));
  for (let s = 0; s < SEMANAS; s++) {
    const tr = el("tr", { "data-semana": s + 1, class: s + 1 === grupo.semana_inicio ? "inicio" : "" },
      el("td", { class: "semana" }, `Semana ${s + 1}`));
    for (let d = 0; d < 7; d++) {
      const td = el("td", { class: "celda", tabindex: 0, "data-s": s, "data-d": d, "aria-label": `Semana ${s + 1}, ${DIAS[d]}` });
      pintarCelda(td, grupo.rotacion[s][d]);
      td.addEventListener("pointerdown", (e) => { e.preventDefault(); td.focus(); pintando = true; ponerLetra(td, pincel); });
      td.addEventListener("pointerenter", () => pintando && ponerLetra(td, pincel));
      td.addEventListener("keydown", (e) => teclaCelda(e, td));
      tr.append(td);
    }
    tabla.append(tr);
  }
  return tabla;
}

function pintarCelda(td, letra) {
  td.textContent = letra || "";
  td.className = "celda" + (letra ? ` c-${letra}` : "");
}

function ponerLetra(td, letra) {
  const grupo = g();
  const s = Number(td.dataset.s), d = Number(td.dataset.d);
  if (grupo.rotacion[s][d] === letra) return;
  grupo.rotacion[s][d] = letra;
  pintarCelda(td, letra);
  guardar();
  pintarComprobacion();
  pintarPestanas();
}

function teclaCelda(e, td) {
  const s = Number(td.dataset.s), d = Number(td.dataset.d);
  const mover = (ds, dd) => {
    const destino = $(`.rotacion td[data-s="${(s + ds + SEMANAS) % SEMANAS}"][data-d="${(d + dd + 7) % 7}"]`);
    destino?.focus();
  };
  const k = e.key.toUpperCase();
  if ("MTNL".includes(k) && k.length === 1) { ponerLetra(td, k); d === 6 ? mover(1, -6) : mover(0, 1); }
  else if (e.key === "Backspace" || e.key === "Delete") ponerLetra(td, "");
  else if (e.key === "ArrowRight") mover(0, 1);
  else if (e.key === "ArrowLeft") mover(0, -1);
  else if (e.key === "ArrowDown" || e.key === "Enter") mover(1, 0);
  else if (e.key === "ArrowUp") mover(-1, 0);
  else return;
  e.preventDefault();
}

function vaciarRotacion(e) {
  const b = e.currentTarget;
  if (b.dataset.confirmar !== "1") {
    b.dataset.confirmar = "1";
    b.textContent = "⚠️ Pulsa otra vez para vaciarla";
    setTimeout(() => { b.dataset.confirmar = ""; b.textContent = "🗑 Vaciar la rotación"; }, 4000);
    return;
  }
  g().rotacion = Array.from({ length: SEMANAS }, () => Array(7).fill(""));
  guardar();
  pintarPestanas();
  pintarGrupo();
}

// Cobertura y horas en vivo: para cada semana y día, cuántas personas hay de cada turno
function pintarComprobacion() {
  const grupo = g();
  const cont = $("#comprobacion");
  cont.replaceChildren();
  if (rotacionVacia(grupo)) {
    cont.append(el("div", { class: "linea info" }, "Este grupo no tiene rotación todavía, así que no se calculará."));
    return;
  }
  const vacias = grupo.rotacion.flat().filter((c) => !c).length;
  if (vacias) cont.append(el("div", { class: "linea mal" }, `Faltan ${vacias} casillas por rellenar.`));

  const p = estado.parametros;
  const n = grupo.personas.filter((x) => x.nombre.trim()).length || 13;
  const faltas = new Map();
  for (let w = 0; w < SEMANAS; w++) {
    for (let d = 0; d < 7; d++) {
      const cuenta = { M: 0, T: 0, N: 0 };
      for (let k = 0; k < n; k++) {
        const c = grupo.rotacion[(w + grupo.salto * k) % SEMANAS][d];
        if (c in cuenta) cuenta[c]++;
      }
      for (const t of ["M", "T", "N"]) {
        if (cuenta[t] < p.minimos[t]) faltas.set(`${d}${t}`, `${DIAS[d]}: faltan ${NOMBRE_TURNO[t].toLowerCase()}s`);
      }
    }
  }
  if (faltas.size) {
    cont.append(el("div", { class: "linea mal" }, `No se llega a los mínimos algunas semanas. ${[...new Set(faltas.values())].join(" · ")}.`));
  } else if (!vacias) {
    cont.append(el("div", { class: "linea ok" }, `✓ Todos los días se llega a los mínimos (${p.minimos.M} de mañana, ${p.minimos.T} de tarde, ${p.minimos.N} de noche).`));
  }
  const celdas = grupo.rotacion.flat();
  const min26 = celdas.reduce((acc, c) => acc + (p.duracion[c] || 0), 0);
  const anual = min26 * 2 + min26 / 182;
  const sobra = anual - p.horas_anuales;
  if (!vacias) {
    cont.append(el("div", { class: "linea info" },
      `Con esta rotación cada persona haría unas ${hm(anual)} h al año. ` +
      (sobra > 0 ? `Sobran unas ${hm(sobra)} h, que se quitarán como unos ${Math.round(sobra / p.duracion.M)} días F.`
                 : `Faltan unas ${hm(-sobra)} h para llegar a ${hm(p.horas_anuales)}: el programa no podrá cuadrar las horas.`)));
  }
}

function pintarPersonas() {
  const grupo = g();
  const anio = estado.anio;
  const tabla = el("table", { class: "personas" },
    el("tr", {}, el("th", {}, "Nº"), el("th", {}, "Nombre"), el("th", {}, `Nochebuena ${anio - 1}`),
      el("th", {}, `Nochevieja ${anio - 1}`), el("th", {}, `Mañanas de Navidad ${anio}`), el("th", {}, `Qué le toca en ${anio}`)));
  const selector = (pe, campo) => el("select", {
    "aria-label": campo, onchange: (e) => { pe[campo] = e.target.value; guardar(); pintarPersonasToca(); } },
  ...[["", "—"], ["M", "Mañana"], ["T", "Tarde"], ["N", "Noche"]].map(([v, t]) =>
    el("option", { value: v, ...(pe[campo] === v ? { selected: true } : {}) }, t)));
  grupo.personas.forEach((pe, i) => {
    tabla.append(el("tr", {},
      el("td", { class: "nro" }, i + 1),
      el("td", {}, el("input", { type: "text", value: pe.nombre, "aria-label": `Nombre de la persona ${i + 1}`,
        oninput: (e) => { pe.nombre = e.target.value; guardar(); } })),
      el("td", {}, selector(pe, "nochebuena")),
      el("td", {}, selector(pe, "nochevieja")),
      el("td", {}, el("input", { type: "checkbox", checked: pe.mananas, "aria-label": "Mañanas de Navidad",
        onchange: (e) => {
          const marcadas = grupo.personas.filter((x) => x.mananas).length;
          if (e.target.checked && marcadas >= 2) { e.target.checked = false; aviso("Solo se pueden marcar 2 personas por grupo.", true); return; }
          pe.mananas = e.target.checked; guardar(); pintarPersonasToca();
        } })),
      el("td", { class: "toca", "data-i": i }),
    ));
  });
  queueMicrotask(pintarPersonasToca);
  return tabla;
}

function pintarPersonasToca() {
  g().personas.forEach((pe, i) => {
    const td = $(`.personas td.toca[data-i="${i}"]`);
    if (!td) return;
    let texto = "Lo decide el programa";
    if (pe.nochebuena === "M" && pe.nochevieja === "M") texto = "Libra Reyes · fuera de la alternancia";
    else if (pe.mananas) texto = "24 y 31 de mañana";
    else if (pe.nochebuena && !pe.nochevieja) texto = "Nochevieja";
    else if (pe.nochevieja && !pe.nochebuena) texto = "Nochebuena";
    else if (pe.nochebuena && pe.nochevieja) texto = "⚠️ Revisar: hizo las dos";
    td.textContent = texto;
  });
}

function pintarFestivos() {
  const cont = $("#festivos");
  cont.replaceChildren();
  estado.festivos.forEach((f, i) => {
    const dia = el("span", { class: "dia" }, diaSemana(f.fecha));
    cont.append(el("div", { class: "festivo" },
      el("input", { type: "date", value: f.fecha, "aria-label": "Fecha", min: `${estado.anio}-01-01`, max: `${estado.anio}-12-31`,
        onchange: (e) => { f.fecha = e.target.value; dia.textContent = diaSemana(f.fecha); guardar(); } }),
      dia,
      el("input", { type: "text", value: f.nombre, "aria-label": "Nombre del festivo", oninput: (e) => { f.nombre = e.target.value; guardar(); } }),
      el("button", { type: "button", class: "quitar", title: "Quitar este festivo", "aria-label": "Quitar",
        onclick: () => { estado.festivos.splice(i, 1); guardar(); pintarFestivos(); } }, "✕")));
  });
}

function pintarParametros() {
  const p = estado.parametros;
  const cont = $("#parametros");
  cont.replaceChildren();
  const campoHoras = (texto, ayuda, leer, escribir) => el("label", {}, texto,
    el("input", { type: "text", value: hm(leer()), inputmode: "numeric",
      onchange: (e) => {
        const m = aMinutos(e.target.value);
        if (m == null) { aviso("Escríbelo como horas:minutos, por ejemplo 11:22", true); e.target.value = hm(leer()); return; }
        escribir(m); e.target.value = hm(m); guardar(); pintarComprobacion();
      } }), ayuda && el("small", {}, ayuda));
  const campoNum = (texto, ayuda, leer, escribir, min = 0, max = 999) => el("label", {}, texto,
    el("input", { type: "number", value: leer(), min, max,
      onchange: (e) => { escribir(Math.max(min, Math.min(max, Number(e.target.value) || 0))); e.target.value = leer(); guardar(); pintarComprobacion(); } }),
    ayuda && el("small", {}, ayuda));

  cont.append(
    campoHoras("Horas al año", "Por persona", () => p.horas_anuales, (v) => (p.horas_anuales = v)),
    campoHoras("Margen (±)", "Cuánto puede pasarse o quedarse corta", () => p.margen, (v) => (p.margen = v)),
    campoHoras("Turno de mañana", "", () => p.duracion.M, (v) => (p.duracion.M = v)),
    campoHoras("Turno de tarde", "", () => p.duracion.T, (v) => (p.duracion.T = v)),
    campoHoras("Turno de noche", "", () => p.duracion.N, (v) => (p.duracion.N = v)),
    campoNum("Mínimo de mañana", "Personas por grupo y día", () => p.minimos.M, (v) => (p.minimos.M = v), 0, 13),
    campoNum("Mínimo de tarde", "", () => p.minimos.T, (v) => (p.minimos.T = v), 0, 13),
    campoNum("Mínimo de noche", "", () => p.minimos.N, (v) => (p.minimos.N = v), 0, 13),
    campoNum("Máximo de días seguidos", "", () => p.max_dias_seguidos, (v) => (p.max_dias_seguidos = v), 1, 14),
    campoNum("Libranzas tras el máximo", "", () => p.libranzas_tras_max, (v) => (p.libranzas_tras_max = v), 0, 7),
    campoNum("Mínimo de días libres seguidos", "Nunca se libra un día suelto (salvo festivos)",
      () => p.min_libranzas_seguidas, (v) => (p.min_libranzas_seguidas = v), 1, 7),
    campoNum("Máximo de días libres seguidos", "Sin contar los que ya da la rotación",
      () => p.max_libranzas_seguidas, (v) => (p.max_libranzas_seguidas = v), 1, 14),
    campoNum("Tiempo máximo de cálculo", "Segundos por grupo", () => p.tiempo_max_s, (v) => (p.tiempo_max_s = v), 5, 600),
    el("div", { class: "descansos" },
      el("strong", {}, "Días de descanso después de la última noche"),
      el("small", { style: "display:block;margin-bottom:8px" }, "Según el día de la semana de esa noche. Salen siempre como L, nunca como F."),
      el("div", {}, ...DIAS.map((dia, i) => el("label", {}, dia,
        el("input", { type: "number", min: 0, max: 7, value: p.descansos_noche[i],
          onchange: (e) => { p.descansos_noche[i] = Math.max(0, Math.min(7, Number(e.target.value) || 0)); guardar(); } }))))),
  );
}

// ============================================================ acciones
function cambiarAnio(delta) {
  estado.anio += delta;
  const fest = festivosPorAnio[estado.anio];
  if (fest) estado.festivos = structuredClone(fest);
  guardar();
  pintarTodo();
  aviso(fest ? `Año ${estado.anio}: festivos de ${estado.anio} cargados. Revísalos.` : `Año ${estado.anio}: revisa los festivos.`);
}

async function leerFichero(input) {
  const f = input.files[0];
  input.value = "";
  return f ? new Uint8Array(await f.arrayBuffer()) : null;
}

async function generar() {
  $("#resultado").replaceChildren();
  const r = await conEspera("Calculando…", () => llamar("generar", { estado: JSON.stringify(estado) }));
  if (!r) return;
  const nombre = `calendario_${estado.anio}.xlsx`;
  const res = el("div", { class: "resultado" });
  for (const x of r.resumen) {
    const lista = [...x.errores.map((t) => el("li", { class: "mal-txt" }, t)), ...x.avisos.map((t) => el("li", {}, t))];
    res.append(el("div", { class: `res-grupo ${x.ok && !x.errores.length ? "ok" : "mal"}` },
      el("strong", {}, x.ok ? `✅ ${x.grupo}` : `❌ ${x.grupo}`),
      x.ok ? el("div", {}, `Horas por persona: entre ${hm(x.horas_min)} y ${hm(x.horas_max)}`) : null,
      lista.length ? el("ul", {}, lista) : null));
  }
  if (r.excel) {
    const boton = el("button", { type: "button", class: "boton grande verde", onclick: () => descargar(r.excel, nombre) }, `⬇️ Descargar ${nombre}`);
    res.prepend(boton);
    descargar(r.excel, nombre);
    aviso("¡Calendario listo! Se ha descargado el Excel.");
  }
  $("#resultado").append(res);
}

function conectarAcciones() {
  document.querySelectorAll("[data-anio]").forEach((b) => b.addEventListener("click", () => cambiarAnio(Number(b.dataset.anio))));

  $("#btn-plantilla-vacia").addEventListener("click", async () => {
    const bytes = await conEspera("Preparando la plantilla…", () => llamar("plantilla", { anio: estado.anio, vacia: true }));
    if (bytes) descargar(bytes, `plantilla_vacia_${estado.anio}.xlsx`);
  });
  $("#btn-exportar").addEventListener("click", async () => {
    const bytes = await conEspera("Preparando el Excel…", () => llamar("plantilla", { estado: JSON.stringify(estado), anio: estado.anio }));
    if (bytes) descargar(bytes, `datos_${estado.anio}.xlsx`);
  });
  $("#subir-datos").addEventListener("change", async (e) => {
    const bytes = await leerFichero(e.target);
    if (!bytes) return;
    const nuevo = await conEspera("Leyendo el Excel…", () => llamar("importar", { bytes }));
    if (!nuevo) return;
    estado = nuevo;
    grupoActivo = Math.max(0, estado.grupos.findIndex((x) => !rotacionVacia(x)));
    guardar();
    pintarTodo();
    aviso("Datos cargados desde el Excel.");
  });
  $("#subir-calendario").addEventListener("change", async (e) => {
    const bytes = await leerFichero(e.target);
    if (!bytes) return;
    const nuevo = await conEspera("Leyendo el calendario…", () => llamar("siguiente", { estado: JSON.stringify(estado), bytes }));
    if (!nuevo) return;
    estado = nuevo;
    guardar();
    pintarTodo();
    window.scrollTo({ top: 0, behavior: "smooth" });
    aviso(`Listo: ya estás en ${estado.anio}, con la Nochebuena y la Nochevieja apuntadas. Revisa los festivos.`, false, 7000);
  });
  $("#btn-generar").addEventListener("click", generar);
  $("#btn-anadir-festivo").addEventListener("click", () => {
    estado.festivos.push({ fecha: "", nombre: "", tipo: "Local" });
    guardar();
    pintarFestivos();
    $("#festivos .festivo:last-child input[type=date]")?.focus();
  });
  $("#btn-restablecer-festivos").addEventListener("click", () => {
    const fest = festivosPorAnio[estado.anio];
    if (!fest) return aviso(`No tengo los festivos de ${estado.anio}.`, true);
    estado.festivos = structuredClone(fest);
    guardar();
    pintarFestivos();
    aviso(`Festivos de ${estado.anio} restablecidos.`);
  });
  $("#btn-reiniciar").addEventListener("click", (e) => {
    const b = e.currentTarget;
    if (b.dataset.confirmar !== "1") {
      b.dataset.confirmar = "1";
      b.textContent = "¿Seguro? Se borra todo. Pulsa otra vez";
      setTimeout(() => { b.dataset.confirmar = ""; b.textContent = "Empezar de cero"; }, 5000);
      return;
    }
    estado = structuredClone(cargarEstado.inicial);
    grupoActivo = 0;
    guardar();
    pintarTodo();
    b.dataset.confirmar = "";
    b.textContent = "Empezar de cero";
    aviso("Datos borrados.");
  });
}

conectarAcciones();
iniciarPin();
