# 0020 — La vista no adivina, y por eso puede contradecir al motor

**Fecha:** 28 de noviembre de 2026
**Estado:** aceptada
**Ámbito:** la frontera entre lo que el motor declara y lo que la vista observa; el descubrimiento
automático de red; qué se considera un registro huérfano en la vista.

## El problema

El motor registra en la vista el inventario que él mismo va a desplegar. Si la vista no descubre
por su cuenta, ¿deja de ser una comprobación independiente? ¿Se traslada al observador el error del
observado —un motor que despliega mal y una consola que lo pinta bien—? La duda es legítima y toca
justo lo que este repositorio quiere conservar: que haya **alguien que pueda contradecir al motor**.

## La decisión

**1. El descubrimiento automático se queda apagado, y su sitio no lo ocupa nada.** Como *fuente del
inventario* seguirá siendo la declaración. Un rastreo abierto no añade rigor, añade vecinos: en un
espacio de gestión compartido por varios laboratorios arrastra equipos que no son de éste.

**2. La frontera se nombra, porque es la que sostiene todo lo demás.** El motor declara **qué debe
existir** y la vista mide **cómo está**. Ésa es la comprobación que se temía perder, y sigue entera,
pero conviene no exagerar su independencia: no todos los canales son igual de ajenos al motor, y
confundirlos sería vender una garantía que no existe. Se separan en tres.

- **Lo que la vista mide por su cuenta.** El estado, las interfaces, los contadores y si el equipo
  contesta salen de **sus** polls —ICMP cada pocos segundos, configuración cada ~30 s, SNMP y SSH
  contra el aparato—, no de nada que le diga el motor. Un equipo que el motor cree sano sale **en
  rojo** si no contesta.
- **Lo que el motor dibuja.** El **mapa** —sus áreas, equipos y cables— lo coloca el motor, y sus
  enlaces salen de `lab["links"]` (`mapa.contenido`), es decir, de la **declaración**, no de un
  sondeo. El mapa es el plano declarado, no un contraste del cableado: sirve para que la vista
  enseñe el laboratorio donde el plano dice, no para descubrir un cable que falta.
- **Lo que el motor modifica.** La vista no resuelve sola sus alarmas: al converger, el motor da por
  resueltas las de sus propios equipos (`netxms_alarmas_propias`), para no arrastrar un aviso que ya
  no está. La alarma, por tanto, no es un canal puramente observado: el motor también escribe en él.

El contraste **independiente** del cableado —la topología L2 real frente al plano del motor— es
justo la pieza que aún no está: llega con el P1 (tabla del puente, ADR 0019). Hasta entonces, los
enlaces del mapa son lo que el motor declaró, dicho con sus propias palabras.

**3. La independencia se pone donde renta**, que es donde ya estaba declarada: SNMP v3, registros y
poll de topología (P0), y el contraste de la topología L2 real contra el plano del motor (P1), todo
en ADR 0019.

**4. Lo que el descubrimiento sí cazaría —lo inesperado— se cubre con un barrido acotado y a
demanda**, y **como comprobación, no como fuente**. El acotamiento no es un trozo de red por
laboratorio —no existe: hay **una sola** red de gestión compartida, un /16 (10.30.0.0/16), con la
dirección de cada equipo derivada de su vmid (§3.3)—, sino el **plano de gestión entero**, que es
donde puede aparecer lo inesperado. El barrido recorre ese /16, contrasta lo que encuentra con lo
declarado emparejando **por nombre y dirección de gestión** —el mismo par con el que el motor
registra (§3.4)— y nombra lo que **no lleva la marca** `netlabs lab=…`, los **nombres repetidos** y
lo que responde donde no debería haber nada. **No borra nada por su cuenta**: mismo criterio que el
resto del motor, se dice en voz alta, no se actúa solo. Queda **pendiente** declarar el rango exacto
que recorre y su ritmo —un /16 son 65 536 direcciones, no un ping suelto—; mientras no exista, el
precio sigue siendo el de §«Lo que implica»: lo que existe y no está declarado es invisible.

## Por qué el descubrimiento no habría dado lo que se le pide

Encuentra **lo que hay**. Y en un laboratorio, lo que hay es exactamente lo que el motor fabricó: si
el motor construye lo incorrecto, el rastreo lo reporta como vivo, con toda su buena fe. Valida
**presencia y alcance**, no **intención**. La comparación contra lo declarado —la que sí distingue
«no está» de «no es mío»— no la sabe hacer.

## La medición

Medido sobre `f_acme_cuatro_departamentos` (28-nov-2026), después de un `apply`:

- **67 objetos** de clase `Node` en la vista. **65 llevan marca** `netlabs lab=…`. Los dos sin marca
  son el propio servidor de la vista y la puerta de gestión: no son de ningún laboratorio y nunca lo
  fueron.
- Conviven **tres generaciones**: `d_acme_dos_sedes` (parado), `e_tres_routers` (parado) y
  `f_acme_cuatro_departamentos` (en marcha). **Ni un solo registro huérfano.**
- La disciplina de la marca (ADR 0014) se sostiene: los laboratorios ya destruidos (`b_router_dos_puestos`,
  `c_enrutar_y_conmutar`) no dejaron ni una ficha.

Y el contraste ya produjo su primer hallazgo: el motor detectó **14 fichas** con nombre de sus roles
apuntando a direcciones que no son de sus invitados. **No son residuo**: son el equipo de los otros
dos laboratorios, que siguen existiendo, apagados. El motor **se abstuvo** de tocarlas por su marca,
y esa abstención es justo lo que hace fiable al contraste: prefiere dejar una ficha ajena que borrar
el histórico de otro.

## Lo que implica

- Un laboratorio apagado se ve **en rojo** en la vista, y es correcto: no es ruido, es la verdad.
  Borrar esas fichas para dejar la consola más limpia sería mentir sobre dos laboratorios que existen.
- Retirar un laboratorio del todo tiene **un solo camino**: `destroy`, que retira por marca —equipos,
  mapa e inventario— antes de tocar el hipervisor (ADR 0014). Que la vista deje de mostrar un
  laboratorio **sin destruirlo** es otra decisión, y se escribe aparte, con su motivo.
- **El precio, declarado:** un aparato que existe y no está declarado es **invisible** hasta que el
  barrido acotado lo nombre. Se acepta a cambio de no llenar la vista con vecinos ajenos.
- La topología L2 llega por la **tabla del puente (FDB)**, no por LLDP (ADR 0019): es la fuente con
  la que se contrasta el plano.
