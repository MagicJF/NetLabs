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


def _world(resources, networks, pools):
    guests = [
        {
            "vmid": int(item["vmid"]),
            "name": item.get("name"),
            "type": "lxc" if item.get("type") == "lxc" else "qemu",
            "pool": item.get("pool") or "",
            "description": item.get("description") or "",
            "status": item.get("status"),
        }
        for item in resources
        if item.get("type") in ("qemu", "lxc") and item.get("vmid") is not None
    ]
    bridges = [
        {
            "iface": item.get("iface"),
            "type": item.get("type"),
            "cidr": item.get("cidr"),
            "comments": item.get("comments") or "",
        }
        for item in networks
    ]
    return {
        "node": None,
        "used_vmids": sorted({g["vmid"] for g in guests}),
        "guests": guests,
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
        "tags": "netlabs",
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
            "netlabs_plan": lambda world, lab, env: identity.plan(world, lab, env),
            "netlabs_site": lambda world, env: identity.site(world, env),
            "netlabs_docs": lambda lab, env: identity.render_docs(lab, env),
            "netlabs_create_body": _create_body,
            "netlabs_bootstrap": lambda node, env, secret: converge.bootstrap_script(node, env, secret),
            "netlabs_bootstrap_path": lambda node: _create_command(node, None),
            "netlabs_ros_reads": lambda node: list(converge.ROS_READS),
            "netlabs_ros_ops": lambda node, current, secret: converge.ros_ops(node, current, secret),
            "netlabs_linux_ops": lambda node, hostname: converge.linux_ops(node, hostname),
            "netlabs_tunnel_port": lambda vmid: identity.tunnel_port(int(vmid)),
        }
