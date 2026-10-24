# CloudSync para Linux Fedora (KDE Plasma) ☁️

**CloudSync** es una aplicación gráfica moderna inspirada en **MEGASync** y **OneDrive para Windows**, diseñada específicamente para Linux Fedora con KDE Plasma. Permite sincronizar y acceder a tus cuentas de **Google Drive** y **Microsoft OneDrive** con soporte completo para **Archivos a petición (Files On-Demand)**.

---

## 🌟 Nuevas Características y Mejoras Implementadas

1. **Identidad de Cuentas (Correo Electrónico Visible):**
   - Muestra el correo electrónico asociado a cada cuenta sincronizada (ej. `santiagoecg@outlook.com` o tu cuenta de `@gmail.com`) directamente en las tarjetas de la aplicación.
2. **Historial de Descargas de Sesión (Limpio y Temporal):**
   - Cada vez que usas **"Mantener siempre en este equipo"**, la aplicación muestra en tiempo real la descarga activa (progreso en porcentaje y velocidad en MB/s).
   - Al terminar, se registra en el **Historial de esta sesión**.
   - **Reinicio automático:** Al cerrar y volver a abrir la aplicación, este historial se reinicia para no saturar la pantalla con información antigua.
3. **Explorador Visual "Nube vs Local":**
   - Una ventana interactiva que lista tus carpetas y archivos con insignias visuales claras:
     - ☁️ **"Solo en la nube"** (ocupa 0 bytes en tu disco).
     - 💾 **"En este equipo"** (archivo descargado y disponible sin conexión).
   - Incluye buscador rápido por nombre, filtros y botones directos para *Descargar* o *Liberar espacio*.
   - Accesible desde la aplicación o con **clic derecho en Dolphin -> CloudSync -> Ver estado de archivos (Nube vs Local)**.
4. **Icono Colorido y Moderno (Ya no es solo blanco):**
   - Rediseño con degradado azul celeste y zafiro, con insignias vibrantes en verde esmeralda (al día), cian (sincronizando) y ámbar (pausado) que resaltan tanto en paneles oscuros como claros.
5. **Monitor de Velocidad I/O Independiente:**
   - Visualización diferenciada en tiempo real de:
     - `↓ Descarga: X.X MB/s`
     - `↑ Subida: Y.Y MB/s`
6. **Comunicación en Tiempo Real entre Dolphin y la Interfaz (IPC):**
   - Las descargas ordenadas desde Dolphin se comunican instantáneamente por socket local con la aplicación abierta para mostrar las barras de progreso y la velocidad en vivo.

---

## 🚀 Inicio Rápido

Para iniciar la aplicación:
```bash
python3 /run/media/santiagoecg/DATOS/PROGRAMACION/PROYECTOS/GDRIVE/main.py
```
*(O búscala en el menú de aplicaciones de Fedora como **CloudSync**)*.

---

## 🖱️ Uso con Dolphin (Clic Derecho)

Haz clic derecho en cualquier archivo o carpeta dentro de `/run/media/santiagoecg/DATOS/CloudSync/`:
- 📥 **Mantener siempre en este equipo (Descargar):** Descarga el archivo para uso offline.
- 🗑️ **Liberar espacio local:** Libera espacio conservando el acceso directo en la nube.
- 🔍 **Ver estado de archivos (Nube vs Local):** Abre el explorador interactivo en esa carpeta.
