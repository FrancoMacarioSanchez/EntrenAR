# Especificación del modelo 3D para el artista (EntrenAR)

Este documento es el pedido para quien modele el avatar en Blender. El sistema ya funciona con un
avatar generado por código; cuando llegue este archivo, se reemplaza **sin tocar código**: se copia el
`.glb` y se define una variable de entorno.

## 0. Punto de partida

`tools/blender/build_avatar.py` arma en Blender un modelo que **ya cumple toda esta especificación** (cuerpo continuo,
shape keys, zonas, prendas, peinados y materiales). Lo ideal es partir de ahí y mejorar la forma, la cara y la ropa
sin cambiar los nombres. Ver `tools/blender/README.md`.

## 1. Qué hay que entregar

Un único archivo **`avatar_base.glb`** (glTF binario) con:

- Un objeto **`body`**: el cuerpo completo, una sola malla cerrada (sin piezas separadas en las articulaciones).
- Objetos de **ropa** y **pelo** separados (ver punto 5), con los **mismos shape keys** que el cuerpo.
- Ojos, cejas y boca pueden ser objetos aparte o parte del cuerpo.

Presupuesto: **20.000 a 40.000 triángulos en total** (corre en celulares). Sin huesos ni animaciones.

## 2. Medidas, orientación y pose

| Dato | Valor |
|---|---|
| Unidades | metros (escala 1.0 al exportar) |
| Altura | 1,75 m, pies apoyados en **y = 0** |
| Frente | mirando hacia **+Z** (en Blender: −Y), «Y arriba» activado al exportar |
| Lado derecho de la persona | **x negativo** |
| Pose | «A»: brazos abiertos ~18° del cuerpo, codos casi rectos, palmas hacia adentro, piernas levemente separadas |
| Cuerpo base | hombre promedio, contextura media (ver tabla de referencia) |

Alturas de referencia (el sistema dibuja los anillos de medición a esas alturas; el modelo debería respetarlas
con ±2 cm):

| Zona | Altura (m) | Perímetro de referencia (cm) |
|---|---|---|
| Cuello | 1,535 | 38 |
| Hombros (deltoides) | 1,395 | 116 |
| Pecho (pezones) | 1,30 | 100 |
| Cintura (parte más angosta) | 1,10 | 84 |
| Abdomen (ombligo) | 1,03 | 88 |
| Cadera (glúteos) | 0,905 | 98 |
| Brazo (mitad del bíceps) | 1,28 | 33 |
| Antebrazo (parte más ancha) | 1,08 | 28 |
| Muslo | 0,76 | 56 |
| Pantorrilla | 0,37 | 37 |

## 3. Shape keys (obligatorios, con estos nombres exactos)

Cada shape key se modela **en su valor 1.0** a partir del cuerpo base. El sistema usa valores entre −1 y 2,
así que la deformación tiene que verse bien también **en negativo** (el inverso) y **al doble**.
Evitar que una zona atraviese a otra en esos extremos.

| Nombre | En 1.0 el cuerpo… |
|---|---|
| `sex_female` | pasa a ser una mujer promedio: busto, cintura más angosta, cadera más ancha, hombros y cuello más finos, cara más suave |
| `muscle` | queda muy musculoso (hombros, pecho, brazos y piernas grandes; cintura igual) |
| `fat` | tiene mucha grasa corporal (abdomen, cintura, cadera, muslos y cara; brazos un poco) |
| `girth_neck` | cuello +40% de perímetro |
| `girth_shoulders` | hombros/deltoides +40% |
| `girth_chest` | pecho +40% |
| `girth_waist` | cintura +40% |
| `girth_abdomen` | abdomen (zona del ombligo) +40% |
| `girth_hip` | cadera y glúteos +40% |
| `girth_arm` | brazos (bíceps/tríceps) +40% |
| `girth_forearm` | antebrazos +40% |
| `girth_thigh` | muslos +40% |
| `girth_calf` | pantorrillas +40% |

Los `girth_*` son **locales**: solo cambia esa zona, con transición suave hacia las vecinas.
Los de brazos y piernas afectan a **los dos lados** por igual.

## 4. Materiales (el sistema les cambia el color)

Nombrar los materiales así (en minúsculas): `skin`, `top`, `bottom`, `shoe`, `sole`, `hair`, `eye`, `brow`, `lips`.
El color base se reemplaza en tiempo real; pueden tener texturas de detalle en escala de grises (normal map,
rugosidad), pero **no** color de base pintado.

## 5. Ropa y peinados como objetos

Cada prenda es un objeto separado, ajustado al cuerpo y **con los mismos 13 shape keys** (en Blender:
*Data Transfer* o *Surface Deform* desde el cuerpo y luego «Apply as Shape Key» por cada uno).
El sistema muestra solo el objeto del estilo elegido según su nombre:

| Objeto | Prenda |
|---|---|
| `top_tank`, `top_tee`, `top_sports` | musculosa, remera, top deportivo (`none` = sin objeto) |
| `bottom_shorts`, `bottom_leggings`, `bottom_joggers` | short, calza, jogger |
| `hair_short`, `hair_shaved`, `hair_curly`, `hair_long`, `hair_ponytail`, `hair_bun` | peinados (`bald` = sin objeto) |
| `shoes` | zapatillas (siempre visibles) |

Debajo de la ropa ajustada conviene borrar las caras del cuerpo que quedan tapadas **solo si** no se ven
con ninguna otra prenda; si hay dudas, dejarlas.

## 6. Zonas tocables (atributo `_ZONE`)

Para que el alumno toque una parte del cuerpo y se abra la medida (y para el modo «moldear»), el objeto
`body` debe tener un **atributo de vértice entero** llamado `_ZONE` (dominio: punto) con estos valores:

| Valor | Zona | Valor | Zona |
|---|---|---|---|
| 0 | ninguna (cabeza, manos, pies) | 9 | brazo izquierdo |
| 2 | cuello | 10 | antebrazo derecho |
| 3 | hombros | 11 | antebrazo izquierdo |
| 4 | pecho | 12 | muñeca |
| 5 | cintura | 13 | muslo derecho |
| 6 | abdomen | 14 | muslo izquierdo |
| 7 | cadera | 15 | pantorrilla derecha |
| 8 | brazo derecho | 16 | pantorrilla izquierda |

Se pinta fácil con grupos de vértices y un nodo de geometría que escriba el atributo. Si falta, el sistema
estima la zona por la altura (funciona, pero con menos precisión).

## 7. Exportación (Blender 4.x)

`Archivo → Exportar → glTF 2.0 (.glb)` con:
- Incluir: objetos seleccionados · Transformar: **+Y arriba**
- Datos → Malla: **Aplicar modificadores** (antes de crear los shape keys), UVs, normales, **Atributos** (para `_ZONE`)
- Datos → **Shape keys** activado (normales de shape keys también)
- Sin animaciones, sin skinning, sin cámaras ni luces · Compresión Draco: **no**
- Después de exportar, achicarlo: `npx @gltf-transform/cli quantize avatar_base.glb avatar_base.glb` (objetivo: menos de 8 MB)

## 8. Cómo se prueba

1. Copiar el archivo a `frontend/public/models/avatar_base.glb`.
2. En `frontend/.env`: `VITE_AVATAR_GLB=/app/models/avatar_base.glb` → `npm run build`.
3. Abrir la app como alumno → Cuerpo → «Editar avatar». La consola del navegador avisa si falta algún shape key.
4. Probar: sexo, musculatura y grasa al mínimo y al máximo; cada zona en «Moldear» al −100% y +100%; todas las
   prendas y peinados; tocar cada zona en «Cargar medidas».
