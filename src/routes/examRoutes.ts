/**
 * ============================================================================
 * Submission / Exam API route definitions (located, mirrored in TypeScript)
 * ============================================================================
 * Source of truth (backend, CommonJS):
 *   - backend/app.js                  -> app.use('/api/v1/', submissions)
 *   - backend/routes/submissionRoute.js -> route table below
 *
 * Frontend call site:
 *   - frontend/src/components/ExamWindow.tsx -> handleSubmitExam()
 *       fetch(getApiUrl(`api/v1/submission/${examId}`), { method: 'POST', ... })
 *
 * Fully resolved submission endpoint:
 *   POST /api/v1/submission/:examId
 *   middleware: protect  ->  controller: submitAnswers
 * ============================================================================
 */

import type { Router } from 'express';

/** Handler names resolved from backend/controllers/submissioncontroller.js */
export type SubmissionHandler =
  | 'submitAnswers'
  | 'getSubmission'
  | 'getAllSubmissionsForExam'
  | 'getAllSubmissions'
  | 'getSubmissionDetails';

/** Middleware names resolved from backend/middleware/authMiddleware.js */
export type SubmissionMiddleware = 'protect' | 'adminOnly';

export interface SubmissionRouteDefinition {
  /** Path as registered on the router (mounted under /api/v1 by app.js) */
  path: string;
  /** HTTP method */
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  /** Middleware chain, in execution order */
  middleware: SubmissionMiddleware[];
  /** Controller function that terminates the chain */
  handler: SubmissionHandler;
  /** Fully qualified route once mounted by backend/app.js */
  resolved: string;
}

/** Route table - 1:1 with backend/routes/submissionRoute.js */
export const submissionRoutes: SubmissionRouteDefinition[] = [
  {
    // Student clicks "Submit Exam" in ExamWindow.tsx -> handleSubmitExam()
    path: '/submission/:examId',
    method: 'POST',
    middleware: ['protect'],
    handler: 'submitAnswers',
    resolved: 'POST /api/v1/submission/:examId',
  },
  {
    path: '/submission/:examId',
    method: 'GET',
    middleware: ['protect'],
    handler: 'getSubmission',
    resolved: 'GET /api/v1/submission/:examId',
  },
  {
    path: '/submission/admin/all',
    method: 'GET',
    middleware: ['protect', 'adminOnly'],
    handler: 'getAllSubmissions',
    resolved: 'GET /api/v1/submission/admin/all',
  },
  {
    path: '/submission/admin/:examId',
    method: 'GET',
    middleware: ['protect', 'adminOnly'],
    handler: 'getAllSubmissionsForExam',
    resolved: 'GET /api/v1/submission/admin/:examId',
  },
  {
    path: '/submission/details/:submissionId',
    method: 'GET',
    middleware: ['protect', 'adminOnly'],
    handler: 'getSubmissionDetails',
    resolved: 'GET /api/v1/submission/details/:submissionId',
  },
];

/** The single route used by the "Submit Exam" button in ExamWindow.tsx. */
export const EXAM_SUBMIT_ROUTE: SubmissionRouteDefinition = submissionRoutes[0];

/**
 * Helper mirroring the Express registration found in the backend:
 *   router.route('/submission/:examId').post(protect, submitAnswers);
 */
export function registerSubmissionRoutes(
  router: Router,
  resolve: (name: string) => any
): void {
  for (const route of submissionRoutes) {
    const chain = [...route.middleware.map(resolve), resolve(route.handler)];
    switch (route.method) {
      case 'POST':
        router.route(route.path).post(...chain);
        break;
      case 'GET':
        router.route(route.path).get(...chain);
        break;
      default:
        throw new Error('Unsupported method ' + route.method);
    }
  }
}
