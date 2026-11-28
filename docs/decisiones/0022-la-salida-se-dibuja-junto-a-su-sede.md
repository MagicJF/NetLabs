# 0022 — La salida se dibuja junto a su sede, y el tránsito en el centro

**Fecha:** 28 de noviembre de 2026
**Estado:** aceptada
**Ámbito:** el reparto del plano (`deployment_engine/tools/plano.py`); las nubes con `exit: true`
de un laboratorio; el rótulo de cada salida.

## El problema

El laboratorio `f_acme_cuatro_departamentos` declara **tres nubes**: el tránsito del proveedor y una
salida por sede (`ny_salida`, `tk_salida`). El plano las dibujaba **apiladas en columna, centradas
las tres en el mismo `x`**, encima de la caja de la empresa. Y las dos salidas salían con **el mismo
rótulo** —«Salida»— y sin bloque de direcciones (regla del ADR 0015), así que eran **indistinguibles
entre sí** y no se veía cuál era la de qué sede.

Peor: los routers de borde viven en los **extremos** de la empresa —`rte1` en el lado de Nueva York,
`rte2` en el de Tokio, cada uno a caballo del techo de su sede—, así que sus patas de salida tenían
que subir atravesando la caja del tránsito para llegar a una nube centrada que no era la suya. El
dibujo decía lo contrario de lo que dice la declaración: una salida de nadie, compartida.

La salida es **de cada sede** (ADR 0018: una frontera por sede, no una nube común). El plano tenía
que decir lo mismo.

## La decisión

**Ninguna nube cuelga del centro por ser nube.**

- **El tránsito del proveedor se queda donde estaba**: una **banda centrada** por encima de la
  empresa, que es por donde pasan las dos sedes —es del centro, y el centro es la empresa entera—.
- **Cada salida (`exit: true`) se dibuja junto a su propia sede**, en la **vertical del router de
  borde que la alcanza**. Ese router tiene una pata en la salida **y otra en su sede**: ese par es
  lo que ata una nube a su sitio —es dato del laboratorio, no una suposición—. La nube se apoya
  sobre el techo de la empresa, en la misma `x` que su router de borde, y se lee como la de *esa*
  sede.
- **Cada salida lleva un rótulo que la distingue** de la otra («Salida de New York», «Salida de
  Tokyo»), porque son dos nubes distintas y sin nombre propio el plano las dibujaría idénticas.

En el motor, la salida deja de ser una banda más del techo y pasa a ser una nube **anclada**: el
reparto de las sedes no depende de dónde caigan las nubes, así que se reparte una vez para saber por
dónde cae cada sede, se ancla cada salida sobre la vertical de la suya y se reparte otra vez. El
router de borde —que puede tocar **dos** nubes, el tránsito y su salida— se asoma bajo **su** salida,
no bajo la del centro.

## Alternativa descartada

**Dibujar las salidas como bandas estiradas de lado a lado**, una fila por nube. Se descartó porque
una nube estirada deja de parecer una nube, y porque una banda ancha no se lee como «de esta sede»:
se lee como «de todo el ancho», que es justo lo que no es. La nube pequeña, anclada sobre su router,
dice lo que dice la declaración sin una palabra de más.

## Lo que cuesta

Un reparto que se hace en **dos vueltas** —medir, repartir, anclar las salidas, repartir otra vez—
en vez de una. Es barato y acotado: las nubes no influyen en dónde caen las sedes, así que la
segunda vuelta no mueve nada que la primera haya asentado; sólo coloca las salidas. A cambio, el
plano vuelve a contar la verdad: el tránsito es del centro y la salida es de su sede.
