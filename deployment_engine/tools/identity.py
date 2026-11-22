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
               "functions": {"e": "borde", "c": "núcleo", "a": "acceso"}},
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
NODE_KEYS = {"role", "type", "stage", "after", "resources", "image", "networks", "address", "configure"}
NETWORK_KEYS = {"name", "address"}
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


def derive_management(vmid: int, address_space: str) -> ipaddress.IPv4Address:
    """La dirección de gestión es función pura del vmid dentro del plano compartido.

    `vmid % 254 + 1` nunca da .0 ni .255, que no son direcciones de equipo, y es
    biyección sobre los 254 hosts de cada /24. Un /16 encadena 255 de esos bloques
    (`vmid // 254`), así que caben vmids hasta 64769. Por encima, el motor lo dice
    en vez de inventar una dirección.
    """
    _check_vmid(vmid)
    red = ipaddress.ip_network(address_space, strict=False)
    if red.version != 4 or red.prefixlen != 16:
        raise LabError(
            f"la red de gestión tiene que ser un /16 y es {address_space!r}; "
            "es lo que hace que la dirección de cada equipo salga de su vmid sin reparto"
        )
    if vmid > 254 * 255 - 1:
        raise LabError(
            f"no cabe una dirección de gestión para el vmid {vmid} en {address_space}: "
            "un /16 admite vmids hasta 64769"
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
                {"path", "content"}, {"path", "content", "mode"}
            ):
                raise LabError(f"cada fichero de {role!r} es {{path, content, mode?}}")
            if not isinstance(item["path"], str) or not item["path"].startswith("/"):
                raise LabError(f"la ruta de un fichero de {role!r} tiene que ser absoluta")
            if not isinstance(item["content"], str):
                raise LabError(f"el contenido de {item['path']!r} de {role!r} tiene que ser texto")
            if "mode" in item and (not isinstance(item["mode"], str) or not item["mode"]):
                raise LabError(f"el 'mode' de {item['path']!r} de {role!r} tiene que ser texto octal")
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


def _rutas(lab: dict, nodes: list[dict]) -> list[dict]:
    """Una ruta por espacio declarado, con el router del laboratorio como salto.

    Se deriva de lo declarado: el espacio y la dirección de gestión del primer
    router declarado que lleva una pata dentro de él (el orden de la declaración
    decide cuando hay más de uno). Nadie teclea una ruta.

    Un espacio sin ningún router dentro no se puede alcanzar desde la gestión: no
    se inventa un salto ni se calla — el plan lo dice. Y el salto de prueba es la
    dirección que ese router tiene dentro del espacio: si no responde desde la
    gestión, o falta la ruta o el router no deja pasar.
    """
    routers = [n for n in nodes if n["type"] == "router" and n.get("management")]
    rutas = []
    for espacio in lab.get("address_spaces") or []:
        red = ipaddress.ip_network(espacio, strict=False)
        salto = next((r for r in routers if _dentro(r.get("address"), red)), None)
        if salto is None:
            continue
        rutas.append({
            "space": str(red),
            "via": salto["mgmt_address"],
            "role": salto["role"],
            # La dirección que se sondea para saber que el cruce está abierto: la
            # primera pata del router dentro del espacio.
            "prueba": str(ipaddress.ip_interface(salto["address"]).ip),
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

    guests = world.get("guests") or []
    bridges = world.get("bridges") or []
    used = set(int(v) for v in (world.get("used_vmids") or []))
    mine = {g["vmid"]: g for g in guests if g.get("pool") == pool}
    by_role = {}
    sobra = []
    # El nombre del invitado es el del equipo, así que el respaldo por nombre es el
    # propio nombre: se conserva para reconocer invitados creados antes del cambio
    # sin una llamada de configuración por cada uno.
    nombres = {n["role"]: n["role"] for n in lab["nodes"]}
    roles = {n["role"] for n in lab["nodes"]}
    for guest in sorted(mine.values(), key=lambda g: int(g["vmid"])):
        role = _role_of(guest) or nombres.get(guest.get("name") or "")
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
    taken = set(used) | set(assigned.values()) | _ids_of(world.get("guests") or [])
    for node in lab["nodes"]:
        if node["role"] in assigned:
            continue
        vmid = _lowest_free(taken, low, high)
        assigned[node["role"]] = vmid
        taken.add(vmid)

    # Los cables: cada uno es un puente tonto entre dos puertos. El nombre lleva la
    # letra del laboratorio y sus dos puntas, así que dos laboratorios con la misma
    # topología no chocan en el mismo hipervisor.
    cables = _cables(lab) if not control else {"per_port": {}, "links": []}
    nodes = []
    effects = []
    steps = []
    for node in lab["nodes"]:
        if control:
            built = _build_control_node(node, assigned[node["role"]], name, env, mgmt_net)
        else:
            built = _build_node(node, assigned[node["role"]], name, lab, env, mgmt_net, cables)
        nodes.append(built)
        effects.append(
            f"{built['name']:<18} vmid {built['vmid']:<5} "
            f"{' '.join(i['label'] for i in built['interfaces'])}"
        )

    # Las rutas hacia las redes del laboratorio: una por espacio declarado, con el
    # router como salto. Las pone el invitado de gestión —por donde entra el SSH
    # del motor y donde vive lo que observa—, y sin ellas el laboratorio es un
    # agujero negro: se despliega y no se ve.
    rutas = [] if control else _rutas(lab, nodes)
    for ruta in rutas:
        effects.append(
            f"ruta {ruta['space']} -> {ruta['via']} ({ruta['role']}): la red del "
            "laboratorio, vista desde la gestión"
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
    for cable in cables["links"]:
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
    declarados = {c["name"] for c in cables["links"]}
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
            _check_hot_changes(built, existing)
            if existing.get("status") != "running":
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


def _cables(lab: dict) -> dict:
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
        "address": static or ("dhcp" if address == "dhcp" else None),
        "networks": [{"name": n, "address": str(networks[n])} for n in node["networks"]],
        "configure": node.get("configure") or {},
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
        "cores": resources.get("cores", 1),
        "memory": resources.get("memory", 512),
        "disk": resources.get("disk", 8),
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


def _check_hot_changes(built: dict, existing: dict) -> None:
    """Lo que no se cambia en caliente se dice antes de tocar nada."""
    if int(existing["vmid"]) != built["vmid"]:
        raise LabError(f"el rol {built['role']!r} cambió de vmid: eso no se hace en caliente")
    if existing.get("type") != "lxc" and built["guest"] == "lxc":
        raise LabError(f"el rol {built['role']!r} cambia de máquina virtual a contenedor: hace falta destroy")
    if existing.get("type") == "lxc" and built["guest"] == "qemu":
        raise LabError(f"el rol {built['role']!r} cambia de contenedor a máquina virtual: hace falta destroy")
    if existing.get("name") and existing["name"] != built["name"]:
        raise LabError(
            f"el invitado existente se llama {existing['name']!r} y la declaración pide "
            f"{built['name']!r}: el nombre no se cambia en caliente"
        )


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
    # no se reconocería a sí mismo y se tomaría por otro con el mismo espacio.
    match = re.search(r"netlabs\s+lab=([A-Za-z0-9][A-Za-z0-9_-]*)", comment)
    return match.group(1) if match else None


def _space_from_comment(comment: str):
    match = re.search(r"\bspace=([0-9./]+)", comment or "")
    return match.group(1) if match else None


def _role_from_description(description: str):
    match = re.search(r"(?:^|\s)role=([A-Za-z0-9][A-Za-z0-9_.-]*)", description)
    return match.group(1) if match else None


def _role_from_tags(tags: str):
    """El rol que el motor escribió en las etiquetas del invitado.

    `/cluster/resources` NO devuelve la descripción (medido), pero SÍ las etiquetas.
    Leer el rol de ahí es lo que hace que el segundo `apply` reconozca sus propios
    invitados en vez de crear un juego nuevo cada pasada. La descripción sigue
    siendo la marca legible para un humano; las etiquetas son la marca que el motor
    puede leer sin una llamada por invitado.
    """
    for tag in (tags or "").split(";"):
        # Proxmox no admite `=` en una etiqueta, así que el motor escribe
        # `role-<rol>`; se acepta también la forma vieja `role=<rol>` para no
        # dejar de reconocer invitados creados antes de este cambio.
        for prefijo in ("role=", "role-"):
            if tag.startswith(prefijo):
                return tag[len(prefijo):]
    return None


def _role_of(guest: dict):
    """El rol de un invitado: primero la etiqueta, luego la descripción."""
    return _role_from_tags(guest.get("tags") or "") or _role_from_description(
        guest.get("description") or ""
    )


def _ids_of(guests) -> set:
    return {int(g["vmid"]) for g in guests if g.get("vmid") is not None}


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
    used |= _ids_of(world.get("guests") or [])
    vmid = _lowest_free(used, env["vmids"]["min"], env["vmids"]["max"])
    address = derive_management(vmid, management["address_space"])
    # El invitado de gestión se reconoce por su NOMBRE, no por su pool: es el servicio
    # que ya existía antes que el motor y su nombre es único en el hipervisor. Cuando el
    # laboratorio que lo declara cambia de nombre, su pool cambia con él y el invitado
    # se queda en el viejo: reconocerlo por el pool lo daría por ausente y el motor
    # crearía un segundo servicio al lado del que ya corre. La diferencia de pool se
    # arregla moviéndolo (`allow-move`, medido en la API), no creando otro.
    existing = next(
        (g for g in world.get("guests") or [] if g.get("name") == management["guest"]),
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


def _id(role: str) -> str:
    """Un identificador que Mermaid acepte: letras, cifras y guion bajo."""
    limpio = "".join(c if c.isalnum() else "_" for c in role)
    return f"n_{limpio}"


def _mermaid_topologia(lab: dict) -> list[str]:
    """Quién está en qué red y quién es su puerta: la topología, no el cableado.

    Una nube por red declarada y un equipo por nodo; cada nodo cuelga de todas las
    redes en las que tiene pata. Con `architecture-beta` los iconos son vectores
    nativos y el dibujo no depende de una fuente.
    """
    lineas = ["```mermaid", "architecture-beta"]
    for net in lab["networks"]:
        lineas.append(f"    service red_{_id(net['name'])[2:]}(cloud)[{net['name']} {net['address']}]")
    for node in lab["nodes"]:
        papel = node["type"]
        if node.get("address") and node["address"] != "dhcp":
            papel += f" {node['address']}"
        elif node.get("address") == "dhcp":
            papel += " dhcp"
        lineas.append(f"    service {_id(node['role'])}(server)[{node['role']} {papel}]")
    for node in lab["nodes"]:
        for net in dict.fromkeys(node.get("networks") or []):
            lineas.append(f"    {_id(node['role'])}:R -- L:red_{_id(net)[2:]}")
    lineas.append("```")
    return lineas


def _mermaid_cableado(lab: dict) -> list[str]:
    """Qué va con qué: el cableado tal y como se declara, en `architecture-beta`.

    Se dibuja un equipo por nodo, con sus puertos entre paréntesis, y una arista por
    cable. `architecture-beta` no admite texto en las aristas, así que el puerto de
    cada punta va en la etiqueta del equipo; el emparejamiento exacto (qué puerto con
    cuál) está en la tabla de cables, que es la que no admite interpretación.
    """
    lineas = ["```mermaid", "architecture-beta"]
    patas: dict[str, list[int]] = {}
    for link in lab.get("links") or []:
        for extremo in (link["a"], link["z"]):
            patas.setdefault(extremo["node"], []).append(extremo["port"])
    for node in lab["nodes"]:
        suyos = sorted(set(patas.get(node["role"], [])))
        etiqueta = f"{node['role']} (p{', p'.join(str(p) for p in suyos)})" if suyos else node["role"]
        lineas.append(f"    service {_id(node['role'])}(server)[{etiqueta}]")
    for link in lab.get("links") or []:
        a, z = link["a"]["node"], link["z"]["node"]
        lineas.append(f"    {_id(a)}:R -- L:{_id(z)}")
    lineas.append("```")
    return lineas


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
        lines += ["", "### Topología", ""]
        lines += _mermaid_topologia(lab)
        lines += ["", "### Cableado (L2)", ""]
        lines += _mermaid_cableado(lab)
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
    cables = _cables(lab)
    for cable in cables["links"]:
        lines.append(f"| `{cable['name']}` | `{cable['a']}` | `{cable['z']}` | `{cable['space']}` |")
    areas = sorted({area for node in lab["nodes"] for area in (node.get("configure") or {})})
    if areas:
        lines += ["", "Configured areas: " + ", ".join(f"`{a}`" for a in areas) + "."]
    lines += ["", DOC_END]
    return "\n".join(lines) + "\n"
