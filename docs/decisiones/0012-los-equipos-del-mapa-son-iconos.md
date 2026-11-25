# 0012 — Los equipos del mapa se dibujan como iconos, no como etiquetas grandes

Fecha: 2026-11-25

## Contexto

La decisión 0007 quitó las fichas de texto de los equipos y dejó que cada uno se viera con la
**etiqueta grande** de la vista (`objectDisplayMode: 2`): nombre e IP junto al icono. La idea
era que esa etiqueta sustituyera al cartel que se había quitado, sin más adornos.

Con el laboratorio entero delante —veintiséis equipos, veinticinco cables y diez áreas— se ve
que no: una ficha por equipo ocupa más que el propio equipo, tapa los cables que pasan por
debajo y compite con las cabeceras de las áreas, que son las que de verdad orientan en el
dibujo. El nombre y la dirección de un equipo son un dato, no la lectura principal del mapa.

## Decisión

`objectDisplayMode` pasa a **icono** (`0`): cada equipo ocupa su hueco del plano y nada más.
Los números son los de la vista —`MapObjectDisplayMode`: `0` icono, `1` etiqueta pequeña,
`2` ficha grande, `3` estado, `4` plano de planta—, leídos de su código y no elegidos a ojo.

No se añade ningún cartel de texto a cambio: lo que se quiere leer del mapa son las áreas, sus
bloques y los equipos en su sitio. El nombre y la dirección de un equipo quedan en la vista,
a un clic, no encima del dibujo.

## Consecuencias

- El dibujo respira: los cables se ven enteros, que es lo que el mapa a medida existe para
  enseñar.
- Las cabeceras de las áreas —colocadas dentro de su área por la 0007— siguen siendo lo único
  escrito sobre el mapa, y por eso siguen leyéndose.
- Se pierde la lectura de la IP de un vistazo. Se acepta: el plano de la documentación sigue
  llevándola, y la vista la da al seleccionar el equipo.

Ver: `deployment_engine/tools/mapa.py` (`MODO_ICONO`, `AJUSTES_DEL_MAPA`),
`docs/diseno.md` §3.4, `docs/decisiones/0007-las-cabeceras-viven-dentro-de-su-area.md`.