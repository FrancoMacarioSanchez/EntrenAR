# Generador del avatar para Blender

`build_avatar.py` arma el modelo completo de `docs/MODELO_ARTISTA.md`: cuerpo continuo con los 13 shape keys y
el atributo `_ZONE`, prendas (`top_*`, `bottom_*`, `shoes`), peinados (`hair_*`), cara y materiales.
Usa el mismo método que el motor de la app, así que el resultado coincide con el avatar procedural.

## En Blender (4.x)

- **Con interfaz**: Scripting → Abrir `build_avatar.py` → Ejecutar (tarda ~15 s). Aparece la colección
  «EntrenAR Avatar»: se ve un conjunto por vez (los demás objetos quedan ocultos, pero se exportan igual).
  Los shape keys están en Propiedades del objeto → Datos → Shape Keys, con rango −2 a 2 para probar extremos.
- **Por consola** (arma y exporta):
  ```
  blender --background --python build_avatar.py -- --export avatar_base.glb
  ```
- Si un artista lo retoca, al exportar desde Blender conviene achicarlo (Blender no cuantiza):
  ```
  npx @gltf-transform/cli quantize avatar_base.glb avatar_base.glb
  ```

## Sin Blender (Python 3 + numpy)

```
python build_avatar.py --glb avatar_base.glb
```

Escribe un GLB cuantizado (~6 MB, ~3,8 MB con compresión del servidor). En esta carpeta ya hay uno generado:
`avatar_base.glb`.

## Activarlo en la app

1. Copiar `avatar_base.glb` a `frontend/public/models/`.
2. En `frontend/.env`: `VITE_AVATAR_GLB=/app/models/avatar_base.glb` y `npm run build`.

Diferencias con el avatar procedural (el que viene activado): la ropa y el pelo son objetos con volumen real,
pero el archivo se descarga una vez (~4 MB) y la zona no se resalta al moldear. Moldear, medir y todos los
shape keys funcionan igual.
