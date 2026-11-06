import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  base: './',
  server: {
    port: 5173,
    strictPort: true,
    // 截图脚本/编辑器会在项目内产生临时目录，忽略它们避免 chokidar 触发 EBUSY 直接杀掉 dev server
    watch: {
      ignored: [
        '**/shots/**',
        '**/dist/**',
        '**/dist_electron/**',
        '**/.index.html.*.tmpdir/**',
        '**/*.tmp'
      ]
    }
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        index: './index.html',
        setup: './setup.html',
        pet: './pet/pet.html'
      }
    }
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')
    }
  }
})
