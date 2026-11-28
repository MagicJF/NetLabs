# 0021 — El registro lo escucha la vista, y lo enciende el entorno

**Fecha:** 28 de noviembre de 2026
**Estado:** aceptada
**Ámbito:** la recogida de los registros de los equipos en la vista; quién declara que se
escuchan; cuándo hay que reiniciar el servicio de la vista y cuándo no.

## El problema

La vista sabe recoger los registros que le manden los equipos, pero nace con la escucha apagada
—medido en la instalación: `Syslog.EnableListener = 0` y nada escuchando en el 514—. Encenderla
tiene dos partes incómodas: la variable **se guarda en la base del servicio**, no en su fichero de
arranque, y el servicio **sólo la lee al arrancar**, así que un cambio no surte efecto hasta que se
reinicia.

De ahí salen dos preguntas que no se contestan solas. La primera: ¿lo enciende el motor, o se
documenta como un paso a mano que se da una vez? La segunda, si lo enciende: reiniciar el servicio
de la vista es cortar un momento lo que están mirando todos los laboratorios a la vez, así que
—¿cuándo se reinicia, y con qué criterio decide el motor que hace falta?

## La decisión

**1. La escucha es del entorno, no del laboratorio.** Se declara en `observabilidad.registro`, junto
a la identidad con la que se sondea, y por el mismo motivo: un equipo no elige quién le escucha,
igual que no elige con qué se le mira. Si lo declarase cada laboratorio, el mismo sitio recogería
registros de unas máquinas y de otras no, y lo que es una propiedad del sitio —dónde van a parar los
registros— quedaría repartida en cada declaración. El laboratorio no lo nombra; la validación lo
rechaza si lo intenta (ADR 0019, misma forma).

**2. El motor la deja puesta, y sólo la diferencia.** Se lee una vez —`GET /server-config`, todas
las variables juntas— y se escribe únicamente lo que difiere. Un `apply` repetido no escribe nada.
La variable se escribe por el mismo API y con el mismo idioma que el resto de la vista
(`PUT /server-config/{nombre}`), no por la puerta de atrás de la base.

**3. El reinicio no se adivina: lo dice la variable.** Cada variable de configuración del servicio
trae, en la propia lectura, si su cambio exige reiniciarlo (`needServerRestart`). El motor no lleva
su propia lista de nombres que reinician —esa lista habría que mantenerla y se quedaría vieja—, se
lo pregunta a quien lo sabe. Sólo se reinicia si de verdad se ha escrito algo que lo pide, y una
escritura que no cambió nada no reinicia jamás. **Si la variable no se pudo leer** —no está, o no es
visible para la sesión del motor—, se da por hecho que el cambio exige reinicio: ante la duda, que
el cambio surta efecto, porque lo contrario es creer encendido lo que está apagado, que es la peor
de las mentiras de una vista.

**4. Después de reiniciar, se espera a que vuelva a atender.** Un servicio que se reinició y no
levanta dejaría el despliegue en verde y la vista muerta. El paso no se da por bueno hasta que el
servicio vuelve a escuchar.

## Lo que esto no hace todavía

Enciende la escucha, que es la mitad que estaba apagada, pero **el registro no llega solo**: falta
la otra mitad —que los equipos manden sus registros a la vista (en RouterOS, la acción de registro
con destino remoto)— y la comprobación de que un mensaje entra y se guarda. Van aparte, como todo
lo demás, y no cambian nada de lo de arriba: cuando se declaren, la escucha ya estará puesta.

## Consecuencias

- El laboratorio no declara nada nuevo, y no debe: `observabilidad.registro` vive en el entorno.
- Un `apply` normal no reinicia la vista. Sólo reinicia la primera vez —cuando la escucha pasa de
  apagada a encendida— y sólo si alguien cambia el puerto. A partir de ahí, silencio.
- El motor deja de tener conocimiento propio sobre qué variables reinician el servicio: se muda a la
  propia vista, que es quien lo sabe y quien lo cambia de versión.
