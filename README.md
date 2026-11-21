# netlabs

Motor en Ansible que despliega laboratorios de red en un nodo Proxmox **sólo por su API**: crea los
invitados, les pone identidad sin que nadie la declare, configura su interior y lo documenta.

El diseño —qué es cada pieza y por qué— está en [`docs/diseno.md`](docs/diseno.md). Las reglas de
trabajo del repositorio, en [`AGENTS.md`](AGENTS.md).

## Estado

**En construcción.** El repositorio arranca con el diseño y las reglas; el motor aún no existe.
El orden de construcción está en el encargo que originó el proyecto.

## Las cuatro vías de acceso

| A dónde | Por dónde |
| --- | --- |
| Hipervisor Proxmox | su API REST (`/api2/json`) |
| RouterOS | su REST, por la red de gestión |
| Interior de un Linux | SSH, con una ruta estática al router del laboratorio |
| Primer arranque de un router | el agente del invitado, por la API |

Ninguna otra. El motor no entra nunca por SSH al hipervisor ni usa su consola.

## Verbos (previstos)

```
./netlabs plan    --lab <lab>     # qué haría, sin tocar el mundo
./netlabs apply   --lab <lab>     # lo hace y termina demostrando servicio
./netlabs destroy --lab <lab>     # lo retira; nunca toca lo ajeno
./netlabs apply   --site          # converge el plano de gestión
./netlabs check   [nombre]        # comprobaciones del repositorio
```

## Estructura

```
netlabs                 # punto de entrada único; se ejecuta desde la raíz
deployment_engine/      # el motor: no conoce ningún laboratorio concreto
labs/<lab>/<lab>.yml    # el estado deseado de un laboratorio
docs/                   # diseño y decisiones (ADR)
test/                   # pruebas de la identidad, sin hipervisor
```

## Credenciales

`secrets.yml` en la raíz, en texto plano y **gitignored**. Sin vault, sin cifrado: se escriben a mano.
Nunca se imprime su contenido ni se sube.
