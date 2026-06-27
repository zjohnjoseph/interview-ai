// TypeScript mirrors of the backend Pydantic schemas (app/models/schemas.py).
// Nullable fields match the backend exactly (Optional[...] -> | null).

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  name: string;
  role: string;
  created_at: string;
}

export interface InterviewResponse {
  id: string;
  job_title: string;
  job_description: string;
  required_skills: string;
  role_level: string;
  max_questions: number;
  status: string; // "draft" | "active" | "archived"
  created_at: string;
}

export interface SessionResponse {
  id: string;
  interview_id: string;
  token: string;
  candidate_name: string | null;
  candidate_email: string | null;
  status: string; // "pending" | "active" | "completed"
  started_at: string | null;
  completed_at: string | null;
  expires_at: string;
}

export interface QuestionData {
  id: string;
  text: string;
  domain: string;
  difficulty: string;
  created_at: string;
}

export interface NextQuestionResponse {
  completed: boolean;
  question: QuestionData | null;
  questions_remaining: number;
}

export interface EvaluationData {
  score: number;
  accuracy: number;
  completeness: number;
  clarity: number;
  feedback: string;
}

export interface AnswerResponse {
  response_id: string;
  question_text: string;
  evaluation: EvaluationData;
  is_last_question: boolean;
}

export interface ResponseDetail {
  id: string;
  question_text: string;
  is_follow_up: boolean;
  answer_text: string;
  score: number | null;
  accuracy: number | null;
  completeness: number | null;
  clarity: number | null;
  feedback: string | null;
  latency_ms: number | null;
  created_at: string;
}

export interface SessionResultResponse {
  session_id: string;
  candidate_name: string | null;
  candidate_email: string | null;
  overall_score: number | null;
  total_questions: number;
  answered_questions: number;
  responses: ResponseDetail[];
  started_at: string | null;
  completed_at: string | null;
}

export interface ProgressResponse {
  total_questions: number;
  answered_questions: number;
  current_score: number | null;
}
