# 0023 — El tema de la consola no es del entorno: lo pone el navegador, y el motor no lo toca

**Fecha:** 28 de noviembre de 2026
**Estado:** aceptada
**Ámbito:** el tema (claro/oscuro) con el que se ve la consola web de NetXMS; de dónde lo saca;
si el motor puede o debe convergerlo; qué camino le queda a quien quiera verla en oscuro.

## El problema

Quien mira el sitio preguntó, con estas palabras: «También quisiera netxms en dark mode y así lo he
configurado desde la webUI, pero no lo veo aplicarse, sigue viéndose como light mode.» El precedente
que ordena la duda es la escucha de registros (ADR 0021): una propiedad del sitio —cómo se mira a los
equipos— se declara en el entorno y el motor la deja puesta de forma idempotente. La pregunta, por
tanto, no es «¿cómo lo enciendo?», sino «¿es esto una palanca del servidor que el motor pueda
declarar y converger, o es cosa de cada navegador?». Antes de escribir nada hay que averiguarlo, y
«no se puede desde el servidor» es una respuesta válida si viene con la evidencia.

## La averiguación

**El tema no sale del servidor: sale del cliente.** Tanto la consola de escritorio como la web leen
el tema de una **preferencia local del cliente**, la variable `CurrentTheme`, de su
`PreferenceStore` —el mismo almacén donde guardan el tamaño de las ventanas y los formatos de
fecha—, nunca de una variable de configuración del servidor:

- La página de temas del cliente **escribe una preferencia local**, no llama al API del servidor:
  `PreferenceStore.getInstance().set("CurrentTheme", …)` —
  `src/client/nxmc/java/src/rwt/java/org/netxms/nxmc/base/preferencepages/ThemesPage.java:439`
  (y la de escritorio, gemela, en `…/src/swt/java/…/preferencepages/ThemesPage.java`).
- El motor de temas lee ese valor del mismo almacén y sólo de ahí:
  `String currentTheme = ps.getString("CurrentTheme")` —
  `src/client/nxmc/java/src/main/java/org/netxms/nxmc/resources/ThemeEngine.java:247`. Si no hay
  valor, o es `[automatic]`, el tema lo decide el **sistema operativo del navegador**
  (`WidgetHelper.isSystemDarkTheme`, misma clase).

**En la consola web, además, ese almacén es por navegador y vive en el servidor de aplicaciones.**
La versión web (RWT) del cliente no guarda la preferencia en el equipo del usuario, sino en un
fichero **dentro del contenedor de servlets**, uno por identificador de navegador:

- `open(...)` construye la ruta como `stateDir + "/nxmc.preferences." + getStoreId()` —
  `src/client/nxmc/java/src/rwt/java/org/netxms/nxmc/PreferenceStore.java:62`— y `getStoreId()`
  (líneas 82-138) la saca de una **cookie** (`COOKIE_NAME`) del navegador, generando un `UUID`
  nuevo la primera vez. En la consola de escritorio (SWT) la ruta es fija
  (`stateDir/nxmc.preferences`, `…/src/swt/java/…/PreferenceStore.java:56`).

**No existe ninguna variable de servidor para el tema: medido, no supuesto.** La lectura viva de la
configuración del servicio —`GET /server-config`, la misma que usa el motor (`ADR 0021`)— devuelve
**438 variables** y **ninguna** es un tema de consola: no hay `WebUI.*`, ni `Theme`, ni
`ColorScheme`, ni nada con «dark». Las únicas variables con color son de otro asunto: `Server.Color`
(«Identification color for this server», un distintivo del servidor) y
`Objects.NetworkMaps.DefaultBackgroundColor` («Default background color for new network map
objects»). Las `Client.*` (`Client.BaseURL`, `Client.EnableWelcomePage`, los formatos de fecha del
panel) son valores por defecto del cliente, y el tema no está entre ellos. El endpoint sirve, en
efecto, lo que hay en la tabla `config` del servidor (`is_visible=1`):
`src/server/webapi/server_config.cpp` (`H_ServerConfigVariables`).

**Y en la web no se aplica porque la propia consola web lo tiene roto.** El síntoma del usuario es un
fallo conocido de NetXMS, no una configuración mal puesta: el asunto **NX-2569** —«Themes does not
work for web», GitHub `netxms/netxms#2772`— describe exactamente esto, «Dark theme styles only part of
elements, should be created full CSS styling for themes». En el foro oficial, quien abre el hilo
cuenta lo mismo palabra por palabra: elige «Dark [built-in]» en las preferencias del cliente web,
pulsa aplicar, y no pasa nada. El propio mantenedor cierra la puerta a arreglarlo en la consola web
antigua: «Theming support is really poor in nxmc, web version especially. With new web UI (that
supports both light and dark themes), I don't think we should put significant efforts into fixing
themes in existing web UI.»

## La decisión

**1. El tema no se declara en el entorno, porque no es una palanca del servidor.** `netlabs.yml` no
gana ningún bloque para esto: no hay variable que el motor pueda leer, diferenciar y escribir, que es
lo que el ADR 0021 exige para declarar algo. Poner un ajuste inventado sería la palanca falsa que el
precedente prohíbe.

**2. El motor no toca nada para esto, y no es una carencia: es una frontera.** La consola web es del
sitio, pero **su aspecto no lo decide el sitio**: lo decide cada navegador, y ni siquiera el servidor
lo guarda. No hay «lo que hay» contra lo que diferenciar, así que no hay `apply` que hacer.

**3. Si algún día cambia la palanca, se revisa.** La consola web **nueva** (Vue, repositorio
`netxms/web-ui`) sí soporta claro y oscuro, y expone el tema como preferencia de UI del cliente
(store de Pinia), no como configuración de servidor: la conclusión de arriba —es del navegador— se
mantiene mientras siga siendo así. Si apareciera una variable de servidor real —comprobable leyendo
`GET /server-config`—, el tema pasaría a ser un candidato al patrón del ADR 0021 como cualquier otra.

## El camino que sí funciona

- **Consola de escritorio (nxmc SWT).** El tema se elige en «Preferences → Themes» y **funciona**
  (`CurrentTheme` en `stateDir/nxmc.preferences`). Es la vía que da oscuro de verdad; el precio es que
  NetXMS no publica ese cliente para ARM/aarch64.
- **Consola web nueva (Vue).** `netxms/web-ui` trae selector de tema claro/oscuro de serie (se puede
  quitar con `VITE_THEME_PICKER=false`). Es la vía web que el propio NetXMS señala como relevo.
- **La consola web antigua (la desplegada, `nxmc-7.0.4.war`) no da oscuro**, y no es cosa de la
  instalación: es el fallo NX-2569. Además, sus preferencias viven en el directorio de estado del
  contenedor (`…/state/nxmc.preferences.<cookie>`), de modo que **se pierden al reiniciar el
  contenedor o al actualizar el WAR** —otra razón por la que no es un sitio donde el sitio deba fiar
  nada—.

## Consecuencias

- `netlabs.yml` y el motor quedan **exactamente como estaban**: este ADR no cambia una línea de
  configuración ni de código, y lo dice para que nadie lo busque.
- La pregunta «¿por qué no se aplica el dark mode?» tiene **una respuesta con evidencia** —lo pone el
  navegador, y la consola web antigua lo tiene roto— en vez de un ajuste del motor que no existiría.
- Queda escrito el criterio para el futuro: **antes de declarar una palanca, se comprueba que el
  servidor la expone** (`GET /server-config`); si el dato vive en el cliente, no es del entorno.
