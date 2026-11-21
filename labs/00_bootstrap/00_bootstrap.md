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
  Tomcat, no viene con el paquete `netxms-server`: sin Tomcat no hay interfaz
  web, sólo el servidor en `4701` y el API REST.
- **`netxms.matadepera.eu` sigue en 502** porque Caddy apunta a
  `10.10.10.254:8080`, una dirección que ya no responde. Apuntar al invitado
  de gestión no basta: falta la consola web.

