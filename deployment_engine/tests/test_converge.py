# PROPÓSITO:   las pruebas de la capa pura del arranque: qué interfaz se llama qué
#              cuando el router nace. Se inventan el nodo y el entorno, sin hipervisor.
# INVARIANTES: ninguna prueba habla con la API ni escribe en el repositorio.
#              Cada caso fija el MOTIVO: la pata de gestión es la que no tiene red.
# VER:         deployment_engine/tools/converge.py

import json
import pathlib
import sys
import unittest

import yaml

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ / "deployment_engine" / "tools"))

import converge  # noqa: E402
import mapa  # noqa: E402
from identity import LabError  # noqa: E402


def entorno():
    return yaml.safe_load((RAIZ / "netlabs.yml").read_text())


def router(dos_redes=True):
    """Un nodo de red con sus patas: las de laboratorio y la de gestión, la última."""
    interfaces = []
    if dos_redes:
        interfaces = [
            {"index": 0, "network": "lan1", "bridge": "b_rte1p1_wsp1p1"},
            {"index": 1, "network": "lan2", "bridge": "b_rte1p2_wsp2p1"},
        ]
    interfaces.append({"index": len(interfaces), "network": None, "bridge": "vmbr30"})
    return {
        "role": "rte1",
        "name": "rte1",
        "type": "router",
        "mgmt_address": "10.30.0.111",
        "interfaces": interfaces,
        "networks": [i["network"] for i in interfaces if i["network"] is not None],
    }


class Interfaces(unittest.TestCase):
    def test_la_pata_de_gestion_es_la_ultima_creada(self):
        # Con dos redes de laboratorio el motor crea net0, net1 y net2; la de
        # gestión es net2, o sea ether3. Contar `networks` daría ether2 y la
        # dirección acabaría en una red de laboratorio.
        self.assertEqual(converge.management_interface(router()), "ether3")

    def test_una_sola_red_de_laboratorio_da_ether2(self):
        self.assertEqual(converge.management_interface(router(dos_redes=False)), "ether1")

    def test_sin_pata_de_gestion_se_para(self):
        nodo = router()
        nodo["interfaces"] = [i for i in nodo["interfaces"] if i["network"] is not None]
        with self.assertRaises(converge.LabError):
            converge.management_interface(nodo)

    def test_el_script_pone_la_direccion_en_la_pata_de_gestion(self):
        script = converge.bootstrap_script(router(), entorno(), "clave")
        self.assertIn("interface=ether3", script)
        self.assertNotIn("interface=ether2", script)

    def test_una_red_de_laboratorio_se_nombra_desde_uno(self):
        # `net0` de la API es `ether1` del router. Contar desde cero daría ether0,
        # que no existe y hace que la dirección se escriba en ninguna interfaz.
        self.assertEqual(converge.interface_of(router(), "lan1"), "ether1")
        self.assertEqual(converge.interface_of(router(), "lan2"), "ether2")

    def test_una_red_que_el_nodo_no_tiene_no_inventa_pata(self):
        self.assertIsNone(converge.interface_of(router(), "lan3"))


def nodo_router(dos_redes=True):
    return router(dos_redes)


class LaDiferencia(unittest.TestCase):
    def test_una_direccion_que_falta_se_escribe_en_su_pata(self):
        nodo = nodo_router()
        nodo["configure"] = {"addresses": [{"network": "lan1", "address": "10.44.1.1/24"}]}
        ops = converge.ros_ops(nodo, {"addresses": []}, "clave")
        direcciones = [o for o in ops if o["path"] == "/rest/ip/address"]
        self.assertEqual(len(direcciones), 1)
        self.assertEqual(direcciones[0]["method"], "PUT")
        self.assertEqual(direcciones[0]["body"]["interface"], "ether1")

    def test_un_servicio_que_no_existe_se_dice_y_no_se_inventa(self):
        nodo = nodo_router()
        nodo["configure"] = {"services": {"wsss": True}}
        with self.assertRaisesRegex(converge.LabError, "wsss"):
            converge.ros_ops(nodo, {"services": [{"name": "www", ".id": "*1"}]}, "clave")

    def test_un_servicio_apagado_se_enciende_por_su_id(self):
        nodo = nodo_router()
        nodo["configure"] = {"services": {"www": True}}
        ops = converge.ros_ops(nodo, {"identity": {"name": "rte1"},
                                      "services": [{"name": "www", ".id": "*2", "disabled": "true"}]}, "clave")
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["method"], "PATCH")
        self.assertEqual(ops[0]["path"], "/rest/ip/service/*2")


class LasReservasDeLosNodosFinales(unittest.TestCase):
    def nodo(self):
        return {
            "role": "rte1", "name": "rte1", "type": "router",
            "interfaces": [{"index": 0, "network": "lan1",
                            "bridge": "b_rte1p1_wsp1p1"}],
            "networks": [{"name": "lan1", "address": "10.44.1.0/24"}],
            "configure": {"dhcp_server": [{
                "network": "lan1", "pool": "10.44.1.100-10.44.1.199",
                "gateway": "10.44.1.1",
                "leases": [{"address": "10.44.1.50", "role": "wsp1",
                            "mac": "BC:24:11:00:00:01"}],
            }]},
        }

    def test_una_reserva_que_falta_se_crea_en_el_servidor(self):
        ops = converge.ros_ops(self.nodo(), {"pools": [], "dhcp_servers": [],
                                             "dhcp_networks": [], "dhcp_leases": []}, "clave")
        reservas = [o for o in ops if o["path"] == "/rest/ip/dhcp-server/lease"]
        self.assertEqual(len(reservas), 1)
        self.assertEqual(reservas[0]["method"], "PUT")
        self.assertEqual(reservas[0]["body"]["address"], "10.44.1.50")
        self.assertEqual(reservas[0]["body"]["mac-address"], "BC:24:11:00:00:01")
        self.assertEqual(reservas[0]["body"]["server"], "netlabs-lan1")
        self.assertIn("reserva 10.44.1.50", reservas[0]["effect"])

    def test_una_reserva_que_ya_esta_no_se_reescribe(self):
        current = {
            "identity": {"name": "rte1"},
            "pools": [{"name": "netlabs-lan1", "ranges": "10.44.1.100-10.44.1.199"}],
            "dhcp_servers": [{"name": "netlabs-lan1", "interface": "ether1",
                              "address-pool": "netlabs-lan1", ".id": "*1"}],
            "dhcp_networks": [{"address": "10.44.1.0/24", "gateway": "10.44.1.1", ".id": "*2"}],
            "dhcp_leases": [{"address": "10.44.1.50", "mac-address": "BC:24:11:00:00:01",
                             "server": "netlabs-lan1", "comment": "netlabs-reserva-wsp1",
                             ".id": "*3"}],
        }
        self.assertEqual(converge.ros_ops(self.nodo(), current, "clave"), [])

    def test_una_reserva_que_sobra_se_retira(self):
        current = {
            "pools": [], "dhcp_servers": [], "dhcp_networks": [],
            "dhcp_leases": [{"address": "10.44.1.99", "comment": "netlabs-reserva-wsp9",
                             ".id": "*4"}],
        }
        nodo = self.nodo()
        nodo["configure"]["dhcp_server"][0].pop("leases")
        ops = converge.ros_ops(nodo, current, "clave")
        borradas = [o for o in ops if o["path"] == "/rest/ip/dhcp-server/lease/*4"]
        self.assertEqual(len(borradas), 1)
        self.assertEqual(borradas[0]["method"], "DELETE")


class LaPuertaQueAnunciaElServidor(unittest.TestCase):
    def test_la_puerta_es_la_del_router_aunque_el_servidor_no_la_repita(self):
        # El router vive en .254 y su servidor DHCP no repite la puerta. Anunciar
        # .1 por defecto entregaría como salida una dirección que no enruta: el
        # cliente no puede salir por la dirección de otro. La puerta se deriva de
        # la dirección que el router declara en esa red.
        nodo = {
            "role": "rte1", "name": "rte1", "type": "router",
            "interfaces": [{"index": 0, "network": "lan1", "bridge": "b_rte1p1_wsp1p1"}],
            "networks": [{"name": "lan1", "address": "10.44.1.0/24"}],
            "configure": {
                "addresses": [{"network": "lan1", "address": "10.44.1.254/24"}],
                "dhcp_server": [{"network": "lan1",
                                 "pool": "10.44.1.100-10.44.1.199"}],
            },
        }
        ops = converge.ros_ops(nodo, {"pools": [], "dhcp_servers": [],
                                      "dhcp_networks": [], "dhcp_leases": []}, "clave")
        red = next(o for o in ops if o["path"] == "/rest/ip/dhcp-server/network")
        self.assertEqual(red["body"]["gateway"], "10.44.1.254")


class ElInteriorLinux(unittest.TestCase):
    """Un nodo de control declara su interior: repos, paquetes, ficheros, servicios."""

    def nodo(self, **configure):
        return {"role": "netxms", "name": "netxms", "type": "control", "configure": configure}

    def test_un_fichero_que_coincide_no_se_escribe(self):
        nodo = self.nodo(files=[{"path": "/etc/x.conf", "content": "a=1\n"}])
        huella = converge._sha256("a=1\n")
        ops = converge.linux_ops(nodo, {"hostname": "netxms", "files": {"/etc/x.conf": huella}})
        self.assertEqual(ops, [])

    def test_un_fichero_que_falta_se_escribe(self):
        nodo = self.nodo(files=[{"path": "/etc/x.conf", "content": "a=1\n"}])
        ops = converge.linux_ops(nodo, {"hostname": "netxms", "files": {"/etc/x.conf": "-"}})
        self.assertEqual(len(ops), 1)
        self.assertIn("/etc/x.conf", ops[0]["effect"])
        # El contenido viaja en base64: un `$` o un apóstrofo no rompen el comando.
        self.assertIn("base64 -d", ops[0]["cmd"][2])

    def test_el_sondeo_pregunta_por_los_ficheros_declarados(self):
        nodo = self.nodo(files=[{"path": "/etc/x.conf", "content": "a=1\n"}])
        self.assertIn("/etc/x.conf", converge.linux_probe(nodo))

    def test_el_estado_lee_la_huella_de_cada_fichero(self):
        texto = "FILE:/etc/x.conf:abc123\nFILE:/etc/y.conf:-\n"
        estado = converge.linux_state(texto)
        self.assertEqual(estado["files"]["/etc/x.conf"], "abc123")
        self.assertEqual(estado["files"]["/etc/y.conf"], "-")

    def test_la_puerta_de_root_no_lleva_la_contrasena_en_el_comando(self):
        argv = converge.linux_access_cmd("ssh-ed25519 AAAA prueba", "s3cr3t")
        self.assertEqual(argv[:2], ["sh", "-c"])
        self.assertNotIn("s3cr3t", argv[2])
        self.assertIn('CAMBIO:$cambio', argv[2])
        self.assertIn("PermitRootLogin yes", argv[2])
        self.assertIn("ssh-ed25519 AAAA prueba", argv[2])

    def test_la_puerta_se_niega_sin_contrasena(self):
        with self.assertRaises(converge.LabError):
            converge.linux_access_cmd("ssh-ed25519 AAAA prueba", "")

    def test_el_sondeo_pregunta_solo_por_las_fuentes_declaradas(self):
        # Mirar `/etc/apt/sources.list.d/*.list` leería del huésped fuentes que no son
        # del motor: una con credenciales en la URL viaja en base64, que no la esconde.
        nodo = self.nodo(repositories=[{"name": "netxms", "url": "https://x/y",
                                        "suite": "stable", "components": "main"}])
        sondeo = converge.linux_probe(nodo)
        # Sólo las declaradas: la lista del bucle sale de la declaración.
        self.assertIn("for r in netxms", sondeo)
        self.assertIn("/etc/apt/sources.list.d/$r.list", sondeo)
        self.assertIn("REPO:$r", sondeo)
        self.assertNotIn("sources.list.d/*.list", sondeo)

    def test_una_ruta_con_espacios_va_entrecomillada_en_el_sondeo(self):
        # Sin comillas, el shell parte la ruta en dos palabras, el sondeo no la encuentra
        # y el estado no tiene su clave: cada apply volvería a escribir el fichero.
        nodo = self.nodo(files=[{"path": "/etc/x y/z.conf", "content": "a=1\n"}])
        self.assertIn("'/etc/x y/z.conf'", converge.linux_probe(nodo))

    def test_una_fuente_escrita_sin_indice_actualizado_se_reintenta(self):
        # El `.list` bien escrito no basta: sin el `apt-get update` terminado, un paquete
        # que sólo está en esa fuente no existe para apt. La marca de índice completado es
        # lo que distingue las dos cosas, y sin ella el reintento no ocurriría nunca.
        nodo = self.nodo(repositories=[{"name": "netxms", "url": "https://x/y",
                                        "suite": "stable", "components": "main"}])
        linea = converge._repo_line(nodo["configure"]["repositories"][0])
        actual = {"hostname": "netxms", "repositories": {"netxms": linea + "\n"},
                  "repos_ok": {}}
        ops = converge.linux_ops(nodo, actual)
        self.assertEqual(len(ops), 1)
        self.assertIn("apt-get update", ops[0]["cmd"][2])
        self.assertIn(converge._marca_repo("netxms"), ops[0]["cmd"][2])

    def test_una_fuente_escrita_y_con_el_indice_al_dia_no_se_toca(self):
        nodo = self.nodo(repositories=[{"name": "netxms", "url": "https://x/y",
                                        "suite": "stable", "components": "main"}])
        linea = converge._repo_line(nodo["configure"]["repositories"][0])
        actual = {"hostname": "netxms", "repositories": {"netxms": linea + "\n"},
                  "repos_ok": {"netxms": converge._sha256(linea)}}
        self.assertEqual(converge.linux_ops(nodo, actual), [])

    def test_el_estado_lee_la_marca_de_indice_del_repositorio(self):
        estado = converge.linux_state("REPO:netxms:-\nREPO_OK:netxms:abc\n")
        self.assertEqual(estado["repos_ok"]["netxms"], "abc")

    def test_una_recarga_pendiente_se_reintenta_aunque_el_fichero_coincida(self):
        # Haber escrito el fichero no es que el servicio lo haya releído: si la conexión
        # se cortó antes de `try-restart`, el fichero ya coincide en la pasada siguiente y
        # la unidad se quedaría con la configuración vieja para siempre.
        nodo = self.nodo(files=[{"path": "/etc/x.conf", "content": "a=1\n",
                                 "restart": "x.service"}])
        huella = converge._sha256("a=1\n")
        actual = {"hostname": "netxms", "files": {"/etc/x.conf": huella}, "reloads": {}}
        ops = converge.linux_ops(nodo, actual)
        self.assertEqual(len(ops), 1)
        self.assertIn("try-restart x.service", ops[0]["cmd"][2])
        self.assertIn(converge._marca_recarga("/etc/x.conf"), ops[0]["cmd"][2])

    def test_una_recarga_ya_hecha_no_escribe(self):
        nodo = self.nodo(files=[{"path": "/etc/x.conf", "content": "a=1\n",
                                 "restart": "x.service"}])
        huella = converge._sha256("a=1\n")
        actual = {"hostname": "netxms", "files": {"/etc/x.conf": huella},
                  "reloads": {"/etc/x.conf": huella}}
        self.assertEqual(converge.linux_ops(nodo, actual), [])

    def test_los_ficheros_van_antes_que_los_servicios(self):
        nodo = self.nodo(
            files=[{"path": "/etc/x.conf", "content": "a=1\n"}],
            services={"x": True},
        )
        ops = converge.linux_ops(nodo, {"hostname": "netxms", "files": {}, "services": {"x": "inactive"}})
        self.assertEqual(len(ops), 2)
        self.assertIn("fichero", ops[0]["effect"])
        self.assertIn("servicio", ops[1]["effect"])

    def test_un_comando_sin_marca_se_ejecuta_y_con_marca_no(self):
        nodo = self.nodo(commands=[{"run": "x init", "creates": "/var/lib/x/stamp"}])
        ops = converge.linux_ops(nodo, {"hostname": "netxms", "commands": {}})
        self.assertEqual(len(ops), 1)
        self.assertIn("comando", ops[0]["effect"])
        self.assertEqual(converge.linux_ops(nodo, {"hostname": "netxms", "commands": {"/var/lib/x/stamp": True}}), [])

    def test_el_fichero_va_antes_que_el_comando(self):
        # Un comando de inicialización lee su configuración: si el fichero aún no
        # está escrito, arranca con la vieja o falla. El orden no es cosmético.
        nodo = self.nodo(
            files=[{"path": "/etc/x.conf", "content": "a=1\n"}],
            commands=[{"run": "x init", "creates": "/var/lib/x/stamp"}],
        )
        ops = converge.linux_ops(nodo, {"hostname": "netxms", "files": {}, "commands": {}})
        self.assertEqual([o["effect"].split()[0] for o in ops], ["fichero", "comando:"])

    def test_el_comando_va_antes_que_el_servicio(self):
        nodo = self.nodo(
            commands=[{"run": "x init", "creates": "/var/lib/x/stamp"}],
            services={"x": True},
        )
        ops = converge.linux_ops(nodo, {"hostname": "netxms", "commands": {}, "services": {"x": "inactive"}})
        self.assertEqual([o["effect"].split()[0] for o in ops], ["comando:", "servicio"])

    def test_una_credencial_se_converge_por_la_huella_de_la_clave(self):
        # La clave nunca viaja en el comando: se lee de secrets.yml por su
        # nombre y lo que se compara con la marca es su sha256.
        nodo = self.nodo(commands=[{
            "run": "cambiar admin", "stamp": "/var/lib/x/clave", "secret": "netxms",
        }])
        credenciales = {"netxms": {"usuario": "admin", "clave": "s3cr3t"}}
        ops = converge.linux_ops(nodo, {"hostname": "netxms", "stamps": {}}, credenciales)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["secret"], "netxms")
        self.assertIn("credencial netxms", ops[0]["effect"])
        self.assertNotIn("s3cr3t", ops[0]["cmd"][2])
        huella = __import__("hashlib").sha256(b"s3cr3t").hexdigest()
        self.assertIn(huella, ops[0]["cmd"][2])

    def test_la_credencial_ya_aplicada_no_escribe(self):
        nodo = self.nodo(commands=[{
            "run": "cambiar admin", "stamp": "/var/lib/x/clave", "secret": "netxms",
        }])
        huella = __import__("hashlib").sha256(b"s3cr3t").hexdigest()
        credenciales = {"netxms": {"usuario": "admin", "clave": "s3cr3t"}}
        self.assertEqual(
            converge.linux_ops(nodo, {"hostname": "netxms", "stamps": {"/var/lib/x/clave": huella}}, credenciales),
            [],
        )

    def test_una_credencial_que_no_esta_en_secrets_es_un_fallo(self):
        nodo = self.nodo(commands=[{
            "run": "cambiar admin", "stamp": "/var/lib/x/clave", "secret": "netxms",
        }])
        with self.assertRaises(converge.LabError):
            converge.linux_ops(nodo, {"hostname": "netxms", "stamps": {}}, {})

    def test_un_servicio_que_arranca_se_reinicia_no_solo_se_arranca(self):
        nodo = self.nodo(services={"x": True})
        ops = converge.linux_ops(nodo, {"hostname": "netxms", "services": {"x": "activating"}})
        self.assertEqual(len(ops), 1)
        # `restart` relee la configuración; `start` no, y el servicio se queda
        # en bucle de reinicio con la configuración vieja.
        self.assertIn("systemctl restart x", ops[0]["cmd"][2])

    def test_el_contenido_igual_con_los_permisos_cambiados_se_corrige(self):
        # El contenido y el modo son cosas distintas: un fichero con el texto bueno
        # pero sin el bit de ejecución estaba "bien" y nunca se corregía.
        nodo = self.nodo(files=[{"path": "/usr/local/bin/x", "content": "#!/bin/sh\n", "mode": "0755"}])
        huella = converge._sha256("#!/bin/sh\n")
        ops = converge.linux_ops(nodo, {"hostname": "netxms",
                                        "files": {"/usr/local/bin/x": huella},
                                        "modes": {"/usr/local/bin/x": "644"}})
        self.assertEqual(len(ops), 1)
        self.assertIn("chmod 0755", ops[0]["cmd"][2])

    def test_el_mismo_contenido_y_los_mismos_permisos_no_escriben(self):
        nodo = self.nodo(files=[{"path": "/usr/local/bin/x", "content": "#!/bin/sh\n", "mode": "0755"}])
        huella = converge._sha256("#!/bin/sh\n")
        self.assertEqual(
            converge.linux_ops(nodo, {"hostname": "netxms",
                                      "files": {"/usr/local/bin/x": huella},
                                      "modes": {"/usr/local/bin/x": "755"}}),
            [],
        )

    def test_el_estado_lee_los_permisos_de_cada_fichero(self):
        estado = converge.linux_state("MODE:/usr/local/bin/x:755\n")
        self.assertEqual(estado["modes"]["/usr/local/bin/x"], "755")

    def test_el_estado_lee_si_el_servicio_arranca_al_iniciar(self):
        estado = converge.linux_state("SVC:x:active\nSVC_ENABLED:x:enabled\n")
        self.assertEqual(estado["services"]["x"], "active")
        self.assertEqual(estado["enabled"]["x"], "enabled")

    def test_un_servicio_activo_pero_deshabilitado_se_habilita(self):
        # Activo y arranca-al-iniciar son dos cosas: sin mirar la segunda, un
        # servicio activo pero deshabilitado nunca recibía `enable`.
        nodo = self.nodo(services={"x": True})
        ops = converge.linux_ops(nodo, {"hostname": "netxms",
                                        "services": {"x": "active"},
                                        "enabled": {"x": "disabled"}})
        self.assertEqual(len(ops), 1)
        self.assertIn("systemctl enable x", ops[0]["cmd"][2])

    def test_un_servicio_que_ya_arranca_y_esta_habilitado_no_se_toca(self):
        nodo = self.nodo(services={"x": True})
        self.assertEqual(
            converge.linux_ops(nodo, {"hostname": "netxms",
                                      "services": {"x": "active"},
                                      "enabled": {"x": "enabled"}}),
            [],
        )


class LaClaveDelRouter(unittest.TestCase):
    """El laboratorio nombra la credencial; el valor vive en secrets.yml."""

    def nodo(self, password_from="secrets.clave_del_router"):
        nodo = router()
        nodo["configure"] = {"users": [{"name": "admin", "password_from": password_from}]}
        return nodo

    def test_la_clave_sale_del_nombre_que_declara_el_laboratorio(self):
        # El alias declarado es distinto del predeterminado del sitio, y su valor también:
        # si `ros_clave` ignorara `password_from` y tomara siempre `routeros_clave`,
        # devolvería el del sitio y esta prueba pasaría sin comprobar nada.
        self.assertEqual(
            converge.ros_clave(self.nodo(), {"clave_del_router": "del_lab",
                                             "routeros_clave": "del_sitio"}),
            "del_lab",
        )

    def test_sin_usuarios_declarados_se_usa_la_clave_del_sitio(self):
        self.assertEqual(converge.ros_clave(router(), {"routeros_clave": "s3cr3t"}), "s3cr3t")

    def test_un_nombre_que_no_esta_en_secrets_es_un_fallo_con_el_nombre_delante(self):
        with self.assertRaisesRegex(converge.LabError, "clave_del_router"):
            converge.ros_clave(self.nodo(), {"otra_cosa": "x"})

    def test_una_clave_vacia_no_se_toma_por_buena(self):
        with self.assertRaisesRegex(converge.LabError, "clave_del_router"):
            converge.ros_clave(self.nodo(), {"clave_del_router": ""})


class LaObservabilidadDelRouter(unittest.TestCase):
    """El área `snmp` es del laboratorio: si no está, el motor no toca el servicio.

    Con qué se mira **no** lo es: eso lo declara el entorno, y esta clase prueba la rama
    v2c (la que el P0 deja atrás). La rama v3 tiene su propia clase, `LaIdentidadV3`.
    """

    CIDR = "10.30.0.0/16"
    SECRETOS = {"snmp_comunidad": "lab-ro"}
    OBS = {"snmp": {"version": 2, "credencial_from": "secrets.snmp_comunidad"}}
    AREA = {"enabled": True}

    def nodo(self, area=None):
        nodo = router()
        nodo["configure"] = {} if area is None else {"snmp": area}
        return nodo

    def actual(self, enabled="false", comunidades=None):
        return {
            "identity": {"name": "rte1"},
            "snmp": {"enabled": enabled},
            "snmp_community": comunidades if comunidades is not None else [
                {".id": "*0", "name": "public", "addresses": "::/0",
                 "read-access": "true", "write-access": "false",
                 "authentication-protocol": "MD5", "encryption-protocol": "DES",
                 "security": "none"},
            ],
        }

    def test_sin_area_snmp_el_motor_no_toca_el_servicio(self):
        self.assertEqual(
            converge.ros_ops(self.nodo(), self.actual(), "clave", self.SECRETOS, self.CIDR, self.OBS), []
        )

    def test_enciende_snmp_y_sustituye_la_comunidad_abierta(self):
        ops = converge.ros_ops(self.nodo(self.AREA), self.actual(), "clave",
                               self.SECRETOS, self.CIDR, self.OBS)
        caminos = [(o["method"], o["path"]) for o in ops]
        self.assertIn(("POST", "/rest/snmp/set"), caminos)
        self.assertIn(("PUT", "/rest/snmp/community"), caminos)
        self.assertIn(("PATCH", "/rest/snmp/community/*0"), caminos)
        creada = next(o for o in ops if o["path"] == "/rest/snmp/community")
        self.assertEqual(creada["body"]["addresses"], self.CIDR)
        self.assertEqual(creada["body"]["read-access"], "yes")
        self.assertEqual(creada["body"]["write-access"], "no")
        # La comunidad es v2c: en RouterOS lo decide `security`, no los protocolos de v3.
        self.assertEqual(creada["body"]["security"], "none")
        # Y la de fábrica no se apaga: se acota igual que la del laboratorio, para que quien
        # use la de siempre (NetXMS, `snmpwalk`) entre sin que nadie configure nada.
        acotada = next(o for o in ops if o["path"] == "/rest/snmp/community/*0")
        self.assertEqual(acotada["body"], {"addresses": self.CIDR})
        self.assertNotIn("disabled", acotada["body"])

    def test_la_comunidad_de_fabrica_apagada_se_vuelve_a_encender(self):
        """Un `public` apagado por una configuración anterior deja al cliente ciego."""
        actual = self.actual(enabled="true", comunidades=[
            {".id": "*0", "name": "public", "addresses": "::/0", "disabled": "true",
             "read-access": "true", "write-access": "false", "security": "none"},
        ])
        ops = converge.ros_ops(self.nodo(self.AREA), actual, "clave", self.SECRETOS, self.CIDR, self.OBS)
        acotada = next(o for o in ops if o["path"] == "/rest/snmp/community/*0")
        self.assertEqual(acotada["body"]["disabled"], "no")
        self.assertEqual(acotada["body"]["addresses"], self.CIDR)

    def test_una_comunidad_apagada_a_mano_se_respeta(self):
        """Apagar una comunidad propia es una decisión; el motor no la deshace."""
        actual = self.actual(enabled="true", comunidades=[
            {".id": "*0", "name": "public", "addresses": self.CIDR,
             "read-access": "true", "write-access": "false", "security": "none"},
            {".id": "*2", "name": "clientes", "addresses": "::/0", "disabled": "true",
             "read-access": "true", "write-access": "false", "security": "none"},
        ])
        ops = converge.ros_ops(self.nodo(self.AREA), actual, "clave", self.SECRETOS, self.CIDR, self.OBS)
        self.assertEqual([o["path"] for o in ops if o["path"].startswith("/rest/snmp/community/")],
                         [])

    def test_si_ya_esta_no_escribe_nada(self):
        actual = self.actual(enabled="true", comunidades=[
            {".id": "*1", "name": "lab-ro", "addresses": self.CIDR,
             "read-access": "true", "write-access": "false",
             "authentication-protocol": "MD5", "encryption-protocol": "DES",
             "security": "none"},
        ])
        self.assertEqual(
            converge.ros_ops(self.nodo(self.AREA), actual, "clave", self.SECRETOS, self.CIDR, self.OBS), []
        )

    def test_una_comunidad_abierta_en_v3_se_baja_a_v2c(self):
        """Con `security` distinto de none, RouterOS no atiende la comunidad por v2c."""
        actual = self.actual(enabled="true", comunidades=[
            {".id": "*1", "name": "lab-ro", "addresses": self.CIDR,
             "read-access": "true", "write-access": "false",
             "authentication-protocol": "MD5", "encryption-protocol": "DES",
             "security": "authorized"},
        ])
        ops = converge.ros_ops(self.nodo(self.AREA), actual, "clave", self.SECRETOS, self.CIDR, self.OBS)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["method"], "PATCH")
        self.assertEqual(ops[0]["body"], {"security": "none"})

    def test_una_comunidad_propia_abierta_se_restringe(self):
        actual = self.actual(enabled="true", comunidades=[
            {".id": "*1", "name": "lab-ro", "addresses": "::/0",
             "read-access": "true", "write-access": "true",
             "authentication-protocol": "MD5", "encryption-protocol": "DES",
             "security": "none"},
        ])
        ops = converge.ros_ops(self.nodo(self.AREA), actual, "clave", self.SECRETOS, self.CIDR, self.OBS)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["method"], "PATCH")
        self.assertEqual(ops[0]["body"], {"addresses": self.CIDR, "write-access": "no"})

    def test_el_lab_puede_declararlo_apagado(self):
        ops = converge.ros_ops(self.nodo({"enabled": False}), self.actual(enabled="true"),
                               "clave", self.SECRETOS, self.CIDR, self.OBS)
        self.assertEqual([(o["method"], o["body"]) for o in ops],
                         [("POST", {"enabled": "no"})])

    def test_sin_red_de_gestion_no_se_inventa_una_comunidad_abierta(self):
        with self.assertRaisesRegex(converge.LabError, "red de gestión"):
            converge.ros_ops(self.nodo(self.AREA), self.actual(), "clave", self.SECRETOS, None, self.OBS)

    def test_una_comunidad_que_no_esta_en_secrets_es_un_fallo(self):
        with self.assertRaisesRegex(converge.LabError, "snmp_comunidad"):
            converge.ros_ops(self.nodo(self.AREA), self.actual(), "clave", {}, self.CIDR, self.OBS)

    def test_el_encendido_va_marcado_para_su_propio_paso(self):
        # Encender antes de acotar deja el servicio expuesto mientras se acota. Y no
        # basta con ponerlo el último: una llamada que falla dentro del bucle no detiene
        # los elementos siguientes, así que el encendido llegaría igual con una comunidad
        # abierta. La marca es lo que `ros.yml` usa para partirlo en dos pasos.
        ops = converge.ros_ops(self.nodo(self.AREA), self.actual(), "clave",
                               self.SECRETOS, self.CIDR, self.OBS)
        self.assertEqual((ops[-1]["method"], ops[-1]["path"]), ("POST", "/rest/snmp/set"))
        self.assertTrue(ops[-1]["tras_restricciones"])
        for op in ops[:-1]:
            self.assertNotIn("tras_restricciones", op)

    def test_el_encendido_solo_sale_cuando_hace_falta(self):
        # Con SNMP ya encendido no hay marca ninguna: el paso propio del encendido se
        # queda sin elementos y el segundo apply no escribe.
        ops = converge.ros_ops(self.nodo(self.AREA), self.actual(enabled="true"),
                               "clave", self.SECRETOS, self.CIDR, self.OBS)
        self.assertEqual([o for o in ops if o.get("tras_restricciones")], [])

    def test_el_efecto_de_acotar_una_comunidad_no_lleva_su_nombre(self):
        # El nombre de una comunidad es su valor secreto y el efecto se imprime antes de
        # escribir: se nombra por su id interno, que no es secreto.
        ops = converge.ros_ops(self.nodo(self.AREA), self.actual(), "clave",
                               self.SECRETOS, self.CIDR, self.OBS)
        patch = next(o for o in ops if o["method"] == "PATCH")
        self.assertNotIn("public", patch["effect"])
        self.assertIn("*0", patch["effect"])

    def test_una_comunidad_declarada_apagada_se_vuelve_a_encender(self):
        # La propia es la que el laboratorio declara, y declararla es quererla viva: una
        # rotación, o alguien que la apagó a mano, no la deja fuera para siempre.
        actual = self.actual(enabled="true", comunidades=[
            {".id": "*1", "name": "lab-ro", "addresses": self.CIDR,
             "read-access": "true", "write-access": "false",
             "authentication-protocol": "MD5", "encryption-protocol": "DES",
             "security": "none", "disabled": "true"},
        ])
        ops = converge.ros_ops(self.nodo(self.AREA), actual, "clave", self.SECRETOS, self.CIDR, self.OBS)
        self.assertEqual([(o["method"], o["body"]) for o in ops],
                         [("PATCH", {"disabled": "no"})])


class LaIdentidadV3(unittest.TestCase):
    """Con SNMP v3 declarado en el entorno, el equipo deja de contestar en claro.

    Medido contra un CHR 7.25 desplegado, no deducido de la documentación: en RouterOS la
    identidad v3 **es** una entrada de `/snmp/community` con `security=private` cuyo
    nombre es el usuario de SNMP v3, con `security=none` el equipo sigue contestando por
    v2c, y las claves vuelven al leerlas —por eso la comparación es real y un `apply`
    repetido no escribe.
    """

    CIDR = "10.30.0.0/16"
    V3 = {"usuario": "netlabs-ro", "autenticacion": "SHA256",
          "clave_autenticacion": "clave-de-autenticacion", "cifrado": "AES",
          "clave_cifrado": "clave-de-cifrado"}
    SECRETOS = {"snmp_v3": V3}
    OBS = {"snmp": {"version": 3, "credencial_from": "secrets.snmp_v3"}}
    AREA = {"enabled": True}

    def nodo(self, area=AREA):
        nodo = router()
        nodo["configure"] = {} if area is None else {"snmp": area}
        return nodo

    def actual(self, enabled="false", comunidades=None):
        return {
            "identity": {"name": "rte1"},
            "snmp": {"enabled": enabled},
            "snmp_community": comunidades if comunidades is not None else [
                {".id": "*0", "name": "public", "addresses": "::/0",
                 "read-access": "true", "write-access": "false", "security": "none"},
                {".id": "*1", "name": "netlabs-ro-3feba0cb", "addresses": self.CIDR,
                 "read-access": "true", "write-access": "false", "security": "none"},
            ],
        }

    def la_mia(self, **cambios):
        entrada = {".id": "*2", "name": self.V3["usuario"], "addresses": self.CIDR,
                   "read-access": "true", "write-access": "false", "security": "private",
                   "authentication-protocol": self.V3["autenticacion"],
                   "authentication-password": self.V3["clave_autenticacion"],
                   "encryption-protocol": self.V3["cifrado"],
                   "encryption-password": self.V3["clave_cifrado"]}
        entrada.update(cambios)
        return entrada

    def ops(self, actual=None, secretos=None, area=AREA, cidr=CIDR):
        return converge.ros_ops(self.nodo(area), actual or self.actual(), "clave",
                                self.SECRETOS if secretos is None else secretos, cidr, self.OBS)

    def test_crea_la_identidad_v3_y_apaga_el_claro(self):
        ops = self.ops()
        caminos = [(o["method"], o["path"]) for o in ops]
        self.assertIn(("PUT", "/rest/snmp/community"), caminos)
        # Las dos v2c se apagan: la de fábrica y la que quedó de la etapa anterior.
        self.assertEqual([o["path"] for o in ops if o["method"] == "PATCH"],
                         ["/rest/snmp/community/*0", "/rest/snmp/community/*1"])
        for op in ops:
            if op["method"] == "PATCH":
                self.assertEqual(op["body"], {"disabled": "yes"})
        creada = next(o for o in ops if o["path"] == "/rest/snmp/community")
        self.assertEqual(creada["body"]["name"], self.V3["usuario"])
        self.assertEqual(creada["body"]["security"], "private")
        self.assertEqual(creada["body"]["authentication-protocol"], "SHA256")
        self.assertEqual(creada["body"]["encryption-protocol"], "AES")
        self.assertEqual(creada["body"]["authentication-password"], self.V3["clave_autenticacion"])
        self.assertEqual(creada["body"]["encryption-password"], self.V3["clave_cifrado"])
        self.assertEqual(creada["body"]["addresses"], self.CIDR)
        self.assertEqual(creada["body"]["write-access"], "no")
        self.assertEqual((ops[-1]["method"], ops[-1]["path"]), ("POST", "/rest/snmp/set"))
        self.assertTrue(ops[-1]["tras_restricciones"])

    def test_con_v3_puesto_y_las_v2c_apagadas_no_escribe_nada(self):
        actual = self.actual(enabled="true", comunidades=[
            self.la_mia(),
            {".id": "*0", "name": "public", "addresses": self.CIDR, "disabled": "true",
             "read-access": "true", "write-access": "false", "security": "none"},
        ])
        self.assertEqual(self.ops(actual), [])

    def test_al_rotar_una_clave_solo_cambia_esa_clave(self):
        actual = self.actual(enabled="true", comunidades=[
            self.la_mia(**{"authentication-password": "la-vieja-y-mas-larga"}),
        ])
        ops = self.ops(actual)
        self.assertEqual([(o["method"], o["body"]) for o in ops],
                         [("PATCH", {"authentication-password": self.V3["clave_autenticacion"]})])

    def test_una_entrada_sin_cifrado_se_completa(self):
        """Una identidad con autenticación pero sin cifrado (`authorized`) sube a `private`."""
        actual = self.actual(enabled="true", comunidades=[
            self.la_mia(**{"security": "authorized", "encryption-protocol": "DES",
                           "encryption-password": ""}),
        ])
        ops = self.ops(actual)
        self.assertEqual(ops[0]["method"], "PATCH")
        self.assertEqual(ops[0]["body"]["security"], "private")
        self.assertEqual(ops[0]["body"]["encryption-password"], self.V3["clave_cifrado"])
        self.assertEqual(ops[0]["body"]["encryption-protocol"], "AES")

    def test_sin_observabilidad_en_el_entorno_se_dice(self):
        with self.assertRaisesRegex(converge.LabError, "observabilidad.snmp"):
            converge.ros_ops(self.nodo(self.AREA), self.actual(), "clave",
                             self.SECRETOS, self.CIDR, None)

    def test_un_protocolo_que_el_equipo_no_admite_se_dice(self):
        for campo, valor, en_el_mensaje in (("autenticacion", "SHA999", "SHA256"),
                                            ("cifrado", "AES256", "AES")):
            with self.assertRaisesRegex(converge.LabError, en_el_mensaje):
                self.ops(secretos={"snmp_v3": {**self.V3, campo: valor}})

    def test_una_clave_de_menos_de_ocho_caracteres_se_dice(self):
        with self.assertRaisesRegex(converge.LabError, "8 caracteres"):
            self.ops(secretos={"snmp_v3": {**self.V3, "clave_cifrado": "corta"}})

    def test_sin_la_credencial_en_secrets_es_un_fallo(self):
        with self.assertRaisesRegex(converge.LabError, "snmp_v3"):
            self.ops(secretos={})

    def test_el_lab_puede_declararlo_apagado_tambien_con_v3(self):
        ops = self.ops(actual=self.actual(enabled="true"), area={"enabled": False})
        self.assertEqual([(o["method"], o["body"]) for o in ops],
                         [("POST", {"enabled": "no"})])

    def test_el_efecto_no_lleva_el_nombre_de_la_entrada_ni_las_claves(self):
        # El efecto se imprime antes de escribir: ni el nombre (que es el usuario) ni las
        # claves pueden aparecer en él.
        for op in self.ops():
            efecto = op["effect"]
            self.assertNotIn(self.V3["clave_autenticacion"], efecto)
            self.assertNotIn(self.V3["clave_cifrado"], efecto)


class ElSwitchConmuta(unittest.TestCase):
    """El switch mete sus patas de laboratorio en un puente y deja fuera la de gestión."""

    def nodo(self):
        return {
            "role": "swc1", "name": "swc1", "type": "switch",
            "networks": [{"name": "lan"}, {"name": "lan"}],
            "interfaces": [
                {"index": 0, "network": "lan"},
                {"index": 1, "network": "lan"},
                {"index": 2, "network": None},
            ],
            "configure": {},
        }

    def test_crea_el_puente_y_mete_solo_las_patas_de_laboratorio(self):
        ops = converge.ros_ops(self.nodo(), {"identity": {"name": "swc1"},
                                            "bridges": [], "bridge_ports": []}, "clave", {}, None)
        self.assertEqual([(o["method"], o["path"]) for o in ops], [
            ("PUT", "/rest/interface/bridge"),
            ("PUT", "/rest/interface/bridge/port"),
            ("PUT", "/rest/interface/bridge/port"),
        ])
        self.assertEqual({o["body"]["interface"] for o in ops[1:]}, {"ether1", "ether2"})
        self.assertEqual(ops[0]["body"]["name"], "netlabs-lan")

    def test_si_ya_esta_no_escribe_nada(self):
        actual = {
            "identity": {"name": "swc1"},
            "bridges": [{"name": "netlabs-lan"}],
            "bridge_ports": [
                {".id": "*1", "bridge": "netlabs-lan", "interface": "ether1"},
                {".id": "*2", "bridge": "netlabs-lan", "interface": "ether2"},
            ],
        }
        self.assertEqual(converge.ros_ops(self.nodo(), actual, "clave", {}, None), [])

    def test_una_pata_de_gestion_metida_en_el_puente_se_saca(self):
        actual = {
            "bridges": [{"name": "netlabs-lan"}],
            "bridge_ports": [
                {".id": "*1", "bridge": "netlabs-lan", "interface": "ether1"},
                {".id": "*2", "bridge": "netlabs-lan", "interface": "ether2"},
                {".id": "*3", "bridge": "netlabs-lan", "interface": "ether3"},
            ],
        }
        actual["identity"] = {"name": "swc1"}
        ops = converge.ros_ops(self.nodo(), actual, "clave", {}, None)
        self.assertEqual([(o["method"], o["path"]) for o in ops],
                         [("DELETE", "/rest/interface/bridge/port/*3")])


class LasRutasEstaticasDelRouter(unittest.TestCase):
    """El área `routes` de un RouterOS: lo declarado se pone y lo marcado que sobra se quita.

    La marca es el comentario `netlabs-`: una ruta puesta a mano no es del motor y no
    se toca, aunque su destino caiga en una red del laboratorio.
    """

    RUTAS = [{"destination": "10.40.0.0/16", "gateway": "10.99.0.2"}]

    def test_una_ruta_que_falta_se_crea_con_su_marca(self):
        ops = converge.ros_ops(
            {**router(), "configure": {"routes": self.RUTAS}},
            {"identity": {"name": "rte1"}, "addresses": [], "routes": []}, "clave", {}, None)
        self.assertEqual([(o["method"], o["path"]) for o in ops], [("PUT", "/rest/ip/route")])
        self.assertEqual(ops[0]["body"], {"dst-address": "10.40.0.0/16",
                                          "gateway": "10.99.0.2",
                                          "comment": "netlabs-ruta"})

    def test_la_ruta_ya_puesta_no_escribe(self):
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                   "comment": "netlabs-ruta", ".id": "*1"}]
        self.assertEqual(converge._route_ops(self.RUTAS, actual), [])

    def test_el_salto_con_la_pata_pegada_cuenta_igual(self):
        # RouterOS devuelve el salto como `10.99.0.2%ether1` cuando la pata está fija.
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2%ether1",
                   "comment": "netlabs-ruta", ".id": "*1"}]
        self.assertEqual(converge._route_ops(self.RUTAS, actual), [])

    def test_una_ruta_dinamica_no_cuenta_como_puesta(self):
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                   "dynamic": "true", ".id": "*1"}]
        self.assertEqual([o["method"] for o in converge._route_ops(self.RUTAS, actual)], ["PUT"])

    def test_el_mismo_destino_con_otro_salto_se_corrige(self):
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.9",
                   "comment": "netlabs-ruta", ".id": "*7"}]
        ops = converge._route_ops(self.RUTAS, actual)
        self.assertEqual([(o["method"], o["path"]) for o in ops], [("PATCH", "/rest/ip/route/*7")])
        self.assertEqual(ops[0]["body"], {"gateway": "10.99.0.2"})

    def test_una_ruta_propia_apagada_se_vuelve_a_encender(self):
        """Declarar una ruta es quererla en uso: una apagada a mano no lleva tráfico.

        Demuestra que una ruta del motor con el destino y el salto buenos no cuenta como
        puesta si está en `disabled=true`: se enciende, en vez de dejarla apagada para
        siempre mientras el laboratorio la siga declarando.
        """
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                   "comment": "netlabs-ruta", "disabled": "true", ".id": "*3"}]
        ops = converge._route_ops(self.RUTAS, actual)
        self.assertEqual([(o["method"], o["path"], o["body"]) for o in ops],
                         [("PATCH", "/rest/ip/route/*3", {"disabled": "no"})])

    def test_una_ruta_corregida_que_estaba_apagada_se_enciende_tambien(self):
        """Cambiar el salto no basta si la entrada sigue apagada."""
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.9",
                   "comment": "netlabs-ruta", "disabled": "true", ".id": "*4"}]
        ops = converge._route_ops(self.RUTAS, actual)
        self.assertEqual(ops[0]["body"], {"gateway": "10.99.0.2", "disabled": "no"})

    def test_dos_destinos_iguales_con_saltos_distintos_convergen(self):
        """Dos rutas al mismo destino son dos rutas, no una.

        Demuestra que cada entrada declarada reclama una entrada propia distinta: si las
        dos se llevaran la misma, cada pasada le cambiaría el salto a la otra y la tabla
        no tendría nunca las dos rutas que el laboratorio pide.
        """
        rutas = [{"destination": "10.40.0.0/16", "gateway": "10.99.0.2"},
                 {"destination": "10.40.0.0/16", "gateway": "10.99.0.9"}]
        ops = converge._route_ops(rutas, [])
        self.assertEqual([(o["method"], o["body"]) for o in ops], [
            ("PUT", {"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                     "comment": "netlabs-ruta"}),
            ("PUT", {"dst-address": "10.40.0.0/16", "gateway": "10.99.0.9",
                     "comment": "netlabs-ruta"}),
        ])
        # La segunda pasada no escribe nada: las dos están ya en la tabla.
        actual = [{"dst-address": "10.40.0.0/16", "gateway": via,
                   "comment": "netlabs-ruta", ".id": f"*{i}"}
                  for i, via in enumerate(("10.99.0.2", "10.99.0.9"), 1)]
        self.assertEqual(converge._route_ops(rutas, actual), [])

    def test_una_entrada_corregida_no_se_lleva_el_salto_de_la_otra(self):
        """Con una sola entrada propia, la segunda ruta declarada se crea aparte.

        Demuestra que la entrada que ya se corrigió para una entrada declarada no vuelve
        a reclamarse para la siguiente del mismo destino: ésa se crea, y no se reescribe
        el salto de la anterior.
        """
        rutas = [{"destination": "10.40.0.0/16", "gateway": "10.99.0.2"},
                 {"destination": "10.40.0.0/16", "gateway": "10.99.0.9"}]
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.7",
                   "comment": "netlabs-ruta", ".id": "*5"}]
        ops = converge._route_ops(rutas, actual)
        self.assertEqual([(o["method"], o["body"]) for o in ops], [
            ("PATCH", {"gateway": "10.99.0.2"}),
            ("PUT", {"dst-address": "10.40.0.0/16", "gateway": "10.99.0.9",
                     "comment": "netlabs-ruta"}),
        ])

    def test_una_ruta_propia_del_mismo_destino_que_no_se_declara_se_retira(self):
        """Lo declarado ya tiene su entrada: la otra del mismo destino es un resto."""
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                   "comment": "netlabs-ruta", ".id": "*1"},
                  {"dst-address": "10.40.0.0/16", "gateway": "10.99.0.7",
                   "comment": "netlabs-ruta", ".id": "*2"}]
        ops = converge._route_ops(self.RUTAS, actual)
        self.assertEqual([(o["method"], o["path"]) for o in ops], [("DELETE", "/rest/ip/route/*2")])

    def test_lo_que_sobra_marcado_se_retira(self):
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                   "comment": "netlabs-ruta", ".id": "*1"},
                  {"dst-address": "10.41.0.0/16", "gateway": "10.99.0.2",
                   "comment": "netlabs-ruta", ".id": "*2"}]
        ops = converge._route_ops(self.RUTAS, actual)
        self.assertEqual([(o["method"], o["path"]) for o in ops], [("DELETE", "/rest/ip/route/*2")])

    def test_una_ruta_sin_marca_no_se_toca(self):
        # La ajena se queda donde está; lo que falta de lo declarado se pone.
        actual = [{"dst-address": "10.55.0.0/16", "gateway": "10.99.0.9",
                   "comment": "puesta a mano", ".id": "*1"}]
        ops = converge._route_ops(self.RUTAS, actual)
        self.assertEqual([(o["method"], o["body"]["dst-address"]) for o in ops],
                         [("PUT", "10.40.0.0/16")])

    def test_una_ruta_ajena_que_ya_cubre_el_destino_no_se_duplica(self):
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                   "comment": "puesta a mano", ".id": "*1"}]
        self.assertEqual(converge._route_ops(self.RUTAS, actual), [])

    def test_una_ruta_ajena_apagada_no_sustituye_a_la_propia(self):
        """Una ruta ajena apagada no lleva tráfico: no puede hacer de la declarada.

        Demuestra que una ruta del motor activa se conserva cuando fuera hay otra al mismo
        destino y salto pero apagada: dada por puesta con la apagada, el barrido final
        borraba la propia y dejaba el camino cortado. La ajena no se toca.
        """
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                   "comment": "netlabs-ruta", ".id": "*1"},
                  {"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                   "comment": "puesta a mano", "disabled": "true", ".id": "*9"}]
        self.assertEqual(converge._route_ops(self.RUTAS, actual), [])

    def test_una_ruta_propia_apagada_junto_a_una_ajena_apagada_se_enciende(self):
        """La propia apagada se enciende aunque fuera haya otra igual, también apagada.

        Demuestra que el motor reclama su ruta y la pone en uso, en vez de darla por
        puesta con la de fuera —que no lleva tráfico— y dejar la suya sin encender.
        """
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                   "comment": "netlabs-ruta", "disabled": "true", ".id": "*1"},
                  {"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                   "comment": "puesta a mano", "disabled": "true", ".id": "*9"}]
        ops = converge._route_ops(self.RUTAS, actual)
        self.assertEqual([(o["method"], o["path"], o["body"]) for o in ops],
                         [("PATCH", "/rest/ip/route/*1", {"disabled": "no"})])

    def test_una_ruta_ajena_apagada_con_otro_salto_no_bloquea(self):
        """Una ruta ajena apagada no ocupa el destino: no impide poner la declarada.

        Demuestra que el motor no se para ante una ruta de fuera apagada con el mismo
        destino y otro salto: no está en uso, así que la ruta del laboratorio se pone.
        """
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.9",
                   "comment": "puesta a mano", "disabled": "true", ".id": "*9"}]
        ops = converge._route_ops(self.RUTAS, actual)
        self.assertEqual([(o["method"], o["body"]) for o in ops], [
            ("PUT", {"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                     "comment": "netlabs-ruta"}),
        ])

    def test_una_ruta_de_otra_tabla_no_cuenta_ni_bloquea(self):
        """El área administra `main`: una ruta de otra tabla no la consulta este tráfico.

        Demuestra que una ruta ajena al mismo destino y salto declarado pero en la tabla
        `backup` no se toma por la puesta —dejaría la declarada sin crear— y una con otro
        salto no se lee como conflicto: no compite por el camino que este router usa.
        """
        rutas = [{"destination": "10.40.0.0/16", "gateway": "10.99.0.2"}]
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                   "comment": "puesta a mano", "routing-table": "backup", ".id": "*1"},
                  {"dst-address": "10.40.0.0/16", "gateway": "10.99.0.9",
                   "comment": "puesta a mano", "routing-table": "backup", ".id": "*2"}]
        ops = converge._route_ops(rutas, actual)
        self.assertEqual([(o["method"], o["body"]) for o in ops], [
            ("PUT", {"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                     "comment": "netlabs-ruta"}),
        ])

    def test_la_coincidencia_exacta_se_reserva_antes_de_corregir_otra(self):
        """Con una entrada propia exacta, la otra declarada se crea: no se reescribe aquélla.

        Demuestra el orden que evita el ida y vuelta: corregir en el orden declarado tomaba
        la entrada de la segunda ruta para la primera y luego volvía a crear la segunda, con
        un PATCH y un PUT donde basta un PUT —y si el PUT falla, la segunda pierde su salto.
        """
        rutas = [{"destination": "10.40.0.0/16", "gateway": "10.99.0.9"},
                 {"destination": "10.40.0.0/16", "gateway": "10.99.0.2"}]
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                   "comment": "netlabs-ruta", ".id": "*1"}]
        ops = converge._route_ops(rutas, actual)
        self.assertEqual([(o["method"], o["body"]) for o in ops], [
            ("PUT", {"dst-address": "10.40.0.0/16", "gateway": "10.99.0.9",
                     "comment": "netlabs-ruta"}),
        ])

    def test_un_destino_ajeno_con_otro_salto_se_dice(self):
        # El motor no puede cumplir lo declarado sin tocar lo que no es suyo: se para
        # con el destino delante en vez de dejar una ruta que no es la declarada.
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.9",
                   "comment": "puesta a mano", ".id": "*1"}]
        with self.assertRaises(converge.LabError):
            converge._route_ops(self.RUTAS, actual)

    def test_un_destino_ajeno_encendido_se_dice_aunque_la_propia_este_puesta(self):
        """La ajena encendida compite con la declarada aunque la del motor ya esté puesta.

        Demuestra que tener la propia en su sitio no esconde el conflicto: la de fuera va
        al mismo destino por otro salto, se lleva el tráfico si tiene menos distancia y el
        motor no puede retirarla, así que se dice en vez de dar por convergido un camino
        que puede estar saliendo por donde el laboratorio no declara.
        """
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                   "comment": "netlabs-ruta", ".id": "*1"},
                  {"dst-address": "10.40.0.0/16", "gateway": "10.99.0.9",
                   "comment": "puesta a mano", ".id": "*9"}]
        with self.assertRaises(converge.LabError):
            converge._route_ops(self.RUTAS, actual)

    def test_una_ruta_ajena_encendida_con_el_mismo_salto_no_estorba(self):
        """La ajena que sale por el salto declarado no compite: no hay nada que decir.

        Demuestra la frontera de la comprobación anterior —sólo se dice la ajena que
        ofrece otro camino— y que la propia se sigue conservando cuando las dos coinciden.
        """
        actual = [{"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                   "comment": "netlabs-ruta", ".id": "*1"},
                  {"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                   "comment": "puesta a mano", ".id": "*9"}]
        self.assertEqual(converge._route_ops(self.RUTAS, actual), [])

    def test_una_ruta_ajena_por_un_salto_declarado_no_estorba_al_otro(self):
        """Dos rutas al mismo destino, y una ajena por uno de sus saltos declarados.

        Demuestra que la ajena no se toma por un intruso al revisar el otro salto: la
        declaración ya pide un camino por ése, así que la de fuera no ofrece nada que el
        laboratorio no declare, y el `apply` no se para con el laboratorio correcto.
        """
        rutas = [{"destination": "10.40.0.0/16", "gateway": "10.99.0.2"},
                 {"destination": "10.40.0.0/16", "gateway": "10.99.0.9"}]
        actual = [{"dst-address": "10.40.0.0/16", "gateway": via,
                   "comment": "netlabs-ruta", ".id": f"*{i}"}
                  for i, via in enumerate(("10.99.0.2", "10.99.0.9"), 1)]
        actual.append({"dst-address": "10.40.0.0/16", "gateway": "10.99.0.2",
                       "comment": "puesta a mano", ".id": "*9"})
        self.assertEqual(converge._route_ops(rutas, actual), [])

    def test_una_ruta_ajena_por_un_salto_no_declarado_se_dice_tambien(self):
        """La ajena que sale por un camino que nadie declara sí compite, y se dice.

        Demuestra la otra frontera: con dos rutas declaradas al mismo destino, la que va
        por un tercer salto se lleva el tráfico si tiene menos distancia, y el motor no la
        puede retirar.
        """
        rutas = [{"destination": "10.40.0.0/16", "gateway": "10.99.0.2"},
                 {"destination": "10.40.0.0/16", "gateway": "10.99.0.9"}]
        actual = [{"dst-address": "10.40.0.0/16", "gateway": via,
                   "comment": "netlabs-ruta", ".id": f"*{i}"}
                  for i, via in enumerate(("10.99.0.2", "10.99.0.9"), 1)]
        actual.append({"dst-address": "10.40.0.0/16", "gateway": "10.99.0.7",
                       "comment": "puesta a mano", ".id": "*9"})
        with self.assertRaises(converge.LabError):
            converge._route_ops(rutas, actual)


class LasRutasDelLaboratorio(unittest.TestCase):
    """La diferencia entre las rutas declaradas y las que tiene el invitado de gestión.

    Dentro de los espacios del laboratorio se quita lo que sobra; fuera no se entra:
    la ruta por defecto y la de la red de gestión también están en la tabla y no son
    suyas.
    """

    ESPACIOS = ["10.44.0.0/16"]
    DESEADAS = [{"space": "10.44.0.0/16", "via": "10.30.0.104", "role": "rte1",
                 "prueba": "10.44.1.1"}]

    def test_si_ya_esta_no_se_escribe_nada(self):
        actual = [{"dst": "default", "gateway": "10.30.0.1", "dev": "eth0"},
                  {"dst": "10.30.0.0/16", "dev": "eth0", "protocol": "kernel"},
                  {"dst": "10.44.0.0/16", "gateway": "10.30.0.104", "dev": "eth0"}]
        self.assertEqual(converge.rutas_ops(actual, self.DESEADAS, self.ESPACIOS), [])

    def test_una_ruta_que_falta_se_pone(self):
        ops = converge.rutas_ops([{"dst": "default", "gateway": "10.30.0.1"}],
                                 self.DESEADAS, self.ESPACIOS)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["cmd"],
                         converge._sh("ip route add 10.44.0.0/16 via 10.30.0.104"))
        self.assertIn("10.44.0.0/16", ops[0]["effect"])

    def test_una_ruta_con_otro_salto_se_corrige(self):
        # Un router que ya no está: la ruta existe con el salto viejo. Se retira el salto
        # viejo y se pone el declarado —una ruta que ya existe no se puede añadir—.
        actual = [{"dst": "10.44.0.0/16", "gateway": "10.30.0.199"}]
        ops = converge.rutas_ops(actual, self.DESEADAS, self.ESPACIOS)
        self.assertEqual([o["cmd"] for o in ops],
                         [converge._sh("ip route del 10.44.0.0/16 via 10.30.0.199"),
                          converge._sh("ip route replace 10.44.0.0/16 via 10.30.0.104")])

    def test_lo_que_sobra_dentro_de_mis_espacios_se_retira(self):
        actual = [{"dst": "10.44.0.0/16", "gateway": "10.30.0.104"},
                  {"dst": "10.44.1.0/24", "gateway": "10.30.0.104"}]
        ops = converge.rutas_ops(actual, self.DESEADAS, self.ESPACIOS)
        # La que está bien no se toca; la que sobra —una más concreta que ya nadie
        # declara— se retira.
        self.assertEqual([o["cmd"] for o in ops],
                         [converge._sh("ip route del 10.44.1.0/24")])

    def test_fuera_de_mis_espacios_no_se_entra(self):
        actual = [{"dst": "default", "gateway": "10.30.0.1"},
                  {"dst": "10.30.0.0/16", "dev": "eth0"},
                  {"dst": "10.46.0.0/16", "gateway": "10.30.0.108"}]
        self.assertEqual(converge.rutas_ops(actual, [], self.ESPACIOS), [])

    def test_dos_rutas_al_mismo_prefijo_se_retiran_las_dos(self):
        # Dos entradas con métricas distintas son dos rutas distintas: quedarse con una
        # dejaba la otra dentro del espacio para siempre, porque el `del` se emitía una
        # sola vez y `ip route del <prefijo>` quita una de las que encajan.
        actual = [{"dst": "10.44.0.0/16", "gateway": "10.30.0.104", "metric": 100},
                  {"dst": "10.44.0.0/16", "gateway": "10.30.0.120", "metric": 200}]
        ops = converge.rutas_ops(actual, [], self.ESPACIOS)
        self.assertEqual([o["cmd"] for o in ops],
                         [converge._sh("ip route del 10.44.0.0/16")] * 2)

    def test_una_ruta_declarada_con_otra_metrica_no_se_toca(self):
        # Lo que decide si la ruta declarada está puesta es su salto, no su métrica.
        actual = [{"dst": "10.44.0.0/16", "gateway": "10.30.0.104", "metric": 100}]
        self.assertEqual(converge.rutas_ops(actual, self.DESEADAS, self.ESPACIOS), [])

    def test_el_salto_viejo_con_menos_metrica_no_deja_la_ruta_por_puesta(self):
        """Tener nuestro salto en la tabla no es que el tráfico salga por él.

        Demuestra que la ruta no se da por puesta sólo porque exista una entrada con el
        salto declarado: con el salto viejo y menos métrica por delante, el tráfico sigue
        saliendo por el router que ya no está, así que se retira el viejo.
        """
        actual = [{"dst": "10.44.0.0/16", "gateway": "10.30.0.104", "metric": 200},
                  {"dst": "10.44.0.0/16", "gateway": "10.30.0.199", "metric": 100}]
        ops = converge.rutas_ops(actual, self.DESEADAS, self.ESPACIOS)
        self.assertEqual([o["cmd"] for o in ops],
                         [converge._sh("ip route del 10.44.0.0/16 via 10.30.0.199 metric 100")])

    def test_a_metricas_iguales_se_retira_el_salto_viejo(self):
        """Con la misma métrica el tráfico se reparte entre los dos saltos.

        Demuestra que la ruta declarada no se da por puesta cuando el salto viejo tiene
        su misma métrica: `ip route` monta multipath y la mitad del tráfico sale por un
        router que el laboratorio ya no declara. La métrica por defecto no se nombra al
        retirar, porque es como la llama la tabla.
        """
        actual = [{"dst": "10.44.0.0/16", "gateway": "10.30.0.104"},
                  {"dst": "10.44.0.0/16", "gateway": "10.30.0.199"}]
        ops = converge.rutas_ops(actual, self.DESEADAS, self.ESPACIOS)
        self.assertEqual([o["cmd"] for o in ops],
                         [converge._sh("ip route del 10.44.0.0/16 via 10.30.0.199")])

    def test_una_ruta_conectada_no_se_retira(self):
        """Una ruta sin salto no es un salto viejo.

        Demuestra que la frontera se respeta también aquí: retirar una ruta conectada se
        llevaría por delante una interfaz, y no es lo que el laboratorio declara.
        """
        actual = [{"dst": "10.44.0.0/16", "dev": "eth0", "protocol": "kernel"},
                  {"dst": "10.44.0.0/16", "gateway": "10.30.0.104", "dev": "eth0"}]
        self.assertEqual(converge.rutas_ops(actual, self.DESEADAS, self.ESPACIOS), [])

    def test_destroy_retira_lo_que_declaro_y_solo_eso(self):
        actual = [{"dst": "default", "gateway": "10.30.0.1"},
                  {"dst": "10.30.0.0/16", "dev": "eth0"},
                  {"dst": "10.44.0.0/16", "gateway": "10.30.0.104"},
                  {"dst": "10.46.0.0/16", "gateway": "10.30.0.108"}]
        ops = converge.rutas_ops(actual, [], self.ESPACIOS)
        self.assertEqual([o["cmd"] for o in ops],
                         [converge._sh("ip route del 10.44.0.0/16")])

    def test_el_cruce_se_sondea_con_tope(self):
        # El tope va dentro del script porque `until` no vale sobre un include: si no
        # responde en N intentos, sale con error y el que llama lo dice.
        cmd = converge.cruce_cmd({"prueba": "10.44.1.1"}, intentos=4, espera=1)
        self.assertEqual(cmd[:2], ["sh", "-c"])
        self.assertIn("seq 1 4", cmd[2])
        self.assertIn("ping -c1 -W1 10.44.1.1", cmd[2])
        self.assertIn("sleep 1", cmd[2])
        self.assertTrue(cmd[2].rstrip("'\n").endswith("exit 1"))


class ElRegistroEnLaVista(unittest.TestCase):
    """La quinta vía: registrar los equipos de red en lo que observa el sitio.

    El motor crea con credenciales los que faltan y a los ya descubiertos con otras
    credenciales los reporta como pendientes: su API sólo acepta las credenciales al
    crear el equipo. Todo esto es capa pura —(lo declarado, lo leído) → diferencia—, así
    que se prueba con un censo inventado, sin servicio.
    """

    API = "http://127.0.0.1:8000/v1"
    SECRETS = {"routeros_clave": "s3cr3t", "linux_clave": "l1nux"}

    def equipo(self, role="rte1", address="10.30.0.101", usuario="admin"):
        return {
            "role": role, "name": role, "type": "router", "mgmt_address": address,
            # La marca que el motor pone en el invitado y copia al registro de la vista:
            # sin ella no se puede demostrar que un resto es de este laboratorio.
            "description": f"netlabs lab=b_prueba role={role}",
            "configure": {"users": [{"name": usuario, "password_from": "secrets.routeros_clave"}]},
        }

    def test_un_equipo_que_falta_se_da_de_alta_con_su_credencial(self):
        plan = converge.netxms_ops([self.equipo()], [], [], self.API, self.SECRETS)
        self.assertEqual(len(plan["ops"]), 1)
        cuerpo = json.loads(plan["ops"][0]["cuerpo"])
        self.assertEqual(cuerpo["class"], "Node")
        self.assertEqual(cuerpo["ipAddress"], "10.30.0.101")
        self.assertEqual(cuerpo["sshLogin"], "admin")
        self.assertEqual(cuerpo["sshPassword"], "s3cr3t")
        self.assertEqual(cuerpo["sshPort"], 22)
        self.assertEqual(plan["pendientes"], [])

    def servidor(self, address="10.20.66.10/24"):
        return {
            "role": "svs1", "name": "svs1", "type": "server",
            "description": "netlabs lab=d_prueba role=svs1",
            "interfaces": [{"index": 0, "network": "ny_ingenieria", "address": address}],
            "configure": {},
        }

    def test_un_servidor_con_direccion_estatica_se_registra_con_su_terminal(self):
        # Un nodo final no tiene la clave del RouterOS ni una pata de gestión, pero
        # sí una terminal: se registra por su dirección estática con la cuenta de
        # root de los invitados Linux, para que la consola de la vista pueda abrirla.
        plan = converge.netxms_ops([self.servidor()], [], [], self.API, self.SECRETS)
        self.assertEqual(len(plan["ops"]), 1)
        cuerpo = json.loads(plan["ops"][0]["cuerpo"])
        self.assertEqual(cuerpo["ipAddress"], "10.20.66.10")
        self.assertEqual(cuerpo["sshLogin"], "root")
        self.assertEqual(cuerpo["sshPassword"], "l1nux")
        self.assertEqual(cuerpo["sshPort"], 22)

    def test_un_servidor_ya_registrado_sin_terminal_se_rehace(self):
        # El API no deja poner credenciales a un nodo que ya existe, así que un nodo
        # final registrado antes de que hubiera terminal se retira y se vuelve a dar
        # de alta. Sin ese rehacer, su consola seguiría sin saber entrar. La marca
        # del comentario demuestra que el registro es de este laboratorio: sin ella
        # no se podría borrar (AGENTS.md §3.6).
        encontrados = [{"id": 494, "name": "svs1", "ipAddress": {"address": "10.20.66.10"}}]
        detalles = [{"id": 494, "comments": "netlabs lab=d_prueba role=svs1",
                     "sshLogin": "", "sshPassword": "", "sshPort": 22}]
        plan = converge.netxms_ops([self.servidor()], encontrados, detalles, self.API, self.SECRETS)
        self.assertEqual([o["effect"].split()[0] for o in plan["ops"]], ["rehacer", "registrar"])
        self.assertIn("/494", plan["ops"][0]["cmd"][-1])
        self.assertEqual(json.loads(plan["ops"][1]["cuerpo"])["sshLogin"], "root")

    def test_un_servidor_ajeno_con_otras_credenciales_no_se_rehace(self):
        """La marca manda: sin ella, el registro no consta de este laboratorio.

        Demuestra que un nodo final homónimo de otro laboratorio, que ocupa la misma
        dirección y tiene otras credenciales, no se borra para rehacerlo: se perdería
        su histórico. Se dice como pendiente y lo decide una persona.
        """
        encontrados = [{"id": 494, "name": "svs1", "ipAddress": {"address": "10.20.66.10"}}]
        detalles = [{"id": 494, "comments": "netlabs lab=otro role=svs1",
                     "sshLogin": "otro", "sshPassword": "ajena", "sshPort": 22}]
        plan = converge.netxms_ops([self.servidor()], encontrados, detalles, self.API, self.SECRETS)
        self.assertEqual(plan["ops"], [])
        self.assertEqual(len(plan["pendientes"]), 1)
        self.assertIn("no lleva la marca", plan["pendientes"][0])

    def test_un_servidor_ya_registrado_con_su_terminal_no_se_toca(self):
        encontrados = [{"id": 494, "name": "svs1", "ipAddress": {"address": "10.20.66.10"}}]
        detalles = [{"id": 494, "sshLogin": "root", "sshPassword": "l1nux", "sshPort": 22}]
        plan = converge.netxms_ops([self.servidor()], encontrados, detalles, self.API, self.SECRETS)
        self.assertEqual(plan["ops"], [])
        self.assertEqual(plan["pendientes"], [])

    def test_un_nodo_final_por_dhcp_no_se_inventa_una_direccion(self):
        # Sin reserva no hay dirección que registrar: el mapa no puede dibujar un nodo
        # en una dirección que aún no existe. Se queda fuera hasta que tenga una.
        plan = converge.netxms_ops([self.servidor(address="dhcp")], [], [], self.API, self.SECRETS)
        self.assertEqual(plan["ops"], [])
        self.assertEqual(plan["pendientes"], [])

    def test_el_mapa_encuentra_un_nodo_final_por_su_direccion_estatica(self):
        censo = [{"id": 494, "name": "svs1", "ipAddress": {"address": "10.20.66.10"}}]
        objetos, faltan = converge.netxms_objetos_de([self.servidor()], censo)
        self.assertEqual(objetos, {"svs1": 494})
        self.assertEqual(faltan, [])

    def test_un_equipo_que_ya_esta_como_debe_no_escribe_nada(self):
        # Idempotencia: un equipo que ya está con las credenciales puestas no produce
        # ninguna llamada, y por eso el segundo `apply` no escribe.
        encontrados = [{"id": 7, "name": "rte1", "ipAddress": {"address": "10.30.0.101"}}]
        detalles = [{"id": 7, "sshLogin": "admin", "sshPassword": "s3cr3t", "sshPort": 22}]
        plan = converge.netxms_ops([self.equipo()], encontrados, detalles, self.API, self.SECRETS)
        self.assertEqual(plan["ops"], [])
        self.assertEqual(plan["pendientes"], [])

    def test_un_equipo_ya_descubierto_con_otras_credenciales_se_reporta_y_no_se_toca(self):
        # El API de esta versión sólo acepta las credenciales al crear el equipo: uno ya
        # descubierto sin ellas no se borra para rehacerlo —se perdería lo recolectado—,
        # se dice en voz alta y lo cambia una persona en la consola.
        encontrados = [{"id": 7, "name": "rte1", "ipAddress": {"address": "10.30.0.101"}}]
        detalles = [{"id": 7, "sshLogin": "", "sshPassword": "", "sshPort": 22}]
        plan = converge.netxms_ops([self.equipo()], encontrados, detalles, self.API, self.SECRETS)
        self.assertEqual(plan["ops"], [])
        self.assertEqual(len(plan["pendientes"]), 1)
        self.assertIn("10.30.0.101", plan["pendientes"][0])
        self.assertIn("otras credenciales", plan["pendientes"][0])

    def test_sin_usuario_declarado_se_registra_como_administrador(self):
        equipo = {"role": "rte1", "name": "rte1", "mgmt_address": "10.30.0.101", "configure": {}}
        plan = converge.netxms_ops([equipo], [], [], self.API, self.SECRETS)
        self.assertEqual(json.loads(plan["ops"][0]["cuerpo"])["sshLogin"], "admin")

    def test_la_clave_del_equipo_no_viaja_en_la_linea_de_ordenes(self):
        # La clave va en el cuerpo, que entra por la entrada estándar; en la orden —donde
        # la vería `ps` dentro del invitado de gestión— no aparece.
        op = converge.netxms_ops([self.equipo()], [], [], self.API, self.SECRETS)["ops"][0]
        self.assertNotIn("s3cr3t", " ".join(op["cmd"]))
        self.assertIn("s3cr3t", op["cuerpo"])

    def test_el_testigo_no_se_expande_en_la_orden_y_el_error_http_falla(self):
        # El testigo se lee de la entrada y llega a `curl` por una cabecera leída de
        # un descriptor (`-H @/dev/fd/3`): si se expandiera en `-H`, acabaría en los
        # argumentos de `curl` y `ps` lo vería. Y `--fail-with-body` hace que un
        # 403/409/500 no se dé por bueno: una alta rechazada no puede parecer correcta.
        cmd = converge.netxms_censo_cmd(self.API)
        self.assertEqual(cmd[:2], ["sh", "-c"])
        self.assertIn("IFS= read -r t", cmd[2])
        self.assertIn("-H @/dev/fd/3", cmd[2])
        self.assertIn("--fail-with-body", cmd[2])
        # La cabecera se lee de un descriptor, no se entrecomilla como argumento.
        self.assertNotIn('Bearer "', cmd[2])
        self.assertIn("/objects/search", cmd[2])

    def test_la_lectura_del_objeto_lleva_el_testigo_leido_de_la_entrada(self):
        """`netxms_objeto_cmd` arma su propia cabecera: el testigo va en `$t`, no fijo.

        La lectura del objeto —el mapa y sus banderas— es una llamada más al API, así que
        lleva el mismo testigo que las demás. Si en su sitio queda un texto literal, el
        API rechaza la lectura, `--fail-with-body` la cuenta como fallo y el `apply` se
        para antes de escribir el mapa, su huella y sus banderas.
        """
        cmd = converge.netxms_objeto_cmd(self.API, 7)
        self.assertEqual(cmd[:2], ["sh", "-c"])
        self.assertIn("IFS= read -r t", cmd[2])
        self.assertIn("Authorization: Bearer $t", cmd[2])
        self.assertIn("-H @/dev/fd/3", cmd[2])
        self.assertIn("/objects/7", cmd[2])

    def test_la_lectura_de_la_configuracion_lleva_el_testigo_leido_de_la_entrada(self):
        """`netxms_configs_cmd` arma su cabecera como las demás: el testigo va en `$t`, no fijo.

        Si en su sitio queda un texto literal, el API rechaza la lectura, `--fail-with-body` la
        cuenta como fallo y el `apply` se para antes de dejar puesta la escucha de registros.
        """
        cmd = converge.netxms_configs_cmd(self.API)
        self.assertEqual(cmd[:2], ["sh", "-c"])
        self.assertIn("IFS= read -r t", cmd[2])
        self.assertIn("$t", cmd[2])
        self.assertNotIn("***", cmd[2])
        self.assertIn("-H @/dev/fd/3", cmd[2])
        self.assertIn("/server-config", cmd[2])

    def test_el_censo_pregunta_solo_por_equipos(self):
        self.assertEqual(json.loads(converge.netxms_censo_cuerpo()), {"class": ["Node"]})

    def test_el_login_va_a_su_ruta_y_el_cuerpo_lleva_usuario_y_clave(self):
        self.assertIn("/login", converge.netxms_login_cmd(self.API)[2])
        cuerpo = json.loads(converge.netxms_login_cuerpo("admin", "clave"))
        self.assertEqual(cuerpo, {"username": "admin", "password": "clave"})

    def test_las_llamadas_al_api_llevan_tope_de_tiempo(self):
        # Un servicio que escucha pero no contesta dejaría el `curl` colgado para siempre
        # y el `apply` con él: un fallo se dice en vez de esperar a ciegas.
        self.assertIn("--max-time", converge.netxms_censo_cmd(self.API)[2])
        self.assertIn("--max-time", converge.netxms_login_cmd(self.API)[2])
        self.assertIn("--connect-timeout", converge.netxms_login_cmd(self.API)[2])

    def test_un_equipo_que_apunta_a_la_maquina_de_otro_se_retira_y_se_rehace(self):
        """La dirección de gestión se deriva del vmid, y el vmid cambia al rehacer.

        Atada la identidad a la dirección, cada despliegue dejaba en la vista un equipo
        con el nombre bueno apuntando a la máquina de otro: abrir `rta6` llevaba a
        `swa2`. Se busca por nombre; si no lleva su dirección, se retira y se da de alta.
        """
        sobrante = {"id": 269, "name": "rta6", "ipAddress": {"address": "10.30.0.116"}}
        bueno_swa2 = {"id": 271, "name": "swa2", "ipAddress": {"address": "10.30.0.116"}}
        equipo = self.equipo(role="rta6", address="10.30.0.114")
        # .116 es de un equipo de ESTE laboratorio (swa2): el `rta6` que apunta ahí es
        # un resto, no un equipo ajeno.
        swa2 = self.equipo(role="swa2", address="10.30.0.116")
        detalles = [{"id": 269, "comments": "netlabs lab=b_prueba role=rta6"}]
        plan = converge.netxms_ops([equipo, swa2], [sobrante, bueno_swa2], detalles, self.API,
                                   self.SECRETS, vivas=["10.30.0.114", "10.30.0.116"])
        efectos = [op["effect"] for op in plan["ops"]]
        self.assertEqual(len(efectos), 2)
        self.assertIn("retirar rta6", efectos[0])
        self.assertIn("10.30.0.116", efectos[0])
        self.assertIn("/objects/269", plan["ops"][0]["cmd"][2])
        self.assertIn("registrar rta6 (10.30.0.114)", efectos[1])

    def test_con_el_bueno_delante_se_retiran_los_sobrantes_y_no_se_rehace(self):
        censo = [
            {"id": 269, "name": "rta6", "ipAddress": {"address": "10.30.0.120"}},
            {"id": 326, "name": "rta6", "ipAddress": {"address": "10.30.0.114"}},
            {"id": 272, "name": "swa4", "ipAddress": {"address": "10.30.0.120"}},
        ]
        detalles = [{"id": 326, "sshLogin": "admin", "sshPassword": "s3cr3t", "sshPort": 22},
                    {"id": 269, "comments": "netlabs lab=b_prueba role=rta6"}]
        plan = converge.netxms_ops([self.equipo(role="rta6", address="10.30.0.114"),
                                    self.equipo(role="swa4", address="10.30.0.120")],
                                   censo, detalles, self.API, self.SECRETS,
                                   vivas=["10.30.0.114", "10.30.0.120"])
        self.assertEqual([op["effect"][:7] for op in plan["ops"]], ["retirar"])
        self.assertIn("/objects/269", plan["ops"][0]["cmd"][2])

    def test_el_equipo_de_otro_laboratorio_con_el_mismo_nombre_no_se_toca(self):
        """Dos laboratorios pueden tener un `rte1` cada uno: si su dirección es de una
        máquina viva y no es de este laboratorio, el equipo es del otro y se deja."""
        ajeno = {"id": 500, "name": "rte1", "ipAddress": {"address": "10.30.0.140"}}
        plan = converge.netxms_ops([self.equipo()], [ajeno], [], self.API, self.SECRETS,
                                   vivas=["10.30.0.140"])
        self.assertEqual(len(plan["ops"]), 1)
        self.assertIn("registrar rte1 (10.30.0.101)", plan["ops"][0]["effect"])

    def test_las_retiradas_van_antes_que_las_altas(self):
        """Un equipo viejo puede estar ocupando la dirección del que hay que dar de alta.

        El API contesta 409 si la dirección ya es de otro equipo, y las retiradas se
        descubren al recorrer los equipos: en un solo recorrido, la del último llegaba
        después del alta del primero y el apply se paraba a medias.
        """
        censo = [
            {"id": 234, "name": "swa1", "ipAddress": {"address": "10.30.0.107"}},
            {"id": 208, "name": "swc1", "ipAddress": {"address": "10.30.0.109"}},
        ]
        nodes = [self.equipo(role="swc1", address="10.30.0.107"),
                 self.equipo(role="swa1", address="10.30.0.115")]
        plan = converge.netxms_ops(nodes, censo,
                                   [{"id": 234, "comments": "netlabs lab=b_prueba role=swa1"}],
                                   self.API, self.SECRETS,
                                   vivas=["10.30.0.107", "10.30.0.109", "10.30.0.115"])
        efectos = [op["effect"].split()[0] for op in plan["ops"]]
        self.assertEqual(efectos, ["retirar", "registrar", "registrar"])
        self.assertIn("/objects/234", plan["ops"][0]["cmd"][2])

    def test_un_resto_propio_que_apunta_a_un_puesto_del_laboratorio_se_retira(self):
        """La dirección de un puesto es de este laboratorio, aunque el puesto no se registre.

        Demuestra que la retirada no depende de que la dirección sea la de un equipo de red
        declarado: un puesto no se registra y no está en los equipos, así que lo único que
        demuestra que ese `rte1` viejo apuntaba a una máquina de aquí es la lista de
        direcciones de los invitados de este laboratorio. Sin ella, el registro no se
        retira —está vivo, y vivo y ajeno no es un resto— y el equipo se quedaría con la
        dirección de la máquina equivocada.
        """
        resto = {"id": 411, "name": "rte1", "ipAddress": {"address": "10.30.0.150"}}
        plan = converge.netxms_ops([self.equipo()], [resto],
                                   [{"id": 411, "comments": "netlabs lab=b_prueba role=rte1"}],
                                   self.API, self.SECRETS,
                                   vivas=["10.30.0.101", "10.30.0.150"],
                                   propias=["10.30.0.150"])
        self.assertEqual([op["effect"].split()[0] for op in plan["ops"]],
                         ["retirar", "registrar"])
        self.assertIn("/objects/411", plan["ops"][0]["cmd"][2])
        self.assertIn("registrar rte1 (10.30.0.101)", plan["ops"][1]["effect"])
        self.assertEqual(plan["pendientes"], [])

    def test_un_resto_que_no_consta_de_este_laboratorio_no_se_borra(self):
        """Compartir nombre y que la dirección no sea de nadie no demuestra propiedad.

        Demuestra que el histórico de otro laboratorio —un `rte1` homónimo cuyo invitado
        ya se destruyó, así que su dirección no la tiene hoy nadie— no se retira al
        aplicar éste: se dice, y lo retira una persona si resulta ser un resto.
        """
        resto = {"id": 300, "name": "rte1", "ipAddress": {"address": "10.30.0.140"}}
        plan = converge.netxms_ops([self.equipo()], [resto], [], self.API, self.SECRETS,
                                   vivas=[])
        self.assertEqual(len(plan["ops"]), 1)
        self.assertIn("/objects", plan["ops"][0]["cmd"][2])
        self.assertNotIn("DELETE", plan["ops"][0]["cmd"][2])
        self.assertEqual(len(plan["pendientes"]), 1)
        self.assertIn("10.30.0.140", plan["pendientes"][0])
        self.assertIn("no se retira", plan["pendientes"][0])

    def test_un_resto_sin_la_marca_no_se_borra_aunque_la_direccion_sea_de_aqui(self):
        """La dirección de hoy no demuestra quién creó el registro: manda la marca.

        Demuestra el caso que se lleva el histórico de otro laboratorio: el asignador
        reutiliza un vmid y su dirección para un puesto de éste, y el `rte1` del otro cae
        dentro de lo que parece de aquí. Sin la marca en su ficha no se retira; se dice.
        """
        resto = {"id": 500, "name": "rte1", "ipAddress": {"address": "10.30.0.150"}}
        plan = converge.netxms_ops([self.equipo()], [resto],
                                   [{"id": 500, "comments": "netlabs lab=otro role=rte1"}],
                                   self.API, self.SECRETS,
                                   vivas=["10.30.0.101", "10.30.0.150"],
                                   propias=["10.30.0.150"])
        efectos = [op["effect"] for op in plan["ops"]]
        self.assertEqual(len(efectos), 1)
        self.assertIn("registrar rte1", efectos[0])
        self.assertEqual(len(plan["pendientes"]), 1)
        self.assertIn("no lleva la marca", plan["pendientes"][0])

    def test_la_direccion_que_ocupa_otro_equipo_para_el_alta(self):
        """El API contesta 409 si la dirección ya es de otro: el alta no se finge.

        Demuestra que un objeto con otra máquina en la dirección del alta se dice con
        su nombre y su identificador y el plan termina en error, no en una nota: sin el
        alta, el equipo no queda en la vista y `apply` no puede anunciar el laboratorio
        como desplegado. La retirada del plan sí libera la dirección (ver
        `test_las_retiradas_van_antes_que_las_altas`).
        """
        ocupante = {"id": 77, "name": "maquina-suelta", "ipAddress": {"address": "10.30.0.101"}}
        with self.assertRaisesRegex(LabError, "409"):
            converge.netxms_ops([self.equipo()], [ocupante], [], self.API, self.SECRETS,
                                vivas=["10.30.0.101"])

    def test_las_fichas_se_piden_por_los_equipos_y_por_sus_homonimos(self):
        # La búsqueda devuelve resúmenes sin credenciales: la ficha hay que pedirla, y se
        # pide de una vez por los equipos que ya están con su dirección —su estado— y por
        # los homónimos que apuntan a otra —su marca de propiedad, sin la cual un resto no
        # se puede retirar—. La de un nombre que no es de este laboratorio no se pide:
        # leer la de todos para escribir uno sería leer de más.
        encontrados = [
            {"id": 7, "name": "rte1", "ipAddress": {"address": "10.30.0.101"}},  # de este
            {"id": 9, "name": "rte1", "ipAddress": {"address": "10.30.0.108"}},  # homónimo
            {"id": 5, "name": "rte1", "ipAddress": {"address": "10.30.0.101"}},  # de este
            {"id": 4, "name": "swx9", "ipAddress": {"address": "10.30.0.199"}},  # de nadie
        ]
        ids = converge.netxms_ids([self.equipo()], encontrados)
        self.assertEqual(ids, [5, 7, 9])
        self.assertEqual(json.loads(converge.netxms_fichas_cuerpo(ids)), {"ids": [5, 7, 9]})


class ElMapaAtaCadaCableASuInterfaz(unittest.TestCase):
    """El otro extremo del cable: la interfaz por la que sale cada punta.

    El censo de la vista no dice de quién es cada interfaz —no trae el padre—, pero la ficha
    de un equipo trae la lista de sus hijos, que son justo sus interfaces, y el censo de
    interfaces dice el nombre de cada número. Cruzando las dos lecturas que ya se hacían, el
    puerto `p3` del plano queda atado a la `ether3` del equipo y no a un cable anónimo.
    """

    NODOS = [
        {"role": "rta1", "name": "rta1", "mgmt_address": "10.30.0.101"},
        {"role": "swc1", "name": "swc1", "mgmt_address": "10.30.0.102"},
        {"role": "rta9", "name": "rta9", "mgmt_address": "10.30.0.109"},  # no está en la vista
    ]
    CENSO = [
        {"id": 420, "name": "rta1", "ipAddress": {"address": "10.30.0.101"}},
        {"id": 421, "name": "swc1", "ipAddress": {"address": "10.30.0.102"}},
    ]
    FICHAS = [
        {"id": 420, "class": "Node", "children": [436, 437, 438]},
        {"id": 421, "class": "Node", "children": [501, 502]},
    ]
    INTERFACES = [
        {"id": 436, "class": "Interface", "name": "lo"},
        {"id": 437, "class": "Interface", "name": "ether1"},
        {"id": 438, "class": "Interface", "name": "ether2"},
        {"id": 501, "class": "Interface", "name": "ether1"},
        {"id": 502, "class": "Interface", "name": "ether2"},
        {"id": 999, "class": "Interface", "name": "ether9"},  # de otro laboratorio
    ]

    def test_cada_equipo_se_queda_con_sus_interfaces_y_no_con_las_de_otro(self):
        atadas = converge.netxms_interfaces_de(self.NODOS, self.CENSO, self.FICHAS,
                                               self.INTERFACES)
        self.assertEqual(atadas, {
            "rta1": {"ether1": 437, "ether2": 438, "lo": 436},
            "swc1": {"ether1": 501, "ether2": 502},
        })

    def test_un_equipo_que_no_esta_en_la_vista_no_ata_nada(self):
        # Y no se le cuelga la interfaz de otro: `ether9` no es de nadie de este laboratorio.
        atadas = converge.netxms_interfaces_de(self.NODOS, self.CENSO, self.FICHAS,
                                               self.INTERFACES)
        self.assertNotIn("rta9", atadas)
        self.assertNotIn(999, [n for nombres in atadas.values() for n in nombres.values()])

    def test_sin_las_dos_lecturas_no_se_ata_nada_y_el_mapa_se_dibuja_igual(self):
        self.assertEqual(converge.netxms_interfaces_de(self.NODOS, self.CENSO, [], []), {})
        self.assertEqual(json.loads(converge.netxms_interfaces_cuerpo()),
                         {"class": ["Interface"]})
        self.assertIn("/objects/search", converge.netxms_interfaces_cmd("http://x/v1")[2])


class LaCuentaDelMapa(unittest.TestCase):
    """Lo que el mapa dice de sí mismo al escribirse: cuántas puntas quedaron atadas.

    El debug del apply presenta ese número como «interfaces puestas en sus puntas». Contar
    todas las interfaces que la vista le ha descubierto a cada equipo —`lo`, la de gestión,
    las de puertos cuyos cables no salen en el mapa— diría de más y no diría cuántas puntas
    quedaron atadas, que es lo que hay que poder comprobar.
    """

    API = "http://127.0.0.1:8000/v1"
    NODOS = [
        {"role": "rte1", "name": "rte1", "type": "router", "mgmt_address": "10.30.0.101",
         "networks": ["lan1"]},
        {"role": "rta1", "name": "rta1", "type": "router", "mgmt_address": "10.30.0.102",
         "networks": ["lan1"]},
    ]
    CENSO = [
        {"id": 100, "name": "rte1", "ipAddress": {"address": "10.30.0.101"}},
        {"id": 101, "name": "rta1", "ipAddress": {"address": "10.30.0.102"}},
    ]
    # Cada equipo tiene su `lo` y su `ether1`: contar las interfaces descubiertas daría
    # cuatro; sólo dos puntas —una por extremo del único cable— quedan atadas.
    FICHAS = [
        {"id": 100, "class": "Node", "children": [1, 2]},
        {"id": 101, "class": "Node", "children": [3, 4]},
    ]
    INTERFACES = [
        {"id": 1, "class": "Interface", "name": "lo"},
        {"id": 2, "class": "Interface", "name": "ether1"},
        {"id": 3, "class": "Interface", "name": "lo"},
        {"id": 4, "class": "Interface", "name": "ether1"},
    ]
    LAB = {
        "lab": "z_prueba",
        "networks": [{"name": "lan1", "address": "10.20.0.0/24"}],
        "nodes": [
            {"role": "rte1", "name": "rte1", "type": "router", "networks": ["lan1"]},
            {"role": "rta1", "name": "rta1", "type": "router", "networks": ["lan1"]},
        ],
        "links": [{"a": {"node": "rte1", "port": 1}, "z": {"node": "rta1", "port": 1}}],
    }
    SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">'
           '<g data-area="Núcleo" data-x="10" data-y="10" data-ancho="180" data-alto="120" '
           'data-subred="10.20.0.0/24" data-nube="0"/>'
           '<g data-rol="rte1" data-x="60.0" data-y="60.0"/>'
           '<g data-rol="rta1" data-x="120.0" data-y="60.0"/></svg>')

    def test_la_cuenta_suma_las_puntas_atadas_y_no_todas_las_interfaces(self):
        plan = converge.netxms_mapa_ops(self.LAB, self.NODOS, self.CENSO, None, self.API,
                                        "7", self.FICHAS, self.INTERFACES, self.SVG)
        self.assertEqual(plan["equipos"], 2)
        self.assertEqual(plan["cables"], 1)
        # Dos puntas atadas —una por extremo—, no las cuatro interfaces descubiertas.
        self.assertEqual(plan["interfaces"], 2)

    def test_sin_interfaces_descubiertas_la_cuenta_es_cero_y_el_mapa_se_dibuja(self):
        plan = converge.netxms_mapa_ops(self.LAB, self.NODOS, self.CENSO, None, self.API,
                                        "7", [], [], self.SVG)
        self.assertEqual(plan["interfaces"], 0)
        self.assertEqual(plan["cables"], 1)


class ElMapaQueAlguienAjusta(unittest.TestCase):
    """Qué se escribe del mapa —el dibujo, su huella o nada— y con qué comentario.

    El dibujo y su huella viajan en dos peticiones del API, así que el motor tiene que poder
    mandar sólo una: dejar la huella sola cuando el dibujo ya es el del plano —un mapa de
    antes de esta regla, o un `apply` cortado entre las dos—, y no mandar ninguna cuando ya
    está todo. El comentario del objeto es el otro extremo del recorrido: sin él, la huella
    no se comprueba y un ajuste a mano se borra.
    """

    API = "http://127.0.0.1:8000/v1"
    LAB = {
        "lab": "z_prueba",
        "networks": [{"name": "lan1", "address": "10.20.0.0/24"}],
        "nodes": [
            {"role": "rte1", "name": "rte1", "type": "router", "mgmt_address": "10.20.0.11",
             "networks": ["lan1"]},
            {"role": "rta1", "name": "rta1", "type": "router", "mgmt_address": "10.20.0.12",
             "networks": ["lan1"]},
        ],
        "links": [{"a": {"node": "rte1", "port": 1}, "z": {"node": "rta1", "port": 1}}],
    }
    NODOS = LAB["nodes"]
    CENSO = [
        {"id": 100, "name": "rte1", "ipAddress": {"address": "10.20.0.11"}},
        {"id": 101, "name": "rta1", "ipAddress": {"address": "10.20.0.12"}},
    ]
    FICHAS = [
        {"id": 100, "class": "Node", "children": [1]},
        {"id": 101, "class": "Node", "children": [2]},
    ]
    INTERFACES = [
        {"id": 1, "class": "Interface", "name": "ether1"},
        {"id": 2, "class": "Interface", "name": "ether1"},
    ]
    SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">'
           '<g data-area="Núcleo" data-x="10" data-y="10" data-ancho="180" data-alto="120" '
           'data-subred="10.20.0.0/24" data-nube="0"/>'
           '<g data-rol="rte1" data-x="60.0" data-y="60.0"/>'
           '<g data-rol="rta1" data-x="120.0" data-y="60.0"/></svg>')

    def dibujo_del_plano(self):
        """El mapa que el plano pide, derivado como lo deriva el motor."""
        objetos, _ = converge.netxms_objetos_de(self.NODOS, self.CENSO)
        atadas = converge.netxms_interfaces_de(self.NODOS, self.CENSO, self.FICHAS,
                                              self.INTERFACES)
        return mapa.contenido(self.LAB, self.SVG, objetos, atadas)

    def comentario_con(self, huella: str) -> str:
        """El comentario que el motor deja en el mapa: su marca y la huella del dibujo."""
        return f"{converge.netxms_marca_de('z_prueba')} {converge.HUELLA_EN_EL_MAPA}{huella}"

    def plan(self, actual, comentarios="", objeto=None):
        """El plan del mapa. Por defecto, un objeto cuyas banderas ya están encendidas:

        las pruebas de aquí van del dibujo y de su huella, no de las banderas, y sin esto
        todas ellas verían además la operación de las banderas.
        """
        if objeto is None:
            objeto = {"flags": {b: True for b in converge.BANDERAS_QUE_EL_MAPA_ENSENA}}
        return converge.netxms_mapa_ops(self.LAB, self.NODOS, self.CENSO, actual, self.API,
                                        "7", self.FICHAS, self.INTERFACES, self.SVG,
                                        comentarios, objeto)

    def banderas_del_plan(self, plan):
        """La operación de banderas del plan, si la hay."""
        for op in plan["ops"]:
            cuerpo = json.loads(op["cuerpo"]) if op.get("cuerpo") else {}
            if "flags" in cuerpo:
                return cuerpo["flags"]
        return None

    def test_el_mapa_nace_con_el_marco_y_el_fondo_de_estado(self):
        """Un mapa recién hecho trae las banderas apagadas: se encienden al colocarlo."""
        plan = self.plan(None, "", objeto={})
        banderas = self.banderas_del_plan(plan)
        self.assertIsNotNone(banderas, "el mapa no enciende el marco ni el fondo")
        for b in converge.BANDERAS_QUE_EL_MAPA_ENSENA:
            self.assertIs(banderas.get(b), True)

    def test_las_banderas_ya_encendidas_no_se_tocan(self):
        """Idempotencia: con el dibujo al día y las banderas puestas, no hay operación."""
        dibujo = self.dibujo_del_plano()
        plan = self.plan(dibujo, self.comentario_con(mapa.huella(dibujo)))
        self.assertEqual(plan["ops"], [])

    def test_las_banderas_se_encienden_sin_pisar_las_demas(self):
        """El `PATCH` reemplaza el objeto entero: las demás banderas vuelven tal cual."""

        plan = self.plan(None, "", objeto={"flags": {"calculateStatus": True,
                                                    "showStatusFrame": False}})
        banderas = self.banderas_del_plan(plan)
        self.assertIs(banderas.get("calculateStatus"), True, "se ha pisado otra bandera")
        self.assertIs(banderas.get("showStatusIcon"), True)
        self.assertIs(banderas.get("showStatusFrame"), True)
        self.assertIs(banderas.get("showStatusBackground"), True)

    def test_la_huella_se_escribe_con_patch(self):
        """El servicio no acepta `PUT` para tocar un objeto —responde 405—, sino `PATCH`."""
        plan = self.plan(self.dibujo_del_plano(), "")
        sello = [op for op in plan["ops"] if "comments" in (op.get("cuerpo") or "")]
        self.assertEqual(len(sello), 1)
        self.assertIn("-X PATCH", " ".join(sello[0]["cmd"]),
                      "la huella se escribe con un método que el servicio rechaza")

    def test_el_mapa_que_nace_se_escribe_y_se_sella(self):
        """Las dos peticiones: el dibujo del plano y, detrás, su huella en el comentario."""
        plan = self.plan(None)
        self.assertEqual(plan["motivo"], "no hay mapa todavía")
        self.assertEqual(len(plan["ops"]), 2, "el mapa nuevo no se sella")
        sello = json.loads(plan["ops"][1]["cuerpo"])["comments"]
        self.assertEqual(converge.netxms_lab_de_marca(sello), "z_prueba")
        self.assertEqual(converge.netxms_huella_guardada(sello),
                         mapa.huella(self.dibujo_del_plano()))

    def test_la_segunda_pasada_no_escribe_nada(self):
        """Idempotencia: el dibujo del plano con su huella no produce ninguna operación."""
        dibujo = self.dibujo_del_plano()
        plan = self.plan(dibujo, self.comentario_con(mapa.huella(dibujo)))
        self.assertEqual(plan["ops"], [])
        self.assertEqual(plan["motivo"], "ya es el del plano")

    def test_un_mapa_de_antes_de_la_huella_recibe_solo_su_huella(self):
        """Ya coincide con el plano y no lleva huella: se le pone, sin reescribir el dibujo."""
        plan = self.plan(self.dibujo_del_plano(), "")
        self.assertEqual(len(plan["ops"]), 1,
                         "se ha reescrito un dibujo que ya era el del plano")
        self.assertIn("/objects/7", " ".join(plan["ops"][0]["cmd"]))
        self.assertEqual(converge.netxms_huella_guardada(
            json.loads(plan["ops"][0]["cuerpo"])["comments"]),
            mapa.huella(self.dibujo_del_plano()))
        self.assertEqual(plan["motivo"], "faltaba la huella")

    def test_un_apply_cortado_entre_el_dibujo_y_la_huella_se_repara(self):
        """El dibujo del plano con una huella que no cuadra es un corte, no un ajuste.

        Demuestra que no se lee como «ajustado a mano» —lo que dejaría el mapa congelado
        para siempre— sino que se vuelve a dejar la huella del dibujo que hay.
        """
        plan = self.plan(self.dibujo_del_plano(), self.comentario_con("0" * 40))
        self.assertEqual(len(plan["ops"]), 1)
        self.assertEqual(plan["motivo"], "la huella no cuadraba")

    def test_un_mapa_ajustado_a_mano_no_se_toca(self):
        """La huella no cuadra y el dibujo no es el del plano: manda quien lo movió."""
        movido = json.loads(json.dumps(self.dibujo_del_plano()))
        movido["elements"][0]["posX"] = movido["elements"][0]["posX"] + 40
        plan = self.plan(movido, self.comentario_con(mapa.huella(self.dibujo_del_plano())))
        self.assertEqual(plan["ops"], [], "el apply ha pisado el mapa que alguien movió")
        self.assertEqual(plan["motivo"], "ajustado a mano")


class ElMarcadorLimpio(unittest.TestCase):
    """Qué alarmas de la vista se dan por resueltas al converger un laboratorio.

    La vista no resuelve sola una alarma que saltó una vez —la MAC de un invitado que
    cambió al volver a crearlo—, y con ella el equipo se queda en amarillo aunque el mal
    ya no esté. Se resuelven las del laboratorio, y sólo las suyas.
    """

    MIOS = [526, 527, 528]

    def alarma(self, source, severity=3, state=0, message="Duplicate MAC address found",
               id=1):
        return {"id": id, "source": source, "severity": severity, "state": state,
                "message": message}

    def test_una_alarma_viva_de_un_equipo_del_laboratorio_se_resuelve(self):
        propias = converge.netxms_alarmas_propias([self.alarma(526)], self.MIOS)
        self.assertEqual([a["id"] for a in propias], [1])

    def test_la_alarma_de_otro_laboratorio_no_se_toca(self):
        # Los números de otro laboratorio no están entre los míos: no se mira su marcador.
        self.assertEqual(converge.netxms_alarmas_propias([self.alarma(900)], self.MIOS), [])

    def test_una_alarma_ya_resuelta_no_se_vuelve_a_resolver(self):
        # `state` 2 es resuelta: volver a resolverla no cambia nada y ensucia el registro.
        self.assertEqual(
            converge.netxms_alarmas_propias([self.alarma(526, state=2)], self.MIOS), [])

    def test_el_ruido_de_severidad_normal_no_se_resuelve(self):
        # Severidad 0 es lo que la vista apunta sola (un paquete instalado): no es un mal.
        self.assertEqual(
            converge.netxms_alarmas_propias([self.alarma(526, severity=0)], self.MIOS), [])

    def test_una_alarma_de_aviso_para_arriba_si_se_resuelve(self):
        propias = converge.netxms_alarmas_propias(
            [self.alarma(527, severity=1), self.alarma(528, severity=2, id=2)], self.MIOS)
        self.assertEqual([a["id"] for a in propias], [1, 2])

    def test_sin_alarmas_no_hay_nada_que_resolver(self):
        self.assertEqual(converge.netxms_alarmas_propias([], self.MIOS), [])
        self.assertEqual(converge.netxms_alarmas_propias(None, self.MIOS), [])

    NODOS = [{"role": "rta1", "name": "rta1", "mgmt_address": "10.30.0.101"}]

    def test_el_homonimo_de_otro_laboratorio_no_entra_en_la_limpieza(self):
        """Dos `rta1` con distinta dirección: sólo el de aquí se resuelve.

        Demuestra el caso que se lleva por delante el marcador de otro laboratorio: el
        nombre es del laboratorio, no de la vista, así que dos laboratorios pueden tener
        cada uno su `rta1` apuntando a máquinas distintas. Los números propios se emparejan
        por nombre Y dirección, y con ellos la alarma del homónimo queda fuera. La lectura
        de fichas sigue viendo los dos, que es lo que hace falta para saber quién creó el
        resto.
        """
        censo = [
            {"id": 526, "name": "rta1", "ipAddress": {"address": "10.30.0.101"}},  # de este
            {"id": 901, "name": "rta1", "ipAddress": {"address": "10.40.0.101"}},  # homónimo
        ]
        propios = converge.netxms_propios_de(self.NODOS, censo)
        self.assertEqual(propios, [526])
        propias = converge.netxms_alarmas_propias(
            [self.alarma(526), self.alarma(901, id=2)], propios)
        self.assertEqual([a["id"] for a in propias], [1])
        # La ficha del homónimo se sigue leyendo en el registro: sin ella no se sabe quién
        # lo creó y un resto no se puede retirar sin arriesgar el histórico de otro.
        self.assertEqual(converge.netxms_ids(self.NODOS, censo), [526, 901])


class LoQueElDestroyRetiraDeLaVista(unittest.TestCase):
    """La vista también se desmonta: por la marca, nunca por parecerse.

    Un destroy que deja equipos en rojo y el mapa de una red apagada no distingue
    «destruido» de «desplegado». Pero borrar es irreversible: sólo se retira lo que
    consta como de este laboratorio.
    """

    LAB = "b_router_dos_puestos"

    def nodo(self, id, name, address, marca=None):
        return {"id": id, "name": name, "ipAddress": {"address": address},
                "comments": f"netlabs lab={marca} role={name}" if marca else ""}

    def test_la_marca_es_la_que_escribe_el_motor_al_registrar(self):
        self.assertEqual(converge.netxms_marca_de(self.LAB),
                         "netlabs lab=b_router_dos_puestos")

    def test_solo_se_retira_lo_que_lleva_la_marca_de_este_laboratorio(self):
        censo = [
            self.nodo(1, "rta1", "10.30.0.101", marca=self.LAB),
            self.nodo(2, "rta1", "10.40.0.101", marca="otro_lab"),
            self.nodo(3, "swc1", "10.30.0.102", marca="otro_lab"),
        ]
        restos = converge.netxms_restos_de(censo, self.LAB)
        self.assertEqual([r["id"] for r in restos["suyos"]], [1])
        self.assertEqual([r["address"] for r in restos["suyos"]], ["10.30.0.101"])
        self.assertEqual(restos["dudosos"], [])

    def test_un_nombre_que_empieza_como_el_de_este_laboratorio_no_es_un_resto_suyo(self):
        """El nombre del laboratorio se compara ENTERO, no como prefijo de la marca.

        Demuestra el caso que se lleva por delante el histórico de otro laboratorio: un
        laboratorio cuyo nombre empieza por el de éste —`d_acme` y `d_acme_dos_sedes`—
        comparte el prefijo de la marca, y leerla como subcadena tomaba sus registros por
        restos de éste y pasaba sus números al borrado sin comprobar nombre ni dirección
        (AGENTS.md §3.6).
        """
        censo = [self.nodo(1, "rte1", "10.30.0.101", marca="d_acme_dos_sedes")]
        restos = converge.netxms_restos_de(censo, "d_acme")
        self.assertEqual(restos["suyos"], [])

    def test_un_registro_con_el_nombre_del_laboratorio_y_sin_marca_no_se_toca(self):
        """El nombre no demuestra quién lo creó: se dice, no se borra (AGENTS.md §3.6)."""
        restos = converge.netxms_restos_de([self.nodo(9, "wsp1", "10.30.0.150")],
                                           self.LAB, ["wsp1", "wsp2"], ["10.30.0.0/24"])
        self.assertEqual(restos["suyos"], [])
        self.assertEqual([r["id"] for r in restos["dudosos"]], [9])

    def test_un_registro_sin_marca_que_no_está_en_sus_redes_no_se_señala(self):
        """Señalar por el nombre solo acusaría a los equipos de otros laboratorios.

        Todos los laboratorios tienen un `wsp1` y un `rte1`: si bastara el nombre, cada
        destroy diría que los equipos ajenos son restos suyos.
        """
        censo = [self.nodo(9, "wsp1", "10.44.0.150", marca="otro_lab")]
        restos = converge.netxms_restos_de(censo, self.LAB, ["wsp1"], ["10.53.0.0/16"])
        self.assertEqual((restos["suyos"], restos["dudosos"]), ([], []))

    def test_sin_espacios_declarados_no_se_señala_a_nadie(self):
        restos = converge.netxms_restos_de([self.nodo(9, "wsp1", "10.30.0.150")],
                                           self.LAB, ["wsp1"])
        self.assertEqual((restos["suyos"], restos["dudosos"]), ([], []))
        restos = converge.netxms_restos_de([self.nodo(9, "wsp1", "no-es-una-ip")],
                                           self.LAB, ["wsp1"], ["10.30.0.0/24"])
        self.assertEqual(restos["dudosos"], [])

    def test_un_registro_sin_marca_que_no_es_del_laboratorio_no_se_nombra(self):
        restos = converge.netxms_restos_de([self.nodo(5, "netxms", "10.30.0.10")],
                                           self.LAB, ["wsp1"])
        self.assertEqual((restos["suyos"], restos["dudosos"]), ([], []))

    def test_sin_censo_no_hay_nada_que_retirar(self):
        restos = converge.netxms_restos_de(None, self.LAB)
        self.assertEqual((restos["suyos"], restos["dudosos"]), ([], []))

    def test_se_le_pasan_las_fichas_y_no_el_censo(self):
        """El censo no trae los comentarios; las fichas sí.

        Pasarle el censo al retirar daría «no queda nada» siempre —sin comentarios no hay
        marca que leer—, y el destroy daría por limpio un laboratorio que sigue en la vista.
        Por eso se le pasan las fichas, y por eso esto se prueba.
        """
        fichas = {"objects": [self.nodo(1, "rta1", "10.30.0.101", marca=self.LAB)]}
        self.assertEqual([r["id"] for r in
                          converge.netxms_restos_de(fichas, self.LAB)["suyos"]], [1])
        censo = [{"id": 1, "name": "rta1", "ipAddress": {"address": "10.30.0.101"}}]
        self.assertEqual(converge.netxms_restos_de(censo, self.LAB)["suyos"], [])

    def test_el_mapa_del_laboratorio_se_encuentra_por_su_nombre(self):
        hijos = [
            {"id": 3, "class": "NetworkMap", "name": "otro_lab",
             "comments": "netlabs lab=otro_lab"},
            {"id": 7, "class": "NetworkMap", "name": self.LAB, "comments": ""},
        ]
        self.assertEqual(converge.netxms_mapa_del_lab(hijos, self.LAB),
                         {"id": 7, "nombre": self.LAB, "comentario": "", "ajeno": False})

    def test_un_mapa_ajeno_con_el_mismo_nombre_no_se_retira(self):
        hijos = [{"id": 7, "class": "NetworkMap", "name": self.LAB,
                  "comments": "netlabs lab=otro_lab"}]
        self.assertTrue(converge.netxms_mapa_del_lab(hijos, self.LAB)["ajeno"])

    def test_un_mapa_con_una_nota_sin_marca_no_se_toma_por_ajeno(self):
        """Un comentario no vacío sin marca no demuestra que el mapa sea de otro.

        Demuestra que `ajeno` sólo lo activa la marca EXPLÍCITA de otro laboratorio: antes
        cualquier comentario lo hacía, y una nota como «revisar el lunes» bloqueaba tanto
        `apply` como `destroy` del propio mapa, que se llama como el laboratorio.
        """
        hijos = [{"id": 7, "class": "NetworkMap", "name": self.LAB,
                  "comments": "revisar el lunes"}]
        self.assertFalse(converge.netxms_mapa_del_lab(hijos, self.LAB)["ajeno"])

    def test_un_mapa_de_otro_cuyo_nombre_empieza_como_este_se_toma_por_ajeno(self):
        """La marca del mapa se compara entera: el prefijo de `b_router` no es `b_router_dos_puestos`.

        Demuestra que un mapa de otro laboratorio cuyo nombre empieza por el de éste no se
        reconoce como propio —lo que dejaría retirar su dibujo—: se toma por ajeno y se para.
        """
        hijos = [{"id": 7, "class": "NetworkMap", "name": self.LAB,
                  "comments": "netlabs lab=b_router"}]
        self.assertTrue(converge.netxms_mapa_del_lab(hijos, self.LAB)["ajeno"])

    def test_sin_mapa_no_hay_nada_que_retirar(self):
        self.assertEqual(converge.netxms_mapa_del_lab([], self.LAB)["id"], 0)
        self.assertEqual(converge.netxms_mapa_del_lab(None, self.LAB)["id"], 0)
        # Lo que cuelga de la raíz y se llama como el laboratorio pero no es un mapa
        # no se confunde con el suyo.
        self.assertEqual(converge.netxms_mapa_del_lab(
            [{"id": 2, "class": "Container", "name": self.LAB}], self.LAB)["id"], 0)

    def test_el_mapa_nace_con_su_marca_y_se_reconoce_como_suyo(self):
        cuerpo = json.loads(converge.netxms_mapa_crear_cuerpo(self.LAB, 4))
        self.assertEqual(cuerpo, {"class": "NetworkMap", "parentId": 4, "name": self.LAB,
                                  "comments": "netlabs lab=b_router_dos_puestos"})
        nacido = dict(cuerpo, id=11)
        self.assertEqual(converge.netxms_mapa_del_lab([nacido], self.LAB),
                         {"id": 11, "nombre": self.LAB,
                          "comentario": "netlabs lab=b_router_dos_puestos", "ajeno": False})


class LaIdentidadConLaQueSondeaLaVista(unittest.TestCase):
    """Con qué identidad sondea la vista a cada equipo: una sola, la del entorno (ADR 0019).

    El motor le dice a la vista lo mismo que le dijo al equipo, cada uno en su idioma: la
    vista llama `AES-128` a lo que RouterOS llama `AES` —medido contra la instalación, que
    contesta 400 a un `AES` a secas—, y a la comunidad de v2c la llama `authName`, porque
    para v1/v2c el nombre de la comunidad **es** con lo que se autentica. Como el grupo
    devuelve las claves al leerlo, la comparación es real y un `apply` repetido no escribe.
    """

    API = "http://127.0.0.1:8000/v1"
    V3 = {"usuario": "netlabs-ro", "autenticacion": "SHA256",
          "clave_autenticacion": "clave-de-autenticacion", "cifrado": "AES",
          "clave_cifrado": "clave-de-cifrado"}
    SECRETS = {"routeros_clave": "s3cr3t", "linux_clave": "l1nux", "snmp_v3": V3}
    OBS = {"snmp": {"version": 3, "credencial_from": "secrets.snmp_v3"}}
    AREA = {"enabled": True}
    PUESTO = {"version": "2c", "authName": "public", "authMethod": "NONE",
              "authPassword": "", "privMethod": "NONE", "privPassword": ""}

    def equipo(self, role="rte1", address="10.30.0.101", area=AREA):
        return {
            "role": role, "name": role, "type": "router", "mgmt_address": address,
            "description": f"netlabs lab=b_prueba role={role}",
            "configure": {"users": [{"name": "admin", "password_from": "secrets.routeros_clave"}],
                          **({"snmp": area} if area is not None else {})},
        }

    def censo(self, role="rte1", address="10.30.0.101", id_objeto=7):
        return [{"id": id_objeto, "name": role, "ipAddress": {"address": address}}]

    def ficha(self, role="rte1", address="10.30.0.101", id_objeto=7, snmp=None, **extra):
        return dict({
            "id": id_objeto, "name": role, "ipAddress": {"address": address},
            "sshLogin": "admin", "sshPassword": "s3cr3t", "sshPort": 22,
            "comments": f"netlabs lab=b_prueba role={role}",
            "snmp": dict(snmp if snmp is not None else self.PUESTO),
        }, **extra)

    def plan(self, equipo=None, censo=None, fichas=None, **extra):
        return converge.netxms_ops(equipo if equipo is not None else [self.equipo()],
                                   censo, fichas, self.API, self.SECRETS,
                                   observabilidad=self.OBS, **extra)

    def test_el_alta_lleva_la_identidad_dicha_como_la_dice_la_vista(self):
        """Un equipo nace sabiendo ya con qué se le sondea: no hay un rato en claro."""
        op = self.plan()["ops"][0]
        cuerpo = json.loads(op["cuerpo"])
        self.assertEqual(cuerpo["snmp"], {
            "version": "3", "authName": "netlabs-ro", "authMethod": "SHA256",
            "authPassword": "clave-de-autenticacion",
            # `AES` en el idioma de RouterOS es `AES-128` en el de la vista.
            "privMethod": "AES-128", "privPassword": "clave-de-cifrado",
        })

    def test_un_equipo_que_sondea_en_claro_se_pone_al_dia(self):
        plan = self.plan(censo=self.censo(), fichas=[self.ficha()])
        self.assertEqual(len(plan["ops"]), 1)
        self.assertIn("/objects/7/snmp", " ".join(plan["ops"][0]["cmd"]))
        self.assertIn("PATCH", " ".join(plan["ops"][0]["cmd"]))
        self.assertEqual(json.loads(plan["ops"][0]["cuerpo"]), {
            "version": "3", "authName": "netlabs-ro", "authMethod": "SHA256",
            "authPassword": "clave-de-autenticacion",
            "privMethod": "AES-128", "privPassword": "clave-de-cifrado",
        })

    def test_un_equipo_que_ya_sondea_como_debe_no_produce_ninguna_llamada(self):
        ya = {"version": "3", "authName": "netlabs-ro", "authMethod": "SHA256",
              "authPassword": "clave-de-autenticacion", "privMethod": "AES-128",
              "privPassword": "clave-de-cifrado"}
        self.assertEqual(self.plan(censo=self.censo(), fichas=[self.ficha(snmp=ya)])["ops"], [])

    def test_al_rotar_una_clave_se_reescribe_solo_esa_clave(self):
        """El `PATCH` es de fusión: lo que ya coincide no se vuelve a mandar."""
        ya = {"version": "3", "authName": "netlabs-ro", "authMethod": "SHA256",
              "authPassword": "la-vieja", "privMethod": "AES-128",
              "privPassword": "clave-de-cifrado"}
        plan = self.plan(censo=self.censo(), fichas=[self.ficha(snmp=ya)])
        self.assertEqual(json.loads(plan["ops"][0]["cuerpo"]),
                         {"authPassword": "clave-de-autenticacion"})

    def test_un_equipo_sin_el_area_no_lleva_identidad_en_su_alta(self):
        """Sin el área, el motor no toca SNMP en el equipo: la vista no tiene qué sondear."""
        op = self.plan([self.equipo(area=None)])["ops"][0]
        self.assertNotIn("snmp", json.loads(op["cuerpo"]))

    def test_un_equipo_sin_el_area_ya_registrado_no_se_toca(self):
        self.assertEqual(self.plan([self.equipo(area=None)], censo=self.censo(),
                                   fichas=[self.ficha()])["ops"], [])

    def test_sin_identidad_declarada_en_el_entorno_no_se_toca_el_sondeo(self):
        op = converge.netxms_ops([self.equipo()], [], [], self.API, self.SECRETS,
                                 observabilidad={})["ops"][0]
        self.assertNotIn("snmp", json.loads(op["cuerpo"]))

    def test_con_v2c_declarado_a_la_vista_se_le_dice_la_comunidad_del_entorno(self):
        """La comunidad es el `authName` de la vista: cambiarla es lo único que cambia."""
        secretos = dict(self.SECRETS, snmp_comunidad="lab-ro")
        obs = {"snmp": {"version": 2, "credencial_from": "secrets.snmp_comunidad"}}
        plan = converge.netxms_ops([self.equipo()], self.censo(), [self.ficha()],
                                   self.API, secretos, observabilidad=obs)
        self.assertEqual(json.loads(plan["ops"][0]["cuerpo"]), {"authName": "lab-ro"})

    def test_el_nombre_del_equipo_lo_dice_la_vista_con_su_identidad_no_con_sus_claves(self):
        """Lo que se imprime al aplicar no lleva material de clave."""
        plan = self.plan(censo=self.censo(), fichas=[self.ficha()])
        dicho = " ".join(o["effect"] for o in plan["ops"])
        self.assertIn("rte1", dicho)
        self.assertIn("SNMP v3", dicho)
        for secreto in self.V3.values():
            self.assertNotIn(secreto, dicho)

    def test_un_nodo_final_no_lleva_la_identidad_de_los_equipos_de_red(self):
        """Un puesto no habla SNMP: su salud se mira por ICMP, no por el grupo SNMP."""
        servidor = {"role": "svs1", "name": "svs1", "type": "server",
                    "description": "netlabs lab=b_prueba role=svs1",
                    "interfaces": [{"index": 0, "address": "10.20.66.10/24"}],
                    "configure": {"snmp": self.AREA}}
        op = self.plan([servidor])["ops"][0]
        self.assertNotIn("snmp", json.loads(op["cuerpo"]))


class LaTraduccionDeLaSalida(unittest.TestCase):
    """Lo que un router escribe cuando sale de verdad: traduce y resuelve.

    La traducción sale por la pata de la salida y sólo se reconoce como propia la
    que lleva el comentario del motor: una regla puesta a mano no se toca ni se pisa.
    """

    @staticmethod
    def nodo():
        return {"name": "rte1", "role": "rte1", "type": "router",
                "interfaces": [{"network": "lan", "index": 0},
                               {"network": "salida", "index": 1}]}

    def test_se_traduce_por_la_pata_de_la_salida(self):
        self.assertEqual(
            converge._nat_ops(self.nodo(), [{"out": "salida"}], []),
            [{"method": "PUT", "path": "/rest/ip/firewall/nat",
              "body": {"chain": "srcnat", "action": "masquerade",
                       "out-interface": "ether2", "comment": "netlabs-salida"},
              "effect": "traducir la salida por ether2 (masquerade)"}])

    def test_lo_ya_escrito_no_se_vuelve_a_escribir(self):
        actual = [{"chain": "srcnat", "action": "masquerade", "out-interface": "ether2",
                   "comment": "netlabs-salida", ".id": "*1"}]
        self.assertEqual(converge._nat_ops(self.nodo(), [{"out": "salida"}], actual), [])

    def test_una_regla_apagada_se_vuelve_a_encender(self):
        """Una regla propia apagada con `disabled: true` no traduce: hay que encenderla.

        Coincidir en interfaz, acción y cadena no basta si alguien la apagó: sin
        traducir, lo de dentro no vuelve del mundo, y el plan tiene que verlo.
        """
        actual = [{"chain": "srcnat", "action": "masquerade", "out-interface": "ether2",
                   "comment": "netlabs-salida", "disabled": "true", ".id": "*1"}]
        self.assertEqual(
            converge._nat_ops(self.nodo(), [{"out": "salida"}], actual),
            [{"method": "PATCH", "path": "/rest/ip/firewall/nat/*1",
              "body": {"disabled": "no"},
              "effect": "encender la traducción por ether2 (masquerade)"}])

    def test_lo_que_sobra_se_retira_y_lo_ajeno_no(self):
        actual = [{"chain": "srcnat", "action": "masquerade", "out-interface": "ether1",
                   "comment": "netlabs-salida", ".id": "*1"},
                  {"chain": "srcnat", "action": "masquerade", "out-interface": "ether1",
                   "comment": "puesta a mano", ".id": "*2"}]
        ops = converge._nat_ops(self.nodo(), [{"out": "salida"}], actual)
        self.assertEqual([o["method"] for o in ops], ["PUT", "DELETE"])
        self.assertEqual(ops[1]["path"], "/rest/ip/firewall/nat/*1")

    def test_una_salida_que_no_es_una_pata_se_rechaza(self):
        with self.assertRaises(LabError) as ctx:
            converge._nat_ops(self.nodo(), [{"out": "otra"}], [])
        self.assertIn("no es una red suya", str(ctx.exception))

    def test_una_regla_con_una_condicion_de_mas_se_reemplaza(self):
        """Una regla propia con una condición de más no traduce lo declarado: se reemplaza.

        Coincidir en interfaz, acción y cadena no basta si además trae un `src-address`:
        esa regla sólo traduce el tráfico de ese origen, y los clientes que salen por
        otra dirección se quedarían sin traducir sin que el plan lo dijera.
        """
        actual = [{"chain": "srcnat", "action": "masquerade", "out-interface": "ether2",
                   "src-address": "192.0.2.0/24", "comment": "netlabs-salida", ".id": "*1"}]
        ops = converge._nat_ops(self.nodo(), [{"out": "salida"}], actual)
        self.assertEqual([o["method"] for o in ops], ["PUT", "DELETE"])
        self.assertEqual(ops[1]["path"], "/rest/ip/firewall/nat/*1")

    def test_el_resolutor_se_escribe_solo_si_cambia(self):
        self.assertEqual(converge._dns_ops({"servers": ["1.1.1.1"]}, {"servers": "1.1.1.1"}), [])
        ops = converge._dns_ops({"servers": ["1.1.1.1", "9.9.9.9"]}, {"servers": ""})
        self.assertEqual(ops[0]["body"], {"servers": "1.1.1.1,9.9.9.9"})

    def test_el_resolutor_atiende_a_los_suyos_cuando_se_le_pide(self):
        ops = converge._dns_ops({"allow_remote_requests": True},
                                {"allow-remote-requests": "false"})
        self.assertEqual(ops[0]["body"], {"allow-remote-requests": "yes"})
        self.assertEqual(converge._dns_ops({"allow_remote_requests": True},
                                           {"allow-remote-requests": "true"}), [])


class LaEscuchaDeLosRegistros(unittest.TestCase):
    """La vista escucha los registros de los equipos, y sólo se toca lo que cambió.

    La variable que lo enciende se lee con el resto de la configuración del servicio, y cada
    variable dice si su cambio exige reiniciarlo: el motor no lleva su propia lista de nombres
    que reinician, se lo pregunta a quien lo sabe (ADR 0021).
    """

    API = "http://127.0.0.1:8000/v1"
    DECLARADO = {"recoger": True, "puerto": 514}

    @staticmethod
    def configs(escucha="0", puerto="514", reinicio=True):
        return [{"name": "Syslog.EnableListener", "value": escucha, "needServerRestart": reinicio},
                {"name": "Syslog.ListenPort", "value": puerto, "needServerRestart": reinicio}]

    def plan(self, declarado=None, actuales=None, escuchando=None):
        return converge.netxms_registro_ops(
            self.DECLARADO if declarado is None else declarado, actuales, self.API, escuchando)

    def test_una_escucha_apagada_se_enciende_y_pide_reinicio(self):
        plan = self.plan(actuales=self.configs(escucha="0"))
        self.assertEqual([o["effect"] for o in plan["ops"]],
                         ["que la vista escuche los registros de los equipos"])
        self.assertEqual(json.loads(plan["ops"][0]["cuerpo"]), {"value": "1"})
        self.assertIn("/server-config/Syslog.EnableListener", " ".join(plan["ops"][0]["cmd"]))
        self.assertIn("PUT", " ".join(plan["ops"][0]["cmd"]))
        self.assertTrue(plan["reiniciar"])

    def test_una_escucha_ya_encendida_no_produce_ni_llamada_ni_reinicio(self):
        plan = self.plan(actuales=self.configs(escucha="1"))
        self.assertEqual(plan["ops"], [])
        self.assertFalse(plan["reiniciar"])

    def test_el_valor_correcto_con_la_escucha_apagada_reinicia(self):
        """El agujero que se midió: escribir el valor y cortarse antes de reiniciar.

        La vista no tiene ningún campo que diga «esto está escrito y todavía no en vigor», así que
        el valor correcto no demuestra nada: manda que haya alguien escuchando el puerto. Sin esto,
        la pasada siguiente vería el valor correcto y no reiniciaría jamás.
        """
        plan = self.plan(actuales=self.configs(escucha="1"), escuchando=False)
        self.assertEqual(plan["ops"], [])
        self.assertTrue(plan["reiniciar"])

    def test_el_valor_correcto_con_la_escucha_en_pie_no_toca_nada(self):
        plan = self.plan(actuales=self.configs(escucha="1"), escuchando=True)
        self.assertEqual(plan["ops"], [])
        self.assertFalse(plan["reiniciar"])

    def test_sin_poder_medir_la_escucha_no_se_reinicia_a_ciegas(self):
        """Un `ss` que no está o que falla no es excusa para reiniciar el servicio en cada pasada."""
        plan = self.plan(actuales=self.configs(escucha="1"), escuchando=None)
        self.assertEqual(plan["ops"], [])
        self.assertFalse(plan["reiniciar"])

    def test_apagada_y_sin_escucha_no_reinicia_por_la_medida(self):
        """La medida sólo empuja a reiniciar cuando el entorno pidió escuchar, no cuando pidió callar."""
        plan = self.plan(declarado={"recoger": False}, actuales=self.configs(escucha="0"),
                         escuchando=False)
        self.assertEqual(plan["ops"], [])
        self.assertFalse(plan["reiniciar"])

    def test_un_puerto_distinto_se_corrige(self):
        plan = self.plan(actuales=self.configs(escucha="1", puerto="1514"))
        self.assertEqual(json.loads(plan["ops"][0]["cuerpo"]), {"value": "514"})
        self.assertIn("Syslog.ListenPort", " ".join(plan["ops"][0]["cmd"]))

    def test_una_variable_que_no_exige_reinicio_no_reinicia(self):
        plan = self.plan(actuales=self.configs(escucha="0", reinicio=False))
        self.assertEqual(len(plan["ops"]), 1)
        self.assertFalse(plan["reiniciar"])

    def test_una_variable_que_no_se_pudo_leer_se_reinicia_por_si_acaso(self):
        """Ante la duda, que el cambio surta efecto: creer encendido lo que está apagado engaña."""
        plan = self.plan(actuales=[])
        self.assertEqual(len(plan["ops"]), 2)
        self.assertTrue(plan["reiniciar"])

    def test_apagarla_tambien_es_converger(self):
        plan = self.plan(declarado={"recoger": False}, actuales=self.configs(escucha="1"))
        self.assertEqual(json.loads(plan["ops"][0]["cuerpo"]), {"value": "0"})
        self.assertIn("deje de escuchar", plan["ops"][0]["effect"])

    def test_sin_declaracion_no_se_toca_nada(self):
        self.assertEqual(self.plan(declarado={}, actuales=self.configs()),
                         {"ops": [], "reiniciar": False})

    def test_el_reinicio_dice_que_cambio(self):
        cmd = " ".join(converge.netxms_reinicio_cmd())
        self.assertIn("systemctl restart netxmsd", cmd)
        self.assertIn("CAMBIO:1", cmd)


if __name__ == "__main__":
    unittest.main()
