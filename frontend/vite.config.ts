import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'pwa-192.png', 'pwa-512.png'],
      manifest: {
        name: 'Aristeus Kochapp',
        short_name: 'Aristeus',
        description: 'Wochenplanung aus regionalen Angeboten',
        theme_color: '#F6F1E7',
        background_color: '#F6F1E7',
        display: 'standalone',
        start_url: '/',
        lang: 'de',
        icons: [
          { src: '/pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/pwa-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        runtimeCaching: [
          {
            // Cache individual plan detail (shopping list offline)
            urlPattern: /^\/api\/plans\/\d+$/,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'api-plan-detail',
              expiration: { maxEntries: 10, maxAgeSeconds: 7 * 24 * 60 * 60 },
            },
          },
          {
            // Cache plan list
            urlPattern: /^\/api\/plans$/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-plans-list',
              networkTimeoutSeconds: 5,
              expiration: { maxEntries: 1, maxAgeSeconds: 24 * 60 * 60 },
            },
          },
        ],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
