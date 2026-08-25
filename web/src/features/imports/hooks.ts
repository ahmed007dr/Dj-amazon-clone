import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';

import { saveFile } from '@/shared/http';

import * as api from './api';
import type { ImportJob } from './api';

const KEY = ['admin', 'imports'] as const;

export function useImportSpec() {
  return useQuery({
    queryKey: ['imports', 'spec'],
    queryFn: api.getImportSpec,
    // The column guide changes with a deployment, not within a session
    staleTime: 30 * 60 * 1000,
  });
}

export function useImportJobs(params: { page?: number; status?: string }) {
  return useQuery({
    queryKey: [...KEY, params],
    queryFn: () => api.listImportJobs(params),
    staleTime: 10 * 1000,
  });
}

export function useImportJob(id: string | undefined) {
  return useQuery({
    queryKey: [...KEY, 'detail', id],
    queryFn: () => api.getImportJob(id as string),
    enabled: Boolean(id),
  });
}

export function useImportErrors(id: string | undefined, page: number) {
  return useQuery({
    queryKey: [...KEY, 'errors', id, page],
    queryFn: () => api.listImportErrors(id as string, { page }),
    enabled: Boolean(id),
  });
}

export function useUploadImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.uploadImport,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: KEY }),
  });
}

export function usePublishImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.publishImport(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: KEY }),
  });
}

export function useCancelImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      api.cancelImport(id, reason ?? ''),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: KEY }),
  });
}

/**
 * The chunk loop — the browser is the runner.
 *
 * ⚠️  **Sequential, never concurrent.** Each call to `advance` moves the job's
 *     cursor; two in flight at once process the same chunk twice and the counts
 *     stop meaning anything. `busy` is a ref rather than state because state
 *     updates are batched and a second tick can read a stale `false`.
 *
 * ⚠️  **`is_running`, not `!is_terminal`.** `VALIDATED` is a job waiting for a
 *     human to press execute; looping on it calls `advance` forever on a job
 *     that owes no work.
 *
 * ⚠️  **Stopping is not cancelling.** Closing the tab or pressing stop leaves the
 *     job exactly where it is — every chunk is committed — and `run_periodic`
 *     finishes it server-side. Cancel is a separate, explicit decision.
 */
export function useImportRunner(job: ImportJob | undefined) {
  const queryClient = useQueryClient();
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const busy = useRef(false);
  // ⚠️  Read inside the interval so a stop takes effect on the current tick
  //     rather than after the next chunk has already been requested.
  const wanted = useRef(false);

  const id = job?.id;
  const isRunning = job?.is_running ?? false;

  const stop = useCallback(() => {
    wanted.current = false;
    setRunning(false);
  }, []);

  const start = useCallback(() => {
    setError(null);
    wanted.current = true;
    setRunning(true);
  }, []);

  useEffect(() => {
    if (!running || !id) return undefined;

    let cancelled = false;

    const tick = async () => {
      if (busy.current || !wanted.current) return;
      busy.current = true;

      try {
        const next = await api.advanceImport(id);
        if (cancelled) return;

        queryClient.setQueryData([...KEY, 'detail', id], next);

        if (!next.is_running) {
          wanted.current = false;
          setRunning(false);
          void queryClient.invalidateQueries({ queryKey: KEY });
        }
      } catch (cause) {
        if (cancelled) return;
        // ⚠️  A failed chunk stops the loop instead of hammering the endpoint.
        //     The job keeps its cursor, so resuming continues rather than restarts.
        wanted.current = false;
        setRunning(false);
        setError(cause);
      } finally {
        busy.current = false;
      }
    };

    void tick();
    const timer = window.setInterval(() => void tick(), 400);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [running, id, queryClient]);

  // A job already in flight when the page opens — resume without a second press
  useEffect(() => {
    if (isRunning && !running && !error) {
      start();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRunning]);

  return { running, error, start, stop };
}

/**
 * Starting a phase, then letting the runner carry it.
 *
 * ⚠️  `validate` and `execute` only move the job into a running state; they do
 *     no work themselves. Treating their response as the finished job is how a
 *     dry run reports "0 rows" a moment after it was asked to check ten thousand.
 */
export function useStartPhase() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, phase }: { id: string; phase: 'validate' | 'execute' }) =>
      phase === 'validate' ? api.validateImport(id) : api.executeImport(id),
    onSuccess: (job) => {
      queryClient.setQueryData([...KEY, 'detail', job.id], job);
      void queryClient.invalidateQueries({ queryKey: KEY });
    },
  });
}

export function useDownloadTemplate() {
  return useMutation({
    mutationFn: api.downloadTemplate,
    onSuccess: saveFile,
  });
}

export function useDownloadErrorFile() {
  return useMutation({
    mutationFn: (id: string) => api.downloadErrorFile(id),
    onSuccess: saveFile,
  });
}
