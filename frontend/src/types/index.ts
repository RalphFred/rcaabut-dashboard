export type Role = "super_admin" | "library_staff";

export type User = {
  id: number;
  full_name: string;
  email: string;
  role: Role;
  is_active: boolean;
};

export type Course = {
  id: number;
  course_code: string;
  course_title: string;
  college?: string | null;
  department?: string | null;
  programme?: string | null;
  level?: string | null;
  semester?: string | null;
  session?: string | null;
  lecturers: string[];
  description?: string | null;
  status: string;
  created_at: string;
  updated_at?: string;
};

export type Topic = {
  id: number;
  module_number?: number | null;
  module_title?: string | null;
  week_number?: number | null;
  topic_title: string;
  subtopics: string[];
  outcomes: string[];
  extraction_confidence: number;
  is_searchable: boolean;
};

export type CandidateResource = {
  id: number;
  course_id: number;
  topic_id: number;
  category: string;
  title: string;
  authors: string[];
  year?: number | null;
  abstract?: string | null;
  url?: string | null;
  source_system: string;
  relevance_score: number;
  match_reason?: string | null;
  status: string;
};

export type ApprovedResource = {
  id: number;
  course_id: number;
  topic_id: number;
  candidate_id?: number | null;
  category: string;
  title: string;
  authors: string[];
  year?: number | null;
  url?: string | null;
  source_system: string;
  note?: string | null;
  created_at: string;
};

export type Job = {
  id: number;
  course_id?: number | null;
  compact_id?: number | null;
  job_type: string;
  status: string;
  progress: number;
  message?: string | null;
  error_message?: string | null;
};

export type ActivityLog = {
  id: number;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: number;
  created_at: string;
};

export type ExportHistory = {
  id: number;
  course_id: number;
  course: string;
  export_type: string;
  created_by: string;
  created_at: string;
};

export type EvaluationReport = {
  summary: {
    courses: number;
    topics_extracted: number;
    searchable_topics: number;
    candidate_resources: number;
    approved_resources: number;
    approval_rate: number;
    average_candidates_per_searchable_topic: number;
    average_extraction_confidence: number;
    average_completed_job_seconds: number;
  };
  source_breakdown: Record<string, number>;
  category_breakdown: Record<string, number>;
  candidate_status_breakdown: Record<string, number>;
};

export type SourceConfig = {
  id: number;
  source_key: string;
  display_name: string;
  source_type: string;
  base_url?: string | null;
  is_enabled: boolean;
  notes?: string | null;
  created_at: string;
};
