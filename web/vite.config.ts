import { readFileSync } from 'node:fs';
import { fileURLToPath, URL } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

/**
 * ⚠️  **No environment file inside `web/`.** Configuration comes from
 *     `../.env.public` — the very same file Django reads. (ADR-73 · ADR-74)
 *
 *     There used to be a `web/.env` holding `VITE_API_BASE_URL` while `src/.env`
 *     held `CORS_ALLOWED_ORIGINS` and `FRONTEND_BASE_URL`: the same domain
 *     written in four shapes across two files. Switching environment in one and
 *     forgetting the other produces a **silent** failure — the browser blocks
 *     the response and nothing appears in the server log.
 */

/**
 * Reading the shared configuration.
 *
 * ⚠️  **By explicit name, never by scanning a directory.**
 *
 *     Vite's `loadEnv` would have read `../.env` too — the secrets file: the
 *     secret key, the database password and the encryption key for payment
 *     gateway credentials. It only exports prefixed values, true, but opening
 *     the secrets file inside the tool that builds the browser bundle is risk
 *     with no upside: one wrong prefix ships all of it to every visitor.
 *
 * ⚠️  And the matcher below accepts `PUBLIC_` alone.
 *
 *     So even if this reader were ever pointed at the wrong file, not one
 *     unprefixed key could escape. The guarantee is structural, not a matter of
 *     staying alert.
 */
const PUBLIC_KEY = /^\s*(?:export\s+)?(PUBLIC_[A-Z0-9_]+)\s*=\s*(.*)$/;

function readPublicEnv(): Record<string, string> {
  const values: Record<string, string> = {};

  // `.env.public.local` is a local developer override — not committed, and outranks the shared file
  for (const name of ['.env.public', '.env.public.local']) {
    let content: string;
    try {
      content = readFileSync(fileURLToPath(new URL(`../${name}`, import.meta.url)), 'utf8');
    } catch {
      continue;
    }

    for (const line of content.split(/\r?\n/)) {
      const match = PUBLIC_KEY.exec(line);
      if (match) {
        values[match[1]] = match[2].trim().replace(/^(['"])(.*)\1$/, '$2');
      }
    }
  }

  // ⚠️  The real process environment outranks both files — the same precedence ladder as Django.
  //     Containers and deployment platforms set a variable, not a file.
  for (const [key, value] of Object.entries(process.env)) {
    if (key.startsWith('PUBLIC_') && value) {
      values[key] = value;
    }
  }

  return values;
}

const publicEnv = readPublicEnv();

function required(name: string): string {
  const value = publicEnv[name];
  if (!value) {
    // ⚠️  Fail loudly at build time rather than falling back to a default.
    //
    //     A silent default produces a deployment that looks successful and then
    //     fails every call for the first user — which is what `shared/http/config.ts`
    //     guards at runtime. The guard here comes one step earlier: before the bundle is built.
    throw new Error(`${name} غير مضبوط. انسخ .env.public.example إلى .env.public واضبطه.`);
  }
  return value;
}

const scheme = publicEnv.PUBLIC_SCHEME ?? 'http';
const apiOrigin = `${scheme}://${required('PUBLIC_API_DOMAIN')}`;
const apiPrefix = (publicEnv.PUBLIC_API_PREFIX ?? '/api/v1').replace(/\/+$/, '');

/** ⚠️  Empty = follows the server. Set explicitly when media moves to a CDN. */
const mediaOrigin = publicEnv.PUBLIC_MEDIA_ORIGIN || apiOrigin;

/**
 * Dev server port — taken from the site domain itself.
 *
 * ⚠️  `5173` used to be written here while `.env` named it again in the CORS
 *     origins. A port changed in one and not the other makes the browser block
 *     every call. Production has no port in the domain, so the default stays for development.
 */
const sitePort = Number(publicEnv.PUBLIC_SITE_DOMAIN?.split(':')[1] ?? 5173);

export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },

  /**
   * ⚠️  Injection here is an **allowlist written out by name**, not automatic pass-through.
   *
   *     Anything not named in these lines never reaches the browser, whatever
   *     the file contains. And `shared/http/config.ts` remains their only
   *     consumer — not a line of it changed, and the ESLint rule confining
   *     `import.meta` to it still stands.
   */
  define: {
    'import.meta.env.VITE_API_BASE_URL': JSON.stringify(`${apiOrigin}${apiPrefix}`),
    'import.meta.env.VITE_MEDIA_BASE_URL': JSON.stringify(mediaOrigin),
    'import.meta.env.VITE_DEFAULT_LOCALE': JSON.stringify(
      publicEnv.PUBLIC_DEFAULT_LOCALE ?? 'ar',
    ),
  },

  server: {
    port: sitePort,
    // ⚠️  No proxy for the API.
    //
    //     A proxy makes development work off a relative path while production needs
    //     a full address — so the difference between the two environments first
    //     shows up after deployment. The address comes from the shared configuration in both cases.
  },

  build: {
    // ⚠️  Code splitting at the portal level.
    //
    //     A customer browsing the store does not download the admin screens or the
    //     point of sale. A single bundle makes a visitor on a weak connection wait
    //     for code they will never see.
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          query: ['@tanstack/react-query'],
          i18n: ['i18next', 'react-i18next'],
        },
      },
    },
  },
});
