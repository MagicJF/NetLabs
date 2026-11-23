# netlabs

Motor en Ansible que despliega laboratorios de red en un nodo Proxmox **sólo por su API**: crea los
invitados, les pone identidad sin que nadie la declare, configura su interior y lo documenta.

El diseño —qué es cada pieza y por qué— está en [`docs/diseno.md`](docs/diseno.md). Las reglas de
trabajo del repositorio, en [`AGENTS.md`](AGENTS.md).

## Estado

**En curso.** El motor está completo y verificado contra el hipervisor real. El laboratorio de
referencia `b_router_dos_puestos` se despliega con `./netlabs apply b_router_dos_puestos` y se retira
con `./netlabs destroy b_router_dos_puestos`.

## Las cinco vías de acceso

| A dónde | Por dónde |
| --- | --- |
| Hipervisor Proxmox | su API REST (`/api2/json`) |
| RouterOS | su REST, por la red de gestión |
| Interior de un Linux | SSH, con una ruta estática al router del laboratorio |
| Primer arranque de un router | el agente del invitado, por la API |
| El servicio que observa el sitio | su API REST, por el túnel, desde dentro de su invitado |

Ninguna otra. El motor no entra nunca por SSH al hipervisor ni usa su consola.

## Verbos

```
./netlabs plan    <lab>     # qué haría, sin tocar el mundo
./netlabs apply   <lab>     # lo hace y termina demostrando servicio
./netlabs destroy <lab>     # lo retira; nunca toca lo ajeno
./netlabs apply   --site    # converge el plano de gestión
./netlabs docs  [--check]   # regenera la tabla de cada laboratorio
./netlabs check             # comprobaciones del repositorio
```

## Estructura

Cada carpeta de primer nivel tiene **un solo dueño**. Si un fichero no encaja en esta tabla, está
en el sitio equivocado.

```
netlabs                    # punto de entrada único; se ejecuta desde la raíz
netlabs.yml                # configuración del SITIO (nodo, almacenes, gestión): no es un lab
secrets.yml                # credenciales; gitignored
deployment_engine/         # el motor: no conoce ningún laboratorio concreto
  playbooks/               #   los verbos de Ansible: plan, apply, destroy, site
  tasks/                   #   las cinco vías: pve, ros, interior_ssh, bootstrap, netxms
  filter_plugins/          #   el puente entre la capa pura y Ansible
  tools/                   #   identidad, convergencia, comprobaciones, documentación
  tests/                   #   pruebas de la capa pura, sin hipervisor
labs/<lab>/<lab>.yml       # el estado deseado de ESE laboratorio
labs/<lab>/<lab>.md        # sus dos planos (SVG en texto) + las tablas + lo aprendido
logs/<lab>/                # informes de ejecución; gitignored
logs/site/                 # informes del plano de gestión; gitignored
docs/                      # diseño y decisiones (ADR)
.coderabbit.yaml           # qué revisa CodeRabbit y qué no deja pasar
greptile.json              # qué revisa Greptile; las reglas del repositorio, en su idioma
.github/workflows/         # lo que se comprueba solo en cada PR: ./netlabs check
```

Reglas de la estructura:

- **La raíz no guarda código.** Sólo el punto de entrada, la configuración del sitio y la
  documentación. Un fichero nuevo en la raíz se justifica o se va a `docs/`. La configuración de
  las herramientas que miran el repositorio desde fuera —revisores, CI— vive en carpetas con punto
  (`.github/`), que no ensucian la raíz y no se mezclan con lo que se despliega. La excepción
  es `greptile.json`, que se queda en la raíz porque es donde su herramienta lo lee.
- **`deployment_engine/` no conoce ningún laboratorio.** No lee `labs/`: el laboratorio es un
  parámetro. Un valor concreto de un lab aquí es un bug.
- **`labs/<lab>/` sólo declara `<lab>.yml` y `<lab>.md`.** Los dos planos van dentro del `.md`
  como SVG en texto: son código generado, entran en el mismo diff que la declaración y no hay
  ficheros de imagen que regenerar. Nada de configuración global ni de ficheros de estado. Lo
  que se ejecuta no vive aquí.
- **El nombre de un laboratorio es una letra y un título** (`c_enrutar_y_conmutar`). La letra es la
  cabeza del nombre de cada cable y la que hace que el pool de Proxmox empiece por letra; ese nombre
  es también el de la carpeta, el del fichero y el del pool. Dos laboratorios no comparten letra, y
  `./netlabs check` lo comprueba.
- **El nombre de un equipo es su rol** (`rte1`, `swc2`): dos letras de tipo, una de función y el
  ordinal. Ese mismo nombre es el hostname del invitado, su nombre en Proxmox y la punta de cada
  cable que lo toca (AGENTS.md §3.8).
- **Los informes van a `logs/`.** Ni el motor ni los laboratorios guardan su propia salida.
- **`netlabs.yml` es del sitio, no de un laboratorio.** Dice qué hipervisor, qué almacenes y cómo
  se llega a la gestión; nunca qué invitados tiene un laboratorio concreto.

`./netlabs check` comprueba esta estructura: un fichero fuera de su sitio o una carpeta con dos
dueños es un fallo, no una convención.

## Credenciales

`secrets.yml` en la raíz, en texto plano y **gitignored**. Sin vault, sin cifrado: se escriben a mano.
Nunca se imprime su contenido ni se sube.
