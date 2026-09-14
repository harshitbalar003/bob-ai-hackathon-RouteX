/**
 * Adapter index — reads VITE_DATA_SOURCE and re-exports the correct
 * implementation. Components import from here, never from mock.ts or api.ts.
 */
import { mockAdapter } from './mock';
import { apiAdapter } from './api';
import type { DataAdapter } from './types';

const source = import.meta.env.VITE_DATA_SOURCE ?? 'mock';

export const adapter: DataAdapter = source === 'api' ? apiAdapter : mockAdapter;
