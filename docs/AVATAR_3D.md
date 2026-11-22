# Avatar 3D con morph targets (shape keys)

> **Modelo actual:** la app carga por defecto un cuerpo modelado y adaptado con `tools/avatar/build_realistic.py`
> (`frontend/public/models/avatar_body.glb`). El avatar es **solo cuerpo**: sin ropa ni pelo (`BODY_ONLY` en
> `avatarSpec.js`). El cuerpo generado por código queda como respaldo si el archivo no carga.

El avatar es **una única malla base** con **13 morph targets**. El cliente solo mueve pesos
(`morphTargetInfluences`) en tiempo real; el backend guarda la **configuración**.

```
avatarSpec.js         → opciones del avatar, colores, proporciones de referencia del tronco
morph/sdfBody.js      → el cuerpo como UNA superficie continua (campo de distancia con uniones suaves),
                        mallado (surface nets), proyección a cada target y anillos de medición
morph/targets.js      → malla base + 13 targets, pesos, ropa pintada por vértice, accesorios de la cabeza
morph/worker.js       → genera el cuerpo en un Web Worker y lo guarda en IndexedDB (una vez por dispositivo)
morph/AvatarEngine.js → Three.js: shape keys en GPU, normales recalculadas al cambiar, resaltado, GLB externo
BodyViewer.jsx        → escena, cámara, anillos, tocar zonas y moldear arrastrando
AvatarEditor.jsx      → pestañas Cuerpo · Moldear · Pelo · Ropa
backend/apps/members/avatar.py → esquema versionado, validación y los mismos pesos en Python
```

## Cuerpo continuo

El cuerpo ya no son piezas pegadas: es una sola superficie. Tronco, cuello, cabeza, brazos y piernas se
definen como formas matemáticas y se funden con uniones suaves (*smooth min*); cada extremidad se funde con
el tronco pero no con la otra (las piernas no se pegan entre sí). La malla (~37.000 vértices) se genera una vez
por dispositivo (~3 s en un Web Worker la primera vez, después se lee de IndexedDB al instante).

Cada target se obtiene llevando cada vértice de la malla base a la superficie del cuerpo modificado (siguiendo
la articulación y la normal) y luego **suavizando el campo de desplazamientos** sobre la malla, así no hay
pliegues. Los targets se muestrean a mitad de camino y se duplican (aproximación lineal más fiel).

## Qué es morph y qué regenera

| Cambio | Qué pasa | Costo |
|---|---|---|
| Sexo, musculatura, grasa, medidas, moldeado, altura | Solo pesos y escala (animado, en la GPU) + normales recalculadas | 5-10 ms |
| Ropa, colores | Se repinta el color por vértice | < 10 ms |
| Peinado | Se rearma la malla de la cabeza (el cuerpo queda en caché) | ~20 ms |
| Primera vez en un dispositivo | Se genera el cuerpo en segundo plano y se guarda | ~3 s |

## Moldear (estilo Sims)

En el editor, pestaña **Moldear**: se toca una zona (se resalta con el color del gimnasio) y se arrastra hacia
afuera para agrandarla o hacia adentro para achicarla. También hay un control deslizante por zona. El valor se
guarda en `avatar.sculpt` (`{"hip": 0.4, "arm": -0.2}`, de −1 a 1) y se **suma** al peso `girth_<zona>` que salga
de las medidas reales: 1 equivale a +40% de perímetro.

## Shape keys

| Nombre | Peso | Significado |
|---|---|---|
| `sex_female` | 0 a 1 | cuerpo masculino → femenino |
| `muscle` | -1 a 1 | musculatura (0 = promedio) |
| `fat` | -0.43 a 1 | grasa corporal (0 = promedio) |
| `girth_neck`, `girth_shoulders`, `girth_chest`, `girth_waist`, `girth_abdomen`, `girth_hip`, `girth_arm`, `girth_forearm`, `girth_thigh`, `girth_calf` | -0.7 a 1.4 | cada 1.0 = +40% de perímetro respecto de la referencia |

Los pesos de las medidas salen de `medida / referencia` (referencias en `avatar.py` y `avatarSpec.js`).
Los pesos negativos son válidos: el shader extrapola linealmente.

## API

```
GET  /api/v1/me/avatar/       → {"avatar": {...config v2}, "sex": "M", "morph": {"sex_female": 0, "muscle": 0.2, …}}
PUT  /api/v1/me/avatar/       → guarda la configuración (se valida y completa con valores por defecto)
GET  /api/v1/avatar/schema/   → opciones, colores, targets, referencias y valores por defecto
GET  /api/v1/trainer/students/<id>/ → incluye "avatar_morph" con los pesos del alumno
```

Configuración (v2):

```json
{"v": 2, "sex": "F", "skin": 2, "hair_style": "ponytail", "hair_color": "#3f2a1d",
 "top_style": "sports", "top_color": "#ff5a1f", "bottom_style": "leggings", "bottom_color": "#111827",
 "shoe_color": "#f5f5f4", "muscle": 0.6, "fat": 0.35, "use_measures": true,
 "sculpt": {"hip": 0.3, "waist": -0.2}}
```

## Usar un modelo hecho por un artista (Blender → GLB)

La especificación completa para el artista está en **`docs/MODELO_ARTISTA.md`** (medidas, pose, shape keys,
materiales, prendas como objetos, atributo de zonas y opciones de exportación). Para activarlo:

1. Copiar el archivo a `frontend/public/models/avatar_base.glb`.
2. En `frontend/.env`: `VITE_AVATAR_GLB=/app/models/avatar_base.glb` y recompilar (`npm run build`).

Si el archivo no carga o no tiene shape keys, el motor avisa en la consola y usa el cuerpo generado por código.
Con un GLB externo, la ropa y el pelo se muestran u ocultan por nombre de objeto; el resaltado de zona al
moldear solo está disponible en el cuerpo generado por código.
