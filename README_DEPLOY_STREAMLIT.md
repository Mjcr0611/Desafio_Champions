# Despliegue en Streamlit Community Cloud

## 1) Estructura mínima del repo
/ (raíz del repositorio)
├─ polla_champions_2025_streamlit_free.py # tu app
├─ requirements.txt # este archivo
└─ data/ # (opcional) se creará sola si no existe
## 2) Subir a GitHub
1. Crea un repositorio nuevo (público o privado con acceso a Streamlit Cloud).
2. Sube estos archivos:
   - `polla_champions_2025_streamlit_free.py`
   - `requirements.txt`
   - (opcional) un `fixtures.csv` de ejemplo en `data/` si quieres pre-cargar partidos.

## 3) Crear la app en Streamlit Community Cloud
1. Entra a https://streamlit.io/cloud y haz clic en **New app**.
2. Conecta tu cuenta de GitHub si es la primera vez.
3. Selecciona el repositorio, la rama (ej: `main`) y el archivo principal: `polla_champions_2025_streamlit_free.py`.
4. Haz clic en **Deploy**.

## 4) Configurar secretos (contraseña admin)
1. En la página de la app, abre **⋮ > Edit secrets**.
2. Agrega:
ADMIN_PASSWORD = "cambiaEstaClave"
3. Guarda. La app se recargará con el secreto disponible.

> Si no configuras el secreto, la app usará la contraseña por defecto definida en el código.

## 5) Notas de persistencia
- El directorio local puede reiniciarse si la app se actualiza/reinicia. Para jugar entre amigos, suele ser suficiente.
- Si quieres alta persistencia, considera migrar a una base de datos externa (Supabase/Postgres/SQLite alojado) o un backend de archivos (S3/Drive).

## 6) Actualizar la app
- Cada *push* a `main` vuelve a construir la app automáticamente.
- Si agregas nuevas dependencias, actualiza `requirements.txt`.

## 7) Probar
- Abre la URL pública que te da Streamlit Cloud y compártela con tus amigos.
- Verifica carga de fixtures, creación de picks y edición de resultados.