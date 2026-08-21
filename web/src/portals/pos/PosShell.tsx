import { Outlet } from 'react-router-dom';

import { useMySession } from '@/features/pos/hooks';
import { Spinner } from '@/shared/ui/Spinner';

import { PosHeader } from './components/PosHeader';
import { SessionGate } from './components/SessionGate';

import './PosShell.css';

/**
 * The point-of-sale shell.
 *
 * ⚠️  **The shift is an entry condition, not a step inside the screen.**
 *
 *     Every endpoint on the server refuses to work with no open shift (409).
 *     Letting the sale screen open with no shift means the cashier builds a
 *     whole sale in front of the customer and is then refused on the last press
 *     — so a barrier is built here instead of translating a late refusal.
 *
 * ⚠️  And no footer.
 *
 *     A footer is marketing links and company information; it has no place on a
 *     counter terminal, and it eats height the item list needs.
 */
export function PosShell() {
  const session = useMySession();

  return (
    <div className="pos-shell">
      <PosHeader session={session.data ?? null} />

      <main className="pos-shell__body">
        {session.isPending ? (
          <Spinner />
        ) : session.data ? (
          <Outlet />
        ) : (
          <SessionGate />
        )}
      </main>
    </div>
  );
}
