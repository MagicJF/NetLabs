# PROPÓSITO:   pasar a PNG el plano que el motor dibuja en SVG. El SVG es la verdad —lo
#              genera `tools/plano.py` desde la declaración—, pero hay visores de Markdown
#              que no pintan un SVG como imagen: enseñan el texto alternativo y el que abre
#              el documento ve un hueco. Un PNG lo enseña cualquiera.
# INVARIANTES: no dibuja nada: si el PNG y el SVG no cuentan lo mismo es que uno está
#              viejo. El PNG lleva dentro la huella del SVG del que salió, y es lo que
#              `./netlabs check` compara: sin rasterizador no se puede volver a dibujar
#              para saberlo. Sin rasterizador no se inventa un PNG a medias: se avisa y
#              la página se queda con el SVG.
# LÍMITES:     necesita un rasterizador externo instalado (resvg, rsvg-convert o
#              inkscape) y una fuente del sistema que dibujar; sin ninguno de los dos no
#              hay PNG. No valida el dibujo: que el SVG cuente la declaración lo prueba
#              `tools/plano.py` y sus pruebas.
# VER:         deployment_engine/tools/docs.py, deployment_engine/tools/plano.py

from __future__ import annotations

import hashlib
import pathlib
import shutil
import struct
import subprocess
import tempfile
import zlib

# Dónde puede haber una fuente. Sin fuentes, un rasterizador no dibuja ni una letra: el
# plano saldría con las cajas y los cables y ni un nombre, y eso es peor que un hueco,
# porque parece que el diagrama está bien.
SITIOS_DE_FUENTES = (
    pathlib.Path.home() / ".local/share/fonts",
    pathlib.Path.home() / ".fonts",
    pathlib.Path("/usr/share/fonts"),
    pathlib.Path("/usr/local/share/fonts"),
)

# La familia con la que se resuelve lo que el SVG no encuentre. El SVG pide Inter y
# parientes —que es lo que hay en un escritorio— y aquí se cae a la que exista.
FAMILIA_DE_APOYO = "DejaVu Sans"

# La clave del trozo `tEXt` que ata cada PNG a su plano. Un PNG con la huella de otro
# SVG publica una topología que ya no es la declarada.
MARCA = "netlabs-svg"


def fuentes() -> list[pathlib.Path]:
    encontradas: list[pathlib.Path] = []
    for sitio in SITIOS_DE_FUENTES:
        if sitio.is_dir():
            encontradas.extend(sorted(sitio.rglob("*.ttf")))
            encontradas.extend(sorted(sitio.rglob("*.otf")))
    return encontradas


def huella(svg_texto: str) -> str:
    """La huella del SVG: lo que ata un PNG a su plano."""
    return hashlib.sha256(svg_texto.encode("utf-8")).hexdigest()


def marca_del_png(png: pathlib.Path) -> str | None:
    """La huella que el PNG lleva dentro, o None si no la lleva.

    Se lee el PNG a mano (cabecera, trozos y CRC) porque la biblioteca estándar no
    lee metadatos de imagen y no hay dependencias por añadir.
    """
    datos = png.read_bytes()
    if datos[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos = 8
    while pos + 12 <= len(datos):
        largo, tipo = struct.unpack(">I4s", datos[pos:pos + 8])
        if tipo == b"tEXt":
            clave, _, valor = datos[pos + 8:pos + 8 + largo].partition(b"\x00")
            if clave == MARCA.encode("ascii"):
                return valor.decode("ascii", "replace")
        pos += 12 + largo
    return None


def sellar(png: pathlib.Path, svg_texto: str) -> None:
    """Escribe en el PNG la huella del SVG del que salió.

    Sin ella, un SVG actualizado junto a un PNG viejo pasa todas las comprobaciones y
    publica una topología incorrecta; y `./netlabs check` no puede volver a rasterizar
    para averiguarlo, porque el rasterizador puede no estar donde corre el check.
    """
    datos = png.read_bytes()
    if not datos.endswith(b"IEND\xaeB`\x82"):
        raise OSError(f"{png}: no es un PNG que termine en IEND")
    trozo = MARCA.encode("ascii") + b"\x00" + huella(svg_texto).encode("ascii")
    marca = struct.pack(">I", len(trozo)) + b"tEXt" + trozo
    marca += struct.pack(">I", zlib.crc32(b"tEXt" + trozo) & 0xFFFFFFFF)
    png.write_bytes(datos[:-12] + marca + datos[-12:])


def comprobar_png(svg_texto: str, png: pathlib.Path) -> str | None:
    """¿Es este PNG el del plano? Se dice lo que falta, o None si está bien."""
    if not png.exists():
        return f"{png.name}: falta el PNG del plano (ejecuta `./netlabs docs`)"
    marca = marca_del_png(png)
    if marca is None:
        return (f"{png.name}: el PNG no dice de qué plano salió "
                "(ejecuta `./netlabs docs`)")
    if marca != huella(svg_texto):
        return (f"{png.name}: el PNG no corresponde al plano actual "
                "(ejecuta `./netlabs docs`)")
    return None


def _orden(svg: pathlib.Path, png: pathlib.Path) -> list[str] | None:
    """La orden del primer rasterizador que haya, con sus fuentes si las necesita."""
    if shutil.which("resvg"):
        tipos = fuentes()
        if not tipos:
            return None  # dibujaría cajas y cables sin una sola letra
        orden = ["resvg"]
        for tipo in tipos:
            orden += ["--use-font-file", str(tipo)]
        return orden + ["--sans-serif-family", FAMILIA_DE_APOYO, str(svg), str(png)]
    if shutil.which("rsvg-convert"):
        return ["rsvg-convert", "-o", str(png), str(svg)]
    if shutil.which("inkscape"):
        return ["inkscape", str(svg), "--export-type=png", f"--export-filename={png}"]
    return None


def rasterizar(svg_texto: str, png: pathlib.Path, comprobar: bool = False) -> str | None:
    """Escribe `png` a partir del SVG. Devuelve el aviso si no se pudo, o None.

    `comprobar` no dibuja: sólo pregunta si el PNG que hay es el de este SVG, y por eso
    funciona donde no hay rasterizador.
    """
    if comprobar:
        return comprobar_png(svg_texto, png)
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False,
                                     encoding="utf-8") as temporal:
        temporal.write(svg_texto)
        ruta = pathlib.Path(temporal.name)
    try:
        orden = _orden(ruta, png)
        if orden is None:
            return ("sin rasterizador utilizable (resvg, rsvg-convert o inkscape) ni fuentes: "
                    "la página se queda con el SVG, que algunos visores no pintan")
        subprocess.run(orden, check=True, capture_output=True)
        try:
            sellar(png, svg_texto)
        except OSError as error:
            return f"{png.name}: el rasterizador no dejó un PNG que se pueda marcar ({error})"
        return None
    except subprocess.CalledProcessError as error:
        detalle = (error.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        return f"el rasterizador falló con el plano: {detalle[-1] if detalle else error}"
    finally:
        ruta.unlink(missing_ok=True)