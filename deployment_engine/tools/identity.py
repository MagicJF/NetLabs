# PROPÓSITO:   la capa pura del motor. (mundo, declaración, entorno) -> plan.
#              No lee ficheros, no habla con la API y no guarda nada: dadas las
#              mismas entradas da la misma salida, y por eso se prueba sin hipervisor.
# INVARIANTES: ningún valor derivado (vmid, MAC, dirección de gestión) se escribe en
#              el repositorio; se re-derivan preguntando al hipervisor.
#              Un vmid ya usado en el clúster no se reutiliza nunca.
#              Un rol que ya existe en el pool del laboratorio conserva su vmid: sin
#              eso, el segundo `apply` no sería idempotente.
#              Lo que la declaración no dice se rechaza con un mensaje, nunca se
#              ignora en silencio.
# LÍMITES:     no sabe si un vmid está libre de verdad: se lo dice el mundo.
#              No crea nada: devuelve pasos; ejecutarlos es tarea de Ansible.
# VER:         docs/diseno.md §2, §5, §6; deployment_engine/tests/test_identity.py

from __future__ import annotations

import copy
import ipaddress
import re

# Los tipos de nodo son un vocabulario cerrado; cada uno puede hacer una cosa.
# `network device` (router, switch) nace con la pata de gestión; `end node`
# (server, workstation) no la tiene y se llega a él por su router.
#
# El código de dos letras es la cabeza del nombre del equipo y la letra de función
# dice qué hace dentro de su tipo: un router de borde y uno de núcleo no se llaman
# igual porque no son lo mismo. La letra se valida contra esta tabla —una función
# que no existe no es un equipo, es una errata— y no se admite cualquier cosa.
TYPES = {
    "router": {"code": "rt", "guest": "qemu", "network_device": True, "routes": True,
               "functions": {"e": "borde", "c": "núcleo", "a": "acceso", "p": "proveedor"}},
    "firewall": {"code": "fw", "guest": "qemu", "network_device": True, "routes": True,
                 "functions": {"e": "borde", "i": "interior"}},
    "switch": {"code": "sw", "guest": "qemu", "network_device": True, "routes": False,
               "functions": {"c": "núcleo", "a": "acceso", "d": "distribución"}},
    "server": {"code": "sv", "guest": "lxc", "network_device": False, "routes": False,
               "functions": {"s": "servicio", "d": "datos"}},
    "workstation": {"code": "ws", "guest": "lxc", "network_device": False, "routes": False,
                    "functions": {"p": "puesto"}},
    # Un nodo de control no vive en una topología: es el servicio persistente que
    # observa y abre el camino. Su única pata está en la red de gestión y su
    # dirección se deriva del vmid, igual que la del servicio de gestión. No es
    # un equipo de red ni un puesto: no tiene cables ni recibe DHCP, y se llama por
    # el nombre del servicio que declara el laboratorio, no por el patrón de un equipo.
    "control": {"code": "nx", "guest": "lxc", "network_device": False, "routes": False,
                "control": True, "functions": {}},
}

# El único secreto del sitio que un laboratorio puede nombrar para el administrador
# de un RouterOS: dice el nombre, nunca el valor. `converge.ros_clave` lo resuelve
# contra secrets.yml y falla si no está.
ROS_SECRET = "secrets.routeros_clave"
# La comunidad SNMP tampoco se escribe en el laboratorio: se nombra y se resuelve.
SNMP_SECRET = "secrets.snmp_comunidad"

# Las áreas de configuración que el motor entiende, por clase de equipo. Una clave
# fuera de su lista es un error con mensaje (§2.13), no una nota al pie.
# El nombre del equipo no es un área: sale del rol declarado y el motor lo escribe
# en todas partes (el hostname del invitado, la identidad del RouterOS), así que
# declararlo otra vez sería una segunda verdad esperando a contradecirse.
AREAS = {
    "routeros": {"addresses", "routes", "dhcp_server", "services", "users", "snmp"},
    "linux": {"repositories", "packages", "files", "commands", "services"},
}

LAB_KEYS = {"lab", "kind", "address_spaces", "networks", "nodes", "links"}
# Un laboratorio de control no dibuja una topología: declara el servicio que
# observa el resto. Su único nodo vive en la red de gestión y no tiene cables.
KINDS = {"topology", "control"}
NODE_KEYS = {"role", "type", "stage", "after", "resources", "image", "networks", "address", "reserve", "configure"}
# `shape` sólo dice cómo se dibuja la red, nunca cómo se despliega: un puente es un
# puente. Hoy hay una forma con nombre —`cloud`—, la del proveedor al que cada sede se
# asoma por su cuenta; el resto de las redes son áreas del plano.
NETWORK_KEYS = {"name", "address", "title", "shape"}
NETWORK_SHAPES = {"cloud"}
LINK_KEYS = {"a", "z"}
END_KEYS = {"node", "port"}

# El nombre de un laboratorio es su identidad completa: una letra y un título que se
# lee. La letra no es decorativa: es lo que hace único el nombre de cada cable en el
# hipervisor —dos laboratorios con la misma topología no comparten un solo puente— y
# lo que hace que el nombre del pool empiece por letra, que es lo que la API de
# Proxmox exige. La letra y el título son también el nombre de la carpeta y del
# fichero: uno, no cuatro.
LAB_NAME_RE = re.compile(r"^([a-z])_[a-z0-9][a-z0-9_]{1,30}$")
# El nombre de un equipo es el rol declarado y vale para todo: el hostname del
# invitado, su nombre en Proxmox y las dos puntas de cada cable que lo toca. Dos
# letras de tipo, una de función y el ordinal: el segundo equipo de una misma clase
# lleva el 2 donde el primero lleva el 1.
DEVICE_RE = re.compile(r"^([a-z]{2})([a-z])([1-9])$")
# El nodo de un laboratorio de control se llama por su nombre de servicio: no es un
# equipo de una topología y renombrarlo en caliente no es una opción.
CONTROL_NODE_RE = re.compile(r"^[a-z][a-z0-9-]{0,20}$")


class LabError(Exception):
    """Un error de la declaración o del mundo, con el motivo escrito."""


# ---------------------------------------------------------------------------
# Derivación: identidad a partir del identificador
# ---------------------------------------------------------------------------

def derive_mac(vmid: int, iface: int = 0) -> str:
    """La MAC de la interfaz `iface` es función pura del vmid.

    `vmid << 4 | iface` es una biyección para los vmids que Proxmox admite, así
    que dos invitados (o dos interfaces) no pueden compartir MAC sin compartir
    vmid, y entonces el choque lo habría dicho la API antes.
    """
    _check_vmid(vmid)
    if not 0 <= iface < 16:
        raise LabError(f"una interfaz {iface} no cabe en la MAC derivada de {vmid}: se admiten 16")
    valor = (vmid << 4) | iface
    return "BC:24:11:{:02X}:{:02X}:{:02X}".format(
        (valor >> 16) & 0xFF, (valor >> 8) & 0xFF, valor & 0xFF
    )


# El tope de vmids que caben en el plano de gestión: un /16 da 255 bloques de 254
# direcciones. Por encima no hay dirección derivada que dar.
VMID_MAXIMO_MANAGEMENT = 254 * 255 - 1


def _red_de_gestion(address_space: str) -> ipaddress.IPv4Network:
    """El plano de gestión, comprobado: es un /16 y por eso cada vmid cae en su sitio."""
    red = ipaddress.ip_network(address_space, strict=False)
    if not isinstance(red, ipaddress.IPv4Network) or red.prefixlen != 16:
        raise LabError(
            f"la red de gestión tiene que ser un /16 y es {address_space!r}; "
            "es lo que hace que la dirección de cada equipo salga de su vmid sin reparto"
        )
    return red


def cabe_management(vmid: int, address_space: str) -> bool:
    """¿Cabe una dirección de gestión para ese vmid en el plano declarado?

    El clúster puede tener invitados que no son del motor —fuera de su rango, o de un
    hipervisor que admite vmids por encima de los que caben en el /16—. Preguntarles su
    dirección derivada no puede tumbar la lectura del clúster: se saltan. El plano mal
    declarado no se salta: es un error del sitio y se dice.
    """
    _red_de_gestion(address_space)
    return 0 < int(vmid) <= VMID_MAXIMO_MANAGEMENT


def derive_management(vmid: int, address_space: str) -> ipaddress.IPv4Address:
    """La dirección de gestión es función pura del vmid dentro del plano compartido.

    `vmid % 254 + 1` nunca da .0 ni .255, que no son direcciones de equipo, y es
    biyección sobre los 254 hosts de cada /24. Un /16 encadena 255 de esos bloques
    (`vmid // 254`), así que caben vmids hasta 64769. Por encima, el motor lo dice
    en vez de inventar una dirección.
    """
    _check_vmid(vmid)
    red = _red_de_gestion(address_space)
    if vmid > VMID_MAXIMO_MANAGEMENT:
        raise LabError(
            f"no cabe una dirección de gestión para el vmid {vmid} en {address_space}: "
            f"un /16 admite vmids hasta {VMID_MAXIMO_MANAGEMENT}"
        )
    base = int(red.network_address)
    return ipaddress.ip_address(base + (vmid // 254) * 256 + (vmid % 254 + 1))


def _check_vmid(vmid: int) -> None:
    if not isinstance(vmid, int) or isinstance(vmid, bool) or vmid <= 0:
        raise LabError(f"no se puede derivar identidad de un vmid inválido: {vmid!r}")


def tunnel_port(vmid: int) -> int:
    """El puerto local por el que el motor alcanza el REST de un router.

    Se deriva del vmid para no repartir puertos a mano; el rango 20000-29999 no
    pisa los puertos de servicio que ya usan las máquinas del cortafuegos.
    """
    _check_vmid(vmid)
    return 20000 + (vmid % 10000)


# ---------------------------------------------------------------------------
# Validación de la declaración
# ---------------------------------------------------------------------------

def validate(lab: dict, env: dict) -> None:
    """Rechaza lo que el motor no entiende, con el motivo y el sitio."""
    if not isinstance(lab, dict):
        raise LabError("la declaración tiene que ser un mapa YAML")
    unknown = set(lab) - LAB_KEYS
    if unknown:
        raise LabError(
            f"clave desconocida en la declaración: {', '.join(sorted(unknown))}. "
            f"Se admite: {', '.join(sorted(LAB_KEYS))}"
        )
    kind = lab.get("kind", "topology")
    if kind not in KINDS:
        raise LabError(f"el laboratorio declara 'kind' {kind!r}, que no existe. Se admite: {', '.join(sorted(KINDS))}")
    if kind == "control":
        _validate_control(lab, env)
        return

    for key in ("lab", "networks", "nodes"):
        if key not in lab:
            raise LabError(f"la declaración no tiene '{key}', y sin eso no hay laboratorio")

    name = lab["lab"]
    if not isinstance(name, str) or not LAB_NAME_RE.match(name):
        raise LabError(
            f"el nombre del laboratorio {name!r} no vale: una letra y un título que se lee, "
            "en minúsculas y con guion bajo"
        )

    spaces = lab.get("address_spaces") or []
    if not isinstance(spaces, list) or not spaces:
        raise LabError("'address_spaces' tiene que ser una lista con al menos un CIDR")
    nets = []
    for space in spaces:
        try:
            nets.append(ipaddress.ip_network(space, strict=False))
        except ValueError as exc:
            raise LabError(f"espacio de direcciones inválido {space!r}: {exc}") from exc
    for i, a in enumerate(nets):
        for b in nets[i + 1:]:
            if a.overlaps(b):
                raise LabError(
                    f"los espacios {a} y {b} del laboratorio '{name}' se pisan: "
                    "cada laboratorio tiene que tener espacios disjuntos"
                )
    mgmt = ipaddress.ip_network(env["management"]["address_space"], strict=False)
    for space in nets:
        if space.overlaps(mgmt):
            raise LabError(
                f"el espacio {space} pisa la red de gestión {mgmt}, que no pertenece a ningún "
                "laboratorio: elige otro rango"
            )

    declared_networks = lab["networks"]
    if not isinstance(declared_networks, list) or not declared_networks:
        raise LabError("'networks' tiene que ser una lista con al menos una red")
    seen = set()
    by_name = {}
    for net in declared_networks:
        if not isinstance(net, dict):
            raise LabError(f"una red tiene que ser un mapa, y hay {net!r}")
        extra = set(net) - NETWORK_KEYS
        if extra:
            raise LabError(f"clave desconocida en la red {net.get('name')!r}: {', '.join(sorted(extra))}")
        if "name" not in net or "address" not in net:
            raise LabError(f"la red {net!r} necesita 'name' y 'address'")
        if net["name"] in seen:
            raise LabError(f"la red {net['name']!r} está declarada dos veces")
        forma = net.get("shape")
        if forma is not None and forma not in NETWORK_SHAPES:
            raise LabError(
                f"la red {net['name']!r} declara shape {forma!r}: las formas son "
                f"{', '.join(sorted(NETWORK_SHAPES))}")
        seen.add(net["name"])
        try:
            cidr = ipaddress.ip_network(net["address"], strict=False)
        except ValueError as exc:
            raise LabError(f"la red {net['name']!r} tiene una dirección inválida: {exc}") from exc
        if not any(cidr.subnet_of(space) for space in nets):
            raise LabError(
                f"la red {net['name']!r} ({cidr}) no cabe en ningún espacio declarado en "
                f"'address_spaces' ({', '.join(str(s) for s in nets)})"
            )
        # Dos redes en el mismo bloque no son dos áreas: el plano reparte jerarquía por
        # contención y las toma una dentro de otra, así que se queda sin raíz y revienta
        # con un error interno. Se dice aquí, con las dos redes delante.
        if cidr in by_name.values():
            otra = next(n for n, suya in by_name.items() if suya == cidr)
            raise LabError(
                f"la red {net['name']!r} repite el CIDR {cidr}, que ya es de {otra!r}: "
                "dos áreas con la misma dirección no se pueden anidar"
            )
        by_name[net["name"]] = cidr

    nodes = lab["nodes"]
    if not isinstance(nodes, list) or not nodes:
        raise LabError("'nodes' tiene que ser una lista con al menos un nodo")
    roles = set()
    for node in nodes:
        _validate_node(node, by_name, roles)
        roles.add(node["role"])

    for node in nodes:
        for after in node.get("after") or []:
            if after not in roles:
                raise LabError(
                    f"el nodo {node['role']!r} espera a {after!r}, que no está declarado en el laboratorio"
                )
    _reject_stage_cycles(nodes)
    _validate_links(lab)
    _validate_reservas(lab, by_name)


def _validate_control(lab: dict, env: dict) -> None:
    """Un laboratorio de control: el servicio persistente, sin topología.

    No declara espacios ni cables porque no dibuja una red: su nodo vive en la
    red de gestión, que no pertenece a ningún laboratorio. Su nombre sigue la misma
    regla que el de cualquier laboratorio —una letra y un título— y su nodo se llama
    por el servicio que declara, no por el patrón de un equipo.
    """
    name = lab["lab"]
    if not isinstance(name, str) or not LAB_NAME_RE.match(name):
        raise LabError(
            f"el nombre del laboratorio de control {name!r} no vale: una letra y un "
            "título que se lee, en minúsculas y con guion bajo"
        )
    for key in ("address_spaces", "networks", "links"):
        if key in lab:
            raise LabError(
                f"el laboratorio de control {name!r} no declara '{key}': no dibuja una "
                "topología; su nodo vive en la red de gestión"
            )
    nodes = lab.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise LabError("'nodes' tiene que ser una lista con al menos un nodo")
    if len(nodes) > 1:
        raise LabError(
            f"el laboratorio de control {name!r} declara {len(nodes)} nodos: un laboratorio "
            "de control es el servicio persistente, y hay uno"
        )
    roles = set()
    for node in nodes:
        _validate_control_node(node, roles)
        roles.add(node["role"])


def _validate_control_node(node: dict, roles: set) -> None:
    if not isinstance(node, dict):
        raise LabError(f"un nodo tiene que ser un mapa, y hay {node!r}")
    extra = set(node) - NODE_KEYS
    if extra:
        raise LabError(f"clave desconocida en el nodo {node.get('role')!r}: {', '.join(sorted(extra))}")
    for key in ("role", "type", "stage"):
        if key not in node:
            raise LabError(f"el nodo {node.get('role')!r} no tiene '{key}', y es obligatorio")
    role = node["role"]
    if not isinstance(role, str) or not CONTROL_NODE_RE.match(role):
        raise LabError(
            f"el nombre del nodo de control {role!r} no vale: se llama por el servicio "
            "que declara el laboratorio, en minúsculas, con números y guiones"
        )
    if role in roles:
        raise LabError(f"el nodo {role!r} está declarado dos veces: es el servicio persistente y hay uno")
    if node["type"] != "control":
        raise LabError(
            f"el nodo {role!r} de un laboratorio de control declara tipo {node['type']!r}: "
            "sólo se admite 'control'"
        )
    if not isinstance(node["stage"], int) or isinstance(node["stage"], bool) or node["stage"] < 1:
        raise LabError(f"el nodo {role!r} tiene que declarar 'stage' como entero >= 1")
    if "networks" in node:
        raise LabError(
            f"el nodo {role!r} no declara 'networks': su única pata es la red de gestión"
        )
    address = node.get("address", "management")
    if address != "management":
        raise LabError(
            f"el nodo {role!r} tiene 'address' {address!r}: en un laboratorio de control la "
            "dirección se deriva del vmid en la red de gestión"
        )
    resources = node.get("resources") or {}
    if not isinstance(resources, dict):
        raise LabError(f"'resources' del nodo {role!r} tiene que ser un mapa")
    unknown = set(resources) - {"cores", "memory", "disk"}
    if unknown:
        raise LabError(f"recurso desconocido en {role!r}: {', '.join(sorted(unknown))}")
    for key, value in resources.items():
        if not isinstance(value, int) or value <= 0:
            raise LabError(f"el recurso {key!r} del nodo {role!r} tiene que ser un entero positivo")
    if "image" in node and not isinstance(node["image"], str):
        raise LabError(f"'image' del nodo {role!r} tiene que ser texto")
    configure = node.get("configure") or {}
    if not isinstance(configure, dict):
        raise LabError(f"'configure' del nodo {role!r} tiene que ser un mapa de áreas")
    for area in configure:
        if area not in AREAS["linux"]:
            raise LabError(
                f"el nodo {role!r} declara el área {area!r}, que no existe para su tipo. "
                f"Se admite: {', '.join(sorted(AREAS['linux']))}"
            )
    for area, body in configure.items():
        _validate_area(role, area, body, {})


def _validate_links(lab: dict) -> None:
    """Cada cable une dos puertos, y cada puerto del laboratorio va en un cable.

    Un puente es un cable tonto: no tiene dirección, ni puerta, ni MAC. Por eso
    la declaración no puede dejar puertos sueltos —un puerto sin cable no es una
    red, es un olvido— ni unir dos puertos de redes distintas, que sería un
    cable que mezcla dos planes de direcciones sin decirlo.

    Un puerto se llama con una sola cifra porque el nombre del cable tiene que
    caber en los 15 caracteres de un nombre de interfaz de Linux: la letra del
    laboratorio, las dos puntas con su `p` y su puerto. De ahí que un equipo no
    pueda tener más de nueve puertos cableados, y que se diga aquí.
    """
    links = lab.get("links")
    if not isinstance(links, list) or not links:
        raise LabError(
            "'links' tiene que ser una lista con al menos un cable: "
            "cada cable une dos puertos y se convierte en un puente"
        )
    by_role = {n["role"]: n for n in lab["nodes"]}
    used = set()
    for i, link in enumerate(links):
        if not isinstance(link, dict):
            raise LabError(f"el cable {i + 1} tiene que ser un mapa con 'a' y 'z'")
        extra = set(link) - LINK_KEYS
        if extra:
            raise LabError(f"clave desconocida en el cable {i + 1}: {', '.join(sorted(extra))}")
        if set(link) != LINK_KEYS:
            raise LabError(f"el cable {i + 1} necesita exactamente 'a' y 'z' (las dos puntas)")
        ends = []
        for end in ("a", "z"):
            body = link[end]
            if not isinstance(body, dict) or set(body) != END_KEYS:
                raise LabError(f"la punta {end!r} del cable {i + 1} es {{node, port}}")
            node = by_role.get(body["node"])
            if node is None:
                raise LabError(
                    f"el cable {i + 1} cita el nodo {body['node']!r}, que no está declarado"
                )
            port = body["port"]
            if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 9:
                raise LabError(
                    f"el puerto de {body['node']!r} tiene que ser un entero de 1 a 9: "
                    "el nombre del cable es `letra+punta+p+puerto` y tiene que caber en los "
                    "15 caracteres de un nombre de interfaz de Linux"
                )
            if port > len(node["networks"]):
                raise LabError(
                    f"el nodo {body['node']!r} declara {len(node['networks'])} puerto(s) "
                    f"y el cable {i + 1} pide el puerto {port}"
                )
            key = (body["node"], port)
            if key in used:
                raise LabError(
                    f"el puerto {port} de {body['node']!r} está en dos cables: cada puerto es un cable"
                )
            used.add(key)
            ends.append((node, port))
        red_a = ends[0][0]["networks"][ends[0][1] - 1]
        red_z = ends[1][0]["networks"][ends[1][1] - 1]
        if red_a != red_z:
            raise LabError(
                f"el cable {i + 1} une {ends[0][0]['role']!r} puerto {ends[0][1]} ({red_a}) con "
                f"{ends[1][0]['role']!r} puerto {ends[1][1]} ({red_z}): las dos puntas tienen que "
                "estar en la misma red; si quieres unir dos redes, eso es un router, no un cable"
            )
    for node in lab["nodes"]:
        for port in range(1, len(node["networks"]) + 1):
            if (node["role"], port) not in used:
                raise LabError(
                    f"el puerto {port} de {node['role']!r} no está en ningún cable: "
                    "un puente es un cable, y un puerto sin cable no tiene por dónde ir"
                )


def _check_device_name(role: str, kind: str) -> None:
    """El nombre de un equipo lo dice todo: tipo, función y ordinal.

    Dos letras iguales al código del tipo declarado, una letra de función que exista
    para ese tipo, y el ordinal. Si el nombre y el tipo no cuentan lo mismo se para
    aquí: un nombre de switch en un nodo declarado router miente sobre lo que se va a
    desplegar, y ese nombre viaja al hostname del invitado, a su nombre en Proxmox y a
    las puntas de sus cables.
    """
    match = DEVICE_RE.match(role)
    if match is None:
        raise LabError(
            f"el nombre del equipo {role!r} no vale: dos letras de tipo, una de función y "
            "el ordinal (el segundo equipo de una misma clase termina en 2)"
        )
    code, funcion, _orden = match.groups()
    if code != TYPES[kind]["code"]:
        raise LabError(
            f"el nombre del equipo {role!r} empieza por {code!r} y el nodo se declara de "
            f"tipo {kind!r}, cuyo código es {TYPES[kind]['code']!r}: el nombre y el tipo "
            "tienen que contar lo mismo"
        )
    funciones = TYPES[kind]["functions"]
    if funcion not in funciones:
        permite = ", ".join(f"{letra} ({significa})" for letra, significa in sorted(funciones.items()))
        raise LabError(
            f"la función {funcion!r} de {role!r} no existe para un {kind}: se admite {permite}"
        )


def _validate_node(node: dict, networks: dict, roles: set) -> None:
    if not isinstance(node, dict):
        raise LabError(f"un nodo tiene que ser un mapa, y hay {node!r}")
    extra = set(node) - NODE_KEYS
    if extra:
        raise LabError(f"clave desconocida en el nodo {node.get('role')!r}: {', '.join(sorted(extra))}")
    for key in ("role", "type", "stage", "networks"):
        if key not in node:
            raise LabError(f"el nodo {node.get('role')!r} no tiene '{key}', y es obligatorio")

    role = node["role"]
    if not isinstance(role, str):
        raise LabError(f"el nombre del equipo {role!r} no vale: tiene que ser texto")
    if role in roles:
        raise LabError(f"el nombre del equipo {role!r} está declarado dos veces: es el contrato de referencia")
    kind = node["type"]
    if kind not in TYPES:
        raise LabError(
            f"el nodo {role!r} declara tipo {kind!r}, que no existe. "
            f"Se admite: {', '.join(sorted(TYPES))}"
        )
    _check_device_name(role, kind)
    if not isinstance(node["stage"], int) or isinstance(node["stage"], bool) or node["stage"] < 1:
        raise LabError(f"el nodo {role!r} tiene que declarar 'stage' como entero >= 1")

    nets = node["networks"]
    if not isinstance(nets, list) or not nets:
        raise LabError(f"el nodo {role!r} no declara ninguna red: no tendría por dónde hablar")
    for net in nets:
        if net not in networks:
            raise LabError(
                f"el nodo {role!r} usa la red {net!r}, que no está declarada en 'networks' "
                f"({', '.join(sorted(networks)) or 'ninguna'})"
            )
    if kind in ("router", "firewall") and len(set(nets)) != len(nets):
        raise LabError(
            f"el nodo {role!r} declara una red repetida: un router enruta, no conmuta. "
            "Para varias patas en la misma red, declara un switch"
        )
    if kind == "switch" and len(set(nets)) != 1:
        raise LabError(
            f"el nodo {role!r} es un switch y declara {len(set(nets))} redes: un switch es "
            "un solo dominio de difusión; para unir dos redes, un router"
        )

    address = node.get("address")
    if address is None:
        # Un equipo de red no lleva dirección de laboratorio: su gestión se deriva
        # del vmid y va por la pata OOB. Sólo un puesto o un servidor declaran una.
        if not TYPES[kind]["network_device"]:
            raise LabError(f"el nodo {role!r} no declara 'address' (un CIDR o 'dhcp')")
    elif address == "dhcp":
        if TYPES[kind]["network_device"]:
            raise LabError(
                f"el nodo {role!r} es un equipo de red y no puede pedir dirección: "
                "su dirección de gestión se deriva de su vmid"
            )
    else:
        try:
            ip = ipaddress.ip_interface(address)
        except ValueError as exc:
            raise LabError(f"el nodo {role!r} tiene una dirección inválida {address!r}: {exc}") from exc
        if not any(ip.network.subnet_of(net) for net in networks.values()):
            raise LabError(
                f"la dirección {address} del nodo {role!r} no cae en ninguna red que el nodo declare"
            )
        if TYPES[kind]["network_device"] and len(nets) and ip.ip == networks[nets[0]].network_address + 1:
            pass  # la puerta de la primera red es legítima

    reserve = node.get("reserve")
    if reserve is not None:
        # Una reserva es una dirección fija dentro de una red DHCP: el equipo sigue
        # pidiendo dirección, pero el servidor siempre le da la misma. Sólo tiene
        # sentido en un nodo final que pide por DHCP; en un equipo de red su dirección
        # de gestión ya se deriva del vmid.
        if TYPES[kind]["network_device"]:
            raise LabError(
                f"el nodo {role!r} es un equipo de red y no puede declarar 'reserve': "
                "su dirección de gestión se deriva de su vmid"
            )
        if address != "dhcp":
            raise LabError(
                f"el nodo {role!r} declara 'reserve' y no pide la dirección por DHCP: "
                "'reserve' sólo acompaña a 'address: dhcp'"
            )
        try:
            reservada = ipaddress.ip_address(str(reserve))
        except ValueError as exc:
            raise LabError(
                f"la reserva {reserve!r} de {role!r} no es una dirección: {exc}"
            ) from exc
        if reservada.version != 4:
            raise LabError(f"la reserva {reserve!r} de {role!r} no es IPv4")
        if not any(reservada in networks[n] for n in nets):
            raise LabError(
                f"la reserva {reserve} de {role!r} no cae en ninguna red que el nodo declare"
            )
        for n in nets:
            red = networks[n]
            if reservada in red and reservada not in (red.network_address, red.broadcast_address):
                break
        else:
            raise LabError(
                f"la reserva {reserve} de {role!r} es la dirección de red o de difusión"
            )

    resources = node.get("resources") or {}
    if not isinstance(resources, dict):
        raise LabError(f"'resources' del nodo {role!r} tiene que ser un mapa")
    unknown = set(resources) - {"cores", "memory", "disk"}
    if unknown:
        raise LabError(f"recurso desconocido en {role!r}: {', '.join(sorted(unknown))}")
    for key, value in resources.items():
        if not isinstance(value, int) or value <= 0:
            raise LabError(f"el recurso {key!r} del nodo {role!r} tiene que ser un entero positivo")

    if "image" in node and not isinstance(node["image"], str):
        raise LabError(f"'image' del nodo {role!r} tiene que ser texto")

    configure = node.get("configure") or {}
    if not isinstance(configure, dict):
        raise LabError(f"'configure' del nodo {role!r} tiene que ser un mapa de áreas")
    allowed = AREAS["routeros"] if kind in ("router", "switch") else AREAS["linux"]
    for area in configure:
        if area not in allowed:
            raise LabError(
                f"el nodo {role!r} declara el área {area!r}, que no existe para su tipo. "
                f"Se admite: {', '.join(sorted(allowed))}"
            )
    for area, body in configure.items():
        _validate_area(role, area, body, networks)


def _validate_area(role: str, area: str, body, networks: dict) -> None:
    """Cada área tiene su forma; lo que no encaja se rechaza con el porqué."""
    if area == "addresses":
        _require_list(role, area, body)
        for item in body:
            if not isinstance(item, dict) or set(item) != {"network", "address"}:
                raise LabError(f"cada dirección de {role!r} es {{network, address}}")
            if item["network"] not in networks:
                raise LabError(f"el área 'addresses' de {role!r} cita la red {item['network']!r}, que no existe")
            try:
                ipaddress.ip_interface(item["address"])
            except ValueError as exc:
                raise LabError(f"dirección inválida en 'addresses' de {role!r}: {exc}") from exc
    elif area == "routes":
        _require_list(role, area, body)
        for item in body:
            if not isinstance(item, dict) or set(item) != {"destination", "gateway"}:
                raise LabError(f"cada ruta de {role!r} es {{destination, gateway}}")
            for key in ("destination", "gateway"):
                ipaddress.ip_interface(item[key])  # valida forma; el error de ValueError se deja subir
            # El área escribe en `/rest/ip/route`, que es la tabla IPv4; una ruta IPv6
            # pasaría la validación y luego no habría operación capaz de instalarla. Se
            # rechaza aquí y se explica el límite, en vez de llegar a `apply` sin camino.
            destino = ipaddress.ip_interface(item["destination"]).ip
            salto = ipaddress.ip_interface(item["gateway"]).ip
            if not isinstance(destino, ipaddress.IPv4Address) \
                    or not isinstance(salto, ipaddress.IPv4Address):
                raise LabError(
                    f"la ruta {item['destination']!r} -> {item['gateway']!r} de {role!r} "
                    "no es IPv4: el área 'routes' administra la tabla IPv4 del router "
                    "(/rest/ip/route) y el motor no escribe la IPv6"
                )
    elif area == "dhcp_server":
        _require_list(role, area, body)
        for item in body:
            if not isinstance(item, dict) or set(item) not in ({"network", "pool"}, {"network", "pool", "gateway"}):
                raise LabError(
                    f"cada servidor de direcciones de {role!r} es {{network, pool, gateway?}}"
                )
            if item["network"] not in networks:
                raise LabError(f"'dhcp_server' de {role!r} cita la red {item['network']!r}, que no existe")
            try:
                start, end = (ipaddress.ip_address(x) for x in str(item["pool"]).split("-"))
            except ValueError as exc:
                raise LabError(f"el margen {item['pool']!r} de {role!r} no es 'inicio-fin'") from exc
            if start > end or not start in networks[item["network"]] or not end in networks[item["network"]]:
                raise LabError(f"el margen {item['pool']!r} de {role!r} no cae dentro de {item['network']}")
    elif area == "repositories":
        _require_list(role, area, body)
        for item in body:
            if not isinstance(item, dict) or set(item) not in (
                {"name", "url", "suite", "components"},
                {"name", "url", "suite", "components", "key"},
            ):
                raise LabError(
                    f"cada repositorio de {role!r} es {{name, url, suite, components, key?}}"
                )
            for key in ("name", "url", "suite", "components"):
                if not isinstance(item[key], str) or not item[key]:
                    raise LabError(f"el campo {key!r} del repositorio de {role!r} tiene que ser texto no vacío")
            if "key" in item and (not isinstance(item["key"], str) or not item["key"]):
                raise LabError(f"la 'key' del repositorio de {role!r} tiene que ser una URL")
    elif area == "packages":
        _require_list(role, area, body)
        for item in body:
            if not isinstance(item, str) or not item:
                raise LabError(f"cada paquete de {role!r} tiene que ser un nombre no vacío")
    elif area == "files":
        _require_list(role, area, body)
        for item in body:
            if not isinstance(item, dict) or set(item) not in (
                {"path", "content"},
                {"path", "content", "mode"},
                {"path", "content", "restart"},
                {"path", "content", "mode", "restart"},
            ):
                raise LabError(f"cada fichero de {role!r} es {{path, content, mode?, restart?}}")
            if not isinstance(item["path"], str) or not item["path"].startswith("/"):
                raise LabError(f"la ruta de un fichero de {role!r} tiene que ser absoluta")
            if not isinstance(item["content"], str):
                raise LabError(f"el contenido de {item['path']!r} de {role!r} tiene que ser texto")
            if "mode" in item and (not isinstance(item["mode"], str) or not item["mode"]):
                raise LabError(f"el 'mode' de {item['path']!r} de {role!r} tiene que ser texto octal")
            # `restart` es el nombre de la unidad que tiene que releer ESTE fichero
            # cuando cambia: sin él, un fichero de configuración escrito no cambia
            # nada hasta el siguiente reinicio a mano, y el apply diría que ya está.
            if "restart" in item and (not isinstance(item["restart"], str) or not item["restart"]):
                raise LabError(f"el 'restart' de {item['path']!r} de {role!r} tiene que ser "
                               "el nombre de una unidad de systemd")
    elif area == "commands":
        _require_list(role, area, body)
        for item in body:
            if not isinstance(item, dict):
                raise LabError(f"cada comando de {role!r} tiene que ser un mapa")
            # Dos formas, y sólo dos: un trabajo de una sola vez (`creates`) o una
            # credencial (`stamp` + `secret`). La segunda guarda la huella de la
            # clave, no la clave, y la lee de secrets.yml por su nombre.
            if set(item) == {"run", "creates"}:
                if not isinstance(item["creates"], str) or not item["creates"].startswith("/"):
                    raise LabError(f"la ruta 'creates' del comando de {role!r} tiene que ser absoluta")
            elif set(item) == {"run", "stamp", "secret"}:
                if not isinstance(item["stamp"], str) or not item["stamp"].startswith("/"):
                    raise LabError(f"la ruta 'stamp' del comando de {role!r} tiene que ser absoluta")
                if not isinstance(item["secret"], str) or not item["secret"]:
                    raise LabError(f"el campo 'secret' del comando de {role!r} tiene que ser texto no vacío")
            else:
                raise LabError(
                    f"cada comando de {role!r} es {{run, creates}} o {{run, stamp, secret}}: "
                    "sin marca se lanzaría en cada apply"
                )
            if not isinstance(item["run"], str) or not item["run"]:
                raise LabError(f"el campo 'run' del comando de {role!r} tiene que ser texto no vacío")
    elif area == "services":
        if not isinstance(body, dict):
            raise LabError(f"el área 'services' de {role!r} tiene que ser un mapa")
        for key, value in body.items():
            if value not in (True, False):
                raise LabError(f"el servicio {key!r} de {role!r} se declara sí o no, no {value!r}")
    elif area == "users":
        _require_list(role, area, body)
        for item in body:
            if not isinstance(item, dict) or set(item) != {"name", "password_from"}:
                raise LabError(f"cada usuario de {role!r} es {{name, password_from}}")
            if item["password_from"] != ROS_SECRET:
                raise LabError(
                    f"el usuario {item['name']!r} de {role!r} solo puede tomar la clave de "
                    f"`{ROS_SECRET}`: una clave escrita en el laboratorio no se admite"
                )
    elif area == "snmp":
        if not isinstance(body, dict):
            raise LabError(f"el área 'snmp' de {role!r} tiene que ser un mapa")
        sobran = set(body) - {"enabled", "community_from"}
        if sobran:
            raise LabError(
                f"el área 'snmp' de {role!r} no entiende {', '.join(sorted(sobran))}: "
                "es {enabled, community_from}"
            )
        if not isinstance(body.get("enabled"), bool):
            raise LabError(f"el área 'snmp' de {role!r} declara 'enabled' sí o no")
        if body["enabled"] and body.get("community_from") != SNMP_SECRET:
            raise LabError(
                f"la comunidad SNMP de {role!r} solo puede tomar el nombre de `{SNMP_SECRET}`: "
                "la comunidad se nombra, no se escribe en el laboratorio"
            )


def _require_list(role: str, area: str, body) -> None:
    if not isinstance(body, list):
        raise LabError(f"el área {area!r} de {role!r} tiene que ser una lista")


def _reject_stage_cycles(nodes: list) -> None:
    """`after` no puede morderse la cola: un ciclo es una espera eterna."""
    pending = {n["role"]: set(n.get("after") or []) for n in nodes}
    stages = {n["role"]: n["stage"] for n in nodes}
    for role, after in pending.items():
        for other in after:
            if stages[other] > stages[role]:
                raise LabError(
                    f"el nodo {role!r} (etapa {stages[role]}) espera a {other!r} (etapa {stages[other]}): "
                    "un nodo no puede esperar a una etapa posterior"
                )
    seen, stack = set(), set()

    def visit(role, trail):
        if role in stack:
            raise LabError(f"el orden 'after' tiene un ciclo: {' -> '.join(trail + [role])}")
        if role in seen:
            return
        stack.add(role)
        for other in pending[role]:
            visit(other, trail + [role])
        stack.discard(role)
        seen.add(role)

    for role in pending:
        visit(role, [])


def _validate_reservas(lab: dict, networks: dict) -> None:
    """Una reserva no puede pisar una dirección que ya es de alguien.

    El servidor DHCP va a conceder la dirección reservada a un nodo final, así que
    tiene que estar libre: no puede ser la dirección fija de otro equipo ni la puerta
    de la red, y dos nodos no pueden reservar la misma. Se comprueba sobre la
    declaración entera, antes de emitir el plan, para que una errata se descubra al
    calcular y no a mitad de escribir en el router.
    """
    fijas = {}

    def anota(direccion, de_quien):
        fijas.setdefault(str(ipaddress.ip_interface(direccion).ip), de_quien)

    for node in lab["nodes"]:
        role = node["role"]
        if node.get("address") and node["address"] != "dhcp":
            anota(node["address"], f"la dirección de {role!r}")
        configure = node.get("configure") or {}
        for pata in configure.get("addresses") or []:
            anota(pata["address"], f"la dirección de {role!r}")
        for srv in configure.get("dhcp_server") or []:
            if srv.get("gateway"):
                anota(srv["gateway"], f"la puerta que sirve {role!r}")
    # La puerta de cada red —la que el router declara en ella o, si nadie la declara,
    # la primera del rango— también es de alguien: reservarla dejaría al nodo sin
    # salida. Es la misma derivación que el servidor DHCP anuncia, así que una reserva
    # no puede caer en la puerta que de verdad se sirve.
    for net in lab["networks"]:
        fijas.setdefault(_gateway_for(lab, net["name"]), f"la puerta de la red {net['name']!r}")

    reservadas = {}
    for node in lab["nodes"]:
        reserva = node.get("reserve")
        if not reserva:
            continue
        role = node["role"]
        direccion = str(ipaddress.ip_address(str(reserva)))
        if direccion in reservadas:
            raise LabError(
                f"la reserva {direccion} está declarada dos veces: {role!r} y "
                f"{reservadas[direccion]!r} no pueden compartirla"
            )
        reservadas[direccion] = role
        if direccion in fijas:
            raise LabError(
                f"la reserva {direccion} de {role!r} ya es {fijas[direccion]}: "
                "una reserva tiene que estar libre"
            )


# ---------------------------------------------------------------------------
# El plan
# ---------------------------------------------------------------------------

def _dentro(address, red: ipaddress.IPv4Network | ipaddress.IPv6Network) -> bool:
    """¿La dirección declarada de una pata cae dentro de ese espacio?

    Un `dhcp` no es una dirección: no sitúa a nadie. Una dirección sin máscara
    tampoco: la declaración de una pata de laboratorio la lleva.
    """
    if not address or address == "dhcp":
        return False
    return ipaddress.ip_interface(address).ip in red


def _patas(node: dict) -> list:
    """Todas las direcciones declaradas de un equipo: la suelta y las de cada pata.

    Un router con una sola interfaz declara `address`; uno con varias patas —el que
    enruta entre dos o más redes— las declara dentro de `configure.addresses`. Para
    saber si el equipo está dentro de un espacio hay que mirar todas, no sólo la
    primera: si no, un router con una pata en la red del laboratorio y otra fuera
    pasa por no estar dentro y su espacio se queda sin ruta.
    """
    direcciones = []
    if node.get("address"):
        direcciones.append(node["address"])
    for pata in (node.get("configure") or {}).get("addresses") or []:
        if pata.get("address"):
            direcciones.append(pata["address"])
    return direcciones


def _rutas(lab: dict, nodes: list[dict]) -> list[dict]:
    """Una ruta por espacio declarado, con el router del laboratorio como salto.

    Se deriva de lo declarado: el espacio y la dirección de gestión del primer
    router declarado que lleva una pata dentro de él (el orden de la declaración
    decide cuando hay más de uno). Nadie teclea una ruta.

    Un router se cuenta como dentro del espacio si **cualquiera** de sus patas
    declaradas cae dentro, no sólo su `address`: un router de varias patas puede
    tener su primera dirección en otro sitio y seguir siendo el salto.

    Un espacio sin ningún router dentro no se puede alcanzar desde la gestión: no
    se inventa un salto ni se calla — el plan lo dice.

    Lo que se sondea para saber que el cruce está abierto es una dirección
    **detrás** del router —una pata declarada de otro equipo dentro del mismo
    espacio—, porque es lo único que demuestra que el router reenvía. Cuando no
    hay ninguna declarada (los puestos toman dirección por DHCP, y una dirección
    prestada no se declara), se sondea la pata del router y se dice que se
    comprobó el **salto**, no la red: el router responde a su propio ping aunque
    no deje pasar nada, y dar el salto por la red es declarar visto un
    laboratorio que puede seguir siendo un agujero negro.
    """
    routers = [n for n in nodes if n["type"] == "router" and n.get("management")]
    rutas = []
    for espacio in lab.get("address_spaces") or []:
        red = ipaddress.ip_network(espacio, strict=False)
        salto = None
        for router in routers:
            dentro = next((d for d in _patas(router) if _dentro(d, red)), None)
            if dentro is not None:
                salto = (router, dentro)
                break
        if salto is None:
            continue
        router, pata = salto
        detras = None
        for node in nodes:
            if node is router:
                continue
            detras = next((d for d in _patas(node) if _dentro(d, red)), None)
            if detras is not None:
                break
        rutas.append({
            "space": str(red),
            "via": router["mgmt_address"],
            "role": router["role"],
            # La dirección que se sondea para saber que el cruce está abierto, y
            # hasta dónde llega esa comprobación: la red (hay algo detrás del
            # router) o sólo el salto.
            "prueba": str(ipaddress.ip_interface(detras or pata).ip),
            "alcance": "red" if detras is not None else "salto",
        })
    return rutas


def plan(world: dict, lab: dict, env: dict) -> dict:
    """Calcula qué hay que hacer, sin tocar el mundo.

    `world` viene de la API (lo lee tasks/pve.yml); `env` de netlabs.yml. El
    resultado lleva dos mitades: `effects` (lo que un humano lee) y `steps` (lo
    que Ansible ejecuta), y las dos salen del mismo cálculo.
    """
    validate(lab, env)
    name = lab["lab"]
    control = lab.get("kind", "topology") == "control"
    # El pool se llama como el laboratorio: un nombre, no dos. La letra por la que
    # empieza el nombre es lo que la API de Proxmox exige de un pool, así que no hace
    # falta ningún prefijo que no signifique nada.
    pool = name
    management = env["management"]
    mgmt_net = ipaddress.ip_network(management["address_space"], strict=False)

    if not control:
        _check_foreign_spaces(world, lab, env)

    invitados = world.get("invitados") or []
    bridges = world.get("bridges") or []
    used = set(int(v) for v in (world.get("used_vmids") or []))
    mine = {g["vmid"]: g for g in invitados if g.get("pool") == pool}
    by_role = {}
    sobra = []
    # El invitado se reconoce por su nombre, que es el del equipo, dentro del pool del
    # laboratorio: no hay traducción que hacer entre el rol y el nombre porque son el
    # mismo, y no hace falta ninguna marca más — el pool ya dice de quién es.
    nombres = {n["role"]: n["role"] for n in lab["nodes"]}
    roles = {n["role"] for n in lab["nodes"]}
    for guest in sorted(mine.values(), key=lambda g: int(g["vmid"])):
        role = nombres.get(guest.get("name") or "")
        if role in roles and role not in by_role:
            by_role[role] = guest
        else:
            # Duplicado del mismo rol o invitado que la declaración no pide: sobra.
            sobra.append(guest)

    # Un rol que ya vive en el pool conserva su vmid: si no, el segundo apply
    # movería el invitado en vez de no hacer nada.
    assigned = {}
    for node in lab["nodes"]:
        if node["role"] in by_role:
            assigned[node["role"]] = int(by_role[node["role"]]["vmid"])
            used.discard(assigned[node["role"]])

    low, high = env["vmids"]["min"], env["vmids"]["max"]
    taken = set(used) | set(assigned.values()) | _ids_of(world.get("invitados") or [])
    for node in lab["nodes"]:
        if node["role"] in assigned:
            continue
        vmid = _lowest_free(taken, low, high)
        assigned[node["role"]] = vmid
        taken.add(vmid)

    # Los cables: cada uno es un puente tonto entre dos puertos. El nombre lleva la
    # letra del laboratorio y sus dos puntas, así que dos laboratorios con la misma
    # topología no chocan en el mismo hipervisor.
    los_cables = cables(lab) if not control else {"per_port": {}, "links": []}
    nodes = []
    effects = []
    steps = []
    for node in lab["nodes"]:
        if control:
            built = _build_control_node(node, assigned[node["role"]], name, env, mgmt_net)
        else:
            built = _build_node(node, assigned[node["role"]], name, lab, env, mgmt_net, los_cables)
        nodes.append(built)
        effects.append(
            f"{built['name']:<18} vmid {built['vmid']:<5} "
            f"{' '.join(i['label'] for i in built['interfaces'])}"
        )
    _reservar_direcciones(nodes)

    # Las rutas hacia las redes del laboratorio: una por espacio declarado, con el
    # router como salto. Las pone el invitado de gestión —por donde entra el SSH
    # del motor y donde vive lo que observa—, y sin ellas el laboratorio es un
    # agujero negro: se despliega y no se ve.
    rutas = [] if control else _rutas(lab, nodes)
    for ruta in rutas:
        # El plan dice hasta dónde llega la comprobación: con una dirección declarada
        # detrás del router se prueba la red; sin ella, sólo el salto, y decirlo es lo
        # que evita dar por visto un laboratorio que puede seguir siendo un agujero negro.
        comprobacion = ("se comprueba la red" if ruta["alcance"] == "red"
                        else "sólo hay dirección del router: se comprueba el salto")
        effects.append(
            f"ruta {ruta['space']} -> {ruta['via']} ({ruta['role']}): la red del "
            f"laboratorio, vista desde la gestión — {comprobacion}"
        )
    con_router = {r["space"] for r in rutas}
    for espacio in lab.get("address_spaces") or []:
        red = str(ipaddress.ip_network(espacio, strict=False))
        if red not in con_router:
            effects.append(
                f"el espacio {red} no tiene ningún router dentro: desde la gestión "
                "no hay camino hacia él y no se verá"
            )

    # Un puente es un cable: ni dirección, ni puerta, ni MAC. Sólo su nombre y
    # su marca, para que el motor sepa que es suyo y pueda retirarlo.
    for cable in los_cables["links"]:
        bridge = cable["name"]
        comment = f"netlabs lab={name} space={cable['space']} cable={bridge}"
        exists = next((b for b in bridges if b.get("iface") == bridge), None)
        if exists is None:
            steps.append({"op": "bridge_ensure", "bridge": bridge, "comment": comment})
            effects.append(f"crear el cable {bridge} ({cable['a']} <-> {cable['z']})")
        elif comment not in (exists.get("comments") or ""):
            raise LabError(
                f"el puente {bridge} ya existe y no lleva la marca de este laboratorio "
                f"({comment!r}): no es suyo y el motor no lo toca. Si es de otro laboratorio, "
                "cambia su 'slot'; si era tuyo, retíralo a mano"
            )

    # La otra mitad de la diferencia, también para los cables: un puente que
    # lleva la marca de este laboratorio y ya no se declara es basura suya y se
    # retira. Uno sin marca no se toca: puede ser de otro o del propio hipervisor.
    declarados = {c["name"] for c in los_cables["links"]}
    for bridge in bridges:
        iface = bridge.get("iface")
        if iface in declarados or _lab_from_comment(bridge.get("comments") or "") != name:
            continue
        steps.append({"op": "bridge_destroy", "bridge": iface,
                      "comment": bridge.get("comments") or ""})
        effects.append(f"retirar el cable {iface}: lleva la marca de {name} y no se declara")

    if pool not in (world.get("pools") or []):
        steps.append({"op": "pool_ensure", "pool": pool})
        effects.append(f"crear el pool {pool}")

    # Lo que sobra en el pool: la otra mitad de la diferencia. Sin esta cuenta, un
    # apply tras otro deja juegos de invitados viejos dentro del laboratorio.
    for guest in sobra:
        steps.append({
            "op": "guest_destroy",
            "vmid": int(guest["vmid"]),
            "name": guest.get("name"),
            # Misma forma que un nodo del plan: `type` es la clase de equipo y
            # `guest` el tipo de invitado del hipervisor. Así el retiro usa el mismo
            # fichero que `destroy` sin traducir claves.
            "type": guest.get("type"),
            "guest": guest.get("type"),
        })
        effects.append(
            f"retirar {guest.get('name')} ({guest['vmid']}): está en {pool} y la "
            "declaración no lo pide"
        )

    for built in nodes:
        existing = by_role.get(built["role"])
        if existing is None:
            steps.append({"op": "guest_create", "guest": built})
            effects.append(
                f"crear {built['guest']} {built['vmid']} '{built['name']}' en {pool} "
                f"(etapas {built['stage']})"
            )
        else:
            paso = _diferencia_del_invitado(built, existing)
            if paso is not None:
                steps.append(paso)
                if paso["op"] == "guest_set":
                    piezas = []
                    tenia = paso["tenia"]
                    if "memory" in paso and tenia.get("memory") != paso["memory"]:
                        piezas.append(f"memoria {tenia.get('memory')} -> {paso['memory']} MB")
                    if "cores" in paso and tenia.get("cores") != paso["cores"]:
                        piezas.append(f"{tenia.get('cores')} -> {paso['cores']} core(s)")
                    effects.append(
                        f"ajustar {paso['name']} ({paso['vmid']}): "
                        f"{', '.join(piezas) or 'recursos'} — se para un momento y vuelve a "
                        "arrancar; su disco no se toca"
                    )
                else:
                    effects.append(
                        f"rehacer {paso['name']} ({paso['vmid']}) y sólo ese: {paso['motivo']}"
                    )
            elif existing.get("status") != "running":
                steps.append({"op": "guest_start", "vmid": built["vmid"]})
                effects.append(f"arrancar {built['name']} ({built['vmid']})")
        # Un invitado que ya está como debe no genera paso: un plan lleno de
        # "asegurar" que no cambian nada diría que hay trabajo donde no lo hay, y
        # el segundo apply dejaría de poder decir "nada que hacer".

    if any(s["op"] == "guest_create" for s in steps):
        effects.append("cada invitado nuevo se arranca y se espera a que responda (sin dormir a ciegas)")

    # El interior de un nodo de control se converge por SSH, no por REST: su
    # configuración es la de un Linux normal (repositorios, paquetes, servicios).
    # Es un paso, no una nota al margen: el plan no puede leer el interior sin
    # entrar, así que no sabe si hay diferencia. Decir "nada que hacer" cuando
    # queda un interior por converger sería la mentira que este fichero evita.
    # La idempotencia la sostiene el apply: si el interior ya es lo declarado,
    # `linux_ops` no devuelve ninguna orden y no se escribe nada.
    for built in nodes:
        if built.get("control") and (built.get("configure") or {}):
            steps.append({
                "op": "interior_converge",
                "vmid": built["vmid"],
                "role": built["role"],
                "address": built["mgmt_address"],
            })
            effects.append(
                f"converger el interior de {built['name']} ({built['mgmt_address']}): "
                "repositorios, paquetes y servicios"
            )

    # Las rutas hacia las redes del laboratorio viven dentro del invitado de
    # gestión, así que el plan no puede leerlas sin entrar y no sabe si hay
    # diferencia. Como con el interior de un nodo de control, se dice que hay
    # trabajo por hacer; la idempotencia la sostiene el apply, que escribe sólo la
    # diferencia que encuentra.
    if rutas:
        steps.append({"op": "rutas_converge", "rutas": rutas})

    # Los equipos de red del laboratorio se registran en lo que observa el sitio para
    # que quien mira los vea con su credencial y pueda abrir su terminal sin teclear
    # nada. El plan tampoco puede leer ese censo sin entrar por su API, así que vuelve
    # a decir que hay trabajo y el apply escribe sólo la diferencia. Es una vía del
    # motor —la quinta— y tiene su propio paso porque no es converger un interior ni
    # poner una ruta: es hablar con un servicio del sitio.
    equipos = [n for n in nodes if n.get("netxms_address")]
    if equipos:
        steps.append({
            "op": "netxms_registro",
            "equipos": [{"role": n["role"], "address": n["netxms_address"]} for n in equipos],
        })
        effects.append(
            "registrar en lo que observa el sitio los equipos y nodos finales del laboratorio "
            "que falten, con su usuario y su clave cuando la tengan, y retirar los que apunten "
            "a una máquina que ya no es la suya: "
            + ", ".join(f"{n['name']} ({n['netxms_address']})" for n in equipos)
        )
        # Y el mapa: la vista dibuja su topología sola —cada equipo donde le parece, que
        # no se parece a nada de lo que dibuja el plano—, así que se le manda uno a
        # medida, con las áreas del plano y cada equipo donde el plano lo pone. Su paso
        # es el de al lado y no el mismo: el mapa se escribe después de registrar, porque
        # un elemento del mapa sin equipo detrás no lo acepta la vista.
        steps.append({"op": "netxms_mapa"})
        effects.append(
            "colocar en lo que observa el sitio el mapa de la red de este laboratorio, "
            "con cada equipo donde lo pone el plano y las redes del plano entre ellos"
        )

    return {
        "lab": name,
        "pool": pool,
        "nodes": nodes,
        "effects": effects,
        "steps": steps,
        "stages": sorted({n["stage"] for n in nodes}),
        "surplus": [int(g["vmid"]) for g in sobra],
        "rutas": rutas,
        "tunnel_forwards": [
            {"vmid": n["vmid"], "role": n["role"], "address": n["mgmt_address"]}
            for n in nodes
            if n["management"]
        ],
    }


def _endpoint(role: str, port: int) -> str:
    """La punta de un cable: el nombre del equipo y el puerto (`rte1p1`)."""
    return f"{role}p{port}"


def cables(lab: dict) -> dict:
    """Los cables del laboratorio, con su nombre y la red que transportan.

    El nombre empieza por la letra del laboratorio y sigue con sus dos puntas, así
    que dos laboratorios con la misma topología en el mismo hipervisor no comparten
    un solo puente. Devuelve `{equipo: {puerto: nombre}}` para que cada interfaz
    sepa qué puente lleva, y `links` con la lista ordenada para crear los puentes.
    """
    letra = lab["lab"][0]
    by_role = {n["role"]: n for n in lab["nodes"]}
    cidrs = {n["name"]: str(ipaddress.ip_network(n["address"], strict=False)) for n in lab["networks"]}
    per_port = {}
    links = []
    for link in lab["links"]:
        a, z = link["a"], link["z"]
        ea = _endpoint(a["node"], a["port"])
        ez = _endpoint(z["node"], z["port"])
        name = f"{letra}_{ea}_{ez}"
        if len(name) > 15:
            raise LabError(
                f"el cable {name!r} no cabe en un nombre de interfaz (15 caracteres): "
                "acorta el nombre del equipo o usa menos puertos"
            )
        red = by_role[a["node"]]["networks"][a["port"] - 1]
        per_port.setdefault(a["node"], {})[a["port"]] = name
        per_port.setdefault(z["node"], {})[z["port"]] = name
        # `space` es el CIDR de la red que el cable transporta, no su nombre: es
        # lo que otro laboratorio puede leer del comentario para no pisarlo.
        links.append({"name": name, "a": ea, "z": ez, "space": cidrs[red]})
    return {"per_port": per_port, "links": links}


def _reservar_direcciones(nodes: list[dict]) -> None:
    """Convierte cada `reserve` de un nodo final en una concesión fija del router.

    La reserva no es un objeto del invitado: es una entrada en el servidor DHCP del
    router que sirve su red. Se inyecta en el `configure.dhcp_server` del router para
    que `converge._dhcp_ops` la trate como cualquier otra diferencia declarada, sin
    que el laboratorio tenga que repetir la MAC ni el nombre del servidor.

    La reserva cae en UNA de las redes del nodo —la que la contiene— y de ahí salen la
    interfaz y su MAC: un puesto con dos patas no puede acabar reservado en el servidor
    de la primera con la tarjeta de la segunda. Las colisiones con direcciones ya
    declaradas las rechaza `_validate_reservas` antes de llegar aquí.
    """
    for nodo in nodes:
        direccion = nodo.get("reserve")
        if not direccion:
            continue
        reservada = ipaddress.ip_address(direccion)
        indice = next(
            (i for i, net in enumerate(nodo["networks"])
             if reservada in ipaddress.ip_network(net["address"], strict=False)),
            None,
        )
        # `_validate_node` ya garantiza que la reserva cae en una red del nodo; el
        # guardia está por si esa comprobación cambia, para no reservar en la red
        # equivocada en silencio.
        if indice is None:
            raise LabError(
                f"la reserva {direccion} de {nodo['role']!r} no cae en ninguna red del nodo"
            )
        red = nodo["networks"][indice]["name"]
        mac = nodo["interfaces"][indice]["mac"]
        servidor = None
        for router in nodes:
            if router["type"] not in ("router", "firewall"):
                continue
            for item in (router.get("configure") or {}).get("dhcp_server") or []:
                if item.get("network") == red:
                    servidor = (router, item)
                    break
            if servidor:
                break
        if servidor is None:
            raise LabError(
                f"el nodo {nodo['role']!r} reserva {direccion} en la red {red!r}, "
                "pero ningún router declara un servidor DHCP para esa red"
            )
        _router, item = servidor
        item.setdefault("leases", []).append({
            "address": direccion,
            "mac": mac,
            "role": nodo["role"],
        })


def _build_node(node, vmid, lab_name, lab, env, mgmt_net, cables) -> dict:
    kind = node["type"]
    code = TYPES[kind]["code"]
    networks = {n["name"]: ipaddress.ip_network(n["address"], strict=False) for n in lab["networks"]}
    interfaces = []
    for i, net_name in enumerate(node["networks"]):
        cable = cables["per_port"][node["role"]][i + 1]
        interfaces.append({
            "index": i,
            "network": net_name,
            "bridge": cable,
            "mac": derive_mac(vmid, i),
            # La etiqueta dice el cable que de verdad lleva la tarjeta, no la red:
            # si dijera la red, el plan mentiría sobre lo que hay en el hipervisor.
            "label": f"net{i}={cable}",
            "address": None,
            "gateway": None,
        })
    management = TYPES[kind]["network_device"]
    if management:
        index = len(interfaces)
        address = derive_management(vmid, env["management"]["address_space"])
        interfaces.append({
            "index": index,
            "network": None,
            "bridge": env["management"]["bridge"],
            "mac": derive_mac(vmid, index),
            "label": f"net{index}=oob({address})",
        })

    address = node.get("address")
    static = None if address in (None, "dhcp") else str(ipaddress.ip_interface(address))
    reservada = None
    if address == "dhcp" and node.get("reserve"):
        reservada = str(ipaddress.ip_address(node["reserve"]))
    # Un puesto con dirección fija sale por la puerta que declara el router de su red;
    # si nadie la declara, la primera del rango. Se deriva, no se pide.
    if static and not TYPES[kind]["network_device"]:
        interfaces[0]["address"] = static
        interfaces[0]["gateway"] = _gateway_for(lab, node["networks"][0])
    return {
        "role": node["role"],
        "type": kind,
        "guest": TYPES[kind]["guest"],
        "vmid": vmid,
        "name": node["role"],
        "description": f"netlabs lab={lab_name} role={node['role']}",
        "stage": node["stage"],
        "after": node.get("after") or [],
        "cores": (node.get("resources") or {}).get("cores", 1),
        "memory": (node.get("resources") or {}).get("memory", 512),
        "disk": (node.get("resources") or {}).get("disk", 4),
        "image": node.get("image") or (
            env["proxmox"]["template_router"] if kind in ("router", "switch") else None
        ),
        "interfaces": interfaces,
        "management": management,
        "mgmt_address": str(derive_management(vmid, env["management"]["address_space"])) if management else None,
        # La dirección con la que la vista registra este nodo: la de gestión para un
        # equipo de red, la estática o la reservada para un nodo final. Un `dhcp` sin
        # reserva no tiene ninguna todavía, y por eso no entra en el registro ni en el
        # mapa; con reserva sí, porque el servidor siempre le dará esa.
        "netxms_address": (
            str(derive_management(vmid, env["management"]["address_space"])) if management
            else (str(ipaddress.ip_interface(static).ip)
                  if static and not TYPES[kind]["network_device"] else reservada)
        ),
        "address": static or ("dhcp" if address == "dhcp" else None),
        "reserve": reservada,
        "networks": [{"name": n, "address": str(networks[n])} for n in node["networks"]],
        # El plan no comparte estructura con la declaración que recibe: si el motor
        # añadiera la concesión al `dhcp_server` del laboratorio, el segundo plan de la
        # misma declaración la volvería a validar y rechazaría su propia clave.
        "configure": copy.deepcopy(node.get("configure") or {}),
    }


def _build_control_node(node, vmid, lab_name, env, mgmt_net) -> dict:
    """El nodo de control: una sola pata en la red de gestión y nombre de servicio.

    Se llama por su rol, no por `<código>-<rol>`: es el servicio que ya existía
    antes de que hubiera motor, y renombrarlo en caliente no es una opción. Su
    MAC y su dirección se derivan del vmid, igual que las del resto.
    """
    management = env["management"]
    address = derive_management(vmid, management["address_space"])
    prefix = ipaddress.ip_network(management["address_space"], strict=False).prefixlen
    # El invitado de control **es** el de gestión, y ese se declara en `netlabs.yml`
    # (`management`): sus recursos salen de ahí, no de un número por defecto. Si el
    # laboratorio no declarara unos, el plan pediría 1 core contra los 2 del invitado
    # vivo y `apply a_bootstrap` se pararía diciendo que hace falta destroy —un desacuerdo
    # entre el sitio y el laboratorio que no existe en la realidad—. El laboratorio puede
    # sobreescribirlos con `resources` si algún día hace falta.
    resources = node.get("resources") or {}
    return {
        "role": node["role"],
        "type": node["type"],
        "guest": TYPES[node["type"]]["guest"],
        "vmid": vmid,
        "name": node["role"],
        "description": f"netlabs lab={lab_name} role={node['role']}",
        "stage": node["stage"],
        "after": node.get("after") or [],
        "cores": resources.get("cores", management["cores"]),
        "memory": resources.get("memory", management["memory"]),
        "disk": resources.get("disk", management["disk"]),
        "image": node.get("image"),
        "interfaces": [{
            "index": 0,
            "network": None,
            "bridge": management["bridge"],
            "mac": derive_mac(vmid, 0),
            "address": f"{address}/{prefix}",
            "gateway": management["gateway"],
            "label": f"net0=oob({address})",
        }],
        "management": False,
        "control": True,
        "mgmt_address": str(address),
        "address": f"{address}/{prefix}",
        "networks": [],
        "configure": node.get("configure") or {},
    }


def _gateway_for(lab: dict, network: str) -> str:
    """La puerta de una red es la dirección que el router declara en ella; si no
    declara ninguna, la primera del rango. Es derivación, no un número escrito."""
    for node in lab["nodes"]:
        if not TYPES[node["type"]]["network_device"]:
            continue
        for item in (node.get("configure") or {}).get("addresses") or []:
            if item["network"] == network:
                return str(ipaddress.ip_interface(item["address"]).ip)
    for declared in lab["networks"]:
        if declared["name"] == network:
            return str(ipaddress.ip_network(declared["address"]).network_address + 1)
    raise LabError(f"la red {network!r} no está declarada y no tiene puerta")


def _diferencia_del_invitado(built: dict, existing: dict) -> dict | None:
    """Qué hay que hacer con un invitado que ya existe, sin tocar a los demás.

    Antes cualquier diferencia de recursos paraba el plan con un «hace falta
    destroy», y el destroy se lleva el laboratorio entero: subir la memoria de ocho
    switches costaba tirar otros dieciséis equipos que estaban bien. Arreglar uno
    costaba arreglarlos todos.

    Se distinguen dos arreglos, cada uno sobre UN invitado:

    - `guest_set`: cores y memoria. Proxmox los escribe en el config del invitado;
      como aquí no hay globo de memoria, se para un momento y vuelve a arrancar. Su
      disco no se toca: no pierde lo que tenía dentro.
    - `guest_recreate`: lo que no se cambia en caliente de ninguna manera —de máquina
      virtual a contenedor, o el nombre, que es el del rol—: se retira ese y se
      vuelve a crear ese, y sólo ese.
    """
    if int(existing["vmid"]) != built["vmid"]:
        raise LabError(
            f"el rol {built['role']!r} sale con vmid {built['vmid']} y en el mundo está con "
            f"{existing['vmid']}: un vmid no se reescribe, porque los demás invitados y los "
            "puentes lo referencian por número"
        )
    motivo = ""
    if existing.get("name") and existing["name"] != built["name"]:
        motivo = f"se llamaba {existing['name']!r}"
    elif {existing.get("type")} != {built["guest"]}:
        motivo = f"pasa de {existing.get('type')} a {built['guest']}"
    if motivo:
        return {"op": "guest_recreate", "vmid": built["vmid"], "name": built["name"],
                "type": existing.get("type"), "built": built, "motivo": motivo}

    # Los valores ESCRITOS en su config mandan; los del clúster son de en marcha y no
    # ven el cambio que aún no se ha aplicado (a un invitado encendido se le cambia la
    # memoria en el config y sigue con la vieja hasta reiniciar).
    cores_vivos = existing.get("config_cores")
    if cores_vivos is None:
        cores_vivos = existing.get("cores")
    memoria_mb = existing.get("config_memory")
    if not memoria_mb:
        memoria_bytes = existing.get("memory_bytes")
        memoria_mb = (int(memoria_bytes) // (1024 * 1024)) if memoria_bytes else None

    nuevo: dict = {}
    if cores_vivos is not None and int(cores_vivos) != int(built["cores"]):
        nuevo["cores"] = int(built["cores"])
    if memoria_mb and int(memoria_mb) != int(built["memory"]):
        nuevo["memory"] = int(built["memory"])
    if not nuevo:
        return None
    return {
        "op": "guest_set",
        "vmid": built["vmid"],
        "name": built["name"],
        "type": built["guest"],
        "status": existing.get("status") or "unknown",
        "cores": int(built["cores"]),
        "memory": int(built["memory"]),
        # Lo que tenía, para poder contarlo en el plan y en el informe: un plan que
        # dice el valor nuevo y calla el viejo no enseña la diferencia.
        "tenia": {"cores": cores_vivos, "memory": memoria_mb},
    }


def _check_foreign_spaces(world: dict, lab: dict, env: dict) -> None:
    """Los espacios declarados no se pisan con lo que ya hay en el hipervisor."""
    mine = {ipaddress.ip_network(s, strict=False) for s in lab["address_spaces"]}
    for bridge in world.get("bridges") or []:
        comment = bridge.get("comments") or ""
        other = _lab_from_comment(comment)
        if not other or other == lab["lab"]:
            continue
        # Un puente es un cable tonto: no lleva CIDR. El espacio del otro
        # laboratorio viaja en la marca, que es lo que se puede leer de él.
        cidr = _space_from_comment(comment) or bridge.get("cidr")
        if not cidr:
            continue
        try:
            live = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        for space in mine:
            if space.overlaps(live):
                raise LabError(
                    f"el espacio {space} del laboratorio '{lab['lab']}' se pisa con el de '{other}' "
                    f"({live} en {bridge['iface']}): los espacios de direcciones tienen que ser disjuntos"
                )


def _lab_from_comment(comment: str):
    # El nombre de un laboratorio lleva guion bajo (`b_router_dos_puestos`) y la letra
    # por la que empieza: si la marca se partiera en la primera palabra, el laboratorio
    # no se reconocería a sí mismo y se tomaría por otro con el mismo espacio. El
    # patrón es el de un nombre válido (`LAB_NAME_RE`: minúsculas, una letra inicial y
    # guion bajo), no uno más ancho: una marca como `lab=a_x-space=...` contaría como
    # un laboratorio distinto, y esto decide qué puentes se retiran en `bridge_destroy`.
    match = re.search(r"netlabs\s+lab=([a-z][a-z0-9_]*)", comment)
    return match.group(1) if match else None


def _space_from_comment(comment: str):
    match = re.search(r"\bspace=([0-9./]+)", comment or "")
    return match.group(1) if match else None


def _ids_of(invitados) -> set:
    return {int(g["vmid"]) for g in invitados if g.get("vmid") is not None}


def _lowest_free(taken: set, low: int, high: int) -> int:
    for vmid in range(low, high + 1):
        if vmid not in taken:
            return vmid
    raise LabError(
        f"no queda ningún vmid libre entre {low} y {high} en el clúster: "
        "retira algún invitado o sube el rango en netlabs.yml"
    )


# ---------------------------------------------------------------------------
# El servicio de gestión: el invitado persistente que abre el camino
# ---------------------------------------------------------------------------

def site(world: dict, env: dict) -> dict:
    """La identidad del invitado de gestión, que no pertenece a ningún laboratorio.

    Se deriva igual que la de un invitado de laboratorio (vmid libre más bajo,
    MAC y dirección función del vmid) y por eso no hay un número escrito en el
    repositorio. No sale del pool de ningún laboratorio y `destroy` de un
    laboratorio no lo toca.
    """
    management = env["management"]
    used = set(int(v) for v in (world.get("used_vmids") or []))
    used |= _ids_of(world.get("invitados") or [])
    vmid = _lowest_free(used, env["vmids"]["min"], env["vmids"]["max"])
    address = derive_management(vmid, management["address_space"])
    # El invitado de gestión se reconoce por su NOMBRE, no por su pool: es el servicio
    # que ya existía antes que el motor y su nombre es único en el hipervisor. Cuando el
    # laboratorio que lo declara cambia de nombre, su pool cambia con él y el invitado
    # se queda en el viejo: reconocerlo por el pool lo daría por ausente y el motor
    # crearía un segundo servicio al lado del que ya corre. La diferencia de pool se
    # arregla moviéndolo (`allow-move`, medido en la API), no creando otro.
    existing = next(
        (g for g in world.get("invitados") or [] if g.get("name") == management["guest"]),
        None,
    )
    if existing:
        vmid = int(existing["vmid"])
        address = derive_management(vmid, management["address_space"])
    pool_actual = (existing or {}).get("pool") or None
    return {
        # El rol y el nombre salen de netlabs.yml: el motor no sabe qué servicio
        # corre dentro, sólo que hay un invitado de gestión que abre el camino.
        "role": management["guest"],
        "type": "control",
        "guest": "lxc",
        "vmid": vmid,
        "name": management["guest"],
        "description": f"netlabs site=management role={management['guest']}",
        "stage": 1,
        "after": [],
        "cores": management["cores"],
        "memory": management["memory"],
        "disk": management["disk"],
        "image": None,
        "interfaces": [{
            "index": 0,
            "network": None,
            "bridge": management["bridge"],
            "mac": derive_mac(vmid, 0),
            "address": f"{address}/{ipaddress.ip_network(management['address_space']).prefixlen}",
            "gateway": management["gateway"],
            "label": f"net0=oob({address})",
        }],
        "management": False,
        "mgmt_address": str(address),
        "address": f"{address}/{ipaddress.ip_network(management['address_space']).prefixlen}",
        "networks": [],
        "configure": {},
        "exists": existing is not None,
        "pool": management["pool"],
        "pool_actual": pool_actual,
        "mover": existing is not None and pool_actual != management["pool"],
    }


# ---------------------------------------------------------------------------
# La documentación de cada laboratorio: una región generada, comprobada
# ---------------------------------------------------------------------------

DOC_BEGIN = "<!-- netlabs:begin -- generado por `./netlabs docs`; no se edita a mano -->"
DOC_END = "<!-- netlabs:end -->"


def _render_control_docs(lab: dict, env: dict) -> str:
    """La página de un laboratorio de control: un servicio, no una topología.

    No hay cables ni redes que dibujar, así que la tabla sería una mentira con
    columnas vacías. Se dice lo que el laboratorio es: qué nodo, en qué red vive y
    qué áreas convergerá dentro.
    """
    management = env["management"]
    lines = [DOC_BEGIN, "", f"## {lab['lab']}", ""]
    lines.append("Tipo: control (servicio persistente del sitio, sin topología).")
    lines.append(f"Red: `{management['bridge']}` (`{management['address_space']}`), la de gestión.")
    lines.append("")
    lines += ["### Nodes", "", "| role | type | stage | address | resources |",
              "| --- | --- | --- | --- | --- |"]
    for node in sorted(lab["nodes"], key=lambda n: n["role"]):
        resources = node.get("resources") or {}
        res = ", ".join(f"{k}={v}" for k, v in sorted(resources.items())) or "—"
        lines.append(
            f"| `{node['role']}` | {node['type']} | {node['stage']} | "
            f"management (derived) | {res} |"
        )
    areas = sorted({area for node in lab["nodes"] for area in (node.get("configure") or {})})
    if areas:
        lines += ["", "Configured areas: " + ", ".join(f"`{a}`" for a in areas) + "."]
    lines += ["", DOC_END]
    return "\n".join(lines) + "\n"


def _subred(address: str) -> str:
    """La red con una `x` en los octetos de host: `10.20.55.x/24`, como se lee un plano.

    Una red no es una dirección: escribir el `.0` hace creer que ese octeto es un
    equipo. La `x` dice lo que de verdad es, el hueco donde se numeran los equipos.
    """
    red = ipaddress.ip_network(address, strict=False)
    octetos = str(red.network_address).split(".")
    # Los octetos de host son los que quedan por debajo de la máscara: en /24 el
    # cuarto, en /16 el tercero y el cuarto. Los de red se quedan como están.
    for i in range(red.prefixlen // 8, 4):
        octetos[i] = "x"
    return ".".join(octetos) + f"/{red.prefixlen}"


def _profundidad(lab: dict) -> dict[str, int]:
    """Cuántos saltos separan a cada equipo de la raíz de la topología.

    Se mide sobre los `after` declarados: quien no espera a nadie es la raíz —lo más
    cerca de la salida— y quien espera cuelga debajo. Ordenar por esto pone arriba lo
    que da salida y abajo lo que la consume, que es el sentido N-S de la red; los
    equipos del mismo nivel quedan en la misma franja, que es el sentido E-O.
    """
    por_rol = {n["role"]: n for n in lab["nodes"]}
    memo: dict[str, int] = {}

    def prof(rol: str, vistos: frozenset) -> int:
        if rol in memo:
            return memo[rol]
        if rol in vistos:
            raise LabError(f"el ciclo de 'after' pasa por {rol!r}")
        padres = [p for p in (por_rol[rol].get("after") or []) if p in por_rol]
        memo[rol] = 1 + max((prof(p, vistos | {rol}) for p in padres), default=-1)
        return memo[rol]

    return {rol: prof(rol, frozenset()) for rol in por_rol}


def _principal(lab: dict) -> dict[str, str]:
    """En qué red se dibuja cada equipo: aquella donde tiene más patas.

    Un equipo multi-homed no puede estar dentro de dos cajas a la vez, así que se
    dibuja en la que más le ata; las demás patas se ven en las aristas y en la tabla.
    """
    principal: dict[str, str] = {}
    for node in lab["nodes"]:
        patas = list(node.get("networks") or [])
        if not patas:
            continue
        cuenta: dict[str, int] = {}
        for net in patas:
            cuenta[net] = cuenta.get(net, 0) + 1
        principal[node["role"]] = max(cuenta, key=lambda n: (cuenta[n], -patas.index(n)))
    return principal


def _pie_plano(topologia: bool) -> str:
    """El pie de figura: qué hay que saber para leer el plano sin adivinar.

    Sin clave de símbolos: lo que hay que saber para leerlo es qué es un área y qué
    dice cada línea, y eso va aquí, no en una leyenda que repita el dibujo.
    """
    if topologia:
        return ("*cada área es una red; su cabecera dice la subred y el rango que "
                "reparte. Cada equipo lleva escrito lo que no cambia —su dirección "
                "estática, o `dhcp`— y la forma de su símbolo dice su clase. La línea "
                "dice que están conectados y va sin flechas: el plano no inventa un "
                "sentido de tráfico.*")
    return ("*cada punta de cada cable dice el puerto que ocupa; la línea, el cable que "
            "los une tal y como se declara.*")


def render_docs(lab: dict, env: dict) -> str:
    """La región generada de la página del laboratorio, desde la declaración.

    No lleva vmid, MAC ni dirección de gestión: esos se derivan del hipervisor y
    un documento que los clavara mentiría en el siguiente despliegue.
    """
    validate(lab, env)
    if lab.get("kind", "topology") == "control":
        return _render_control_docs(lab, env)
    lines = [DOC_BEGIN, "", f"## {lab['lab']}"]
    lines.append("Address spaces: " + ", ".join(f"`{s}`" for s in lab["address_spaces"]))
    if lab.get("networks"):
        # El dibujo es código, no una imagen: se ve en el visor de Markdown y se puede
        # leer y comparar como cualquier otra línea del documento.
        # El plano va escrito aquí dentro, como SVG en texto: se lee y se compara como
        # cualquier otra línea del documento, y el diff del commit enseña exactamente qué
        # cambió en el dibujo cuando cambia la declaración. Va además como fichero suelto
        # (`docs.escribir_plano`), del mismo dibujo y en la misma pasada, para poder
        # abrirlo y compartirlo por sí solo y para servir de fondo al mapa de la vista.
        import plano  # noqa: PLC0415  (los módulos viven en tools/)
        # Un solo plano. Hubo dos —topología y cableado— y el de cableado lo dibujaba
        # otro motor, plano y antiguo: enseñaba los mismos equipos, los mismos puertos
        # y las mismas direcciones, pero con otra colocación, y quien abría el
        # documento veía dos dibujos que no coincidían. El bueno es este, que ya dibuja
        # un símbolo por equipo y una línea por cable con el puerto de cada punta.
        lines += ["", "### Topología", "", plano.plano(lab, "topologia"), "",
                  _pie_plano(True)]
    lines += ["", "### Networks", "", "| network | address |", "| --- | --- |"]
    for net in lab["networks"]:
        lines.append(f"| `{net['name']}` | `{net['address']}` |")
    lines += ["", "### Nodes", "", "| role | type | stage | interfaces | address | resources |",
              "| --- | --- | --- | --- | --- | --- |"]
    for node in sorted(lab["nodes"], key=lambda n: (n["stage"], n["role"])):
        resources = node.get("resources") or {}
        res = ", ".join(f"{k}={v}" for k, v in sorted(resources.items())) or "—"
        if TYPES[node["type"]]["network_device"]:
            address = "management (derived)"
        else:
            address = "from router (DHCP)" if node["address"] == "dhcp" else f"`{node['address']}`"
        lines.append(
            f"| `{node['role']}` | {node['type']} | {node['stage']} | "
            f"{', '.join(f'`{n}`' for n in node['networks'])} | {address} | {res} |"
        )
    lines += ["", "### Cables", "", "| bridge | a | z | network |", "| --- | --- | --- | --- |"]
    los_cables = cables(lab)
    for cable in los_cables["links"]:
        lines.append(f"| `{cable['name']}` | `{cable['a']}` | `{cable['z']}` | `{cable['space']}` |")
    areas = sorted({area for node in lab["nodes"] for area in (node.get("configure") or {})})
    if areas:
        lines += ["", "Configured areas: " + ", ".join(f"`{a}`" for a in areas) + "."]
    lines += ["", DOC_END]
    return "\n".join(lines) + "\n"
