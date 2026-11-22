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


def _simbolo(tipo: str, cx: float, cy: float, escala: float = 1.0,
             rol: str = "") -> str:
    """El símbolo de esa clase, centrado en (cx, cy).

    Lleva su papel y su centro en atributos `data-*`: son la única forma de
    comprobar por programa que un router quedó a caballo de la red que le toca, sin
    leer el plano a ojo.
    """
    quien = f' data-rol="{_esc(rol)}"' if rol else ""
    return (f'<g{quien} data-x="{cx:.1f}" data-y="{cy:.1f}" '
            f'transform="translate({cx:.1f},{cy:.1f}) scale({escala})">'
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
HUECO_NUBE = 34       # aire entre la nube y la caja de la empresa
HUECO_PASILLO = 108   # hueco entre dos áreas que une un equipo: ahí cabe su símbolo
BANDA_PASILLO = 150   # pasillo lateral: por ahí bajan los cables, sin pisar cajas
ALTO_EQUIPO = 84      # la fila de equipos dentro de un área
PASO_CLIENTES = 84    # aire vertical entre dos clientes de la misma área
MARGEN_ARRIBA = 16


def _mascara(texto: str) -> str:
    """Cómo se lee una red en un plano: octetos de host en `x` y su prefijo.

    Una sola convención para todas las áreas —`10.20.55.x/24`, `10.x.x.x/10`,
    `203.0.113.x/30`—: con la máscara escrita unas veces y otras no, el que lee el
    plano no sabe si dos cajas hablan de la misma red o de un prefijo distinto.
    """
    red = ipaddress.ip_network(texto, strict=False)
    octetos = str(red.network_address).split(".")
    for i in range(red.prefixlen // 8, 4):
        octetos[i] = "x"
    return ".".join(octetos) + f"/{red.prefixlen}"


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
        self.alto_min = 0.0     # suelo que le pone la medida común de todas las redes
        self.ancho_min = 0.0
        self.padre: Region | None = None
        self.nodos: list[str] = []
        self.pasillos: list[tuple[Region, Region, str]] = []
        self.espina = False
        self.cabecera = 40.0
        self.servicios: list[str] = []
        # Una nube no es un área del cliente: es la red del proveedor y se dibuja como
        # tal. Y `enchufe` es el equipo que reparte dentro del área —el switch de
        # acceso—, que va en su propia fila arriba para que los cables entren por él.
        self.nube = False
        self.enchufe: str | None = None
        # A qué lado de esta área corre el pasillo por el que bajan los cables: por
        # ahí se asoman los routers de sus departamentos, así que sus cajas se
        # apartan al lado contrario y el pasillo queda libre.
        self.corredor: str | None = None
        # Una raíz sintética es el lienzo, no un área: si no comparten caja, no se pinta.
        self.sintetica = False

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
        # `shape: cloud` es una decisión de dibujo: la red se pinta como nube porque no
        # es un segmento del cliente, no porque el despliegue sea distinto.
        region.nube = net.get("shape") == "cloud"
        regiones.append(region)
        por_red[net["name"]] = region
    for espacio in lab.get("address_spaces") or []:
        red = ipaddress.ip_network(espacio, strict=False)
        if any(red == r.cidr for r in regiones):
            # Un espacio que ya es una red declarada se dibuja una vez: la red manda,
            # que es la que tiene equipos y puerta.
            continue
        # La caja del espacio se rotula como cualquier otra red —con `x` en los
        # octetos de host—, no con el `.0` de la dirección de red, que se lee como si
        # fuera la dirección de un equipo.
        regiones.append(Region("espacio:" + str(red), _mascara(str(red)),
                               _mascara(str(red)), red))

    for region in regiones:
        candidatos = [p for p in regiones
                      if p is not region and region.cidr.subnet_of(p.cidr)]
        if candidatos:
            region.padre = min(candidatos, key=lambda p: -p.prefijo)
            region.padre.hijas.append(region)

    raices = [r for r in regiones if r.padre is None]
    if len(raices) > 1:
        # Las raíces que comparten caja se agrupan: dos sedes bajo el mismo /8 son una
        # empresa, y la caja que las envuelve es ACME. La nube no entra nunca en esa
        # caja: representa el exterior, así que se queda fuera, al lado.
        tierra = [r for r in raices if not r.nube]
        nubes = [r for r in raices if r.nube]
        caja = None
        if len(tierra) > 1:
            for prefijo in range(min(r.prefijo for r in tierra) - 1, 7, -1):
                prueba = ipaddress.ip_network(
                    f"{tierra[0].cidr.network_address}/{prefijo}", strict=False)
                if all(r.cidr.subnet_of(prueba) for r in tierra):
                    caja = Region("espacio:" + str(prueba), _mascara(str(prueba)), "", prueba)
                    caja.hijas = sorted(tierra, key=lambda r: (int(r.cidr.network_address),
                                                              r.prefijo))
                    for hija in caja.hijas:
                        hija.padre = caja
                    break
        nuevas = ([caja] if caja else tierra) + nubes
        if len(nuevas) == 1:
            nuevas[0].hijas.sort(key=lambda r: (int(r.cidr.network_address), r.prefijo))
            return nuevas[0]
        # Todavía quedan raíces que no comparten caja: la raíz es el mundo, y el mundo
        # no se dibuja —el exterior no está dentro de ninguna de sus áreas.
        raiz = Region("espacio:0.0.0.0/0", "", "", ipaddress.ip_network("0.0.0.0/0"))
        raiz.sintetica = True
        raiz.hijas = sorted(nuevas, key=lambda r: (int(r.cidr.network_address), r.prefijo))
        for hija in raiz.hijas:
            hija.padre = raiz
        return raiz
    raiz = raices[0]
    raiz.hijas.sort(key=lambda r: (int(r.cidr.network_address), r.prefijo))
    return raiz


def _casa(node: dict, por_red: dict[str, Region]) -> tuple[Region | None, list[Region]]:
    """Dónde vive un equipo y por dónde se asoma.

    Vive en el área más estrecha que contiene TODAS sus patas; y devuelve, por cada
    pata, la hija de esa área por la que entra. Un router de borde tiene dos —la nube
    y la sede— y por eso no se dibuja dentro de ninguna de las dos: se dibuja a
    caballo de las dos, que es lo que hace un router.
    """
    patas = [por_red[n] for n in node.get("networks") or [] if n in por_red]
    unicas = list(dict.fromkeys(patas))
    if not unicas:
        return None, []
    casa = unicas[0]
    while casa.padre and not all(_contiene(casa, otra) for otra in unicas):
        casa = casa.padre
    grupos: list[Region] = []
    for pata in unicas:
        if pata is casa:
            hija = casa
        else:
            hija = pata
            while hija.padre is not None and hija.padre is not casa:
                hija = hija.padre
        if hija not in grupos:
            grupos.append(hija)
    return casa, grupos


def _entre(una: Region, otra: Region) -> tuple[float, float]:
    """El punto donde dos áreas se tocan: ahí se dibuja el equipo que las une.

    Un router no está dentro de la red que conecta, está en el borde: media caja en
    cada lado. Se busca el tramo en el que las dos áreas se miran —el solape de sus
    rectángulos— y se pone en su mitad.
    """
    if _contiene(una, otra) or _contiene(otra, una):
        # Una dentro de otra: no hay «aire entre medias» donde ponerlo. Se pone en el
        # borde de la de dentro que mira al exterior —arriba, que es donde el área
        # grande tiene su cabecera—, así que el router se apoya en la frontera de las
        # dos y no en mitad de ninguna.
        dentro = otra if _contiene(una, otra) else una
        return dentro.x + dentro.ancho / 2, dentro.y
    x0, x1 = max(una.x, otra.x), min(una.x + una.ancho, otra.x + otra.ancho)
    y0, y1 = max(una.y, otra.y), min(una.y + una.alto, otra.y + otra.alto)
    if una.y + una.alto <= otra.y or otra.y + otra.alto <= una.y:
        # Una encima de otra: el corte es horizontal, en el aire que las separa.
        arriba, abajo = sorted((una, otra), key=lambda r: r.y)
        corte = (arriba.y + arriba.alto + abajo.y) / 2
        if x1 > x0:
            return (x0 + x1) / 2, corte
        return (arriba.x + arriba.ancho + abajo.x) / 2, corte
    # Una al lado de otra: el corte es vertical.
    izquierda, derecha = sorted((una, otra), key=lambda r: r.x)
    corte = (izquierda.x + izquierda.ancho + derecha.x) / 2
    if y1 > y0:
        return corte, (y0 + y1) / 2
    return corte, (izquierda.y + izquierda.alto + derecha.y) / 2


def _centro_de_lo_suyo(rol: str, patas: dict[str, list[Region]],
                       por_red: dict[str, Region]) -> float:
    """Por dónde cae un equipo: el centro de sus áreas, sin contar la nube.

    Sirve para ordenar dos equipos que comparten frontera: el que mira a la izquierda
    se dibuja a la izquierda, aunque la frontera sea la misma.
    """
    centros = [p.x + p.ancho / 2 for p in patas.get(rol) or [] if not p.nube]
    return sum(centros) / len(centros) if centros else 0.0


def _equipos_de(region: Region) -> list[str]:
    """Los equipos que viven en esa área o en lo que contiene."""
    dentro = list(region.nodos)
    for hija in region.hijas:
        dentro += _equipos_de(hija)
    return dentro


def _marcar_pasillos(raiz: Region, cruces: dict[str, list[Region]]) -> None:
    """Marca las áreas que se dibujan como banda arriba, con lo demás debajo.

    Dos casos. La nube del proveedor, siempre: no cuelga de las sedes, las sedes
    cuelgan de ella. Y el área que varios equipos cruzan hacia hermanas distintas —el
    core de una sede, al que se asoman los tres routers de departamento—, porque si se
    dibujara al lado de los departamentos sólo uno de los tres routers quedaría en su
    frontera y los otros dos tendrían que cruzar el área del vecino.
    """
    for region in _todas(raiz):
        for hija in region.hijas:
            if hija.nube:
                hija.espina = True
                continue
            # Dos equipos distintos, cada uno asomándose a otra hermana: es un reparto
            # —el core de una sede—. Un solo equipo que toca tres áreas a la vez es un
            # firewall, y ese se dibuja en medio de las tres, no como banda.
            quienes: set[str] = set()
            hermanas: set[int] = set()
            for rol, grupos in cruces.items():
                if hija not in grupos:
                    continue
                for otro in grupos:
                    if otro is not hija and otro in region.hijas:
                        quienes.add(rol)
                        hermanas.add(id(otro))
            if len(quienes) >= 2 and len(hermanas) >= 2:
                hija.espina = True


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
    """Mide el árbol y deja todas las redes del mismo tamaño.

    Dos redes con el mismo contenido pero de sitios distintos deben salir iguales: si
    una sede apila tres departamentos altos y la otra tres bajos, las dos cajas de sede
    acaban a la misma altura pero la última red de una queda muy por encima de la de al
    lado —el pie del plano, descosido—. Con un suelo común, todas las redes miden lo
    mismo y el pie queda a plomo.
    """
    _medir_region(region)
    hojas = [r for r in _todas(region) if not r.hijas and not r.nube]
    if not hojas:
        return
    alto = max(r.alto for r in hojas)
    ancho = max(r.ancho for r in hojas)
    if any(abs(r.alto - alto) > 0.5 or abs(r.ancho - ancho) > 0.5 for r in hojas):
        for hoja in hojas:
            hoja.alto_min, hoja.ancho_min = alto, ancho
        _medir_region(region)


def _medir_region(region: Region) -> None:
    """Mide el área desde dentro hacia fuera: primero lo que contiene, luego ella."""
    region.cabecera = 0.0 if region.sintetica else _mide_cabecera(region)
    en_fila = [h for h in region.hijas if not h.espina]
    for i, hija in enumerate(en_fila):
        # El pasillo de una sede va por el lado que mira al centro del dibujo: las
        # cajas se arriman al borde de fuera y los cables bajan por dentro, que es por
        # donde va el router que las une.
        hija.corredor = "derecha" if i < len(en_fila) / 2 else "izquierda"
    for hija in region.hijas:
        _medir_region(hija)
    if not region.hijas:
        # El equipo que reparte va en su propia fila: los cables del exterior entran
        # por él y no por debajo de los demás equipos del área.
        fila = [r for r in region.nodos if r != region.enchufe]
        ancho_celda = CELDA_ANCHO
        if fila:
            ancho_celda = max(ancho_celda, max(
                len(r) * 12.5 * 0.58 + 24 for r in fila))
        if region.enchufe and fila:
            # Con switch, la caja tiene dos columnas: él a un lado y los clientes en
            # columna al otro. Medida como una fila de todos, sobraba ancho y faltaba
            # alto: el último cliente se salía por el suelo del área.
            region.ancho = 2 * M_REG + ancho_celda * 2
            region.alto = (region.cabecera + MARGEN_ARRIBA
                           + max(ALTO_EQUIPO, PASO_CLIENTES * (len(fila) - 1) + ALTO_EQUIPO)
                           + 26)
        else:
            region.ancho = 2 * M_REG + ancho_celda * max(len(region.nodos), 1)
            # Una sola fila de equipos: el switch a un extremo y los clientes al otro.
            region.alto = region.cabecera + MARGEN_ARRIBA + ALTO_EQUIPO + 26
        if region.nube:
            # Una nube con el alto de una fila de equipos es una caja estrecha. Y sus
            # equipos se dibujan a caballo del borde, así que necesitan aire dentro.
            region.alto = max(region.alto, 170.0)
            region.ancho = max(region.ancho, 300.0)
        region.alto = max(region.alto, region.alto_min)
        region.ancho = max(region.ancho, region.ancho_min)
        return
    fila, espina = _fila(region)
    if len(fila) >= 3:
        # Tres áreas hermanas o más se apilan: puestas de lado a lado, tres
        # departamentos caben en cajas estrechas donde los nombres se pelean, y la
        # sede sale apaisada como un cartel. Apiladas, cada una es una banda ancha y
        # se lee de arriba abajo, que es como se lee una sede.
        for hija in fila:
            hija.ancho = max(h.ancho for h in fila)
            # Y del mismo alto: apiladas con altos distintos, la última de una sede
            # acaba más abajo que la de al lado y el pie del plano queda descosido.
            hija.alto = max(h.alto for h in fila)
        ancho = max([h.ancho for h in fila] + [h.ancho for h in espina] + [0])
        if region.corredor:
            ancho += BANDA_PASILLO
    else:
        if len(fila) > 1:
            for hija in fila:
                hija.alto = max(h.alto for h in fila)
        ancho = max([sum(h.ancho for h in fila) + _huecos(region, fila)] +
                    [h.ancho for h in espina] + [0])
    alto = region.cabecera + MARGEN_ARRIBA
    if region.nodos:
        # El switch de núcleo del área va en su propia fila, encima de las áreas que
        # dependen de ella. Si el alto no la cuenta, esas áreas se salen por el suelo
        # y el dibujo acaba siendo un amasijo de cajas encajadas a la fuerza.
        alto += ALTO_EQUIPO + 12
    if espina:
        for caja in espina:
            # La nube es el exterior: se dibuja separada de la caja de la empresa y con
            # aire, para que se lea que está FUERA. Pegada al borde, la nube parece una
            # sala más de la casa y los routers de borde quedan metidos en la red
            # privada, que es justo lo que no son.
            alto += caja.alto + (HUECO_NUBE if caja.nube else HUECO_REG)
    if len(fila) >= 3:
        alto += sum(h.alto for h in fila) + HUECO_REG * (len(fila) - 1)
    else:
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
    if region.nodos:
        hueco = region.ancho / (len(region.nodos) + 1)
        for i, rol in enumerate(region.nodos):
            region.dentro[rol] = (x + hueco * (i + 1), alto + ALTO_EQUIPO / 2)
        alto += ALTO_EQUIPO + 12
    if espina:
        # Las bandas se apilan de arriba abajo; si hubiera más de una, comparten el
        # ancho del área y ninguna tapa a la de al lado.
        for caja in espina:
            if caja.nube:
                # La nube es el exterior, no una banda del dibujo: se queda pequeña y
                # centrada. Estirada de lado a lado dejaría de parecer una nube.
                _repartir(caja, x + (region.ancho - caja.ancho) / 2, alto)
            else:
                # El pasillo ocupa todo el ancho: es el eje del dibujo, no una caja más.
                _estirar(caja, x + M_REG, alto, region.ancho - 2 * M_REG)
            alto += caja.alto + (HUECO_NUBE if caja.nube else HUECO_REG)
    # La fila se centra en el área: un área más ancha que sus hijas no las deja
    # arrimadas a la izquierda, que se leería como si faltara algo a la derecha.
    if len(fila) >= 3:
        banda = BANDA_PASILLO if region.corredor else 0
        borde = x + M_REG + (0 if region.corredor == "derecha" else banda)
        for hija in fila:
            _repartir(hija, borde, alto)
            alto += hija.alto + HUECO_REG
    else:
        ancho_fila = sum(h.ancho for h in fila) + _huecos(region, fila)
        cursor = x + (region.ancho - ancho_fila) / 2
        for i, hija in enumerate(fila):
            _repartir(hija, cursor, alto)
            cursor += hija.ancho
            if i < len(fila) - 1:
                cursor += HUECO_PASILLO if any(
                    {una, otra} == {hija, fila[i + 1]} for una, otra, _ in region.pasillos
                ) else HUECO_REG


def _estirar(region: Region, x: float, y: float, ancho: float) -> None:
    """Un área de lado a lado, con sus equipos repartidos por ese ancho."""
    region.ancho = max(ancho, region.ancho)
    region.asentar(x, y)
    if not region.hijas:
        _repartir_equipos(region)
    else:
        _repartir(region, x, y)


def _repartir_equipos(region: Region) -> None:
    """Los equipos del área, en una fila: el switch al extremo que mira a su router.

    El switch de acceso es la puerta del área, y el cable que le llega viene del
    router que está a caballo del borde. Ponerlo en el extremo de ese borde deja el
    cable corto y sin cruzarse con los clientes, que se quedan al otro lado.
    """
    if not region.nodos:
        return
    fila = list(region.nodos)
    if region.enchufe:
        # El corredor de la casa dice por dónde entra el cable: el switch va a ese
        # lado, no al que le toque por orden de declaración.
        lado = getattr(region.padre, "corredor", None) if region.padre else None
        if lado == "derecha":
            fila = [r for r in fila if r != region.enchufe] + [region.enchufe]
        else:
            fila = [region.enchufe] + [r for r in fila if r != region.enchufe]
    if not region.enchufe:
        y = region.y + region.cabecera + MARGEN_ARRIBA + ALTO_EQUIPO / 2
        hueco = (region.ancho - 2 * M_REG) / len(fila)
        for i, rol in enumerate(fila):
            region.dentro[rol] = (region.x + M_REG + hueco * (i + 0.5), y)
        return
    # Con switch en el área, los clientes van en columna a su lado: en fila, el cable
    # del switch al cliente del fondo pasa POR ENCIMA del cliente de en medio y el
    # plano dibuja una cadena de equipos donde hay una estrella.
    lado = getattr(region.padre, "corredor", None) if region.padre else None
    fila = [r for r in fila if r != region.enchufe]
    ancho_celda = (region.ancho - 2 * M_REG) / 2
    x_switch = region.x + region.ancho - M_REG - ancho_celda / 2 if lado == "derecha" \
        else region.x + M_REG + ancho_celda / 2
    x_clientes = region.x + M_REG + ancho_celda / 2 if lado == "derecha" \
        else region.x + region.ancho - M_REG - ancho_celda / 2
    medio = region.y + region.cabecera + MARGEN_ARRIBA + (region.alto - region.cabecera
                                                          - MARGEN_ARRIBA - 26) / 2
    region.dentro[region.enchufe] = (x_switch, medio)
    paso = PASO_CLIENTES
    alto_fila = paso * (len(fila) - 1)
    for i, rol in enumerate(fila):
        region.dentro[rol] = (x_clientes, medio - alto_fila / 2 + paso * i)


def _plano_anidado(lab: dict) -> str:
    """El plano de topología: áreas dentro de áreas, y cada equipo a caballo de las suyas."""
    raiz = _arbol(lab)
    por_red = {r.nombre: r for r in _todas(raiz) if not r.nombre.startswith("espacio:")}
    por_nodo = {n["role"]: n for n in lab["nodes"]}
    _servicios(lab, por_red)
    regiones = _todas(raiz)

    patas: dict[str, list[Region]] = {}
    casa_de: dict[str, Region] = {}
    cruces: dict[str, list[Region]] = {}
    for nodo in lab["nodes"]:
        patas[nodo["role"]] = [por_red[n] for n in nodo.get("networks") or [] if n in por_red]
        casa, grupos = _casa(nodo, por_red)
        if casa is None:
            continue
        casa_de[nodo["role"]] = casa
        if len(grupos) == 1:
            casa.nodos.append(nodo["role"])
            if nodo["type"] == "switch" and casa.enchufe is None:
                # El switch de acceso es la puerta del área: los cables entran por él.
                casa.enchufe = nodo["role"]
            continue
        # A caballo: el router no vive en ninguna de las dos áreas, vive en su borde.
        cruces[nodo["role"]] = grupos
        if all(g in casa.hijas for g in grupos[:2]):
            # Dos hermanas en la misma fila: se separan para que quepa el símbolo.
            casa.pasillos.append((grupos[0], grupos[1], nodo["role"]))
    _marcar_pasillos(raiz, cruces)
    _medir(raiz)
    _repartir(raiz, 0.0, 0.0)
    # Dos equipos pueden compartir frontera —los dos routers de borde, sin ir más
    # lejos—: se reparten a lo largo de ella en vez de dibujarse uno encima del otro.
    por_frontera: dict[tuple[int, int], list[str]] = {}
    for rol, grupos in cruces.items():
        clave = tuple(sorted((id(grupos[0]), id(grupos[1]))))
        por_frontera.setdefault(clave, []).append(rol)
    for rol, grupos in cruces.items():
        # Un equipo se dibuja a caballo de dos áreas; con tres o más patas se elige la
        # primera pareja —el símbolo no puede estar en tres bordes a la vez— y las
        # demás se alcanzan por su cable, que es lo que de verdad las une.
        una, otra = grupos[0], grupos[1]
        casa = casa_de[rol]
        if una.nube or otra.nube:
            # El router de borde no flota en el aire que separa la nube de la empresa:
            # se apoya en la frontera de la empresa, que es donde acaba la red propia,
            # y a la altura de SU sede. Las dos sedes tienen su propia salida, así que
            # no pueden acabar los dos routers en el mismo punto del borde.
            dentro = otra if una.nube else una
            suya = [q for q in patas.get(rol) or [] if not q.nube]
            x = (suya[0].x + suya[0].ancho / 2) if suya else dentro.x + dentro.ancho / 2
            repartible = False
            # El router de borde tiene una pata en su sede y otra en Internet: va a
            # caballo del techo de SU SEDE, no del techo de la empresa. Puesto en el
            # borde de la caja grande, no interseca ninguna de las dos redes que une.
            caja = suya[0] if suya else dentro
            while caja.padre is not None and not caja.padre.sintetica:
                caja = caja.padre
            y = (suya[0].y if suya else caja.y)
        elif _contiene(una, otra) or _contiene(otra, una):
            # Una dentro de otra: el router se apoya en el costado de la de dentro que
            # mira al pasillo de la casa. En el techo chocaría con su cabecera, y ahí
            # arriba está el switch de núcleo.
            dentro = otra if _contiene(una, otra) else una
            lado = casa.corredor
            x = (dentro.x + dentro.ancho) if lado == "derecha" else dentro.x
            y = dentro.y + dentro.alto / 2
            repartible = False
            repartible = False
        else:
            x, y = _entre(una, otra)
            repartible = True
        hermanos = por_frontera[tuple(sorted((id(una), id(otra))))]
        # Sólo se reparten los que se colocaron en mitad del aire entre dos áreas: los
        # que se apoyan en una frontera ya saben dónde van —cada sede tiene la suya— y
        # repartirlos los amontonaría en el centro del dibujo.
        if repartible and len(hermanos) > 1:
            # El orden es el de la red que hay debajo de cada uno: izquierda y derecha
            # salen donde uno espera encontrarlas.
            hermanos = sorted(hermanos, key=lambda r: _centro_de_lo_suyo(r, patas, por_red))
            comun = (max(una.x, otra.x), min(una.x + una.ancho, otra.x + otra.ancho))
            if comun[1] > comun[0]:
                paso = (comun[1] - comun[0]) / (len(hermanos) + 1)
                x = comun[0] + paso * (hermanos.index(rol) + 1)
            else:
                comun = (max(una.y, otra.y), min(una.y + una.alto, otra.y + otra.alto))
                paso = (comun[1] - comun[0]) / (len(hermanos) + 1)
                y = comun[0] + paso * (hermanos.index(rol) + 1)
        casa_de[rol].dentro[rol] = (x, y)

    def punto_de(rol: str) -> tuple[float, float]:
        for region in regiones:
            if rol in region.dentro:
                return region.dentro[rol]
        raise KeyError(rol)

    # --- los cables -----------------------------------------------------------
    # Cada cable es un cable: une dos puertos y dice cuáles. Lo único que no se dibuja
    # así es la nube, que no es un equipo: cada router se asoma a ella por su cuenta,
    # y por eso entre las dos sedes no hay una línea, hay dos patas a Internet.
    tipos = {n["role"]: n["type"] for n in lab["nodes"]}
    cables: list[tuple[str, int, str, int]] = []
    nubes: dict[str, list[tuple[str, int]]] = {}
    for link in lab.get("links") or []:
        a, z = link["a"], link["z"]
        redes = por_nodo[a["node"]].get("networks") or []
        red = por_red.get(redes[a["port"] - 1]) if a["port"] <= len(redes) else None
        if red is not None and red.nube:
            nubes.setdefault(red.nombre, []).extend([(a["node"], a["port"]),
                                                     (z["node"], z["port"])])
            continue
        cables.append((a["node"], a["port"], z["node"], z["port"]))

    piezas: list[str] = []
    for region in regiones:
        piezas.append(_area(region, region.servicios, suave=bool(region.hijas)))

    # El cable que baja de un área a otra corre por el pasillo que queda sobre las
    # áreas de destino, no en diagonal: una diagonal cruza las áreas que haya en medio
    # y el plano acabaría diciendo que ese cable pasa por dentro de otro departamento.
    corredores: dict[int, int] = {}
    salidas: dict[str, list[int]] = {}
    for rol_a, puerto_a, _z, _pz in cables:
        salidas.setdefault(rol_a, []).append(puerto_a)

    def cable_entre(rol_a, puerto_a, rol_z, puerto_z) -> str:
        pa, pz = punto_de(rol_a), punto_de(rol_z)
        ta, tz = SIMBOLO[tipos[rol_a]], SIMBOLO[tipos[rol_z]]
        casa_a, casa_z = casa_de[rol_a], casa_de[rol_z]
        if casa_a is casa_z:
            casa = casa_a
            # Si el cable va en recta y hay otro equipo del área en medio, la recta lo
            # atraviesa y el plano dibuja una cadena donde hay dos cables al switch: se
            # rodea por el lado que queda libre.
            if not casa.hijas:
                otros = [casa.dentro[r] for r in casa.nodos
                         if r not in (rol_a, rol_z) and r in casa.dentro]
                x0, x1 = sorted((pa[0], pz[0]))
                y0, y1 = sorted((pa[1], pz[1]))
                en_medio = [q for q in otros
                            if x0 - 20 <= q[0] <= x1 + 20 and y0 - 20 <= q[1] <= y1 + 20]
                if en_medio:
                    centro = casa.dentro.get(casa.enchufe) if casa.enchufe else None
                    if abs(pa[0] - pz[0]) < abs(pa[1] - pz[1]):
                        # vertical: se aparta en horizontal, hacia fuera del switch
                        lado = -1 if (centro and centro[0] < pa[0]) else 1
                        desvio = lado * 40
                        if not (casa.x + 25 < pa[0] + desvio < casa.x + casa.ancho - 25):
                            desvio = -desvio
                        px = min(max(pa[0] + desvio, casa.x + 25),
                                 casa.x + casa.ancho - 25)
                        return "".join([
                            _codo([(pa[0], pa[1]), (px, pa[1]), (px, pz[1]), (pz[0], pz[1])]),
                            _puerto(px, pa[1] + 12, puerto_a, arriba=False),
                            _puerto(px, pz[1] - 12, puerto_z, arriba=True),
                        ])
                    # horizontal: se aparta por debajo, que el techo lo ocupa la cabecera
                    py = min(pa[1] + 40, casa.y + casa.alto - 26)
                    return "".join([
                        _codo([(pa[0], pa[1]), (pa[0], py), (pz[0], py), (pz[0], pz[1])]),
                        _puerto(pa[0] + 12, py, puerto_a, arriba=False),
                        _puerto(pz[0] - 12, py, puerto_z, arriba=False),
                    ])
            # Dos equipos de la misma área pero en plantas distintas —el switch de
            # núcleo arriba y un router en el borde de un departamento— se unen por el
            # pasillo: en diagonal, el cable atravesaría el departamento que hay en
            # medio y el plano diría que ese cable pasa por dentro de otra red.
            if (casa.corredor and casa.hijas
                    and abs(pa[0] - pz[0]) > 8 and abs(pa[1] - pz[1]) > 8):
                # El carril va por el borde exterior del pasillo: los nombres de los
                # routers se quedan entre su símbolo y el carril, y no los tacha nadie.
                lane = (casa.x + casa.ancho - 18 if casa.corredor == "derecha"
                        else casa.x + 18)
                # Cada cable baja por su propio carril y sale del switch por su altura:
                # compartiendo carril, tres cables se dibujan como uno solo que se
                # ramifica, y un plano dice que hay tres enlaces, no un bus.
                suyos = sorted(salidas.get(rol_a) or [puerto_a])
                centro = (len(suyos) - 1) / 2
                desvio = (suyos.index(puerto_a) - centro) * 13
                lane += desvio
                # Se sale por el lado que mira al pasillo: por el otro, el puerto se
                # escribe encima del nombre del propio switch.
                salida_x = (pa[0] + ta[0] / 2 + 3 if casa.corredor == "derecha"
                            else pa[0] - ta[0] / 2 - 3)
                y_salida = pa[1] + desvio
                return "".join([
                    _codo([(pa[0], pa[1]), (salida_x, pa[1]),
                           (salida_x + 12, y_salida), (lane, y_salida),
                           (lane, pz[1]), (pz[0], pz[1])]),
                    _puerto(salida_x + 6, y_salida, puerto_a, arriba=False),
                    _puerto(lane, pz[1] - 4, puerto_z, arriba=True),
                ])
            return _linea(pa, pz, ta, tz, puerto_a, puerto_z)
        if abs(pz[1] - pa[1]) < 40:
            return _linea(pa, pz, ta, tz, puerto_a, puerto_z)
        abajo = pz[1] > pa[1]
        caja = casa_z if abajo else casa_a
        corredor = corredores.get(id(caja), 0)
        corredores[id(caja)] = corredor + 1
        y = (caja.y - 10 - 7 * corredor) if abajo else (caja.y + caja.alto + 10 + 7 * corredor)
        salida = pa[1] + (ta[1] / 2 + 2) * (1 if abajo else -1)
        entrada = pz[1] - (tz[1] / 2 + 2) * (1 if abajo else -1)
        # Las bajadas de un mismo equipo salen por puntos distintos: si salieran todas
        # del mismo, el plano dibujaría un solo cable donde hay tres.
        # Cada bajada sale por su punto: la primera por la izquierda, la última por la
        # derecha. Si salieran todas del centro, el plano dibujaría un cable donde hay
        # tres y no se sabría qué puerto va a qué departamento.
        suyos = sorted(salidas.get(rol_a) or [puerto_a])
        centro = (len(suyos) - 1) / 2
        desvio = (suyos.index(puerto_a) - centro) * 26
        return "".join([
            _codo([(pa[0] + desvio, salida), (pa[0] + desvio, y),
                   (pz[0], y), (pz[0], entrada)]),
            _puerto(pa[0] + desvio, salida, puerto_a, arriba=not abajo),
            _puerto(pz[0], entrada, puerto_z, arriba=abajo),
        ])

    for rol_a, puerto_a, rol_z, puerto_z in cables:
        piezas.append(cable_entre(rol_a, puerto_a, rol_z, puerto_z))

    # La nube no tiene equipos: cada router se asoma a ella con su pata y su puerto.
    for nombre, asomos in nubes.items():
        nube = por_red[nombre]
        for i, (rol, puerto) in enumerate(asomos):
            piezas.append(_pata_a_nube(punto_de(rol), nube, SIMBOLO[tipos[rol]], puerto, i))

    # Una red sin equipos nuestros se alcanza con una pata hasta su borde: dentro no
    # hay a qué atar la línea.
    for rol, suyas in patas.items():
        for pata in suyas:
            if rol in pata.dentro or pata.nube:
                continue
            px, py = punto_de(rol)
            if pata.x <= px <= pata.x + pata.ancho and pata.y <= py <= pata.y + pata.alto:
                # El equipo ya está dentro del área: la pata no hay que dibujarla.
                continue
            if not _equipos_de(pata):
                piezas.append(_pata_de_area((px, py), pata, SIMBOLO[tipos[rol]]))

    textos: list[str] = []
    cables_planos = [(a, z) for a, _, z, _ in cables]
    puntos: list[tuple[float, float]] = [(0.0, 0.0), (raiz.ancho, raiz.alto)]
    for region in regiones:
        for rol, (cx, cy) in region.dentro.items():
            piezas.append(_simbolo(tipos[rol], cx, cy, rol=rol))
            lineas = _que_dice(por_nodo[rol])
            textos.append(_etiqueta(cx, cy, lineas, clase=tipos[rol],
                                    lado=_lado(rol, punto_de, cables_planos,
                                               caja=region if not region.sintetica else None,
                                               ancho_etiqueta=_ancho_etiqueta(lineas))))
            # El nombre va al costado del símbolo y puede salirse del área: el lienzo
            # tiene que contarlo, o la última letra se corta en el borde del dibujo.
            puntos += [(cx - 96, cy - 34), (cx + 96, cy + 66)]

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


def _lado(rol: str, punto_de, cables: list[tuple[str, str]],
          caja: Region | None = None, ancho_etiqueta: float = 96.0) -> str:
    """De qué lado cabe el nombre: el que más lejos queda de sus conexiones.

    `caja` es el área donde vive el equipo: un lado que deja el nombre fuera de su
    caja no vale, por mucho aire que tenga. Era lo que pasaba con la dirección de un
    servidor en la columna de la derecha, escrita cruzando el borde del departamento.
    """
    cx, cy = punto_de(rol)

    def dentro_del_lado(lado: str) -> bool:
        if caja is None:
            return True
        if lado == "derecha":
            return cx + 33 + ancho_etiqueta <= caja.x + caja.ancho
        if lado == "izquierda":
            return cx - 33 - ancho_etiqueta >= caja.x
        if lado == "abajo":
            return cy + 37 + 12 <= caja.y + caja.alto
        return cy - 37 - 12 >= caja.y

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
    mejor, aire = "abajo", -10.0
    for candidato, (ux, uy) in (("abajo", (0, 1)), ("derecha", (1, 0)),
                                ("izquierda", (-1, 0)), ("arriba", (0, -1))):
        hueco = min(1 - (ux * ex + uy * ey) for ex, ey in rumbos)
        if not dentro_del_lado(candidato):
            hueco -= 10.0   # sacar el nombre de su caja es peor que pisar un cable
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


def _puerto(x: float, y: float, numero: int, arriba: bool = True) -> str:
    """El número del puerto, junto al cable y pegado a su equipo.

    Sin esto un switch es una caja con líneas: no se sabe por dónde entra cada cable,
    y el plano deja de servir para cablear.
    """
    dy = -6 if arriba else 12
    return (f'<text x="{x + 6:.1f}" y="{y + dy:.1f}" font-family="{FUENTE}" '
            f'font-size="9" fill="{TENUE}">p{numero}</text>')


def _pata_a_nube(inicio: tuple[float, float], region: Region,
                 tam: tuple[float, float], puerto: int, sitio: int = 0) -> str:
    """La pata del router a la nube, por el pasillo y entrando por la base.

    La nube es pequeña y está centrada, así que los dos routers no caen debajo de
    ella: si la pata subiera en vertical, acabaría en el aire y el plano diría que la
    sede no tiene salida. Sube, corre por el pasillo que queda bajo la nube y entra
    por su base, cada sede por su lado.
    """
    cx, cy = inicio
    arranque = cy - tam[1] / 2 - 2
    base = region.y + region.alto - 8
    carril = base + max(10.0, (arranque - base) / 2)
    centro = region.x + region.ancho / 2
    destino = centro - 34 if sitio % 2 == 0 else centro + 34
    # El puerto se escribe en el tramo horizontal, en el aire que queda entre la sede
    # y la nube: pegado al router, caía justo bajo su propio nombre y sus direcciones.
    medio = cx + (destino - cx) * 0.5
    return "".join([
        _codo([(cx, arranque), (cx, carril), (destino, carril), (destino, base)]),
        (f'<text x="{medio:.1f}" y="{carril - 5:.1f}" font-family="{FUENTE}" '
         f'font-size="9" fill="{TENUE}">p{puerto}</text>'),
    ])


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
            piezas.append(_simbolo(nodo["type"], cx, cy, rol=nodo["role"]))
            textos.append(_etiqueta(cx, cy, etiqueta(nodo), clase=nodo["type"],
                                    lado=lado(rol)))
            puntos += [(cx - 70, cy - 30), (cx + 70, cy + 56)]

    for rol, (cx, cy) in posiciones.items():
        piezas.append(_simbolo(por_rol[rol]["type"], cx, cy, rol=rol))
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
            # Con 10 px de aire, el último renglón quedaba a la altura del puerto del
            # cable que sale hacia arriba y se escribían uno sobre otro.
            y = cy - alto / 2 - 16 - (len(lineas) - 1 - i) * 12
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
        f'<g data-area="{_esc(caja.titulo)}" data-x="{caja.x:.1f}" data-y="{caja.y:.1f}" '
        f'data-ancho="{caja.ancho:.1f}" data-alto="{caja.alto:.1f}" data-subred="{_esc(caja.subred)}" '
        f'data-nube="{int(getattr(caja, "nube", False))}" '
        f'data-hijas="{len(getattr(caja, "hijas", []))}"/>',
        f'<text x="{caja.x + 16:.1f}" y="{caja.y + 21:.1f}" font-family="{FUENTE}" '
        f'font-size="12.5" font-weight="650" fill="{EQUIPO_TRAZO}" '
        f'paint-order="stroke" stroke="#ffffff" stroke-width="3.2">{_esc(caja.titulo)}</text>',
    ]
    if caja.subred:
        textos.append(
            f'<text x="{caja.x + 16:.1f}" y="{caja.y + 36:.1f}" font-family="{FUENTE}" '
            f'font-size="10.5" fill="{TENUE}" paint-order="stroke" stroke="#ffffff" '
            f'stroke-width="3">{_esc(caja.subred)}</text>')
    # Lo que la red tiene montado de forma permanente —el rango que reparte— se escribe
    # en su cabecera. La puerta no: esa es la dirección del equipo que la toca, y va
    # escrita en el equipo, que es su dueño; repetirla aquí sólo añadiría ruido.
    fijos = list(servicios or [])
    for i, linea in enumerate(fijos):
        textos.append(f'<text x="{caja.x + 16:.1f}" y="{caja.y + 51 + i * 14:.1f}" '
                      f'font-family="{FUENTE}" font-size="10.5" fill="{EQUIPO_TRAZO}" '
                      f'paint-order="stroke" stroke="#ffffff" stroke-width="3">'
                      f'{_esc(linea)}</text>')
    if getattr(caja, "sintetica", False):
        return ""
    if getattr(caja, "nube", False):
        return _silueta_nube(caja) + "".join(textos)
    trazo = ' stroke-dasharray="7 5"' if suave else ''
    return "".join([
        (f'<rect x="{caja.x:.1f}" y="{caja.y:.1f}" width="{caja.ancho:.1f}" '
         f'height="{caja.alto:.1f}" rx="14" fill="{RED_RELLENO}" '
         f'fill-opacity="{0.03 if suave else 0.06}" '
         f'stroke="{RED_TRAZO}" stroke-width="1.4"{trazo}/>'),
        *textos,
    ])


# La nube se dibuja con la silueta de siempre —bultos redondos—, escalada al área que
# le toca: una caja redondeada diría «segmento del cliente», y la red del proveedor no
# lo es. El camino está normalizado a 100x60 y se estira con una transformación.
_NUBE = ("M24,58 C10,58 2,50 2,41 C2,33 9,26 17,26 C16,13 26,5 38,6 "
         "C47,6 54,11 57,18 C61,10 70,7 77,10 C86,13 90,21 88,27 "
         "C96,28 100,34 100,40 C100,50 92,58 80,58 Z")


def _silueta_nube(caja: Caja) -> str:
    """La caja del área, dibujada como una nube.

    Se escala lo mismo en los dos ejes y se centra: estirar sólo un eje convierte la
    nube en una mancha alargada, y el dibujo deja de decir «esto es Internet».
    """
    factor = min(caja.ancho / 100, caja.alto / 60)
    dx = caja.x + (caja.ancho - 100 * factor) / 2
    dy = caja.y + (caja.alto - 60 * factor) / 2
    escala = f"translate({dx:.1f},{dy:.1f}) scale({factor:.4f})"
    return (f'<path d="{_NUBE}" transform="{escala}" fill="{RED_RELLENO}" '
            f'fill-opacity="0.07" stroke="{RED_TRAZO}" stroke-width="{1.2 / factor:.2f}"/>')


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
           puerto_a: int | None = None, puerto_z: int | None = None,
           discontinua: bool = False) -> str:
    """Una conexión entre dos símbolos, sin flecha y sin etiqueta en el cable.

    `discontinua` marca la salida a Internet, que no es un cable del laboratorio. Nada
    más se escribe encima: cada dato vive en su equipo o en la cabecera de su red.
    """
    inicio = _borde(a, z, tam_a)
    fin = _borde(z, a, tam_z)
    largo_cable = math.hypot(fin[0] - inicio[0], fin[1] - inicio[1]) or 1
    guion = ' stroke-dasharray="5 4"' if discontinua else ''
    linea = (f'<line x1="{inicio[0]:.1f}" y1="{inicio[1]:.1f}" x2="{fin[0]:.1f}" '
             f'y2="{fin[1]:.1f}" stroke="{LINEA}" stroke-width="1.6" '
             f'stroke-linecap="round"{guion}/>')
    etiquetas = ""
    # El paso se acorta en cables cortos y se alarga en los largos: a 16 px fijos, dos
    # equipos separados por un palmo veían sus dos puertos escritos uno sobre otro, y a
    # 26 px el rótulo se metía debajo del nombre del equipo.
    paso = min(26.0, max(7.0, (largo_cable - 26) / 2))
    for punto, numero, hacia in ((inicio, puerto_a, fin), (fin, puerto_z, inicio)):
        if numero is None:
            continue
        dx, dy = hacia[0] - punto[0], hacia[1] - punto[1]
        largo = math.hypot(dx, dy) or 1
        # El puerto va pegado a su equipo, sobre el cable: es de quien lo nombra. El
        # desplazamiento es corto en el eje del cable y lateral al otro, para que los
        # tres cables de un switch no amontonen sus rótulos en el mismo punto.
        x = punto[0] + dx / largo * paso + (-11 if abs(dy) > abs(dx) else 0)
        y = punto[1] + dy / largo * paso - (8 if abs(dx) >= abs(dy) else 3)
        etiquetas += (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FUENTE}" '
                      f'font-size="9" fill="{TENUE}">p{numero}</text>')
    return linea + etiquetas
