export type Domain = "research" | "audience" | "analytics" | "creative" | "media" | "content";
export type Effort = "low" | "medium" | "high";
export type Impact = "low" | "medium" | "high";
export type ApprovalStatus = "pending" | "approved" | "rejected";
export type ApprovalUpdateStatus = "approved" | "rejected";
export type Confidence = "high" | "medium" | "low";

export type AnalyzeRequest = {
  org_id: string;
  product: string;
  audience: string;
  channels: string[];
  budget: number;
  goal: string;
};

export type Recommendation = {
  id: string;
  domain: Domain;
  finding: string;
  source: string;
  effort: Effort;
  impact: Impact;
  action: string;
  needs_approval: boolean;
};

export type AnalyzeResponse = {
  campaign_id: string;
  run_id: string;
  action_sheet_id: string;
  approval_id: string | null;
  recommendations: Recommendation[];
};

export type ApprovalResponse = {
  action_sheet_id: string;
  recommendation_id: string;
  status: ApprovalStatus;
};

export type ApprovalState = {
  recommendation_id: string;
  status: ApprovalStatus;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string | null;
};

export type ActionSheetReportResponse = {
  action_sheet_id: string;
  campaign_id: string;
  run_id: string;
  org_id: string;
  brief: AnalyzeRequest;
  recommendations: Recommendation[];
  approvals: ApprovalState[];
  model_used: string;
  processing_ms: number | null;
  created_at: string | null;
};

export type AuditRowResponse = {
  id: string;
  campaign_id: string;
  run_id: string;
  step_index: number;
  node: string;
  summary: string;
  source: string | null;
  confidence: Confidence | null;
  pii_accessed: boolean;
  model_used: string | null;
  created_at: string | null;
};

export type AuditTraceResponse = {
  run_id: string;
  rows: AuditRowResponse[];
};

export type RuntimeConfigResponse = {
  app_name: string;
  app_version: string;
  supabase_url: string;
  supabase_anon_key: string;
};

export type ApiErrorResponse = {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
  };
};
