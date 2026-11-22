# Adaptar un cuerpo modelado como avatar

`build_realistic.py` toma un GLB con **una malla de cuerpo humano** (puede venir a medias, sin aplicar el
modificador Espejo, y en pose T) y genera `frontend/public/models/avatar_body.glb`, que la app usa por defecto.

```
python build_realistic.py modelo.glb                 # escribe frontend/public/models/avatar_body.glb
python build_realistic.py modelo.glb salida.glb
```

Requiere Python 3 + numpy (no necesita Blender). Tarda ~25 s.

## Qué hace

1. **Suelda** los vértices duplicados, **espeja** la mitad que falta y verifica que la malla quede cerrada.
2. **Escala** a 1,75 m, pies en y = 0, mirando a +Z.
3. **Pose A**: si los brazos están horizontales, los baja girándolos desde el hombro, con pesos suaves hacia el
   tronco (el resto del cuerpo no se mueve).
4. Detecta el **esqueleto** (hombros, codos, muñecas, entrepierna, rodillas, tobillos, cuello, cabeza) y las
   **referencias del tronco** (cadera, cintura, pecho, axila).
5. **Calibra** suavemente (hasta ±18%) cada parte alrededor de su propio eje hacia los perímetros promedio.
6. **Transfiere los 13 shape keys** del cuerpo procedural: cada vértice se asocia a la misma parte, a la misma
   altura relativa (por las referencias del tronco) y al mismo ángulo alrededor del hueso; el desplazamiento se
   gira a la dirección de su hueso y se escala a su grosor. A `sex_female` se le agrega el busto.
7. **Subdivide** (Loop) la malla y los shape keys juntos: superficie suave.
8. Guarda en el archivo (`extras` de la malla): el atributo `_ZONE`, los **anillos de medición** de la forma base y
   de cada shape key, y los **perímetros propios** del modelo (hombre y mujer). La app compara las medidas del
   alumno contra esos perímetros, así el promedio se ve como el modelo y cada medida mueve el peso correcto.

## En la app

- Por defecto se carga `/app/models/avatar_body.glb` (~1,7 MB; se descarga una vez y queda en caché).
- Para volver al cuerpo generado por código: `VITE_AVATAR_GLB=none` en `frontend/.env` y `npm run build`.
- El avatar es solo cuerpo (sin ropa ni pelo): se personalizan sexo, tono de piel, musculatura, grasa, medidas y
  el moldeado por zona.

## Si cambia el modelo

Exportarlo desde Blender como GLB (Y arriba, un solo objeto de cuerpo, sin rotaciones sin aplicar) y volver a
correr el script. Si el cuerpo viene en pose A ya hecha, la detección de axila lo detecta y no rota (o rota poco).
