# PROPÓSITO:   el mapa del laboratorio en lo que observa el sitio (NetXMS), colocado como
#              el plano. La vista tiene su propia topología automática —los equipos
#              repartidos por un algoritmo suyo, que no se parece a nada de lo que
#              dibuja el motor—: aquí se manda un mapa **a medida** en el que cada
#              equipo está donde lo puso el plano y cada red es la caja que el plano
#              dibuja. Así el mapa de la vista y el plano de la documentación son el
#              mismo dibujo, no dos parecidos.
# INVARIANTES: la geometría sale del propio plano (`plano.plano(lab, "topologia")`), que
#              ya lleva la posición de cada cosa en atributos `data-*`: no se recalcula
#              nada aquí, para que no puedan discrepar. Nada de este módulo habla con el
#              API ni escribe: deriva el contenido del mapa y dice si el que hay ya
#              coincide.
#              La vista dibuja los cables **por encima** de todo lo demás, así que un
#              rótulo colocado donde pasa un cable se queda ilegible. Por eso el nombre y
#              el bloque de cada área no van en el rótulo de su caja —que la vista pega
#              arriba a la izquierda, justo donde cruzan los cables que bajan de la red
#              troncal— sino en una caja de texto que se coloca en el primer rincón de su
#              área por el que no pase ningún cable ni se apoye ningún equipo. La
#              colocación es de este módulo, y por eso se puede comprobar por programa
#              (test_mapa) en vez de a ojo.
#              Cada equipo lleva además su **ficha** —sus patas con la interfaz que la vista
#              le ha descubierto y la red que sirve, sus direcciones y el rango que reparte—
#              y cada cable su **nombre y sus dos puertos**, tal y como se llaman en el
#              laboratorio: lo que el YML declara viaja al mapa en vez de quedarse en el
#              fichero, y el cable queda atado a la interfaz de la que de verdad sale.
# LÍMITES:     el dibujo es el del plano, con su lienzo y sus posiciones: este módulo no
#              recalcula geometría ni inventa áreas, y lo que no cabe —un rótulo, una
#              ficha— se busca sitio hasta el tope de sus anillos y, agotado, se devuelve
#              el menos malo en vez de moverse a otro sitio. Reconoce interfaces por su
#              nombre (`ether<N>`) y equipos por su rol: un equipo cuya interfaz no siga
#              esa convención se dibuja igual pero sin atar, y uno que la vista no conozca
#              no se dibuja. Nada de aquí habla con el API, escribe ni espera.
# VER:         docs/diseno.md §3.4 (el mapa a medida);
#              docs/decisiones/0004-el-mapa-de-la-vista-lo-coloca-el-plano.md y
#              docs/decisiones/0005-el-mapa-dice-lo-que-dice-el-yaml.md

import json
import math
import xml.etree.ElementTree as ET

import plano                    # el mismo plano del que sale la geometría, y sus rangos
from identity import cables     # el nombre de un cable se deriva en un solo sitio

# Cómo nombra la vista a las cosas del mapa. Son los números que viajan en el JSON del
# API: el tipo de elemento y, dentro de los adornos, la caja de grupo.
ELEMENTO_OBJETO = 1        # un equipo de la vista
ELEMENTO_ADORNO = 2        # una figura del mapa, no un equipo
ADORNO_CAJA = 0            # la caja de grupo: un rectángulo con su rótulo
ELEMENTO_TEXTO = 5         # una caja de texto: un rótulo suelto

TAMANO_EQUIPO = 100        # lado del hueco de un equipo en el mapa, como la vista

# Cómo se ve el mapa. Los colores van en BGR —la vista los guarda así y los lee así— y
# son de la familia que se lee sobre un fondo claro: la vista pinta el relleno de una caja
# con el color del adorno muy rebajado y su borde entero, y el borde es lo que se ve.
BLANCO, NEGRO = 0xFFFFFF, 0x000000
GRIS_DEL_BORDE = 0x999999      # el filo del rótulo: dice dónde acaba el texto
AZUL_PIZARRA = 0x573B1F        # rgb(31, 59, 87): el cable, oscuro sobre el gris del fondo
TRAZO_CABLE = 2                # la vista pone 4 por defecto: con 2 el cable tapa menos
ESTILO_CABLE = 1               # continua, como el plano
ENRUTADO_CABLE = 1             # recto, como el plano

# Lo que el mapa pide de sí mismo: el color y el trazo de sus cables. Sin esto la vista
# los dibuja con su criterio —un gris ancho y translúcido que se pierde en el fondo— y no
# hay forma de pedirlo desde fuera.
AJUSTES_DEL_MAPA = {
    "defaultLinkColorSource": 0,          # color propio, no el del estado del enlace
    "defaultLinkColor": AZUL_PIZARRA,
    "defaultLinkWidth": TRAZO_CABLE,
    "defaultLinkStyle": ESTILO_CABLE,
    "defaultLinkRouting": ENRUTADO_CABLE,
}

# Cuánto ocupa un rótulo. La vista mide el texto con la fuente que le digo, así que aquí
# se estima —ancho por letra más su relleno— y se guarda un margen: una estimación corta
# dejaría el rótulo pisando un cable sin que nadie se enterase.
ETIQUETA_FUENTE = 9            # puntos: se lee y deja sitio en áreas de 300 de ancho
ETIQUETA_LETRA = 6.4           # ancho estimado de una letra a esa fuente
ETIQUETA_RELLENO = 20          # el aire de la caja alrededor del texto
ETIQUETA_ALTO = 24
ETIQUETA_MARGEN = 10           # aire entre el rótulo y el borde de su área
ETIQUETA_GUARDA = 6            # de sobra, al comprobar si un cable lo pisa
ETIQUETA_APOYO = 2             # aire entre el nombre de un área y su bloque, debajo
CUADRICULA = 5                 # rincones que se prueban por cada lado, si los de fuera fallan
AIRE_FICHA = 16                # aire entre un equipo y el cartel que lo describe
RADIOS_FICHA = 10              # anillos alrededor de un equipo, si sus cuatro lados están tomados
VUELTAS_FICHA = 16             # sitios que se prueban en cada anillo


def disposicion(svg: str) -> dict:
    """Dónde queda cada cosa en el plano: el lienzo, las áreas y los equipos.

    Se lee de los atributos `data-*` que el propio plano lleva —los mismos que usan las
    pruebas del dibujo—, así que el mapa no puede colocarse en un sitio distinto del que
    el plano enseña. El SVG se lee con el lector XML de la biblioteca estándar y no con
    expresiones, porque el plano escapa al escribir —un rótulo «Ventas & almacén» viaja
    como `Ventas &amp; almacén`— y el lector XML devuelve el texto tal cual, que es lo que
    tiene que leerse en la vista; copiar el atributo crudo enseñaría el escape.
    """
    raiz = ET.fromstring(svg)
    ancho, alto = raiz.get("width"), raiz.get("height")
    if ancho is None or alto is None:
        raise ValueError("el plano no declara su tamaño: no hay mapa que colocar")
    areas, equipos, cables_del_plano = [], {}, []
    for grupo in raiz.iter():
        atributos = grupo.attrib
        if "data-area" in atributos:
            areas.append({
                "titulo": atributos["data-area"],
                "subred": atributos.get("data-subred", ""),
                "x": float(atributos["data-x"]),
                "y": float(atributos["data-y"]),
                "ancho": float(atributos["data-ancho"]),
                "alto": float(atributos["data-alto"]),
                "nube": atributos.get("data-nube") == "1",
            })
        elif "data-rol" in atributos:
            equipos[atributos["data-rol"]] = (float(atributos["data-x"]),
                                              float(atributos["data-y"]))
        elif atributos.get("class") == "cable" and "data-a" in atributos:
            cables_del_plano.append({"a": atributos["data-a"], "pa": int(atributos["data-pa"]),
                                     "z": atributos["data-z"], "pz": int(atributos["data-pz"])})
    return {"ancho": float(ancho), "alto": float(alto),
            "areas": areas, "equipos": equipos, "cables": cables_del_plano}


def renglones(area: dict) -> list:
    """Los renglones que rotulan un área: el nombre con su prefijo y, debajo, el bloque.

    Van partidos así —y no «nombre» y «bloque entero»— porque manda el renglón más ancho:
    «10.20.55.0 - 10.20.55.255 (/24)» mide 218 px y hay cuatro áreas del repositorio —una
    por cada sede de un laboratorio, y la de un laboratorio pequeño— donde no cabe sin
    pisar un cable, mientras que sin el prefijo mide 167 y sí cabe. El prefijo se lee en el
    primer renglón, junto al nombre, que es donde no estorba.
    """
    if not area["subred"] or area["subred"] == area["titulo"]:
        return [area["titulo"]]
    rango, _, prefijo = area["subred"].partition(" (")
    if not prefijo:
        return [area["titulo"], area["subred"]]
    return [f"{area['titulo']} ({prefijo.rstrip(')')})", rango]


def rotulos_de(area: dict) -> tuple:
    """Los rótulos de un área y lo que ocupan juntos: el nombre y, debajo, su bloque.

    Se colocan como un solo bloque —el nombre arriba, el bloque debajo— porque así se leen;
    dos búsquedas por separado acababan con el nombre arriba del área y su bloque al otro
    extremo. Y se busca una sola vez porque lo que ocupa el grupo es lo que hay que
    esquivar: si el grupo cabe en un hueco, cada renglón cabe dentro del grupo.
    """
    textos = renglones(area)
    ancho, alto = tamano_del_grupo(textos)
    return textos, ancho, alto


def tamano_de_rotulo(texto: str) -> tuple:
    """Lo que se estima que ocupa ese rótulo en el mapa: ancho y alto."""
    return round(len(texto) * ETIQUETA_LETRA + ETIQUETA_RELLENO), ETIQUETA_ALTO


def candidatos(area: dict, ancho: float, alto: float) -> list:
    """Dónde puede ir un rótulo, por orden de preferencia: dentro de su área y, si no cabe,
    pegado a ella.

    Primero los rincones —arriba y abajo, a la izquierda antes que a la derecha, que es
    donde el plano pone sus rótulos— y luego el centro de los lados. Después una rejilla
    por toda el área: en un área grande y muy cableada —dos sedes con sus routers de borde
    y sus cables cruzando de una a otra— los rincones pueden quedar todos debajo de un
    cable. Y si ni así, justo encima y justo debajo del área, que el rótulo se lee igual y
    sigue diciendo de qué área es.
    """
    izquierda = area["x"] + ETIQUETA_MARGEN
    arriba = area["y"] + ETIQUETA_MARGEN
    derecha = max(izquierda, area["x"] + area["ancho"] - ancho - ETIQUETA_MARGEN)
    abajo = max(arriba, area["y"] + area["alto"] - alto - ETIQUETA_MARGEN)
    medio_x = max(izquierda, min(derecha, area["x"] + (area["ancho"] - ancho) / 2))
    medio_y = max(arriba, min(abajo, area["y"] + (area["alto"] - alto) / 2))

    orden = [(izquierda, arriba), (derecha, arriba)]
    for fila in range(CUADRICULA):
        for columna in range(CUADRICULA):
            orden.append((round(izquierda + (derecha - izquierda) * columna / (CUADRICULA - 1)),
                          round(arriba + (abajo - arriba) * fila / (CUADRICULA - 1))))
    orden += [(izquierda, abajo), (derecha, abajo), (izquierda, medio_y), (derecha, medio_y),
              (izquierda, max(0.0, area["y"] - alto - ETIQUETA_MARGEN)),
              (izquierda, area["y"] + area["alto"] + ETIQUETA_MARGEN)]

    sitios, vistos = [], set()
    for sitio in orden:
        if sitio not in vistos:
            vistos.add(sitio)
            sitios.append(sitio)
    return sitios


def sitio_libre(area: dict, ancho: float, alto: float, cables: list, ocupado: list) -> tuple:
    """El primer rincón del área donde el rótulo no queda tapado por un cable ni por un equipo.

    `cables` son los segmentos que dibuja la vista (`((x, y), (x, y))`) y `ocupado` los
    rectángulos que ya hay puestos. Si no queda ninguno libre se devuelve el primero: un
    rótulo tapado se ve mal, pero un rótulo fuera de su área no dice nada.
    """
    for x, y in candidatos(area, ancho, alto):
        rectangulo = (x - ETIQUETA_GUARDA, y - ETIQUETA_GUARDA,
                      ancho + 2 * ETIQUETA_GUARDA, alto + 2 * ETIQUETA_GUARDA)
        if any(solapan(rectangulo, otro) for otro in ocupado):
            continue
        if any(corta(rectangulo, uno, otro) for uno, otro in cables):
            continue
        return x, y
    return candidatos(area, ancho, alto)[0]


def ficha_de(node: dict, lab: dict, interfaces: dict) -> list:
    """El cartel de un equipo: sus patas con su interfaz y su red, sus direcciones y su reparto.

    Todo sale de la declaración —cuántas patas tiene, qué red lleva cada una, qué dirección
    y qué rango reparte— y de los nombres de interfaz que la vista le ha descubierto al
    equipo, que es lo único que no se puede deducir del YML. El equipo del plano y el equipo
    de la vista son el mismo si sus patas y sus interfaces coinciden; esto es lo que lo deja
    ver en el mapa.
    """
    redes = {red["name"]: red for red in lab.get("networks") or []}
    config = node.get("configure") or {}
    direcciones = {d["network"]: d["address"] for d in config.get("addresses") or []}
    suyas = interfaces.get(node["role"]) or {}

    cuantas = len(node["networks"])
    # Las patas en un solo renglón: el puerto del plano y la interfaz del equipo, que son lo
    # mismo visto desde cada lado. La red de cada pata ya la dicen el plano y el cable que
    # sale de ella; repetirla aquí haría un cartel que no cabe en las sedes pequeñas, que son
    # justo donde más falta hace poder leerlo.
    patas = " · ".join(f"p{puerto} ether{puerto}" if f"ether{puerto}" in suyas else f"p{puerto}"
                       for puerto in range(1, cuantas + 1))
    cabecera = f"{node['role']} · {cuantas} pata{'' if cuantas == 1 else 's'}"
    lineas = [f"{cabecera}: {patas}" if patas else cabecera]

    # La dirección de cada pata, si se declara; si el equipo la pide por DHCP se dice, como
    # lo dice el plano, y no se le inventa ninguna.
    dichas = " · ".join(direcciones[red] for red in node["networks"] if red in direcciones)
    if dichas:
        lineas.append(dichas)
    elif node.get("address") == "dhcp":
        lineas.append("dhcp")

    for srv in config.get("dhcp_server") or []:
        cidr = str((redes.get(srv.get("network")) or {}).get("address") or "")
        corto = plano.rango_corto(srv.get("pool") or "", cidr) if cidr else ""
        # «reparte» y no «dhcp» a secas: el rango ya lo dice el rótulo de su área, y lo que
        # aquí se enseña es qué router lo reparte.
        lineas.append(f"reparte dhcp {corto or srv.get('pool') or ''}".rstrip())
    return lineas


def _interfaz(interfaces: dict, rol: str, puerto: int) -> int:
    """El número con el que la vista conoce la interfaz de ese puerto, o 0 si no la tiene.

    La vista llama a las interfaces de un equipo como las llama el equipo —`ether1`,
    `ether2`…— y el puerto `p3` del plano es su `ether3`: es la misma convención con la que
    el motor conecta cada tarjeta, así que no hay nada que adivinar. Una interfaz que la
    vista no haya descubierto —el equipo acaba de registrarse— llega como 0 y el cable se
    dibuja igual, sin atar.
    """
    return int((interfaces.get(rol) or {}).get(f"ether{puerto}") or 0)


def _puerto(interfaces: dict, rol: str, puerto: int) -> str:
    """Cómo se rotula una punta del cable: su puerto y, si se sabe, la interfaz del equipo.

    Es el mismo saber que usa el cable para atarse —el puerto `p3` del plano es la `ether3`
    del equipo— puesto en la punta, que es donde se lee: así el nombre de la interfaz viaja
    con el cable aunque la ficha del equipo no lo repita.
    """
    suya = f"ether{puerto}"
    return f"p{puerto} {suya}" if suya in (interfaces.get(rol) or {}) else f"p{puerto}"


def tamano_del_grupo(textos: list) -> tuple:
    """Lo que ocupa un grupo de renglones: manda el más ancho y el alto es su suma."""
    return (max(tamano_de_rotulo(texto)[0] for texto in textos),
            sum(tamano_de_rotulo(texto)[1] for texto in textos) + ETIQUETA_APOYO * (len(textos) - 1))


def sitio_junto_a(punto: tuple, ancho: float, alto: float, cables: list, ocupado: list,
                  lienzo: tuple) -> tuple:
    """El primer sitio alrededor de un equipo donde su ficha no queda tapada por nada.

    Primero los cuatro lados —a la derecha antes que a la izquierda, que es por donde baja
    el cable de la red troncal— y después las diagonales y un anillo más ancho, por si el
    equipo está en un rincón muy cableado. La ficha tiene que caber en el lienzo: un cartel
    que se sale del mapa no se ve. Si no hay ningún sitio, se devuelve el de su derecha,
    que es el que menos estorba —una ficha tapada se lee mal, pero una sin sitio no dice nada.
    """
    cx, cy = punto
    ancho_lienzo, alto_lienzo = lienzo
    medio = TAMANO_EQUIPO / 2

    def cabe(x: float, y: float) -> bool:
        if x < 0 or y < 0 or x + ancho > ancho_lienzo or y + alto > alto_lienzo:
            return False
        rectangulo = (x - ETIQUETA_GUARDA, y - ETIQUETA_GUARDA,
                      ancho + 2 * ETIQUETA_GUARDA, alto + 2 * ETIQUETA_GUARDA)
        if any(solapan(rectangulo, otro) for otro in ocupado):
            return False
        return not any(corta(rectangulo, uno, otro) for uno, otro in cables)

    derecho, izquierdo = cx + medio + AIRE_FICHA, cx - medio - AIRE_FICHA - ancho
    abajo, arriba = cy + medio + AIRE_FICHA, cy - medio - AIRE_FICHA - alto
    # Los cuatro lados —a la derecha antes que a la izquierda—, luego las diagonales y
    # después un anillo tras otro alrededor del equipo: en una sede apretada, con el router
    # pegado al switch y los puestos alrededor, los cuatro lados se agotan.
    orden = [(derecho, cy - alto / 2), (izquierdo, cy - alto / 2),
             (cx - ancho / 2, abajo), (cx - ancho / 2, arriba),
             (derecho, abajo), (izquierdo, abajo), (derecho, arriba), (izquierdo, arriba)]
    for radio in range(1, RADIOS_FICHA + 1):
        salto = medio + AIRE_FICHA * (radio + 1)
        for paso in range(VUELTAS_FICHA):
            giro = 2 * math.pi * paso / VUELTAS_FICHA
            orden.append((cx + salto * math.cos(giro) - ancho / 2,
                          cy + salto * math.sin(giro) - alto / 2))
    for x, y in orden:
        if cabe(round(x), round(y)):
            return round(x), round(y)
    return round(orden[0][0]), round(orden[0][1])


def cajas_de_texto(textos: list, x: float, y: float, primero: int) -> list:
    """Las cajas de texto de un grupo de renglones, desde el número de elemento `primero`.

    Enteros: la vista lee la posición con `json_object_get_int32` y un decimal —«70.0»— le
    llega como cero. La caja se queda en la esquina y vuelve a estar debajo de un cable,
    que es justo lo que se viene a arreglar.
    """
    cajas, renglon = [], 0
    for salto, texto in enumerate(textos):
        _, alto_texto = tamano_de_rotulo(texto)
        cajas.append({
            "id": primero + salto, "type": ELEMENTO_TEXTO, "flags": 0,
            "posX": round(x), "posY": round(y + renglon), "TextBox": config_de_rotulo(texto),
        })
        renglon += alto_texto + ETIQUETA_APOYO
    return cajas


def solapan(uno: tuple, otro: tuple) -> bool:
    """¿Se pisan dos rectángulos? (`(x, y, ancho, alto)`)."""
    return not (uno[0] + uno[2] <= otro[0] or otro[0] + otro[2] <= uno[0]
                or uno[1] + uno[3] <= otro[1] or otro[1] + otro[3] <= uno[1])


def corta(rectangulo: tuple, uno: tuple, otro: tuple) -> bool:
    """¿El segmento que va de `uno` a `otro` toca ese rectángulo?

    Recorte de Liang–Barsky: se acorta el segmento contra cada lado del rectángulo y si
    algo queda del segmento, lo toca.
    """
    x, y, ancho, alto = rectangulo
    izquierda, arriba, derecha, abajo = x, y, x + ancho, y + alto
    t0, t1 = 0.0, 1.0
    dx, dy = otro[0] - uno[0], otro[1] - uno[1]
    for avance, distancia in ((-dx, uno[0] - izquierda), (dx, derecha - uno[0]),
                              (-dy, uno[1] - arriba), (dy, abajo - uno[1])):
        if avance == 0:
            if distancia < 0:
                return False
            continue
        cruce = distancia / avance
        if avance < 0:
            if cruce > t1:
                return False
            t0 = max(t0, cruce)
        else:
            if cruce < t0:
                return False
            t1 = min(t1, cruce)
    return True


def config_de_rotulo(texto: str) -> str:
    """La caja de texto que la vista dibuja: el rótulo, con su fondo y su filo.

    La vista guarda esta configuración como un texto —un JSON dentro del JSON del mapa—,
    y es la parte del elemento que dice **qué se lee**.
    """
    return json.dumps({
        "text": texto,
        "backgroundColor": BLANCO, "textColor": NEGRO,
        "borderColor": GRIS_DEL_BORDE, "borderRequired": True,
        "fontSize": ETIQUETA_FUENTE, "drillDownObjectId": 0,
    }, ensure_ascii=False)


def contenido(lab: dict, svg: str, objetos: dict, interfaces: dict | None = None) -> dict:
    """El contenido del mapa: las áreas, los equipos, sus fichas y los cables, donde los pone el plano.

    `objetos` traduce el rol de cada equipo al número con el que la vista lo conoce, e
    `interfaces` trae, por equipo, el nombre de cada una de sus interfaces con el número de
    objeto que la vista le ha dado. Un equipo del plano que no esté en la vista no se dibuja
    —y los cables que salen de él tampoco—, porque un elemento del mapa sin objeto detrás no
    lo acepta la vista. Sin `interfaces` el mapa se dibuja igual, pero sus cables no quedan
    atados a la interfaz de la que salen ni la ficha puede nombrarlas.
    """
    donde = disposicion(svg)
    nombres = cables(lab)["per_port"]
    interfaces = interfaces or {}
    elementos, numero, elemento_de = [], 0, {}
    for area in donde["areas"]:
        numero += 1
        elementos.append({
            "id": numero, "type": ELEMENTO_ADORNO, "decorationType": ADORNO_CAJA,
            "flags": 0, "title": "",
            "posX": round(area["x"]), "posY": round(area["y"]),
            "width": round(area["ancho"]), "height": round(area["alto"]),
        })

    en_donde = {rol: (cx, cy) for rol, (cx, cy) in donde["equipos"].items() if rol in objetos}
    for rol, (cx, cy) in sorted(en_donde.items()):
        numero += 1
        elemento_de[rol] = numero
        elementos.append({
            "id": numero, "type": ELEMENTO_OBJETO, "flags": 0,
            "objectId": int(objetos[rol]),
            "posX": round(cx - TAMANO_EQUIPO / 2), "posY": round(cy - TAMANO_EQUIPO / 2),
            "width": TAMANO_EQUIPO, "height": TAMANO_EQUIPO,
        })

    enlaces, trazos = [], []
    for cable in lab.get("links") or []:
        una, punta_a = cable["a"]["node"], int(cable["a"]["port"])
        otra, punta_z = cable["z"]["node"], int(cable["z"]["port"])
        if una not in elemento_de or otra not in elemento_de:
            continue
        trazos.append((en_donde[una], en_donde[otra]))
        # El cable se llama como en el laboratorio —`e_swc1p1_rta1p1`, que es el nombre de su
        # puente— y cada punta dice su puerto; la interfaz es la que la vista le ha
        # descubierto al equipo con ese número. Sin ella el cable se dibuja igual, pero no
        # queda atado a algo que se pueda medir.
        enlaces.append({
            "element1": elemento_de[una], "element2": elemento_de[otra],
            "interface1": _interfaz(interfaces, una, punta_a),
            "interface2": _interfaz(interfaces, otra, punta_z),
            "type": 0, "flags": 0,
            "name": str(nombres.get(una, {}).get(punta_a) or ""),
            "connectorName1": _puerto(interfaces, una, punta_a),
            "connectorName2": _puerto(interfaces, otra, punta_z),
            "colorSource": 0, "color": 0, "colorProvider": "", "config": "",
        })

    # Los equipos ocupan su hueco: una ficha encima de uno se leería mal aunque no pasara
    # ningún cable por ahí.
    ocupado = [(round(cx - TAMANO_EQUIPO / 2), round(cy - TAMANO_EQUIPO / 2),
                TAMANO_EQUIPO, TAMANO_EQUIPO) for cx, cy in en_donde.values()]

    # Las fichas van primero, y pegadas a su equipo: son suyas y no se pueden ir lejos —un
    # cartel que no está junto al equipo que describe no dice de quién es—. El rótulo de un
    # área, en cambio, puede buscarse otro rincón dentro de ella: es él quien las esquiva.
    fichas = {node["role"]: node for node in lab["nodes"] if node["role"] in en_donde}
    for rol, (cx, cy) in sorted(en_donde.items()):
        node = fichas.get(rol)
        if node is None:
            # Un equipo que está en la vista y en el plano pero no se declara en el fichero
            # —el nodo de control, que vive en la red de gestión— no tiene ficha que enseñar.
            continue
        textos = ficha_de(node, lab, interfaces)
        ancho, alto = tamano_del_grupo(textos)
        x, y = sitio_junto_a((cx, cy), ancho, alto, trazos, ocupado, (donde["ancho"], donde["alto"]))
        ocupado.append((x, y, ancho, alto))
        cajas = cajas_de_texto(textos, x, y, numero + 1)
        elementos += cajas
        numero += len(cajas)

    # Los rótulos se colocan de la zona más pequeña a la más grande: la pequeña —una sede
    # con su router y su switch, que es casi todo equipo, ficha y cable— no tiene dónde
    # elegir, y la grande que la envuelve sí. Al revés, el rótulo del laboratorio se ponía en
    # el primer hueco que encontraba —dentro de una sede— y dejaba a la sede sin sitio.
    puestos = {}
    for indice, area in sorted(enumerate(donde["areas"]), key=lambda par: par[1]["ancho"] * par[1]["alto"]):
        textos, ancho, alto = rotulos_de(area)
        x, y = sitio_libre(area, ancho, alto, trazos, ocupado)
        ocupado.append((x, y, ancho, alto))
        puestos[indice] = (textos, x, y)

    for indice in range(len(donde["areas"])):
        textos, x, y = puestos[indice]
        cajas = cajas_de_texto(textos, x, y, numero + 1)
        elementos += cajas
        numero += len(cajas)

    return {
        **AJUSTES_DEL_MAPA,
        "width": round(donde["ancho"]), "height": round(donde["alto"]),
        "elements": elementos, "links": enlaces,
    }


def texto_de(elemento: dict) -> str:
    """La configuración de una caja de texto, la haya escrito quien la haya escrito.

    Al escribirla viaja en `TextBox` y al leerla vuelve en `config`: la vista no la
    devuelve con el mismo nombre con el que se le manda.
    """
    crudo = elemento.get("config") or elemento.get("TextBox") or ""
    return str(crudo)


def _resumen_elemento(elemento: dict) -> tuple:
    """Lo que de verdad distingue un elemento de otro: dónde y qué enseña.

    El número de elemento no entra —lo reparte quien escribe— y el lienzo tampoco: lo que
    importa es que cada cosa esté en su sitio y sea la que es.
    """
    donde = (elemento.get("type"), int(elemento.get("posX") or 0), int(elemento.get("posY") or 0),
             int(elemento.get("width") or 0), int(elemento.get("height") or 0))
    if int(elemento.get("type") or 0) == ELEMENTO_OBJETO:
        return donde + ("equipo", int(elemento.get("objectId") or 0))
    if int(elemento.get("type") or 0) == ELEMENTO_TEXTO:
        return donde + ("texto", _config_ordenada(elemento))
    return donde + ("adorno", int(elemento.get("decorationType") or 0), str(elemento.get("title") or ""))


def _config_ordenada(elemento: dict) -> str:
    """La configuración de una caja de texto, ordenada: para compararla, no para leerla.

    La vista devuelve el mismo texto que se le mandó, pero con sus claves en su orden y
    sus acentos escapados; ordenada, dos configuraciones iguales se comparan igual.
    """
    crudo = texto_de(elemento)
    if not crudo:
        return ""
    try:
        return json.dumps(json.loads(crudo), sort_keys=True, ensure_ascii=False)
    except ValueError:
        return crudo


def esta_al_dia(actual: dict | None, deseado: dict) -> bool:
    """¿El mapa que hay ya es el que el plano pide?

    Los enlaces se comparan por los equipos que unen y no por su número: la vista reparte
    los suyos, así que el número de enlace cambia al escribirlos y no significa nada.
    """
    if not actual:
        return False
    if resumen_ajustes(actual) != resumen_ajustes(deseado):
        return False
    if _resumen_elemento_de(actual) != _resumen_elemento_de(deseado):
        return False
    return _resumen_cableado(actual) == _resumen_cableado(deseado)


def resumen_ajustes(mapa: dict) -> tuple:
    """El color y el trazo de los cables: el mapa también cambia cuando cambian ellos."""
    return tuple(int(mapa.get(clave) or 0) for clave in sorted(AJUSTES_DEL_MAPA))


def _resumen_elemento_de(mapa: dict) -> list:
    return sorted(_resumen_elemento(e) for e in mapa.get("elements") or [])


def _resumen_cableado(mapa: dict) -> list:
    """Los cables por lo que dicen: qué equipos unen, por qué interfaz y cómo se llaman.

    El número de enlace no entra —lo reparte la vista— pero sí todo lo que se lee en el
    mapa: sin esto, un mapa con los cables anónimos y con las puntas sueltas se daría por
    bueno y no habría forma de que el nombre del cable llegara a la vista nunca.
    """
    elementos = mapa.get("elements") or []
    nombre = {}
    for elemento in elementos:
        if int(elemento.get("type") or 0) == ELEMENTO_OBJETO:
            nombre[int(elemento.get("id") or 0)] = int(elemento.get("objectId") or 0)
        else:
            nombre[int(elemento.get("id") or 0)] = str(elemento.get("title") or "") or _config_ordenada(elemento)
    lazos = set()
    for enlace in mapa.get("links") or []:
        una = nombre.get(int(enlace.get("element1") or 0))
        otra = nombre.get(int(enlace.get("element2") or 0))
        if una is None or otra is None:
            continue
        # Cada punta viaja con su interfaz y su puerto, así que las dos puntas se ordenan
        # juntas —la vista puede devolver el cable con las puntas cambiadas— pero la
        # interfaz no se despega del equipo del que es: si se ordenaran por separado, un
        # cable con las puntas al revés parecería otro distinto y el mapa se reescribiría
        # en cada pasada.
        puntas = sorted(((str(una), int(enlace.get("interface1") or 0),
                          str(enlace.get("connectorName1") or "")),
                         (str(otra), int(enlace.get("interface2") or 0),
                          str(enlace.get("connectorName2") or ""))))
        lazos.add((tuple(puntas), str(enlace.get("name") or "")))
    return sorted(lazos)


def cuerpo(contenido_mapa: dict) -> str:
    """El cuerpo que se le manda a la vista: sólo lo que el API acepta escribir.

    La lectura devuelve claves que la escritura rechaza —`filter` y `linkScript` con nulo—,
    así que aquí sólo viajan las que definen el mapa: el lienzo, su contenido y cómo se
    dibujan sus cables.
    """
    return json.dumps({
        **{clave: contenido_mapa[clave] for clave in AJUSTES_DEL_MAPA},
        "width": contenido_mapa["width"],
        "height": contenido_mapa["height"],
        "elements": contenido_mapa["elements"],
        "links": contenido_mapa["links"],
    }, ensure_ascii=False)
