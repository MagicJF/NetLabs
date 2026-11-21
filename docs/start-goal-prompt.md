# /goal — NetLabs: motor de laboratorios sobre Proxmox, por API

## 1. Encargo en una frase

Construye desde cero, en `~/repos/netlabs` y publicado en `MagicJF/NetLabs`, un motor en Ansible que
despliega **un laboratorio** (un router RouterOS CHR y dos nodos finales LXC) en un nodo Proxmox
**sólo por su API**, le da identidad derivada, configura su interior, lo vigila desde NetXMS y lo
documenta de forma que no envejezca; con `plan`, `apply`, `destroy` y un conjunto de comprobaciones
que se ejecutan en CI. El diseño está escrito: **`/home/hermes/repos/netlabs/docs/diseno.md` es el documento
autoritativo**. Este encargo lo convierte en código; no lo rediseña.

## 2. Material de referencia — y lo que se rechaza

**Léelo en este orden:**

1. `/home/hermes/repos/netlabs/docs/diseno.md` — el diseño completo: actores, identificadores derivados,
   declaración, interior por áreas, verificación, versionado. Si algo de este encargo lo contradice,
   manda el documento (y avísalo en el informe). es la referencia autoritativa del proyecto y tiene que viajar con el código.
2. `~/repos/netlabs-iac` — el intento **anterior**. Vale como consulta de detalles de API ya
   probados, **no como modelo de estructura ni de estilo**.

**Lo que se rechaza de `netlabs-iac`, con su motivo (no lo reconstruyas):**

- **Ceremonia de capas**: `deployment_engine/tasks/`, `tools/`, `filter_plugins/`, `templates/` y un
  `docs/` con informes, encargos y revisiones selladas por hash. Aquí: un árbol pequeño (§4).
- **Registro paralelo**: `api.jsonl`, `interior.jsonl`, `console.jsonl` — diarios por llamada que
  nadie lee y que hay que mantener sincronizados. Aquí el registro es **el informe de Ansible**.
- **Verbo `verify` separado de `check`**: dos nombres para mirar lo mismo. Aquí hay **tres verbos** y
  las comprobaciones son CI.
- **Esperas a ciegas** (`sleep 420`, `while pgrep`): agotan el reloj. Aquí se sondea una condición
  con tope.
- **Documentación con dos escritores**: prosa y tablas generadas en el mismo fichero sin frontera.
  Aquí hay dos regiones con marcadores y un solo escritor por región.
- **Vocabulario del interior inventado por cada laboratorio** y Jinja ilegible de cuatro niveles.

**Lo que sí se conserva**: motor agnóstico del laboratorio; identidad derivada (sin fichero de
estado); declaración como única fuente de verdad; idempotencia medida; y documentación vigilada por
una comprobación, no por buena voluntad.

## 3. Paso 0 — el nodo y el repositorio

**3.1. Línea base del nodo (ya limpia; verifícala antes de empezar).** Los restos de los intentos
anteriores **ya se retiraron**: quedan exactamente tres puentes (`vmbr0` publicación de servicios,
`vmbr1` gestión con NAT, `vmbr22` segundo segmento de gestión), tres contenedores ajenos (100
`hermesagent` parado, 101 `caddy`, 105 `netbox`) y **ningún** invitado de laboratorio ni pool de
laboratorio. Compruébalo al empezar con `GET /nodes/<n>/network`, `/nodes/<n>/qemu`,
`/nodes/<n>/lxc` y `/pools`, y si aparece algo distinto, **para y pregunta** antes de tocar nada.

Si en el futuro vuelve a haber restos, el criterio es el siguiente — retira **sólo** lo que sea
inequívocamente de un laboratorio viejo:

- Puentes huérfanos: los que llevan un comentario `cable: ...` o la marca
  `lab=... gestionado por netlabs_v4_b` y que **ningún invitado usa** (`vmbr4`–`vmbr21`,
  `vmb_util` son candidatos; compruébalo uno a uno). Se borran con `DELETE /nodes/<n>/network/<iface>`
  y `PUT /nodes/<n>/network`.
- Pool `lab_00_netlab_utilities` si está vacío.
- **No toques nunca**: `vmbr0` (publicación de servicios), `vmbr1` (gestión con NAT), `vmbr22`
  (segundo segmento de gestión), ni los invitados ajenos **100** (`hermesagent`, parado), **101**
  (`caddy`), **102** (`ctl-vigilante`), **105** (`netbox`). Si algo no está claro, **pregunta**; no
  borres por si acaso. Deja en el informe: qué había, qué quitaste y qué dejaste.

**3.2. Repositorio: ya existe, no lo crees.** Está en `~/repos/netlabs` y es público
(`MagicJF/NetLabs`), con un primer commit que trae `AGENTS.md`, `docs/diseno.md`, `README.md` y
`.gitignore`. **Tu directorio de trabajo es ese repositorio.**

Antes de tu primera acción, confirma que tu contexto lleva las reglas del repositorio (`AGENTS.md`):
pregúntate si lo tienes delante y, si no, **léelo entero** — es el contrato de cómo se trabaja aquí. No
lo reescribas ni crees otro fichero de contexto al lado.

Commits en estilo convencional (`feat:`, `fix:`, `docs:`, `test:`, `chore:`), en imperativo y en
castellano. **Empuja pronto y a menudo** (rama corta por cambio y PR, o directo a `main` si es de una
línea); no acumules una semana de trabajo local.

**3.3. Credenciales.** `secrets.yml` en la raíz, **gitignored**, en texto plano (sin vault, sin
cifrado). Cópialo de `~/repos/netlabs-iac/deployment_engine/secrets.yml` y añade lo que falte. Nunca
se imprime, nunca se commitea.

Antes de nada, **verifica por API lo que el token puede hacer** (`GET /access/permissions`) y
escríbelo en el README como capacidad medida, no supuesta:

- Necesita: crear/borrar invitados y sus discos, crear/borrar puentes, pools, y
  `VM.GuestAgent.Audit` (leer el agente).
- Necesita además **`VM.GuestAgent.Unrestricted`** para el arranque de los routers (§6.5).
  **Ya está concedido** (verificado con el propio token): el rol `NetlabsMotorVms` incluye
  `VM.GuestAgent.Unrestricted`, `VM.GuestAgent.FileWrite` y `VM.GuestAgent.FileRead`, además de
  crear/borrar invitados, discos y redes. Si aun así una llamada devuelve *permission check
  failed*, **para y dilo** con la ruta y el privilegio que falta; no lo rodees con CLI ni SSH.

Datos del entorno ya verificados (úsalos, no los inventes):

| Dato | Valor |
| --- | --- |
| Nodo | `Proxmox`, PVE 9.2.21, `https://54.36.168.83:8006` |
| Almacenes | `local` (dir: `images`, `import`, `iso`) y `local-zfs` |
| Imagen del router | `local:import/chr-7.25.1.raw` (128 MB, CHR 7.25.1) |
| Plantilla LXC | la que haya en `local:vztmpl/` (si no hay, descarga una Debian estable) |
| Herramientas | ansible-core 2.22.0, ansible-lint 26.11.0, Python 3.13.5, jq 1.7, yamllint 1.38.0 en `~/.local/bin` |

## 4. Estructura como CONTRATO

```
netlabs                      # el ÚNICO punto de entrada (Python, stdlib); se ejecuta desde la raíz
netlabs.yml                  # configuración del motor (no del laboratorio): nada de labs aquí
secrets.yml                  # GITIGNORED
deployment_engine/
  playbooks/{plan,apply,destroy,site}.yml
  tasks/{pve.yml,ros.yml,interior_ssh.yml,bootstrap.yml}
  filter_plugins/identidad.py     # función pura: (mundo, declaración) → identidad
  templates/lab.md.j2             # esqueleto de la región generada
  tools/{plan.py,documentos.py,checks.py}
docs/diseno.md               # el diseño autoritativo (copia del documento de diseño)
labs/<lab>/<lab>.yml         # estado deseado de ESE laboratorio (fuente de verdad)
labs/<lab>/<lab>.md          # región generada + prosa libre
management/management.yml    # el plano de gestión (el servicio persistente); NO es un lab
test/                        # pruebas de la función de identidad, con fixtures
docs/decisiones/NNNN-*.md    # ADR: sólo decisiones caras de revertir
README.md  AGENTS.md  CHANGELOG.md  VERSION  .gitignore  requirements.txt
```

**Presupuesto de estructura**: nada de cuarto nivel de subdirectorios dentro de
`deployment_engine/`. Si un cambio lo pide, **para y justifícalo por escrito** en el PR. Un fichero,
un propósito.

## 5. Reglas duras (van también a `AGENTS.md`)

1. **Sólo API de Proxmox** (`/api2/json`). Prohibido `qm`, `pct`, `pvesh`, SSH al hipervisor,
   snippets y hookscripts. Si algo no se puede por API, **para y pregunta**.
2. **Una sola puerta por vía**: toda llamada al hipervisor pasa por `tasks/pve.yml`; a RouterOS por
   `tasks/ros.yml`; al interior Linux por `tasks/interior_ssh.yml`. Ningún otro fichero abre una
   conexión.
3. **Sin variables de entorno**: toda la configuración sale de `secrets.yml` + `netlabs.yml` + la
   declaración.
4. **El motor no contiene ni un valor de ningún laboratorio**: conoce reglas (el menor identificador
   libre del clúster, el pool se llama como la carpeta, la MAC se deriva del identificador), nunca
   valores. Y **no lee `labs/`**: el laboratorio es un parámetro.
5. **Nada derivado se guarda**: ni identificadores, ni MACs, ni ficheros de asignación. El estado se
   re-deriva leyendo la API.
6. **La MAC no se declara nunca**; se deriva del identificador. Si un YAML de lab tiene una MAC, es
   un bug.
7. **Idempotencia medida**: dos `apply` seguidos ⇒ el segundo `changed=0` y sin llamadas de escritura.
8. **El motor nunca borra** lo que no está en la declaración. `destroy` se niega si el invitado
   sigue declarado, y sólo actúa sobre el pool del laboratorio y sobre lo que lleva su marca.
9. **El interior es por áreas cerradas**: `identity`, `addresses`, `routes`, `dhcp_server`,
   `services`, `users`. Dentro de un área declarada, lo que sobra se quita; fuera, no se toca. Un
   laboratorio no puede inventarse primitivas: pide una nueva al motor, con ADR.

## 6. El motor: verbos y garantías

```
./netlabs plan    --lab <lab>     # qué haría, sin tocar el mundo
./netlabs apply   --lab <lab>     # lo hace y termina demostrando servicio
./netlabs destroy --lab <lab>     # lo retira; nunca toca lo ajeno
./netlabs apply   --site          # converge el plano de gestión (no es un lab; no se destruye)
./netlabs check   [nombre]        # comprobaciones del repositorio (esto es CI, no un verbo de despliegue)
```

**6.1. Identidad derivada** (`filter_plugins/identidad.py`, función pura y probada con fixtures):
identificador = el menor libre en **todo** el clúster; nombre = `<tipo>-<alias>`; MAC = función del
identificador en el rango `BC:24:11`; descripción = `lab=<lab> rol=<rol> gestionado por netlabs`;
dirección de gestión = función del identificador dentro del **/16** de gestión.
Tipos cerrados: `rt`, `fw`, `srv`, `ws`, `sw`, `ctl`.

**6.2. Redes y patas.** Las redes del laboratorio se declaran con nombre y CIDR y se referencian por
nombre; el orden declarado es el orden de las patas (`net0`, `net1`…). Cada red es un puente propio,
creado con la marca de propiedad. **La pata de gestión va la última** en routers y switches, y los
nodos finales **no la tienen**. Los espacios de direcciones de dos laboratorios no pueden solaparse:
**compruébalo en `plan`** contra lo que ya existe y contra el /16 de gestión.

**6.3. Ciclo de vida.** `plan` lee el mundo y calcula la diferencia (sin escrituras: demuéstralo con
un `plan` sobre un lab inexistente y otro sobre uno ya desplegado). `apply` converge: pool → puentes →
invitados → arranque → interior → rutas → verificación. `destroy` borra en orden inverso, se niega si
algo sigue declarado y jamás toca el pool de gestión.

**6.4. Orden de arranque**: etapa (`stage`) para lo grueso y `after: [rol, …]` para lo fino dentro de
la misma etapa. Nunca se arranca una etapa antes de que la anterior esté convergida y sirviendo.

**6.5. Arranque de un router sin dirección** (lo único que usa el agente del hipervisor; medido y
verificado): `POST /agent/file-write` con `encode=1` y el script en claro (el aviso `guest-file-close
timeout` es cosmético) y `POST /agent/exec` con `command=<fichero>`, luego `GET /agent/exec-status`
hasta `exited=1`; se acepta sólo con `exitcode=0` y la salida esperada. El script pone la dirección de
gestión en la última pata, habilita el servicio HTTPS de RouterOS y deja el usuario y la contraseña de
`secrets.yml`, **escrito para poder ejecutarse dos veces sin cambiar nada**. Después se lee
`/agent/network-get-interfaces` para confirmar que la dirección está puesta (esto basta con
`VM.GuestAgent.Audit`).

**6.6. Interior.** RouterOS: su REST (`/rest/...`) por la red de gestión, área por área. Linux (LXC):
SSH a su dirección del laboratorio con **una ruta estática en la máquina que ejecuta Ansible**
apuntando a la dirección de gestión del router; el router enruta, no se salta por dentro de él.

**6.7. El plano de gestión.** `management/management.yml` declara el servicio persistente: un LXC con
NetXMS (instalación y arranque con una tarea **idempotente**; si el paquete se resiste, documenta el
paso manual y sigue, sin fingir que está hecho). `apply --site` lo converge en su propio pool. Con
cada laboratorio, el motor le añade **las rutas** hacia las redes del lab y da de alta los invitados
en NetXMS por su API, si está disponible.

## 7. Verificación: qué significa «está bien»

- **Diferencia en los dos sentidos.** Las expectativas se derivan de la **declaración**, nunca de una
  lista literal: lo declarado que falta y lo que sobra sin declarar se cuentan por separado y ambos
  deben ser cero.
- **`apply` termina demostrando servicio**, no sólo existencia: el router contesta su REST, los
  clientes hacen ping a su puerta, NetXMS ve los nodos (consulta su API y guarda la respuesta).
- **El plan no escribe**: se comprueba con una ejecución sobre un lab inexistente y otra sobre uno
  desplegado.
- **Lo que una comprobación no puede probar, se dice** (por ejemplo, espacios de identificadores
  libres sin credenciales).

## 8. Documentación: un escritor por región

`labs/<lab>/<lab>.md` tiene dos regiones:

```markdown
<!-- generado:inicio -->
…tablas derivadas de la declaración (rol, tipo, recursos, redes, dirección, etapa)…
<!-- generado:fin -->

## Por qué así
…prosa libre: decisiones, trampas, qué se aprendió…
```

Dentro de los marcadores **no se escribe a mano**: lo reescribe `tools/documentos.py` desde la
declaración; `./netlabs check docs` falla si difiere de su render y la herramienta **falla, no
adivina**, si faltan o se duplican marcadores. Fuera, prosa libre y ningún check opina. La prosa no
repite valores de la región generada: los cita.

Reglas del repositorio para el agente: **un solo fichero de contexto**, `AGENTS.md`, ya escrito y
en la raíz del repositorio. Cumple lo que dice; si algo no encaja con lo que encuentras, dilo en el
informe **antes** de cambiarlo. Nunca `.hermes.md` al lado: lo dejaría invisible.

## 9. Estilo y comentarios

- Claves, ficheros, verbos y campos **en inglés** y literales de la API (`vmid`, `net0`, `scsi0`,
  `bridge`, `/ip/address`). La prosa y los comentarios, en castellano.
- `snake_case`, sin abreviar (`containers`, no `ctns`).
- Cabecera obligatoria en cada fichero: `PROPÓSITO`, `INVARIANTES`, `LÍMITES`, `VER` (puntero al
  doc/ADR/check).
- Constantes y rutas arriba del fichero. Jinja complejo: o se traduce a castellano en un comentario,
  o se mueve a un filtro comentado.

## 10. Calidad

Un solo comando corre todas las puertas offline: `./netlabs check` — enlaces, docs (render),
referencias, accesos (que nada fuera de las tres puertas abra conexiones), declaración (esquema y
tipos cerrados), espacios de direcciones, colisiones de nombres, pureza del motor (ni un valor de un
lab dentro de `deployment_engine/`) y README. Más `ansible-lint` y `yamllint` sin hallazgos nuevos.

**Cada comprobación debe haberse visto gritar**: rompe a propósito lo que vigila, comprueba que falla
con un mensaje que dice cómo arreglarlo, y déjalo escrito en el PR.

## 11. El laboratorio de ejemplo

Un `labs/uno/uno.yml` con: dos redes declaradas, un `rt` (CHR) con sus dos patas más la de gestión,
un `srv` y un `ws` (LXC) colgados de la red interna, `stage` y `after` explícitos, y áreas de interior
mínimas (`identity`, `addresses`, `routes`, `dhcp_server`, `services` en el router; `users` y
`addresses` en los Linux). Sin MACs, sin identificadores, sin direcciones de gestión: todo eso se
deriva. Cómo llevarlo a real, en orden: copiar `secrets.yml`, comprobar el token, `./netlabs plan`,
`./netlabs apply`.

## 12. Alcance del test final (definición de «hecho»)

Contra el nodo real, con la imagen y el token que ya existen:

```
./netlabs check                      # todo verde
./netlabs plan --lab uno             # plan coherente, sin escrituras
./netlabs apply --site               # el servicio persistente converge; NetXMS responde
./netlabs apply --lab uno            # converge en UNA pasada
./netlabs apply --lab uno            # segunda pasada: changed=0
./netlabs destroy --lab uno          # retira el lab; NetXMS y su pool intactos
```

Y la evidencia, pegada en el informe: salida real de cada comando, `changed` de la segunda pasada,
la respuesta del router por REST, el ping de un cliente a su puerta y la respuesta de NetXMS
mostrando el nodo. Sin esa salida, no está hecho.

## 13. Fuera de alcance (y dónde se extendería)

- **Fase 2** (dos sedes con tránsito y rutas estáticas): un laboratorio más, sin tocar el motor.
- **Agentes dentro de los invitados** (métricas de CPU/memoria): un área nueva del interior.
- **cloud-init / servicio de metadatos**: cerrado en este hipervisor (medido); no se persigue.
- **HA, multi-nodo, Windows, contenedores de aplicación, certificados**: nada de esto.
- **Consola serie**: puerta de emergencia a mano, nunca en el camino del motor.

## 14. Cómo trabajar y reportar

- **Capa por capa, verificando cada una**: repositorio y comprobaciones; identidad con sus pruebas;
  `plan`; `apply` (pool, puentes, invitados); arranque del router; interior; NetXMS; `destroy`; docs;
  CI; etiqueta `0.1.0`.
- **Pregunta en vez de inventar.** Si el diseño no cubre un caso, para, escribe la pregunta y sigue
  con lo demás.
- **Nada de afirmaciones sin salida**: cada «funciona» lleva el comando y su salida.
- **Apunta las trampas mientras las pisas** (por ejemplo: una oferta DHCP sale con checksum corrupto
  si no se apaga el *offload* de la tarjeta virtual; el agente devuelve `guest-file-close timeout`
  aunque el fichero llegue entero). Van al `AGENTS.md` y a la prosa del laboratorio.
- **Último paso**: guarda el procedimiento aprendido como skill (`netlabs`) con las trampas, los
  comandos exactos y lo que no hay que repetir.
