import { defineConfig } from 'vite'

// Configuración mínima
export default defineConfig({
  server: {
    host: true,        // Escuchar en todas las interfaces (evita casos donde localhost resuelve solo a IPv6 ::1)
    port: 5173,        // Puerto por defecto
    open: true,        // Abre el navegador automáticamente
    // En desarrollo, el frontend (5173) proxya API/WS al backend (8001)
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8001',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',    // Carpeta de salida para producción
    sourcemap: true,   // Útil para debuggear errores en producción
  }
})
