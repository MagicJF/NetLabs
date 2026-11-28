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

**Lo que se midió en la instalación viva** (ya no es «lo que dice el código»):

- **Syslog: está apagado.** `Syslog.EnableListener = 0` y no hay nada escuchando en 514/udp. Se enciende con una variable **guardada en la base**, no en `netxmsd.conf`:
  `nxdbmgr set Syslog.EnableListener 1` —ya existe `nxdbmgr get/set`, y `-N` no reemplaza el valor si
  ya está: idempotente de serie—, **exige reiniciar el servicio**, y `Syslog.ListenPort` es 514 (por
  debajo de 1024 hace falta privilegio). Los mensajes van a la tabla `syslog` y se **atan a un equipo
  por su dirección de origen**: lo que venga de una fuente que no sea un equipo declarado **se
  descarta** salvo `Syslog.AllowUnknownSources=1` (hoy 0). Ese detalle es el que hace que un syslog
  «encendido» no registre nada y parezca que funciona.
- **Topología: no hay nada que encender — ya lo está.** `Topology.PollingInterval = 1800`,
  `Topology.RoutingTable.UpdateInterval = 300`, `Topology.EnableSTPDiscovery = 1`, el hook
  `TopologyPoll` se carga al arrancar, y **no existe ninguna variable que lo apague**: el flag por
  equipo (`flags.disableTopologyPoll`) ya está en `false`. El §7 decía «hoy sin ejecutar» y **eso es
  lo que estaba mal**. Pero encendido no es lo mismo que sirviendo: **`physical_links` está vacío**,
  no ha descubierto un solo enlace de capa 2. Lo que queda de esta parte no es encenderla, es
  averiguar por qué no ve nada —¿RouterOS no publica STP/LLDP en sus puentes como la vista espera,
  el radio de descubrimiento, la red de gestión?— antes de dar la topología por hecha.


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
  va aparte de los laboratorios. Pero **el motor no queda fuera del P0**, ni en los equipos ni en la
  vista. En RouterOS, un laboratorio que declare el área `snmp` pone la identidad v3 con
  `security: private` y apaga las comunidades v2c —antes `_snmp_ops` imponía `security: none` y
  volvía a encender las de fábrica, así que el `apply` siguiente habría deshecho el v3 sin decirlo—.
  Y en la vista se le dice **la misma identidad traducida a su idioma**, que no es el mismo: la
  instalación llama `AES-128` a lo que RouterOS llama `AES` y contesta 400 a un `AES` a secas, y a la
  comunidad de v2c la llama `authName`, que es lo que es. Se le dice por el grupo SNMP del equipo
  (`/objects/{id}/snmp`), que es el único sitio por el que su API acepta tocar cómo se sondea un
  equipo: las credenciales SSH sólo las acepta al crear, y por eso un equipo con la terminal bien y el
  sondeo en claro se quedaba así. Sin esto, retirar las comunidades en claro habría dejado a la vista
  sin poder sondear y el P0 sería decorativo.
- La consola pública **no está en ese camino**: el motor habla con el servicio **desde dentro de su
  invitado**, por su API (`management.api`, `http://127.0.0.1:8000/v1`), que es por donde lee el censo,
  da de alta los equipos, les dice con qué sondearlos y coloca el mapa. Que `netxms.matadepera.eu:443`
  falle es del proxy que publica la consola, y no bloquea ni a la topología ni al syslog.
- Quedan de esta parte —P0— la **recogida de registros** y el **poll de topología**; el sondeo v3
  está desplegado sobre el laboratorio `f_acme_cuatro_departamentos` y medido: los catorce equipos de
  red llevan la identidad v3 en su RouterOS con las comunidades v2c apagadas, la vista guarda esa
  misma identidad para los catorce, y desde el invitado de la vista —su propia herramienta, sus mismas
  credenciales— el equipo contesta a `authPriv` con `sysName.0: rte1` mientras la comunidad de fábrica
  por v2c **agota el tiempo**: ya no hay nadie contestando en claro. El API de esta versión no tiene
  sondeo forzado (responde 404 a `POST /objects/{id}/poll/{tipo}`), así que el sondeo de la vista se
  comprueba por sus credenciales y su estado —`snmpUnreachable: false`, driver `MIKROTIK`—, no por una
  ejecución a demanda.
