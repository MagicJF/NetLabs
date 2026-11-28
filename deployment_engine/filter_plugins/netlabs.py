# PROPÓSITO:   el puente entre Ansible y la capa pura. Un solo sitio donde el motor
#              expone lo calculado (plan, cuerpo de creación, llamadas REST) para que
#              las tareas no tengan lógica escondida en Jinja.
# INVARIANTES: ningún filtro habla con la red. Lo que hace es traducir datos.
# VER:         deployment_engine/tools/identity.py, deployment_engine/tools/converge.py

from __future__ import annotations

import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "tools"))

import converge  # noqa: E402
import identity  # noqa: E402


def netlabs_con_config(mundo: dict, configuraciones: dict) -> dict:
    """Pega a cada invitado los recursos ESCRITOS en su config.

    `configuraciones` viene de `tasks/guest_config.yml`: {vmid: {cores, memory(MB)}}. Un
    invitado sin config leído se queda con lo que dice el clúster, que para uno parado
    es lo mismo y para uno en marcha puede no serlo: por eso el plan prefiere
    `config_*` cuando está.
    """
    salida = dict(mundo)
    salida["invitados"] = []
    for invitado in mundo.get("invitados") or []:
        dato = (configuraciones or {}).get(str(invitado.get("vmid"))) or {}
        nuevo = dict(invitado)
        if dato:
            nuevo["config_cores"] = int(dato.get("cores") or invitado.get("cores") or 1)
            nuevo["config_memory"] = int(dato.get("memory") or 0)
            # Las tarjetas se leen del mismo config: sin ellas, un invitado que ya
            # existía conserva las de antes y la configuración nueva le habla a una
            # interfaz que no es la que cree. Sólo se pega lo que se leyó; un invitado
            # sin config no se inventa tarjetas.
            if "net" in dato:
                nuevo["config_interfaces"] = dato["net"]
        salida["invitados"].append(nuevo)
    return salida


def netlabs_direcciones_vivas(invitados, espacio: str) -> list:
    """Las direcciones de gestión que hoy tienen los invitados del clúster.

    Sirve para distinguir un resto de un despliegue anterior —su dirección ya no la tiene
    nadie— de un equipo de otro laboratorio en marcha, que se llama igual y no se toca.

    Sólo se derivan las de los invitados que pueden tener dirección en este plano: el
    clúster puede tener máquinas que no son del motor (un `vmid` por encima de los que
    caben en el /16), y preguntarles la suya lanzaría y dejaría el laboratorio sin
    registrar por un invitado que no tiene nada que ver.
    """
    return [str(identity.derive_management(int(g["vmid"]), espacio))
            for g in invitados or []
            if g.get("vmid") and identity.cabe_management(int(g["vmid"]), espacio)]


def _world(resources, networks, pools):
    invitados = [
        {
            "vmid": int(item["vmid"]),
            "name": item.get("name"),
            "type": "lxc" if item.get("type") == "lxc" else "qemu",
            "pool": item.get("pool") or "",
            "status": item.get("status"),
            # Lo que el invitado tiene EN MARCHA. No es lo que hay escrito en su
            # config: a una máquina encendida se le cambia la memoria en el config y
            # sigue con la vieja hasta reiniciar. `netlabs_con_config` añade después los
            # valores escritos, que son los que compara el plan; esto queda de respaldo
            # para cuando el config no se pudo leer.
            "cores": item.get("maxcpu"),
            "memory_bytes": item.get("maxmem"),
            "node": item.get("node"),
        }
        for item in resources
        if item.get("type") in ("qemu", "lxc") and item.get("vmid") is not None
    ]
    bridges = [
        {
            "iface": item.get("iface"),
            "type": item.get("type"),
            "cidr": item.get("cidr"),
            # El puente de una salida lleva dirección y máscara —es la puerta que ve
            # el router desde su pata—: se conservan para que el plan pueda comprobar
            # que siguen siendo las suyas y reapuntarlas si el tramo cambió.
            "address": item.get("address"),
            "netmask": item.get("netmask"),
            "comments": item.get("comments") or "",
        }
        for item in networks
    ]
    return {
        "node": None,
        "used_vmids": sorted({g["vmid"] for g in invitados}),
        "invitados": invitados,
        "bridges": bridges,
        "pools": sorted(p.get("poolid") for p in pools if p.get("poolid")),
    }


def _create_body(node, env, pool, ssh_public_key=None):
    """El cuerpo de la API para hacer nacer un invitado, en un solo sitio.

    Se decide una vez y sólo al crear: el bus del disco, el agente y la consola
    serie no se cambian en caliente sin rehacer el invitado, así que fingir que se
    convergen sería mentir en el segundo `apply`.
    """
    body = {
        "vmid": node["vmid"],
        "cores": node["cores"],
        "memory": node["memory"],
        "description": node["description"],
        "pool": pool,
    }
    if node["guest"] == "lxc":
        body.update({
            "hostname": node["name"],
            "ostemplate": env["proxmox"]["template_lxc"],
            "rootfs": f"{env['proxmox']['storage_guests']}:{node['disk']}",
            "unprivileged": 1,
            "features": "nesting=1",
            "swap": 0,
            "cmode": "shell",
        })
        if ssh_public_key:
            body["ssh-public-keys"] = ssh_public_key
        for iface in node["interfaces"]:
            valor = f"name=eth{iface['index']},bridge={iface['bridge']},hwaddr={iface['mac']}"
            if iface.get("address"):
                valor += f",ip={iface['address']},gw={iface['gateway']}"
            else:
                valor += ",ip=dhcp"
            body[f"net{iface['index']}"] = valor
    else:
        body.update({
            "name": node["name"],
            "agent": 1,
            "serial0": "socket",
            "vga": "serial0",
            "ostype": "l26",
            "scsihw": "virtio-scsi-single",
            # El CHR no arranca con el disco en virtio-scsi (medido): SATA.
            "sata0": (f"{env['proxmox']['storage_guests']}:0,"
                      f"import-from={env['proxmox']['storage']}:import/{node['image']}"),
            "bootdisk": "sata0",
        })
        for iface in node["interfaces"]:
            body[f"net{iface['index']}"] = f"virtio={iface['mac']},bridge={iface['bridge']}"
    return body


def _create_command(node, env):
    """El comando que ejecuta el arranque: la ruta del fichero, no su texto.

    Medido: el agente de un CHR ejecuta por RUTA. Un `command` con el script pegado
    no hace nada; el fichero escrito antes sí.
    """
    return f"/netlabs-boot-{node['vmid']}.rsc"


class FilterModule:
    def filters(self):
        return {
            "netlabs_world": _world,
            "netlabs_con_config": netlabs_con_config,
            "netlabs_direcciones_vivas": netlabs_direcciones_vivas,
            "netlabs_plan": lambda world, lab, env: identity.plan(world, lab, env),
            "netlabs_site": lambda world, env: identity.site(world, env),
            "netlabs_docs": lambda lab, env: identity.render_docs(lab, env),
            "netlabs_create_body": _create_body,
            "netlabs_bootstrap": lambda node, env, secret: converge.bootstrap_script(node, env, secret),
            "netlabs_bootstrap_path": lambda node: _create_command(node, None),
            "netlabs_ros_reads": lambda node: list(converge.ROS_READS),
            "netlabs_ros_clave": lambda node, secrets: converge.ros_clave(node, secrets),
            "netlabs_secreto": lambda secrets, nombre: converge.secreto(secrets, nombre),
            "netlabs_ros_ops": lambda node, current, secret, secrets=None, cidr=None, observabilidad=None: converge.ros_ops(node, current, secret, secrets, cidr, observabilidad),
            "netlabs_linux_ops": lambda node, current, credenciales=None: converge.linux_ops(node, current, credenciales),
            "netlabs_linux_probe": lambda node: converge.linux_probe(node),
            "netlabs_linux_probe_cmd": lambda node: converge.linux_probe_cmd(node),
            "netlabs_linux_access_cmd": lambda publica, clave: converge.linux_access_cmd(publica, clave),
            "netlabs_linux_state": lambda text: converge.linux_state(text),
            "netlabs_rutas_ops": lambda actuales, deseadas, espacios: converge.rutas_ops(
                actuales, deseadas, espacios),
            "netlabs_cruce_cmd": lambda cruce: converge.cruce_cmd(cruce),
            "netlabs_tunnel_port": lambda vmid: identity.tunnel_port(int(vmid)),
            # La quinta vía: el registro de los equipos en lo que observa el sitio.
            "netlabs_netxms_login_cmd": lambda api: converge.netxms_login_cmd(api),
            "netlabs_netxms_login_cuerpo": lambda usuario, clave: converge.netxms_login_cuerpo(usuario, clave),
            "netlabs_netxms_censo_cmd": lambda api: converge.netxms_censo_cmd(api),
            "netlabs_netxms_censo_cuerpo": lambda api=None: converge.netxms_censo_cuerpo(),
            "netlabs_netxms_fichas_cmd": lambda api: converge.netxms_fichas_cmd(api),
            "netlabs_netxms_fichas_cuerpo": lambda ids=None, api=None: converge.netxms_fichas_cuerpo(ids),
            "netlabs_netxms_ids": lambda nodes, encontrados: converge.netxms_ids(nodes, encontrados),
            "netlabs_netxms_ops": lambda nodes, encontrados, detalles, api, secrets=None,
                vivas=None, propias=None, observabilidad=None: converge.netxms_ops(
                    nodes, encontrados, detalles, api, secrets, vivas=vivas, propias=propias,
                    observabilidad=observabilidad),
            "netlabs_netxms_objeto_cmd": lambda api, id_objeto:
                converge.netxms_objeto_cmd(api, id_objeto),
            "netlabs_netxms_borrar_cmd": lambda api, id_objeto:
                converge.netxms_borrar_cmd(api, id_objeto),
            # La configuración del propio servicio: la escucha de registros se declara en el
            # entorno y el motor la deja puesta, reiniciando sólo si de verdad hace falta.
            "netlabs_netxms_configs_cmd": lambda api: converge.netxms_configs_cmd(api),
            "netlabs_netxms_registro_ops": lambda declarado, actuales, api, escuchando=None:
                converge.netxms_registro_ops(declarado, actuales, api, escuchando),
            "netlabs_netxms_reinicio_cmd": lambda _=None: converge.netxms_reinicio_cmd(),
            # El mapa a medida: el del laboratorio, colocado como el plano.
            "netlabs_netxms_raices_cmd": lambda api: converge.netxms_raices_cmd(api),
            "netlabs_netxms_hijos_cmd": lambda api, id_objeto:
                converge.netxms_hijos_cmd(api, id_objeto),
            "netlabs_netxms_raiz_de_mapas": lambda raices: converge.netxms_raiz_de_mapas(raices),
            "netlabs_netxms_mapa_del_lab": lambda hijos, lab, nombre=None:
                converge.netxms_mapa_del_lab(hijos, lab, nombre),
            "netlabs_netxms_mapa_crear_cuerpo": lambda lab, raiz:
                converge.netxms_mapa_crear_cuerpo(lab, raiz),
            "netlabs_netxms_marca_de": lambda lab: converge.netxms_marca_de(lab),
            "netlabs_netxms_restos_de": lambda nodos, lab, equipos=None, espacios=None:
                converge.netxms_restos_de(nodos, lab, equipos, espacios),
            "netlabs_netxms_mapa_crear_cmd": lambda api: converge.netxms_mapa_crear_cmd(api),
            "netlabs_netxms_mapa_leer_cmd": lambda api, id_mapa:
                converge.netxms_mapa_leer_cmd(api, id_mapa),
            "netlabs_netxms_interfaces_cmd": lambda api: converge.netxms_interfaces_cmd(api),
            # El marcador limpio: las alarmas de los equipos del laboratorio, resueltas.
            "netlabs_netxms_alarmas_cmd": lambda api: converge.netxms_alarmas_cmd(api),
            "netlabs_netxms_alarmas_propias": lambda alarmas, ids:
                converge.netxms_alarmas_propias(alarmas, ids),
            "netlabs_netxms_propios": lambda nodes, censo:
                converge.netxms_propios_de(nodes, censo),
            "netlabs_netxms_alarma_resolver_cmd": lambda api, id_alarma:
                converge.netxms_alarma_resolver_cmd(api, id_alarma),
            "netlabs_netxms_interfaces_cuerpo": lambda api=None: converge.netxms_interfaces_cuerpo(),
            "netlabs_netxms_mapa_ops": lambda lab, nodes, encontrados, actual, api, id_mapa,
                fichas=None, interfaces=None, comentarios="", objeto=None: converge.netxms_mapa_ops(
                    lab, nodes, encontrados, actual, api, id_mapa, fichas, interfaces,
                    comentarios=comentarios, objeto=objeto),
        }
