import { fileURLToPath, URL } from 'node:url'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

const CSP_NONCE_PLACEHOLDER = '%CSP_NONCE%'

function cspNoncePlaceholder(): Plugin {
  const injectNonce = (html: string) =>
    html
      .replace(
        /(<meta\b[^>]*\bname=["']csp-nonce["'][^>]*\bcontent=["'])([^"']*)(["'])/i,
        `$1${CSP_NONCE_PLACEHOLDER}$3`,
      )
      .replace(
        /(<script\b(?![^>]*\bnonce=)(?![^>]*\bsrc=["']https?:\/\/)[^>]*)(>)/gi,
        `$1 nonce="${CSP_NONCE_PLACEHOLDER}"$2`,
      )
      .replace(
        /(<link\b[^>]*\brel=["']modulepreload["'][^>]*)(>)/gi,
        `$1 nonce="${CSP_NONCE_PLACEHOLDER}"$2`,
      )

  return {
    name: 'csp-nonce-placeholder-pre',
    apply: 'build',
    transformIndexHtml: {
      order: 'pre',
      handler: injectNonce,
    },
  }
}

function cspNoncePlaceholderPost(): Plugin {
  const injectNonce = (html: string) =>
    html
      .replace(
        /(<script\b(?![^>]*\bnonce=)(?![^>]*\bsrc=["']https?:\/\/)[^>]*)(>)/gi,
        `$1 nonce="${CSP_NONCE_PLACEHOLDER}"$2`,
      )
      .replace(
        /(<link\b[^>]*\brel=["']modulepreload["'][^>]*)(>)/gi,
        `$1 nonce="${CSP_NONCE_PLACEHOLDER}"$2`,
      )

  return {
    name: 'csp-nonce-placeholder-post',
    apply: 'build',
    transformIndexHtml: {
      order: 'post',
      handler: injectNonce,
    },
  }
}

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
    plugins: [react(), cspNoncePlaceholder(), cspNoncePlaceholderPost(), ...(isTgMini ? [tgMiniMoveScriptToBody()] : [])],
    base: isTgMini ? '/api/tg-mini/' : '/',
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    build: {
      target: 'es2022',
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
