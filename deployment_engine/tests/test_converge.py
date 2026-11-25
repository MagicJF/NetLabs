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
    """El área `snmp` es del laboratorio: si no está, el motor no toca el servicio."""

    CIDR = "10.30.0.0/16"
    SECRETOS = {"snmp_comunidad": "lab-ro"}
    AREA = {"enabled": True, "community_from": "secrets.snmp_comunidad"}

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
            converge.ros_ops(self.nodo(), self.actual(), "clave", self.SECRETOS, self.CIDR), []
        )

    def test_enciende_snmp_y_sustituye_la_comunidad_abierta(self):
        ops = converge.ros_ops(self.nodo(self.AREA), self.actual(), "clave",
                               self.SECRETOS, self.CIDR)
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
        ops = converge.ros_ops(self.nodo(self.AREA), actual, "clave", self.SECRETOS, self.CIDR)
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
        ops = converge.ros_ops(self.nodo(self.AREA), actual, "clave", self.SECRETOS, self.CIDR)
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
            converge.ros_ops(self.nodo(self.AREA), actual, "clave", self.SECRETOS, self.CIDR), []
        )

    def test_una_comunidad_abierta_en_v3_se_baja_a_v2c(self):
        """Con `security` distinto de none, RouterOS no atiende la comunidad por v2c."""
        actual = self.actual(enabled="true", comunidades=[
            {".id": "*1", "name": "lab-ro", "addresses": self.CIDR,
             "read-access": "true", "write-access": "false",
             "authentication-protocol": "MD5", "encryption-protocol": "DES",
             "security": "authorized"},
        ])
        ops = converge.ros_ops(self.nodo(self.AREA), actual, "clave", self.SECRETOS, self.CIDR)
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
        ops = converge.ros_ops(self.nodo(self.AREA), actual, "clave", self.SECRETOS, self.CIDR)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["method"], "PATCH")
        self.assertEqual(ops[0]["body"], {"addresses": self.CIDR, "write-access": "no"})

    def test_el_lab_puede_declararlo_apagado(self):
        ops = converge.ros_ops(self.nodo({"enabled": False}), self.actual(enabled="true"),
                               "clave", self.SECRETOS, self.CIDR)
        self.assertEqual([(o["method"], o["body"]) for o in ops],
                         [("POST", {"enabled": "no"})])

    def test_sin_red_de_gestion_no_se_inventa_una_comunidad_abierta(self):
        with self.assertRaisesRegex(converge.LabError, "red de gestión"):
            converge.ros_ops(self.nodo(self.AREA), self.actual(), "clave", self.SECRETOS, None)

    def test_una_comunidad_que_no_esta_en_secrets_es_un_fallo(self):
        with self.assertRaisesRegex(converge.LabError, "snmp_comunidad"):
            converge.ros_ops(self.nodo(self.AREA), self.actual(), "clave", {}, self.CIDR)

    def test_el_encendido_va_marcado_para_su_propio_paso(self):
        # Encender antes de acotar deja el servicio expuesto mientras se acota. Y no
        # basta con ponerlo el último: una llamada que falla dentro del bucle no detiene
        # los elementos siguientes, así que el encendido llegaría igual con una comunidad
        # abierta. La marca es lo que `ros.yml` usa para partirlo en dos pasos.
        ops = converge.ros_ops(self.nodo(self.AREA), self.actual(), "clave",
                               self.SECRETOS, self.CIDR)
        self.assertEqual((ops[-1]["method"], ops[-1]["path"]), ("POST", "/rest/snmp/set"))
        self.assertTrue(ops[-1]["tras_restricciones"])
        for op in ops[:-1]:
            self.assertNotIn("tras_restricciones", op)

    def test_el_encendido_solo_sale_cuando_hace_falta(self):
        # Con SNMP ya encendido no hay marca ninguna: el paso propio del encendido se
        # queda sin elementos y el segundo apply no escribe.
        ops = converge.ros_ops(self.nodo(self.AREA), self.actual(enabled="true"),
                               "clave", self.SECRETOS, self.CIDR)
        self.assertEqual([o for o in ops if o.get("tras_restricciones")], [])

    def test_el_efecto_de_acotar_una_comunidad_no_lleva_su_nombre(self):
        # El nombre de una comunidad es su valor secreto y el efecto se imprime antes de
        # escribir: se nombra por su id interno, que no es secreto.
        ops = converge.ros_ops(self.nodo(self.AREA), self.actual(), "clave",
                               self.SECRETOS, self.CIDR)
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
        ops = converge.ros_ops(self.nodo(self.AREA), actual, "clave", self.SECRETOS, self.CIDR)
        self.assertEqual([(o["method"], o["body"]) for o in ops],
                         [("PATCH", {"disabled": "no"})])


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
    SECRETS = {"routeros_clave": "s3cr3t"}

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

    def test_un_servidor_con_direccion_estatica_se_registra_sin_credenciales(self):
        # Un nodo final no tiene la clave del RouterOS ni una pata de gestión: se
        # registra por su dirección estática y sin campos de SSH inventados.
        plan = converge.netxms_ops([self.servidor()], [], [], self.API, self.SECRETS)
        self.assertEqual(len(plan["ops"]), 1)
        cuerpo = json.loads(plan["ops"][0]["cuerpo"])
        self.assertEqual(cuerpo["ipAddress"], "10.20.66.10")
        self.assertNotIn("sshPassword", cuerpo)
        self.assertNotIn("sshLogin", cuerpo)

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


if __name__ == "__main__":
    unittest.main()
