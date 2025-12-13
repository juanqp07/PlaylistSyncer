
Wrapper para spotdl / yt-dlp
============================
Archivos generados en: /mnt/data/spotdl_wrapper

Archivos:
- main.py           : Script principal (CLI)
- config.json       : Archivo de configuración editable
- requirements.txt  : Paquetes sugeridos (spotdl, yt-dlp, tqdm, mutagen)

Cómo usar:
1) Edita /mnt/data/spotdl_wrapper/config.json con tus preferencias.
2) Crea un entorno virtual y instala dependencias:
   python3 -m venv venv
   source venv/bin/activate
   pip install -r /mnt/data/spotdl_wrapper/requirements.txt
3) Ejecuta:
   python /mnt/data/spotdl_wrapper/main.py <url1> <url2>
   python /mnt/data/spotdl_wrapper/main.py --file urls.txt
Nota: El script delega en las herramientas 'spotdl' y 'yt-dlp' en PATH. Ajusta config.json
para pasar args extra si quieres opciones específicas de cada herramienta.
