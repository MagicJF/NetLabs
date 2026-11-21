# Laboratorio `00_bootstrap`

Lo que se aprendió ejecutándolo va debajo de la tabla. La tabla se genera con
`./netlabs docs` y no se edita a mano: sale de la declaración.

<!-- netlabs:begin -- generado por `./netlabs docs`; no se edita a mano -->

## 00_bootstrap

Tipo: control (servicio persistente del sitio, sin topología).
Red: `vmbr30` (`10.30.0.0/16`), la de gestión.

### Nodes

| role | type | stage | address | resources |
| --- | --- | --- | --- | --- |
| `netxms` | control | 1 | management (derived) | — |

Configured areas: `commands`, `files`, `identity`, `packages`, `repositories`, `services`.

<!-- netlabs:end -->


## Lo aprendido al ejecutarlo

- **El pool no puede llamarse `00_bootstrap` en Proxmox.** La API exige que el
  nombre de un pool empiece por letra, así que el motor lo llama
  `lab-00_bootstrap` y el invitado de gestión vive ahí. El nombre del
  laboratorio sigue siendo `00_bootstrap`: sólo se prefija el pool.
- **El servidor no arranca sin esquema.** Con la base de datos vacía sale con
  `status=3/NOTIMPLEMENTED` y se queda en bucle de reinicio. `nxdbmgr init`
  crea el esquema una sola vez y deja una marca en disco; la marca es lo que
  hace que el segundo `apply` no repita el comando.
- **`nxdbmgr init` imprime la contraseña de `admin` una sola vez.** No se
  vuelve a mostrar: si se pierde, hay que recrear la base de datos. La
  contraseña generada no se guarda en el repositorio.
- **El Web API escucha sólo en loopback** (`127.0.0.1:8000`), así que no se
  alcanza desde fuera del invitado. La consola web (`nxmc`) es un WAR de
  Jakarta Servlet y no viene con el paquete `netxms-server`: sin contenedor no
  hay interfaz web, sólo el servidor en `4701` y el API REST.
- **La consola se despliega como WAR, no como paquete.** `tomcat11` sí está en
  trixie, pero el WAR se descarga de `netxms.com` (53 MB) y se suelta en
  `/var/lib/tomcat11/webapps/`. El comando lleva `creates` apuntando al propio
  WAR: se baja una vez y el segundo `apply` no lo repite.
- **La consola necesita saber a qué servidor hablar.** Sin
  `/usr/share/tomcat11/lib/nxmc.properties` (`server=127.0.0.1`) no arranca la
  aplicación. Es el classpath común de Tomcat, no el directorio del WAR.
- **El orden importa y no es cosmético.** Los ficheros se escriben antes que
  los comandos: `nxdbmgr init` lee `/etc/netxmsd.conf` para saber dónde está
  la base de datos. Con el orden inverso funcionó por casualidad —el fichero
  ya estaba de un `apply` anterior— y habría fallado en una máquina nueva.
- **El 502 era del proxy, no del invitado.** Caddy apuntaba a
  `10.10.10.254:8080`, una dirección que ya no responde. Se cambió a
  `10.30.0.103:8080` (el invitado de gestión) con copia de seguridad del
  `Caddyfile`; el cambio vive fuera del repositorio, en el contenedor de Caddy.
  La consola responde en `https://netxms.matadepera.eu/nxmc/`.

