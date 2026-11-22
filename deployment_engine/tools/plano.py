# PROPÓSITO:   dibujar el plano de un laboratorio como un plano de red de verdad: las
#              redes son áreas translúcidas, cada clase de equipo tiene su símbolo
#              (router, switch, cortafuegos, servidor, puesto) y el router se sienta en
#              el cruce de las redes que une, no colgando de ellas.
# INVARIANTES: sale entero de la declaración (redes, nodos, cables) y no se pinta a
#              mano; el SVG se escribe dentro de la página y `./netlabs docs --check`
#              lo compara con lo que la declaración produce hoy, así que no se queda viejo.
#              Nada de números derivados: ni vmid, ni MAC, ni dirección de gestión.
# LÍMITES:     es puro texto: no enlaza imágenes, no pide fuentes, no ejecuta nada.
# VER:         deployment_engine/tools/docs.py; docs/diseno.md §4

from __future__ import annotations

import math
import re

# Todo el plano usa una sola paleta: el color dice qué es cada cosa (red, equipo,
# cortafuegos, borde), no qué laboratorio es.
TINTA = "#0f172a"
TENUE = "#475569"
LINEA = "#94a3b8"
RED_TRAZO = "#93b4f5"
RED_RELLENO = "#3b82f6"
EQUIPO_TRAZO = "#1d4ed8"
EQUIPO_RELLENO = "#dbeafe"
FUEGO_TRAZO = "#c2410c"
FUEGO_RELLENO = "#fff7ed"
BORDE_TRAZO = "#64748b"
BORDE_RELLENO = "#f8fafc"
FUENTE = "'Inter','Segoe UI',Helvetica,Arial,sans-serif"

# Cada símbolo ocupa una caja de este tamaño: sirve para centrar la etiqueta debajo
# y para saber por dónde sale una arista sin que cruce el dibujo.
SIMBOLO = {
    "router": (44, 44),
    "switch": (58, 26),
    "firewall": (50, 32),
    "server": (32, 38),
    "workstation": (40, 30),
    "control": (46, 24),
    "internet": (72, 44),
}
CELDA_ANCHO = 130      # hueco de un equipo dentro de su red: símbolo + etiqueta
CELDA_HUECO = 84       # alto de ese hueco
CELDA_MARGEN = 16      # aire entre el borde del área y sus equipos
CABECERA_AREA = 54     # nombre y subred de la red, dentro de su área
HUECO_PATAS = 6        # el borde del área pasa POR DEBAJO del símbolo del equipo
MARGEN = 24
CABECERA = 52          # título del plano
PIE = 54               # leyenda de símbolos


def _esc(texto: str) -> str:
    return (str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


# ---------------------------------------------------------------- símbolos ----
# Los símbolos son los de un plano de red, reducidos a vectores: el router es el
# círculo con cuatro flechas, el switch la caja con flechas cruzadas, el cortafuegos
# el muro de ladrillos. La forma dice la clase de un vistazo; el texto, el nombre.


def _flecha(x1: int, y1: int, x2: int, y2: int, color: str = EQUIPO_TRAZO) -> str:
    """Una flecha de verdad: línea y punta, para que se lea el sentido."""
    angulo = math.atan2(y2 - y1, x2 - x1)
    largo, ancho = 4.2, 2.6
    px, py = x2 - largo * math.cos(angulo), y2 - largo * math.sin(angulo)
    izq = (px - ancho * math.sin(angulo), py + ancho * math.cos(angulo))
    der = (px + ancho * math.sin(angulo), py - ancho * math.cos(angulo))
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2 - 2}" y2="{y2 - 2}" stroke="{color}" '
            f'stroke-width="1.6" stroke-linecap="round"/>'
            f'<polygon points="{x2},{y2} {izq[0]:.1f},{izq[1]:.1f} {der[0]:.1f},{der[1]:.1f}" '
            f'fill="{color}"/>')


def _simbolo(tipo: str, cx: float, cy: float, escala: float = 1.0) -> str:
    """El símbolo de esa clase, centrado en (cx, cy)."""
    g = [f'<g transform="translate({cx:.1f},{cy:.1f}) scale({escala})">']
    if tipo == "router":
        g.append(f'<circle r="20" fill="{EQUIPO_RELLENO}" stroke="{EQUIPO_TRAZO}" stroke-width="2"/>')
        g.append(_flecha(-13, -5, 13, -5))
        g.append(_flecha(13, 5, -13, 5))
        g.append(_flecha(-5, 13, -5, -13))
        g.append(_flecha(5, -13, 5, 13))
    elif tipo == "switch":
        g.append(f'<rect x="-28" y="-12" width="56" height="24" rx="4" '
                 f'fill="#ffffff" stroke="{EQUIPO_TRAZO}" stroke-width="2"/>')
        g.append(_flecha(-16, -4, 16, -4))
        g.append(_flecha(16, 4, -16, 4))
        g.append('<polygon points="-20,-9 -20,-1 -16,-1 -16,-9" fill="#bfdbfe"/>')
    elif tipo == "firewall":
        g.append(f'<rect x="-24" y="-15" width="48" height="30" rx="3" '
                 f'fill="{FUEGO_RELLENO}" stroke="{FUEGO_TRAZO}" stroke-width="2"/>')
        g.append(f'<path d="M-22 0H22M-8 -13V0M10 -13V0M-16 0V13M2 0V13M20 0V13" '
                 f'stroke="{FUEGO_TRAZO}" stroke-width="1.4" fill="none"/>')
    elif tipo == "server":
        g.append(f'<rect x="-15" y="-18" width="30" height="36" rx="3" '
                 f'fill="#ffffff" stroke="{EQUIPO_TRAZO}" stroke-width="2"/>')
        g.append(f'<path d="M-15 -6H15M-15 6H15" stroke="{EQUIPO_TRAZO}" stroke-width="1.3"/>')
        g.append(f'<circle cx="-9" cy="-12" r="1.7" fill="{EQUIPO_TRAZO}"/>'
                 f'<circle cx="-9" cy="0" r="1.7" fill="{EQUIPO_TRAZO}"/>')
    elif tipo == "workstation":
        g.append(f'<rect x="-19" y="-15" width="38" height="24" rx="2.5" '
                 f'fill="#ffffff" stroke="{EQUIPO_TRAZO}" stroke-width="2"/>')
        g.append(f'<path d="M-19 -7H19" stroke="{EQUIPO_TRAZO}" stroke-width="1.3"/>'
                 f'<path d="M0 9V14M-7 14H7" stroke="{EQUIPO_TRAZO}" stroke-width="1.6" '
                 f'stroke-linecap="round"/>')
    elif tipo == "control":
        g.append(f'<rect x="-22" y="-11" width="44" height="22" rx="11" '
                 f'fill="#ffffff" stroke="{BORDE_TRAZO}" stroke-width="2"/>')
        g.append(f'<circle cx="-10" cy="0" r="3" fill="{BORDE_TRAZO}"/>'
                 f'<path d="M-2 0H12" stroke="{BORDE_TRAZO}" stroke-width="1.6"/>')
    elif tipo == "internet":
        g.append(f'<path d="M-30 8c-6 0-11-5-11-11s5-11 11-11c2-8 9-13 17-13 9 0 16 6 18 14 '
                 f'7 0 12 5 12 11s-5 10-12 10z" fill="{BORDE_RELLENO}" '
                 f'stroke="{BORDE_TRAZO}" stroke-width="2" transform="translate(3,6)"/>')
    g.append("</g>")
    return "".join(g)


# ------------------------------------------------------------------ layout ----

class Caja:
    """Una red dibujada como área: su rectángulo y los equipos que viven dentro."""

    def __init__(self, nombre: str, titulo: str, subred: str):
        self.nombre = nombre
        self.titulo = titulo
        self.subred = subred
        self.ancho = 0.0
        self.alto = 0.0
        self.x = 0.0          # esquina superior izquierda
        self.y = 0.0
        self.rel: dict[str, tuple[float, float]] = {}
        self.dentro: dict[str, tuple[float, float]] = {}

    @property
    def centro(self) -> tuple[float, float]:
        return self.x + self.ancho / 2, self.y + self.alto / 2

    def asentar(self, x: float | None = None, y: float | None = None) -> None:
        """Fija el área en el plano y lleva sus equipos de relativo a absoluto."""
        if x is not None:
            self.x = x
        if y is not None:
            self.y = y
        self.dentro = {rol: (self.x + dx, self.y + dy) for rol, (dx, dy) in self.rel.items()}


def _ancho_etiqueta(textos: list[str], tam: float = 12) -> float:
    # Ancho aproximado de una fuente de palo seco: mejor que recortar la etiqueta.
    return max((len(t) * tam * 0.58 for t in textos), default=0.0)


def _niveles(nodos: list[dict], profundidad: dict[str, int]) -> dict[int, list[dict]]:
    niveles: dict[int, list[dict]] = {}
    for nodo in nodos:
        niveles.setdefault(profundidad[nodo["role"]], []).append(nodo)
    for nivel in niveles.values():
        nivel.sort(key=lambda n: n["role"])
    return dict(sorted(niveles.items()))


def _colocar_dentro(caja: Caja, nodos: list[dict], profundidad: dict[str, int],
                    eje: str, etiqueta) -> None:
    """Reparte los equipos de la red en columnas o filas por profundidad.

    `eje` dice por dónde entra la red al plano: con `h` el router queda a un lado y
    las profundidades avanzan en horizontal; con `v` el router queda encima y
    avanzan en vertical. El primer nivel —lo que cuelga de la puerta— queda siempre
    pegado al lado del router, para que la pata sea corta y no cruce el área.

    Mide el área y guarda las posiciones **relativas a su esquina**; asentarlas es
    trabajo de `Caja.asentar`, cuando el área ya sabe dónde va.
    """
    niveles = _niveles(nodos, profundidad)
    etiquetas = {n["role"]: etiqueta(n) for n in nodos}
    ancho_celda = max([CELDA_ANCHO] + [max(_ancho_etiqueta(t) + 18, 96) for t in etiquetas.values()])
    alto_celda = CELDA_HUECO
    filas = max(len(v) for v in niveles.values())

    if eje == "h":
        # Niveles en columnas; dentro de cada nivel, equipos en fila vertical.
        caja.ancho = 2 * CELDA_MARGEN + ancho_celda * len(niveles)
        caja.alto = 2 * CELDA_MARGEN + CABECERA_AREA + alto_celda * filas
        for columna, miembros in enumerate(niveles.values()):
            x = CELDA_MARGEN + ancho_celda * (columna + 0.5)
            y0 = caja.alto / 2 - alto_celda * len(miembros) / 2
            for fila, nodo in enumerate(miembros):
                caja.rel[nodo["role"]] = (x, y0 + alto_celda * (fila + 0.5))
    else:
        caja.alto = 2 * CELDA_MARGEN + CABECERA_AREA + alto_celda * len(niveles)
        caja.ancho = 2 * CELDA_MARGEN + ancho_celda * filas
        for fila, miembros in enumerate(niveles.values()):
            y = CELDA_MARGEN + CABECERA_AREA + alto_celda * (fila + 0.5)
            x0 = caja.ancho / 2 - ancho_celda * len(miembros) / 2
            for columna, nodo in enumerate(miembros):
                caja.rel[nodo["role"]] = (x0 + ancho_celda * (columna + 0.5), y)


def _borde(caja_simbolo: tuple[float, float], hacia: tuple[float, float],
           tam: tuple[float, float]) -> tuple[float, float]:
    """El punto por el que sale una arista del símbolo, mirando hacia el otro extremo.

    Se recorta contra la caja del símbolo: una línea que nace en el centro de un
    router lo atravesaría, y un plano no se dibuja así.
    """
    cx, cy = caja_simbolo
    dx, dy = hacia[0] - cx, hacia[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    hx, hy = tam[0] / 2 + 3, tam[1] / 2 + 3
    factor = min(hx / abs(dx) if dx else math.inf, hy / abs(dy) if dy else math.inf)
    return cx + dx * factor, cy + dy * factor

def _cadena(salidas: list[dict]) -> list[dict]:
    """Ordena las puertas de salida de fuera hacia dentro, por sus propios `after`."""
    por_rol = {n["role"]: n for n in salidas}
    orden: list[dict] = []
    vistos: set[str] = set()

    def visita(nodo: dict) -> None:
        if nodo["role"] in vistos:
            return
        vistos.add(nodo["role"])
        for padre in nodo.get("after") or []:
            if padre in por_rol:
                visita(por_rol[padre])
        orden.append(nodo)

    for nodo in sorted(salidas, key=lambda n: n["role"]):
        visita(nodo)
    return orden


def _direccion_de(nodo: dict, red: str | None = None) -> str:
    """La dirección con la que ese equipo se asoma a esa red (o a la primera)."""
    for pata in (nodo.get("configure") or {}).get("addresses") or []:
        if red is None or pata.get("network") == red:
            return pata["address"]
    if nodo.get("address") and nodo["address"] != "dhcp":
        return nodo["address"]
    return "dhcp" if nodo.get("address") == "dhcp" else ""


def plano(lab: dict, modo: str = "topologia") -> str:
    """El SVG del plano. `modo` elige qué une cada línea: la jerarquía o el cable."""
    import identity  # noqa: PLC0415  (el módulo se importa desde tools/)

    profundidad = identity._profundidad(lab)
    principal = identity._principal(lab)
    nodos = lab["nodes"]
    por_rol = {n["role"]: n for n in nodos}
    tipos_presentes = sorted({n["type"] for n in nodos})
    salidas = [n for n in nodos if profundidad[n["role"]] == 0]

    def etiqueta(nodo: dict) -> list[str]:
        """Lo que se lee bajo el símbolo: el nombre y, si cabe, su dirección.

        Un equipo con pata en varias redes no lleva sus direcciones debajo —se
        amontonarían—: cada dirección vive en la cabecera del área que abre. En el
        cableado el nombre va solo: los puertos los dice cada punta de su cable.
        """
        if modo == "cableado":
            return [nodo["role"]]
        if profundidad[nodo["role"]] == 0 or len(nodo.get("networks") or []) > 1:
            return [nodo["role"]]
        direccion = _direccion_de(nodo)
        return [nodo["role"]] + ([direccion] if direccion else [])

    # --- las redes, como áreas -------------------------------------------------
    cajas: dict[str, Caja] = {}
    for net in lab["networks"]:
        cajas[net["name"]] = Caja(net["name"], net.get("title") or net["name"],
                                  identity._subred(net["address"]))
    dentro = [n for n in nodos if profundidad[n["role"]] > 0 and principal.get(n["role"]) in cajas]
    for net in lab["networks"]:
        suyos = [n for n in dentro if principal[n["role"]] == net["name"]]
        eje = "v" if len(lab["networks"]) == 1 else "h"
        if suyos:
            _colocar_dentro(cajas[net["name"]], suyos, profundidad, eje, etiqueta)
        else:
            caja = cajas[net["name"]]
            caja.ancho = CELDA_ANCHO + 2 * CELDA_MARGEN
            caja.alto = CELDA_HUECO + CABECERA_AREA + 2 * CELDA_MARGEN

    # --- el eje: internet, las puertas y las áreas alrededor del router --------
    # El router no cuelga de las redes: se sienta donde se tocan. Con dos redes, una
    # a cada lado; con una, la red debajo y la salida arriba; con más, en abanico.
    cadena = _cadena(salidas)
    separacion = 104
    posiciones: dict[str, tuple[float, float]] = {}
    y = 0.0
    for nodo in cadena:
        posiciones[nodo["role"]] = (0.0, y)
        y += separacion
    router = cadena[-1]["role"] if cadena else None
    origen = posiciones[router] if router else (0.0, 0.0)

    y_internet = (posiciones[cadena[0]["role"]][1] - separacion) if cadena else -separacion
    internet_xy = (0.0, y_internet)

    redes = [cajas[n["name"]] for n in lab["networks"]]
    if len(redes) == 1:
        caja = redes[0]
        caja.asentar(origen[0] - caja.ancho / 2, origen[1] + HUECO_PATAS)
    elif len(redes) == 2:
        izquierda, derecha = redes
        izquierda.asentar(origen[0] - HUECO_PATAS - izquierda.ancho,
                          origen[1] - izquierda.alto / 2)
        derecha.asentar(origen[0] + HUECO_PATAS, origen[1] - derecha.alto / 2)
    else:
        # Con tres o más redes, el equipo de varias patas se rodea: una a cada lado y
        # el resto debajo, de modo que su símbolo quede en el cruce de las tres áreas
        # y no colgado encima de una fila de cajas.
        izquierda, derecha, resto = redes[0], redes[1], redes[2:]
        izquierda.asentar(origen[0] - HUECO_PATAS - izquierda.ancho,
                          origen[1] - izquierda.alto / 2)
        derecha.asentar(origen[0] + HUECO_PATAS, origen[1] - derecha.alto / 2)
        total = sum(c.ancho for c in resto) + 40 * (len(resto) - 1)
        x = origen[0] - total / 2
        # La fila de abajo arranca por debajo de las áreas de los lados: dos redes no
        # pueden solaparse en el dibujo, que se leerían como una sola.
        techo = max((origen[1] + c.alto / 2 for c in (izquierda, derecha)),
                    default=origen[1])
        for caja in resto:
            caja.asentar(x, max(origen[1] + HUECO_PATAS, techo + 26))
            x += caja.ancho + 40

    def punto_de(rol: str) -> tuple[float, float]:
        if rol == "internet":
            return internet_xy
        if rol in posiciones:
            return posiciones[rol]
        for caja in cajas.values():
            if rol in caja.dentro:
                return caja.dentro[rol]
        raise KeyError(rol)

    # --- las líneas -----------------------------------------------------------
    # Cada arista es (a, z). Sin flechas: un plano dice quién toca a quién, no por
    # dónde va el tráfico, y lo que hay que leer de una conexión ya vive en su equipo
    # o en la cabecera de su red.
    aristas: list[tuple[str, str]] = []
    cables: list[tuple[str, int, str, int]] = []
    if modo == "cableado":
        cables = [(link["a"]["node"], link["a"]["port"], link["z"]["node"], link["z"]["port"])
                  for link in lab.get("links") or []]
    else:
        if cadena:
            aristas.append(("internet", cadena[0]["role"]))
        for nodo in cadena[1:]:
            padres = [p for p in (nodo.get("after") or []) if p in posiciones]
            if padres:
                aristas.append((padres[0], nodo["role"]))
            else:
                anterior = cadena[cadena.index(nodo) - 1]["role"]
                aristas.append((anterior, nodo["role"]))
        for nodo in sorted(dentro, key=lambda n: (profundidad[n["role"]], n["role"])):
            for padre in nodo.get("after") or []:
                if padre in por_rol and profundidad.get(padre, 0) > 0:
                    aristas.append((padre, nodo["role"]))
                elif padre in posiciones:
                    aristas.append((padre, nodo["role"]))
        # Una red cuyos equipos no cuelgan de la puerta declarada sigue tocando el
        # router: la pata se dibuja hasta el borde del área, que es lo que hay.
        for red in lab["networks"]:
            caja = cajas[red["name"]]
            tocada = any(a in caja.dentro or z in caja.dentro
                         for a, z in aristas
                         if not (a.startswith("red:") or z.startswith("red:")))
            if not tocada and router and red["name"] in (por_rol[router].get("networks") or []):
                aristas.append((router, f"red:{red['name']}"))

    # --- geometría a SVG ------------------------------------------------------
    pasarelas: dict[str, list[str]] = {}
    for rol, (cx, cy) in posiciones.items():
        for red in por_rol[rol].get("networks") or []:
            direccion = _direccion_de(por_rol[rol], red)
            # Sólo una dirección de verdad es una puerta; «dhcp» es cómo la consigue
            # el equipo, no una dirección que se pueda escribir en un plano.
            if re.fullmatch(r"[0-9.]+/[0-9]+", direccion or ""):
                if direccion not in pasarelas.setdefault(red, []):
                    pasarelas[red].append(direccion)

    def lado(rol: str) -> str:
        """De qué lado cabe el nombre: el que más lejos queda de sus conexiones.

        Un nombre pegado a un cable se lee como si el cable lo atravesara, así que se
        elige el costado con más aire. Empate: abajo primero, que es donde se busca el
        nombre de un equipo.
        """
        if rol == "internet":
            return "arriba"
        cx, cy = punto_de(rol)
        vecinos = [z for a, _, z, _ in cables if a == rol]
        vecinos += [a for a, _, z, _ in cables if z == rol]
        for a, z in aristas:
            if a == rol:
                vecinos.append(z[4:] if z.startswith("red:") else z)
            elif z == rol:
                vecinos.append(a[4:] if a.startswith("red:") else a)
        rumbos = []
        for otro in vecinos:
            if otro not in por_rol and otro != "internet":
                continue  # una red sin equipos: el rumbo lo da su área, no un equipo
            ox, oy = punto_de(otro)
            dx, dy = ox - cx, oy - cy
            largo = math.hypot(dx, dy)
            if largo > 1:
                rumbos.append((dx / largo, dy / largo))
        if not rumbos:
            return "abajo"
        mejor, aire = "abajo", -1.0
        for candidato, (ux, uy) in (("abajo", (0, 1)), ("derecha", (1, 0)),
                                    ("izquierda", (-1, 0)), ("arriba", (0, -1))):
            hueco = min(1 - (ux * ex + uy * ey) for ex, ey in rumbos)
            if hueco > aire + 1e-9:
                mejor, aire = candidato, hueco
        return mejor

    piezas: list[str] = []
    textos: list[str] = []
    puntos: list[tuple[float, float]] = [internet_xy]
    for caja in cajas.values():
        piezas.append(_area(caja, pasarelas.get(caja.nombre, [])))
        puntos += [(caja.x, caja.y), (caja.x + caja.ancho, caja.y + caja.alto)]

    for caja in cajas.values():
        for rol, (cx, cy) in caja.dentro.items():
            nodo = por_rol[rol]
            piezas.append(_simbolo(nodo["type"], cx, cy))
            textos.append(_etiqueta(cx, cy, etiqueta(nodo), clase=nodo["type"],
                                    lado=lado(rol)))
            puntos += [(cx - 70, cy - 30), (cx + 70, cy + 56)]

    for rol, (cx, cy) in posiciones.items():
        piezas.append(_simbolo(por_rol[rol]["type"], cx, cy))
        textos.append(_etiqueta(cx, cy, etiqueta(por_rol[rol]),
                                clase=por_rol[rol]["type"], lado=lado(rol)))
        puntos += [(cx - 70, cy - 30), (cx + 70, cy + 56)]
    if modo == "topologia":
        # El cableado no dibuja la salida a Internet: no hay cable declarado que la
        # una, y una nube sin línea no es un plano de cableado, es un adorno.
        piezas.append(_simbolo("internet", *internet_xy))
        textos.append(_etiqueta(*internet_xy, ["Internet"], clase="internet", lado="arriba"))
        puntos += [(internet_xy[0] - 44, internet_xy[1] - 26),
                   (internet_xy[0] + 44, internet_xy[1] + 60)]

    for a, a_puerto, z, z_puerto in cables:
        tipo_a = por_rol[a]["type"] if a in por_rol else "internet"
        tipo_z = por_rol[z]["type"] if z in por_rol else "internet"
        piezas.append(_cable(punto_de(a), punto_de(z), SIMBOLO[tipo_a], SIMBOLO[tipo_z],
                             a_puerto, z_puerto))

    for a, z in aristas:
        if a.startswith("red:") or z.startswith("red:"):
            # La pata llega hasta el borde del área, que es todo lo que se puede
            # dibujar: dentro de ella no hay ningún equipo declarado al que atar.
            caja = cajas[(a if a.startswith("red:") else z)[4:]]
            inicio = posiciones[router]
            # Qué borde del área mira al equipo: el lado o el techo/suelo, según por
            # dónde caiga. Una red a la izquierda se toca por su borde derecho.
            dx = abs(caja.centro[0] - inicio[0]) / max(caja.ancho, 1)
            dy = abs(caja.centro[1] - inicio[1]) / max(caja.alto, 1)
            if dx > dy:
                x = caja.x + caja.ancho if caja.centro[0] > inicio[0] else caja.x
                fin = (x, min(max(inicio[1], caja.y + 24), caja.y + caja.alto - 24))
            else:
                y = caja.y if caja.centro[1] > inicio[1] else caja.y + caja.alto
                fin = (min(max(inicio[0], caja.x + 24), caja.x + caja.ancho - 24), y)
            if math.hypot(fin[0] - inicio[0], fin[1] - inicio[1]) > \
                    max(SIMBOLO[por_rol[router]["type"]]) / 2 + 2:
                # Si el borde del área ya pasa por debajo del símbolo, el equipo está
                # tocándola: una pata de dos píxeles sólo añadiría tinta.
                piezas.append(_linea(inicio, fin, SIMBOLO[por_rol[router]["type"]]))
            continue
        pa, pz = punto_de(a), punto_de(z)
        tipo_a = "internet" if a == "internet" else por_rol[a]["type"]
        tipo_z = "internet" if z == "internet" else por_rol[z]["type"]
        piezas.append(_linea(pa, pz, SIMBOLO[tipo_a], SIMBOLO[tipo_z],
                             discontinua="internet" in (a, z)))

    # --- normalizar y componer ------------------------------------------------
    xs = [p[0] for p in puntos]
    ys = [p[1] for p in puntos]
    minx, miny = min(xs), min(ys)
    ancho = max(max(xs) - minx + 2 * MARGEN, _ancho_leyenda(tipos_presentes) + 2 * MARGEN)
    alto = max(ys) - miny + 2 * MARGEN + CABECERA + PIE
    dx, dy = MARGEN - minx, MARGEN + CABECERA - miny

    leyenda = _leyenda(tipos_presentes, ancho / 2, alto - PIE / 2 - 2)
    espacios = ", ".join(identity._subred(s) for s in lab["address_spaces"])
    # El pie de figura dice lo que un plano no debe dejar adivinar: qué es cada área.
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho:.0f}" height="{alto:.0f}" '
        f'viewBox="0 0 {ancho:.0f} {alto:.0f}" role="img" '
        f'aria-label="Plano de {_esc(lab["lab"])}">',
        f'<rect width="{ancho:.0f}" height="{alto:.0f}" fill="#ffffff"/>',
        f'<text x="{ancho / 2:.1f}" y="28" text-anchor="middle" font-family="{FUENTE}" '
        f'font-size="15" font-weight="650" fill="{TINTA}">{_esc(lab["lab"])}</text>',
        f'<text x="{ancho / 2:.1f}" y="45" text-anchor="middle" font-family="{FUENTE}" '
        f'font-size="11.5" fill="{TENUE}">{_esc(espacios)}</text>',
        f'<g transform="translate({dx:.1f},{dy:.1f})">',
        *piezas,
        *textos,
        "</g>",
        leyenda,
        "</svg>",
        "",
    ])


def _etiqueta(cx: float, cy: float, lineas: list[str], clase: str = "equipo",
              lado: str = "abajo") -> str:
    """El nombre del equipo junto a su símbolo, y sus direcciones si las tiene.

    `lado` no es capricho: un nombre centrado bajo el símbolo queda tachado por el
    cable que sale de él hacia abajo, así que ahí el nombre se pone al costado. El
    halo blanco remata el trabajo cuando una línea roza una letra.
    """
    ancho, alto = SIMBOLO.get(clase) or (40, 40)
    partes = []
    for i, texto in enumerate(lineas):
        tam = 12.5 if i == 0 else 10.5
        peso = 600 if i == 0 else 400
        color = TINTA if i == 0 else TENUE
        if lado == "derecha":
            x, ancla = cx + ancho / 2 + 9, "start"
            y = cy + 4 + (i - (len(lineas) - 1) / 2) * 12
        elif lado == "izquierda":
            x, ancla = cx - ancho / 2 - 9, "end"
            y = cy + 4 + (i - (len(lineas) - 1) / 2) * 12
        elif lado == "arriba":
            x, ancla = cx, "middle"
            y = cy - alto / 2 - 10 - (len(lineas) - 1 - i) * 12
        else:
            x, ancla = cx, "middle"
            y = cy + alto / 2 + 13 + i * 12
        partes.append(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{ancla}" '
                      f'font-family="{FUENTE}" font-size="{tam}" font-weight="{peso}" '
                      f'fill="{color}" stroke="#ffffff" stroke-width="3.5" '
                      f'paint-order="stroke">{_esc(texto)}</text>')
    return "".join(partes)


def _area(caja: Caja, pasarelas: list[str]) -> str:
    """Una red: área translúcida con su nombre, su subred y quién le da puerta.

    La dirección con la que el router se asoma a la red se escribe aquí, en la
    cabecera del área, y no encima del cable: sobre la línea quedaba tapando el
    borde del área, que es justo lo que hay que ver.
    """
    textos = [
        f'<text x="{caja.x + 16:.1f}" y="{caja.y + 21:.1f}" font-family="{FUENTE}" '
        f'font-size="12.5" font-weight="650" fill="{EQUIPO_TRAZO}">{_esc(caja.titulo)}</text>',
        f'<text x="{caja.x + 16:.1f}" y="{caja.y + 36:.1f}" font-family="{FUENTE}" '
        f'font-size="10.5" fill="{TENUE}">{_esc(caja.subred)}</text>',
    ]
    if pasarelas:
        textos.append(f'<text x="{caja.x + 16:.1f}" y="{caja.y + 51:.1f}" '
                      f'font-family="{FUENTE}" font-size="10.5" fill="{EQUIPO_TRAZO}">'
                      f'puerta {_esc(", ".join(pasarelas))}</text>')
    return "".join([
        f'<rect x="{caja.x:.1f}" y="{caja.y:.1f}" width="{caja.ancho:.1f}" '
        f'height="{caja.alto:.1f}" rx="14" fill="{RED_RELLENO}" fill-opacity="0.06" '
        f'stroke="{RED_TRAZO}" stroke-width="1.4"/>',
        *textos,
    ])


def _cable(a: tuple[float, float], z: tuple[float, float],
           tam_a: tuple[float, float], tam_z: tuple[float, float],
           puerto_a: int, puerto_z: int) -> str:
    """Un cable: la línea y, en cada punta, el puerto que ocupa.

    El puerto se escribe pegado al equipo del que sale —una regleta se lee en su
    aparato, no en mitad del cable—, así que un switch con tres cables enseña tres
    etiquetas cortas en vez de tres frases largas que se pisan entre sí.
    """
    inicio = _borde(a, z, tam_a)
    fin = _borde(z, a, tam_z)
    largo = math.hypot(fin[0] - inicio[0], fin[1] - inicio[1]) or 1
    ux, uy = (fin[0] - inicio[0]) / largo, (fin[1] - inicio[1]) / largo
    piezas = [f'<line x1="{inicio[0]:.1f}" y1="{inicio[1]:.1f}" x2="{fin[0]:.1f}" '
              f'y2="{fin[1]:.1f}" stroke="{LINEA}" stroke-width="1.6" '
              f'stroke-linecap="round"/>']
    for (px, py), (dx, dy), puerto in ((inicio, (ux, uy), puerto_a),
                                       (fin, (-ux, -uy), puerto_z)):
        # El puerto va SOBRE el cable, a un paso del símbolo: ahí no lo tapa el nombre
        # del equipo (que el plano aparta del rumbo de sus cables) ni la cabecera del
        # área, y se ve de qué punta del cable es sin leer nada más.
        tx, ty = px + dx * 18, py + dy * 18
        piezas += [
            f'<rect x="{tx - 10:.1f}" y="{ty - 8:.1f}" width="20" height="16" rx="5" '
            f'fill="#ffffff" stroke="{EQUIPO_TRAZO}" stroke-width="1.1"/>',
            f'<text x="{tx:.1f}" y="{ty + 3.5:.1f}" text-anchor="middle" '
            f'font-family="{FUENTE}" font-size="10" font-weight="600" '
            f'fill="{EQUIPO_TRAZO}">p{puerto}</text>',
        ]
    return "".join(piezas)


def _linea(a: tuple[float, float], z: tuple[float, float],
           tam_a: tuple[float, float] = (20, 20),
           tam_z: tuple[float, float] = (20, 20),
           discontinua: bool = False) -> str:
    """Una conexión entre dos símbolos, sin flecha y sin etiqueta en el cable.

    `discontinua` marca la salida a Internet, que no es un cable del laboratorio. Nada
    más se escribe encima: cada dato vive en su equipo o en la cabecera de su red.
    """
    inicio = _borde(a, z, tam_a)
    fin = _borde(z, a, tam_z)
    guion = ' stroke-dasharray="5 4"' if discontinua else ''
    return (f'<line x1="{inicio[0]:.1f}" y1="{inicio[1]:.1f}" x2="{fin[0]:.1f}" '
            f'y2="{fin[1]:.1f}" stroke="{LINEA}" stroke-width="1.6" '
            f'stroke-linecap="round"{guion}/>')


_ORDEN_CLASE = ("router", "switch", "firewall", "server", "workstation", "control")
_NOMBRES_CLASE = {"router": "router", "switch": "switch", "firewall": "cortafuegos",
                  "server": "servidor", "workstation": "puesto", "control": "control"}


def _ancho_leyenda(tipos: list[str]) -> float:
    """Lo que ocupa la clave de símbolos, para que el lienzo la contenga."""
    nombres = _NOMBRES_CLASE
    items = [t for t in _ORDEN_CLASE if t in tipos]
    return 26 + sum(SIMBOLO[t][0] * 0.72 + 8 + len(nombres[t]) * 6.4 for t in items) \
        + 22 * len(items)


def _leyenda(tipos: list[str], cx: float, cy: float) -> str:
    """La clave de símbolos: sólo las clases que el laboratorio tiene de verdad.

    Un plano que dibuja un símbolo y no dice qué clase es obliga a adivinar; uno que
    lista clases que no están es ruido. Van las que hay, con la forma de verdad.
    """
    nombres = _NOMBRES_CLASE
    items = [t for t in _ORDEN_CLASE if t in tipos]
    # Ancho de cada celda: el símbolo (ya escalado) y su nombre.
    anchos = [(SIMBOLO[t][0] * 0.72 + 8 + len(nombres[t]) * 6.4) for t in items]
    total = 26 + sum(anchos) + 22 * len(items)
    x = cx - total / 2
    piezas = [f'<rect x="{x:.1f}" y="{cy - 19:.1f}" width="{total:.1f}" height="38" '
              f'rx="10" fill="#ffffff" stroke="#e2e8f0"/>',
              f'<rect x="{x + 12:.1f}" y="{cy - 7:.1f}" width="18" height="14" rx="4" '
              f'fill="{RED_RELLENO}" fill-opacity="0.08" stroke="{RED_TRAZO}"/>',
              f'<text x="{x + 35:.1f}" y="{cy + 4:.1f}" font-family="{FUENTE}" '
              f'font-size="11" fill="{TENUE}">red</text>']
    x += 22 + 35
    for tipo, ancho in zip(items, anchos):
        piezas.append(_simbolo(tipo, x + SIMBOLO[tipo][0] * 0.36, cy, 0.72))
        piezas.append(f'<text x="{x + SIMBOLO[tipo][0] * 0.72 + 7:.1f}" y="{cy + 4:.1f}" '
                      f'font-family="{FUENTE}" font-size="11" fill="{TENUE}">'
                      f'{_esc(nombres[tipo])}</text>')
        x += ancho + 22
    return "".join(piezas)
