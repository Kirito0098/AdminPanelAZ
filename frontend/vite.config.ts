import { fileURLToPath, URL } from 'node:url'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

function tgMiniMoveScriptToBody(): Plugin {
  return {
    name: 'tg-mini-move-script-to-body',
    apply: 'build',
    enforce: 'post',
    transformIndexHtml: {
      order: 'post',
      handler(html, ctx) {
        if (!ctx.filename?.includes('tg-mini')) return html
        const scriptRe =
          /<script[^>]*src="\/api\/tg-mini\/assets\/[^"]+\.js"[^>]*><\/script>\s*/i
        const match = html.match(scriptRe)
        if (!match) return html
        const script = match[0].trim()
        return html.replace(scriptRe, '').replace('</body>', `    ${script}\n  </body>`)
      },
    },
  }
}

export default defineConfig(({ mode }) => {
  const isTgMini = mode === 'tg-mini'

  return {
    plugins: [react(), ...(isTgMini ? [tgMiniMoveScriptToBody()] : [])],
    base: isTgMini ? '/api/tg-mini/' : '/',
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    build: {
      outDir: isTgMini ? '../backend/app/static/tg_mini' : 'dist',
      emptyOutDir: true,
      cssCodeSplit: !isTgMini,
      modulePreload: !isTgMini,
      rollupOptions: {
        input: isTgMini ? 'tg-mini.html' : 'index.html',
        ...(isTgMini
          ? {
              output: {
                format: 'iife',
                inlineDynamicImports: true,
                entryFileNames: 'assets/tg-mini-[hash].js',
                assetFileNames: 'assets/tg-mini-[hash][extname]',
              },
            }
          : {}),
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
