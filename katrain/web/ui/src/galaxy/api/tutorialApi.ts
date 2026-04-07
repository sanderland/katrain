import type {
  TutorialCategory,
  TutorialBook,
  TutorialBookDetail,
  TutorialSection,
  TutorialSectionDetail,
  TutorialFigure,
  BoardPayload,
} from '../../types/tutorial';

const BASE = '/api/v1/tutorials';

async function apiGet<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`);
  if (!resp.ok) throw new Error(`Tutorial API ${resp.status}: ${await resp.text()}`);
  return resp.json() as Promise<T>;
}

async function apiPut<T>(path: string, body: unknown, token?: string): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const resp = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers,
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`Tutorial API ${resp.status}: ${await resp.text()}`);
  return resp.json() as Promise<T>;
}

export const TutorialAPI = {
  // Categories
  getCategories: (): Promise<TutorialCategory[]> => apiGet('/categories'),

  // Books
  getBooks: (category: string): Promise<TutorialBook[]> =>
    apiGet(`/categories/${encodeURIComponent(category)}/books`),
  getBook: (bookId: number): Promise<TutorialBookDetail> => apiGet(`/books/${bookId}`),

  // Sections
  getSections: (chapterId: number): Promise<TutorialSection[]> =>
    apiGet(`/chapters/${chapterId}/sections`),
  getSection: (sectionId: number): Promise<TutorialSectionDetail> =>
    apiGet(`/sections/${sectionId}`),

  // Figures
  getFigure: (figureId: number): Promise<TutorialFigure> => apiGet(`/figures/${figureId}`),
  saveBoardPayload: (figureId: number, payload: BoardPayload, token?: string, expectedUpdatedAt?: string): Promise<TutorialFigure> =>
    apiPut(`/figures/${figureId}/board`, {
      board_payload: payload,
      expected_updated_at: expectedUpdatedAt ?? null,
    }, token),

  // Narration
  saveNarration: (figureId: number, narration: string, audioAsset?: string | null, token?: string): Promise<TutorialFigure> =>
    apiPut(`/figures/${figureId}/narration`, {
      narration,
      audio_asset: audioAsset ?? null,
    }, token),

  // Verify
  verifyFigure: (figureId: number, token?: string): Promise<TutorialFigure> =>
    apiPut(`/figures/${figureId}/verify`, {}, token),

  // Assets
  assetUrl: (relativePath: string): string => `${BASE}/assets/${relativePath}`,
};
