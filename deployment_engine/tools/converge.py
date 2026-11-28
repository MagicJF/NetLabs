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
from urllib.parse import urlsplit

from identity import (LabError, ROS_SECRET, SNMP_V3_AUTENTICACION, SNMP_V3_CIFRADO,
                      TYPES, lab_from_comment)

import mapa
import plano

# Las áreas de RouterOS que el motor sabe leer por REST. Son las mismas que valida
# identity.AREAS["routeros"]: una lectura de más es una dependencia de más.
# Cada lectura lleva su clave pegada: lo leído se ordena por lo que cada lectura ES, no
# por el orden en que salió. Con una lista de rutas y otra de nombres —paralelas— basta
# con que una se descuadre para que el diccionario entero se descoloque: el motor ve
# entonces un equipo vacío y le propone escribir lo que ya tiene.
ROS_READS = (
    {"clave": "identity", "ruta": "/rest/system/identity"},
    {"clave": "addresses", "ruta": "/rest/ip/address"},
    {"clave": "routes", "ruta": "/rest/ip/route"},
    {"clave": "pools", "ruta": "/rest/ip/pool"},
    {"clave": "dhcp_servers", "ruta": "/rest/ip/dhcp-server"},
    {"clave": "dhcp_networks", "ruta": "/rest/ip/dhcp-server/network"},
    {"clave": "services", "ruta": "/rest/ip/service"},
    {"clave": "users", "ruta": "/rest/user"},
    {"clave": "snmp", "ruta": "/rest/snmp"},
    {"clave": "snmp_community", "ruta": "/rest/snmp/community"},
    {"clave": "bridges", "ruta": "/rest/interface/bridge"},
    {"clave": "bridge_ports", "ruta": "/rest/interface/bridge/port"},
    # Las concesiones fijas de los nodos finales: una reserva no se puede leer del
    # invitado, vive en el servidor DHCP del router.
    {"clave": "dhcp_leases", "ruta": "/rest/ip/dhcp-server/lease"},
    # La salida a la red pública: la traducción que la hace posible y el resolutor con
    # el que los puestos resuelven de verdad.
    {"clave": "nat", "ruta": "/rest/ip/firewall/nat"},
    {"clave": "dns", "ruta": "/rest/ip/dns"},
)

PREFIX = "netlabs-"

# Las condiciones de una regla de traducción: lo que RouterOS compara para decidir si
# la regla toca un paquete. El motor sólo escribe `out-interface`, así que cualquier
# otra puesta en la regla la hace traducir menos de lo declarado.
CONDICIONES_NAT = (
    "src-address", "dst-address", "src-address-list", "dst-address-list",
    "src-port", "dst-port", "protocol", "in-interface", "in-interface-list",
    "out-interface-list", "src-mac-address", "connection-mark", "packet-mark",
    "routing-mark", "tcp-flags", "icmp-options", "connection-state", "dscp",
    "content", "layer7-protocol", "tls-host",
)

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
            secrets: dict | None = None, mgmt_cidr: str | None = None,
            observabilidad: dict | None = None) -> list[dict]:
    """Las llamadas REST que llevan el router de lo que hay a lo declarado.

    `current` es lo que devolvieron las lecturas de ROS_READS. Cada llamada lleva
    `effect`, la frase que el humano lee en el plan: si un cambio no se puede
    explicar en una frase, no se hace.

    SNMP es un área declarada (`snmp: {enabled}`); sin ella el motor no toca el
    servicio. Con qué se mira —SNMP v3, o la comunidad v2c en claro— lo declara el
    entorno (`observabilidad.snmp`, ADR 0019), no el laboratorio: sólo lectura y
    restringido a la red de gestión en ambos casos.
    """
    ops: list[dict] = []
    configure = node.get("configure") or {}
    if node.get("type") == "switch":
        ops += _switch_ops(node, current)

    # El nombre del equipo lo pone el motor desde el rol declarado: no es un área que
    # el laboratorio repita, porque una segunda verdad acaba contradiciendo a la
    # primera. El equipo se llama igual en su identidad, en su hostname y en sus cables.
    # Va antes del corte de abajo: un equipo sin áreas declaradas —un switch con
    # `configure: {}`— sigue teniendo nombre, y reconciliarlo no depende de que declare
    # nada. Lo que sí queda condicionado a su área es cada configuración de más abajo.
    actual = (current.get("identity") or {}).get("name")
    if actual != node["name"]:
        ops.append({"method": "POST", "path": "/rest/system/identity/set",
                    "body": {"name": node["name"]},
                    "effect": f"identidad del router -> {node['name']}"})

    if not configure:
        return ops

    area_snmp = configure.get("snmp")
    if area_snmp is not None:
        # La identidad con la que se mira no se resuelve aquí: `_snmp_ops` la pide sólo si el
        # área enciende el servicio. Apagar SNMP no necesita credencial —una retirada o a medias
        # no puede impedir apagarlo—, y resolverla antes dejaría el servicio encendido por un
        # secreto que no hace falta para dejarlo como el laboratorio dice.
        ops += _snmp_ops(current.get("snmp") or {}, current.get("snmp_community") or [],
                         area_snmp, observabilidad, secrets, mgmt_cidr)

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
    if "routes" in configure:
        ops += _route_ops(configure["routes"], current.get("routes") or [])
    if "nat" in configure:
        ops += _nat_ops(node, configure["nat"], current.get("nat") or [])
    if "dns" in configure:
        ops += _dns_ops(configure["dns"], current.get("dns") or {})
    if "users" in configure:
        ops += _user_ops(configure["users"], current.get("users") or [], routeros_clave)
    return ops


def observabilidad_de(bloque: dict | None, secrets: dict | None) -> dict | None:
    """La identidad con la que se mira a los equipos, resuelta (ADR 0019).

    El entorno declara la versión y **nombra** la credencial; aquí se resuelve contra
    `secrets.yml`. Devuelve `None` si el entorno no declara nada: entonces un laboratorio
    que encienda SNMP no tiene con qué mirarlo, y `_snmp_ops` lo dice en vez de
    inventarse una identidad.
    """
    snmp = (bloque or {}).get("snmp")
    if snmp is None:
        return None
    nombre = snmp["credencial_from"].removeprefix("secrets.")
    if snmp["version"] == 2:
        comunidad = secreto(secrets or {}, nombre)
        if not comunidad or len(comunidad) > 32 or any(c.isspace() for c in comunidad):
            raise LabError(
                "la comunidad SNMP de secrets.yml no vale: entre 1 y 32 caracteres, sin espacios"
            )
        return {"version": 2, "comunidad": comunidad}

    bloque_v3 = secreto_bloque(secrets or {}, nombre)
    faltan = {"usuario", "autenticacion", "clave_autenticacion", "cifrado", "clave_cifrado"} - set(bloque_v3)
    if faltan:
        raise LabError(f"a `secrets.{nombre}` le falta {', '.join(sorted(faltan))}")
    usuario = str(bloque_v3["usuario"])
    if not usuario or len(usuario) > 32 or any(c.isspace() for c in usuario):
        raise LabError(
            f"el usuario SNMP v3 de `secrets.{nombre}` no vale: entre 1 y 32 caracteres, "
            "sin espacios (en RouterOS el usuario ES el nombre de la entrada)"
        )
    autenticacion = str(bloque_v3["autenticacion"]).upper()
    cifrado = str(bloque_v3["cifrado"]).upper()
    if autenticacion not in SNMP_V3_AUTENTICACION:
        raise LabError(
            f"la autenticación SNMP v3 de `secrets.{nombre}` es {autenticacion!r}, y el "
            f"equipo admite {', '.join(SNMP_V3_AUTENTICACION)}"
        )
    if cifrado not in SNMP_V3_CIFRADO:
        raise LabError(
            f"el cifrado SNMP v3 de `secrets.{nombre}` es {cifrado!r}, y el equipo admite "
            f"{', '.join(SNMP_V3_CIFRADO)} (`AES` es AES-128)"
        )
    # SNMP v3 exige una clave de al menos ocho octetos: el equipo acepta menos, y luego la
    # mano falla en el sondeo con un «usmStats» que no dice por qué. Se corta antes.
    for campo in ("clave_autenticacion", "clave_cifrado"):
        if len(str(bloque_v3[campo])) < 8:
            raise LabError(f"`secrets.{nombre}.{campo}` tiene menos de 8 caracteres: SNMP v3 no la admite")
    return {
        "version": 3,
        "usuario": usuario,
        "autenticacion": autenticacion,
        "clave_autenticacion": str(bloque_v3["clave_autenticacion"]),
        "cifrado": cifrado,
        "clave_cifrado": str(bloque_v3["clave_cifrado"]),
    }


def _snmp_ops(ajustes: dict, comunidades: list, area: dict,
              bloque: dict | None, secrets: dict | None,
              mgmt_cidr: str | None) -> list[dict]:
    """El área `snmp` de un laboratorio: el servicio encendido, y con qué se mira.

    NetXMS no puede sacar el nombre, las interfaces ni las tablas de rutas y ARP de un
    CHR sin SNMP; con él, el router se convierte en la fuente de lo que cuelga de sus
    redes. El laboratorio decide **si** se enciende y nada más —la versión y la identidad
    las declara el entorno (`observabilidad.snmp`, ADR 0019), porque mirar no es cosa de
    un laboratorio—, y el motor deriva lo que no se declara: sólo lectura, y sólo desde la
    red de gestión.

    La identidad se resuelve **sólo** cuando el área la enciende: apagar el servicio —o
    dejarlo como está— no necesita las claves del sitio, y resolverlas antes del corte hacía
    que `snmp: {enabled: false}` fallara si `secrets.snmp_v3` faltaba o ya no valía, en vez
    de apagar SNMP.
    """
    encendido_ahora = str(ajustes.get("enabled", "")).lower() in ("true", "yes")
    if not area["enabled"]:
        if encendido_ahora:
            return [{"method": "POST", "path": "/rest/snmp/set",
                     "body": {"enabled": "no"},
                     "effect": "SNMP apagado (el laboratorio no lo declara encendido)"}]
        return []

    identidad = observabilidad_de(bloque, secrets)
    if identidad is None:
        raise LabError(
            "el laboratorio enciende SNMP y el entorno no declara `observabilidad.snmp`: "
            "no se inventa una identidad con la que mirar (ADR 0019)"
        )
    if not mgmt_cidr:
        raise LabError("falta la red de gestión para restringir el acceso SNMP")
    if identidad["version"] == 3:
        return _snmp_v3_ops(identidad, comunidades, mgmt_cidr, encendido_ahora)
    return _snmp_v2c_ops(identidad["comunidad"], comunidades, mgmt_cidr, encendido_ahora)


def _snmp_v2c_ops(comunidad: str, comunidades: list, mgmt_cidr: str,
                  encendido_ahora: bool) -> list[dict]:
    """SNMP v2c: una comunidad de lectura, acotada a la gestión, y el resto igual.

    La rama que el P0 deja atrás, y que sigue viva porque un equipo que no sepa v3 tiene
    que poder mirarse de alguna manera. Las claves se declaran en el entorno: aquí ya
    llegan resueltas.
    """
    # El encendido va al final, no al principio: mientras la comunidad siga abierta a
    # `::/0`, encender el servicio lo deja expuesto. El bucle de escritura de `ros.yml`
    # ejecuta estas llamadas en orden y para en la primera que falla —y con ella el
    # play—, así que una restricción que no se aplica deja el servicio **apagado**, que
    # es el fallo inocuo. Encender primero era exponerlo y confiar en que el PATCH
    # posterior llegara: el contrato del área exige el acceso sólo desde la red de gestión.
    ops: list[dict] = []
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
        # Una comunidad declarada que quedó apagada —una rotación, o alguien que la
        # apagó— no responde aunque sus permisos ya coincidan: se vuelve a encender.
        # La rama de las demás comunidades sí respeta una apagada a mano; la propia es
        # la que el laboratorio declara, y declararla es quererla viva.
        if str(propia.get("disabled", "")).lower() in ("true", "yes"):
            cambios["disabled"] = "no"
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
                        # Por su id interno, no por su nombre: el nombre de una comunidad
                        # es su valor secreto, y `ros.yml` imprime el `effect` antes de
                        # escribir. Un valor renombrado en el diagnóstico es un secreto
                        # en el informe (la declaración nombra el secreto, no lo escribe).
                        "effect": f"acotar la comunidad SNMP {otra['.id']} -> {mgmt_cidr} "
                                  "(v2c, sólo lectura)"})

    # Sólo ahora, con las comunidades ya acotadas: mientras la comunidad siga abierta a
    # `::/0`, encender el servicio lo deja expuesto. Va MARCADO para que `ros.yml` lo
    # ejecute en un paso propio, después de que el anterior haya terminado entero —una
    # llamada que falla dentro del mismo bucle NO impide que Ansible siga con los
    # elementos siguientes (medido: recorre todos y falla al final), así que el orden
    # dentro de la lista no bastaba—. El contrato del área exige acceso sólo desde la
    # red de gestión, y si una restricción falla el servicio queda apagado.
    if not encendido_ahora:
        ops.append({"method": "POST", "path": "/rest/snmp/set",
                    "body": {"enabled": "yes"},
                    "tras_restricciones": True,
                    "effect": "SNMP encendido, con la comunidad ya acotada a la gestión"})
    return ops


def _snmp_v3_ops(identidad: dict, comunidades: list, mgmt_cidr: str,
                 encendido_ahora: bool) -> list[dict]:
    """SNMP v3: un usuario autenticado y cifrado, y ninguna comunidad en claro.

    En RouterOS la identidad v3 **es una entrada de `/snmp/community`** con `security`
    distinto de `none` —`private` es autenticación y cifrado—, y su nombre es el usuario
    de SNMP v3. Medido contra un CHR 7.25 desplegado, no deducido: con `security=private`
    el equipo deja de responder a v2c con ese nombre, que es justo lo que el P0 busca, y
    las claves vuelven al leerlas, así que la comparación es real y un `apply` repetido no
    reescribe nada.
    """
    usuario = identidad["usuario"]
    v3 = {
        "security": "private",
        "authentication-protocol": identidad["autenticacion"],
        "authentication-password": identidad["clave_autenticacion"],
        "encryption-protocol": identidad["cifrado"],
        "encryption-password": identidad["clave_cifrado"],
    }
    ops: list[dict] = []
    propia = next((c for c in comunidades if c.get("name") == usuario), None)
    if propia is None:
        ops.append({"method": "PUT", "path": "/rest/snmp/community",
                    "body": {"name": usuario, "addresses": mgmt_cidr,
                             "read-access": "yes", "write-access": "no", **v3},
                    "effect": f"identidad SNMP v3 (authPriv), sólo lectura, desde {mgmt_cidr}"})
    else:
        cambios: dict = {}
        # La propia se vuelve a encender aunque alguien la apagara: declararla es quererla
        # viva. Las demás no: ésas las respeta esta rama y las apaga la de abajo.
        if str(propia.get("disabled", "")).lower() in ("true", "yes"):
            cambios["disabled"] = "no"
        if propia.get("addresses") != mgmt_cidr:
            cambios["addresses"] = mgmt_cidr
        if str(propia.get("read-access", "")).lower() not in ("true", "yes"):
            cambios["read-access"] = "yes"
        if str(propia.get("write-access", "")).lower() in ("true", "yes"):
            cambios["write-access"] = "no"
        for campo, valor in v3.items():
            # RouterOS devuelve las claves al leerlas (medido), así que comparar es
            # comparar de verdad: si ya coinciden, no hay llamada y el apply no cambia nada.
            if str(propia.get(campo, "")) != str(valor):
                cambios[campo] = valor
        if cambios:
            ops.append({"method": "PATCH", "path": f"/rest/snmp/community/{propia['.id']}",
                        "body": cambios,
                        "effect": f"identidad SNMP v3 -> {mgmt_cidr} (authPriv, sólo lectura)"})

    # Con v3 declarado, una comunidad v2c es exactamente el claro que el P0 retira: se
    # apaga. Medido: mientras `security=none` siguiera en pie, el equipo seguiría
    # contestando a `snmpwalk -v2c` con ese nombre, y la migración sería decorativa. Se
    # nombran por su id, nunca por su nombre: el nombre de una comunidad es su valor.
    for otra in comunidades:
        if otra.get("name") == usuario:
            continue
        if str(otra.get("disabled", "")).lower() in ("true", "yes"):
            continue
        ops.append({"method": "PATCH", "path": f"/rest/snmp/community/{otra['.id']}",
                    "body": {"disabled": "yes"},
                    "effect": f"apagar la comunidad v2c {otra['.id']} (con v3 no queda claro)"})

    # Sólo al final, y marcado para que `ros.yml` lo ejecute en un paso propio, después de
    # que las restricciones hayan terminado enteras: encender antes de acotar es abrir.
    if not encendido_ahora:
        ops.append({"method": "POST", "path": "/rest/snmp/set",
                    "body": {"enabled": "yes"},
                    "tras_restricciones": True,
                    "effect": "SNMP encendido, con la identidad v3 ya puesta"})
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


def _route_ops(declaradas: list, actuales: list) -> list[dict]:
    """Las rutas estáticas declaradas, y sólo las que son del motor.

    Una ruta de RouterOS se reconoce por su destino y su salto. Las que crea el
    motor llevan el prefijo en el comentario: es lo que separa lo suyo de una ruta
    puesta a mano, que se respeta aunque caiga en una red del laboratorio. Dentro
    de lo marcado, lo que sobra se retira, igual que en las demás áreas.

    Un destino ya ocupado por una ruta ajena con un salto que el laboratorio no declara
    no se pisa: se dice, porque el motor no puede cumplir lo declarado sin tocar lo que
    no es suyo. Una ruta ajena apagada no cuenta: no lleva tráfico, así que ni hace de
    declarada ni impide poner la del laboratorio. Una ajena encendida sí cuenta aunque
    la del motor ya esté puesta: compite con ella por la distancia, y darla por buena
    escondería que el tráfico puede salir por donde el laboratorio no declara.
    """
    def clave(ruta: dict) -> tuple[str, str]:
        # El salto puede venir con la pata pegada (`10.99.0.2%ether1`): la
        # dirección es lo que identifica la ruta, no cómo se alcanza la pata.
        return (str(ipaddress.ip_network(ruta.get("dst-address", ""), strict=False)),
                str(ruta.get("gateway", "")).split("%")[0])

    es_dinamica = lambda r: str(r.get("dynamic", "false")).lower() in ("true", "yes")
    # El área administra la tabla `main`: una ruta de otra tabla (`backup`, o la que
    # declare una regla de enrutado) no la consulta este tráfico, así que no satisface
    # una declarada, no compite con ella y no se retira. Se queda fuera del área entera.
    es_main = lambda r: str(r.get("routing-table") or "main") == "main"
    estaticas = [r for r in actuales or [] if not es_dinamica(r) and es_main(r)]
    propias = [r for r in estaticas
               if str(r.get("comment", "")).startswith(PREFIX)]

    def apagada(ruta: dict) -> bool:
        return str(ruta.get("disabled", "false")).lower() in ("true", "yes")

    # Una ruta ajena apagada no lleva tráfico: no puede hacer de la declarada —el motor
    # se apoyaría en un camino cortado— ni ocupar el destino para impedir la suya. Sólo
    # cuenta la ajena que de verdad está en uso.
    ajenas = {clave(r) for r in estaticas
              if not str(r.get("comment", "")).startswith(PREFIX) and not apagada(r)}

    deseadas = []
    for item in declaradas or []:
        red = str(ipaddress.ip_network(item["destination"], strict=False))
        via = str(ipaddress.ip_interface(item["gateway"]).ip)
        deseadas.append((red, via))

    ops: list[dict] = []
    # Los saltos que el laboratorio declara para cada destino. Una ruta ajena por uno de
    # ellos no ofrece un camino que la declaración no pida ya —el motor tiene la suya por
    # ese salto—, así que no es un conflicto. Dos rutas al mismo destino con saltos
    # distintos son dos rutas declaradas, y comparar la ajena sólo con el salto que se está
    # declarando tomaba la del otro salto por un intruso y paraba el `apply` con el
    # laboratorio correcto.
    saltos_declarados: dict[str, set[str]] = {}
    for red, via in deseadas:
        saltos_declarados.setdefault(red, set()).add(via)

    # Cada entrada declarada se lleva UNA entrada propia, y ninguna se comparte: dos
    # rutas al mismo destino con saltos distintos son dos rutas, y si las dos reclamaran
    # la misma entrada cada pasada le cambiaría el salto a la otra y no convergería.
    sin_reclamar = list(propias)
    # Se reservan PRIMERO las coincidencias exactas de todas las declaradas, antes de
    # corregir ninguna. Con dos saltos declarados (A, B) y sólo la entrada propia por B,
    # corregir en el orden declarado tomaba la de B para A y luego volvía a crear B: un
    # PATCH y un PUT donde basta un PUT, y si el PUT falla el equipo pierde el salto que
    # ya tenía. Reservando, cada declarada encuentra la suya o se crea.
    exactas: list = [None] * len(deseadas)
    for i, (red, via) in enumerate(deseadas):
        # Una ruta ajena ENCENDIDA al mismo destino y por un salto que el laboratorio no
        # declara compite con la declarada —RouterOS se queda con la de menos distancia y,
        # a distancias iguales, reparte el tráfico— y el motor no puede retirarla: se dice.
        # Se mira ANTES de dar la declarada por puesta, porque una propia ya en su sitio
        # también deja el camino a merced de la de fuera; mirarlo después escondía justo
        # ese caso.
        if any(destino == red and salto not in saltos_declarados[red]
               for destino, salto in ajenas):
            raise LabError(
                f"ya hay una ruta a {red} que no es del motor: el motor no la toca y no "
                "puede poner la que declara el laboratorio. Se retira a mano o se cambia "
                "el destino declarado"
            )
        igual = next((r for r in sin_reclamar if clave(r) == (red, via)), None)
        if igual is not None:
            sin_reclamar.remove(igual)
            exactas[i] = igual

    for i, (red, via) in enumerate(deseadas):
        igual = exactas[i]
        if igual is not None:
            # Una ruta propia apagada no lleva tráfico: declararla es quererla en uso, y
            # una que alguien apagó a mano no puede quedarse así para siempre mientras el
            # laboratorio siga declarándola —las sedes se quedarían sin comunicación y
            # nada lo diría—.
            if apagada(igual):
                ops.append({"method": "PATCH", "path": f"/rest/ip/route/{igual['.id']}",
                            "body": {"disabled": "no"},
                            "effect": f"encender la ruta {red} -> {via}"})
            continue
        if (red, via) in ajenas:
            continue
        # Mismo destino, otro salto: el salto viejo es justo lo que hay que corregir —es
        # un router que ya no está—, y `PUT` respondería que la ruta ya existe.
        otra = next((r for r in sin_reclamar if clave(r)[0] == red), None)
        if otra is not None:
            sin_reclamar.remove(otra)
            cuerpo = {"gateway": via}
            if apagada(otra):
                cuerpo["disabled"] = "no"
            ops.append({"method": "PATCH", "path": f"/rest/ip/route/{otra['.id']}",
                        "body": cuerpo,
                        "effect": f"ruta {red} -> {via} (antes {otra.get('gateway')})"})
            continue
        ops.append({"method": "PUT", "path": "/rest/ip/route",
                    "body": {"dst-address": red, "gateway": via,
                             "comment": f"{PREFIX}ruta"},
                    "effect": f"ruta {red} -> {via}"})

    # Lo propio que ninguna entrada declarada reclamó sobra. No hay excepción por
    # compartir destino: lo declarado ya tiene su entrada, así que ésta es un resto.
    for ruta in sin_reclamar:
        red, via = clave(ruta)
        ops.append({"method": "DELETE", "path": f"/rest/ip/route/{ruta['.id']}",
                    "effect": f"sobra la ruta {red} -> {via}"})
    return ops


def _sin_condiciones_extra(regla: dict) -> bool:
    """Verdadero si la regla no lleva ninguna condición más que su pata de salida.

    Las condiciones son lo que RouterOS compara para decidir si la regla toca un
    paquete. El motor sólo escribe `out-interface`, así que cualquier otra puesta en la
    regla —un `src-address`, un `protocol`— la hace traducir menos de lo declarado: no
    es la del laboratorio aunque coincida en interfaz, acción y cadena, y se reemplaza
    en vez de darla por buena.
    """
    return not any(str(regla.get(campo) or "") for campo in CONDICIONES_NAT)


def _nat_ops(node: dict, declaradas: list, actuales: list) -> list[dict]:
    """La traducción de la salida: lo que sale por la pata pública.

    Un laboratorio con salida real tiene direcciones privadas dentro y el mundo fuera,
    y sin traducir no vuelve nada. El laboratorio declara por dónde sale (`out`, el
    nombre de una red suya, que se traduce a la pata que la lleva) y qué hace
    (`action`, por defecto `masquerade`).

    Sólo se escribe en la cadena `srcnat`, y sólo se reconoce como propio lo que lleva
    el comentario del motor, igual que en las rutas: una regla puesta a mano no se
    toca ni se pisa.
    """
    ops = []
    nuestras = [r for r in actuales if str(r.get("comment", "")).startswith(PREFIX)]
    sin_reclamar = list(nuestras)
    for item in declaradas:
        iface = interface_of(node, item["out"])
        if iface is None:
            raise LabError(
                f"la salida {item['out']!r} de {node['name']} no es una red suya: "
                "no hay pata por la que traducir"
            )
        accion = item.get("action", "masquerade")
        igual = next((r for r in sin_reclamar
                      if r.get("out-interface") == iface and r.get("action") == accion
                      and r.get("chain") == "srcnat" and _sin_condiciones_extra(r)), None)
        if igual is not None:
            sin_reclamar.remove(igual)
            # Una regla propia apagada con `disabled: true` no traduce: coincidir en
            # interfaz, acción y cadena no basta. Se vuelve a encender, igual que se
            # hace con una ruta propia que alguien apagó a mano.
            if str(igual.get("disabled", "false")).lower() in ("true", "yes"):
                ops.append({"method": "PATCH",
                            "path": f"/rest/ip/firewall/nat/{igual['.id']}",
                            "body": {"disabled": "no"},
                            "effect": f"encender la traducción por {iface} ({accion})"})
            continue
        ops.append({"method": "PUT", "path": "/rest/ip/firewall/nat",
                    "body": {"chain": "srcnat", "action": accion,
                             "out-interface": iface, "comment": f"{PREFIX}salida"},
                    "effect": f"traducir la salida por {iface} ({accion})"})

    for regla in sin_reclamar:
        ops.append({"method": "DELETE", "path": f"/rest/ip/firewall/nat/{regla['.id']}",
                    "effect": f"sobra la traducción por {regla.get('out-interface')}"})
    return ops


def _dns_ops(declarado: dict, actual: dict) -> list[dict]:
    """El resolutor del router: a quién pregunta y si atiende a los suyos.

    RouterOS no tiene un objeto por servidor: `/ip/dns` es un ajuste único, con la
    lista en una sola cadena separada por comas. Un router con salida real resuelve
    por la puerta de esa salida, y `allow_remote_requests` es lo que hace que los
    puestos que lo tienen de servidor —los que sirve su DHCP— resuelvan también.
    """
    ops = []
    servidores = declarado.get("servers")
    if servidores is not None:
        deseado = (",".join(servidores) if isinstance(servidores, (list, tuple))
                   else str(servidores))
        ahora = str(actual.get("servers") or "").replace(" ", "")
        if ahora != deseado:
            ops.append({"method": "POST", "path": "/rest/ip/dns/set",
                        "body": {"servers": deseado},
                        "effect": f"resolver -> {deseado}"})
    atiende = declarado.get("allow_remote_requests")
    if atiende is not None:
        ahora = str(actual.get("allow-remote-requests", "")).lower() in ("true", "yes")
        if ahora != bool(atiende):
            ops.append({"method": "POST", "path": "/rest/ip/dns/set",
                        "body": {"allow-remote-requests": "yes" if atiende else "no"},
                        "effect": f"el resolutor {'atiende' if atiende else 'no atiende'} a la red"})
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
    concesiones = {str(l.get("comment") or ""): l for l in current.get("dhcp_leases") or []}
    deseados_pool, deseados_srv, deseados_red, deseados_reserva = set(), set(), set(), set()

    for item in declarados:
        iface = interface_of(node, item["network"])
        nombre = f"{PREFIX}{item['network']}"
        red = item.get("network")
        gateway = _gateway_served(node, red, item)
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

        for reserva in item.get("leases") or []:
            comentario = f"{PREFIX}reserva-{reserva['role']}"
            deseados_reserva.add(comentario)
            cuerpo = {
                "address": str(reserva["address"]),
                "mac-address": str(reserva["mac"]),
                "server": nombre,
                "comment": comentario,
                "disabled": "no",
            }
            actual = concesiones.get(comentario)
            if actual is None:
                ops.append({"method": "PUT", "path": "/rest/ip/dhcp-server/lease",
                            "body": cuerpo,
                            "effect": f"reserva {reserva['address']} para {reserva['role']} "
                                      f"({reserva['mac']}) en {nombre}"})
            else:
                cambios = {}
                if str(actual.get("address")) != cuerpo["address"]:
                    cambios["address"] = cuerpo["address"]
                if str(actual.get("mac-address") or "").lower() != cuerpo["mac-address"].lower():
                    cambios["mac-address"] = cuerpo["mac-address"]
                if actual.get("server") != nombre:
                    cambios["server"] = nombre
                if str(actual.get("disabled", "false")).lower() in ("true", "yes"):
                    cambios["disabled"] = "no"
                if cambios:
                    ops.append({"method": "PATCH", "path": f"/rest/ip/dhcp-server/lease/{actual['.id']}",
                                "body": cambios,
                                "effect": f"reserva {reserva['address']} para {reserva['role']} "
                                          f"({reserva['mac']}) en {nombre}"})

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
    for comentario, concesion in concesiones.items():
        if comentario.startswith(f"{PREFIX}reserva-") and comentario not in deseados_reserva:
            ops.append({"method": "DELETE", "path": f"/rest/ip/dhcp-server/lease/{concesion['.id']}",
                        "effect": f"sobra la reserva {concesion.get('address')} "
                                  f"({concesion.get('comment')})"})
    return ops


def _gateway_served(node: dict, network: str, item: dict) -> str:
    """La puerta que el servidor anuncia: la suya o la del router en esa red.

    Si el servidor no repite la puerta, la primera del rango no sirve cuando el
    router vive en otra dirección: el cliente saldría por una dirección que no
    enruta. Se usa la que el router declara en esa red, la misma que el plan
    deriva para las patas estáticas; sólo si tampoco la declara se cae a la
    primera del rango.
    """
    if item.get("gateway"):
        return item["gateway"]
    for pata in (node.get("configure") or {}).get("addresses") or []:
        if pata.get("network") == network:
            return str(ipaddress.ip_interface(pata["address"]).ip)
    return _first_host(node, network)


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


def secreto_bloque(secrets: dict, nombre: str) -> dict:
    """Un secreto del sitio que es un mapa —una credencial con varios campos—, por su nombre.

    Es a la identidad v3 lo que `secreto` es a la comunidad v2c: la identidad de SNMP v3
    no cabe en una cadena —usuario, protocolo de autenticación, protocolo de cifrado y sus
    dos claves—, así que vive en un mapa y aquí se comprueba que lo sea antes de leer campo
    a campo. Ausente o de otro tipo es un fallo del sitio y se dice.
    """
    valor = (secrets or {}).get(nombre)
    if not isinstance(valor, dict):
        raise LabError(
            f"secrets.yml no tiene {nombre!r} o no es un mapa: la credencial se nombra, "
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

# Dónde deja el motor las marcas que no caben en el fichero declarado: que un
# repositorio ya actualizó su índice y que una unidad ya releyó su configuración.
# Fuera de las rutas que el laboratorio declara, para no pisar lo suyo.
MARCA_DIR = "/var/lib/netlabs"

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
for r in {repos}; do
  f="/etc/apt/sources.list.d/$r.list"
  if [ -f "$f" ]; then
    echo "REPO:$r:$(base64 -w0 < "$f")"
  else
    echo "REPO:$r:-"
  fi
  m="{reload_dir}/apt/$r.ok"
  if [ -f "$m" ]; then echo "REPO_OK:$r:$(cat "$m")"; else echo "REPO_OK:$r:-"; fi
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
for f in {reloads}; do
  m="{reload_dir}/reload/$(printf '%s' "$f" | sha256sum | cut -d' ' -f1).ok"
  if [ -f "$m" ]; then echo "RELOAD:$f:$(cat "$m")"; else echo "RELOAD:$f:-"; fi
done
true
"""


def _marca_repo(nombre: str) -> str:
    """Dónde queda registrado que un repositorio declarado ya actualizó su índice.

    Escribir el `.list` y actualizar el índice son dos hechos distintos, y sólo el
    segundo hace que un paquete nuevo sea instalable. La marca guarda la huella de
    la línea declarada: si cambia el repositorio, la marca vieja no vale y se
    vuelve a actualizar.
    """
    return f"{MARCA_DIR}/apt/{nombre}.ok"


def _marca_recarga(ruta: str) -> str:
    """Dónde queda registrado que una unidad ya releyó la configuración de un fichero.

    La ruta se resume a su huella porque puede llevar `/`; la marca no necesita ser
    legible, sólo distinguir un fichero de otro.
    """
    return f"{MARCA_DIR}/reload/{hashlib.sha256(ruta.encode('utf-8')).hexdigest()}.ok"


def linux_probe(node: dict) -> str:
    """El sondeo que se ejecuta por SSH para leer el interior de un Linux.

    Pregunta sólo por lo declarado: los paquetes que el nodo pide, los servicios
    que toca y las fuentes APT que declara. Un paquete que no se declara no se
    consulta, y una fuente que el laboratorio no declara tampoco: leer las demás
    sería sacar del huésped lo que no es del motor —una fuente con credenciales en
    la URL viaja en base64, que no la esconde—, y además `HOST:` ya lee el nombre
    del huésped, que sí hace falta para su identidad.

    Todo lo que se interpola va entrecomillado con `shlex.quote`: una ruta con
    espacios, sin comillas, se parte en dos palabras y el sondeo no la encuentra —
    el estado no tendría su clave, y cada apply volvería a escribir el fichero, a
    ejecutar el comando y a aplicar la credencial, porque nada de eso coincidiría.
    """
    configure = node.get("configure") or {}
    paquetes = " ".join(configure.get("packages") or [])
    servicios = " ".join(sorted((configure.get("services") or {}).keys()))
    ficheros = " ".join(shlex.quote(f["path"]) for f in configure.get("files") or [])
    comandos = " ".join(shlex.quote(c["creates"])
                        for c in configure.get("commands") or [] if "creates" in c)
    # Una marca de credencial guarda la huella de la clave, nunca la clave: así el
    # sondeo puede comparar sin que el secreto salga del fichero de secretos.
    marcas = " ".join(shlex.quote(c["stamp"])
                      for c in configure.get("commands") or [] if "stamp" in c)
    repos = " ".join(shlex.quote(r["name"]) for r in configure.get("repositories") or [])
    recargas = " ".join(shlex.quote(f["path"])
                        for f in configure.get("files") or [] if f.get("restart"))
    return LINUX_STATE_SCRIPT.format(
        packages=paquetes, services=servicios, files=ficheros, commands=comandos,
        stamps=marcas, repos=repos, reloads=recargas, reload_dir=MARCA_DIR,
    )


def linux_state(text: str) -> dict:
    """El estado de un interior Linux, leído de la salida del sondeo.

    El sondeo es un script `sh` que el motor ejecuta por SSH y que imprime una
    línea por hecho: `HOST:`, `PKG:`, `SVC:`, `REPO:`, `REPO_OK:`, `RELOAD:` y las
    demás. Se parsea aquí, en Python puro, para que la comparación se pruebe sin
    hipervisor.
    """
    import base64

    state = {"hostname": "", "packages": {}, "services": {}, "enabled": {},
             "repositories": {}, "repos_ok": {}, "files": {}, "modes": {},
             "commands": {}, "stamps": {}, "reloads": {}}
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
        elif linea.startswith("REPO_OK:"):
            _, nombre, valor = linea.split(":", 2)
            state["repos_ok"][nombre] = valor.strip()
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
        elif linea.startswith("RELOAD:"):
            resto = linea[7:]
            ruta, _, huella = resto.rpartition(":")
            state["reloads"][ruta] = huella.strip()
    return state


def _repo_line(repo: dict) -> str:
    """La línea de `sources.list.d` que representa un repositorio declarado."""
    signed = f" [signed-by=/etc/apt/keyrings/{repo['name']}.gpg]" if repo.get("key") else ""
    return f"deb{signed} {repo['url']} {repo['suite']} {repo['components']}"


def _repo_script(repo: dict) -> str:
    """El script que deja el repositorio puesto *y* su índice actualizado.

    Las dos cosas son inseparables en un solo script, pero se comprueban por
    separado: la marca de índice completado se escribe al final y sólo si todo lo
    anterior salió bien (`set -e`), así que el sondeo puede distinguir un `.list`
    bien escrito de un `apt-get update` terminado. Sin esa distinción, un `update`
    que falló tras escribir el `.list` quedaba invisible para siempre —el fichero
    ya coincidía— y un paquete que sólo está en el índice nuevo no se instalaba
    nunca, sin que nada lo dijera.
    """
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
    marca = _marca_repo(repo["name"])
    lineas.append(f"install -d {shlex.quote(os.path.dirname(marca))}")
    lineas.append(
        f"printf '%s' {shlex.quote(_sha256(_repo_line(repo)))} > {shlex.quote(marca)}"
    )
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


def linux_access_cmd(clave_publica: str, contrasena: str) -> list:
    """El script que deja abierta la puerta de root de un invitado Linux.

    El invitado nace con la clave pública del motor ya autorizada —se la pasa
    `create_guest` al crearlo—, pero esa clave sirve para que el motor entre, no
    para que entre una persona desde la consola de la vista. Para eso hace falta
    una clave de root y un sshd que acepte contraseña; las dos cosas se escriben
    aquí, una sola vez.

    La contraseña no viaja en el comando: entra por la entrada estándar y se lee
    sólo cuando la huella del marcador no coincide. El marcador guarda la huella,
    nunca la contraseña, y es lo que hace que el segundo `apply` no escriba ni
    reinicie el servicio. El script imprime `CAMBIO:1` si tocó algo, para que la
    tarea pueda distinguir «ya estaba» de «lo he abierto».
    """
    if not contrasena:
        raise LabError(
            "no hay contraseña para los invitados Linux: declara `linux_clave` en secrets.yml"
        )
    huella = hashlib.sha256(contrasena.encode("utf-8")).hexdigest()
    config = "PermitRootLogin yes\nPasswordAuthentication yes"
    script = f"""set -eu
cambio=0
install -d -m 700 /root/.ssh
clave={shlex.quote(clave_publica)}
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
if [ -n "$clave" ] && ! grep -qxF "$clave" /root/.ssh/authorized_keys; then
  printf '%s\\n' "$clave" >> /root/.ssh/authorized_keys
  cambio=1
fi
if [ "$(cat /etc/netlabs-ssh 2>/dev/null || true)" != {shlex.quote(huella)} ]; then
  IFS= read -r clave_root || true
  if [ -n "$clave_root" ]; then
    printf 'root:%s\\n' "$clave_root" | chpasswd
    printf '%s\\n' {shlex.quote(huella)} > /etc/netlabs-ssh
    chmod 600 /etc/netlabs-ssh
    cambio=1
  fi
fi
config={shlex.quote(config)}
if [ "$(cat /etc/ssh/sshd_config.d/90-netlabs.conf 2>/dev/null || true)" != "$config" ]; then
  printf '%s' "$config" > /etc/ssh/sshd_config.d/90-netlabs.conf
  chmod 644 /etc/ssh/sshd_config.d/90-netlabs.conf
  cambio=1
fi
if [ "$cambio" = 1 ]; then
  systemctl restart ssh 2>/dev/null || service ssh restart
fi
echo "CAMBIO:$cambio"
"""
    return _sh(script)


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
        puesto = (repos_ahora.get(repo["name"]) or "").strip() == esperado.strip()
        # El fichero bien escrito no basta: sin el índice actualizado, un paquete que
        # sólo vive en este repositorio no existe para `apt-get install`. Se reintenta
        # mientras el `.list` no coincida **o** la marca de índice completado no esté,
        # y el script entero se vuelve a ejecutar (es idempotente) porque un `update`
        # que falló dejó el `.list` ya correcto.
        actualizado = (current.get("repos_ok") or {}).get(repo["name"]) == _sha256(_repo_line(repo))
        if puesto and actualizado:
            continue
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
        coincide = ((current.get("files") or {}).get(fichero["path"]) == esperado
                    and _modo_igual(fichero, current))
        if not coincide:
            ops.append({
                "cmd": _sh(_file_script(fichero)),
                "effect": f"fichero {fichero['path']}",
            })
        if not fichero.get("restart"):
            continue
        # Un fichero que **es** la configuración de un servicio no se nota hasta que el
        # servicio lo vuelve a leer, y haberlo escrito no es que se haya releído: si la
        # conexión se cortó antes de `try-restart`, el fichero ya coincide en la pasada
        # siguiente y la unidad se queda con la configuración vieja para siempre. La
        # recarga completada se registra en su propia marca y se reintenta hasta que
        # esté —y la segunda pasada, entonces, no escribe nada—.
        # `try-restart` y no `restart`: en el primer apply el servicio puede no estar en
        # pie todavía (su base de datos se inicializa más abajo, en los comandos), y
        # `try-restart` sobre algo que no corre no arranca nada —los servicios se
        # convergen al final— mientras que sobre lo que corre sí relee. Medido: sale 0 si
        # la unidad existe y 5 si no existe, así que una errata en el nombre se dice en
        # vez de pasar por buena.
        if coincide and (current.get("reloads") or {}).get(fichero["path"]) == esperado:
            continue
        marca = _marca_recarga(fichero["path"])
        recarga = (f"systemctl try-restart {shlex.quote(fichero['restart'])} && "
                   f"install -d {shlex.quote(os.path.dirname(marca))} && "
                   f"printf '%s' {shlex.quote(esperado)} > {shlex.quote(marca)}")
        ops.append({
            "cmd": _sh(recarga),
            "effect": (f"releer la configuración de {fichero['restart']}: cambió "
                       f"{fichero['path']}" if not coincide
                       else f"releer la configuración de {fichero['restart']} "
                            "(quedó pendiente de la pasada anterior)"),
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


def _salto(entrada: dict) -> str:
    """El salto de una entrada tal y como lo nombra `ip route del`.

    El mismo salto con otra métrica son dos entradas distintas de la tabla, así que hay
    que decir cuál se retira: `ip route del <prefijo>` a secas se lleva la primera que
    encaje, que puede no ser la que se quiere quitar. La métrica por defecto no se
    nombra —viene sin ella—, y nombrarla apuntaría a otra entrada.
    """
    salto = f"via {entrada['gateway']}"
    if entrada.get("metric") not in (None, 0):
        salto += f" metric {entrada['metric']}"
    return salto


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
        # Una lista, no un valor: dos rutas al mismo prefijo con métricas distintas son
        # dos entradas de la tabla, y quedarse con una dejaba la otra sin retirar —el
        # `del` se emitía una sola vez y la sobrante se quedaba dentro del espacio para
        # siempre—. La métrica es lo que las distingue, así que se conserva.
        ahora.setdefault(red, []).append({"gateway": ruta.get("gateway"),
                                          "metric": ruta.get("metric")})

    declaradas = {}
    for deseada in deseadas or []:
        red = ipaddress.ip_network(deseada["space"], strict=False)
        declaradas[red] = deseada
        entradas = ahora.get(red, [])
        mia = any(entrada["gateway"] == deseada["via"] for entrada in entradas)
        # Sólo un salto compite con el nuestro: una ruta conectada —sin salto— no es un
        # salto que retirar, y quitarla se llevaría por delante una interfaz.
        ajenas = [e for e in entradas if e["gateway"] and e["gateway"] != deseada["via"]]
        if mia and not ajenas:
            continue
        # Que la nuestra esté puesta no basta: con otra entrada del mismo prefijo el
        # tráfico no sale necesariamente por ella —`ip route` se queda con la de menos
        # métrica y, a métricas iguales, reparte el tráfico entre las dos—. El salto que
        # sobra es lo que se retira, y retirarlo es lo que deja a la declarada mandando
        # de verdad. Se retira antes de poner la nuestra: si no, la tabla se queda con
        # las dos y el problema vuelve a esconderse.
        for entrada in ajenas:
            ops.append({
                "cmd": _sh(f"ip route del {red} {_salto(entrada)}"),
                "effect": (f"retirar el salto {entrada['gateway']} de {red}: el "
                           f"laboratorio declara {deseada['via']}"),
            })
        if not mia:
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
        # Una retirada por entrada: `ip route del <prefijo>` quita una de las que
        # encajan en el prefijo, así que hacen falta tantas órdenes como entradas haya.
        for _entrada in ahora[red]:
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
# El tope de tiempo de cada llamada al API: sin él, un servicio que escucha pero no
# contesta deja el `curl` colgado y el `apply` con él. Un fallo se dice en vez de
# esperar a ciegas.
NETXMS_TOPE = "--connect-timeout 10 --max-time 60"
# Las rutas del API que el motor usa, en un solo sitio: son la parte del motor que
# sabe cómo se llama esto por dentro. Cambiar de versión del servicio se toca aquí.
NETXMS_RUTA_LOGIN = "/login"
NETXMS_RUTA_CENSO = "/objects/search"
NETXMS_RUTA_FICHAS = "/objects/details"
NETXMS_RUTA_CREAR = "/objects"

# El grupo SNMP de un equipo: `GET`/`PATCH /objects/{id}/snmp`, una ruta por equipo —el
# API no tiene ninguna que escriba el grupo de varios de una vez—. Es el único sitio por
# el que se le dice a la vista **con qué identidad** sondea un equipo: las credenciales
# SSH de la ficha común sólo se aceptan al crear, pero las de SNMP sí se corrigen después
# (medido: `PATCH` 200 y el grupo cambia).
NETXMS_RUTA_SNMP = "/objects/{}/snmp"

# Cómo se llama el cifrado en cada sistema. El entorno declara la identidad en el idioma
# de RouterOS —donde `AES` es AES-128— y la vista la escribe a la suya: medido contra la
# instalación (`libnxsnmp`, `s_snmpPrivMethodNames`), admite `NONE|DES|AES-128|AES-192|
# AES-256`, así que `AES` a secas le contesta 400 y hay que traducirlo aquí. Los métodos
# de autenticación se llaman igual en los dos (MD5, SHA1, SHA256, SHA512), y la vista
# admite además SHA224 y SHA384, que RouterOS no sabe.
NETXMS_CIFRADO_DESDE_ROUTEROS = {"DES": "DES", "AES": "AES-128"}


def netxms_login_cmd(api: str) -> list:
    """El login: el único que no lleva testigo. El cuerpo entra por la entrada estándar.

    Con tope de tiempo: sin él, un servicio que escucha pero no contesta deja el
    `curl` colgado para siempre y el `apply` con él. Un fallo se dice en vez de
    esperar a ciegas.
    """
    return _sh(f"curl -sS {NETXMS_TOPE} -X POST -H 'Content-Type: application/json' "
               f"-d @- {api}{NETXMS_RUTA_LOGIN}")


def netxms_login_cuerpo(usuario: str, clave: str) -> str:
    """El cuerpo del login, en JSON y sin escapar a mano."""
    return json.dumps({"username": usuario, "password": clave})


def netxms_cmd(api: str, ruta: str, metodo: str = "POST") -> list:
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
        f"curl -sS {NETXMS_TOPE} --fail-with-body -X {metodo} -H @/dev/fd/3 "
        f"-H 'Content-Type: application/json' -d @- {api}{ruta}"
    )


def netxms_objeto_cmd(api: str, id_objeto) -> list:
    """Leer un objeto entero —el mapa y sus banderas— sin cuerpo: sólo el testigo.

    El testigo entra igual que en las demás llamadas: por la entrada y al descriptor 3,
    para que no se vea en la línea de órdenes.
    """
    return _sh(
        "IFS= read -r t; exec 3<<EOF\n"
        "Authorization: Bearer $t\n"
        "EOF\n"
        f"curl -sS {NETXMS_TOPE} --fail-with-body -X GET -H @/dev/fd/3 "
        f"{api}/objects/{int(id_objeto)}"
    )


def netxms_borrar_cmd(api: str, id_objeto) -> list:
    """Retirar de la vista un equipo que apunta a una máquina que ya no es la suya.

    El API de esta versión **no deja corregir** la dirección de un equipo: ni `PUT` ni
    `PATCH` la cambian (medido: contestan 200 y la ficha sigue igual). Lo único que
    funciona es retirarlo y volver a darlo de alta con la dirección buena.
    """
    return netxms_cmd(api, f"/objects/{int(id_objeto)}", metodo="DELETE")


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


def netxms_interfaces_cmd(api: str) -> list:
    """Las interfaces que la vista conoce, todas de una vez.

    La vista las cuelga de su equipo —son sus hijos—, pero el censo no dice de quién es
    cada una: por eso se leen aparte, y se cruzan con la ficha de cada equipo, que sí trae
    la lista de sus hijos. Son dos lecturas que ya se hacen, no una nueva.
    """
    return netxms_cmd(api, NETXMS_RUTA_CENSO)


def netxms_interfaces_cuerpo() -> str:
    """Sólo las interfaces: los cables del mapa se atan a ellas."""
    return json.dumps({"class": [NETXMS_CLASE_INTERFAZ]})


def netxms_crear_cmd(api: str) -> list:
    """Dar de alta un equipo con sus credenciales."""
    return netxms_cmd(api, NETXMS_RUTA_CREAR)


def netxms_snmp_cmd(api: str, id_objeto) -> list:
    """Escribir con qué identidad sondea la vista a un equipo (su grupo SNMP)."""
    return netxms_cmd(api, NETXMS_RUTA_SNMP.format(int(id_objeto)), metodo="PATCH")


def netxms_imagen_cmd(api: str, id_objeto) -> list:
    """Decirle a la vista con qué imagen dibuja a un equipo (su `mapImage`).

    Es un `PATCH` del propio objeto: la imagen no viaja en el mapa —el mapa sólo pide el
    icono de cada objeto— sino que se guarda en el objeto, y de ahí la lee la vista (ver
    `netxms_icono_de`). El API de esta versión acepta el `mapImage` en un `PATCH` del
    objeto, igual que el grupo SNMP de al lado.
    """
    return netxms_cmd(api, f"/objects/{int(id_objeto)}", metodo="PATCH")



# La configuración del propio servicio de la vista: `GET`/`PUT /server-config/{nombre}`. No es
# un objeto del inventario sino una variable del servicio, y el API las trata como al resto: una
# lectura y una escritura por nombre. Medido en la instalación: la lectura devuelve, además del
# valor, si el cambio exige reiniciar el servicio (`needServerRestart`), así que el motor no
# adivina cuándo hay que reiniciar — se lo pregunta a quien lo sabe.
NETXMS_RUTA_CONFIGS = "/server-config"
NETXMS_RUTA_CONFIG = "/server-config/{}"

# Cómo se llama en el servicio lo que enciende la escucha de registros y dónde escucha. Los
# nombres son suyos, no del motor: cambiarlos es cambiar de versión de la vista.
NETXMS_REGISTRO_ESCUCHA = "Syslog.EnableListener"
NETXMS_REGISTRO_PUERTO = "Syslog.ListenPort"
# El puerto en el que la vista escucha por defecto: el que trae el servicio sin que nadie lo cambie.
NETXMS_REGISTRO_PUERTO_POR_DEFECTO = 514


def netxms_configs_cmd(api: str) -> list:
    """Todas las variables de configuración visibles del servicio, de una vez.

    Una sola lectura en vez de una por variable: el servicio las devuelve juntas y el motor
    decide con esa foto si hay algo que escribir. Sin cuerpo —es una lectura—, y con el
    testigo por el descriptor de siempre para que no se vea en la línea de órdenes.
    """
    return _sh(
        "IFS= read -r t; exec 3<<EOF\n"
        "Authorization: Bearer $t\n"
        "EOF\n"
        f"curl -sS {NETXMS_TOPE} --fail-with-body -X GET -H @/dev/fd/3 "
        f"{api}{NETXMS_RUTA_CONFIGS}"
    )


def netxms_config_cmd(api: str, nombre: str) -> list:
    """Escribir una variable de configuración del servicio; el valor va en el cuerpo."""
    return netxms_cmd(api, NETXMS_RUTA_CONFIG.format(nombre), metodo="PUT")


def netxms_registro_puerto(declarado: dict | None, actuales: list | None) -> int:
    """El puerto en el que la vista escucha los registros: el declarado, o el que ya tiene.

    El plan sólo escribe el puerto si el entorno lo declara, así que cuando no lo declara el
    efectivo es el que la vista tenga guardado —y su defecto si no aparece—. Medir el de fábrica
    cuando no hay ninguno declarado daría por apagada una escucha que sí está, y el motor
    reiniciaría la vista en cada pasada sin corregir nunca la diferencia.
    """
    puerto = (declarado or {}).get("puerto")
    if puerto is not None:
        return int(puerto)
    for variable in actuales or []:
        if isinstance(variable, dict) and variable.get("name") == NETXMS_REGISTRO_PUERTO:
            try:
                return int(variable.get("value"))
            except (TypeError, ValueError):
                break
    return NETXMS_REGISTRO_PUERTO_POR_DEFECTO


def netxms_registro_ops(declarado: dict | None, actuales: list | None, api: str,
                        escuchando: bool | None = None) -> dict:
    """Lo que hay que escribir para que la vista recoja los registros como el entorno declara.

    `actuales` es lo que devolvió `GET /server-config` —la lista entera, que es una lectura y no
    una por variable—. `escuchando` es si hay algo escuchando de verdad el puerto declarado, que
    lo mide quien llama (la variable no lo dice). Devuelve `{"ops": [...], "reiniciar": bool}`.

    El reinicio no se adivina: cada variable dice si su cambio lo exige (`needServerRestart`),
    así que sólo se reinicia cuando de verdad se ha escrito algo que lo pide, y nunca por una
    escritura que no cambió nada. Si la variable no aparece en la lectura —no está o no es
    visible—, se da por hecho que el cambio exige reinicio: ante la duda, que el cambio surta
    efecto, porque lo contrario es dejarlo apagado creyendo que está encendido.

    Pero el valor escrito **no es la escucha en pie**, y la vista no tiene ningún campo que diga
    «esto está escrito y todavía no en vigor» —medido: la lectura sólo trae el valor—: una pasada
    que escriba y se corte antes de reiniciar dejaría el valor correcto y la escucha apagada, y la
    siguiente pasada, al ver el valor correcto, no reiniciaría jamás. Por eso, cuando se declaró
    encendida y **no hay nadie escuchando el puerto**, se reinicia aunque no hubiera nada que
    escribir. Sin poder medirlo (`escuchando is None`) no se reinicia: un reinicio a ciegas en cada
    pasada sería peor que el problema.

    Sin declaración no se toca nada: encender una escucha que nadie ha pedido es una decisión del
    entorno, no del motor (ADR 0019). El laboratorio no declara esto —ni sus equipos—: el qué se
    mira es del mundo.
    """
    if not declarado:
        return {"ops": [], "reiniciar": False}
    por_nombre = {v.get("name"): v for v in (actuales or []) if isinstance(v, dict)}
    encender = bool(declarado.get("recoger"))
    deseado = {NETXMS_REGISTRO_ESCUCHA: "1" if encender else "0"}
    if declarado.get("puerto") is not None:
        deseado[NETXMS_REGISTRO_PUERTO] = str(declarado["puerto"])
    ops: list[dict] = []
    reiniciar = False
    for nombre, valor in deseado.items():
        actual = por_nombre.get(nombre)
        if actual is not None and str(actual.get("value", "")) == valor:
            continue
        if nombre == NETXMS_REGISTRO_ESCUCHA:
            efecto = ("que la vista escuche los registros de los equipos"
                      if valor == "1" else "que la vista deje de escuchar registros de los equipos")
        else:
            efecto = f"que la vista escuche los registros en el puerto {valor}"
        ops.append({"cmd": netxms_config_cmd(api, nombre),
                    "cuerpo": json.dumps({"value": valor}),
                    "effect": efecto})
        # Desconocida o presente: si no se pudo leer, se reinicia por si acaso.
        reiniciar = reiniciar or bool((actual or {}).get("needServerRestart", True))
    # El valor dice lo que está escrito; la escucha dice lo que pasa. Si se declaró encendida y no
    # hay nadie escuchando, falta el reinicio —lo escriba esta pasada o una anterior que se cortó—.
    if encender and escuchando is False:
        reiniciar = True
    return {"ops": ops, "reiniciar": reiniciar}


def netxms_reinicio_cmd() -> list:
    """Reiniciar el servicio de la vista, y decirlo.

    Va por la puerta del invitado (`interior_ssh.yml`) porque no es una llamada a su API sino un
    servicio de dentro. Imprime `CAMBIO:1` para que el motor pueda distinguir «se reinició» de
    «se intentó»: la puerta no da por bueno lo que no puede comprobar.
    """
    return _sh("systemctl restart netxms-server && echo CAMBIO:1")


# El puerto por defecto de cada esquema: el que un cliente HTTP usaría cuando la dirección no lo
# escribe. Sin esto, una dirección válida como `http://127.0.0.1/v1` se quedaría sin puerto que
# leer y el `apply` se pararía, o la espera aceptaría cualquier puerto abierto.
NETXMS_PUERTO_POR_ESQUEMA = {"http": 80, "https": 443}


def netxms_puerto_api(api: str) -> int:
    """El puerto por el que atiende el servicio de gestión, leído de su dirección.

    La dirección del API es la única que sabe por dónde se entra, así que el puerto no se
    escribe a mano: se lee de ella con un analizador de URL, que entiende lo que partir la
    cadena no —una dirección sin puerto (`http://127.0.0.1/v1`) y una IPv6 entre corchetes
    (`http://[::1]:8000/v1`)—. Sin puerto explícito manda el del esquema, que es lo que haría
    un cliente HTTP. Una dirección que el analizador no sepa leer para el `apply` en vez de
    inventarse un puerto, que sería dejar la espera mirando donde nadie escucha.
    """
    partes = urlsplit(api)
    try:
        puerto = partes.port
    except ValueError as exc:
        raise LabError(
            f"la dirección del API de gestión no trae un puerto válido: {api}") from exc
    if puerto is not None:
        return puerto
    return NETXMS_PUERTO_POR_ESQUEMA.get(partes.scheme.lower(), 80)


def netxms_espera_cmd(puerto: int) -> list:
    """El guion que espera a que el servicio vuelva a atender, y sólo entonces lo dice.

    Sondea con un tope en vez de esperar a ciegas, y mira las escuchas TCP filtrando por el
    puerto **entero** —`ss ... sport = :<puerto>`—: una coincidencia parcial (`:80` dentro de
    `:8080`) daría por vuelto un servicio que todavía no atiende, y el `apply` acabaría en
    verde con la vista muerta. El guion viaja entrecomillado entero (ver `_sh`).
    """
    vueltas = " ".join(str(vuelta) for vuelta in range(1, 61))
    return _sh(
        f"for i in {vueltas}; do "
        f"ss -Hltn sport = :{int(puerto)} | grep -q LISTEN && echo LISTO && exit 0; "
        f"sleep 3; done; exit 1"
    )


def _identidad_para_la_vista(identidad: dict | None) -> dict | None:
    """La identidad resuelta del entorno, dicha como la dice la vista.

    Una sola identidad se declara una vez y cada sistema la escribe a su manera: RouterOS
    llama `AES` a lo que la vista llama `AES-128`, y la comunidad de v2c se llama aquí
    `authName` porque para SNMP v1/v2c el nombre de la comunidad **es** el nombre con el
    que se autentica. Sin identidad declarada no hay nada que poner: quien la necesite lo
    dice (el equipo que la encienda lo comprueba en `_snmp_ops`).
    """
    if identidad is None:
        return None
    if identidad["version"] == 2:
        return {"version": "2c", "authName": identidad["comunidad"], "authMethod": "NONE",
                "authPassword": "", "privMethod": "NONE", "privPassword": ""}
    return {
        "version": "3",
        "authName": identidad["usuario"],
        "authMethod": identidad["autenticacion"],
        "authPassword": identidad["clave_autenticacion"],
        "privMethod": NETXMS_CIFRADO_DESDE_ROUTEROS.get(identidad["cifrado"], identidad["cifrado"]),
        "privPassword": identidad["clave_cifrado"],
    }


def _cambios_del_grupo(actual: dict, deseado: dict) -> dict:
    """Los campos del grupo SNMP que hay que escribir, comparando de verdad.

    La vista aplica un `PATCH` de fusión —sólo lo que se le manda— y devuelve las claves al
    leerlas (medido), así que la comparación es real: si ya coinciden, no hay llamada y un
    `apply` repetido no escribe. Se manda la versión siempre que cambie, porque es la que
    elige el modelo de seguridad: un usuario v3 escrito sobre un equipo en v2c se guardaría
    como comunidad, y las claves viajarían en claro sin que nadie se enterara.
    """
    return {clave: valor for clave, valor in deseado.items()
            if str(actual.get(clave, "")) != str(valor)}



def _direccion_de(node: dict) -> str:
    """La dirección con la que la vista conoce a este nodo, o vacío si aún no tiene.

    Un equipo de red se registra por su pata de gestión (`mgmt_address`), que no está
    en su topología. Un nodo final —servidor o puesto— no tiene pata de gestión: se
    registra por la dirección de su única interfaz cuando es estática, o por la que el
    servidor DHCP le reservó. Un `dhcp` sin reserva no es una dirección: no hay nada
    que registrar, y fingir una sería dibujar un nodo que no es.
    """
    if node.get("netxms_address"):
        return str(node["netxms_address"])
    if node.get("reserve"):
        return str(node["reserve"])
    if node.get("mgmt_address"):
        return str(node["mgmt_address"])
    if node.get("type") not in ("server", "workstation"):
        return ""
    for iface in node.get("interfaces") or []:
        direccion = str(iface.get("address") or "").strip()
        if not direccion or direccion == "dhcp":
            continue
        try:
            return str(ipaddress.ip_interface(direccion).ip)
        except ValueError:
            continue
    return ""


def linux_clave(_node: dict, secrets: dict | None = None) -> str:
    """La contraseña de root que el motor deja a los invitados Linux.

    Es una credencial del sitio, no del laboratorio: el laboratorio no lleva
    escritas claves, igual que no lleva la del RouterOS. Sin ella no se puede
    abrir una terminal desde la vista, así que su ausencia es un error y no un
    nodo a medias.
    """
    valor = (secrets or {}).get("linux_clave")
    if not isinstance(valor, str) or not valor:
        raise LabError(
            "no hay `linux_clave` en secrets.yml: es la contraseña con la que se abre "
            "la terminal de los invitados Linux desde la vista"
        )
    return valor


def _la_vista_sondea(node: dict) -> bool:
    """Si la vista mira a este equipo por SNMP: un equipo de red que enciende el área.

    Un puesto no habla SNMP —su salud va por ICMP— y un equipo sin el área no tiene el servicio
    encendido, así que la vista no tiene qué sondear en ninguno de los dos. Sin ninguno, el motor
    no resuelve la identidad de sondeo: no hace falta.
    """
    if node.get("type") in ("server", "workstation"):
        return False
    return bool(((node.get("configure") or {}).get("snmp") or {}).get("enabled"))


# La imagen con la que la vista dibuja un equipo. El mapa **no** la elige: el mapa sólo
# pide el icono de cada objeto, y la vista lo saca del propio objeto (`getMapImage()`) y,
# si el objeto no trae imagen, de la que ella da por la **clase**. Y ahí está el problema
# que esto arregla: un servidor y un puesto de trabajo son los dos un `Node` de Linux, sin
# ninguna capacidad SNMP que los distinga, así que la vista les pone el mismo dibujo; un
# router y un switch sí se separan porque sus capacidades (`isRouter`, `isBridge`) son
# distintas. Fijar la imagen del objeto por el **tipo** del equipo deja de depender de lo
# que la vista adivine y separa un servidor de un puesto aunque sean el mismo nodo genérico.
#
# Los identificadores son los de la biblioteca de imágenes que la vista ya trae —los que
# siembra su administrador de base de datos—, no inventados: un UUID que no exista deja al
# equipo sin dibujar. Y la imagen va en el **objeto**, no en el mapa, porque es de donde la
# vista la lee (`netxms_imagen_cmd`).
NETXMS_ICONO_POR_TIPO = {
    # Un router y un cortafuegos enrutan los dos y la biblioteca no trae un dibujo propio de
    # cortafuegos: comparten el de aparato de red en vez de fingir que hay uno distinto.
    "router": "bacde727-b183-4e6c-8dca-ab024c88b999",
    "firewall": "bacde727-b183-4e6c-8dca-ab024c88b999",
    "switch": "f9105c54-8dcf-483a-b387-b4587dfd3cba",
    "server": "ba6ab507-f62d-4b8f-824c-ca9d46f22375",
    "workstation": "904e7291-ee3f-41b7-8132-2bd29288ecc8",
    "control": "092e4b35-4e7c-42df-b9b7-d5805bfac64e",
}
# Un tipo que no esté en la tabla —uno que se añada mañana— no puede quedarse sin dibujar:
# cae en el nodo genérico, que es la imagen que la vista da a lo que no reconoce.
NETXMS_ICONO_POR_DEFECTO = "904e7291-ee3f-41b7-8132-2bd29288ecc8"


def netxms_icono_de(nodo: dict) -> str:
    """La imagen con la que la vista dibuja a este equipo, según su tipo.

    El tipo es la parte del rol que dice qué es el equipo —sale del nombre y no de una
    lista de equipos de un laboratorio—. Un tipo desconocido no rompe el alta: se dibuja
    como el nodo genérico.
    """
    return NETXMS_ICONO_POR_TIPO.get(str(nodo.get("type")), NETXMS_ICONO_POR_DEFECTO)


def netxms_ops(nodes: list[dict], encontrados: list | None, detalles: list | None,
               api: str, secrets: dict | None = None,
               puerto: int = NETXMS_PUERTO_SSH, vivas: list | None = None,
               propias: list | None = None, observabilidad: dict | None = None) -> dict:
    """Qué equipos del laboratorio faltan en la vista, y cuáles están a medias.

    `encontrados` es el censo que devuelve la búsqueda (resúmenes, sin credenciales);
    `detalles`, las fichas de los que ya están (que sí las traen, y por eso se piden).
    El resultado lleva dos listas: `ops` (lo que hay que escribir) y `pendientes` (lo
    que no se puede arreglar por el API y se dice).

    **La identidad de un equipo en la vista es su nombre, no su dirección.** La
    dirección de gestión se deriva del vmid, y el vmid cambia cuando el invitado se
    rehace: atada a la dirección, cada despliegue daba de alta un equipo nuevo con el
    mismo nombre y el viejo se quedaba apuntando a la máquina de otro —abrir un router
    en la consola llevaba al switch de otra sede—. Por eso se busca por nombre y se comprueba la
    dirección: si el equipo con ese nombre no lleva su dirección, se retira y se vuelve
    a dar de alta. El API de esta versión no deja corregirla (ver `netxms_borrar_cmd`).

    `vivas` son las direcciones que hoy tiene algún invitado del clúster, y `propias` las
    de los invitados de **este** laboratorio. Un equipo con el mismo nombre y una
    dirección viva que no es de este laboratorio es de **otro** laboratorio en marcha, y
    no se toca; uno que apunta a una dirección de este laboratorio que no es la suya es
    un resto de este y se borra. Uno que apunta a una dirección que hoy no tiene nadie
    **no se borra**: compartir nombre y que la dirección esté libre no demuestra a quién
    pertenece —el homónimo de un laboratorio ya destruido deja exactamente eso— y su
    histórico no se retira por si acaso; sale como pendiente y lo retira una persona.
    Lo que va en `propias` son las direcciones de los invitados del laboratorio, no las
    de sus equipos: así se distingue «suya y con otra máquina» de «de nadie».

    Un equipo que ya está como debe no produce ninguna llamada —eso es lo que hace que
    el segundo `apply` no escriba— y uno que ya está con otras credenciales sale como
    pendiente, porque el API de esta versión sólo las acepta al crear el equipo.

    La identidad con la que la vista **sondea** un equipo va aparte y sí se corrige: se
    le dice en el alta y, si el equipo ya estaba registrado con otra —o sondéandose en
    claro—, con un `PATCH` de su grupo SNMP. Es la misma identidad que el entorno declara
    una sola vez (ADR 0019); aquí sólo se traduce a como la escribe la vista.

    La imagen con la que la vista **dibuja** a un equipo también va aparte y se corrige:
    se fija en el alta y, en uno que ya estaba registrado sin ella, con un `PATCH` del
    objeto. Sale del **tipo** del equipo —un dato que lleva el rol, derivado del nombre— y
    no de una lista de equipos de un laboratorio, así que vale para cualquier laboratorio;
    sin ella, un servidor y un puesto —los dos un `Node` de Linux— salen con el mismo
    dibujo (ver `netxms_icono_de`).
    """
    por_nombre: dict = {}
    por_ip: dict = {}
    for objeto in encontrados or []:
        nombre_visto = str(objeto.get("name") or "").strip()
        if nombre_visto:
            por_nombre.setdefault(nombre_visto, []).append(objeto)
        suya = str((objeto.get("ipAddress") or {}).get("address") or "")
        if suya:
            por_ip.setdefault(suya, []).append(objeto)
    leidos: dict = {}
    for detalle in detalles or []:
        if isinstance(detalle, dict) and detalle.get("id") is not None:
            leidos[int(detalle["id"])] = detalle

    vivas_set = {str(d) for d in (vivas or [])}
    # Las de este laboratorio: las de sus invitados, no sólo las de los equipos que se
    # registran (una estación de trabajo no se registra, pero su dirección es de aquí, y
    # un resto apuntando ahí es un resto de este laboratorio).
    direcciones_del_lab = ({str(d) for d in propias} if propias
                           else {_direccion_de(n) for n in nodes or []
                                 if _direccion_de(n)})

    def marca_de(node: dict) -> str:
        """La marca que el motor escribe en el comentario del equipo, si es suya.

        Compartir nombre y que la dirección la tenga hoy un invitado de este laboratorio
        no demuestra quién creó el registro: el asignador puede reutilizar un vmid y su
        dirección para un puesto de otro laboratorio, y entonces el histórico de aquél
        cae dentro de lo que parece de éste. La marca que se escribe al crear el equipo
        sí lo dice, y sin ella el registro se conserva y se informa.
        """
        descripcion = str(node.get("description") or "")
        return descripcion if descripcion.startswith("netlabs lab=") else ""

    # Las retiradas van ANTES que las altas, todas juntas: un equipo viejo puede estar
    # ocupando la dirección del que hay que dar de alta —el API contesta 409 si la
    # dirección ya es de otro—, y las retiradas se descubren al recorrer los equipos,
    # así que en un solo recorrido la del último llegaría después del alta del primero.
    #
    # Se hace en dos pasadas —primero las retiradas, después las altas— por la misma
    # razón llevada al plan: la segunda pasada sabe qué direcciones va a liberar la
    # primera y no toma por ocupada una que este mismo `apply` deja libre.
    borrados: list[dict] = []
    retirados: set[int] = set()
    pendientes: list[str] = []
    equipos: list[tuple[dict, list[dict], dict | None]] = []
    for node in nodes or []:
        direccion = _direccion_de(node)
        if not direccion:
            continue
        nombre = node.get("name") or node.get("role")
        candidatos = por_nombre.get(str(nombre), [])
        objeto = next(
            (o for o in candidatos
             if str((o.get("ipAddress") or {}).get("address")) == str(direccion)), None)
        equipos.append((node, candidatos, objeto))

        # Los que llevan el mismo nombre y no son este equipo: o son restos de este
        # laboratorio —una máquina suya que ya no es la que dicen—, o son de otro
        # laboratorio. Compartir nombre no basta para saberlo: sólo se retira lo que se
        # puede demostrar de aquí, es decir, un objeto con la marca de este laboratorio
        # que apunta a una dirección que hoy tiene un invitado suyo. Un objeto que apunta
        # a una dirección que ya no tiene nadie puede ser el histórico de un laboratorio
        # destruido, y eso no se borra (AGENTS.md §3.6): se dice y lo retira una persona
        # si es un resto.
        for sobrante in candidatos:
            if sobrante is objeto:
                continue
            suya = str((sobrante.get("ipAddress") or {}).get("address") or "")
            ficha = leidos.get(int(sobrante["id"])) or {}
            suya_de_aqui = (marca_de(node)
                            and marca_de(node) in str(ficha.get("comments") or ""))
            if suya_de_aqui and suya in direcciones_del_lab:
                borrados.append({
                    "cmd": netxms_borrar_cmd(api, sobrante["id"]),
                    "cuerpo": "",
                    "effect": (f"retirar {nombre}, que apuntaba a {suya} "
                               f"y ya no es esa máquina"),
                })
                if sobrante.get("id") is not None:
                    retirados.add(int(sobrante["id"]))
            elif suya not in vivas_set:
                pendientes.append(
                    f"{nombre}: hay un equipo con ese nombre apuntando a {suya or 'ninguna dirección'}, "
                    "y ningún invitado de este laboratorio tiene esa dirección: no consta que sea "
                    "suyo, así que no se retira para no borrar el histórico de otro laboratorio. "
                    "Si es un resto de este, retíralo a mano en la consola"
                )
            elif suya in direcciones_del_lab:
                # La dirección es de aquí, pero el registro no lleva la marca de este
                # laboratorio: pudo crearlo otro sobre una máquina que hoy es nuestra.
                # No hay prueba, así que no se borra; se dice para que alguien decida.
                pendientes.append(
                    f"{nombre}: hay un equipo con ese nombre apuntando a {suya}, que hoy es "
                    "de este laboratorio, pero su registro no lleva la marca de aquí: no "
                    "consta que sea suyo y no se retira. Si es un resto, retíralo a mano"
                )

    altas: list[dict] = []
    identidades: list[dict] = []
    imagenes: list[dict] = []
    # La identidad de sondeo sólo se resuelve si algún equipo la pide: un laboratorio sin SNMP
    # no exige la credencial —no hay nada que sondear—, y resolverla antes hacía que faltara un
    # secreto que nadie iba a usar. Se resuelve una vez y se reutiliza en cada alta y en cada
    # PATCH del grupo SNMP.
    de_la_vista = (_identidad_para_la_vista(observabilidad_de(observabilidad, secrets))
                   if any(_la_vista_sondea(n) for n in nodes or []) else None)
    for node, _candidatos, objeto in equipos:
        direccion = _direccion_de(node)
        nombre = node.get("name") or node.get("role")
        # Un nodo final no habla RouterOS: su terminal se abre con la cuenta de los
        # invitados Linux. Hasta ahora se registraba sin credenciales y la consola
        # no sabía abrirle nada; ahora se registra con root y la clave del sitio,
        # igual que un equipo de red se registra con la suya.
        es_final = node.get("type") in ("server", "workstation")
        usuario = "root" if es_final else (_declared_user(node) or "admin")
        clave = linux_clave(node, secrets) if es_final else ros_clave(node, secrets or {})
        # La identidad con la que la vista sondea un equipo se pone donde hay algo que
        # sondear: sólo en quien enciende SNMP. Sin el área, el motor no toca el servicio
        # en el equipo (ver `_snmp_ops`), así que tampoco tiene sentido decirle a la vista
        # que lo sondee; y un nodo final no habla SNMP —su salud se mira por ICMP—, así
        # que la identidad es de los equipos de red.
        grupo = de_la_vista if _la_vista_sondea(node) else None
        # Un nodo final que ya está registrado sin credenciales (o con otras) no se
        # puede arreglar con PATCH: el API de esta versión las ignora. Se rehace una
        # vez —se retira y se vuelve a dar de alta— para que su terminal abra sola;
        # su histórico de ping es lo único que se pierde y se repuebla en el sondeo.
        rehacer = (objeto is not None and es_final
                   and int(objeto.get("id") or 0) in retirados)
        if objeto is not None and es_final and not rehacer:
            actual = leidos.get(int(objeto["id"])) or {}
            if (str(actual.get("sshLogin") or "") == usuario
                    and str(actual.get("sshPassword") or "") == clave
                    and int(actual.get("sshPort") or 0) == int(puerto)):
                continue
            # Compartir nombre y dirección no demuestra quién creó el registro: el
            # asignador puede reutilizar la dirección para un puesto de otro
            # laboratorio. La marca del comentario es la prueba; sin ella no se
            # rehace, porque borraría el histórico de otro (AGENTS.md §3.6).
            suyo_de_aqui = (marca_de(node)
                            and marca_de(node) in str(actual.get("comments") or ""))
            if not suyo_de_aqui:
                pendientes.append(
                    f"{nombre} ({direccion}): ya está en la vista con otras credenciales "
                    f"(usuario {actual.get('sshLogin') or 'ninguno'}), y su registro no "
                    "lleva la marca de este laboratorio: no consta que sea suyo y no se "
                    "rehace para no borrar el histórico de otro. Si es un resto, "
                    "retíralo a mano en la consola"
                )
                continue
            borrados.append({
                "cmd": netxms_borrar_cmd(api, objeto["id"]),
                "cuerpo": "",
                "effect": (f"rehacer {nombre} ({direccion}) para que su terminal "
                           f"abra como {usuario}"),
            })
            retirados.add(int(objeto["id"]))
            rehacer = True

        if objeto is None or rehacer:
            # El API contesta 409 si la dirección ya es de otro equipo. Se mira antes,
            # para decirlo con su nombre y su id en vez de dejar que el play se pare a
            # mitad con un cuerpo de error; y se para igual, porque un alta obligatoria
            # que no se hace no puede pasar por un laboratorio desplegado.
            ocupantes = [o for o in por_ip.get(str(direccion), [])
                         if o.get("id") is None or int(o["id"]) not in retirados]
            if ocupantes:
                otro = ocupantes[0]
                # No es un aviso: sin el alta, el equipo no está en la vista y el
                # laboratorio no está desplegado. Un `pendientes` aquí dejaba que
                # `netxms.yml` anunciara el laboratorio como desplegado sin haberlo
                # registrado, y el 409 que antes paraba el play ya no llegaba a verse.
                raise LabError(
                    f"{nombre}: la dirección {direccion} ya la ocupa el equipo "
                    f"{otro.get('name') or '(sin nombre)'} (id {otro.get('id')}), que no "
                    "consta como retirada en este plan: el API rechazaría el alta con 409 "
                    "y no hay manera de registrar el equipo. Retíralo a mano si es un resto"
                )
            cuerpo = {
                "class": "Node",
                "name": nombre,
                "ipAddress": str(direccion),
                # La marca de propiedad: sin ella, mañana no se puede demostrar que este
                # registro lo creó este laboratorio y su histórico no se puede retirar.
                "comments": node.get("description") or "",
                "sshLogin": usuario,
                "sshPassword": clave,
                "sshPort": int(puerto),
                # La imagen con la que la vista dibuja el equipo: va en el alta para que
                # un servidor y un puesto no salgan los dos con el mismo dibujo genérico
                # (ver `netxms_icono_de`). Es una propiedad del objeto, no del mapa.
                "mapImage": netxms_icono_de(node),
            }
            # Las credenciales SSH sólo se aceptan al crear; las de SNMP sí se pueden
            # corregir después, pero van en el mismo alta cuando se sabe con antelación:
            # un equipo que naciera sondeándose en claro y se arreglara en el mismo
            # `apply` habría pasado un rato con las claves a la vista de la red.
            if grupo:
                cuerpo["snmp"] = grupo
            altas.append({
                "cmd": netxms_crear_cmd(api),
                "cuerpo": json.dumps(cuerpo),
                "effect": f"registrar {nombre} ({direccion}) en la vista, como {usuario}",
            })
            continue

        # Un equipo de red ya registrado con otras credenciales no se rehace: borrarlo
        # perdería lo recolectado y su identidad; se dice para que lo cambie una
        # persona. Los nodos finales sí se rehacen arriba, porque su terminal es el
        # único uso de esas credenciales.
        actual = leidos.get(int(objeto["id"])) or {}
        # La identidad de sondeo va aparte de la terminal y se arregla aunque la terminal
        # esté como debe: son dos cosas independientes, y un equipo que ya tiene bien sus
        # credenciales SSH puede seguir contestando en claro por SNMP.
        if grupo and objeto.get("id") is not None:
            cambios = _cambios_del_grupo(actual.get("snmp") or {}, grupo)
            if cambios:
                identidades.append({
                    "cmd": netxms_snmp_cmd(api, objeto["id"]),
                    "cuerpo": json.dumps(cambios),
                    "effect": (f"decirle a la vista con qué identidad sondea a {nombre} "
                               f"({direccion}): SNMP v{grupo['version']}"),
                })
        if (str(actual.get("sshLogin") or "") == usuario
                and str(actual.get("sshPassword") or "") == clave
                and int(actual.get("sshPort") or 0) == int(puerto)):
            continue
        pendientes.append(
            f"{nombre} ({direccion}): ya está en la vista con otras credenciales "
            f"(usuario {actual.get('sshLogin') or 'ninguno'}), y el API de esta versión "
            "sólo las acepta al crear el equipo: cámbialas a mano en su consola"
        )

    # La imagen de un equipo que ya estaba registrado se corrige en su propia pasada, no en
    # el alta: la corrección va al objeto que **existe** —uno que se acaba de crear o
    # recrear ya la lleva en el cuerpo— y no toca el que se retira para rehacerlo, que la
    # recibirá al volver a nacer. Va aparte de las credenciales por la misma razón que la
    # identidad de sondeo: es una propiedad independiente, y un equipo con la terminal bien
    # puede seguir saliendo con el dibujo genérico de antes de que el motor fijara la imagen.
    #
    # Y sólo se le cambia la imagen a un equipo que **consta que es de este laboratorio**: la
    # marca del comentario es la misma prueba que gobierna el borrado, y un objeto con el
    # nombre y la dirección de un equipo pero sin la marca —uno manual, o el resto de otro
    # laboratorio que ocupa esa dirección— no se toca, ni para dibujarlo.
    for node, _candidatos, objeto in equipos:
        if objeto is None or int(objeto["id"]) in retirados:
            continue
        actual = leidos.get(int(objeto["id"])) or {}
        suyo_de_aqui = (marca_de(node)
                        and marca_de(node) in str(actual.get("comments") or ""))
        if not suyo_de_aqui:
            continue
        imagen = netxms_icono_de(node)
        if str(actual.get("mapImage") or "") == imagen:
            continue
        direccion = _direccion_de(node)
        nombre = node.get("name") or node.get("role")
        imagenes.append({
            "cmd": netxms_imagen_cmd(api, objeto["id"]),
            "cuerpo": json.dumps({"mapImage": imagen}),
            "effect": f"decirle a la vista con qué imagen dibuja a {nombre} ({direccion})",
        })
    return {"ops": borrados + altas + identidades + imagenes, "pendientes": pendientes}


def netxms_ids(nodes: list[dict], encontrados: list | None) -> list:
    """Los identificadores de los equipos de este laboratorio que ya están en la vista.

    La búsqueda devuelve resúmenes sin credenciales, así que la ficha hay que pedirla:
    se pide **de una vez** por los que interesan, y no la de todo el censo — que sería
    leer lo de todos los laboratorios para escribir lo de uno—.
    """
    # Se piden las fichas de dos clases de objeto, y ninguna más: los equipos que ya
    # están **con su nombre y su dirección**, cuyo estado hay que mirar; y los que llevan
    # el nombre de un equipo del laboratorio aunque apunten a otra dirección, porque su
    # ficha es la única prueba de quién los creó —la marca del comentario— y sin ella un
    # resto no se puede retirar sin arriesgar el histórico de otro laboratorio.
    claves = {(str(n.get("name") or n.get("role")), _direccion_de(n))
              for n in nodes or [] if _direccion_de(n)}
    nombres = {str(n.get("name") or n.get("role")) for n in nodes or []}
    ids = []
    for objeto in encontrados or []:
        direccion = (objeto.get("ipAddress") or {}).get("address")
        nombre = str(objeto.get("name") or "").strip()
        clave = (nombre, str(direccion or ""))
        if direccion and (clave in claves or nombre in nombres) and objeto.get("id") is not None:
            ids.append(int(objeto["id"]))
    return sorted(ids)

# --- el mapa del laboratorio en la vista ------------------------------------
# El mapa que la vista dibuja sola —su topología por direcciones— no se parece a nada de
# lo que dibuja el plano. Aquí se deriva el mapa **a medida**: las áreas del plano como
# cajas, cada equipo de red en el sitio donde el plano lo pone —a caballo de sus redes— y
# cada cable del laboratorio entre los dos equipos que une.

NETXMS_RUTA_RAICES = "/objects"
NETXMS_CLASE_RAICES_DE_MAPA = "NetworkMapRoot"
NETXMS_CLASE_MAPA = "NetworkMap"
NETXMS_CLASE_INTERFAZ = "Interface"


def netxms_raices_cmd(api: str) -> list:
    """Las raíces de la vista: ahí está la de mapas, con su número."""
    return netxms_cmd(api, NETXMS_RUTA_RAICES, metodo="GET")


def netxms_hijos_cmd(api: str, id_objeto) -> list:
    """Lo que cuelga de un objeto: los mapas cuelgan de la raíz de mapas."""
    return netxms_cmd(api, f"/objects/{int(id_objeto)}/children", metodo="GET")


def netxms_mapa_crear_cmd(api: str) -> list:
    """Dar de alta el mapa del laboratorio, colgando de la raíz de mapas."""
    return netxms_cmd(api, NETXMS_RUTA_CREAR)


def netxms_mapa_leer_cmd(api: str, id_mapa) -> list:
    """Lo que el mapa tiene dibujado ahora mismo."""
    return netxms_cmd(api, f"/objects/{int(id_mapa)}/map", metodo="GET")


def netxms_mapa_escribir_cmd(api: str, id_mapa) -> list:
    """Escribir el contenido del mapa. Es `PUT`: reemplaza el dibujo entero."""
    return netxms_cmd(api, f"/objects/{int(id_mapa)}/map", metodo="PUT")


# --- lo que el laboratorio deja en la vista ---------------------------------
# `destroy` desmonta lo que el laboratorio declaró, y la vista es uno de los sitios donde
# lo declarado dejó rastro: sus equipos registrados y su mapa. Un laboratorio destruido no
# puede seguir apareciendo en la consola —equipos que ya no existen, en rojo, y un mapa que
# enseña una red que se apagó—, porque entonces «destruido» no se distingue de «desplegado».
#
# Ni aquí ni en Proxmox se borra «lo que sobra» ni «lo que está caído»: eso se llevaría por
# delante el de otro laboratorio que hoy no está desplegado. Se borra **lo que lleva la
# marca** que el motor escribe al dar de alta cada cosa (`netlabs lab=<lab>`), y el mapa por
# su nombre, que es el del laboratorio y la raíz no admite dos iguales.

NETXMS_MARCA = "netlabs lab="


def netxms_marca_de(lab: str) -> str:
    """La marca de propiedad de este laboratorio, tal y como se escribe al registrar."""
    return f"{NETXMS_MARCA}{lab}"


HUELLA_EN_EL_MAPA = "plano="


def netxms_huella_guardada(comentarios: str) -> str:
    """La huella del plano que el motor dejó escrita en el mapa, si dejó alguna.

    Se busca como palabra entera y no como trozo: una huella copiada a mano en medio de
    otra cosa no es la marca del motor, y creer que sí dejaría el mapa congelado.
    """
    for trozo in str(comentarios or "").split():
        if trozo.startswith(HUELLA_EN_EL_MAPA):
            return trozo[len(HUELLA_EN_EL_MAPA):]
    return ""


def netxms_lab_de_marca(comentario: str) -> str:
    """El laboratorio que nombra la marca de un comentario; vacío si no lleva ninguna.

    Se lee el valor **entero** de `lab=`, hasta el espacio, y se compara por igualdad, no
    como subcadena: `netlabs lab=x_uno` es prefijo de `netlabs lab=x_uno_dos`, y tomarlos
    por el mismo haría que destruir el primero se llevara por delante el histórico del
    segundo, sin comprobar nombre ni dirección (AGENTS.md §3.6). Se reutiliza el reconocedor
    de la identidad (`identity.lab_from_comment`), que ya valida ese patrón: el nombre de un
    laboratorio se escribe una sola vez.
    """
    return lab_from_comment(comentario or "") or ""



def netxms_restos_de(nodos: list | dict | None, lab: str, equipos: list | None = None,
                     espacios: list | None = None) -> dict:
    """Qué equipos de la vista son de este laboratorio, y cuáles lo parecen sin serlo.

    Los primeros son los que llevan la marca de este laboratorio en su comentario: de ésos
    consta que los registró el motor y se retiran con él. Los segundos son los que se
    llaman como un equipo del laboratorio y **además** tienen su dirección en un espacio que
    el laboratorio declaraba —donde estaría de verdad un resto suyo— pero no llevan su
    marca: no se tocan, se dicen, para que una persona decida. Un nombre no demuestra quién
    creó un registro y el asignador reutiliza direcciones (AGENTS.md §3.6); por eso el
    nombre solo no basta para señalar a nadie: hace falta que la dirección caiga en las
    redes que este laboratorio declaraba.

    Se le pasa lo que devuelve `/objects/details`, no el censo: el censo —`/objects/search`—
    **no trae los comentarios**, y sin ellos no hay marca que leer. Acepta el sobre tal cual
    (`{"objects": [...]}`) o la lista de objetos.
    """
    if isinstance(nodos, dict):
        nodos = nodos.get("objects") or []
    nombres = {str(n) for n in (equipos or [])}
    suyos, dudosos = [], []
    for nodo in nodos or []:
        comentario = str(nodo.get("comments") or "")
        ficha = {
            "id": int(nodo["id"]),
            "name": str(nodo.get("name") or ""),
            "address": str((nodo.get("ipAddress") or {}).get("address") or ""),
        }
        if netxms_lab_de_marca(comentario) == lab:
            suyos.append(ficha)
        elif ficha["name"] in nombres and _es_del_laboratorio(ficha["address"], espacios):
            dudosos.append(ficha)
    return {"suyos": suyos, "dudosos": dudosos}


def _es_del_laboratorio(direccion: str, espacios: list | None) -> bool:
    """¿Cae esta dirección en alguna de las redes que el laboratorio declaraba?

    Sin espacios declarados no se señala a nadie: señalar por el nombre solo llevaría a
    decir que los equipos de otros laboratorios —que comparten nombres— son restos.
    """
    if not direccion or not espacios:
        return False
    try:
        red = ipaddress.ip_network(direccion + "/32", strict=False)
    except ValueError:
        return False
    return _en_mis_espacios(red, espacios)


def netxms_mapa_del_lab(hijos: list | None, lab: str, nombre: str | None = None) -> dict:
    """El mapa de este laboratorio entre los que cuelgan de la raíz de mapas.

    Se reconoce por su nombre —el del laboratorio— y devuelve `{"id", "nombre", "ajeno",
    "comentario"}`: `id` vale 0 si no hay ninguno, y `ajeno` dice que el que se llama así
    lleva la marca de **otro** laboratorio; entonces no es suyo y no se retira: se para y se
    dice. El comentario viaja con la ficha porque es donde el motor deja la huella de lo que
    escribió: sin él no se puede distinguir un mapa que alguien ha ajustado a mano de uno
    que ha quedado como el plano, y el `apply` escribiría encima del trabajo de una persona.
    """
    nombre = str(nombre or lab)
    for objeto in hijos or []:
        if str(objeto.get("class") or "") != NETXMS_CLASE_MAPA:
            continue
        if str(objeto.get("name") or "") != nombre:
            continue
        marca = str(objeto.get("comments") or "")
        # `ajeno` es «lleva la marca EXPLÍCITA de OTRO laboratorio»: una nota suelta
        # —«revisar el lunes»— no demuestra que el mapa sea de otro y no puede bloquear
        # el propio, que se llama como el laboratorio y la raíz no admite dos iguales.
        lab_del_mapa = netxms_lab_de_marca(marca)
        return {"id": int(objeto["id"]), "nombre": nombre, "comentario": marca,
                "ajeno": bool(lab_del_mapa) and lab_del_mapa != lab}
    return {"id": 0, "nombre": nombre, "comentario": "", "ajeno": False}


def netxms_mapa_crear_cuerpo(lab: str, raiz) -> str:
    """El cuerpo con el que nace el mapa del laboratorio, con su marca de propiedad.

    La misma marca que llevan los equipos: es lo que deja demostrar mañana que este mapa lo
    creó este laboratorio y que se puede retirar sin rozar el de otro.
    """
    return json.dumps({
        "class": NETXMS_CLASE_MAPA,
        "parentId": int(raiz),
        "name": lab,
        "comments": netxms_marca_de(lab),
    })


# --- el marcador limpio -----------------------------------------------------
# La vista no resuelve sola sus alarmas. Una que saltó **una vez** —una MAC que cambió al
# volver a crear los invitados, una MAC que dos nodos compartieron un instante— se queda
# viva para siempre, y con ella el equipo en amarillo: el mapa enseña un mal que ya no
# está. Aquí se dan por resueltas las de los equipos de este laboratorio al converger. Si
# el mal sigue de verdad, la vista la vuelve a levantar en su siguiente vuelta: resolver no
# es esconder, es dejar de repetir lo que ya pasó.

NETXMS_RUTA_ALARMAS = "/alarms"
NETXMS_ALARMA_VIVA = 0            # la vista: 0 viva, 1 reconocida, 2 resuelta
NETXMS_AVISO = 1                  # severidad: por debajo de aviso no hay nada que mirar


def netxms_alarmas_cmd(api: str) -> list:
    """El registro de alarmas de la vista, entero.

    El listado no filtra por equipo —`?objectId=` lo ignora, comprobado—, así que se pide
    todo y se separa aquí, por el `source` que cada alarma sí trae.
    """
    return netxms_cmd(api, NETXMS_RUTA_ALARMAS, metodo="GET")


def netxms_alarma_resolver_cmd(api: str, id_alarma) -> list:
    """Dar por resuelta una alarma. Es lo que la vista acepta: `DELETE` contesta 405."""
    return netxms_cmd(api, f"{NETXMS_RUTA_ALARMAS}/{int(id_alarma)}/resolve", metodo="POST")


def netxms_alarmas_propias(alarmas: list | None, ids: list | None) -> list:
    """Las alarmas vivas y con algo que decir de los equipos de ESTE laboratorio.

    Sólo las de sus equipos (`source`, que es el número del objeto): las de otro
    laboratorio no se tocan. Y sólo de aviso para arriba: por debajo está el ruido que la
    vista apunta sola —un paquete instalado— y eso no se resuelve ni hace falta.
    """
    mios = {int(i) for i in ids or []}
    return [a for a in (alarmas or [])
            if int(a.get("source") or 0) in mios
            and int(a.get("state") or 0) == NETXMS_ALARMA_VIVA
            and int(a.get("severity") or 0) >= NETXMS_AVISO]


def netxms_raiz_de_mapas(raices: list | None) -> int | None:
    """El número de la raíz de mapas, que no se supone: se lee de la vista."""
    for objeto in raices or []:
        if str(objeto.get("class") or "") == NETXMS_CLASE_RAICES_DE_MAPA:
            return int(objeto["id"])
    return None


def netxms_objetos_de(nodes: list[dict], censo: list | None) -> tuple[dict, list]:
    """Qué número tiene en la vista cada equipo de red del laboratorio.

    Se empareja por nombre **y** dirección, como el registro: dos laboratorios pueden
    tener cada uno su equipo de red con el mismo nombre —el nombre es del laboratorio, no
    de la vista— y el que se dibuja en este mapa es el que apunta a la máquina de este
    laboratorio. Un equipo que no está en la vista devuelve su nombre en la segunda
    lista: sin objeto detrás, un elemento del mapa no lo acepta la vista, así que no se
    dibuja y se dice.
    """
    objetos, faltan = {}, []
    for node in nodes or []:
        nombre = str(node.get("name") or node.get("role") or "")
        direccion = _direccion_de(node)
        if not nombre or not direccion:
            continue
        cual = next((o for o in censo or []
                     if str(o.get("name") or "") == nombre
                     and str((o.get("ipAddress") or {}).get("address") or "") == direccion), None)
        if cual is None:
            faltan.append(nombre)
            continue
        objetos[str(node.get("role") or nombre)] = int(cual["id"])
    return objetos, sorted(faltan)


def netxms_propios_de(nodes: list[dict], censo: list | None) -> list:
    """Los números de los equipos de ESTE laboratorio en la vista, por nombre **y** dirección.

    `netxms_ids` devuelve también los homónimos que llevan el nombre de un equipo de aquí
    apuntando a otra máquina: la ficha de ésos hace falta para saber quién los creó, porque
    sin la marca no se puede retirar un resto sin arriesgar el histórico de otro
    laboratorio. Pero un homónimo es de otro y sus alarmas no se miran: con sus números, el
    marcador daría por resueltas las de un laboratorio ajeno. Aquí sólo quedan los que están
    con la dirección que este laboratorio les deriva, que es el mismo emparejamiento con el
    que el mapa los dibuja.
    """
    objetos, _ = netxms_objetos_de(nodes, censo)
    return sorted({int(numero) for numero in objetos.values()})


def netxms_interfaces_de(nodes: list[dict], censo: list | None, fichas: list | None,
                         interfaces: list | None) -> dict:
    """Qué número tiene en la vista cada interfaz de cada equipo del laboratorio.

    En la vista una interfaz se llama como la llama su equipo —`ether1`, `ether2`…—, que es
    el mismo nombre con el que el motor conecta cada pata: el puerto `p3` del plano es la
    `ether3` del equipo. El número hace falta para que el cable del mapa quede atado a la
    interfaz por la que sale, en vez de unir dos iconos sin decir por dónde va.

    Se cruzan dos lecturas que ya se hacían: el censo de interfaces dice el nombre de cada
    número, y la ficha de cada equipo dice cuáles son sus hijos —sus interfaces—. El censo
    por sí solo no basta: no dice de quién es cada interfaz.
    """
    objetos, _ = netxms_objetos_de(nodes, censo)
    nombre_de = {int(o["id"]): str(o.get("name") or "")
                 for o in interfaces or [] if o.get("id") is not None}
    hijos_de = {}
    for ficha in fichas or []:
        if ficha.get("id") is None:
            continue
        hijos = []
        for hijo in ficha.get("children") or []:
            if isinstance(hijo, dict) and hijo.get("id") is not None:
                hijos.append(int(hijo["id"]))
            elif isinstance(hijo, int):
                hijos.append(hijo)
        hijos_de[int(ficha["id"])] = hijos
    salida = {}
    for node in nodes or []:
        rol = str(node.get("role") or node.get("name") or "")
        suyo = objetos.get(rol)
        if not suyo:
            continue
        suyas = {nombre_de[i]: i for i in hijos_de.get(int(suyo), [])
                 if nombre_de.get(i)}
        if suyas:
            salida[rol] = dict(sorted(suyas.items()))
    return salida


BANDERAS_QUE_EL_MAPA_ENSENA = ("showStatusIcon", "showStatusFrame", "showStatusBackground")


def netxms_mapa_banderas(objeto: dict | None) -> dict | None:
    """El cuerpo que enciende el marco y el fondo de estado, o None si ya están puestos.

    Las banderas viajan con nombre y apellido (`showStatusFrame`), no como número: el
    `PATCH` del API reemplaza el objeto de banderas entero, así que se devuelven todas
    las que el mapa tiene —las que trae de fábrica uno recién hecho, si todavía no hay
    ninguna— con las tres encendidas. Sólo se manda cuando alguna está apagada, para que
    el `apply` siga sin tocar nada la segunda vez.
    """
    vivas = dict((objeto or {}).get("flags") or {})
    if not vivas:
        vivas = {"showStatusIcon": True}
    if all(vivas.get(b) is True for b in BANDERAS_QUE_EL_MAPA_ENSENA):
        return None
    for b in BANDERAS_QUE_EL_MAPA_ENSENA:
        vivas[b] = True
    return {"flags": vivas}


def netxms_mapa_ops(lab: dict, nodes: list[dict], censo: list | None, actual: dict | None,
                    api: str, id_mapa, fichas: list | None = None,
                    interfaces: list | None = None, svg: str | None = None,
                    comentarios: str = "", objeto: dict | None = None) -> dict:
    """Lo que hay que escribir para que el mapa de la vista sea el plano del laboratorio.

    Sólo se escribe si el mapa que hay no es ya el que el plano pide: la segunda pasada no
    toca nada. Los equipos del plano que la vista no conoce no se dibujan (y sus cables
    tampoco) y salen en `pendientes`, que es lo que se dice en voz alta.

    `fichas` e `interfaces` son las dos lecturas con las que cada cable queda atado a la
    interfaz por la que sale (`netxms_interfaces_de`); sin ellas el mapa se dibuja igual,
    pero sus cables unen dos iconos y no dicen por dónde van. `comentarios` es el comentario
    del objeto tal y como lo tiene la vista: ahí viaja la huella de lo que el motor escribió
    la última vez, que es lo que distingue un ajuste a mano de un cambio del plano.
    """
    objetos, faltan = netxms_objetos_de(nodes, censo)
    if svg is None:
        svg = plano.plano(lab, "topologia")
    atadas = netxms_interfaces_de(nodes, censo, fichas, interfaces)
    deseado = mapa.contenido(lab, svg, objetos, atadas)
    # Las interfaces que de verdad quedaron atadas: cuántas puntas de los cables generados
    # traen la interfaz de la que salen. Contar las interfaces que la vista le ha descubierto
    # a cada equipo diría de más —entran `lo`, la de gestión y las de puertos cuyos cables no
    # salen en el mapa— y no diría cuántas puntas quedaron atadas, que es lo que se comprueba.
    cuantas = sum(1 for enlace in deseado["links"] for punta in ("interface1", "interface2")
                  if int(enlace.get(punta) or 0))
    # Las áreas son las cajas del plano y los rótulos, las cajas de texto: la ficha de cada
    # equipo y el nombre y el bloque de cada zona. Contar por todo lo que no es un equipo y
    # llamarlo «áreas» es contar mal lo que se está mirando.
    cajas = sum(1 for e in deseado["elements"] if int(e.get("type") or 0) == mapa.ELEMENTO_ADORNO)
    rotulos = sum(1 for e in deseado["elements"] if int(e.get("type") or 0) == mapa.ELEMENTO_TEXTO)
    cuenta = {"equipos": len(objetos), "interfaces": cuantas, "cables": len(deseado["links"]),
              "areas": cajas, "rotulos": rotulos}
    escribir = mapa.que_escribir(actual, deseado, netxms_huella_guardada(comentarios))
    banderas = netxms_mapa_banderas(objeto)
    if not escribir["dibujo"] and not escribir["huella"] and banderas is None:
        return {"ops": [], "pendientes": faltan, "motivo": escribir["motivo"], **cuenta}
    ops = []
    if escribir["dibujo"]:
        ops.append({
            "cmd": netxms_mapa_escribir_cmd(api, id_mapa),
            "cuerpo": mapa.cuerpo(deseado),
            "effect": (f"colocar el mapa {lab.get('lab')} como el plano: "
                       f"{len(objetos)} equipos, {len(deseado['links'])} cables y "
                       f"{cajas} áreas"),
        })
    if escribir["huella"]:
        # Va en su propia petición porque el API no admite el comentario en el `PUT` del
        # dibujo; cuando el dibujo ya es el del plano, es la única que se manda.
        #
        # `PATCH` y no `PUT`: el API documenta el `PUT` para tocar un objeto, pero el
        # servicio en pie responde 405 y no escribe nada —ni el comentario ni las
        # banderas—. Comprobado contra el servicio de verdad, con el mapa del laboratorio.
        ops.append({
            "cmd": netxms_cmd(api, f"/objects/{int(id_mapa)}", "PATCH"),
            "cuerpo": json.dumps({"comments": f"{netxms_marca_de(str(lab.get('lab') or ''))} "
                                             f"{HUELLA_EN_EL_MAPA}{mapa.huella(deseado)}"}),
            "effect": "dejar en el mapa la huella de lo que el motor escribió",
        })
    if banderas is not None:
        ops.append({
            "cmd": netxms_cmd(api, f"/objects/{int(id_mapa)}", "PATCH"),
            "cuerpo": json.dumps(banderas),
            "effect": "encender en el mapa el marco y el fondo de estado",
        })
    return {
        "motivo": ("encender el marco y el fondo de estado"
                   if not escribir["dibujo"] and not escribir["huella"] else escribir["motivo"]),
        "ops": ops,
        "pendientes": faltan, **cuenta,
    }
