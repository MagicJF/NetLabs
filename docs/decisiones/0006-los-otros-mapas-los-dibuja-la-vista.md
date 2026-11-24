# 0006 — Los otros mapas los dibuja la vista, para comprobar el plano

**Fecha:** 24 de noviembre de 2026
**Estado:** aceptada
**Ámbito:** `deployment_engine/tools/mapa.py` (`generados`, `cuerpo_de_generado`),
`converge.netxms_generados_ops` y `tasks/netxms_mapa.yml`.
Continúa el **mapa a medida** (ADR 0003 abrió la vía, 0004 lo colocó, 0005 lo llenó de lo que
dice el YAML).

## El problema

El mapa del laboratorio lo dibuja el motor: es fiel al YAML porque sale de él, y esa fidelidad es
justo su límite —si el YAML se equivoca, el mapa se equivoca con él, y nada lo delata—. La vista
ofrece mapas que **se dibuja ella** con lo que sus equipos le cuentan. El cuadro «Create Network
Map» ofrece cinco tipos: Custom, Layer 2 topology, IP topology, Internal communication topology y
OSPF topology.

## Lo que se midió contra la vista (7.0.4, API v1)

- Un mapa **generado** se da de alta por el mismo `/objects` que el del plano, con `mapType`, la
  raíz de mapas como padre y dos campos que sí acepta: **`seedObjects`** —de dónde parte— y
  **`discoveryRadius`** —cuánto puede alejarse—. No acepta `filter` (400). Los tipos son los del
  API: `1` capa 2, `2` direcciones (`0` es el a medida).
- **El dibujo no viene en la respuesta del alta.** Recién dado de alta, `GET /objects/{id}/map`
  contesta sin elementos; unos segundos después contesta el mapa entero: lo compone el servidor
  cuando alguien lo mira. Una lectura inmediata parece un mapa vacío y no lo es.
- **El de capa 2 (mapType 1)** dibujó los **7 equipos del laboratorio y 5 enlaces** —los puertos
  que cada equipo dice ver por su base de reenvío—, y **el radio no cambia nada**: el dominio de
  capa 2 ya acota el dibujo (medido con radio 0, 1, 2 y 3: idéntico).
- **El de direcciones (mapType 2)** sigue las redes y las rutas, y con radio 1 dibujó **26
  equipos**: los 7 del laboratorio, los de los demás laboratorios y el propio servicio de
  gestión, porque todos comparten la red de gestión. Con radio 2 sólo se alejaba más. Es un mapa
  de la red, no del laboratorio, y así se dice.
- **Internal communication y OSPF** no se dan de alta: este motor enruta a mano, sin agentes ni
  protocolos de encaminamiento, y un mapa de lo que no existe no comprueba nada.
- **La semilla envejece**: el número de objeto de un equipo cambia cuando el invitado se rehace,
  y el API de esta versión no deja corregir la semilla de un mapa (ver `netxms_borrar_cmd`). Lo
  que sí se sabe sin preguntar es si el registro de equipos se ha tocado en esta pasada.

## La decisión

1. **Dos mapas de comprobación por laboratorio**, colgando de la raíz como el del plano y
   nombrados con su nombre: `<laboratorio> · capa 2` y `<laboratorio> · direcciones`. Al de capa
   2 se le da radio 0 y al de direcciones radio 1 —lo medido, no lo supuesto—.
2. **No se les escribe ni una coordenada.** El cuerpo que se manda sólo dice de dónde parte —los
   equipos del laboratorio, como semilla— y hasta dónde mira; el dibujo es del servidor. Por eso
   no se comparan con el plano ni se corrigen: se dan de alta y se miran.
3. **Se dan de alta si faltan, y se rehacen sólo si el registro de equipos se ha tocado** en esta
   pasada. Una segunda pasada no los toca —ni los vuelve a escribir—, que es lo que mantiene el
   `changed` diciendo la verdad.
4. **Lo que enseñan se dice en el informe**, y se dice que el de direcciones es de la red entera,
   para que nadie lea en él un mapa del laboratorio.
5. **Los mapas que no comprueban nada no se dan de alta**: ni el de comunicación interna ni el de
   OSPF, que describen protocolos que estos laboratorios no usan.
