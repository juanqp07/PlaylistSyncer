Changelog

All notable changes to this project will be documented in this file.

## [1.4.1] - 2025-12-14
### Changed
- **Renombramiento:** Proyecto renombrado a `PlaylistSyncer`.
- **Idioma:** Localización completa al Español (UI, Logs, README).
- **Concurrencia:** Eliminada la descarga paralela. Ahora las descargas son secuenciales (1 en 1) para mayor estabilidad.
- **UI:** Corrección de alineación en botones de playlist y mejoras de estilo.
- **Historial:** Añadido fecha/hora exacta y contador de canciones descargadas.
- **Audio:** Añadido selector de Bitrate (Auto, 320k, 256k, 192k, 128k).
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
- **Log Aesthetics**: Deduplicated rate limit warnings and improved log coloring.

### Security
- Planned: Non-root user execution (Coming in 1.0.1/1.1.0).
