# 0027 — El agente de la vista en los nodos finales Linux: lo enciende el laboratorio, lo instala el sitio

**Fecha:** 28 de noviembre de 2026
**Estado:** aceptada
**Ámbito:** la parte P2 de la observabilidad (ADR 0019): que un servidor (`svs`) o un puesto
(`wsp`) de un laboratorio se mire **por dentro** —CPU, memoria, disco y procesos— con el agente de
NetXMS, en vez de ser un «responde / no responde». De dónde sale el paquete del agente, cómo se
declara, cómo se comprueba que la vista lo ve, y por qué los equipos de red se quedan como están.

## El problema

Un nodo final Linux no habla SNMP: con SNMP la vista le sacaría las interfaces, no la salud. Hasta
ahora, su ficha en la vista era un `ping`: el invitado estaba «en verde» mientras contestara, sin
decir nada de su CPU, su memoria, su disco ni sus procesos. El ADR 0019 dejó esto como la parte P2 y
lo acotó a los nodos finales: «**En RouterOS no existe**: por eso su ficha pone «No» y ahí no hay
nada que activar.» La pregunta es, entonces, cómo se declara el agente y quién lo pone —el motor, no
alguien entrando a mano en el invitado—, y cómo se sabe que la vista lo está viendo de verdad.

## La averiguación

**El agente no está en la imagen.** El nodo final es Debian 13 (trixie) —

```
$ ssh root@10.50.55.10 cat /etc/os-release
PRETTY_NAME="Debian GNU/Linux 13 (trixie)"
VERSION_ID="13"
VERSION_CODENAME=trixie
```

— y en él **no hay agente ni paquete que lo ofrezca**: `apt-cache policy netxms-agent` no devuelve
nada (el repositorio de NetXMS no está configurado) y `dpkg -l | grep -i netxms` está vacío. El
agente vive en el repositorio propio del proyecto, y para esa imagen ofrece hasta **7.0.5-1+trixie**:

```
$ curl -fsSL https://packages.netxms.org/7.x/debian/dists/trixie/main/binary-amd64/Packages \
    | awk '/^Package: netxms-agent$/{p=1} p&&/^Version:/{print $2; p=0}' | sort -V | tail -1
7.0.5-1+trixie
```

Es decir: el paquete se puede instalar, pero hay que **añadir el repositorio** primero. Eso es lo que
el laboratorio no puede elegir por su cuenta, porque es del sitio.

**El agente lee un solo fichero de configuración, y su lista de acceso tiene tres escalones.** El
paquete 7.0.5-1 trae **sólo** `/etc/nxagentd.conf` (su `postinst` lo crea de una plantilla; su
`man 5 nxagentd.conf` no lista ningún otro fichero, y no hay directorio de fragmentos que el agente
lea además). La propia plantilla del paquete describe las tres listas de acceso del `[CORE]`, y por
ahí se ve cuál es la mínima:

- `MasterServers` — «full access to the agent (including remote configuration editing)».
- `ControlServers` — «query metrics and execute preconfigured actions (e.g. `System.Reboot`…)».
- `Servers` — «query metrics and **nothing more** — readonly mode».

**Quien detecta el agente es el poll de configuración, no el motor.** El API de la vista de esta
versión **no tiene sondeo forzado** (`POST /objects/{id}/poll/{tipo}` responde 404, medido en el P0:
ADR 0019), así que no se puede pedir «sondea ahora». Lo que queda es que la ficha del equipo diga, en
`capabilities.isNativeAgent`, si la vista le ha visto el agente; y eso lo enciende el poll de
configuración, que corre por temporizador (cada ~30 s, ADR 0020).

## La decisión

**1. Lo enciende el laboratorio y lo instala el sitio.** El nodo declara el área como declara `snmp`:

```yaml
configure:
  agente: {enabled: true}
```

y **con qué** se instala —el paquete y el repositorio— vive en el entorno (`observabilidad.agente`),
porque mirar no es cosa de un laboratorio: un nodo no elige quién le mira. Es el mismo reparto que la
identidad de SNMP (ADR 0019) y la escucha de registros (ADR 0021). La validación **rechaza** que un
laboratorio declare el paquete o el repositorio, y rechaza el área `agente` en un equipo de red
(RouteOS no lleva agente) y en el invitado de gestión (que **ya es** la vista y ya lleva el suyo:
declararlo ahí lo escribiría dos veces, en el mismo sitio donde corre el servicio).

**2. El plan lo expande a las áreas que el motor ya converge.** `agente: {enabled}` se convierte, en
la identidad, en: el repositorio del sitio, el paquete del agente, su fichero de configuración
(`/etc/nxagentd.conf`, con `[CORE] Servers=<espacio de gestión>` y los registros al diario) y su
servicio (`netxms-agent`) encendido. El interior del invitado se converge así con las **mismas**
tareas que cualquier Linux (`linux_ops`): el agente no estrena una vía de escritura, y el segundo
`apply` no escribe nada. El área declarada **se sigue viendo** en la ficha del plan: no se sustituye
por las cuatro áreas que produce.

**3. El agente acepta como lectora a la red de gestión y a nadie más.** `Servers`, la lista de
**sólo lectura**: CPU, memoria, disco y procesos se leen, y no hace falta que la vista pueda además
ejecutar acciones (`ControlServers`) ni reescribir la configuración del agente (`MasterServers`).
Como el agente lee un solo fichero, el motor escribe ahí el que declara —sustituyendo la plantilla
del paquete, que deja `MasterServers=127.0.0.0/8`—.

**4. No se fuerza el sondeo: se espera con tope, y agotarlo es un fallo.** Con el agente puesto, la
comprobación es la ficha del equipo: el motor la mira hasta que el poll de configuración diga
`capabilities.isNativeAgent: true`. Se sale en el instante en que lo dice —sin esperas a ciegas— y,
si el tope (20 intentos × 15 s) se agota, **la tarea falla y lo dice** con el equipo y el tiempo
esperado delante. No se tapa con `failed_when: false`: un laboratorio desplegado que no se puede
mirar por dentro no está desplegado. Un nodo cuya ficha ya lo dice no produce ninguna llamada, así
que la convergencia sigue siendo idempotente.

**5. Los equipos de red se quedan como están.** En RouterOS no hay agente que poner: su observación
sigue siendo SNMP (P0) e ICMP. Esto no cambia una línea de lo que ya había para ellos.

## Consecuencias

- Se declaró el agente en los doce nodos finales del laboratorio desplegado
  (`labs/f_acme_cuatro_departamentos`: `svs1`-`svs4` y `wsp1`-`wsp8`); cualquier otro laboratorio lo
  declara igual en el suyo.
- El entorno gana `observabilidad.agente` (`paquete`, `repositorio`) en `netlabs.yml`; el motor gana
  la expansión del área y la comprobación de la ficha.
- El invariante que el repositorio no perdona se respeta por los dos lados: nada espera a ciegas
  (se sondea con tope y se sale al cumplirse) y un agente que no aparece **se dice** (la tarea falla).
- **Lo que este ADR no puede afirmar sin desplegar:** que el paquete se instale y que la vista vea el
  agente **en vivo** exige un `apply` (tarda ~20 min y toca infraestructura desplegada), que no se
  ejecuta al escribir esto. Lo medido es la imagen y el repositorio (arriba, con sus comandos); lo
  comprobado en frío es la lógica pura (las pruebas) y las diez comprobaciones de `./netlabs check`.
