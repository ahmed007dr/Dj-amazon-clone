import { lazy, Suspense } from 'react';
import { useLocation } from 'react-router-dom';

import { GUIDE_ROOT } from '@/portals/admin/docs/paths';

/**
 * The "about this page" link in the header.
 *
 * ⚠️  **The guide's text is loaded lazily, here and nowhere in the shell.**
 *
 *     Finding "which topic explains this screen?" needs every topic's `path`, which
 *     lives in the same module as all the guide's prose. Importing it statically
 *     would put that whole text into the admin shell — downloaded by every admin on
 *     every visit, before they have asked for any help. As a lazy chunk it arrives
 *     after the screen has rendered, and the link simply appears when it is ready
 *     (or never, when nothing documents this screen).
 */
const ResolvedLink = lazy(() =>
  import('./DocsHelpLinkResolved').then((module) => ({ default: module.DocsHelpLinkResolved })),
);

export function DocsHelpLink() {
  const { pathname } = useLocation();

  // On the guide itself the link would point at where you already are — and skipping the
  // render also skips downloading the chunk twice.
  if (pathname === GUIDE_ROOT || pathname.startsWith(`${GUIDE_ROOT}/`)) return null;

  return (
    <Suspense fallback={null}>
      <ResolvedLink />
    </Suspense>
  );
}
