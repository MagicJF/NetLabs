# 0026 — La topología de capa 2 la dice la tabla del puente, y el motor la lee y la contrasta

**Fecha:** 28 de noviembre de 2026
**Estado:** aceptada
**Ámbito:** la fase P1 de la observabilidad (ADR 0019). Cómo se obtiene de verdad la topología de
capa 2 de un laboratorio, dónde la deja la vista, cómo el motor la lee, y qué se hace cuando no
cuadra con el plano. De dónde salió `physical_links` vacío.

## El problema

El ADR 0019 dejó el P1 enunciado así: «La topología L2 real por la **tabla del puente (FDB)**, no
por LLDP; con ella delante, se contrasta con el plano del motor». El arranque de la fase venía con
una observación de campo: el sondeo de topología **ya está encendido** —`Topology.PollingInterval`
en 1800 s, `Topology.EnableSTPDiscovery` en 1, el hook cargado, y el flag por equipo
`disableTopologyPoll` en `false`— y **no hay variable que lo apague**; el laboratorio
`f_acme_cuatro_departamentos` está desplegado. Y sin embargo la tabla `physical_links` de la base de
la vista **está vacía**: no ha descubierto un solo enlace de capa 2. La pregunta era por qué, y no
si encender algo.

## La averiguación

**1. `physical_links` está vacía porque no es la tabla del descubrimiento: es una tabla manual.** La
documentación de la vista lo dice —«Physical links … defined manually»— y el descubrimiento de capa
2 de NetXMS no escribe ahí. Que esté vacía es lo esperado, no un fallo del sondeo. La observación de
partida daba por hecho que «el poll corre y no ve nada»; lo medido es que **corre y sí ve, pero lo
deja en otro sitio**.

**2. Lo que la vista descubre queda en cada interfaz, como su vecina.** El detalle de una interfaz
—`/objects/details`— trae los campos `peerNodeId`, `peerInterfaceId` y `peerDiscoveryProtocol`: el
equipo que tiene al otro lado, su interfaz, y con qué lo supo. Medido en vivo en el laboratorio
desplegado, con la sesión del API del invitado de gestión:

    GET /objects/details      →  23 de las 25 interfases declaran `peerNodeId`
    ... "peerDiscoveryProtocol": 1, "peerDiscoveryProtocolText": "FDB"

El número `1` (texto «FDB») es la tabla de reenvío del puente. La documentación del servicio fija el
orden con el que resuelve la vecindad —driver del equipo, luego LLDP, CDP, NDP y STP, y **por último
la FDB**— y reserva STP y FDB a los equipos con capacidad de puente, precisamente lo que el ADR 0019
quería: **para un RouterOS que no publica LLDP de fiar, lo que manda es la FDB**. La vista, pues,
**ya ve** la topología de capa 2. No había que encender nada: había que leerla del sitio correcto.

**3. La vista descubre 23 de los 25 cables que declara el plano, no todos.** Se contrastó la
vecindad medida con `lab["links"]` del laboratorio. Las dos que la vista no ve son
`swc3 p1 ↔ rtp1 p1` y `swa2 p3 ↔ wsp4 p1`. Y en las dos, **la MAC del otro extremo SÍ está en la
tabla del puente del switch**, medida con `nxsnmpwalk` contra el propio equipo desde el invitado de
gestión:

    10.30.0.148 (swc3) dot1dTpFdbAddress →
      BC2411000930 : port 1   (swc3 ether1)
      BC2411000940 : port 1   (rtp1 ether1)   ← el extremo que la vista no enlazó, sí en la FDB
      BC2411000950 : port 2   (rte1 ether1)   ← éste la vista sí lo enlazó
    10.30.0.159 (swa2) dot1dTpFdbAddress →
      BC24110009E2 : port 3   (swa2 ether3)
      BC2411000A40 : port 3   (wsp4)          ← el extremo que la vista no enlazó, sí en la FDB

Es decir: **los dos cables existen** —el puente tiene aprendida la MAC al otro lado— y lo que falla
es la **correlación de la vista**, no el plano. La vista no inventa enlaces; lo que le pasa es que
se le pierden algunos que el puente sí tiene. El motivo exacto de la correlación perdida **no se ha
podido fijar**: la documentación describe la regla «un puerto con una sola MAC» como la que NetXMS
usa para atar un vecino, y los puertos implicados tienen dos MAC (la propia del puerto del switch y
la del vecino) —candidato plausible—, pero los puertos `swc3 p2` y `swc3 p3`, con la misma forma,
**sí** se resolvieron, así que ese candidato no queda demostrado y no se afirma.

**4. No hay sondeo forzado por el API en esta versión.** `POST /objects/{id}/poll/{tipo}` responde
404. El descubrimiento va al ritmo del temporizador del servidor (1800 s); el motor no puede pedir
una topología «ahora». Por eso el contraste es una **lectura** —lo que la vista tenga aprendido en
ese momento—, no una medida que el motor provoque.

## La decisión

**1. La capa 2 no se enciende: se lee.** El sondeo es de la vista y ya está en marcha; el motor no
gana ninguna palanca para encenderlo —no existe la que lo apagaría, así que no hay nada que
converger ahí—. Lo que el motor hace es **leer la vecindad que la vista ya descubrió por la FDB** y
decirla. `physical_links` no se toca: no es la tabla del descubrimiento.

**2. El contraste se declara en el entorno, no en el laboratorio.** `netlabs.yml` gana
`observabilidad.topologia: {contrastar: true}`, junto a `snmp` y `registro` y por el mismo motivo
(ADR 0019): mirar no es cosa de un laboratorio. El laboratorio no declara nada nuevo —su mínimo
sigue siendo `snmp: {enabled: true}` en el equipo, que es lo que hace que la vista lo pueda sondear
por SNMP y, con ello, leer su FDB—. `contrastar: false` lo apaga y el motor no gasta ni una llamada.

**3. El contraste dice quién discrepa, y no actúa.** La vista **no inventa enlaces** —los aprende
del puente—, así que:

- Un enlace que la vista **ve** y el plano **no declara** es del **plano** la falta: le sobra un
  cable por dibujar. El hallazgo viaja con su soporte (`FDB`), que es la evidencia.
- Un cable que el plano **declara** y la vista **no ve** sólo la delata a **la vista** cuando sus
  **dos puntas son equipos que el motor sondea** (router, switch, firewall): cruzan tramas siempre,
  así que el puente debería tenerlas, y si la vista no las enlaza es su descubrimiento —o que el
  cable no está—. Si **una punta es un nodo final** (un puesto, un servidor), la vista puede no
  haberlo visto hablar —el puente sólo aprende de tráfico, y un puesto callado no deja rastro— y
  entonces **no se concluye**: se dice «sin concluir» en vez de culpar a quien no consta.

En la medición, esto deja `swc3 ↔ rtp1` (dos equipos sondeados) del lado de la vista, y
`swa2 ↔ wsp4` (un puesto) como **sin concluir** —honesto: el motor no puede leer la FDB del switch
por el API, y no afirma lo que no puede medir—. Y a la vez, medido a mano, **los dos existen**, así
que el contraste que dice «sin concluir» no se equivoca: dice justo lo que no puede probar. Cuando
un cable entre dos equipos sondeados le falte a la vista, la prueba la da el propio puente
(`nxsnmpwalk` contra el switch, la misma medición de arriba), no el motor.

**4. El contraste es una lectura, y por eso una segunda pasada no escribe nada.** No añade ninguna
operación al `apply`: lee el censo, las fichas y el detalle de las interfaces —que el mapa ya lee— y
los cruza. La convergencia idempotente es la de siempre: lo que ya está, no se toca; y aquí no hay
nada que poner, sólo que mirar.

## Consecuencias

- La vista **ya ve** la capa 2 por la tabla del puente; queda dicho **dónde** lo deja (la vecindad de
  cada interfaz, no `physical_links`) para que nadie vuelva a buscar en la tabla equivocada.
- El motor gana una comprobación **independiente del plano** para el cableado (§7.1): la declara el
  entorno, la lee del sitio que la descubre, y dice cuál de los dos miente —o que no puede saberlo—.
- Queda escrito, con su medición, que **a la vista se le pierden enlaces** (2 de 25 en el
  laboratorio medido) aun teniendo la MAC en la FDB, y que el motivo no se ha fijado: es una
  limitación medida de la correlación del servicio, no del motor ni del plano.
- Si aparece una versión del servicio con sondeo forzado por el API, o que resuelva los puertos con
  más de una MAC, se revisa: el contraste no depende de eso para funcionar, sólo para acertar todos
  los cables.

## Ver también

- `docs/decisiones/0019-la-observabilidad-por-partes.md` — la fase y su reparto (P0/P1/P2).
- `docs/decisiones/0020-la-vista-no-adivina.md` — declarar el inventario no es pintar el resultado.
- `docs/decisiones/0004-el-mapa-de-la-vista-lo-coloca-el-plano.md` — el plano del motor, contra el
  que se contrasta.
- `docs/diseno.md` §7.1 y §7.4.
