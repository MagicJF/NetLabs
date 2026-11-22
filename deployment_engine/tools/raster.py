# PROPÓSITO:   pasar a PNG el plano que el motor dibuja en SVG. El SVG es la verdad —lo
#              genera `tools/plano.py` desde la declaración—, pero hay visores de Markdown
#              que no pintan un SVG como imagen: enseñan el texto alternativo y el que abre
#              el documento ve un hueco. Un PNG lo enseña cualquiera.
# INVARIANTES: no dibuja nada: si el PNG y el SVG no cuentan lo mismo es que uno está
#              viejo, y el motor los escribe siempre juntos. Sin rasterizador no se
#              inventa un PNG a medias: se avisa y la página se queda con el SVG.
# VER:         deployment_engine/tools/docs.py, deployment_engine/tools/plano.py

from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile

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


def fuentes() -> list[pathlib.Path]:
    encontradas: list[pathlib.Path] = []
    for sitio in SITIOS_DE_FUENTES:
        if sitio.is_dir():
            encontradas.extend(sorted(sitio.rglob("*.ttf")))
            encontradas.extend(sorted(sitio.rglob("*.otf")))
    return encontradas


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
    """Escribe `png` a partir del SVG. Devuelve el aviso si no se pudo, o None."""
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False,
                                     encoding="utf-8") as temporal:
        temporal.write(svg_texto)
        ruta = pathlib.Path(temporal.name)
    try:
        orden = _orden(ruta, png)
        if orden is None:
            return ("sin rasterizador utilizable (resvg, rsvg-convert o inkscape) ni fuentes: "
                    "la página se queda con el SVG, que algunos visores no pintan")
        if comprobar:
            if not png.exists():
                return f"{png.name}: falta el PNG del plano (ejecuta `./netlabs docs`)"
            return None
        subprocess.run(orden, check=True, capture_output=True)
        return None
    except subprocess.CalledProcessError as error:
        detalle = (error.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        return f"el rasterizador falló con el plano: {detalle[-1] if detalle else error}"
    finally:
        ruta.unlink(missing_ok=True)