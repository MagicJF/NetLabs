# 0023 — El DNS lo da la red: resuelve el router de la sede y sus puestos lo aprenden por DHCP

**Fecha:** 28 de noviembre de 2026
**Estado:** aceptada
**Ámbito:** `netlabs.yml` → `dns`; el área `dns` de un laboratorio; el servidor DHCP de sus routers;
`deployment_engine/tools/{identity,converge}.py` y `deployment_engine/tasks/ros.yml`.

## El problema

Desde la terminal de un puesto del laboratorio, `ping google.com` responde «Temporary failure in name
resolution». La salida a internet ya existe —cada sede tiene su pata de salida, traducida por NAT en
el nodo (ADR 0018)—, pero **nadie resuelve**: el puesto tiene puerta, no servidor de nombres. El
router de la sede *sabe* llegar al mundo por su salida, y sin embargo no se le había dicho ni a quién
preguntar ni que atendiera a los suyos.

## La decisión

El DNS es **de la red**, no del invitado: configuración cero dentro de los puestos.

- **El router de la sede resuelve y reenvía.** En RouterOS, `/ip dns` con una lista de servidores
  aguas arriba y `allow-remote-requests=yes`, que es lo que le permite atender las peticiones de su
  propia red. El puesto pregunta al router; el router pregunta fuera por su pata de salida.
- **El puesto lo aprende por DHCP.** El servidor de direcciones del router anuncia al **propio
  router** como servidor DNS en la opción de la red servida (`/ip dhcp-server/network`,
  `dns-server`). Los invitados Linux ya toman su dirección por DHCP, así que quedan resueltos solos:
  el motor no escribe un `resolv.conf` ni toca nada dentro de ningún invitado.
- **El laboratorio dice *si*, y nada más.** Su área `dns` es `{enabled}` —como `snmp` (ADR 0019)—.
  Con qué resolutor se hace es del **entorno**:

```yaml
dns:
  servers: [9.9.9.9, 1.1.1.1]
```

- **La dirección del resolutor vive en el entorno** —una sola vez, junto a la salida—, porque tiene
  que ser alcanzable **por la pata de salida de la sede**: los routers reenvían por ahí y el nodo
  Proxmox traduce ese espacio hacia su enlace público (ADR 0018). No puede ser la red de gestión ni
  el propio hipervisor —por la salida no se vuelve a casa (ADR 0018), y no resolverían un nombre de
  fuera—, así que se declara un resolutor **público**, alcanzable desde la salida sin abrir nada más.

El motor deriva lo que no se declara, y sólo escribe la diferencia: los puestos de un router que
resuelve aprenden la opción por DHCP, y una segunda pasada no escribe nada.

## Alternativas descartadas

- **Un `resolv.conf` (o un `/etc/systemd/resolved.conf`) dentro de cada invitado.** Es la tentación
  —una línea y funciona—, pero mete una segunda verdad dentro del invitado, duplica lo que la red ya
  puede dar, y obliga a tocar cada puesto y cada servidor. Si el invitado aprende su dirección por
  DHCP, tiene que aprender también a quién preguntar: es lo que hace cualquier red real.
- **Que cada laboratorio declare sus propios servidores DNS.** Dos sedes del mismo laboratorio
  podrían acabar preguntando a sitios distintos, y la dirección tendría que ser alcanzable por la
  salida de **esa** sede en concreto —una decisión que no es del laboratorio, igual que la identidad
  SNMP (ADR 0019)—. El laboratorio declara *si* resuelve; *con qué* lo dice el entorno.
- **Apuntar al resolutor del nodo o al de la red de gestión.** Por la salida no se vuelve a casa
  (ADR 0018): no son alcanzables desde la sede, y no resolverían un nombre de fuera.

## Lo que cuesta

Una dirección más en `netlabs.yml`, que se paga con este ADR. Y una dependencia honesta: si el
entorno no declara `dns.servers`, un laboratorio que diga `dns: {enabled: true}` **falla al
converger** —dice que no hay a quién preguntar— en vez de dejar a los puestos preguntando al vacío.
