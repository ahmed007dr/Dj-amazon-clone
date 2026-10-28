import { Navigate, useSearchParams } from 'react-router-dom';

/**
 * The old staff URL, forwarded to the users-and-staff page.
 *
 * ⚠️  `/admin/staff` lives on in bookmarks, support notes and browser history, and
 *     `/admin/staff?add=1` was the link the users screen used for "Add staff
 *     member". Both would land on the 404 page if the route were simply removed.
 *     `replace` keeps the dead URL out of the history, so Back does not bounce
 *     through the redirect.
 *
 *     Other query parameters are carried over (`add=1` above); only `tab` is
 *     forced, since the staff screen is what the old URL meant.
 *
 *     It is not behind `RequirePermission`: a redirect shows nothing, and the
 *     destination carries the guard.
 */
export function StaffRedirect() {
  const [params] = useSearchParams();
  const next = new URLSearchParams(params);
  next.set('tab', 'staff');

  return <Navigate replace to={`/admin/users?${next.toString()}`} />;
}
