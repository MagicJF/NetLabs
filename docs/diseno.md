# Netlabs · documento de diseño

**Para quien lo construye.** Este documento es el encargo. Describe un sistema que todavía
no existe. Lo que no esté aquí se decide con los principios de §2 y se anota como decisión
donde se implementa.

**Referencia autorizada y con reservas.** Existe un repositorio previo,
`/home/hermes/repos/netlabs-iac`, que puede consultarse. **No es un modelo a seguir**: fue un
desarrollo prematuro que llegó a verde y desplegó laboratorios reales, con aciertos claros (la
separación motor/laboratorio, la documentación comprobada) y errores y decisiones mal tomadas
(ceremonia excesiva, ficheros y capas de más, un vocabulario del interior que se volvió un
laberinto, despliegues lentos con esperas a ciegas, y un registro por llamada que nadie
leía). Se consulta para **no repetir lo malo** y para reutilizar ideas probadas; nunca para
copiar estructura ni para dar por bueno algo porque allí funcione.

**Idioma y nomenclatura.** La **prosa y los comentarios** van en castellano. Todo lo demás
—claves de la declaración, nombres de ficheros y directorios, verbos, campos de los
informes y mensajes de error— va en **inglés**, con el vocabulario de la API que
corresponda (`vmid`, `memory`, `cores`, `bridge`, `address`, `net0`, `ip/dhcp-server`,
`ip/service`). Un ingeniero tiene que poder leer el repositorio y la declaración **sin saber
castellano**; el castellano es para explicar, no para nombrar.

---

## 1. Qué es Netlabs

Netlabs despliega **laboratorios de red efímeros** —topologías de routers y equipos Linux—
en un hipervisor Proxmox, **exclusivamente por su API REST**, a partir de la declaración de
cada laboratorio, y los deja **observables desde la consola web de NetXMS**.

Tres objetivos, en este orden:

1. **Predictible y observable.** Lo desplegado es siempre lo declarado, se despliega igual
   cada vez, y se ve entero desde una sola consola.
2. **Rápido.** Un laboratorio se declara en un fichero y existe en pocos minutos; se retira
   sin dejar residuos.
3. **Comprensible.** El sistema completo cabe en la cabeza de una persona; la complejidad
   que no compre un objetivo se rechaza.

**No objetivos de esta versión:** aprovisionamiento por cloud-init (además, en este hipervisor
no está disponible: §3.8), agentes de monitorización dentro de los invitados, servicios
persistentes de infraestructura más allá del de observación, alta disponibilidad, multi-nodo,
Windows, contenedores de aplicación, ni certificados o gestión de secretos más allá de un
fichero ignorado por git.

**Un despliegue bien hecho vale más que uno rápido.** Los tiempos importan —un despliegue de
media hora no se usa—, pero no se persigue un cronómetro a costa de garantías: entre llegar
antes y saber que lo desplegado está bien, se elige lo segundo.

---

## 2. Principios

Cada principio lleva el fracaso concreto que evita.

### 2.1. El motor es agnóstico de los laboratorios

El motor sabe que existen nodos, redes, direcciones, roles y etapas; **no sabe qué topología
tiene nadie**. Conoce reglas genéricas (el identificador libre más bajo del clúster, la MAC
se deriva del identificador, el nombre dice qué equipo es), nunca valores. **Añadir un
laboratorio no toca ni un fichero del motor.**

*Evita:* el motor convertido en un archivo de casos especiales, donde cualquier cambio obliga
a leerlo entero.

### 2.2. Dos capas, sólo dos

```
engine/         generic: knows no lab
labs/<lab>/     the declaration of THAT topology, plus its documentation
```

Dentro de `engine/` no hay capas intermedias ni un subdirectorio por función: un fichero, un
propósito, y el nombre lo dice. Si un cambio pide una estructura más profunda, se justifica
por escrito o se descarta.

*Evita:* el laberinto de rutas donde ya nadie sabe dónde vive nada.

### 2.3. El estado deseado es la declaración; no hay otro estado

Cada laboratorio se declara en **un fichero YAML**, y ese fichero **es** el estado deseado.
**Ansible** lo lleva a la realidad, es **idempotente** y no guarda nada propio en disco: ni
inventario, ni fichero de asignaciones, ni memoria de lo que desplegó.

Todo lo derivado se **re-deriva** preguntando al hipervisor: identificadores, MAC,
direcciones de gestión y pertenencia. El **nombre de un equipo sí se declara** —es su
identidad—, y de él salen el hostname del invitado, su nombre en el hipervisor y las
puntas de sus cables. La **frontera de propiedad** —qué es de este
laboratorio y qué es ajeno— se lee también del hipervisor: un grupo de recursos con el
nombre del laboratorio y una descripción en cada nodo que dice a qué rol pertenece.

*Evita:* el estado que se desincroniza del mundo y convierte cada despliegue en una
negociación entre dos verdades.

### 2.4. Un único punto de entrada, con tres verbos

```
./netlabs plan     --lab <lab>   what would be done, without touching the world
./netlabs apply    --lab <lab>   do it, and prove that it serves
./netlabs destroy  --lab <lab>   take it down
```

Empezamos con tres; un verbo nuevo se añade cuando alguien demuestre que lo necesita. Ningún
verbo se copia por laboratorio y todos se lanzan desde la raíz del repositorio. **Netlabs no
es un servicio**: es el envoltorio que lanza Ansible sobre una declaración.

El **plano de gestión** —el servicio persistente— se aplica con el mismo verbo y la misma clase
de declaración, pero **no es un laboratorio**: `apply --site` lo converge, y `destroy` no lo
acepta. Lo persistente no se destruye desde la herramienta.

Las **comprobaciones del repositorio** no son un verbo: son la verificación que corre en CI
(§11). `apply` termina **demostrando servicio** —no sólo que los recursos existen— y
`destroy` informa de lo que retiró.

*Evita:* scripts sueltos que hacen «casi lo mismo» y se separan con el tiempo; y la ambigüedad
de dos verbos que parecen mirar lo mismo.

### 2.5. Ninguna espera a ciegas

Nada de dormir un tiempo fijo «para dar tiempo». Toda espera es **una condición con un tope**:
se sondea y se sale en el instante en que se cumple; agotar el tope es un **fallo**, no un
verde.

*Evita:* el despliegue que tarda de más porque durmió, el que mira antes de tiempo y el proceso
que se queda parado sin decir por qué.

**La condición se escribe para que pueda fallar.** «El puesto tiene dirección» es una IPv4 en una
interfaz que no sea `lo`, no la palabra `inet` en cualquier parte de la respuesta: el bucle local
siempre la lleva y una comprobación así nunca falla —y una comprobación que no puede fallar no
comprueba nada—. Si el puesto arrancó antes de que su router sirviera DHCP y se quedó mudo, el
motor lo **reinicia una vez** (una reparación acotada, visible en el informe) y vuelve a sondear;
si aun así no hay dirección, el `apply` para con su nombre.

### 2.6. Nunca para en silencio, nunca sigue de largo

Un paso que no puede cumplirse **para y dice qué falta y cómo se arregla**. No hay «continuar
de todos modos», ni valores por defecto silenciosos, ni un verde que tape un aviso.

*Evita:* el despliegue que «termina bien» dejando medio laboratorio sin configurar.

### 2.7. Idempotencia

Dos `apply` seguidos: el segundo **no cambia nada**. Es una propiedad del diseño —derivar en
vez de recordar, comparar antes de escribir—, no un extra.

*Evita:* el motor que duplica recursos y no se puede ejecutar dos veces sin miedo.

### 2.8. Una sola vía para cada cosa

Al hipervisor se le habla **sólo** por su API REST, desde un fichero del motor. A un RouterOS,
**sólo** por su API REST —salvo su primer arranque, que va por el agente del hipervisor, es
decir, también por la API (§3.8)—. A un Linux, **sólo** por SSH. Al servicio que observa el sitio
(NetXMS), **sólo** por su API REST y **desde dentro de su invitado** —ahí aterriza el túnel del
motor—: por esa puerta registra el motor cada equipo de red con su credencial y le coloca el
mapa de la red (§3.4), y no toca su base
por ninguna otra (§3.4; `docs/decisiones/0003`, `0004` y `0005`). Un equipo se identifica en la
vista por su **nombre y su dirección de gestión**: dos laboratorios pueden tener a la vez un
`rta1`, y el nombre solo no basta para saber de cuál es el registro. La dirección se deriva del
vmid, así que cambia cuando al invitado se le
asigna **otro** vmid —rehacerlo conservando el vmid conserva la dirección—, y un nodo con el
nombre bueno y la dirección de otra máquina se retira y se vuelve a dar de alta —el API no deja
corregir la dirección—. Una vía nueva para lo mismo es un defecto, no una
comodidad.

*Evita:* llamadas a la API repartidas por todo el motor, imposibles de seguir y de auditar.

### 2.9. El informe de la ejecución es el de Ansible

No hay un registro propio. Lo que queda de una ejecución es **el informe que Ansible ya
produce** —tareas, `changed`, `failed`, tiempos— guardado como texto **fuera del
repositorio** y publicado como artefacto en CI.

*Evita:* el diario por llamada en formato máquina que nadie lee, que ensucia el repositorio y
que hay que mantener sincronizado con el código; y el efecto contrario, no saber qué pasó.

### 2.10. La documentación se comprueba, no se promete

La página de cada laboratorio tiene dos regiones: una **generada** desde la declaración
(tablas de nodos, direcciones, etapas) y otra de **prosa** escrita a mano (por qué se hizo
así, qué se aprendió). La comprobación re-renderiza la región generada y **falla si difiere**
de lo que hay en el fichero.

La región generada lleva además un **plano**, también sacado de la declaración: la
**topología** (cada red como área translúcida con su nombre y su subred, y dentro quién cuelga
de ella —la dirección de la puerta no se repite en la cabecera del área: se lee junto al símbolo
del router, que es quien la tiene—), con un símbolo por equipo y una línea por cable, cada una
con el puerto de sus dos puntas. Un solo plano: hubo también un dibujo de cableado, hecho
por un segundo motor plano, que enseñaba los mismos equipos y los mismos puertos con otra
colocación —dos retratos del mismo dato que no coincidían y hacían dudar de los dos—. Lo dibuja
`tools/plano.py` y va **en los dos sitios**: dentro del `.md`, como SVG en texto —es código
generado, entra en el mismo diff que la declaración y se lee y se compara como cualquier otra
línea del documento—, y en su `<lab>-topologia.svg`, el mismo dibujo en un fichero que se abre y
se comparte por sí solo y que sirve de fondo al mapa de la vista (§3.4). Los dos salen del mismo
dibujo en la misma pasada, así que no pueden discrepar.
`./netlabs docs --check` vuelve a dibujarlo y compara el texto con el del fichero —y con el del
`.svg`—, así que un plano viejo es un fallo. Mermaid no
sirve para esto: no sabe dibujar los símbolos de una red (router, switch, cortafuegos, servidor)
y sus áreas no pueden tocarse, así que un router con pata en dos redes no se puede poner entre
ellas.

El plano se dibuja como un plano de red, no como un organigrama. **El eje lo marca el router**:
un equipo con pata en varias redes se sienta donde se tocan, **encima del cruce** —el borde de
cada área pasa por debajo de su símbolo, no a un lado—, con una red a cada lado y la salida a
Internet arriba; con una sola red, el router se sienta sobre el techo del área.

**Lo que no cambia se escribe**: cada equipo lleva su dirección estática bajo el nombre —una por
pata si tiene varias, como un router con un pie en cada red— y el que sale por DHCP lo dice con
esa palabra. Cada área, en su cabecera, lleva su nombre, su subred y **el rango que sirve su
DHCP**. La red se escribe como el bloque que es —`10.20.55.0 - 10.20.55.255 (/24)`,
`10.20.0.0 - 10.20.255.255 (/16)`—: la primera y la última dirección se leen de un golpe y el
prefijo va al final, así dos áreas de tamaños distintos se comparan sin contar octetos. Una
dirección sola va sin `/32`, que no añade nada a quien ya la ve entera. La puerta no se repite en la cabecera: es la dirección del equipo que toca la red y va
escrita en él, que es su dueño. Un equipo de una sola red vive
dentro de la suya, y dentro de cada red la profundidad baja: lo que cuelga de la puerta queda
pegado a ella. **La clase la dice el símbolo**, plano y de línea, sin volumen ni perspectiva: el router
es el círculo con las cuatro flechas, el switch la caja con las flechas cruzadas y sus puertos, el
cortafuegos el muro de ladrillos, el servidor la torre de bahías, el puesto la pantalla con su peana
y el nodo de gestión la pantalla con la rueda dentada. El color de acento dice la familia, como en
los juegos de iconos de AWS: morado para lo que conmuta y enruta, rojo para lo que filtra, gris para
lo que atiende al usuario. Se dibujan aquí con vectores, hijo a hijo del mismo generador, y no se
copian de ningún pack de iconos: los de Cisco y los de AWS son suyos, sus licencias no permiten
redistribuirlos y este plano se versiona entero junto al laboratorio. No lleva clave de símbolos:
la forma y el nombre de cada equipo ya dicen lo que es, y una clave que repite lo que el dibujo
enseña sólo ocupa sitio. Un solo color para todas las redes —el color dice «esto es una red», no «esta red es distinta»—. Las líneas van **sin
flecha**: el plano dice quién toca a quién, y una punta sugeriría un tráfico que nadie declaró;
la salida a Internet se distingue por el trazo discontinuo, que no es un cable del laboratorio.
Un plano que no sale de la declaración no se dibuja: se pudre el primero que alguien cambie algo
a mano.

*Evita:* el documento que describe un sistema que ya no existe.

### 2.11. Las comprobaciones se ganan el sitio

Hay las comprobaciones que aportan valor real: que la declaración sea coherente, que los
espacios de direcciones no se pisen, que la documentación no se quede vieja, que sólo las
vías autorizadas hablen con el hipervisor, que el motor no lleve valores de ningún
laboratorio, que las referencias resuelvan. Ninguna más por completitud ni heredada sin
motivo. Cada una tiene que haberse visto **gritar** rompiendo a propósito lo que vigila.

*Evita:* la batería de comprobaciones que se mantiene por sí misma y ya nadie entiende.

### 2.12. Las decisiones se escriben cuando son caras de revertir

No hay un registro de decisiones por cambio. Se escribe una nota corta cuando la decisión
afecta a varias partes **y** sería cara de deshacer. Todo lo demás vive en el comentario del
fichero que lo implementa, que es donde se lee.

*Evita:* el archivo de decisiones que crece más rápido que el producto.

### 2.13. La declaración es explícita y el error es educativo

Lo declarado se aplica; lo que el motor no entiende es un **error con mensaje**, que dice qué
se admite y dónde está el límite. El vocabulario se diseña **por composición**: pocas
primitivas que se combinan, no una casilla por caso. Una clave desconocida nunca se ignora en
silencio.

*Evita:* por un lado, el laboratorio que cree haber configurado algo que el motor descartó;
por otro, el vocabulario que exige horas de estudio para escribir dos líneas.

### 2.14. La vía de configuración y la de observación son la misma

No hay una red de gestión para desplegar y otra para vigilar: hay **una**. Ansible configura
por ella y NetXMS observa por ella. Si no responde, el verbo para y dice qué pieza falta.

*Evita:* dos planos de gestión que mantener sincronizados y el intermediario que existe sólo
porque el observador no llegaba.

---

## 3. Los actores

### 3.1. El hipervisor (Proxmox)

Es el **mundo**: guarda los invitados, sus recursos, sus tarjetas, los bridges y los grupos de
recursos. Nadie le supone nada; **Ansible le pregunta** antes de actuar y le vuelve a preguntar
al terminar. Netlabs no habla con Proxmox: lo hace Ansible, a través de la vía de acceso del
motor.

**Por qué sólo por su API REST.** Es la vía que da **predictibilidad** (la misma petición
produce el mismo efecto), **observabilidad** (el informe de Ansible nombra cada recurso que
tocó) e **idempotencia** (se puede preguntar el estado antes de escribir). El acceso por SSH
abre una puerta por la que se pueden lanzar acciones que escapan a las tres: no aparecen en el
informe, no se comparan con el estado deseado y no son reproducibles. **El motor no entra por
SSH al hipervisor, jamás.** (§9 para el uso excepcional del SSH como herramienta de
diagnóstico durante el desarrollo.)

### 3.2. El motor (Ansible)

Convierte una declaración en realidad. Se lanza desde fuera del hipervisor y trabaja en cuatro
pasos: **leer el mundo, calcular la diferencia, aplicarla por etapas y demostrar que lo
declarado sirve**.

Ansible se usa como vehículo —tareas, hechos, condicionales, manejo de errores— porque es
inspeccionable: se lee lo que va a hacer y su informe es la evidencia de lo que hizo.

### 3.3. La red de gestión (OOB)

Una red que **no pertenece a ningún laboratorio** y por la que se llega a los **equipos de
red** de todos. Es infraestructura del sistema, no topología: **no se declara en el
laboratorio y el motor no la replantea en cada despliegue** — siempre es la misma red, con la
misma puerta, y por eso todos los laboratorios comparten plano de gestión.

- **Por qué una sola y compartida.** Es la expresión mínima de «existe un plano de gestión».
  Con una por laboratorio habría que enrutar entre ellas y mantener un punto de entrada por
  laboratorio.
- **Un solo espacio de direcciones, no uno por laboratorio.** La red de gestión es **un /16** y
  la dirección de cada equipo de red sale de su identificador (único en todo el hipervisor), así
  que **no hay reparto que llevar**: ni índice por laboratorio, ni una dirección de puerta por
  laboratorio, ni estado que se pueda desincronizar. Un trozo de red por laboratorio parece más
  ordenado, pero obliga a que la puerta tenga una dirección en cada trozo y a que alguien
  reparta los trozos: dos cosas que mantener para no ganar nada, porque el identificador ya
  garantiza que no se repita una dirección.
- **Por qué la dirección de gestión se deriva del identificador.** Todo lo derivado se calcula
  (§2.3): la dirección de gestión de un equipo de red es una **función de su identificador**,
  sin servidor que la reparta, sin caducidad y sin estado. Cuando el espacio se acaba, el
  motor lo dice en vez de inventar una dirección.
- **Por qué no DHCP en la OOB.** Un servidor más que mantener en el host y una dependencia del
  orden de arranque, a cambio de nada.
- **Qué NO está en la OOB.** Los nodos finales (servidores, puestos): no tienen pata de
  gestión. Se llega a ellos por el router de su red (§4).

### 3.4. NetXMS: el servicio persistente (observar, y el camino del motor)

NetXMS **no es un actor del laboratorio**: es un servicio **persistente**, en su propio pool,
que sobrevive a los `apply` y a los `destroy` de cualquier laboratorio.

Es **un solo invitado**, y cubre dos necesidades del sistema:

1. **Observación.** Su consola web es la vista única de todo lo desplegado, y su histórico
   sobrevive a que un laboratorio se destruya. Vigila por **SNMP e ICMP**, por la red de
   gestión y por las rutas hacia las redes de cada laboratorio (§4).
2. **El camino del motor.** Ansible se ejecuta fuera del hipervisor y las direcciones de
   gestión son privadas: necesita entrar en la red de gestión. Ese camino se abre **por este
   mismo servicio**, porque ya tiene que ver todas las redes. **No hay un invitado aparte para
   esto, ni un bastión por laboratorio**: es una función del servicio, no una pieza nueva.

Si el camino no responde, `apply` **para** y dice qué falta; no lo rodea por otra vía.

**Coste aceptado y dicho claro:** es **punto único de fallo** del despliegue y tiene dos
papeles (observar y transportar). Se acepta porque la alternativa —un equipo de paso
dedicado— es un segundo servicio permanente que instalar, actualizar y explicar para hacer lo
mismo.

**Es el único servicio persistente.** Fuera de los laboratorios no hay nada más, y lo que
tenga que persistir **vive dentro de este mismo invitado**: si algún día hace falta un
servicio auxiliar (por ejemplo, algo que responda en la red donde arrancan los routers), es
un proceso más en esa máquina, no otro invitado ni otro pool.

**Por qué no una «antena» por laboratorio.** Una antena es un agente NetXMS en modo proxy:
alguien dentro del laboratorio que reenvía al servidor lo que el servidor no alcanza. Resuelve
un problema real —que el servidor no llegue— y con rutas hacia las redes del laboratorio ese
problema se resuelve sin instalar nada dentro: añadir la antena sería un agente más por
laboratorio que puede caerse, un salto que explicar y menos realismo.

**La terminal de la consola web.** NetXMS puede abrir una shell a un equipo desde el
navegador. En esta fase se usa **sólo para los equipos de red**, y va por su **dirección de
gestión** (la OOB): mismo camino que el resto, sin depender de las rutas del laboratorio.
Extenderlo a los nodos finales es posible y no se descarta, pero no es requisito. Lo que hay
que decir en voz alta: esa shell es **para una persona**, no para el motor — Ansible configura
por su vía (§6) y no por la terminal de nadie.

**Qué nodos finales entran en la vista.** Un equipo de red entra por su pata de gestión. Un
servidor o un puesto no tiene pata de gestión: entra por la dirección de su interfaz, y sólo si
esa dirección es **estable**. Por eso un nodo final con dirección **estática** se registra y se
dibuja en el mapa, mientras que uno con `address: dhcp` no se inventa una dirección que todavía
no tiene. Para que un nodo DHCP aparezca hay dos caminos: darle una dirección estática (deja de
ejercer de cliente DHCP) o **reservarle una dirección por MAC** en el router que sirve su red;
la reserva convierte el DHCP en una dirección estable y el nodo se registraría igual que uno
estático. **La reserva todavía no la crea el motor**: hoy habría que ponerla a mano en el
router y el nodo seguiría sin `netxms_address`, así que en esta fase el camino soportado para
un nodo DHCP es la dirección estática. NetXMS no adivina la dirección leyendo la tabla de
leases: un lease puede cambiar y el nodo quedaría apuntando a una dirección que ya no es la
suya.

**Dos laboratorios con los mismos nombres.** NetXMS admite dos nodos llamados `rta1`; lo que
los distingue es su **dirección de gestión**, que sale del vmid y por tanto es única. El mapa
de cada laboratorio se construye sólo con los objetos cuya pareja nombre+dirección es la suya,
así que el mapa de uno no enseña equipos del otro. La terminal de la consola también va a la
dirección del nodo, no a su nombre: abrir `rta1` desde el mapa del laboratorio `d` conecta con
el `rta1` de `d`, no con el de `e`. Lo único que puede confundir es el árbol de objetos, donde
los dos nombres se ven iguales; ahí ayudan la dirección y el comentario de propiedad del nodo.

**El mapa a medida: lo que la vista enseña es el plano.** La vista sabe dibujar su propia
topología —descubre por direcciones y la reparte a su manera—, y ese dibujo **no se parece a
nada de lo que dibuja el plano**: ni las áreas, ni dónde cae cada router, ni qué redes quedan
a un lado y a otro. Así que el motor **le manda un mapa hecho a medida**, con el mismo dibujo
que la documentación:

- las **áreas** del plano, como cajas de grupo; su nombre y su bloque de direcciones van en **cajas
  de texto** colocadas **dentro de su propia área**, arriba a la izquierda como las cabeceras del
  plano, apartándose sólo lo justo para no pisar un cable o un equipo: un rótulo que dice de qué
  red es no puede caer en la caja de otra red;
- cada **equipo de red** del laboratorio donde el plano lo pone —el router en la frontera de
  las redes que une, el switch del núcleo en el centro—, con la **etiqueta grande** de la vista:
  nombre e IP, sin cartel de patas ni de reparto, que no aportaba y se comía el sitio de las
  cabeceras;
- cada **cable** del laboratorio, entre los dos equipos que une, con el **puerto y la interfaz de
  cada punta** (`p1 ether1`), atados a la interfaz de la vista por la que de verdad sale, y los
  **ajustes** que dicen cómo se dibujan: color propio y trazo fino, porque el gris ancho que pone
  la vista se pierde en el gris de las cajas. El **nombre del cable** —el del puente que lo tiende
  el despliegue— no se dibuja: la vista lo pone en el centro del enlace y tapa el cable. Viaja en
  la configuración del enlace, donde queda informado sin estorbar.

El dibujo **no se escribe a mano y lo que dice tampoco**: la geometría se lee del propio plano
(`plano.py` escribe la posición de cada cosa en atributos `data-*` del SVG) —así el mapa de la
vista y el plano de la documentación **no pueden discrepar**: son el mismo dibujo—, y los nombres,
puertos e interfaces salen del **YML** y viajan con esos mismos atributos. El mapa se
nombra como el laboratorio, y se escribe **sólo si no es ya el que el plano pide** —escribirlo de
más sería perder cualquier ajuste hecho a mano, porque el API lo reemplaza entero—.

Dos cosas se dicen en voz alta. Los **puestos de trabajo no salen en el mapa**: la quinta vía
registra equipos de red (§3.4), y un elemento del mapa sin equipo detrás lo rechaza la vista.
Y un equipo de red que la vista no conozca —porque lleva otras credenciales, o porque el
registro no llegó— tampoco se dibuja: sale en `pendientes`. Un mapa al que le falta un router
sin decirlo es un mapa que miente.

**Un solo mapa, el del laboratorio.** El motor no da de alta los mapas de capa 2 ni de
direcciones que dibuja el servidor con lo que sus equipos le cuentan: añaden ruido y no enseñan
el plano. El mapa que se mantiene es el que el motor coloca a medida, y es el único que hay que
mirar. Los mapas de comunicación interna y de OSPF tampoco se dan de alta: describen protocolos
que estos laboratorios no usan.

### 3.5. Pools: el plano de gestión y los laboratorios no se mezclan

- **Pool de gestión (persistente):** el servicio de observación y camino. Ningún laboratorio
  lo crea, lo modifica ni lo destruye.
- **Pool del laboratorio (efímero):** todo lo del laboratorio. `destroy --lab X` actúa **sólo**
  sobre este pool y sobre lo que el motor creó y marcó como suyo; nada más.
- La separación no es un acuerdo de caballeros: es la **frontera de propiedad** (§2.3) leída
  del hipervisor. Si algo no está en el pool del laboratorio ni lleva su marca, no se toca.

**El servicio persistente se configura como cualquier invitado**: es una máquina del hipervisor
y Ansible entra en ella como en cualquier Linux (§6). Su declaración vive en su propio fichero y
su propio pool —no es un laboratorio, y ningún laboratorio la escribe—. Lo que sí cambia con
cada laboratorio son las **rutas** que necesita para ver sus redes: se derivan de lo declarado y
se ponen al aplicar el laboratorio.
- Un laboratorio nuevo **no crea ni toca** el servicio persistente: sólo añade sus equipos, sus
  puentes y sus rutas, y lo retira todo al destruirse.
- **Los puentes se van con el laboratorio**, igual que sus invitados: se crean con la marca de
  propiedad, y `destroy` se lleva los que llevan la marca y ya no usa nadie de fuera. Nada se
  acumula entre despliegues.
- **Un puente no es una red: es un cable.** El hipervisor no hace de conmutador. Lo que aquí se
  llama puente es el cable tonto que une dos puertos, y se explica en §3.9.

### 3.6. La consola serie: puerta de emergencia

**Ya no es el camino de arranque**: eso lo hace el agente (§3.8). Se conserva como **puerta de
emergencia** para un router que no responde al agente, y se usa **la consola serie de la
máquina** (`serial0`), no la gráfica: la serie es texto, se puede leer entera, se puede buscar
una marca en ella y no depende de que alguien mire una pantalla en el momento justo.

Se abre **a mano y sólo cuando algo ha fallado**; sigue siendo **sólo para RouterOS** y no sirve
para configurar nada: lo que se configure, se configura por la vía del equipo. Y si una
emergencia enseña algo, su fruto es una comprobación nueva o un mensaje mejor del motor (§9), no
un procedimiento paralelo.

### 3.7. El Guest Agent del hipervisor no es un agente de monitorización

Son dos cosas distintas y conviene no confundirlas:

- **Guest Agent del hipervisor (QEMU).** Toda VM nace con él habilitado, y el token del motor
  lleva **lectura** para observar y **ejecución**, acotada, para el arranque de un router
  (§3.8). Sirve para **leer** el estado del invitado sin entrar en él: si está arrancado, qué
  interfaces tiene y qué direcciones tiene puestas. Y sirve para **una cosa más**: ejecutar el
  script de arranque de un router. Nada más: no es una vía para configurar lo que ya está en
  marcha.
- **Agente de monitorización (NetXMS).** Un programa dentro del invitado que reporta métricas
  al servidor. **No se instala en esta fase** (§12).

Tres vías, tres papeles, y no son intercambiables: la **API** crea, el **Guest Agent** lee y
ejecuta el script de arranque (§3.8), y a partir de ahí la **vía del equipo** (REST de RouterOS,
SSH de Linux) configura.


### 3.8. Cómo arranca un router que aún no tiene dirección (medido, no supuesto)

Un router recién creado no tiene dirección. Se probó con **seis CHR 7.25.1 de fábrica**,
cada uno con disco nuevo importado de la imagen, y esto es lo que se midió.

**Lo que trae de fábrica.** Un **cliente de direcciones en su primera interfaz**
(`dhcp-client` sobre `ether1`), y nada más: sin dirección, sin rutas, sin scripts. Con un
servidor delante, toma dirección **a los siete segundos** del arranque.

**El servicio de metadatos no se usa aquí.** Se levantó el escenario completo: servidor de
direcciones en el segmento, `169.254.169.254/32` puesto en la interfaz del hipervisor y un
HTTP en el puerto 80 sirviendo `/latest/user-data`. En todos los arranques de fábrica:
**cero paquetes** hacia esa dirección —ni ARP ni HTTP—, y en los dos últimos la dirección se
tomó a los siete segundos, o sea **dentro de la ventana del primer arranque**. Tampoco lo
intentó después, con dirección y ruta ya puestas. Conclusión: lo que lo dispara es **detectar
una nube**, no estar recién creado; en este hipervisor no ocurre nunca. **Descartado con
evidencia.**

**Qué es esa dirección y por qué aquí no aparece (documentado).** `169.254.169.254` es el
servicio de metadatos de las nubes —el de Amazon EC2—: el invitado pregunta ahí su nombre y su
clave pública al arrancar. MikroTik lo explicó en su foro: la consulta **se repite sólo mientras
no haya ruta** hacia esa dirección y **se detiene al primer fallo**; y **desde 6.42 el CHR
detecta si está dentro de EC2 y, si no lo está, no hace la comprobación**. En 2015 fue un fallo
que inundó registros de routers (los caminos pedidos eran `/latest/meta-data/public-keys/0/openssh-key`
y `/latest/meta-data/hostname`); en 2018 un CHR sobre ESX hizo 250 000 intentos en doce horas
hasta que se le puso una ruta *blackhole*.

**Probado también con la firma de EC2 puesta a mano.** Se arrancó un CHR de fábrica con el
firmware de la máquina declarando `Amazon EC2` como fabricante y producto, con dirección tomada
a los siete segundos y el servicio respondiendo en esa dirección: **cero conexiones y ninguna
línea en el registro del router**. Qué comprueba exactamente para «saber» que está en una nube
no está publicado —se lo preguntaron a MikroTik en ese mismo hilo y no hubo respuesta—, así que
no se persigue: **en este hipervisor la vía de metadatos está cerrada**.

**Trampa del entorno, medida y cara de encontrar:** en el puente, el *offload* de checksum de
la tarjeta virtual corrompe las respuestas del servidor de direcciones y el invitado las
descarta en silencio (en la captura se ve el checksum UDP malo). Hay que apagarlo en la
interfaz virtual del invitado (`ethtool -K tap<id> tx off`) o el router se queda buscando
dirección para siempre.

**Lo que sí funciona: el Guest Agent del propio RouterOS.** Tres pasos, todos por la API del
hipervisor:

1. `agent/network-get-interfaces` devuelve las interfaces con su MAC y sus direcciones.
   **Basta el permiso de lectura** (`VM.GuestAgent.Audit`).
2. `agent/file-write` deja un fichero de script dentro del invitado (`encode: 1`, contenido en
   claro). El hipervisor avisa de un `guest-file-close` con *timeout*: es **cosmético**, el
   fichero llega entero (probado con sesenta líneas).
3. `agent/exec` ejecuta ese script y devuelve **salida y código de retorno**. Probado con
   `:put "…"` (salida exacta, código 0) y con un alta real de dirección: el router la tomó y la
   lectura del agente la mostró.

**Decisión: el arranque va por el Guest Agent.** No hace falta consola, ni dirección, ni
servicio auxiliar, ni una interfaz de más. La **consola serie** queda como **puerta de
emergencia** (si el agente no responde), no como camino normal, y sigue siendo **sólo para
RouterOS**.

**Decisión adoptada, con su alcance escrito.** El motor arranca los routers por el Guest Agent,
y para eso el token lleva `VM.GuestAgent.Unrestricted`. Se acepta porque la ejecución va **por
la API**: aparece en el informe de la ejecución, es idempotente y no abre una puerta lateral
como SSH. Y se acota en tres reglas, para que no se convierta en una vía general de configurar
invitados:

- **Un solo fichero de arranque**, escrito para poder ejecutarse dos veces sin cambiar nada.
- **Sólo en el arranque de un router.** Lo que se configure después va por la vía del equipo
  (§6); el agente no es un atajo para saltársela.
- **Leer se hace con el permiso mínimo** (`VM.GuestAgent.Audit`), y el token está acotado al
  pool del laboratorio, de modo que no alcanza a nada de fuera de él.

### 3.9. El cableado: un puente es un cable, no un conmutador

**El hipervisor no conmuta nada.** Un puente de Proxmox es, en este diseño, un **cable tonto**:
une exactamente dos puertos y transporta lo que le metan. No tiene dirección, ni puerta, ni MAC,
ni DHCP, ni VLAN: si tuviera cualquiera de esas cosas, sería un conmutador, y el motor no crea
conmutadores.

**El nombre del cable lleva la letra del laboratorio y sus dos puntas.** Se nombra
`<letra>_<equipo>p<puerto>_<equipo>p<puerto>`, y cada equipo por su rol:

```
c_rte1p1_swc1p1     laboratorio `c`: el router de borde 1 -> el switch de núcleo 1
b_rte1p2_wsp2p1     laboratorio `b`: el router de borde 1 -> el segundo puesto
```

**La letra es la del nombre del laboratorio** (`c_enrutar_y_conmutar`) y es lo que hace
que dos laboratorios con la misma topología en el mismo hipervisor no compartan un solo
nombre de puente. Cada punta mide seis caracteres (dos de tipo, una de función, el
ordinal, `p` y el puerto), así que el nombre mide 15 y **cabe en el tope de 15
caracteres de un nombre de interfaz en Linux** (`IFNAMSIZ` es 16, con el nulo final). El
nombre del cable dice qué une sin consultar la declaración: es la mitad de la
documentación.

**Por qué el puerto es de una cifra.** El tope de 15 no es una convención: es del
kernel. Con la letra del laboratorio y las dos puntas dentro, el puerto cabe en una
cifra, y de ahí que **un equipo no pueda tener más de nueve puertos cableados**. El
límite se dice: al pedir el puerto 10 el motor se para con un mensaje, en vez de dejar
que la API de Proxmox acepte el nombre y el puente falle después, al levantarlo.

**El comentario del puente dice de quién es.** Como el cable no puede llevar CIDR, su marca vive
en el comentario: `netlabs lab=<lab> space=<cidr> cable=<nombre>`. Es lo que permite a `destroy`
retirar sólo lo suyo y a otro laboratorio detectar que ese nombre ya está ocupado. Un puente con
el nombre de un cable de este laboratorio y sin su marca **no se toca**: es de otro.

**Funciones de conmutación: se declaran, no se improvisan.** Cuando un laboratorio necesita
conmutar (VLAN, agregación, varios puertos en un mismo dominio), se declara un nodo de tipo
`switch`: un **RouterOS** que hace ese papel. Sus puertos se conectan con cables a los demás
equipos, igual que cualquier otro. El hipervisor nunca conmuta; el que conmuta es un equipo del
laboratorio, y por tanto se puede leer, configurar y destruir como cualquier otro.

**Lo que esto implica.** Un puerto declarado sin cable es un error, no una red implícita; un
cable que une dos redes distintas es un error, porque eso es enrutar, y enrutar es un router.
Cambiar el cableado de un invitado que ya existe no se hace en caliente: se rehace **ese**
invitado —se retira y se vuelve a crear— y **ningún otro se toca**; el plan lo dice antes de
tocar nada. Los recursos no llegan a eso: los cores y la memoria se escriben en el config del
invitado con él parado un momento, y su disco, sus cables y lo que tenga dentro siguen donde
estaban. Se comparan contra lo **escrito** en el config, no contra lo que el invitado tiene en
marcha: a una máquina encendida se le puede cambiar la memoria en el config y seguir con la
vieja hasta reiniciar, y la lectura del clúster no vería la diferencia justo cuando existe.

Antes cualquier diferencia paraba el plan con un «hace falta destroy», y el `destroy` se lleva el
laboratorio entero: subir la memoria de ocho conmutadores costaba tirar otros dieciséis equipos
que estaban bien. Arreglar uno costaba arreglarlos todos, y eso no es converger: es demoler.

---

## 4. Dos clases de nodo, y cómo se llega a cada uno

Esta es la pieza que hay que entender bien, porque de ella salen casi todas las demás
decisiones.

### 4.1. Equipos de red (`type: router`, `type: switch`)

Son los que **hacen la red**: routers y conmutadores. **El conmutador es un RouterOS** que hace
funciones de conmutación, no un puente del hipervisor: se declara como cualquier otro equipo y se
conecta con cables (§3.9). Nacen con **una pata más** en la red de gestión —la última, para no
renumerar las interfaces declaradas— y su dirección de gestión se deriva del identificador.

Por ahí los alcanza **Ansible** (entrando por el servicio persistente, §3.4) y por ahí los
observa **NetXMS**.
Es su plano de gestión; su tráfico de datos no pasa por ahí.

**Un switch, dentro, es un puente.** El motor no le pone direcciones de laboratorio (no declara
`address`) y converge su interior a un único `/interface/bridge` llamado `netlabs-<red>` con una
sola entrada por cada pata de laboratorio; la pata de gestión queda **fuera** del puente, porque
si entrara el switch sería un cable entre la red de gestión y el laboratorio. El puente va sin STP
(`protocol-mode: none`): no hay bucles que romper en un cableado declarado, y un protocolo que no
se declara no se enciende. Todas sus patas tienen que ser de la **misma red** —un switch que une
dos redes está enrutando— y por eso el mismo tipo no admite la red repetida que un router sí
prohíbe.

### 4.2. Nodos finales (`type: server`, `type: workstation`)

Son los que **usan la red**: servidores y puestos, contenedores Linux. **No tienen red de
gestión, ni dirección derivada, ni pata extra.** Viven en una red del laboratorio, detrás de
su router.

**Cómo se llega a ellos: por el router.** Igual que en una red desplegada de verdad:

- **Ansible** les habla por **SSH** a su dirección del laboratorio, y el router sólo **enruta**:
  el equipo que ejecuta Ansible tiene una **ruta estática** hacia el espacio del laboratorio que
  apunta a la dirección de gestión del router. No se salta *por dentro* del router (nada de
  abrir sesión en el RouterOS para pasar de un lado a otro): el router hace lo que sabe hacer,
  enrutar. Esa ruta se pone con `apply` y se retira con `destroy`.
- **NetXMS** los alcanza por una **ruta hacia el espacio de direcciones del laboratorio**, con
  el router como siguiente salto. Esa ruta se **deriva**: espacio declarado por el laboratorio
  + dirección de gestión de su router. Se da de alta con `apply` y se retira con `destroy`; no
  la teclea nadie.
- En esta fase se observan **por ICMP** (disponibilidad) y aparecen en la topología como lo que
  son: hojas del segmento que el router publica. **Sin agente dentro**: por eso no hay CPU,
  memoria ni procesos de esos nodos. Es el precio consciente de no instalar nada en ellos, y se
  puede revisar más adelante (§12).

### 4.3. Lo que esto implica (y hay que asumir)

1. **El router tiene que dejar pasar ese tráfico.** Sin una regla que permita el cruce desde
   la red de gestión hacia sus redes, el laboratorio es un agujero negro: el motor no llega a
   los nodos finales y NetXMS los ve caídos. Esa regla es parte de lo que se configura en el
   router, y el motor la comprueba (si no está, `apply` falla diciéndolo).
2. **Si el router no responde, sus nodos son invisibles.** No se enmascara: el fallo se
   diagnostica en el router, que es donde está. Es una propiedad deseable —se parece a la
   realidad— y no un defecto que haya que sortear.
3. **Los espacios de direcciones de los laboratorios deben ser disjuntos**, o las rutas de
   NetXMS se pisan. Ya es regla de la declaración.
4. **Un nodo final no necesita entrada desde fuera**: si algún día necesita un agente, éste
   sale hacia el servidor; no requiere que el servidor entre.
5. **Menos piezas por laboratorio**: una pata por equipo de red, ninguna por nodo final, y una
   ruta por red declarada — derivada, no escrita a mano.

### 4.4. El recorrido completo

```
  declaración YAML (estado deseado)
        │
        │  plan:  Ansible lee el mundo por la API y calcula la diferencia
        ▼
  Ansible ──API REST──► Proxmox: crea grupo, redes y nodos
        │                       (identidad derivada: id, nombre, MAC)
        │
        │  arranque: el agente escribe y ejecuta un script en el EQUIPO DE RED,
        │            que aún no tiene dirección (sin consola y sin IP)
        ▼
  el equipo de red recibe su dirección de gestión en la red OOB
        │
        ├──► Ansible configura por OOB: RouterOS por su REST
        │    y los nodos finales por SSH, con el router como salto
        │
        └──► NetXMS observa: equipos de red por OOB; nodos finales por rutas
             hacia las redes del laboratorio → consola web
```

Un laboratorio nuevo aparece en la consola de NetXMS **sin que nadie dé de alta nada por
laboratorio**: los equipos de red tienen dirección de gestión, las rutas se derivan de lo
declarado, y la topología se dibuja con lo que los propios equipos cuentan.

---

## 5. La declaración de un laboratorio

Siguiendo la convención más extendida en infraestructura declarativa —la de Compose y
Terraform, también la de los manifiestos de Kubernetes—: **primero se nombran las redes,
después los nodos, y los nodos se refieren a las redes por su nombre**. No hay referencias
posicionales ni números mágicos, y el orden de las patas es el orden en que se declaran.

```yaml
lab: <letra>_<título>                    # la letra es la cabeza de cada cable y el nombre
                                         # es también el de la carpeta, el fichero y el pool

address_spaces: [<cidr>, ...]            # addresses this lab may use; no other lab may

networks:                                # named networks of the lab
  - name: <network-name>
    address: <cidr>

nodes:
  - role: <equipo>                       # su nombre en todas partes: dos letras de tipo,
                                         # una de función y el ordinal (`swc2`)
    type: router | server | workstation | switch
    stage: <integer>                     # coarse order: a stage waits for the previous one
    after: [<role>, ...]                 # optional: fine order inside the same stage
    resources: {cores, memory, disk}
    image: <image, when it applies>
    networks: [<network-name>, ...]      # order is the interface numbering: net0, net1...
    address: <cidr | dhcp>               # dhcp = asks its network for one
    configure:                           # optional: if absent, the engine does not go in
      <area>: { ... }
```

Reglas:

1. **Nada derivado.** Ni identificadores, ni MAC, ni direcciones de gestión. El **nombre de un
   equipo sí se declara entero** —tipo, función y ordinal— y el motor lo comprueba contra el tipo
   declarado: si no cuentan lo mismo, se para antes de tocar nada.
2. **Los espacios de direcciones son exclusivos** entre laboratorios, y **no se confía en la
   palabra**: el plan lo comprueba contra lo que ya existe en el hipervisor (y contra el espacio
   de gestión), y falla antes de tocar nada si se pisan.
3. **El tipo de nodo manda:** lo que un tipo no puede hacer se rechaza antes de tocar nada,
   con el motivo. Un puesto no enruta; un router no es un puesto.
4. **El orden es explícito y en dos niveles.** La **etapa** ordena lo grueso —una etapa no
   empieza hasta que la anterior converge y sirve— y, dentro de una etapa, `after` ordena lo
   fino: un nodo espera a que los roles que cita estén sirviendo. Lo que no se declara no se
   adivina, y así se evita la carrera de direccionamiento por construcción y no por suerte.
5. **Lo declarado se aplica y lo ausente se respeta:** dentro de un área declarada, lo que
   sobra se quita; fuera de las áreas declaradas, el nodo se deja como está.

---

## 6. El interior de los nodos

Tres vías, cada una en un fichero del motor:

- **RouterOS, el primer arranque:** un único script, escrito y ejecutado por el **agente del
  hipervisor**, que le da su dirección de gestión y abre el servicio (§3.8). Es lo único que el
  agente hace, y no se vuelve a usar después.
- **RouterOS, a partir de ahí:** su API REST, autenticada, por la red de gestión.
- **Linux:** SSH, por la red de gestión hasta el router del laboratorio y desde ahí a la red del
  nodo, con la contraseña del fichero de secretos (§10).

Lo configurable se declara por **áreas**, nombradas con el vocabulario de la API del equipo
(`addresses`, `routes`, `dhcp_server`, `services`, `users`, `snmp`). Un área declarada se
converge entera; un área ausente se deja intacta. El **nombre del equipo no es un área**: sale del
rol declarado y el motor lo escribe en todas partes (el hostname del invitado, la identidad del
RouterOS), así que declararlo otra vez sería una segunda verdad esperando a contradecirse. Todas las
áreas y sus claves caben en **una tabla que se lee de una sentada**; si un laboratorio necesita algo
que no está, se añade la primitiva al motor **con su prueba**, no se abre una puerta genérica del
tipo «ejecuta esta orden» ni se permite un caso especial por laboratorio.

El área `snmp` enciende el servicio y mantiene una comunidad de **sólo lectura, restringida a la
red de gestión**: el laboratorio dice `enabled` y nombra la comunidad (`community_from`), y el
valor se resuelve en `secrets.yml`. Sin el área, el motor no toca el servicio; es lo que permite
a NetXMS leer nombre, interfaces, rutas y tabla ARP del router, y de ahí lo que cuelga de sus
redes (§3.4).

El área que abre el laboratorio al plano de gestión (permitir el cruce desde la red de gestión
hacia sus redes) forma parte del router y la aplica el motor: sin ella, §4.3.

---

## 7. Observabilidad

- La consola web de NetXMS **es** la vista: estado de cada equipo, interfaces, topología,
  histórico y alertas.
- **Equipos de red:** alcanzables por su dirección de gestión; se vigilan por SNMP (el propio
  equipo expone su estado) y por ICMP.
- **Nodos finales:** alcanzables por las rutas derivadas hacia las redes del laboratorio; se
  vigilan por ICMP y aparecen como hojas del segmento de su router. Sin agente en esta fase.
- Un laboratorio desplegado aparece **porque lo declarado basta** para saber a quién alcanzar.
- Al destruir un laboratorio, sus equipos desaparecen de la vista viva y **el histórico se
  conserva**: la observación es persistente, el laboratorio es efímero.
- NetXMS no configura nodos: lo que se configure se configura por la vía normal de cada uno.

---

## 8. El informe de una ejecución

No hay registro propio, ni ficheros por llamada, ni nada que ensucie el repositorio. Lo que
queda de una ejecución es **el informe que Ansible produce**: qué tareas corrieron, qué
cambió, qué falló, cuánto tardó.

- Se guarda como **texto, fuera del repositorio**, y en CI se publica como artefacto del
  trabajo. El repositorio guarda declaración, documentación y código; nada más.
- Se puede subir el detalle con la verbosidad de Ansible cuando hace falta depurar; no se
  guarda por defecto.
- **Lo que se pierde** con esta decisión: la traza por llamada a la API. **Por qué es
  aceptable**: el informe ya nombra la tarea y el recurso, y para el detalle fino están la
  verbosidad de Ansible y el registro de tareas del propio hipervisor. Un diario por llamada se
  pagó con mantenimiento y no se leyó nunca.
- **Las credenciales nunca aparecen** en el informe: las tareas que las tocan se marcan para
  que su salida no se imprima.

---

## 9. Depuración por SSH: uso excepcional y declarado

El motor nunca usa SSH contra el hipervisor (§3.1). Pero **durante el desarrollo** hace falta
ver las cosas por dentro: por qué un router no respondió, qué le pasó a una interfaz, qué dice
el registro de un sistema. Para eso existe una vía de depuración por SSH, **temporal y
excepcional**, a cualquier máquina: el hipervisor, una VM, un RouterOS o un contenedor.

1. **Sólo para diagnosticar.** Nunca para cambiar el mundo: si algo se puede saber por la API
   o por la vía normal del equipo, se sabe por ahí.
2. **Sólo cuando la vía normal no alcanza**, y se anota qué se intentó antes y por qué no
   bastó.
3. **Su fruto es una mejora del harness.** Lo averiguado por SSH se convierte en una
   comprobación nueva, un mensaje de error mejor o una primitiva del motor. Una sesión de
   depuración que no deja nada es una sesión perdida.
4. **No deja código.** Ningún fichero del motor, ninguna tarea y ningún verbo abre una conexión
   SSH que no sea la vía declarada hacia un Linux. La depuración se hace a mano, fuera del
   motor.
5. **Se dice cuando se usa:** en el informe de lo hecho, qué se miró por SSH y qué se aprendió.

---

## 10. Credenciales y autenticación

Fase experimental: **la simplicidad manda**.

- Todo en **un fichero `secrets.yml` en texto plano**, ignorado por git. Sin vault, sin
  cifrado, sin gestor de secretos y sin certificados.
- **Sin contraseña cuando no es obligatoria**: si un equipo o una API admiten acceso sin
  autenticar, se usa así.
- Cuando la autenticación es obligatoria, **usuario y contraseña** bastan; nada de certificados
  ni de rotación.
- Las credenciales **no se imprimen** en la salida de Ansible.
- **El token del hipervisor lleva permisos mínimos, y cada permiso ampliado tiene su motivo
  escrito.** Lectura del agente para observar, y ejecución del agente
  (`VM.GuestAgent.Unrestricted`) **sólo** para el arranque de los routers (§3.8). Está acotado
  al pool del laboratorio, así que no alcanza a nada que no sea suyo.
- Se asume y se dice: es un entorno de laboratorio, aislado y de usar y tirar. Llevarlo a
  producción obligaría a cambiar esta sección entera.

---

## 11. Repositorio, versiones y entrega continua

Desde el primer commit, porque el proyecto va a cambiar mucho y conviene ver su evolución:

- **Versión semántica** (`MAYOR.MENOR.PARCHE`) en un fichero `VERSION`, con su `CHANGELOG.md`.
  Mientras la MAYOR sea `0`, cualquier MENOR puede romper.
- **GitHub** con ramas cortas por cambio (`feat/…`, `fix/…`, `docs/…`), pull request y
  *squash* a `main`: un cambio, un commit.
- **CI en cada pull request**: las comprobaciones del repositorio, la comprobación de
  documentación y el *lint* de lo que se pueda analizar. Un pull request no se mezcla con el CI
  en rojo.
- **Release por etiqueta**: al publicar, la versión sube, el CHANGELOG pasa de «no publicado» a
  su versión con fecha, se etiqueta y se crea la release con esa entrada.
- **Nunca se sube** `secrets.yml`, ni informes de ejecución, ni nada que no sea declaración,
  documentación o código.

---

## 12. Lo que se descarta del intento anterior, y lo que se deja para más adelante

| se descarta | por qué |
| --- | --- |
| Muchos ficheros y subdirectorios por función | Nadie sabía dónde vivía nada; cada cambio costaba una exploración |
| Un registro de decisiones por cambio | Creció más rápido que el producto y se volvió burocracia |
| Decenas de comprobaciones | Se mantenían por sí mismas; nadie recordaba qué protegía cada una |
| Un vocabulario del interior con una casilla por caso | Escribir un laboratorio exigía estudiarlo; el modelo se volvió el producto |
| Esperas de duración fija («duerme y mira») | Despliegues lentos y, a veces, procesos parados sin motivo |
| Un equipo de paso (bastión) por laboratorio | Un invitado, una red y un arranque más por laboratorio, para hacer lo que ya hace la red de gestión |
| Antenas (agente proxy) por laboratorio | Piezas de más que sólo existían porque el observador no llegaba |
| Un diario por llamada en formato máquina | Ruido que se mantiene y no se lee, y que ensucia el repositorio |
| La consola gráfica (VNC) para arrancar un equipo | No es texto: no se puede leer entera ni buscar en ella una marca |
| Un camino de configuración distinto del de observación | Dos planos que mantener sincronizados |
| La consola como camino normal de arranque | Ya no hace falta: el agente escribe y ejecuta el script de arranque por la API; la consola queda para emergencias |

**Lo que se conserva, porque funcionó:** la separación motor/laboratorio; el estado deseado en
YAML como única verdad; derivar la identidad en vez de guardarla; una sola vía de acceso por
protocolo; la documentación generada y comprobada; y el hábito de no dar nada por bueno sin la
salida real del comando que lo prueba.

**Lo que se deja para más adelante, con su porqué:** el **agente** de monitorización dentro de
los nodos finales (daría CPU, memoria y procesos, a cambio de instalar y mantener una pieza más
en cada invitado; hoy basta con saber si el nodo está vivo y cómo está su segmento), la
**terminal** de la consola web para nodos finales (hoy sólo para equipos de red), y las
**máquinas virtuales con cloud-init** (los contenedores cubren el caso, y el primer arranque de
un router ya lo resuelve el agente: en este hipervisor la vía de metadatos está cerrada, §3.8).

---

## 13. Entregables, en dos fases

### Fase 1 — el mínimo que demuestra el modelo

1. Repositorio `Netlabs` con el ejecutable único, `engine/`, `labs/`, un README que explica el
   modelo sin valores de ningún laboratorio, `VERSION`, `CHANGELOG` y CI en verde.
2. **Laboratorio mínimo**: un router, dos redes y dos puestos que toman dirección del router.
3. Ciclo completo en verde: `plan`, `apply` (que termina demostrando servicio) y un segundo
   `apply` **sin cambios**.
4. Los equipos del laboratorio **aparecen en la consola de NetXMS**: el router por su dirección
   de gestión, los puestos por la ruta derivada hacia su red.
5. Un router recién creado recibe su dirección de gestión **sin consola y sin tocar nada a
   mano**, y la prueba es la lectura del agente y la respuesta del propio router.
6. `destroy` retira el laboratorio sin residuos y el histórico de NetXMS sobrevive.

### Fase 2 — el laboratorio de dos sedes

6. Dos sedes con **la misma numeración interna por departamento** (ventas, ingeniería,
   marketing), unidas por una red de tránsito, cada sede con su router y **una ruta estática
   hacia la sede contraria** —no un bridge compartido—.
7. Ciclo completo en verde, con la segunda pasada sin cambios y las dos sedes intercambiando
   tráfico.
8. Todo el laboratorio visible en NetXMS como una topología de dos sedes.

### Evidencia

Cada entrega se acompaña de la **salida real** de los comandos, el informe de Ansible y el
resultado de las comprobaciones. No se afirma nada que no esté respaldado por esa salida.

### Criterio de aceptación global

Una persona que no haya participado escribe un laboratorio nuevo **leyendo sólo el README y un
ejemplo de declaración**, y el motor lo despliega **sin tocar `engine/`**.

---

## 14. Glosario

| término | qué es |
| --- | --- |
| **lab** | topología declarada, efímera, con su propio espacio de direcciones |
| **engine** | programa genérico que la hace existir; no conoce ninguna topología |
| **node** | un elemento del laboratorio: router, switch, server, workstation |
| **network device** | el que hace la red (router, switch): tiene red de gestión |
| **end node** | el que usa la red (server, workstation): se llega a él por su router |
| **role** | el papel de un node dentro de su lab: su contrato de referencia y su nombre en todas partes |
| **stage** | unidad de orden: una no empieza hasta que la anterior converge y sirve |
| **area** | conjunto de ajustes que se convergen enteros dentro de un node |
| **OOB** | red de gestión compartida, por la que se llega a los equipos de red |
| **management pool** | pool del servicio persistente: es el de su laboratorio de control, y ningún otro laboratorio lo toca |
| **lab pool** | pool efímero de un laboratorio, que se llama como él; es el alcance de `destroy` |
| **guest agent (QEMU)** | agente del hipervisor: sólo **lee** estado del invitado |
| **serial console** | la consola de texto del router, alcanzada por la API; por ahí va la línea de arranque |
| **guest agent (QGA)** | el agente del CHR: lee estado y puede ejecutar un script de RouterOS |
| **derive** | calcular a partir de la identidad del nodo, en vez de guardarlo |
| **ownership boundary** | cómo se distingue lo creado por Netlabs de lo ajeno |
| **service proof** | la comprobación, al final de `apply`, de que lo declarado **sirve** |
