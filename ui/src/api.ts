import type {
  ActionSheetReportResponse,
  AnalyzeRequest,
  AnalyzeResponse,
  ApiErrorResponse,
  ApprovalResponse,
  ApprovalUpdateStatus,
  AuditTraceResponse,
  RuntimeConfigResponse,
} from "./types";

export async function loadRuntimeConfig(): Promise<RuntimeConfigResponse> {
  return requestJson<RuntimeConfigResponse>("/api/config");
}

export async function runAnalyze(
  token: string,
  payload: AnalyzeRequest,
): Promise<AnalyzeResponse> {
  return requestJson<AnalyzeResponse>("/api/analyze", {
    method: "POST",
    headers: authedJsonHeaders(token),
    body: JSON.stringify(payload),
  });
}

export async function getActionSheet(
  token: string,
  actionSheetId: string,
): Promise<ActionSheetReportResponse> {
  return requestJson<ActionSheetReportResponse>(
    `/api/action-sheets/${pathSegment(actionSheetId)}`,
    {
      headers: authedHeaders(token),
    },
  );
}

export async function getAuditTrace(token: string, runId: string): Promise<AuditTraceResponse> {
  return requestJson<AuditTraceResponse>(`/api/runs/${pathSegment(runId)}/audit`, {
    headers: authedHeaders(token),
  });
}

export async function updateApproval(
  token: string,
  actionSheetId: string,
  recommendationId: string,
  status: ApprovalUpdateStatus,
): Promise<ApprovalResponse> {
  return requestJson<ApprovalResponse>(
    `/api/action-sheets/${pathSegment(actionSheetId)}/approvals/${
      pathSegment(recommendationId)
    }`,
    {
      method: "POST",
      headers: authedJsonHeaders(token),
      body: JSON.stringify({ status }),
    },
  );
}

function authedHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

function authedJsonHeaders(token: string): HeadersInit {
  return {
    ...authedHeaders(token),
    "Content-Type": "application/json",
  };
}

function pathSegment(value: string): string {
  return encodeURIComponent(value);
}

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as T;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as ApiErrorResponse;
    const code = payload.error?.code;
    const message = payload.error?.message;
    if (code && message) {
      return `${code}: ${message}`;
    }
    if (message) {
      return message;
    }
  } catch {
    return `Request failed with HTTP ${response.status}.`;
  }
  return `Request failed with HTTP ${response.status}.`;
}
