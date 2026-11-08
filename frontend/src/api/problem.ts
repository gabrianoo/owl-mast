/**
 * Common error envelope (OM-01.04 contract): RFC 9457 problem details (`application/problem+json`)
 * as produced by the backend. Only the status and a safe title are consumed; `detail` is never
 * rendered, so connector or stack internals cannot reach the page.
 */
export interface ProblemDetail {
  status: number;
  title: string;
  type?: string;
}

export const PROBLEM_MEDIA_TYPE = 'application/problem+json';

export function parseProblem(body: unknown, fallbackStatus: number): ProblemDetail {
  if (typeof body === 'object' && body !== null) {
    const record = body as Record<string, unknown>;
    const status = typeof record.status === 'number' ? record.status : fallbackStatus;
    const title = typeof record.title === 'string' && record.title.length <= 200 ? record.title : 'Request failed';
    const type = typeof record.type === 'string' ? record.type : undefined;
    return type === undefined ? { status, title } : { status, title, type };
  }
  return { status: fallbackStatus, title: 'Request failed' };
}
