# PROPÓSITO:   las pruebas de la marca que ata un PNG a su plano. Sin rasterizador no
#              se puede volver a dibujar para comparar, así que lo que se demuestra es la
#              única prueba posible: que el PNG dice de qué SVG salió, y que una marca
#              que no corresponde se ve.
# INVARIANTES: ninguna prueba escribe en el repositorio; trabajan en un directorio
#              temporal y corren con la biblioteca estándar (unittest).
# VER:         deployment_engine/tools/raster.py

import pathlib
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ / "deployment_engine" / "tools"))

import raster  # noqa: E402

# Un PNG mínimo y válido: cabecera e IEND, sin imagen. Basta para probar los trozos.
PNG_VACIO = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x00IEND\xaeB`\x82"


class LaMarcaDelPng(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.png = pathlib.Path(self.temporal.name) / "plano.png"
        self.png.write_bytes(PNG_VACIO)

    def tearDown(self):
        self.temporal.cleanup()

    def test_el_png_sellado_es_el_de_su_svg(self):
        """El PNG lleva dentro la huella del SVG del que salió, y se lee del fichero."""
        raster.sellar(self.png, "<svg>plano A</svg>")
        self.assertEqual(raster.comprobar_png("<svg>plano A</svg>", self.png), None)

    def test_un_svg_actualizado_deja_el_png_viejo_en_evidencia(self):
        """Un SVG nuevo junto a un PNG viejo no puede pasar: publicaría otra topología."""
        raster.sellar(self.png, "<svg>plano A</svg>")
        aviso = raster.comprobar_png("<svg>plano B</svg>", self.png)
        self.assertIsNotNone(aviso)
        self.assertIn("no corresponde", aviso)

    def test_un_png_sin_marca_no_se_da_por_bueno(self):
        """Un PNG que no dice de qué plano salió no demuestra nada, aunque exista."""
        aviso = raster.comprobar_png("<svg>plano A</svg>", self.png)
        self.assertIsNotNone(aviso)
        self.assertIn("no dice", aviso)

    def test_un_png_que_falta_se_dice(self):
        self.png.unlink()
        aviso = raster.comprobar_png("<svg>plano A</svg>", self.png)
        self.assertIsNotNone(aviso)
        self.assertIn("falta", aviso)

    def test_sellar_conserva_el_png_legible(self):
        """La marca va antes de IEND: el PNG sigue siendo un PNG."""
        raster.sellar(self.png, "<svg>plano A</svg>")
        datos = self.png.read_bytes()
        self.assertTrue(datos.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertTrue(datos.endswith(b"IEND\xaeB`\x82"))
        self.assertEqual(raster.marca_del_png(self.png), raster.huella("<svg>plano A</svg>"))


if __name__ == "__main__":
    unittest.main()