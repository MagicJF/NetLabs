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
existir** —nombre, rol, dirección de gestión, credenciales de adopción y el dibujo del mapa—. La
vista mide **cómo está**. La vista no recibe del motor ni un solo dato de estado: el estado, las
interfaces, los enlaces, las alarmas y los contadores salen de **sus** polls —ICMP cada pocos
segundos, configuración cada ~30 s, SNMP y SSH contra el aparato—. Un equipo que el motor cree sano
sale **en rojo** si no contesta. Ésa es la comprobación que se temía perder, y sigue entera.

**3. La independencia se pone donde renta**, que es donde ya estaba declarada: SNMP v3, registros y
poll de topología (P0), y el contraste de la topología L2 real contra el plano del motor (P1), todo
en ADR 0019.

**4. Lo que el descubrimiento sí cazaría —lo inesperado— se cubre con un barrido acotado y a
demanda** del espacio de gestión del propio laboratorio, y **como comprobación, no como fuente**:
nombra lo que no lleva marca y los nombres repetidos, y **no borra nada por su cuenta**. Mismo
criterio que el resto del motor: se dice en voz alta, no se actúa solo.

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
