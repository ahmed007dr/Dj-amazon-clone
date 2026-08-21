import { useCallback } from 'react';

import { useAuth } from './useAuth';

/**
 * "Does the user hold this?"
 *
 * ⚠️  **For display, not for guarding.**
 *
 *     The server refuses regardless of what the screen shows. Hiding a button
 *     is not security — but showing a button that fails when pressed is a bad
 *     experience, and showing fifteen links the user does not hold makes them
 *     think the system is broken.
 *
 * ⚠️  And **the owner always holds everything**.
 *
 *     `is_owner` makes their permission list unnecessary. And without this
 *     exception the system locks its own owner out at the first wrong configuration.
 *
 * ⚠️  And absence means **no**, not "maybe".
 *
 *     Before `/auth/me` arrives the list is empty; showing everything until it
 *     does makes the links flicker on every startup.
 */
export function useCan(): (permission?: string | null) => boolean {
  const { user } = useAuth();

  return useCallback(
    (permission) => {
      if (user === null) return false;
      if (user.is_owner) return true;

      // ⚠️  `null` = no condition: a screen anyone who reaches it may open.
      if (permission === undefined || permission === null) return true;

      return (user.permissions ?? []).includes(permission);
    },
    [user],
  );
}

/**
 * The structural conditions — these are not Django permissions.
 *
 * ⚠️  Some gates on the server ask "do they have a profile?" rather than "do
 *     they hold this?": point of sale asks about the account type, and the
 *     staff portal about an active employee profile. Mixing them with
 *     permissions made the hiding contradict the server in both directions.
 */
export function useIs(): (requirement: 'owner' | 'admin' | 'employee') => boolean {
  const { user } = useAuth();

  return useCallback(
    (requirement) => {
      if (user === null) return false;

      switch (requirement) {
        case 'owner':
          return user.is_owner;
        case 'admin':
          return user.has_admin_profile || user.is_owner;
        case 'employee':
          return user.has_employee_profile || user.is_owner;
        default:
          return false;
      }
    },
    [user],
  );
}
