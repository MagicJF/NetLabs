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

import ipaddress
import math
import re

# Todo el plano usa una sola paleta: el color dice qué es cada cosa (red, equipo,
# cortafuegos, borde), no qué laboratorio es.
TINTA = "#0f172a"
TENUE = "#475569"
LINEA = "#94a3b8"
RED_TRAZO = "#93b4f5"
RED_RELLENO = "#3b82f6"
EQUIPO_TRAZO = "#1b5fa8"      # el trazo de los equipos, un solo azul de plano
EQUIPO_RELLENO = "#ffffff"
EQUIPO_CARA = "#eef5fb"
# El color de acento dice la familia, como en los juegos de iconos de AWS: la red en
# morado, la seguridad en rojo, lo que atiende el usuario en gris.
RED_TRAZO_EQ = "#7c4dff"      # router, switch
SEG_TRAZO_EQ = "#d93f4c"      # cortafuegos
FIN_TRAZO_EQ = "#5b7793"      # servidor, puesto, gestión
FUEGO_TRAZO = SEG_TRAZO_EQ
FUEGO_RELLENO = "#fdf0f1"
BORDE_TRAZO = "#5b7793"
BORDE_RELLENO = "#f4f7fa"
FUENTE = "'Inter','Segoe UI',Helvetica,Arial,sans-serif"

# Cada símbolo ocupa una caja de este tamaño: sirve para centrar la etiqueta debajo
# y para saber por dónde sale una arista sin que cruce el dibujo.
SIMBOLO = {
    "router": (38, 38),
    "switch": (52, 24),
    "firewall": (48, 28),
    "server": (26, 38),
    "workstation": (32, 28),
    "control": (42, 24),
    "internet": (74, 42),
}
CELDA_ANCHO = 130      # hueco de un equipo dentro de su red: símbolo + etiqueta
CELDA_HUECO = 84       # alto de ese hueco
CELDA_MARGEN = 16      # aire entre el borde del área y sus equipos
CABECERA_AREA = 54     # nombre y subred de la red, dentro de su área
HUECO_PATAS = 6        # el borde del área pasa POR DEBAJO del símbolo del equipo
MARGEN = 24
CABECERA = 52          # título del plano


def _esc(texto: str) -> str:
    return (str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


# ---------------------------------------------------------------- símbolos ----
# Los símbolos son los de un plano de red, dibujados aquí a la manera de los de Cisco
# —el router es un cilindro con cuatro flechas en la cara de arriba, el switch una
# placa en perspectiva con sus flechas cruzadas, el cortafuegos el muro de ladrillos,
# el servidor una torre de bahías, el puesto una pantalla con su peana— y en su azul.
# Se dibujan con vectores y no se copian de su pack de iconos: esos son suyos y su
# licencia no permite redistribuirlos, y este plano se genera y se versiona entero.


def _flecha(x1: float, y1: float, x2: float, y2: float, color: str = EQUIPO_TRAZO,
            grosor: float = 1.5, largo: float = 4.0, ancho: float = 2.4) -> str:
    """Una flecha de verdad: línea y punta, para que se lea el sentido."""
    angulo = math.atan2(y2 - y1, x2 - x1)
    px, py = x2 - largo * math.cos(angulo), y2 - largo * math.sin(angulo)
    izq = (px - ancho * math.sin(angulo), py + ancho * math.cos(angulo))
    der = (px + ancho * math.sin(angulo), py - ancho * math.cos(angulo))
    return (f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2 - 1.2:.1f}" y2="{y2 - 1.2:.1f}" '
            f'stroke="{color}" stroke-width="{grosor}" stroke-linecap="round"/>'
            f'<polygon points="{x2:g},{y2:g} {izq[0]:.1f},{izq[1]:.1f} '
            f'{der[0]:.1f},{der[1]:.1f}" fill="{color}"/>')


def _engranaje(cx: float, cy: float, radio: float) -> str:
    """Una rueda dentada de verdad: disco, dientes y eje. Un asterisco no es un engranaje."""
    dientes = "".join(
        f'<rect x="{cx + radio - 0.6:.1f}" y="{cy - 1.5:.1f}" width="{radio * 0.55:.1f}" '
        f'height="3" rx="0.6" fill="{EQUIPO_TRAZO}" '
        f'transform="rotate({k * 45:.0f} {cx:.1f} {cy:.1f})"/>'
        for k in range(8))
    return "".join([
        dientes,
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radio:.1f}" fill="{EQUIPO_CARA}" '
        f'stroke="{EQUIPO_TRAZO}" stroke-width="1.6"/>',
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radio * 0.42:.1f}" fill="#ffffff" '
        f'stroke="{EQUIPO_TRAZO}" stroke-width="1.3"/>',
    ])


def _simbolo_cisco(tipo: str) -> str:
    """El dibujo de esa clase, centrado en el origen."""
    azul, relleno, cara = FIN_TRAZO_EQ, EQUIPO_RELLENO, EQUIPO_CARA
    if tipo == "router":
        # Plano, sin volumen: el círculo y las cuatro direcciones que encamina.
        return "".join([
            f'<circle r="15.5" fill="{relleno}" stroke="{RED_TRAZO_EQ}" stroke-width="2"/>',
            _flecha(-3, 0, -11.5, 0, color=RED_TRAZO_EQ, largo=3.4, ancho=2.2),
            _flecha(3, 0, 11.5, 0, color=RED_TRAZO_EQ, largo=3.4, ancho=2.2),
            _flecha(0, -3, 0, -11.5, color=RED_TRAZO_EQ, largo=3.4, ancho=2.2),
            _flecha(0, 3, 0, 11.5, color=RED_TRAZO_EQ, largo=3.4, ancho=2.2),
        ])
    if tipo == "switch":
        # Plano también: la caja de frente y, dentro, las dos flechas cruzadas que
        # dicen «esto conmuta», con la fila de puertos marcada abajo.
        return "".join([
            f'<rect x="-24" y="-10" width="48" height="20" rx="3" fill="{relleno}" '
            f'stroke="{RED_TRAZO_EQ}" stroke-width="2"/>',
            _flecha(-14, -3, 10, -3, color=RED_TRAZO_EQ, largo=3.2, ancho=2.0),
            _flecha(14, 3, -10, 3, color=RED_TRAZO_EQ, largo=3.2, ancho=2.0),
            f'<path d="M-16 10v3M-8 10v3M0 10v3M8 10v3M16 10v3" stroke="{RED_TRAZO_EQ}" '
            f'stroke-width="1.4"/>',
        ])
    if tipo == "firewall":
        # El muro de ladrillos, con las hiladas trabadas.
        return "".join([
            f'<rect x="-23" y="-13" width="46" height="26" rx="2" fill="{FUEGO_RELLENO}" '
            f'stroke="{FUEGO_TRAZO}" stroke-width="1.8"/>',
            f'<path d="M-23 -4.3H23M-23 4.3H23" stroke="{FUEGO_TRAZO}" stroke-width="1.4"/>',
            f'<path d="M-7.7 -13V-4.3M7.7 -13V-4.3M0 -4.3V4.3M-15.3 4.3V13M15.3 4.3V13" '
            f'stroke="{FUEGO_TRAZO}" stroke-width="1.4"/>',
        ])
    if tipo == "server":
        # Torre de bahías: tres alturas, cada una con su indicador.
        return "".join([
            f'<rect x="-12" y="-18" width="24" height="36" rx="2.5" fill="#ffffff" '
            f'stroke="{azul}" stroke-width="1.8"/>',
            f'<path d="M-12 -10H12M-12 -2H12M-12 6H12" stroke="{azul}" stroke-width="1.2"/>',
            '<circle cx="-7" cy="-14" r="1.7" fill="#16a34a"/>'
            '<circle cx="-7" cy="-6" r="1.7" fill="#16a34a"/>'
            f'<circle cx="-7" cy="2" r="1.7" fill="{azul}"/>',
        ])
    if tipo == "workstation":
        # Pantalla con su peana: el puesto de trabajo de siempre.
        return "".join([
            f'<rect x="-15" y="-13" width="30" height="21" rx="2" fill="#ffffff" '
            f'stroke="{azul}" stroke-width="1.8"/>',
            f'<rect x="-11.5" y="-9.5" width="23" height="14" rx="1" fill="{cara}"/>',
            f'<path d="M-4 8v5h8V8" fill="none" stroke="{azul}" stroke-width="1.6"/>',
            f'<rect x="-9" y="13" width="18" height="2.4" rx="1.2" fill="{azul}"/>',
        ])
    if tipo == "control":
        # Puesto de gestión: una pantalla con su traza y, al lado, la rueda dentada.
        return "".join([
            f'<rect x="-21" y="-11" width="28" height="22" rx="3" fill="#ffffff" '
            f'stroke="{azul}" stroke-width="1.8"/>',
            f'<path d="M-17 5l5-7 4 4 5-8 4 6" fill="none" stroke="{azul}" '
            f'stroke-width="1.5" stroke-linejoin="round"/>',
            _engranaje(13, 0, 5.2),
        ])
    if tipo == "internet":
        return (f'<path d="M-30 8c-6 0-11-5-11-11s5-11 11-11c2-8 9-13 17-13 9 0 16 6 18 14 '
                f'7 0 12 5 12 11s-5 10-12 10z" fill="{BORDE_RELLENO}" '
                f'stroke="{BORDE_TRAZO}" stroke-width="1.8" transform="translate(3,6)"/>')
    return f'<circle r="14" fill="{relleno}" stroke="{azul}" stroke-width="1.8"/>'


def _simbolo(tipo: str, cx: float, cy: float, escala: float = 1.0) -> str:
    """El símbolo de esa clase, centrado en (cx, cy)."""
    return (f'<g transform="translate({cx:.1f},{cy:.1f}) scale({escala})">'
            f'{_simbolo_cisco(tipo)}</g>')


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
    if red is not None and len(nodo.get("networks") or []) > 1:
        # Una dirección suelta no dice a cuál de sus redes se asoma: escribirla en la
        # cabecera de todas sería inventar una puerta donde no la hay.
        return ""
    if nodo.get("address") and nodo["address"] != "dhcp":
        return nodo["address"]
    return "dhcp" if nodo.get("address") == "dhcp" else ""


# ------------------------------------------------------- planos anidados ----
# La numeración de un sitio no es una lista de redes sueltas: es una muñeca rusa.
# Un /24 vive DENTRO de un /16, que vive dentro de un /8, y el plano tiene que
# enseñar eso con áreas dentro de áreas, no con cajas hermanas. El anidamiento no
# se declara: sale de las direcciones, que ya lo dicen.
#
# La colocación de cada área es la de un árbol: las hijas en fila, y la que hace de
# pasillo —la que un equipo de dentro cruza para hablar con dos hermanas, que es lo
# que hace el tránsito entre dos sedes— encima y de lado a lado, para que las patas
# bajen rectas a cada sitio en vez de cruzar las áreas de los demás.

M_REG = 20            # aire entre el borde de un área y lo que contiene
HUECO_REG = 30        # aire entre dos áreas hermanas
HUECO_PASILLO = 108   # hueco entre dos áreas que une un equipo: ahí cabe su símbolo
ALTO_EQUIPO = 84      # la fila de equipos dentro de un área
MARGEN_ARRIBA = 16


def _mascara(texto: str) -> str:
    """Cómo se lee una red en un plano: con los octetos de host en `x`."""
    red = ipaddress.ip_network(texto, strict=False)
    octetos = str(red.network_address).split(".")
    for i in range(red.prefixlen // 8, 4):
        octetos[i] = "x"
    return ".".join(octetos)


class Region(Caja):
    """Una porción de la numeración: su rectángulo, lo que cuelga de ella y quién vive dentro.

    Una red declarada es una región hoja; un espacio de direcciones, la región que
    las contiene. La raíz —`10.x.x.x`— no se declara: se deduce de que todo lo
    declarado cabe en ella.
    """

    def __init__(self, nombre: str, titulo: str, subred: str, cidr) -> None:
        super().__init__(nombre, titulo, subred)
        self.cidr = cidr
        self.hijas: list[Region] = []
        self.padre: Region | None = None
        self.nodos: list[str] = []
        self.pasillos: list[tuple[Region, Region, str]] = []
        self.espina = False
        self.cabecera = 40.0
        self.servicios: list[str] = []

    @property
    def prefijo(self) -> int:
        return self.cidr.prefixlen


def _mide_cabecera(region: Region) -> float:
    """El alto del encabezado: nombre, subred y, en una red, lo que tiene montado."""
    alto = 22.0
    if region.subred:
        alto += 15.0
    alto += 14.0 * len(region.servicios)
    return max(alto, 32.0)


def _contiene(region: Region, hoja: Region | None) -> bool:
    """Si `hoja` es `region` o cuelga de ella."""
    while hoja is not None:
        if hoja is region:
            return True
        hoja = hoja.padre
    return False


def _arbol(lab: dict) -> Region:
    """El árbol de la numeración declarada, con su raíz deducida si hace falta."""
    import identity  # noqa: PLC0415

    regiones: list[Region] = []
    por_red: dict[str, Region] = {}
    for net in lab["networks"]:
        region = Region(net["name"], net.get("title") or net["name"],
                        identity._subred(net["address"]),
                        ipaddress.ip_network(net["address"], strict=False))
        regiones.append(region)
        por_red[net["name"]] = region
    for espacio in lab.get("address_spaces") or []:
        red = ipaddress.ip_network(espacio, strict=False)
        if any(red == r.cidr for r in regiones):
            # Un espacio que ya es una red declarada se dibuja una vez: la red manda,
            # que es la que tiene equipos y puerta.
            continue
        regiones.append(Region("espacio:" + str(red), _mascara(str(red)), str(red), red))

    for region in regiones:
        candidatos = [p for p in regiones
                      if p is not region and region.cidr.subnet_of(p.cidr)]
        if candidatos:
            region.padre = min(candidatos, key=lambda p: -p.prefijo)
            region.padre.hijas.append(region)

    raices = [r for r in regiones if r.padre is None]
    if len(raices) > 1:
        # Lo que comparten las raíces es la caja que las envuelve: 10.x.x.x cuando
        # conviven dos sedes bajo el mismo /8. Si no comparten nada (`/0`), no hay caja.
        for prefijo in range(min(r.prefijo for r in raices) - 1, 7, -1):
            prueba = ipaddress.ip_network(f"{raices[0].cidr.network_address}/{prefijo}",
                                          strict=False)
            if all(r.cidr.subnet_of(prueba) for r in raices):
                raiz = Region("espacio:" + str(prueba), _mascara(str(prueba)), "", prueba)
                raiz.hijas = sorted(raices, key=lambda r: (int(r.cidr.network_address),
                                                           r.prefijo))
                for hija in raiz.hijas:
                    hija.padre = raiz
                return raiz
    raiz = raices[0]
    raiz.hijas.sort(key=lambda r: (int(r.cidr.network_address), r.prefijo))
    return raiz


def _casa(node: dict, por_red: dict[str, Region]) -> tuple[Region | None, list[Region]]:
    """Dónde se dibuja un equipo: en el área más estrecha donde tiene pata.

    Un equipo con patas en varias redes hermanas —el router entre dos LAN— no vive
    en ninguna de ellas: vive en el pasillo que las une, y por eso se devuelve el
    padre y las hermanas que toca, para colocarlo entre las dos.
    """
    patas = [por_red[n] for n in node.get("networks") or [] if n in por_red]
    if not patas:
        return None, []
    estrecho = max(p.prefijo for p in patas)
    candidatas = [p for p in patas if p.prefijo == estrecho]
    unicas = list(dict.fromkeys(candidatas))
    if len(unicas) == 1:
        return unicas[0], []
    casa = unicas[0]
    while casa.padre and not all(_contiene(casa, otra) for otra in unicas):
        casa = casa.padre
    return casa, unicas


def _equipos_de(region: Region) -> list[str]:
    """Los equipos que viven en esa área o en lo que contiene."""
    dentro = list(region.nodos)
    for hija in region.hijas:
        dentro += _equipos_de(hija)
    return dentro


def _marcar_pasillos(raiz: Region, patas: dict[str, list[Region]]) -> None:
    """Marca el área que sirve de pasillo entre hermanas.

    Un área es pasillo si sus equipos vuelven a asomarse a dos o más hermanas: el
    tránsito entre dos sedes lo es, porque cada router de borde tiene una pata ahí y
    otra en su sede. Se dibuja encima y de lado a lado, y las patas bajan rectas.
    """
    for region in _todas(raiz):
        for hija in region.hijas:
            vecinas = set()
            for rol in _equipos_de(hija):
                for pata in patas.get(rol, []):
                    for hermana in region.hijas:
                        if hermana is not hija and _contiene(hermana, pata):
                            vecinas.add(id(hermana))
            if len(vecinas) >= 2:
                hija.espina = True


def _centrar_enchufes(regiones: list[Region], casa_de: dict[str, Region],
                      lab: dict) -> None:
    """El equipo que reparte —el switch, el router— al medio de su fila.

    Con el enchufe en un extremo, el cable al último equipo de la fila pasa por
    encima de los que hay en medio y el plano parece una cadena. En el centro, cada
    cable sale hacia su lado y no cruza a nadie.
    """
    grado: dict[str, int] = {}
    for link in lab.get("links") or []:
        a, z = link["a"]["node"], link["z"]["node"]
        if casa_de.get(a) is None or casa_de.get(a) is not casa_de.get(z):
            continue
        grado[a] = grado.get(a, 0) + 1
        grado[z] = grado.get(z, 0) + 1
    for region in regiones:
        if len(region.nodos) < 3:
            continue
        orden = sorted(region.nodos, key=lambda rol: -grado.get(rol, 0))
        if not grado:
            continue
        mitad = len(orden) // 2
        fila: list[str | None] = [None] * len(orden)
        fila[mitad] = orden[0]
        huecos = [i for i in range(len(orden)) if i != mitad]
        for rol, hueco in zip(orden[1:], huecos):
            fila[hueco] = rol
        region.nodos = [rol for rol in fila if rol is not None]


def _servicios(lab: dict, por_red: dict[str, Region]) -> None:
    """El rango que cada red reparte, escrito en la cabecera de su área."""
    import identity  # noqa: PLC0415

    for nodo in lab["nodes"]:
        for srv in (nodo.get("configure") or {}).get("dhcp_server") or []:
            region = por_red.get(srv.get("network") or "")
            if region is None:
                continue
            subred = identity._subred(str(region.cidr))
            rango = _rango_corto(srv.get("pool") or "", subred.replace(".x/", ".0/"))
            if rango:
                region.servicios.append(f"dhcp {rango}")


def _medir(region: Region) -> None:
    """Mide el área desde dentro hacia fuera: primero lo que contiene, luego ella."""
    region.cabecera = _mide_cabecera(region)
    for hija in region.hijas:
        _medir(hija)
    if not region.hijas:
        cuantas = max(len(region.nodos), 1)
        ancho_celda = CELDA_ANCHO
        if region.nodos:
            ancho_celda = max(ancho_celda, max(
                len(r) * 12.5 * 0.58 + 24 for r in region.nodos))
        region.ancho = 2 * M_REG + ancho_celda * cuantas
        region.alto = region.cabecera + MARGEN_ARRIBA + ALTO_EQUIPO + 30
        return
    fila, espina = _fila(region)
    ancho = max([sum(h.ancho for h in fila) + _huecos(region, fila)] +
                [h.ancho for h in espina] + [0])
    alto = region.cabecera + MARGEN_ARRIBA
    if espina:
        alto += max(h.alto for h in espina) + HUECO_REG
    alto += max([h.alto for h in fila] + [0])
    region.ancho = 2 * M_REG + ancho
    region.alto = alto + M_REG


def _fila(region: Region) -> tuple[list[Region], list[Region]]:
    espina = [h for h in region.hijas if h.espina]
    fila = [h for h in region.hijas if not h.espina]
    return fila, espina


def _huecos(region: Region, fila: list[Region]) -> float:
    """El aire entre las áreas de la fila: más ancho donde un equipo cruza de una a otra."""
    total = 0.0
    for i, hija in enumerate(fila[:-1]):
        cruza = any({una, otra} == {hija, fila[i + 1]}
                    for una, otra, _ in region.pasillos)
        total += HUECO_PASILLO if cruza else HUECO_REG
    return total


def _repartir(region: Region, x: float, y: float) -> None:
    """Asienta el área y todo lo que contiene, ya con su tamaño definitivo."""
    region.asentar(x, y)
    if not region.hijas:
        _repartir_equipos(region)
        return
    fila, espina = _fila(region)
    alto = y + region.cabecera + MARGEN_ARRIBA
    if espina:
        for caja in espina:
            # El pasillo ocupa todo el ancho: es el eje del dibujo, no una caja más.
            _estirar(caja, x + M_REG, alto, region.ancho - 2 * M_REG)
        alto += max(c.alto for c in espina) + HUECO_REG
    # La fila se centra en el área: un área más ancha que sus hijas no las deja
    # arrimadas a la izquierda, que se leería como si faltara algo a la derecha.
    ancho_fila = sum(h.ancho for h in fila) + _huecos(region, fila)
    cursor = x + (region.ancho - ancho_fila) / 2
    for i, hija in enumerate(fila):
        _repartir(hija, cursor, alto)
        cursor += hija.ancho
        if i < len(fila) - 1:
            cursor += HUECO_PASILLO if any(
                {una, otra} == {hija, fila[i + 1]} for una, otra, _ in region.pasillos
            ) else HUECO_REG
    _pasillos(region, fila)


def _estirar(region: Region, x: float, y: float, ancho: float) -> None:
    """Un área de lado a lado, con sus equipos repartidos por ese ancho."""
    region.ancho = max(ancho, region.ancho)
    region.asentar(x, y)
    if not region.hijas:
        _repartir_equipos(region)
    else:
        _repartir(region, x, y)


def _repartir_equipos(region: Region) -> None:
    """Los equipos, en fila bajo la cabecera, con el mismo aire entre ellos."""
    if not region.nodos:
        return
    ancho, alto = region.ancho, region.alto
    hueco = (ancho - 2 * M_REG) / len(region.nodos)
    for i, rol in enumerate(region.nodos):
        region.dentro[rol] = (region.x + M_REG + hueco * (i + 0.5),
                              region.y + alto - 30 - ALTO_EQUIPO / 2 + 18)


def _pasillos(region: Region, fila: list[Region]) -> None:
    """El equipo que une dos áreas hermanas, en el pasillo entre las dos."""
    for una, otra, rol in region.pasillos:
        if una in fila and otra in fila:
            izquierda, derecha = sorted((una, otra), key=lambda c: c.x)
            region.dentro[rol] = ((izquierda.x + izquierda.ancho + derecha.x) / 2,
                                  (izquierda.y + derecha.y) / 2 + izquierda.alto / 2)


def _plano_anidado(lab: dict) -> str:
    """El plano de topología: áreas dentro de áreas, hasta la red de cada equipo."""
    raiz = _arbol(lab)
    por_red = {r.nombre: r for r in _todas(raiz) if not r.nombre.startswith("espacio:")}
    por_nodo = {n["role"]: n for n in lab["nodes"]}
    _servicios(lab, por_red)
    regiones = _todas(raiz)

    patas: dict[str, list[Region]] = {}
    casa_de: dict[str, Region] = {}
    for nodo in lab["nodes"]:
        patas[nodo["role"]] = [por_red[n] for n in nodo.get("networks") or [] if n in por_red]
        casa, hermanas = _casa(nodo, por_red)
        if casa is None:
            continue
        casa.nodos.append(nodo["role"])
        casa_de[nodo["role"]] = casa
        if hermanas:
            casa.pasillos.append((hermanas[0], hermanas[1], nodo["role"]))
    _marcar_pasillos(raiz, patas)
    _centrar_enchufes(regiones, casa_de, lab)
    _medir(raiz)
    _repartir(raiz, 0.0, 0.0)

    def punto_de(rol: str) -> tuple[float, float]:
        for region in regiones:
            if rol in region.dentro:
                return region.dentro[rol]
        raise KeyError(rol)

    # --- las líneas -----------------------------------------------------------
    piezas: list[str] = []
    for region in regiones:
        piezas.append(_area(region, region.servicios, suave=bool(region.hijas)))
    cables: list[tuple[str, str]] = [
        (link["a"]["node"], link["z"]["node"]) for link in lab.get("links") or []
        # Un cable entre dos áreas ya lo dice la pata del área: dibujarlo además como
        # una diagonal de router a puesto cruza medio plano y no añade nada.
        if casa_de.get(link["a"]["node"]) is casa_de.get(link["z"]["node"])]
    patas_fuera: list[tuple[str, Region | None, Region]] = []
    for rol, suyas in patas.items():
        casa = next((r for r in regiones if rol in r.nodos), None)
        for pata in suyas:
            if rol in pata.dentro:
                # Ya está dentro: la pata la dibuja el borde del área, no una línea.
                continue
            patas_fuera.append((rol, casa, pata))

    textos: list[str] = []
    tipos = {n["role"]: n["type"] for n in lab["nodes"]}
    puntos: list[tuple[float, float]] = [(0.0, 0.0), (raiz.ancho, raiz.alto)]
    for region in regiones:
        for rol, (cx, cy) in region.dentro.items():
            piezas.append(_simbolo(tipos[rol], cx, cy))
            textos.append(_etiqueta(cx, cy, _que_dice(por_nodo[rol]), clase=tipos[rol],
                                    lado=_lado(rol, punto_de, cables)))
            # El nombre va al costado del símbolo y puede salirse del área: el lienzo
            # tiene que contarlo, o la última letra se corta en el borde del dibujo.
            puntos += [(cx - 96, cy - 34), (cx + 96, cy + 66)]

    for a, z in cables:
        piezas.append(_linea(punto_de(a), punto_de(z), SIMBOLO[tipos[a]],
                             SIMBOLO[tipos[z]]))
    # Las patas que salen del área donde vive el equipo van hasta el borde del área
    # que tocan: dentro no hay ningún equipo al que atar la línea.
    for rol, casa, pata in patas_fuera:
        piezas.append(_pata_de_area(punto_de(rol), pata, SIMBOLO[tipos[rol]]))

    xs = [p[0] for p in puntos]
    ys = [p[1] for p in puntos]
    minx, miny = min(xs), min(ys)
    ancho = max(xs) - minx + 2 * MARGEN
    alto = max(ys) - miny + 2 * MARGEN + CABECERA
    dx, dy = MARGEN - minx, MARGEN + CABECERA - miny
    return ("\n".join([
        (f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho:.0f}" height="{alto:.0f}" '
         f'viewBox="0 0 {ancho:.0f} {alto:.0f}" role="img" '
         f'aria-label="Plano de {_esc(lab["lab"])}">'),
        f'<rect width="{ancho:.0f}" height="{alto:.0f}" fill="#ffffff"/>',
        (f'<text x="{ancho / 2:.1f}" y="28" text-anchor="middle" font-family="{FUENTE}" '
         f'font-size="15" font-weight="650" fill="{TINTA}">{_esc(lab["lab"])}</text>'),
        (f'<text x="{ancho / 2:.1f}" y="45" text-anchor="middle" font-family="{FUENTE}" '
         f'font-size="11.5" fill="{TENUE}">'
         f'{_esc(" · ".join(_mascara(s) for s in lab.get("address_spaces") or []))}</text>'),
        f'<g transform="translate({dx:.1f},{dy:.1f})">',
        *piezas,
        *textos,
        "</g>",
        "</svg>",
        "",
    ]))


def _todas(raiz: Region) -> list[Region]:
    """La raíz y todo lo que cuelga de ella, en orden de dibujo: de fuera hacia dentro."""
    salida = [raiz]
    for hija in raiz.hijas:
        salida += _todas(hija)
    return salida


def _que_dice(nodo: dict) -> list[str]:
    """El nombre y sus direcciones, una por pata: lo que no cambia no se esconde."""
    direcciones: list[str] = []
    for red in nodo.get("networks") or []:
        direccion = _direccion_de(nodo, red if len(nodo.get("networks") or []) > 1 else None)
        if direccion and direccion not in direcciones:
            direcciones.append(direccion)
    if not direcciones:
        direccion = _direccion_de(nodo)
        if direccion:
            direcciones.append(direccion)
    return [nodo["role"], *direcciones]


def _lado(rol: str, punto_de, cables: list[tuple[str, str]]) -> str:
    """De qué lado cabe el nombre: el que más lejos queda de sus conexiones."""
    cx, cy = punto_de(rol)
    rumbos = []
    for a, z in cables:
        if a != rol and z != rol:
            continue
        otro = z if a == rol else a
        if otro.startswith("red:"):
            continue
        try:
            ox, oy = punto_de(otro)
        except KeyError:
            continue
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


def _pata_de_area(inicio: tuple[float, float], region: Region,
                  tam: tuple[float, float]) -> str:
    """La pata de un equipo al área que toca, por el pasillo y sin cruzar cajas.

    Una diagonal del router al rincón de un área atraviesa las áreas que haya en
    medio —y el plano acabaría diciendo que ese cable pasa por dentro de otro
    departamento—, así que la pata baja primero, corre por el pasillo que queda
    sobre las áreas y entra por el techo de la suya. Es como se cablea de verdad.
    """
    cx, cy = inicio
    x0, y0 = region.x, region.y
    x1, y1 = region.x + region.ancho, region.y + region.alto
    mitad = region.x + region.ancho / 2
    arriba = cy < y0
    if arriba or cy > y1:
        pasillo = y0 - 10 if arriba else y1 + 10
        salida = cy + tam[1] / 2 + 2 if arriba else cy - tam[1] / 2 - 2
        borde = y0 if arriba else y1
        return _codo([(cx, salida), (cx, pasillo), (mitad, pasillo), (mitad, borde)])
    # A la altura del área: se entra por el costado que mira al equipo.
    x = x0 if cx < x0 else x1
    y = min(max(cy, y0 + 26), y1 - 26)
    return _linea(inicio, (x, y), tam, (1.0, 1.0))


def _codo(puntos: list[tuple[float, float]]) -> str:
    """Una línea de varios tramos, en ángulo recto."""
    trazo = " ".join(f"{x:.1f},{y:.1f}" for x, y in puntos)
    return (f'<polyline points="{trazo}" fill="none" stroke="{LINEA}" '
            f'stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>')


def plano(lab: dict, modo: str = "topologia") -> str:
    """El SVG del plano. `modo` elige qué une cada línea: la jerarquía o el cable."""
    if modo == "topologia" and (lab.get("networks") or []):
        # La topología enseña la numeración como lo que es: áreas dentro de áreas.
        return _plano_anidado(lab)

    import identity  # noqa: PLC0415  (el módulo se importa desde tools/)

    profundidad = identity._profundidad(lab)
    principal = identity._principal(lab)
    nodos = lab["nodes"]
    por_rol = {n["role"]: n for n in nodos}
    salidas = [n for n in nodos if profundidad[n["role"]] == 0]

    def etiqueta(nodo: dict) -> list[str]:
        """Lo que se lee bajo el símbolo: el nombre y, si cabe, su dirección.

        Un equipo con pata en varias redes no lleva sus direcciones debajo —se
        amontonarían—: cada dirección vive en la cabecera del área que abre. En el
        cableado el nombre va solo: los puertos los dice cada punta de su cable.
        """
        # Lo que no cambia se escribe en los dos planos: un cableado con los equipos
        # mudos obliga a saltar al otro dibujo para saber quién es quién por dentro.
        # Lo que no cambia se escribe: una línea por pata con dirección. Un equipo con
        # varias redes lleva una por red, en el orden en que las declara; el que sale
        # por DHCP lo dice con esa palabra, que también es información.
        direcciones: list[str] = []
        for red in nodo.get("networks") or []:
            direccion = _direccion_de(nodo, red if len(nodo.get("networks") or []) > 1 else None)
            if direccion and direccion not in direcciones:
                direcciones.append(direccion)
        if not direcciones:
            direccion = _direccion_de(nodo)
            if direccion:
                direcciones.append(direccion)
        return [nodo["role"], *direcciones]

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
        # Las conexiones son los cables DECLARADOS (`links`). `after` dice el orden de
        # arranque, no quién está cableado con quién: dibujar por `after` inventaba
        # líneas entre equipos que no comparten ningún cable. `after` se sigue usando
        # para colocar —la cadena de salidas y las áreas—, pero no para conectar.
        for link in lab.get("links") or []:
            aristas.append((link["a"]["node"], link["z"]["node"]))
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

    # Servicios fijos que cada red tiene declarados: el rango que sirve su DHCP.
    servicios: dict[str, list[str]] = {}
    for nodo in nodos:
        for srv in (nodo.get("configure") or {}).get("dhcp_server") or []:
            red = srv.get("network")
            if not red or red not in cajas:
                continue
            subred = cajas[red].subred
            rango = _rango_corto(srv.get("pool") or "", subred.replace(".x/", ".0/"))
            if rango:
                servicios.setdefault(red, []).append(f"dhcp {rango}")

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
        piezas.append(_area(caja, servicios.get(caja.nombre, [])))
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
    ancho = max(xs) - minx + 2 * MARGEN
    alto = max(ys) - miny + 2 * MARGEN + CABECERA
    dx, dy = MARGEN - minx, MARGEN + CABECERA - miny

    espacios = ", ".join(identity._subred(s) for s in lab["address_spaces"])
    # El pie de figura dice lo que un plano no debe dejar adivinar: qué es cada área.
    return "\n".join([
        # Cada cadena va entre paréntesis: dentro de una lista, dos literales pegados
        # en líneas distintas se leen como una coma que falta, no como una frase
        # partida (ISC004 en ruff). El SVG del plano no cambia.
        (f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho:.0f}" height="{alto:.0f}" '
         f'viewBox="0 0 {ancho:.0f} {alto:.0f}" role="img" '
         f'aria-label="Plano de {_esc(lab["lab"])}">'),
        f'<rect width="{ancho:.0f}" height="{alto:.0f}" fill="#ffffff"/>',
        (f'<text x="{ancho / 2:.1f}" y="28" text-anchor="middle" font-family="{FUENTE}" '
         f'font-size="15" font-weight="650" fill="{TINTA}">{_esc(lab["lab"])}</text>'),
        (f'<text x="{ancho / 2:.1f}" y="45" text-anchor="middle" font-family="{FUENTE}" '
         f'font-size="11.5" fill="{TENUE}">{_esc(espacios)}</text>'),
        f'<g transform="translate({dx:.1f},{dy:.1f})">',
        *piezas,
        *textos,
        "</g>",
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


def _rango_corto(rango: str, subred: str) -> str:
    """El rango DHCP sin repetir lo que ya dice la subred: `10.44.1.100-199`."""
    desde, _, hasta = str(rango).partition("-")
    prefijo = subred.rsplit(".", 1)[0] + "."
    if hasta.startswith(prefijo) and desde.startswith(prefijo):
        return f"{desde}-{hasta[len(prefijo):]}"
    return str(rango)


def _area(caja: Caja, servicios: list[str] | None = None, suave: bool = False) -> str:
    """Una red: área translúcida con su nombre, su subred y quién le da puerta.

    La dirección con la que el router se asoma a la red se escribe aquí, en la
    cabecera del área, y no encima del cable: sobre la línea quedaba tapando el
    borde del área, que es justo lo que hay que ver.

    `suave` distingue un área que CONTIENE otras —un espacio de direcciones— de una
    red con equipos dentro: trazo discontinuo para la caja de fuera, para que se lea
    de un vistazo qué es un sitio y qué es una red.
    """
    textos = [
        f'<text x="{caja.x + 16:.1f}" y="{caja.y + 21:.1f}" font-family="{FUENTE}" '
        f'font-size="12.5" font-weight="650" fill="{EQUIPO_TRAZO}">{_esc(caja.titulo)}</text>',
    ]
    if caja.subred:
        textos.append(
            f'<text x="{caja.x + 16:.1f}" y="{caja.y + 36:.1f}" font-family="{FUENTE}" '
            f'font-size="10.5" fill="{TENUE}">{_esc(caja.subred)}</text>')
    # Lo que la red tiene montado de forma permanente —el rango que reparte— se escribe
    # en su cabecera. La puerta no: esa es la dirección del equipo que la toca, y va
    # escrita en el equipo, que es su dueño; repetirla aquí sólo añadiría ruido.
    fijos = list(servicios or [])
    for i, linea in enumerate(fijos):
        textos.append(f'<text x="{caja.x + 16:.1f}" y="{caja.y + 51 + i * 14:.1f}" '
                      f'font-family="{FUENTE}" font-size="10.5" fill="{EQUIPO_TRAZO}">'
                      f'{_esc(linea)}</text>')
    trazo = ' stroke-dasharray="7 5"' if suave else ''
    return "".join([
        (f'<rect x="{caja.x:.1f}" y="{caja.y:.1f}" width="{caja.ancho:.1f}" '
         f'height="{caja.alto:.1f}" rx="14" fill="{RED_RELLENO}" '
         f'fill-opacity="{0.03 if suave else 0.06}" '
         f'stroke="{RED_TRAZO}" stroke-width="1.4"{trazo}/>'),
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
    piezas = [(f'<line x1="{inicio[0]:.1f}" y1="{inicio[1]:.1f}" x2="{fin[0]:.1f}" '
               f'y2="{fin[1]:.1f}" stroke="{LINEA}" stroke-width="1.6" '
               f'stroke-linecap="round"/>')]
    # El paso con el que la etiqueta se separa del símbolo se acorta en cables cortos:
    # con 18 fijos, un cable de 46 px dejaba las dos etiquetas a 10 px del centro cada
    # una —20 de ancho— y se solapaban justo donde hay que leerlas. Se pide que los dos
    # centros queden a más de lo que mide una etiqueta (22 px, con holgura), y un mínimo
    # para que no se metan dentro del símbolo.
    paso = min(18.0, max(6.0, (largo - 22) / 2))
    for (px, py), (dx, dy), puerto in ((inicio, (ux, uy), puerto_a),
                                       (fin, (-ux, -uy), puerto_z)):
        # El puerto va SOBRE el cable, a un paso del símbolo: ahí no lo tapa el nombre
        # del equipo (que el plano aparta del rumbo de sus cables) ni la cabecera del
        # área, y se ve de qué punta del cable es sin leer nada más.
        tx, ty = px + dx * paso, py + dy * paso
        piezas += [
            (f'<rect x="{tx - 10:.1f}" y="{ty - 8:.1f}" width="20" height="16" rx="5" '
             f'fill="#ffffff" stroke="{EQUIPO_TRAZO}" stroke-width="1.1"/>'),
            (f'<text x="{tx:.1f}" y="{ty + 3.5:.1f}" text-anchor="middle" '
             f'font-family="{FUENTE}" font-size="10" font-weight="600" '
             f'fill="{EQUIPO_TRAZO}">p{puerto}</text>'),
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
