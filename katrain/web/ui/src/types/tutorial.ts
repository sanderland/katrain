// ── Response types matching Pydantic models ──────────────────────────────────

export interface TutorialCategory {
  slug: string;
  title: string;
  summary: string;
  order: number;
  book_count: number;
}

export interface TutorialBook {
  id: number;
  category: string;
  subcategory: string;
  title: string;
  author: string | null;
  translator: string | null;
  slug: string;
  chapter_count: number;
}

export interface TutorialChapter {
  id: number;
  book_id: number;
  chapter_number: string;
  title: string;
  order: number;
  section_count: number;
}

export interface TutorialSection {
  id: number;
  chapter_id: number;
  section_number: string;
  title: string;
  order: number;
  figure_count: number;
}

export interface TutorialFigure {
  id: number;
  section_id: number;
  page: number;
  figure_label: string;
  book_text: string | null;
  page_context_text: string | null;
  bbox: { x_min: number; y_min: number; x_max: number; y_max: number } | null;
  page_image_path: string | null;
  board_payload: BoardPayload | null;
  recognition_debug: RecognitionDebug | null;
  narration: string | null;
  audio_asset: string | null;
  video_asset: string | null;
  video_duration_ms: number | null;
  video_size_bytes: number | null;
  order: number;
  updated_at: string | null;
}

export interface TutorialSectionDetail extends TutorialSection {
  figures: TutorialFigure[];
}

export interface TutorialBookDetail extends TutorialBook {
  chapters: TutorialChapter[];
}

// ── Board payload ────────────────────────────────────────────────────────────

export interface BoardPayload {
  size: number;
  stones: { B: [number, number][]; W: [number, number][] };
  labels?: Record<string, string>;       // move numbers: "3,3" → "1"
  letters?: Record<string, string>;      // letter annotations: "5,5" → "A"
  shapes?: Record<string, string>;       // shape markers: "7,7" → "triangle"
  highlights?: [number, number][];
  viewport?: { col: number; row: number; size?: number; cols?: number; rows?: number } | null;
}

// ── Recognition debug types ──────────────────────────────────────────────────

export interface RecognitionDebug {
  human_verified?: boolean;
  verified_at?: string;
  verified_by?: string;
  deskew?: {
    angle: number;
    debug_image?: string;   // grid lines projected onto original (pre-deskew) crop
    grid_image?: string;    // grid lines on deskewed crop
  };
  bbox?: {
    method: string;
    bbox: [number, number, number, number] | null;
    debug_image?: string;
  };
  region?: {
    method: string;
    col_start: number;
    row_start: number;
    confidence?: number;
    evidence?: string[];
    grid_rows?: number;
    grid_cols?: number;
    needs_vllm?: boolean;
  };
  cv_detection?: {
    debug_image?: string;
    spacing?: number;
    total_occupied?: number;
    confident_count?: number;
    ambiguous_count?: number;
  };
  classification?: {
    annotated_crop?: string;
    contact_sheet?: string;
    label_map?: Record<string, [number, number]>;
    confident_cv?: Record<string, string>;
    cv_preclass?: Record<string, string>;
    classifications?: Record<string, string> | null;
    patch_images?: Record<string, string>;
  };
  crop_image?: string;
}

// ── Edit mode types ──────────────────────────────────────────────────────────

export type StoneEditMode = 'black' | 'white' | 'alternate';
export type EditTool = 'stone' | 'letter' | 'shape' | 'eraser' | null;
export type ShapeType = 'triangle' | 'square' | 'circle' | 'cross';
