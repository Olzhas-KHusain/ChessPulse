import { useEffect, useState } from 'react';

import { ApiError } from '../services/chesspulseApi';

export type ApiState<T> =
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'success'; data: T };

/**
 * Runs `load` whenever `key` changes, cancelling the previous request (AbortController)
 * so stale responses never overwrite newer ones.
 */
export function useApi<T>(
  key: string | null,
  load: (signal: AbortSignal) => Promise<T>,
): ApiState<T> | null {
  const [state, setState] = useState<ApiState<T> | null>(null);

  useEffect(() => {
    if (key === null) {
      setState(null);
      return undefined;
    }
    const controller = new AbortController();
    setState({ status: 'loading' });
    load(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setState({ status: 'success', data });
      },
      (error: unknown) => {
        if (controller.signal.aborted) return;
        const apiError =
          error instanceof ApiError
            ? error
            : new ApiError(0, 'UNEXPECTED_ERROR', 'Something went wrong.', null);
        setState({ status: 'error', error: apiError });
      },
    );
    return () => controller.abort();
    // `load` is recreated every render; `key` captures every input that matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return state;
}
