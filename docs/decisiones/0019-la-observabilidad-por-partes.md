# 0019 — La observabilidad se enciende por partes, y empieza por lo barato

**Fecha:** 28 de noviembre de 2026
**Estado:** aceptada
**Ámbito:** la capa de observabilidad (NetXMS) y lo que declaran los equipos del laboratorio; los
routers RouterOS y los nodos finales Linux.

## El problema

La vista ve hoy los equipos por **SNMP v2c y por ICMP, y nada más**. La ficha de `rta1` —un RouterOS
CHR 7.25 desplegado— lo dice sin ambigüedad: Router sí, SNMP sí, Entity MIB sí; LLDP, CDP, OSPF,
Bridge, 802.1x y Agent, no. Y de las polls, la de **topología** aparece sin ejecutar (*not yet
retrieved*) con el descubrimiento de red en *never*.

Con eso:

- las **comunidades SNMP viajan en claro** por la red de gestión;
- **no se recoge un solo registro** de los equipos: nada explica *por qué* cayó una interfaz;
- no hay **topología L2 real** con la que contrastar el plano que dibuja el motor (ADR 0007);
- los **nodos finales Linux** existen sólo como «responde / no responde».

Enfrentarlo todo a la vez no es lo que este repositorio necesita: cada pieza tiene que poder
justificarse sola y **medirse** sobre un laboratorio desplegado, no sobre una lista de deseos.

## La decisión

Se enciende por partes, en orden de retorno sobre coste, y cada parte es su propio cambio, en su rama
y su PR.

**P0 — barato y de retorno inmediato**

1. **SNMP v3** en los equipos RouterOS y en su ficha de la vista, en lugar de la comunidad v2c en
   claro. RouterOS 7 la soporta entera y la vista también.
2. **Syslog**: los equipos envían sus registros a la vista, que los correlaciona.
3. **El poll de topología encendido.** Sin él, por mucho que un equipo anuncie vecinos, la vista no
   mira.

**P1 — la topología, con lo que sí es fiable**

4. La topología L2 se apoya en la **tabla de reenvío del puente (FDB/Bridge)**, no en el LLDP. El
   LLDP de MikroTik en NetXMS no es de fiar —es una limitación conocida, con hilos en el propio foro
   de NetXMS—; la tabla de direcciones del puente sí se lee.
5. Con la topología real delante, se contrasta con el plano del motor (ADR 0007): cuando discrepen,
   una de las dos miente y hay que saber cuál.

**P2 — la profundidad que sólo da un agente**

6. **Agente NetXMS en los nodos finales Linux** (CPU, memoria, disco, procesos). En RouterOS no
   existe agente: por eso su ficha pone «No» y ahí no hay nada que activar.

**Lo que no se enciende**

7. El **descubrimiento automático de red** se queda en *never*: el inventario de un laboratorio lo
   declara el motor, no lo adivina un rastreo. Un descubrimiento abierto llenaría la vista de vecinos
   ajenos al laboratorio.

**Lo que es material de laboratorio, no de monitorización**

8. OSPF, VRRP, BFD, 802.1x y VXLAN no se encienden para *mirar mejor*: se modelan como laboratorios,
   uno por protocolo, porque el valor está en poder romperlos. La vista los ve si existen —ésa es la
   razón de que tenga la capacidad—, pero no los inventa.

## Lo que implica

- Las capacidades de un equipo las detecta el **poll de configuración** de la vista. Tras un cambio
  en RouterOS hay que forzarlo para que la ficha deje de mentir: no se activan a mano.
- Queda anotada la **limitación del LLDP MikroTik ↔ NetXMS** para no volver a investigarla desde
  cero ni prometer lo que no da.
- El §7 de `docs/diseno.md` decía «sin agente en esta fase»; esta decisión lo sustituye por un P2
  declarado y con motivo.
- **Nada de esto se declara en un laboratorio**: se enciende en los equipos y en la vista, y por eso
  va aparte de los laboratorios. Pero **el motor no queda fuera del P0**: la migración a SNMP v3
  tendrá que adaptar también lo que el motor restaura. En un laboratorio que declare el área `snmp`,
  `_snmp_ops` (`tools/converge.py`) impone `security: none` —v2c— a la comunidad declarada y a las
  demás activas, y vuelve a encender las de fábrica: el `apply` siguiente desharía el v3 y
  devolvería el laboratorio al claro sin decirlo. Hasta que le llegue el turno, el motor se queda
  como está.
- **Antes del P0** lo que hay que comprobar es el camino entre la vista y los equipos —que el sondeo
  SNMP v3 y los registros lleguen por la red de gestión—, que es de lo que el P0 depende. La consola
  pública no está en ese camino: el motor habla con el servicio **desde dentro de su invitado**, por
  su API (`management.api`, `http://127.0.0.1:8000/v1`), que es por donde lee y coloca el mapa. Que
  `netxms.matadepera.eu:443` falle es del proxy que publica la consola, y no bloquea ni a la
  topología ni al syslog.
