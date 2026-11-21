# PROPÓSITO:   la convergencia es también una función: (lo declarado, lo que hay) ->
#              las llamadas que faltan. Aquí viven cuatro derivaciones puras que usan
#              tasks/ros.yml, tasks/interior_ssh.yml, tasks/bootstrap.yml y tasks/pve.yml:
#              leer el interior, comparar y decir qué escribir. Nada de esto habla con
#              la red: se prueba con casos inventados como la identidad.
# INVARIANTES: dentro de un área declarada, lo que sobra se quita; fuera, no se entra.
#              El nombre de cada objeto que el motor crea en el interior lleva prefijo
#              `netlabs-`: es la marca que separa lo suyo de lo que ya estaba.
#              Ninguna llamada depende de la posición en una lista: las interfaces se
#              citan por el nombre que el motor les dio (etherN), no por índice leído.
# LÍMITES:     no sabe si el interior responde; si no responde, el plan no se ejecuta.
# VER:         docs/diseno.md §2.12-§2.13, §4.4, §6; test/test_converge.py

from __future__ import annotations

import ipaddress

from identity import LabError, TYPES

# Las áreas de RouterOS que el motor sabe leer por REST. Son las mismas que valida
# identity.AREAS["routeros"]: una lectura de más es una dependencia de más.
ROS_READS = (
    "/rest/system/identity",
    "/rest/ip/address",
    "/rest/ip/pool",
    "/rest/ip/dhcp-server",
    "/rest/ip/dhcp-server/network",
    "/rest/ip/service",
    "/rest/user",
)

PREFIX = "netlabs-"

# El nombre de la interfaz es el que el motor le puso al crear el invitado: la pata
# i es ether<i>, y la de gestión es la última. No es un número de un laboratorio: es
# cómo se llama lo que el propio motor creó.
def interface_of(node: dict, network: str) -> str | None:
    """La pata que lleva una red de laboratorio, contada como la cuenta el router.

    Se recorre `interfaces` (que sí trae el índice de la tarjeta) y se numera desde
    1: `net0` de la API es `ether1` de RouterOS. Contar por `networks` daría ether0
    y, peor, devolvería None cuando la lista son dicts y no nombres.
    """
    for iface in node["interfaces"]:
        if iface.get("network") == network:
            return f"ether{iface['index'] + 1}"
    return None


def management_interface(node: dict) -> str:
    """La pata de gestión es la que no tiene red de laboratorio: la ÚLTIMA.

    Se busca en la lista de interfaces, no se cuenta `networks`: la lista de redes
    del laboratorio no incluye la pata de gestión, así que contar por ahí deja el
    nombre una pata corto (ether2 donde el motor creó ether3) y la dirección acaba
    en una red de laboratorio en vez de en la OOB.
    """
    for iface in node["interfaces"]:
        if iface.get("network") is None:
            return f"ether{iface['index'] + 1}"
    raise LabError(f"el nodo {node['role']!r} no tiene pata de gestión declarada")


# ---------------------------------------------------------------------------
# Arranque del router: el único script que se escribe por el agente
# ---------------------------------------------------------------------------

def bootstrap_script(node: dict, env: dict, routeros_password: str) -> str:
    """El script que deja al router con dirección de gestión. Una sola vez, al nacer.

    Quita el cliente de direcciones que el CHR trae de fábrica en su primera pata
    —si no, más tarde pediría una concesión en una red donde él es el servidor— y
    pone la dirección derivada en la pata de gestión, que es la ÚLTIMA: las de
    laboratorio se configuran después por REST, que es el camino normal.
    """
    if not TYPES[node["type"]]["network_device"]:
        raise LabError(f"el nodo {node['role']!r} no es un equipo de red y no se arranca por el agente")
    username = _declared_user(node) or "admin"
    space = ipaddress.ip_network(env["management"]["address_space"], strict=False)
    mgmt = node["mgmt_address"]
    return "\n".join([
        "/delay 2s",
        f'/ip service set www address={space}',
        "/ip service enable www",
        "/ip dhcp-client remove [find where interface=ether1]",
        f'/ip address remove [find where address="{mgmt}/16"]',
        f"/ip address add address={mgmt}/16 interface={management_interface(node)}",
        ':if ([:len [/user find where name="%s"]] = 0) do={/user add name="%s" group=full}'
        % (username, username),
        # El agente ejecuta con una política sin `sensitive`: `/user set` falla con
        # "not enough permissions (9)" (medido). Se intenta sin abortar el script —
        # la dirección es lo que no puede perderse — y la clave la pone la puerta
        # REST, que sí corre con la política completa del admin.
        ':do {/user set [find where name="%s"] password="%s"} on-error={:put "clave pendiente: la pone REST"}'
        % (username, _quote(routeros_password)),
        ':put "netlabs bootstrap done"',
        "",
    ])


def _declared_user(node: dict) -> str | None:
    for user in (node.get("configure") or {}).get("users") or []:
        return user["name"]
    return None


def _quote(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


# ---------------------------------------------------------------------------
# RouterOS: comparar lo declarado con lo leído y decir qué falta
# ---------------------------------------------------------------------------

def ros_ops(node: dict, current: dict, routeros_password: str) -> list[dict]:
    """Las llamadas REST que llevan el router de lo que hay a lo declarado.

    `current` es lo que devolvieron las lecturas de ROS_READS. Cada llamada lleva
    `effect`, la frase que el humano lee en el plan: si un cambio no se puede
    explicar en una frase, no se hace.
    """
    ops: list[dict] = []
    configure = node.get("configure") or {}
    if not configure:
        return ops

    if "identity" in configure:
        actual = (current.get("identity") or {}).get("name")
        deseado = configure["identity"]["name"]
        if actual != deseado:
            ops.append({"method": "POST", "path": "/rest/system/identity/set",
                        "body": {"name": deseado},
                        "effect": f"identidad del router -> {deseado}"})

    if "services" in configure:
        servicios = {s.get("name"): s for s in current.get("services") or []}
        for nombre, activo in sorted(configure["services"].items()):
            servicio = servicios.get(nombre)
            if servicio is None:
                # Los servicios de RouterOS son fijos: no se crean, se encienden o se
                # apagan. Un nombre que no existe es una errata en el laboratorio, y se
                # dice en vez de inventar un servicio que el router no tiene.
                raise LabError(
                    f"el servicio {nombre!r} no existe en el router: los servicios son "
                    f"fijos. Los que hay: {', '.join(sorted(servicios))}"
                )
            esta_deshabilitado = str(servicio.get("disabled", "false")).lower() in ("true", "yes")
            if activo == esta_deshabilitado:
                ops.append({"method": "PATCH", "path": f"/rest/ip/service/{servicio['.id']}",
                            "body": {"disabled": "no" if activo else "yes"},
                            "effect": f"servicio {nombre} {'al alta' if activo else 'de baja'}"})

    if "addresses" in configure:
        ops += _address_ops(node, configure["addresses"], current.get("addresses") or [])
    if "dhcp_server" in configure:
        ops += _dhcp_ops(node, configure["dhcp_server"], current)
    if "users" in configure:
        ops += _user_ops(configure["users"], current.get("users") or [], routeros_password)
    return ops


def _address_ops(node: dict, deseadas: list, actuales: list) -> list[dict]:
    ops = []
    nuestras = {f"ether{i}" for i in range(len(node["networks"]))}
    deseadas_por_pata = {}
    for item in deseadas:
        deseadas_por_pata.setdefault(interface_of(node, item["network"]), []).append(item["address"])
    for iface, direcciones in deseadas_por_pata.items():
        for direccion in direcciones:
            if not any(a.get("interface") == iface and a.get("address") == direccion for a in actuales):
                ops.append({"method": "PUT", "path": "/rest/ip/address",
                            "body": {"address": direccion, "interface": iface},
                            "effect": f"dirección {direccion} en {iface}"})
    for actual in actuales:
        if actual.get("interface") not in nuestras or actual.get("dynamic") == "true":
            continue
        if actual.get("address") not in sum(deseadas_por_pata.values(), []):
            ops.append({"method": "DELETE", "path": f"/rest/ip/address/{actual['.id']}",
                        "effect": f"sobra la dirección {actual.get('address')} en {actual.get('interface')}"})
    return ops


def _dhcp_ops(node: dict, declarados: list, current: dict) -> list[dict]:
    """Un servidor de direcciones son tres objetos en RouterOS: margen, servidor y red.

    Los tres llevan el prefijo del motor; lo que se llame de otra forma no se toca
    aunque viva en la misma interfaz, y lo que declaramos y no está se crea.
    """
    ops = []
    pools = {p.get("name"): p for p in current.get("pools") or []}
    servidores = {s.get("name"): s for s in current.get("dhcp_servers") or []}
    redes = {r.get("address"): r for r in current.get("dhcp_networks") or []}
    deseados_pool, deseados_srv, deseados_red = set(), set(), set()

    for item in declarados:
        iface = interface_of(node, item["network"])
        nombre = f"{PREFIX}{item['network']}"
        red = item.get("network")
        gateway = item.get("gateway") or _first_host(node, red)
        rango = str(item["pool"])
        deseados_pool.add(nombre)
        deseados_srv.add(nombre)
        deseados_red.add(_network_cidr(node, red))

        if nombre not in pools:
            ops.append({"method": "PUT", "path": "/rest/ip/pool",
                        "body": {"name": nombre, "ranges": rango},
                        "effect": f"margen de direcciones {rango} ({nombre})"})
        elif pools[nombre].get("ranges") != rango:
            ops.append({"method": "PATCH", "path": f"/rest/ip/pool/{pools[nombre]['.id']}",
                        "body": {"ranges": rango},
                        "effect": f"margen de direcciones {rango} ({nombre})"})

        if nombre not in servidores:
            ops.append({"method": "PUT", "path": "/rest/ip/dhcp-server",
                        "body": {"name": nombre, "interface": iface,
                                 "address-pool": nombre, "disabled": "no"},
                        "effect": f"servidor de direcciones en {iface} ({nombre})"})
        else:
            srv = servidores[nombre]
            if srv.get("interface") != iface or srv.get("address-pool") != nombre:
                ops.append({"method": "PATCH", "path": f"/rest/ip/dhcp-server/{srv['.id']}",
                            "body": {"interface": iface, "address-pool": nombre},
                            "effect": f"servidor de direcciones en {iface} ({nombre})"})

        cidr = _network_cidr(node, red)
        if cidr not in redes:
            ops.append({"method": "PUT", "path": "/rest/ip/dhcp-server/network",
                        "body": {"address": cidr, "gateway": gateway},
                        "effect": f"red servida {cidr} por {gateway}"})
        elif redes[cidr].get("gateway") != gateway:
            ops.append({"method": "PATCH", "path": f"/rest/ip/dhcp-server/network/{redes[cidr]['.id']}",
                        "body": {"gateway": gateway},
                        "effect": f"red servida {cidr} por {gateway}"})

    for nombre, pool in pools.items():
        if nombre.startswith(PREFIX) and nombre not in deseados_pool:
            ops.append({"method": "DELETE", "path": f"/rest/ip/pool/{pool['.id']}",
                        "effect": f"sobra el margen {nombre}"})
    for nombre, srv in servidores.items():
        if nombre.startswith(PREFIX) and nombre not in deseados_srv:
            ops.append({"method": "DELETE", "path": f"/rest/ip/dhcp-server/{srv['.id']}",
                        "effect": f"sobra el servidor {nombre}"})
    for cidr, red in redes.items():
        if cidr not in deseados_red and _is_declared_network(node, cidr):
            ops.append({"method": "DELETE", "path": f"/rest/ip/dhcp-server/network/{red['.id']}",
                        "effect": f"sobra la red servida {cidr}"})
    return ops


def _first_host(node: dict, network: str) -> str:
    for declarada in node["networks"]:
        if declarada["name"] == network:
            cidr = ipaddress.ip_network(declarada["address"])
            return str(cidr.network_address + 1)
    raise LabError(f"el nodo {node['role']!r} no declara la red {network!r}")


def _network_cidr(node: dict, network: str) -> str:
    for declarada in node["networks"]:
        if declarada["name"] == network:
            return str(ipaddress.ip_network(declarada["address"]))
    raise LabError(f"el nodo {node['role']!r} no declara la red {network!r}")


def _is_declared_network(node: dict, cidr: str) -> bool:
    return any(str(ipaddress.ip_network(n["address"])) == cidr for n in node["networks"])


def _user_ops(declarados: list, actuales: list, routeros_password: str) -> list[dict]:
    """Sólo se da de alta; la clave no se puede leer, así que no se comprueba.

    Reaplicarla en cada pasada haría `changed` en la segunda, que es justo lo que no
    puede pasar. Un cambio de clave se aplica con `destroy` + `apply`, y se dice.
    """
    existentes = {u.get("name") for u in actuales}
    ops = []
    for user in declarados:
        if user["name"] not in existentes:
            ops.append({"method": "PUT", "path": "/rest/user",
                        "body": {"name": user["name"], "password": routeros_password,
                                 "group": "full"},
                        "effect": f"usuario {user['name']}"})
    return ops


# ---------------------------------------------------------------------------
# Interior Linux: identidad y servicios, sin inventar vocabulario
# ---------------------------------------------------------------------------

def linux_ops(node: dict, current_hostname: str) -> list[dict]:
    ops = []
    configure = node.get("configure") or {}
    if "identity" in configure and configure["identity"]["name"] != current_hostname:
        ops.append({"cmd": ["hostnamectl", "set-hostname", configure["identity"]["name"]],
                    "effect": f"nombre del equipo -> {configure['identity']['name']}"})
    for service, activo in sorted((configure.get("services") or {}).items()):
        comando = (["systemctl", "enable", "--now", service] if activo
                   else ["systemctl", "disable", "--now", service])
        ops.append({"cmd": comando,
                    "effect": f"servicio {service} {'al alta' if activo else 'de baja'}",
                    "check": ["systemctl", "is-active", service],
                    "want": "active" if activo else "inactive"})
    return ops