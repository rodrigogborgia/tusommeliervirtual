import { defineConfig } from 'vite'

// Configuración mínima
export default defineConfig({
  server: {
    port: 5173,        // Puerto por defecto
    open: true,        // Abre el navegador automáticamente
  },
  build: {
    outDir: 'dist',    // Carpeta de salida para producción
    sourcemap: true,   // Útil para debuggear errores en producción
  }
})
