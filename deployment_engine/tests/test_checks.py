# PROPÓSITO:   las pruebas de las comprobaciones que no necesitan hipervisor. Se
#              inventan los laboratorios y se comprueba que `check` ve lo que tiene
#              que ver: sin esto, una comprobación que deja pasar lo que debe cazar
#              es una comprobación que no existe.
# INVARIANTES: ninguna prueba toca el repositorio ni la API; corren con la biblioteca
#              estándar (unittest) y sustituyen la lectura de `labs/` por datos
#              inventados, para poder romper el caso a propósito.
# VER:         deployment_engine/tools/checks.py

import pathlib
import sys
import unittest
from unittest import mock

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ / "deployment_engine" / "tools"))

import checks  # noqa: E402


def entorno():
    return {"management": {"address_space": "10.30.0.0/16"},
            "salida": {"address_space": "172.30.0.0/16"}}


def lab(nombre, espacios, redes):
    """Un laboratorio de mentira con sus espacios y sus redes (nombre, CIDR, claves)."""
    return {"lab": nombre, "address_spaces": list(espacios),
            "networks": [{"name": n, "address": a, **extra} for n, a, extra in redes]}


class LosEspaciosDeSalida(unittest.TestCase):
    """Dos laboratorios no pueden compartir el tramo de una salida a la red pública.

    Las salidas no son redes del laboratorio —caen dentro del espacio del entorno, y
    eso es lo que se les pide—, pero sus direcciones viven juntas en el mismo
    hipervisor: el mismo tramo en dos laboratorios son dos puentes con la misma
    puerta, y las respuestas salen por el puente equivocado.
    """

    def comprobar(self, labs):
        rutas = {nombre: (RAIZ / "labs" / nombre / f"{nombre}.yml", cuerpo)
                 for nombre, cuerpo in labs.items()}
        with mock.patch.object(checks, "laboratorios", return_value=rutas):
            return checks.comprobar_espacios(entorno())

    def test_dos_laboratorios_con_el_mismo_tramo_de_salida_se_rechazan(self):
        errores = self.comprobar({
            "x_uno": lab("x_uno", ["10.44.0.0/16"],
                         [("salida", "172.30.10.0/24", {"exit": True})]),
            "y_dos": lab("y_dos", ["10.45.0.0/16"],
                         [("salida", "172.30.10.0/24", {"exit": True})]),
        })
        self.assertTrue(any("se pisa" in e for e in errores), errores)

    def test_dos_laboratorios_con_tramos_de_salida_distintos_pasan(self):
        # Y no se quejan de caer dentro del espacio de salida del entorno (172.30.0.0/16):
        # eso es justo lo que se le pide a una salida.
        errores = self.comprobar({
            "x_uno": lab("x_uno", ["10.44.0.0/16"],
                         [("salida", "172.30.10.0/24", {"exit": True})]),
            "y_dos": lab("y_dos", ["10.45.0.0/16"],
                         [("salida", "172.30.20.0/24", {"exit": True})]),
        })
        self.assertEqual(errores, [])

    def test_una_salida_no_pisa_la_red_interna_de_otro_laboratorio(self):
        errores = self.comprobar({
            "x_uno": lab("x_uno", ["10.44.0.0/16"],
                         [("salida", "172.30.10.0/24", {"exit": True})]),
            "y_dos": lab("y_dos", ["172.30.10.0/24"], []),
        })
        self.assertTrue(any("se pisa" in e for e in errores), errores)


if __name__ == "__main__":
    unittest.main(verbosity=2)
