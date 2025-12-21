Registro de Cambios

Todos los cambios notables en este proyecto serán documentados en este archivo.

## [1.7.0] - 2025-12-21
### Añadido
- **Carpeta por Playlist**: Cada playlist ahora descarga su contenido en un subdirectorio propio dentro de `downloads/`, incluyendo su archivo `.m3u8` y la carpeta `.sync`.
- **Limpieza Automática**: Al eliminar una playlist desde la UI, se borra también su carpeta de descargas para liberar espacio.
- **Limpieza de Títulos (SpotDL)**: Ahora se eliminan automáticamente términos como "(Video Oficial)", "(Lyric)", "[Letra]", etc., de los títulos de YouTube antes de buscarlos en Spotify, reduciendo errores de "No results found".
- **Responsive Móvil**: Mejoras significativas en la vista de tarjetas de Playlists y Navbar para dispositivos móviles.

### Corregido
- **Crash de Inicio**: Reparado error de indentación crítico en `core.py`.
- **Rutas**: Solucionado error `FileNotFoundError` asegurando la creación recursiva de directorios en tiempo de ejecución.
- **Nombres Seguros**: Forzado de nombres de carpeta ASCII para evitar problemas de compatibilidad con emojis/acentos en el sistema de archivos.

## [1.6.0] - 2025-12-14
### Añadido
- **Modo Turbo (Batch)**: Procesamiento en lotes de 50 canciones para playlists de YouTube. Reduce drásticamente el tiempo de inicio y consumo de CPU.
- **M3U Estándar Profesional**: Generación de archivos `.m3u8` con metadatos completos (`#EXTM3U`, `#EXTINF`), duración exacta (vía `ffprobe`) y títulos correctos.
- **Logs Inteligentes**: Nueva visualización compacta para el procesamiento de lotes ("Procesando lote de 50 canciones...").

### Corregido
- **Estabilidad FFmpeg**: Forzado modo "single-thread" en SpotDL para evitar bloqueos de archivos y errores de conversión durante descargas masivas.
- **Duplicados M3U**: Lógica de anti-duplicados reescrita para ser estricta (línea exacta) y evitar bucles infinitos de reescritura.
- **Protección de Sistema**: Añadido manejo de errores para la creación de carpetas `.sync` en sistemas de archivos restringidos.
- **Truncado de Nombres**: Solucionado error donde nombres con puntos (ej: `feat.`) se cortaban incorrectamente en la lista de reproducción.

## [1.5.1] - 2025-12-14
### Corregido
- **M3U Glue Bug**: Solucionado error crítico donde los nombres de archivos se pegaban en una sola línea en el archivo M3U. Ahora se fuerza el salto de línea.
- **Optimización SpotDL**: Desactivada la creación de archivos `.sync` innecesarios para búsquedas individuales de YouTube.
- **Barra de Progreso**: Corregido el conteo inicial de canciones para que la barra de progreso funcione correctamente con playlists de YouTube.

## [1.5.0] - 2025-12-14
### Añadido
- **Arquitectura Solo-SpotDL**: Ahora utiliza SpotDL para todas las descargas, asegurando metadatos y nombres de archivo de alta calidad.
- **Soporte de Playlists de YouTube**: Extrae automáticamente los títulos de las playlists de YouTube y los busca/descarga a través de SpotDL.
- **Lógica Híbrida M3U**: Utiliza la generación nativa de M3U de SpotDL para enlaces de Spotify, y un sistema robusto de añadido manual para importaciones de YouTube para evitar sobrescrituras.
- **Logs en Frontend**: Salida de terminal mejorada para mostrar la playlist actual y el estado de extracción.

### Cambiado
- **Eliminada Concurrencia**: Desactivadas las descargas simultáneas para evitar límites de velocidad (Rate Limits) y mejorar la estabilidad.
- **Mejora en Seguridad de Procesos**: La eliminación de procesos ahora se limita al usuario actual para evitar problemas en el sistema.
- **Limpieza de UI**: Eliminada la configuración de concurrencia de la interfaz web.

## [1.4.2] - 2025-12-14
### Corregido
- **Sync:** Corregido bug crítico que impedía el inicio de las descargas (hilos huérfanos).
- **Control:** Restaurado el botón de Stop (endpoint `/stop` ausente).
- **Sanitización**: Corrige transcodificación de acentos (NFD).
- **YT-DLP**: Corregido comando (URL faltante y bitrate automático "0").
- **Robustez (YT)**: Evitado bucle infinito cuando hay vídeos borrados en una playlist (`--ignore-errors`).
- **Estado**: Mejor detección de la canción actual tras recargar la página.
- **Pulido de Logs**: Traducción de "Skipping/Already exists" a "✔ Ya existe", y conteo correcto de errores ("Video unavailable") para que la barra de progreso llegue al 100%.

### Cambiado
- **M3U:** Eliminado prefijo `./` para mayor compatibilidad con reproductores.
- **UI:** Botón de "Reparar" ahora es ámbar para mejor visibilidad.

## [1.4.1] - 2025-12-14
### Changed
- **Renombramiento:** Proyecto renombrado a `PlaylistSyncer`.
- **Idioma:** Localización completa al Español (UI, Logs, README).
- **Concurrencia:** Eliminada la descarga paralela. Ahora las descargas son secuenciales (1 en 1) para mayor estabilidad.
- **UI:** Corrección de alineación en botones de playlist y mejoras de estilo.
- **Historial:** Añadido fecha/hora exacta y contador de canciones descargadas.
- **Audio:** Añadido selector de Bitrate (Auto, 320k, 256k, 192k, 128k).
- **Mantenimiento:** Nueva herramienta "Reparar Archivos" para eliminar IDs/Emojis y corregir M3Us.
- **Log:** Mejora visual de logs con emojis y textos claros en Español.
- **Core:** Estandarización de nombres de archivo `{Artista} - {Titulo}` y limpieza de rutas M3U.
- **CI/CD:** Docker tagging automatizado basado en versión del código.

## [1.3.0] - 2025-12-13
### Added
- **Programación Automática**: Nuevo sistema de ejecución en segundo plano con intervalos configurables (1h, 6h, 12h, 24h).
- **Edición de Playlists**: Ahora es posible editar el nombre y las URLs de una playlist existente sin tener que borrarla.
- **Botón "AÑADIR"**: Mejorada la interfaz de creación de playlists para ser más intuitiva y alineada.

### Fixed
- Corregido error de sintaxis en `app.js` que impedía cargar las pestañas.
- Solucionado problema de visualización en los modales y el listado de tracks.

## [1.2.0] - 2025-12-13
### Added
- **Historial de Trabajos**: Nueva pestaña para ver el registro de ejecuciones pasadas (éxito, items descargados, duración).
- **Interfaz por Pestañas**: Reorganización completa del UI en Dashboard, Playlists, Historial y Ajustes.
- **Sincronización Individual**: Botón para sincronizar una única playlist bajo demanda.
- **Notificaciones Toast**: Reemplazo de `alert()` por notificaciones no intrusivas.

### Changed
- Migración de base de datos a SQLite para mejor persistencia y rendimiento.
- Mejoras visuales generales (CSS Grid, colores, espaciado).

## [v1.1.0] - 2025-12-13
### Added
- **SQLite Database**: Migración desde `playlists.json` a base de datos robusta `soniq.db`.
- **Modular Frontend**: Refactorización completa de `app.js` en módulos (`api.js`, `ui.js`, `ws.js`).
- **Log Parsing Core**: Separación de lógica de parseo de logs (`backend/log_parser.py`) para mayor limpieza.
- **Python Typing**: Añadidos Type Hints en el backend para mejorar la estabilidad.

### Changed
- Refactorización masiva del `DownloaderManager` para usar el nuevo parser y sistema de eventos.
- Actualizada la ruta `/js` en el backend para servir los módulos del frontend.
- Mejorada la gestión de concurrencia y hilos en el backend.

## [1.0.0] - 2025-12-13
### Added
- **Hacker Console**: Real-time log viewer in the web UI.
- **Sync Button**: New synchronization workflow replacing simple download.
- **Playlist Tracking**: Visual indicator for current playlist being processed.
- **Track Counts**: Persistent track count display in playlist list.

### Changed
- **Renamed Project**: From "OpusVault" to **Soniq**.
- **Core Unification**: CLI and Web now share the exact same download logic.
- **UI Improvements**: Better spacing, responsive layout, and refined status states.
- **Log Separation**: Consola Docker (Raw/Debug) vs Frontend (Pretty/Colors).
- **Robustez (YT)**: Evitado falso error al finalizar playlist con vídeos no disponibles (Soft Success).
- **Robustez (SpotDL)**: Detección de éxito mediante log "Saved results" (Soft Success).
- **Sanitización**: Ahora transfiere acentos a ASCII (á->a, ñ->n) para máxima compatibilidad con Navidrome.
- **Estado**: Mejor detección de la canción actual tras recargar la página.
- **UI**: Barra de progreso más visible y animada. Logs con colores reales en la web.
- **UI**: Barra de progreso más visible y animada. Logs con colores reales en la web.
- **Robustez**: Corrección de directorios en primera ejecución (fresh install).

### Security
- Planned: Non-root user execution (Coming in 1.0.1/1.1.0).
