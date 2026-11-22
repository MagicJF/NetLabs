# netlabs — instrucciones para el agente

Lee esto entero antes de tocar nada. No es documentación del proyecto: son las reglas que hacen que
el proyecto siga siendo verdad dentro de dos semanas. El diseño está en `docs/diseno.md`; este fichero
dice cómo se trabaja sobre él.

## 1. Qué hay aquí

Un motor en Ansible que despliega laboratorios de red en un nodo Proxmox **sólo por su API**: crea
invitados, les pone identidad sin que nadie la declare, configura su interior y lo documenta. Un
laboratorio es un fichero YAML; el motor no sabe de ninguno en concreto.

Tres consecuencias que ordenan todo lo demás:

- **El laboratorio es un dato.** Si una línea del motor menciona un rol, una red o un número de un
  laboratorio concreto, es un bug, aunque funcione.
- **No hay estado guardado.** Lo que existe se lee del hipervisor cada vez. Un fichero de
  asignaciones es un bug: miente en cuanto alguien toca algo a mano.
- **Lo que no se demuestra, no se ha hecho.** Cada «ya funciona» va con el comando y su salida.

Y una frontera de carpetas que no se cruza: **cada carpeta de primer nivel tiene un solo dueño.**
`deployment_engine/` es el motor y no lee `labs/`; `labs/<lab>/` sólo declara `<lab>.yml` y
`<lab>.md`; los informes de ejecución van a `logs/`, nunca dentro del motor ni de un laboratorio;
`netlabs.yml` en la raíz es configuración del **sitio** (nodo, almacenes, gestión), no de un
laboratorio concreto. La raíz no guarda código. `./netlabs check` comprueba esta estructura: un
fichero fuera de su sitio es un fallo, no una convención.

## 2. Las cinco vías

Sólo hay cinco formas de hablar con el mundo, y cada una vive en un fichero. Si necesitas una
sexta, para y plantéala; no la abras por tu cuenta.

| A dónde | Por dónde | Fichero |
| --- | --- | --- |
| Hipervisor Proxmox | `https://<nodo>:8006/api2/json` | `tasks/pve.yml` |
| RouterOS | su REST, por la red de gestión | `tasks/ros.yml` |
| Interior Linux (LXC) | SSH a su dirección, con ruta estática al router | `tasks/interior_ssh.yml` |
| Primer arranque de un router | el agente del invitado, por la API | `tasks/bootstrap.yml` |
| El servicio que observa el sitio (NetXMS) | su API REST, por el túnel, desde dentro de su invitado | `tasks/netxms.yml` |

La cuarta existe por una razón concreta: un router recién creado **no tiene dirección**, así que no
hay a dónde hacer SSH ni dónde pedir su REST. El agente del hipervisor escribe un fichero y lo
ejecuta; es la única puerta que se abre antes de que exista red, y se cierra en cuanto la hay.

La quinta la abre el motor para **registrar cada equipo de red en lo que observa el sitio**, con su
usuario y su clave, de modo que quien mira lo vea en la consola y pueda abrir su terminal sin teclear
nada. Va contra el API del servicio de gestión, que escucha **dentro** de su invitado: se llama con
`curl` por la puerta de siempre (`interior_ssh.yml`), desde dentro. El servicio es **del sitio**, no
de un laboratorio (`netlabs.yml` → `management.api` y `secrets.yml`), y por eso el motor sí puede
nombrarlo aunque el laboratorio de control lo adopte como su nodo. Es una vía de **escritura de la
diferencia**: se dan de alta los equipos que faltan y se dice en voz alta lo que no se puede
corregir por el API (un equipo ya descubierto con otras credenciales). Sólo se abre donde el
laboratorio tiene algo que registrar —los equipos de red, no los puestos—, así que un laboratorio de
control no la usa. El porqué completo está en `docs/decisiones/0003`.

## 3. Lo que no se hace, y por qué

1. **No se usa `qm`, `pct`, `pvesh` ni SSH al nodo para desplegar.** Si el motor depende de la shell
   del hipervisor, deja de ser reproducible y deja de dejar rastro. La API es el contrato; la shell es
   una costumbre. (Para *diagnosticar* sí puedes entrar por SSH: su fruto debe ser una comprobación
   nueva o un mensaje de error mejor, nunca un atajo.)
2. **No se declaran números que se pueden derivar.** Ni identificadores, ni MACs, ni direcciones de
   gestión. Se derivan del identificador que elige el motor; si un YAML los lleva, es un bug. El
   **nombre de un equipo sí se declara entero** —dos letras de tipo, una de función y el ordinal—:
   es su identidad, y el motor la comprueba contra el tipo declarado en vez de adivinarla.
3. **No se escribe a mano dentro de lo generado.** Si el agente edita lo que genera la herramienta,
   el fichero pasa a tener dos verdades y la herramienta lo sobrescribe.
4. **No se añaden colecciones de Ansible.** Sólo `ansible.builtin`: una dependencia menos que explicar
   y que instalar.
5. **No se espera a ciegas.** Nada de `sleep 300`. Se sondea una condición con un tope; si el tope se
   agota, es un fallo, no un verde. Un `sleep` generoso esconde justo el fallo que buscabas.
6. **No se borra lo que no está declarado.** El motor actúa sobre el pool del laboratorio y sobre lo
   que lleva su marca. Todo lo demás es de otro y no se toca.
7. **No se configura fuera de las áreas que el laboratorio declara.** Dentro de un área, lo que sobra
   se quita; fuera, no se entra. Sin esta frontera, el motor se convierte en un `ssh` con esteroides.
8. **El hipervisor no conmuta: un puente es un cable tonto.** Un `bridge` de Proxmox une exactamente
   dos puertos y se llama por la letra del laboratorio y sus dos puntas,
   `<letra>_<equipo>p<puerto>_<equipo>p<puerto>` (por ejemplo `c_rte1p1_swc1p1`, 15 caracteres como
   tope). No lleva CIDR, ni puerta, ni MAC, ni DHCP, ni VLAN: esas cosas son del puerto, no del
   cable. Si un laboratorio necesita conmutar, se declara un nodo `switch` (un RouterOS) y se cablea
   como cualquier otro equipo. El nombre de cada equipo es su rol —dos letras de tipo, una de función
   y el ordinal— y ese mismo nombre es el del invitado, el de su hostname y el de la punta de cada
   cable que lo toca: un nombre, no tres. La punta mide seis caracteres, así que el cable cabe en los
   15 de un nombre de interfaz de Linux porque **el puerto es de una cifra**: nueve puertos cableados
   por equipo, y al agotarse el motor lo dice en vez de reventar al levantar el puente.

## 4. Quién pone los números

El laboratorio declara **qué** quiere: roles, tipo de equipo, puertos, cables (qué puerto une con qué
puerto) y qué configurar dentro. El motor decide **cuánto y cuál**: el identificador (el menor libre
del clúster), el nombre (`<tipo>-<alias>`), el nombre de cada cable, la MAC, la dirección de gestión y
la descripción que dice de quién es cada invitado.

Esa derivación es una función pura —(lo que hay en el mundo, lo que pides) → identidad— y por eso se
prueba con casos inventados, sin hipervisor. Si la tocas, la prueba va en el mismo commit.

## 5. Cómo se sabe que algo está bien

Tres pruebas, y ninguna se sustituye por otra:

- **La identidad no se repite**: dos laboratorios distintos, desplegados a la vez, no comparten un
  número. Se comprueba leyendo el clúster, no razonando.
- **El motor es idempotente de verdad**: el segundo `apply` no escribe nada. Si escribe, hay una
  decisión tomada por accidente.
- **La diferencia va en los dos sentidos**: lo declarado que falta y lo que sobra sin declarar son dos
  cuentas distintas y las dos deben dar cero. Contar sólo una es cómo se llega a un laboratorio
  «correcto» con basura dentro.

Y el cierre: `./netlabs check` en verde, más la salida real de `plan`, `apply` (dos veces) y `destroy`.
Si no puedes pegar esa salida, no lo cuentes como hecho.

## 6. Cómo se trabaja

- **Una capa cada vez, y verificada antes de la siguiente**: identidad → `plan` → `apply` → arranque
  del router → interior → observación → `destroy` → documentación. Una capa a medias contamina la
  siguiente y el fallo aparece tres capas más abajo.
- **Pregunta antes de suponer.** Si el diseño no cubre el caso, escribe la pregunta, sigue con otra
  capa y vuelve. Rellenar el hueco en silencio es cómo nacen las decisiones que nadie recuerda.
- **Rompe cada comprobación una vez.** Si no la has visto fallar, no sabes si comprueba algo.
- **Deja el rastro en el sitio correcto**: la decisión cara de revertir, en un ADR; la trampa
  descubierta al ejecutar, en la prosa del laboratorio; la regla que debe cumplirse siempre, aquí.
- **Empuja pronto.** Una rama corta por cambio, commits en imperativo y en castellano. Lo que no está
  en el remoto no existe para el resto.

## 7. Trampas ya pagadas

Están aquí para que no las pagues otra vez. Si encuentras una nueva, añádela.

- **`file-write` miente al cerrar**: responde *guest-file-close timeout* aunque el fichero llegue
  entero. Se da por bueno por el resultado de la ejecución (`exitcode=0` y la salida esperada).
- **El agente ejecuta por ruta, no por texto**: escribe el script a un fichero y ejecuta su nombre.
- **No hay servicio de metadatos** en este hipervisor: el router no pregunta a `169.254.169.254`.
  No pierdas una tarde con cloud-init.
- **El DHCP sale con el checksum mal** si la tarjeta virtual no tiene el *offload* apagado; el
  invitado descarta la oferta sin decir nada.
- **Un `permission check failed` no se rodea**: dice la ruta y el privilegio que falta, y se para.

## 8. Dónde mirar

- `docs/diseno.md` — el diseño y el porqué de cada pieza. Manda sobre este fichero.
- `docs/decisiones/` — las decisiones caras de revertir, con su alternativa descartada.
- `labs/<lab>/<lab>.md` — lo aprendido ejecutando ese laboratorio concreto.
- El código — cuando los tres anteriores callan, y entonces el comentario que falta se añade.

**Un solo fichero de contexto por repositorio.** Este. Nunca un `.hermes.md` al lado: Hermes lo carga
primero y este quedaría invisible, con lo que las reglas dejarían de aplicarse sin que nadie lo note.
