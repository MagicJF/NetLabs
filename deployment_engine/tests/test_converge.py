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

    def test_un_equipo_que_ya_esta_como_debe_no_escribe_nada(self):
        # Idempotencia: un equipo que ya está con las credenciales puestas no produce
        # ninguna llamada, y por eso el segundo `apply` no escribe.
        encontrados = [{"id": 7, "ipAddress": {"address": "10.30.0.101"}}]
        detalles = [{"id": 7, "sshLogin": "admin", "sshPassword": "s3cr3t", "sshPort": 22}]
        plan = converge.netxms_ops([self.equipo()], encontrados, detalles, self.API, self.SECRETS)
        self.assertEqual(plan["ops"], [])
        self.assertEqual(plan["pendientes"], [])

    def test_un_equipo_ya_descubierto_con_otras_credenciales_se_reporta_y_no_se_toca(self):
        # El API de esta versión sólo acepta las credenciales al crear el equipo: uno ya
        # descubierto sin ellas no se borra para rehacerlo —se perdería lo recolectado—,
        # se dice en voz alta y lo cambia una persona en la consola.
        encontrados = [{"id": 7, "ipAddress": {"address": "10.30.0.101"}}]
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

    def test_las_fichas_se_piden_solo_por_los_equipos_de_este_laboratorio(self):
        # La búsqueda devuelve resúmenes sin credenciales: la ficha hay que pedirla, y se
        # pide de una vez y sólo por los equipos de este laboratorio —leer la de todos
        # para escribir uno sería leer de más—.
        encontrados = [
            {"id": 7, "ipAddress": {"address": "10.30.0.101"}},   # de este laboratorio
            {"id": 9, "ipAddress": {"address": "10.30.0.108"}},   # de otro
            {"id": 5, "ipAddress": {"address": "10.30.0.101"}},   # de este laboratorio
        ]
        ids = converge.netxms_ids([self.equipo()], encontrados)
        self.assertEqual(ids, [5, 7])
        self.assertEqual(json.loads(converge.netxms_fichas_cuerpo(ids)), {"ids": [5, 7]})


if __name__ == "__main__":
    unittest.main()
