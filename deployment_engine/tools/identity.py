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
# VER:         docs/diseno.md §2, §5, §6; test/test_identity.py

from __future__ import annotations

import ipaddress
import re

# Los tipos de nodo son un vocabulario cerrado; cada uno puede hacer una cosa.
# `network device` (router, switch) nace con la pata de gestión; `end node`
# (server, workstation) no la tiene y se llega a él por su router.
TYPES = {
    "router": {"code": "rt", "guest": "qemu", "network_device": True, "routes": True},
    "switch": {"code": "sw", "guest": "qemu", "network_device": True, "routes": False},
    "server": {"code": "srv", "guest": "lxc", "network_device": False, "routes": False},
    "workstation": {"code": "ws", "guest": "lxc", "network_device": False, "routes": False},
}

# Las áreas de configuración que el motor entiende, por clase de equipo. Una clave
# fuera de su lista es un error con mensaje (§2.13), no una nota al pie.
AREAS = {
    "routeros": {"identity", "addresses", "routes", "dhcp_server", "services", "users"},
    "linux": {"identity", "services"},
}

LAB_KEYS = {"lab", "address_spaces", "networks", "nodes"}
NODE_KEYS = {"role", "type", "stage", "after", "resources", "image", "networks", "address", "configure"}
NETWORK_KEYS = {"name", "address"}

ROLE_RE = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,30}$")


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
    for key in ("lab", "networks", "nodes"):
        if key not in lab:
            raise LabError(f"la declaración no tiene '{key}', y sin eso no hay laboratorio")

    name = lab["lab"]
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise LabError(f"el nombre del laboratorio {name!r} no vale: minúsculas, números y guiones")

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
    if not isinstance(role, str) or not ROLE_RE.match(role):
        raise LabError(f"el rol {role!r} no vale: minúsculas, números y guiones, empezando por letra")
    if role in roles:
        raise LabError(f"el rol {role!r} está declarado dos veces: es el contrato de referencia")
    kind = node["type"]
    if kind not in TYPES:
        raise LabError(
            f"el nodo {role!r} declara tipo {kind!r}, que no existe. "
            f"Se admite: {', '.join(sorted(TYPES))}"
        )
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
    if kind in ("router", "switch") and len(set(nets)) != len(nets):
        raise LabError(f"el nodo {role!r} declara una red repetida: cada pata es una interfaz")

    address = node.get("address")
    if address is None:
        raise LabError(f"el nodo {role!r} no declara 'address' (un CIDR o 'dhcp')")
    if address == "dhcp":
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
    if area == "identity":
        if not isinstance(body, dict) or set(body) != {"name"}:
            raise LabError(f"el área 'identity' de {role!r} es {{name: <texto>}}")
        if not isinstance(body["name"], str) or not body["name"]:
            raise LabError(f"el nombre de identidad de {role!r} tiene que ser texto no vacío")
    elif area == "addresses":
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
            if item["password_from"] != "secrets.routeros_password":
                raise LabError(
                    f"el usuario {item['name']!r} de {role!r} solo puede tomar la clave de "
                    "`secrets.routeros_password`: una clave escrita en el laboratorio no se admite"
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

def plan(world: dict, lab: dict, env: dict) -> dict:
    """Calcula qué hay que hacer, sin tocar el mundo.

    `world` viene de la API (lo lee tasks/pve.yml); `env` de netlabs.yml. El
    resultado lleva dos mitades: `effects` (lo que un humano lee) y `steps` (lo
    que Ansible ejecuta), y las dos salen del mismo cálculo.
    """
    validate(lab, env)
    name = lab["lab"]
    pool = f"netlabs-lab-{name}"
    management = env["management"]
    mgmt_net = ipaddress.ip_network(management["address_space"], strict=False)

    _check_foreign_spaces(world, lab, env)

    guests = world.get("guests") or []
    bridges = world.get("bridges") or []
    used = set(int(v) for v in (world.get("used_vmids") or []))
    mine = {g["vmid"]: g for g in guests if g.get("pool") == pool}
    by_role = {}
    for guest in mine.values():
        role = _role_from_description(guest.get("description") or "")
        if role:
            by_role[role] = guest

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

    nodes = []
    effects = []
    steps = []
    for node in lab["nodes"]:
        built = _build_node(node, assigned[node["role"]], name, lab, env, mgmt_net)
        nodes.append(built)
        effects.append(
            f"{built['name']:<18} vmid {built['vmid']:<5} "
            f"{' '.join(i['label'] for i in built['interfaces'])}"
        )

    # Puentes del laboratorio: se crean con su marca y se van con él.
    for net in lab["networks"]:
        bridge = _bridge_name(name, net["name"])
        comment = f"netlabs lab={name} network={net['name']}"
        exists = next((b for b in bridges if b.get("iface") == bridge), None)
        if exists is None:
            steps.append({"op": "bridge_ensure", "bridge": bridge, "comment": comment})
            effects.append(f"crear el puente {bridge} ({net['address']}) marcado '{comment}'")
        elif comment not in (exists.get("comments") or ""):
            raise LabError(
                f"el puente {bridge} ya existe y no lleva la marca de este laboratorio "
                f"({comment!r}): no es suyo y el motor no lo toca. Elige otro nombre de red "
                "o retira ese puente a mano si de verdad era tuyo"
            )

    if pool not in (world.get("pools") or []):
        steps.append({"op": "pool_ensure", "pool": pool})
        effects.append(f"crear el pool {pool}")

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
        steps.append({"op": "guest_ensure", "guest": built})

    if any(s["op"] == "guest_create" for s in steps):
        effects.append("cada invitado nuevo se arranca y se espera a que responda (sin dormir a ciegas)")

    return {
        "lab": name,
        "pool": pool,
        "nodes": nodes,
        "effects": effects,
        "steps": steps,
        "stages": sorted({n["stage"] for n in nodes}),
        "tunnel_forwards": [
            {"vmid": n["vmid"], "role": n["role"], "address": n["mgmt_address"]}
            for n in nodes
            if n["management"]
        ],
    }


def _build_node(node, vmid, lab_name, lab, env, mgmt_net) -> dict:
    kind = node["type"]
    code = TYPES[kind]["code"]
    networks = {n["name"]: ipaddress.ip_network(n["address"], strict=False) for n in lab["networks"]}
    interfaces = []
    for i, net_name in enumerate(node["networks"]):
        interfaces.append({
            "index": i,
            "network": net_name,
            "bridge": _bridge_name(lab_name, net_name),
            "mac": derive_mac(vmid, i),
            "label": f"net{i}={net_name}",
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

    address = node["address"]
    static = None if address == "dhcp" else str(ipaddress.ip_interface(address))
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
        "name": f"{code}-{node['role']}",
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
        "address": static or "dhcp",
        "networks": [{"name": n, "address": str(networks[n])} for n in node["networks"]],
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
        cidr = bridge.get("cidr")
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
    match = re.search(r"netlabs\s+lab=([A-Za-z0-9][A-Za-z0-9-]*)", comment)
    return match.group(1) if match else None


def _role_from_description(description: str):
    match = re.search(r"(?:^|\s)role=([A-Za-z0-9][A-Za-z0-9_.-]*)", description)
    return match.group(1) if match else None


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
    existing = next(
        (g for g in world.get("guests") or []
         if g.get("name") == management["guest"] and g.get("pool") == management["pool"]),
        None,
    )
    if existing:
        vmid = int(existing["vmid"])
        address = derive_management(vmid, management["address_space"])
    return {
        "role": "netxms",
        "type": "control",
        "guest": "lxc",
        "vmid": vmid,
        "name": management["guest"],
        "description": "netlabs site=management role=netxms",
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
    }


def _bridge_name(lab: str, network: str) -> str:
    # 15 caracteres es el tope de un nombre de interfaz en Linux: un nombre que no
    # cabe se dice, no se recorta, porque recortar dos redes distintas al mismo
    # nombre las juntaría en silencio.
    name = f"vmb_{lab}_{network}"
    if len(name) > 15:
        raise LabError(
            f"el puente de la red {network!r} del laboratorio {lab!r} se llamaría {name!r}, "
            "que no cabe en un nombre de interfaz (15 caracteres): acorta el laboratorio o la red"
        )
    return name


# ---------------------------------------------------------------------------
# La documentación de cada laboratorio: una región generada, comprobada
# ---------------------------------------------------------------------------

DOC_BEGIN = "<!-- netlabs:begin -- generado por `./netlabs docs`; no se edita a mano -->"
DOC_END = "<!-- netlabs:end -->"


def render_docs(lab: dict, env: dict) -> str:
    """La región generada de la página del laboratorio, desde la declaración.

    No lleva vmid, MAC ni dirección de gestión: esos se derivan del hipervisor y
    un documento que los clavara mentiría en el siguiente despliegue.
    """
    validate(lab, env)
    lines = [DOC_BEGIN, "", f"## {lab['lab']}", ""]
    lines.append("Address spaces: " + ", ".join(f"`{s}`" for s in lab["address_spaces"]))
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
    areas = sorted({area for node in lab["nodes"] for area in (node.get("configure") or {})})
    if areas:
        lines += ["", "Configured areas: " + ", ".join(f"`{a}`" for a in areas) + "."]
    lines += ["", DOC_END]
    return "\n".join(lines) + "\n"
