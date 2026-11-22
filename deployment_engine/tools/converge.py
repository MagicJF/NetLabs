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
# VER:         docs/diseno.md §2.12-§2.13, §4.4, §6; deployment_engine/tests/test_converge.py

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import shlex

from identity import LabError, ROS_SECRET, TYPES

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
    "/rest/snmp",
    "/rest/snmp/community",
    "/rest/interface/bridge",
    "/rest/interface/bridge/port",
)

PREFIX = "netlabs-"

# Las comunidades que RouterOS trae puestas de fábrica. Cualquier cliente que no se
# configure manda una de estas; si el equipo las apaga, el cliente deja de ver nada.
COMUNIDADES_DE_FABRICA = ("public", "default")

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

def bootstrap_script(node: dict, env: dict, routeros_clave: str) -> str:
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
        % (username, _quote(routeros_clave)),
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

def ros_ops(node: dict, current: dict, routeros_clave: str,
            secrets: dict | None = None, mgmt_cidr: str | None = None) -> list[dict]:
    """Las llamadas REST que llevan el router de lo que hay a lo declarado.

    `current` es lo que devolvieron las lecturas de ROS_READS. Cada llamada lleva
    `effect`, la frase que el humano lee en el plan: si un cambio no se puede
    explicar en una frase, no se hace.

    SNMP es un área declarada (`snmp: {enabled, community_from}`); sin ella el
    motor no toca el servicio. La comunidad se nombra en el laboratorio y se
    resuelve en secrets.yml; sólo lectura y restringida a la gestión.
    """
    ops: list[dict] = []
    configure = node.get("configure") or {}
    if node.get("type") == "switch":
        ops += _switch_ops(node, current)
    if not configure:
        return ops

    area_snmp = configure.get("snmp")
    if area_snmp is not None:
        ops += _snmp_ops(current.get("snmp") or {}, current.get("snmp_community") or [],
                         area_snmp, secrets, mgmt_cidr)

    # El nombre del equipo lo pone el motor desde el rol declarado: no es un área que
    # el laboratorio repita, porque una segunda verdad acaba contradiciendo a la
    # primera. El equipo se llama igual en su identidad, en su hostname y en sus cables.
    actual = (current.get("identity") or {}).get("name")
    if actual != node["name"]:
        ops.append({"method": "POST", "path": "/rest/system/identity/set",
                    "body": {"name": node["name"]},
                    "effect": f"identidad del router -> {node['name']}"})

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
        ops += _user_ops(configure["users"], current.get("users") or [], routeros_clave)
    return ops


def _snmp_ops(ajustes: dict, comunidades: list, area: dict,
              secrets: dict | None, mgmt_cidr: str | None) -> list[dict]:
    """El área `snmp` de un laboratorio: servicio encendido y una comunidad de lectura.

    NetXMS no puede sacar el nombre, las interfaces ni las tablas de rutas y ARP de un
    CHR sin SNMP; con él, el router se convierte en la fuente de lo que cuelga de sus
    redes. El laboratorio decide si se enciende; el motor deriva lo que no se declara
    (sólo lectura, y sólo desde la red de gestión).
    """
    encendido_ahora = str(ajustes.get("enabled", "")).lower() in ("true", "yes")
    if not area["enabled"]:
        if encendido_ahora:
            return [{"method": "POST", "path": "/rest/snmp/set",
                     "body": {"enabled": "no"},
                     "effect": "SNMP apagado (el laboratorio no lo declara encendido)"}]
        return []

    comunidad = secreto(secrets or {}, area["community_from"].removeprefix("secrets."))
    if len(comunidad) > 32 or any(c.isspace() for c in comunidad):
        raise LabError(
            f"la comunidad SNMP de secrets.yml no vale: entre 1 y 32 caracteres, sin espacios"
        )
    if not mgmt_cidr:
        raise LabError("falta la red de gestión para restringir la comunidad SNMP")

    ops: list[dict] = []
    if not encendido_ahora:
        ops.append({"method": "POST", "path": "/rest/snmp/set",
                    "body": {"enabled": "yes"},
                    "effect": "SNMP encendido"})

    propia = next((c for c in comunidades if c.get("name") == comunidad), None)
    # La comunidad del laboratorio es v2c, y en RouterOS el campo que lo decide es
    # `security`: con `none` el equipo atiende peticiones v1/v2c con esa comunidad. Los
    # protocolos de autenticación y cifrado son de SNMPv3 — RouterOS trae MD5/DES puestos
    # y rechaza `none` con un 400 — así que no se tocan: con `security=none` no cuentan.
    v2c = {"security": "none"}
    if propia is None:
        ops.append({"method": "PUT", "path": "/rest/snmp/community",
                    "body": {"name": comunidad, "addresses": mgmt_cidr,
                             "read-access": "yes", "write-access": "no", **v2c},
                    "effect": f"comunidad SNMP de sólo lectura (v2c), desde {mgmt_cidr}"})
    else:
        cambios: dict = {}
        if propia.get("addresses") != mgmt_cidr:
            cambios["addresses"] = mgmt_cidr
        if str(propia.get("read-access", "")).lower() not in ("true", "yes"):
            cambios["read-access"] = "yes"
        if str(propia.get("write-access", "")).lower() in ("true", "yes"):
            cambios["write-access"] = "no"
        for campo, valor in v2c.items():
            if str(propia.get(campo, "")).lower() != valor:
                cambios[campo] = valor
        if cambios:
            ops.append({"method": "PATCH", "path": f"/rest/snmp/community/{propia['.id']}",
                        "body": cambios,
                        "effect": f"comunidad SNMP -> {mgmt_cidr} (v2c, sólo lectura)"})

    # Dentro del área, lo que sobra no se apaga: una comunidad que el equipo trae de
    # fábrica (`public`, `default`) es la que cualquier cliente del sitio usa por defecto
    # —NetXMS, un `snmpwalk` a mano—, y apagarla obliga a configurar el cliente. Se acota
    # a la red de gestión, de sólo lectura y v2c, que es lo que la hace inofensiva: lo que
    # no se admite es una comunidad abierta a `::/0`, y ninguna queda así.
    for otra in comunidades:
        if otra.get("name") == comunidad:
            continue
        # Una comunidad que alguien apagó a mano se respeta; la de fábrica no: si está
        # apagada es residuo de una configuración anterior, y dejarla así es justo lo
        # que obliga a tocar el cliente. Se vuelve a encender, ya acotada.
        apagada = str(otra.get("disabled", "")).lower() in ("true", "yes")
        if apagada and otra.get("name") not in COMUNIDADES_DE_FABRICA:
            continue
        cambios = {}
        if apagada:
            cambios["disabled"] = "no"
        if otra.get("addresses") != mgmt_cidr:
            cambios["addresses"] = mgmt_cidr
        if str(otra.get("read-access", "")).lower() not in ("true", "yes"):
            cambios["read-access"] = "yes"
        if str(otra.get("write-access", "")).lower() in ("true", "yes"):
            cambios["write-access"] = "no"
        for campo, valor in v2c.items():
            if str(otra.get(campo, "")).lower() != valor:
                cambios[campo] = valor
        if cambios:
            ops.append({"method": "PATCH", "path": f"/rest/snmp/community/{otra['.id']}",
                        "body": cambios,
                        "effect": f"comunidad SNMP {otra.get('name')!r} -> {mgmt_cidr} "
                                  "(v2c, sólo lectura)"})
    return ops


def _switch_ops(node: dict, current: dict) -> list[dict]:
    """Un switch no enruta: junta sus patas de laboratorio en un solo puente.

    La pata de gestión (la última) queda fuera del puente: si entrara, el switch
    sería un cable entre la red de gestión y el laboratorio, que es justo lo que
    el diseño prohíbe. El puente se llama por la red, no por el equipo: dos
    switches del mismo laboratorio no comparten puente dentro de su RouterOS.
    """
    red = node["networks"][0]["name"]
    nombre = f"{PREFIX}{red}"
    ops: list[dict] = []

    puentes = {b.get("name") for b in current.get("bridges") or []}
    if nombre not in puentes:
        ops.append({"method": "PUT", "path": "/rest/interface/bridge",
                    "body": {"name": nombre, "protocol-mode": "none"},
                    "effect": f"puente {nombre} (sin STP: no hay bucles que romper)"})

    puertos = current.get("bridge_ports") or []
    puestas = {(p.get("bridge"), p.get("interface")) for p in puertos}
    deseadas = {(nombre, f"ether{i + 1}") for i in range(len(node["networks"]))}
    for _, interfaz in sorted(deseadas):
        if (nombre, interfaz) not in puestas:
            ops.append({"method": "PUT", "path": "/rest/interface/bridge/port",
                        "body": {"bridge": nombre, "interface": interfaz},
                        "effect": f"{interfaz} al puente {nombre}"})

    # Dentro del puente, lo que sobra se quita: una pata de gestión metida a mano
    # dejaría el laboratorio colgando de la red OOB.
    for puerto in puertos:
        if puerto.get("bridge") == nombre and \
                (puerto.get("bridge"), puerto.get("interface")) not in deseadas:
            ops.append({"method": "DELETE",
                        "path": f"/rest/interface/bridge/port/{puerto['.id']}",
                        "effect": f"sacar {puerto.get('interface')} del puente {nombre}"})
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


def secreto(secrets: dict, nombre: str) -> str:
    """El valor de un secreto del sitio, por su nombre. Ausente o vacío es un fallo."""
    valor = (secrets or {}).get(nombre)
    if not isinstance(valor, str) or not valor:
        raise LabError(
            f"secrets.yml no tiene {nombre!r} o está vacío: la credencial se nombra, "
            "el valor vive en secrets.yml"
        )
    return valor


def ros_clave(node: dict, secrets: dict) -> str:
    """La clave del router, resuelta desde el nombre que declara el laboratorio.

    El laboratorio escribe `password_from: secrets.routeros_clave`, no la clave.
    Aquí se convierte ese nombre en el valor de secrets.yml: si el nombre no
    apunta a nada, es un fallo del sitio y se dice, no se sigue con una clave
    vacía que fallaría luego en el login sin explicar por qué.
    """
    users = (node.get("configure") or {}).get("users") or [{"password_from": ROS_SECRET}]
    nombre = str(users[0].get("password_from", ROS_SECRET))
    clave_del_sitio = nombre.removeprefix("secrets.")
    valor = (secrets or {}).get(clave_del_sitio)
    if not isinstance(valor, str) or not valor:
        raise LabError(
            f"{node.get('name') or node.get('role')} toma la clave de {nombre!r} y "
            f"secrets.yml no tiene {clave_del_sitio!r}: se declara por su nombre y el "
            "valor vive en secrets.yml"
        )
    return valor


def _user_ops(declarados: list, actuales: list, routeros_clave: str) -> list[dict]:
    """Sólo se da de alta; la clave no se puede leer, así que no se comprueba.

    Reaplicarla en cada pasada haría `changed` en la segunda, que es justo lo que no
    puede pasar. Un cambio de clave se aplica con `destroy` + `apply`, y se dice.
    """
    existentes = {u.get("name") for u in actuales}
    ops = []
    for user in declarados:
        if user["name"] not in existentes:
            ops.append({"method": "PUT", "path": "/rest/user",
                        "body": {"name": user["name"], "password": routeros_clave,
                                 "group": "full"},
                        "effect": f"usuario {user['name']}"})
    return ops


# ---------------------------------------------------------------------------
# Interior Linux: identidad y servicios, sin inventar vocabulario
# ---------------------------------------------------------------------------

LINUX_STATE_SCRIPT = """\
echo "HOST:$(hostname)"
for p in {packages}; do
  if dpkg-query -W -f='${{Status}}' "$p" 2>/dev/null | grep -q 'install ok installed'; then
    echo "PKG:$p:1"
  else
    echo "PKG:$p:0"
  fi
done
for s in {services}; do
  echo "SVC:$s:$(systemctl is-active "$s" 2>/dev/null || true)"
  echo "SVC_ENABLED:$s:$(systemctl is-enabled "$s" 2>/dev/null || true)"
done
for f in /etc/apt/sources.list.d/*.list; do
  [ -e "$f" ] || continue
  echo "REPO:$(basename "$f" .list):$(base64 -w0 < "$f")"
done
for f in {files}; do
  if [ -f "$f" ]; then
    echo "FILE:$f:$(sha256sum "$f" | cut -d' ' -f1)"
    echo "MODE:$f:$(stat -c '%a' "$f")"
  else
    echo "FILE:$f:-"
  fi
done
for c in {commands}; do
  if [ -e "$c" ]; then echo "CMD:$c:1"; else echo "CMD:$c:0"; fi
done
for s in {stamps}; do
  if [ -f "$s" ]; then echo "STAMP:$s:$(cat "$s")"; else echo "STAMP:$s:-"; fi
done
true
"""


def linux_probe(node: dict) -> str:
    """El sondeo que se ejecuta por SSH para leer el interior de un Linux.

    Pregunta sólo por lo declarado: los paquetes que el nodo pide y los servicios
    que toca. Un paquete que no se declara no se consulta, porque el motor no
    tiene por qué saber qué hay dentro de un huésped que no es suyo.
    """
    configure = node.get("configure") or {}
    paquetes = " ".join(configure.get("packages") or [])
    servicios = " ".join(sorted((configure.get("services") or {}).keys()))
    ficheros = " ".join(f["path"] for f in configure.get("files") or [])
    comandos = " ".join(c["creates"] for c in configure.get("commands") or [] if "creates" in c)
    # Una marca de credencial guarda la huella de la clave, nunca la clave: así el
    # sondeo puede comparar sin que el secreto salga del fichero de secretos.
    marcas = " ".join(c["stamp"] for c in configure.get("commands") or [] if "stamp" in c)
    return LINUX_STATE_SCRIPT.format(
        packages=paquetes, services=servicios, files=ficheros, commands=comandos,
        stamps=marcas,
    )


def linux_state(text: str) -> dict:
    """El estado de un interior Linux, leído de la salida del sondeo.

    El sondeo es un script `sh` que el motor ejecuta por SSH y que imprime una
    línea por hecho: `HOST:`, `PKG:`, `SVC:` y `REPO:`. Se parsea aquí, en Python
    puro, para que la comparación se pruebe sin hipervisor.
    """
    import base64

    state = {"hostname": "", "packages": {}, "services": {}, "enabled": {},
             "repositories": {}, "files": {}, "modes": {}, "commands": {},
             "stamps": {}}
    for linea in (text or "").splitlines():
        if linea.startswith("HOST:"):
            state["hostname"] = linea[5:].strip()
        elif linea.startswith("PKG:"):
            _, nombre, valor = linea.split(":", 2)
            state["packages"][nombre] = valor.strip() == "1"
        elif linea.startswith("SVC_ENABLED:"):
            _, nombre, valor = linea.split(":", 2)
            state["enabled"][nombre] = valor.strip()
        elif linea.startswith("SVC:"):
            _, nombre, valor = linea.split(":", 2)
            state["services"][nombre] = valor.strip()
        elif linea.startswith("REPO:"):
            _, nombre, valor = linea.split(":", 2)
            try:
                state["repositories"][nombre] = base64.b64decode(valor.strip()).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001 - una línea rota no debe tumbar el plan
                state["repositories"][nombre] = ""
        elif linea.startswith("MODE:"):
            # La ruta puede llevar `:`, así que se parte por el último separador.
            resto = linea[5:]
            ruta, _, modo = resto.rpartition(":")
            state["modes"][ruta] = modo.strip()
        elif linea.startswith("FILE:"):
            # La ruta puede llevar `:`, así que se parte por el último separador.
            resto = linea[5:]
            ruta, _, huella = resto.rpartition(":")
            state["files"][ruta] = huella.strip()
        elif linea.startswith("CMD:"):
            resto = linea[4:]
            ruta, _, valor = resto.rpartition(":")
            state["commands"][ruta] = valor.strip() == "1"
        elif linea.startswith("STAMP:"):
            resto = linea[6:]
            ruta, _, huella = resto.rpartition(":")
            state["stamps"][ruta] = huella.strip()
    return state


def _repo_line(repo: dict) -> str:
    """La línea de `sources.list.d` que representa un repositorio declarado."""
    signed = f" [signed-by=/etc/apt/keyrings/{repo['name']}.gpg]" if repo.get("key") else ""
    return f"deb{signed} {repo['url']} {repo['suite']} {repo['components']}"


def _repo_script(repo: dict) -> str:
    """El script que deja el repositorio puesto. Sólo se ejecuta si difiere."""
    lineas = [
        "set -e",
        "install -d /etc/apt/keyrings",
        "export DEBIAN_FRONTEND=noninteractive",
        "command -v curl >/dev/null 2>&1 || "
        "{ apt-get update -qq && apt-get install -y -qq --no-install-recommends "
        "curl ca-certificates gnupg; }",
    ]
    if repo.get("key"):
        lineas.append(
            f"curl -fsSL {repo['key']} -o /etc/apt/keyrings/{repo['name']}.gpg"
        )
    lineas.append(
        f"printf '%s\\n' {shlex.quote(_repo_line(repo))} > "
        f"/etc/apt/sources.list.d/{repo['name']}.list"
    )
    lineas.append("apt-get update -qq")
    return "\n".join(lineas)


def _sha256(content: str) -> str:
    """La huella del contenido declarado, que es lo que se compara con el fichero."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _modo_igual(fichero: dict, current: dict) -> bool:
    """¿El fichero tiene, además del contenido, los permisos declarados?

    El contenido y los permisos son cosas distintas: un fichero con el contenido
    correcto pero el modo cambiado —un ayudante al que alguien quitó el bit de
    ejecución— pasaba por bueno y nunca se corregía. Si la declaración no fija
    `mode`, los permisos no se tocan. `stat -c %a` y el modo declarado son ambos
    octales; se comparan como número para que `0755` y `755` sean el mismo.
    """
    if not fichero.get("mode"):
        return True
    tiene = (current.get("modes") or {}).get(fichero["path"])
    if tiene is None:
        return False
    try:
        return int(str(fichero["mode"]).strip(), 8) == int(str(tiene).strip(), 8)
    except ValueError:
        return False


def _file_script(fichero: dict) -> str:
    """El script que deja un fichero con su contenido exacto.

    El contenido viaja en base64: entrecomillarlo a mano rompe con cualquier
    apóstrofo, salto de línea o `$` que lleve dentro, y un fichero de
    configuración los lleva. Base64 no tiene ninguno de esos caracteres.
    """
    payload = base64.b64encode(fichero["content"].encode("utf-8")).decode("ascii")
    ruta = shlex.quote(fichero["path"])
    lineas = [
        "set -e",
        f"install -d {shlex.quote(os.path.dirname(fichero['path']))}",
        f"printf '%s' {shlex.quote(payload)} | base64 -d > {ruta}",
    ]
    if fichero.get("mode"):
        lineas.append(f"chmod {shlex.quote(fichero['mode'])} {ruta}")
    return "\n".join(lineas)


def _sh(script: str) -> list:
    """Un script como argv para `ssh <host> sh -c ...`.

    SSH pega los argumentos con espacios y el shell remoto los vuelve a partir:
    sin comillas, un script de varias palabras llega hecho trizas y `sh -c` se
    queda con la primera. Por eso el script viaja entrecomillado con `shlex.quote`,
    que es lo mismo que hace el shell al recibirlo.
    """
    return ["sh", "-c", shlex.quote(script)]


def linux_probe_cmd(node: dict) -> list:
    """El sondeo listo para ejecutarse: el script, ya entrecomillado."""
    return _sh(linux_probe(node))


def _credencial(credenciales: dict, nombre: str) -> str:
    """El valor de una credencial declarada en `secrets.yml`.

    Se admite la forma corta (`nombre: clave`) y la larga (`nombre: {usuario,
    clave}`): el motor sólo necesita la clave, el usuario lo lee quien entra.
    """
    if not credenciales or nombre not in credenciales:
        raise LabError(
            f"la credencial {nombre!r} no está en secrets.yml: una clave no se "
            "escribe en el laboratorio, se declara por su nombre"
        )
    valor = credenciales[nombre]
    if isinstance(valor, dict):
        valor = valor.get("clave")
    if not isinstance(valor, str) or not valor:
        raise LabError(f"la credencial {nombre!r} de secrets.yml no tiene 'clave'")
    return valor


def linux_ops(node: dict, current: dict, credenciales: dict | None = None) -> list[dict]:
    """La diferencia entre lo declarado y lo que hay dentro de un Linux.

    El área es la frontera: se tocan identidad, repositorios, paquetes y
    servicios. Nada más. Cada operación lleva su comando y su efecto legible; si
    no hay diferencia, no hay operación y el segundo apply no cambia nada.
    """
    ops = []
    configure = node.get("configure") or {}
    current = current or {}
    paquetes_ahora = current.get("packages") or {}
    servicios_ahora = current.get("services") or {}
    repos_ahora = current.get("repositories") or {}

    # El repositorio primero: un paquete que sólo está en un repo nuevo no se
    # puede instalar antes de que el repo esté puesto.
    for repo in configure.get("repositories") or []:
        esperado = _repo_line(repo) + "\n"
        if (repos_ahora.get(repo["name"]) or "").strip() != esperado.strip():
            ops.append({
                "cmd": _sh(_repo_script(repo)),
                "effect": f"repositorio {repo['name']} -> {repo['url']} {repo['suite']}",
            })

    faltan = [p for p in configure.get("packages") or [] if not paquetes_ahora.get(p)]
    if faltan:
        ops.append({
            "cmd": _sh("export DEBIAN_FRONTEND=noninteractive; "
                       "apt-get install -y -qq --no-install-recommends "
                       + " ".join(faltan)),
            "effect": "paquetes: " + ", ".join(faltan),
        })

    # Los ficheros van antes que los comandos y que los servicios: un comando de
    # inicialización lee su configuración, y un servicio que arranca con una
    # configuración que aún no está escrita falla y se queda en bucle de reinicio.
    for fichero in configure.get("files") or []:
        esperado = _sha256(fichero["content"])
        if ((current.get("files") or {}).get(fichero["path"]) == esperado
                and _modo_igual(fichero, current)):
            continue
        ops.append({
            "cmd": _sh(_file_script(fichero)),
            "effect": f"fichero {fichero['path']}",
        })
        # Un fichero que **es** la configuración de un servicio no se nota hasta que el
        # servicio lo vuelve a leer. `try-restart` y no `restart`: en el primer apply el
        # servicio puede no estar en pie todavía (su base de datos se inicializa más
        # abajo, en los comandos), y `try-restart` sobre algo que no corre no arranca
        # nada —los servicios se convergen al final— mientras que sobre lo que corre sí
        # relee. Medido: sale 0 si la unidad existe y 5 si no existe, así que una errata
        # en el nombre se dice en vez de pasar por buena.
        if fichero.get("restart"):
            ops.append({
                "cmd": _sh(f"systemctl try-restart {shlex.quote(fichero['restart'])}"),
                "effect": f"releer la configuración de {fichero['restart']}: cambió {fichero['path']}",
            })

    # Los comandos con `creates` son el trabajo de una sola vez (inicializar una
    # base de datos, desplegar un WAR): se ejecutan si su marca no existe y nunca
    # más. Van después de los ficheros y antes de los servicios.
    for comando in configure.get("commands") or []:
        if "creates" in comando:
            if (current.get("commands") or {}).get(comando["creates"]):
                continue
            ops.append({
                "cmd": _sh(comando["run"]),
                "effect": f"comando: {comando['creates']}",
            })
            continue
        # Una credencial se converge por su huella: si la marca guarda el sha256
        # de la clave declarada, no hay nada que escribir. Si cambia la clave en
        # secrets.yml, la huella cambia y el comando se vuelve a ejecutar. El
        # valor nunca viaja en el comando: se pasa por la entrada estándar.
        nombre = comando["secret"]
        huella = _sha256(_credencial(credenciales or {}, nombre))
        if (current.get("stamps") or {}).get(comando["stamp"]) == huella:
            continue
        # La marca sólo se escribe si el comando salió bien: si falla, el
        # siguiente apply lo vuelve a intentar en vez de dar por hecho un
        # cambio que no ocurrió.
        # El `&&` va en la misma línea que el final del comando: en una línea
        # nueva, `sh` lo lee como principio de instrucción y aborta con
        # «Syntax error: && unexpected».
        script = (comando["run"].rstrip() + " && "
                  f"printf '%s' {shlex.quote(huella)} > {shlex.quote(comando['stamp'])}")
        ops.append({
            "cmd": _sh(script),
            "effect": f"credencial {nombre}",
            "secret": nombre,
        })

    habilitado_ahora = current.get("enabled") or {}
    for service, activo in sorted((configure.get("services") or {}).items()):
        # Arrancar y arrancar-al-iniciar son dos cosas distintas: un servicio
        # activo pero deshabilitado no recibía `enable` y uno parado pero
        # habilitado no recibía `disable`, así que se quedaba mal para siempre.
        # Se comparan las dos.
        quiere_activo = "active" if activo else "inactive"
        tiene_activo = servicios_ahora.get(service, "unknown")
        quiere_arranque = "enabled" if activo else "disabled"
        tiene_arranque = habilitado_ahora.get(service, "unknown")
        if tiene_activo == quiere_activo and tiene_arranque == quiere_arranque:
            continue
        # `restart` y no `start`: un servicio que ya está en bucle de reinicio por
        # una configuración mala no vuelve a leerla con un `start`; con `restart`
        # sí, y es lo que hace que la convergencia se note.
        comando = _sh(
            f"systemctl enable {service} && systemctl restart {service}" if activo
            else f"systemctl disable --now {service}"
        )
        ops.append({"cmd": comando,
                    "effect": f"servicio {service} {'al alta' if activo else 'de baja'}",
                    "check": ["systemctl", "is-active", service],
                    "want": quiere_activo})

    identidad = node["name"]
    if identidad and identidad != current.get("hostname"):
        ops.append({"cmd": ["hostnamectl", "set-hostname", identidad],
                    "effect": f"nombre del equipo -> {identidad}"})
    return ops


# ---------------------------------------------------------------------------
# Las rutas hacia las redes del laboratorio
# ---------------------------------------------------------------------------

def _en_mis_espacios(red, espacios: list) -> bool:
    """¿Esa ruta cae dentro de un espacio que este laboratorio declara?

    Es la frontera: dentro se quita lo que sobra, fuera no se entra. Así la ruta
    por defecto y la de la red de gestión —que también están en la tabla— no se
    tocan, y las de otro laboratorio tampoco.
    """
    return any(red.subnet_of(ipaddress.ip_network(e, strict=False)) for e in espacios or [])


def rutas_ops(actuales: list, deseadas: list, espacios: list) -> list[dict]:
    """La diferencia entre las rutas declaradas y las que tiene el invitado de gestión.

    `actuales` es la tabla real (`ip -4 -j route show`); `deseadas`, las que derivó
    el plan (una por espacio, con el router del laboratorio como salto); `espacios`,
    la frontera declarada. Cada operación lleva su comando y su efecto legible: si no
    hay diferencia, no hay operación y el segundo apply no escribe nada.
    """
    ops: list[dict] = []
    ahora: dict = {}
    for ruta in actuales or []:
        destino = ruta.get("dst") or ruta.get("destination")
        if not destino or destino == "default":
            continue
        red = ipaddress.ip_network(destino, strict=False)
        if not _en_mis_espacios(red, espacios):
            continue
        ahora[red] = ruta.get("gateway")

    declaradas = {}
    for deseada in deseadas or []:
        red = ipaddress.ip_network(deseada["space"], strict=False)
        declaradas[red] = deseada
        if ahora.get(red) == deseada["via"]:
            continue
        # `replace` y no `add`: una ruta que ya existe con otro salto no se puede
        # añadir, y el salto viejo —un router que ya no está— es justo lo que hay
        # que corregir.
        verbo = "replace" if red in ahora else "add"
        ops.append({
            "cmd": _sh(f"ip route {verbo} {red} via {deseada['via']}"),
            "effect": f"ruta {red} -> {deseada['via']} ({deseada['role']})",
        })

    for red in sorted(ahora):
        if red in declaradas:
            continue
        ops.append({
            "cmd": _sh(f"ip route del {red}"),
            "effect": f"retirar la ruta {red}: el laboratorio ya no la declara",
        })
    return ops


def cruce_cmd(ruta: dict, intentos: int = 15, espera: int = 2) -> list:
    """El sondeo del cruce: se pregunta por la pata del router dentro del espacio.

    Con tope —un número de intentos y una espera entre ellos— y con un `exit` que
    dice si respondió. El tope va dentro del script porque `until` no es válido
    sobre un `include_tasks` (medido): no se espera a ciegas, y el silencio no se
    da por bueno.
    """
    return _sh(
        f"for i in $(seq 1 {int(intentos)}); do "
        f"ping -c1 -W1 {shlex.quote(ruta['prueba'])} >/dev/null 2>&1 && exit 0; "
        f"sleep {int(espera)}; done; exit 1"
    )


# ---------------------------------------------------------------------------
# La quinta vía: registrar los equipos en lo que observa el sitio (NetXMS)
# ---------------------------------------------------------------------------
#
# El API del servicio de gestión escucha **dentro** de su invitado, y el túnel del
# motor aterriza ahí: por eso se llama con `curl` desde dentro y por la puerta de
# siempre (`interior_ssh.yml`), no desde el nodo de control.
#
# Nada viaja en la línea de órdenes donde lo vería `ps`: el testigo de la sesión va
# en la **primera línea de la entrada estándar** y el cuerpo —que lleva la clave del
# equipo— detrás. Cada llamada se lleva su testigo, así que no queda ningún fichero
# de sesión en el invitado que haya que limpiar.
#
# Medido contra NetXMS 7.0.4 (la última publicada): el login devuelve un testigo; la
# búsqueda por IP no trae las credenciales (hay que pedir la ficha del objeto); y las
# credenciales SSH **sólo se aceptan al crear el equipo** —un `PATCH` con ellas
# responde 200 y no toca la base—, que es lo que hace que un equipo ya registrado con
# otras credenciales no se pueda corregir por el API y se diga en voz alta.

NETXMS_PUERTO_SSH = 22
# Las rutas del API que el motor usa, en un solo sitio: son la parte del motor que
# sabe cómo se llama esto por dentro. Cambiar de versión del servicio se toca aquí.
NETXMS_RUTA_LOGIN = "/login"
NETXMS_RUTA_CENSO = "/objects/search"
NETXMS_RUTA_FICHAS = "/objects/details"
NETXMS_RUTA_CREAR = "/objects"


def netxms_login_cmd(api: str) -> list:
    """El login: el único que no lleva testigo. El cuerpo entra por la entrada estándar."""
    return _sh(f"curl -sS -X POST -H 'Content-Type: application/json' -d @- {api}{NETXMS_RUTA_LOGIN}")


def netxms_login_cuerpo(usuario: str, clave: str) -> str:
    """El cuerpo del login, en JSON y sin escapar a mano."""
    return json.dumps({"username": usuario, "password": clave})


def netxms_cmd(api: str, ruta: str) -> list:
    """Una llamada con testigo: el testigo en la primera línea de la entrada, y el cuerpo detrás.

    El testigo no se guarda en ningún fichero del invitado —cada llamada se lleva el
    suyo— y ni él ni el cuerpo aparecen en la línea de órdenes, donde los vería `ps`.
    """
    return _sh(
        # El testigo se lee de la entrada y se entrega a `curl` por una cabecera
        # leída de un descriptor (`-H @/dev/fd/3`): así no se expande en la línea
        # de órdenes y `ps` no lo ve. `--fail-with-body` hace fallar un 4xx/5xx en
        # vez de darlo por bueno: un alta rechazada no puede parecer correcta.
        "IFS= read -r t; exec 3<<EOF\n"
        "Authorization: Bearer $t\n"
        "EOF\n"
        "curl -sS --fail-with-body -H @/dev/fd/3 "
        f"-H 'Content-Type: application/json' -d @- {api}{ruta}"
    )


def netxms_censo_cmd(api: str) -> list:
    """El censo de equipos de la vista."""
    return netxms_cmd(api, NETXMS_RUTA_CENSO)


def netxms_censo_cuerpo() -> str:
    """Sólo los equipos: lo que el motor registra son equipos, no subredes ni mapas."""
    return json.dumps({"class": ["Node"]})


def netxms_fichas_cmd(api: str) -> list:
    """Las fichas de los equipos que ya están, de una vez."""
    return netxms_cmd(api, NETXMS_RUTA_FICHAS)


def netxms_fichas_cuerpo(ids: list) -> str:
    return json.dumps({"ids": [int(i) for i in ids or []]})


def netxms_crear_cmd(api: str) -> list:
    """Dar de alta un equipo con sus credenciales."""
    return netxms_cmd(api, NETXMS_RUTA_CREAR)


def netxms_ops(nodes: list[dict], encontrados: list | None, detalles: list | None,
               api: str, secrets: dict | None = None,
               puerto: int = NETXMS_PUERTO_SSH) -> dict:
    """Qué equipos del laboratorio faltan en la vista, y cuáles están a medias.

    `encontrados` es el censo que devuelve la búsqueda (resúmenes, sin credenciales);
    `detalles`, las fichas de los que ya están (que sí las traen, y por eso se piden).
    El resultado lleva dos listas: `ops` (lo que hay que escribir) y `pendientes` (lo
    que no se puede arreglar por el API y se dice).

    El motor sólo **crea lo que falta**: no borra un equipo que ya está para volver a
    crearlo con credenciales. Un equipo que ya está como debe no produce ninguna
    llamada —eso es lo que hace que el segundo `apply` no escriba— y uno que ya está
    con otras credenciales sale como pendiente, porque el API de esta versión sólo las
    acepta al crear el equipo.
    """
    por_ip: dict = {}
    for objeto in encontrados or []:
        direccion = (objeto.get("ipAddress") or {}).get("address")
        if direccion:
            por_ip.setdefault(str(direccion), objeto)
    leidos: dict = {}
    for detalle in detalles or []:
        if isinstance(detalle, dict) and detalle.get("id") is not None:
            leidos[int(detalle["id"])] = detalle

    ops: list[dict] = []
    pendientes: list[str] = []
    for node in nodes or []:
        direccion = node.get("mgmt_address")
        if not direccion:
            continue
        nombre = node.get("name") or node.get("role")
        usuario = _declared_user(node) or "admin"
        clave = ros_clave(node, secrets or {})
        objeto = por_ip.get(str(direccion))

        if objeto is None:
            cuerpo = {
                "class": "Node",
                "name": nombre,
                "ipAddress": str(direccion),
                "sshLogin": usuario,
                "sshPassword": clave,
                "sshPort": int(puerto),
            }
            ops.append({
                "cmd": netxms_crear_cmd(api),
                "cuerpo": json.dumps(cuerpo),
                "effect": f"registrar {nombre} ({direccion}) en la vista, como {usuario}",
            })
            continue

        actual = leidos.get(int(objeto["id"])) or {}
        if (str(actual.get("sshLogin") or "") == usuario
                and str(actual.get("sshPassword") or "") == clave
                and int(actual.get("sshPort") or 0) == int(puerto)):
            continue
        pendientes.append(
            f"{nombre} ({direccion}): ya está en la vista con otras credenciales "
            f"(usuario {actual.get('sshLogin') or 'ninguno'}), y el API de esta versión "
            "sólo las acepta al crear el equipo: cámbialas a mano en su consola"
        )
    return {"ops": ops, "pendientes": pendientes}


def netxms_ids(nodes: list[dict], encontrados: list | None) -> list:
    """Los identificadores de los equipos de este laboratorio que ya están en la vista.

    La búsqueda devuelve resúmenes sin credenciales, así que la ficha hay que pedirla:
    se pide **de una vez** por los que interesan, y no la de todo el censo — que sería
    leer lo de todos los laboratorios para escribir lo de uno.
    """
    direcciones = {str(n["mgmt_address"]) for n in nodes or [] if n.get("mgmt_address")}
    ids = []
    for objeto in encontrados or []:
        direccion = (objeto.get("ipAddress") or {}).get("address")
        if direccion and str(direccion) in direcciones and objeto.get("id") is not None:
            ids.append(int(objeto["id"]))
    return sorted(ids)