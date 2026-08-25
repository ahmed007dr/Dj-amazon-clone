import { useCallback, useEffect, useRef, useState } from 'react';

import {
  advanceImport,
  cancelImport,
  startExecution,
  startValidation,
  type ImportJob,
} from './adminApi';

/**
 * The chunk loop.
 *
 * ⚠️  **A ref, not state, decides whether to keep going.**
 *
 *     The loop is an async recursion, and reading `job.is_running` from state
 *     inside it reads the value captured when the closure was created — which
 *     is always the previous chunk's. The loop either stops one chunk early or
 *     never stops at all, and both look like a hung import.
 *
 * ⚠️  And the loop **stops itself when the component unmounts.**
 *
 *     Without it, navigating away leaves requests firing against a job nobody
 *     is watching, each one calling `setJob` on a dead component. The work
 *     itself is not lost — the server wrote every chunk down, and
 *     `run_periodic` finishes what the tab abandoned.
 */
export type RunnerPhase = 'idle' | 'validating' | 'executing';

export function useImportRunner(initial: ImportJob | null) {
  const [job, setJob] = useState<ImportJob | null>(initial);
  const [phase, setPhase] = useState<RunnerPhase>('idle');
  const [error, setError] = useState<unknown>(null);

  const running = useRef(false);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      running.current = false;
    };
  }, []);

  const loop = useCallback(async (id: string) => {
    running.current = true;
    try {
      for (;;) {
        if (!alive.current || !running.current) return;

        const next = await advanceImport(id);
        if (!alive.current) return;

        setJob(next);
        if (!next.is_running) return;

        // ⚠️  A breath between chunks, not a throttle.
        //
        //     Back-to-back requests from one tab pin a server worker on a
        //     shared host for the whole import, and every other page the admin
        //     has open waits behind it. Twenty-five milliseconds is invisible
        //     to the progress bar and leaves the queue moving.
        await new Promise((resolve) => setTimeout(resolve, 25));
      }
    } catch (cause) {
      if (alive.current) setError(cause);
    } finally {
      running.current = false;
      if (alive.current) setPhase('idle');
    }
  }, []);

  const validate = useCallback(
    async (id: string) => {
      setError(null);
      setPhase('validating');
      try {
        setJob(await startValidation(id));
        await loop(id);
      } catch (cause) {
        setError(cause);
        setPhase('idle');
      }
    },
    [loop],
  );

  const execute = useCallback(
    async (id: string) => {
      setError(null);
      setPhase('executing');
      try {
        setJob(await startExecution(id));
        await loop(id);
      } catch (cause) {
        setError(cause);
        setPhase('idle');
      }
    },
    [loop],
  );

  const stop = useCallback(async (id: string) => {
    // ⚠️  The local loop is stopped **first**, then the server is told.
    //
    //     The other order leaves one more chunk in flight after the cancel
    //     lands, and it writes rows into a job the admin was told had stopped.
    running.current = false;
    setJob(await cancelImport(id));
    setPhase('idle');
  }, []);

  return { job, setJob, phase, error, validate, execute, stop, isBusy: phase !== 'idle' };
}
