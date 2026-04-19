import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

function stableChunkBucket(prefix: string, name: string, bucketCount: number) {
  let hash = 0
  for (const char of name) {
    hash += char.charCodeAt(0)
  }
  return `${prefix}-${hash % bucketCount}`
}

// https://vite.dev/config/
export default defineConfig({
  optimizeDeps: {
    entries: ['index.html', 'src/**/*.{ts,vue}'],
    include: [
      'vue',
      'vue-router',
      'pinia',
      'axios',
      'element-plus',
      '@element-plus/icons-vue',
      '@vue-flow/core',
      '@vue-flow/background',
      '@vue-flow/controls',
      '@vue-flow/minimap',
      '@vueuse/core',
      'echarts',
      'd3',
      'd3-force',
      'xterm',
      '@xterm/addon-fit',
      '@xterm/addon-web-links',
    ],
  },
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return undefined
          }

          if (id.includes('zrender')) {
            return 'vendor-zrender'
          }

          if (id.includes('echarts')) {
            if (id.includes('/charts/')) {
              return 'vendor-echarts-charts'
            }

            if (id.includes('/components/')) {
              return 'vendor-echarts-components'
            }

            if (id.includes('/renderers/')) {
              return 'vendor-echarts-renderers'
            }

            if (id.includes('/core/')) {
              return 'vendor-echarts-runtime'
            }

            return 'vendor-echarts-core'
          }

          if (id.includes('@vue-flow')) {
            return 'vendor-vue-flow'
          }

          if (id.includes('@element-plus/icons-vue')) {
            return 'vendor-element-plus-icons'
          }

          if (id.includes('element-plus')) {
            const componentMatch = id.match(/element-plus\/(?:es|lib)\/components\/([^/]+)/)
            const componentName = componentMatch?.[1] ?? 'core'
            return stableChunkBucket('vendor-element-plus', componentName, 6)
          }

          if (id.includes('d3')) {
            return 'vendor-d3'
          }

          if (id.includes('xterm')) {
            return 'vendor-xterm'
          }

          if (id.includes('vue') || id.includes('pinia') || id.includes('vue-router')) {
            return 'vendor-vue'
          }

          return 'vendor-misc'
        },
      },
    },
  },
  plugins: [
    vue(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
      imports: ['vue', 'vue-router', 'pinia'],
      dts: 'src/auto-imports.d.ts',
    }),
    Components({
      dts: 'src/components.d.ts',
    }),
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${process.env.VITE_API_PORT || 8000}`,
        rewrite: (path) => path.replace(/^\/api/, ''),
        changeOrigin: true,
      },
      '/ws': {
        target: `ws://127.0.0.1:${process.env.VITE_API_PORT || 8000}`,
        ws: true,
      },
    },
  },
})
