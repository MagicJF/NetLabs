# 0014 — El destroy también desmonta la vista

Fecha: 2026-11-27

## Contexto

El `destroy` retiraba lo que el laboratorio declaró del hipervisor —invitados, puentes, pool—
y del invitado de gestión —las rutas hacia sus redes—, y **no** tocaba la vista. Medido: tras
destruir `d_acme_dos_sedes`, `e_tres_routers` y `b_router_dos_puestos`, la consola de NetXMS
seguía con 68 equipos, de los que **42 eran de laboratorios que ya no existían**, y con el mapa
`b_router_dos_puestos` dibujando una red apagada. Esos equipos no están «en el histórico»: están
en la vista **viva**, en rojo, y quien mira la consola por la mañana ve un sitio averiado donde
sólo hay un laboratorio que se apagó ayer.

La regla escrita (§7) decía que «el histórico se conserva». Leía bien y decidía mal: dejaba
«destruido» y «desplegado» con la misma cara, y obligaba a limpiar a mano cada vez —que es
justo lo que el motor existe para no tener que hacer—. El histórico sin dueño no es histórico:
es basura con buenas intenciones.

## Decisión

`destroy` retira también lo que el laboratorio dejó **en la vista**: sus equipos y su mapa.

- **Qué se retira, se retira por la marca.** Los equipos llevan la marca que el motor escribe
  al registrarlos (`netlabs lab=<lab> role=<rol>`, en los comentarios del objeto); se retiran
  los que llevan la de **este** laboratorio, y ninguno más. El mapa se reconoce por su nombre
  —es el del laboratorio, y la raíz de mapas no admite dos iguales— y **también nace con la
  marca** desde esta decisión, para que mañana su propiedad sea igual de demostrable. Un mapa
  que se llamara igual y llevara la marca de otro no se toca: se para y se dice.
- **Un registro que se llama como un equipo del laboratorio pero no lleva su marca no se
  borra**: se dice en voz alta. El asignador reutiliza direcciones y todos los laboratorios
  comparten nombres de equipo (`rte1`, `wsp1`, `swc1`), así que un nombre no demuestra quién
  creó un registro (AGENTS.md §3.6) — y bastaría con el nombre para que cada `destroy`
  acusara a los equipos de los demás. Se señala sólo si además su dirección cae en una red
  que el laboratorio declaraba (`address_spaces`), que es donde estaría un resto suyo de
  verdad.
- **La vista se desmonta primero**, antes de tocar el hipervisor. Si la vista no se puede
  limpiar —el servicio no responde, el API no da sesión—, el `destroy` se para y el laboratorio
  queda entero: medio destruido es lo único peor que sin destruir.
- **Lo que se retira se lee de vuelta.** La comprobación final del `destroy` —la que cuenta—
  incluye ya «ningún equipo con su marca en la vista, ni su mapa»: no se deduce de lo que se
  mandó borrar, se lee del API después.

Lo que **no** cambia: el servicio persistente y su base —su invitado no es un laboratorio y no
lo toca ningún `destroy` (§2.4, §3.4)—, el histórico de todo lo demás, y la puerta por la que
se habla con su API (la misma: `netxms_entrar.yml` → `interior_ssh.yml`).

## Consecuencias

- **Se pierde el histórico de los equipos de un laboratorio destruido** —las series de ping y
  SNMP de esos nodos, que cuelgan del objeto del equipo—. Es exactamente lo que se busca: el
  laboratorio es efímero, y su rastro se va con él. Lo que se quiera conservar de una ejecución
  hay que exportarlo **antes** de destruir.
- Destruir y volver a desplegar el mismo laboratorio deja la vista como si nunca hubiera
  pasado: sin equipos huérfanos ni mapas de redes apagadas, y con el histórico empezando de
  cero en el segundo despliegue. Es lo que hace que «destruido» se vea destruido.
- La limpieza **no puede llevarse por delante lo de nadie**: sin marca no se borra, y su
  ausencia se dice en el informe en vez de callarse.
- Los mapas creados antes de esta decisión no llevan marca; se reconocen por su nombre, que es
  único en la raíz de mapas. A partir de aquí nacen marcados.

Ver: `deployment_engine/playbooks/destroy.yml`,
`deployment_engine/tasks/netxms_retirar.yml`, `deployment_engine/tasks/netxms_entrar.yml`,
`deployment_engine/tools/converge.py` (`netxms_marca_de`, `netxms_restos_de`,
`netxms_mapa_del_lab`, `netxms_mapa_crear_cuerpo`), `docs/diseno.md` §7,
`docs/decisiones/0003-registrar-los-equipos-en-la-vista.md`.
