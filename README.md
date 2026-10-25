# CloudSync para Linux (KDE Plasma & Fedora) ☁️

**CloudSync** es una aplicación gráfica moderna y ligera diseñada para Linux (optimizada para KDE Plasma y Dolphin en Fedora), inspirada en la experiencia de **OneDrive para Windows** y **MEGASync**. 

Permite sincronizar y acceder a tus cuentas de **Google Drive** y **Microsoft OneDrive** con soporte completo para **Archivos a petición (Files On-Demand)** mediante montajes virtuales eficientes con `rclone`.

---

## 🌟 Características Principales

- ☁️ **Archivos a Petición (Files On-Demand):**
  - Explora terabytes de almacenamiento en la nube sin ocupar espacio en tu disco local (0 bytes).
  - Los archivos se descargan transparentemente en caché solo cuando los abres o cuando decides descargarlos explícitamente.

- 🛡️ **Protección de Datos y Liberación Segura de Caché:**
  - Sistema de seguridad que detecta archivos recién modificados o pendientes de subida (*dirty cache*).
  - Al hacer clic en **"Liberar espacio"**, la aplicación jamás interrumpe ni elimina archivos que no hayan completado su subida y confirmación en la nube.

- 🔄 **Transferencia Directa entre Nubes (Cloud-to-Cloud Streaming):**
  - Copia o mueve archivos y carpetas directamente entre diferentes nubes (ej. OneDrive ➔ Google Drive) o entre distintas cuentas de un mismo proveedor.
  - Transferencia en streaming directo por memoria RAM: **0 bytes ocupados en disco local**.
  - Opciones de copia y movimiento seguro (solo elimina del origen tras verificar la integridad en el destino).

- 🐬 **Integración Nativa con Dolphin (KDE Plasma):**
  - Menú contextual de clic derecho completamente integrado:
    - 📥 **Mantener siempre en este equipo (Descargar)**.
    - 🗑️ **Liberar espacio local**.
    - 🔍 **Ver estado de archivos (Nube vs Local)**.
    - 🔄 **Pasar a otra nube (Copiar / Mover sin usar disco)**.
  - Comunicación en tiempo real (IPC vía sockets locales) entre Dolphin y la aplicación gráfica.

- 🔍 **Explorador Visual "Nube vs Local":**
  - Vista interactiva para inspeccionar cualquier carpeta con insignias claras:
    - ☁️ **Solo en la nube** (marcador virtual, 0 B en disco).
    - 💾 **En este equipo** (descargado y disponible offline).
    - ⏳ **Subiendo a la nube** (archivo modificado en sincronización).
  - Buscador en tiempo real, filtros por estado y botones de acción rápida.

- ⚡ **Monitor de Rendimiento en Tiempo Real:**
  - Medición diferenciada de velocidad I/O (`↓ Descarga: X.X MB/s` | `↑ Subida: Y.Y MB/s`).
  - Historial de descargas limpio por sesión.
  - Uso de memoria optimizado y operaciones asíncronas para garantizar una interfaz fluida sin micro-cortes.

- 👤 **Identidad y Multicuenta:**
  - Detección automática del correo electrónico y nombre del propietario para cada cuenta vinculada.
  - Soporte para vincular múltiples cuentas del mismo proveedor de forma independiente.

---

## 📋 Requisitos del Sistema

- **Sistema Operativo:** Fedora Linux 38+ (o cualquier distribución Linux con entorno KDE Plasma 5/6 o compatible con XDG Desktop).
- **Python:** 3.9 o superior.
- **Rclone:** Instalado en el sistema (`sudo dnf install rclone`).
- **Dependencias Python:** `PySide6`.

---

## 🚀 Instalación y Puesta en Marcha

### 1. Clonar el repositorio
```bash
git clone https://github.com/faistreet/CloudSync.git
cd CloudSync
```

### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 3. Instalar integración con el sistema (Lanzador y menú de Dolphin)
Ejecuta el script de instalación incluido para registrar el icono, el acceso directo en el menú de aplicaciones y las acciones de clic derecho en Dolphin:
```bash
chmod +x install.sh
./install.sh
```

### 4. Iniciar la aplicación
Puedes iniciar la aplicación buscándola como **CloudSync** en el menú de aplicaciones de tu entorno o desde la terminal:
```bash
python3 main.py
```

---

## 🖱️ Uso con Dolphin (Clic Derecho)

Dentro de tu carpeta configurada de sincronización (por defecto `~/CloudSync/`):

- **Mantener siempre en este equipo:** Descarga el archivo o carpeta completa a la caché local para trabajar sin conexión a internet.
- **Liberar espacio local:** Elimina los datos locales del archivo liberando espacio en tu disco, manteniendo el archivo visible y accesible desde la nube.
- **Ver estado de archivos (Nube vs Local):** Abre el inspector interactivo para revisar el estado de cada archivo de la carpeta.
- **Pasar a otra nube:** Abre el asistente de transferencia para mover o copiar elementos entre cuentas sin pasar por el disco físico.

---

## ⚙️ Configuración y Seguridad

- Las configuraciones de la aplicación se guardan de forma local en `~/.config/cloudsync/config.json`.
- Los datos de autenticación y tokens OAuth son administrados de manera cifrada y segura a través de `rclone` local (`rclone.conf`).
- No se envían datos de telemetría ni credenciales a ningún servidor externo.

---

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Consulta el archivo `LICENSE` para más detalles.
