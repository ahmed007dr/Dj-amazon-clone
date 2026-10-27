import { Navigate, useParams } from 'react-router-dom';

/**
 * The old import URLs, forwarded to the single import page.
 *
 * ⚠️  Bookmarks, links in support notes and the browser history all hold
 *     `/admin/products/import/jobs` and `/admin/products/import/<id>`; breaking them
 *     would land people on the 404 page. `replace` keeps the dead URL out of the
 *     history, so Back does not bounce through the redirect.
 *
 *     They are not behind `RequirePermission`: a redirect shows nothing, and the
 *     destination carries the guard.
 */
const HUB = '/admin/products/import';

export function ImportJobsRedirect() {
  return <Navigate replace to={`${HUB}?tab=jobs`} />;
}

export function ImportJobRedirect() {
  const { id } = useParams<{ id: string }>();

  return <Navigate replace to={`${HUB}?tab=import&job=${encodeURIComponent(id ?? '')}`} />;
}
