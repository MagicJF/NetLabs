# 0009 — La terminal de un invitado Linux se abre con root y la clave del sitio

Fecha: 2026-11-25

## Contexto

NetXMS ya abre una terminal a los equipos de red porque su nodo se registra con la cuenta y la
clave de RouterOS. Un puesto o un servidor no tiene RouterOS: se registraba sólo por su
dirección, para que la vista lo dibujara y lo sondeara, y su consola no tenía con qué entrar.
La consecuencia era una asimetría visible: el mismo mapa enseñaba un router con terminal y un
puesto sin ella, aunque el invitado Linux estuviera vivo.

## Decisión

1. Todo invitado Linux de un laboratorio nace con la **clave pública del motor** autorizada.
   No es la clave de una persona: es la que el motor necesita para configurarlo, y ya era el
   camino del invitado de gestión.
2. Antes de registrar el nodo final en NetXMS, `apply` entra con esa clave y deja al invitado:
   - una contraseña de `root`, `linux_clave` de `secrets.yml`, una credencial del sitio;
   - un `sshd` que acepta contraseña de `root`;
   - la clave pública del motor autorizada, por si el invitado se recreó sin ella.
3. El nodo final se registra en NetXMS con `sshLogin: root`, `sshPassword: <linux_clave>` y
   `sshPort: 22`, igual que un equipo de red se registra con su cuenta. La terminal de la
   consola web abre la sesión por esa dirección, no por la del motor.
4. La contraseña **no viaja en la línea de órdenes**: el script la recibe por la entrada
   estándar y sólo la usa si la huella del marcador `/etc/netlabs-ssh` no coincide. El
   marcador guarda la huella, no la contraseña. Si coincide, el script contesta `CAMBIO:0` y
   no reinicia nada, así que el segundo `apply` sigue siendo idempotente.
5. El API de esta versión de NetXMS acepta `sshLogin` y `sshPassword` **sólo al crear** el
   nodo: `PATCH` los ignora y tampoco acepta `sshKeyId` al crear. Por eso un nodo final ya
   registrado sin credenciales se **retira y se vuelve a dar de alta** una vez; es la única
   manera de que su terminal abra. Un equipo de red en la misma situación sigue reportado como
   `pendiente`: borrarlo perdería su histórico y su identidad, y eso no se hace sin decirlo.

## Consecuencias

- El mapa de la vista es coherente: todos los equipos del laboratorio tienen terminal, y la
  de un puesto o servidor entra con `root` y la clave del sitio.
- La contraseña es del sitio y no del laboratorio: cambiar `linux_clave` y volver a aplicar
  reabre la puerta de todos los invitados; no hay que tocar cada YAML.
- El invitado no guarda la contraseña en claro: guarda su huella. La contraseña sí queda en
  `secrets.yml` y en el registro de NetXMS, como la de RouterOS, y por eso `secrets.yml` no se
  publica.
- El primer `apply` sobre un laboratorio anterior a esta decisión rehace sus nodos finales una
  vez. Es un cambio de identidad en la vista, no del invitado: las IP y el estado del
  laboratorio no cambian.
- Un nodo DHCP sin reserva sigue sin terminal ni registro: no hay dirección estable a la que
  entrar.

Ver: `docs/diseno.md` §3.4, `deployment_engine/tools/converge.py`,
`deployment_engine/tasks/linux_access.yml`, `deployment_engine/playbooks/apply.yml`,
`deployment_engine/tests/test_converge.py`.