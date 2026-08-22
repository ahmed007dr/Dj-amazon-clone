import { readFileSync } from 'node:fs';
import { fileURLToPath, URL } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

/**
 * ⚠️  **No environment file inside `web/`, and none beside it either.**
 *
 *     Configuration comes from `../config/environment.py` — the very same file
 *     Django reads. (ADR-73 · ADR-74)
 *
 *     There used to be a `web/.env` holding `VITE_API_BASE_URL` while `src/.env`
 *     held `CORS_ALLOWED_ORIGINS` and `FRONTEND_BASE_URL`: the same domain
 *     written in four shapes across two files. Switching environment in one and
 *     forgetting the other produces a **silent** failure — the browser blocks
 *     the response and nothing appears in the server log.
 *
 *     That source was `.env.public` until the switch moved into
 *     `config/environment.py`. Parsing Python from a bundler is unusual; reading
 *     a *second* copy of the domain would be worse. The frontend must be built
 *     for the same environment the server runs, and one file is how that is
 *     guaranteed rather than remembered.
 */

/**
 * Reading the shared configuration out of `config/environment.py`.
 *
 * ⚠️  **By explicit name, never by scanning a directory.**
 *
 *     Vite's `loadEnv` would have read `../.env.production` too — the secrets
 *     file: the secret key, the database password and the encryption key for
 *     payment gateway credentials. It only exports prefixed values, true, but
 *     opening the secrets file inside the tool that builds the browser bundle is
 *     risk with no upside: one wrong prefix ships all of it to every visitor.
 *
 * ⚠️  And the file this reads **cannot** hold a secret by construction: it is
 *     committed to Git, which is exactly why the secrets were never put in it.
 */

/** `IS_PRODUCTION = True` — a commented line does not match, `^` sees to that. */
const SWITCH = /^\s*IS_PRODUCTION\s*=\s*(True|False)\b/m;

/** Only `"KEY": "value"` pairs. List values (EXTRA_*) are for Django alone. */
const ENTRY = /^\s*"([A-Z_]+)"\s*:\s*"([^"]*)"/gm;

/**
 * The two blocks, as literal patterns rather than one built from a string.
 *
 * ⚠️  A template literal would eat the escapes: `\s` inside `` `...` `` is not a
 *     whitespace class, it is the letter `s`. The regex then matches nothing and
 *     the build fails with "block not found" while the block is plainly there.
 *
 * ⚠️  `^\}` with the multiline flag — the closing brace of the block sits at
 *     column 0, while the `]` of the nested lists never does. Matching braces
 *     properly would mean writing a parser; anchoring to the layout the file
 *     already has is enough, and it fails loudly rather than quietly if broken.
 */
const BLOCKS = {
  PRODUCTION: /^PRODUCTION\s*=\s*\{([\s\S]*?)^\}/m,
  DEVELOPMENT: /^DEVELOPMENT\s*=\s*\{([\s\S]*?)^\}/m,
};

function readEnvironment(): Record<string, string> {
  const path = fileURLToPath(new URL('../config/environment.py', import.meta.url));

  let source: string;
  try {
    source = readFileSync(path, 'utf8');
  } catch {
    throw new Error('config/environment.py غير موجود — هو مصدر الدومين للطرفين.');
  }

  const flag = SWITCH.exec(source);
  if (!flag) {
    throw new Error('لم يُعثر على IS_PRODUCTION في config/environment.py.');
  }

  const blockName = flag[1] === 'True' ? 'PRODUCTION' : 'DEVELOPMENT';

  const block = BLOCKS[blockName].exec(source);
  if (!block) {
    throw new Error(`لم يُعثر على كتلة ${blockName} في config/environment.py.`);
  }

  const values: Record<string, string> = {};
  ENTRY.lastIndex = 0;
  let entry: RegExpExecArray | null;
  while ((entry = ENTRY.exec(block[1])) !== null) {
    // The `PUBLIC_` prefix is what the rest of this file and Django both speak
    values[`PUBLIC_${entry[1]}`] = entry[2];
  }

  // ⚠️  The real process environment outranks the file — the same precedence
  //     ladder as Django. Containers and deployment platforms set a variable, not a file.
  for (const [key, value] of Object.entries(process.env)) {
    if (key.startsWith('PUBLIC_') && value) {
      values[key] = value;
    }
  }

  return values;
}

const publicEnv = readEnvironment();

function required(name: string): string {
  const value = publicEnv[name];
  if (!value) {
    // ⚠️  Fail loudly at build time rather than falling back to a default.
    //
    //     A silent default produces a deployment that looks successful and then
    //     fails every call for the first user — which is what `shared/http/config.ts`
    //     guards at runtime. The guard here comes one step earlier: before the bundle is built.
    throw new Error(`${name} غير مضبوط — راجع كتلة البيئة في config/environment.py.`);
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

  /**
   * ⚠️  **Assets are referenced under `/static/`, not `/`.**
   *
   *     Django serves this build: `collectstatic` copies `web/dist` into
   *     `STATIC_ROOT` and WhiteNoise serves it at `/static/`. The default base
   *     of `/` would emit `<script src="/assets/app.js">`, and nothing answers
   *     `/assets/` — the page loads white, with no error in the Django log,
   *     because a 404 for a script is not a server fault.
   *
   *     Change this and `STATICFILES_DIRS` together or not at all.
   */
  base: '/static/',

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
