import type { ActionSheetReportResponse, AuditTraceResponse } from "./types";

export function buildReportMarkdown(
  report: ActionSheetReportResponse,
  audit: AuditTraceResponse | null,
): string {
  const approvals = new Map(
    report.approvals.map((approval) => [approval.recommendation_id, approval.status]),
  );
  const auditRows = [...(audit?.rows ?? [])].sort(
    (left, right) => left.step_index - right.step_index,
  );

  const lines = [
    "# MIRA Action Sheet",
    "",
    "## Campaign Brief",
    `- Product: ${normalizeText(report.brief.product)}`,
    `- Audience: ${normalizeText(report.brief.audience)}`,
    `- Channels: ${report.brief.channels.map(normalizeText).join(", ")}`,
    `- Budget: ${report.brief.budget}`,
    `- Goal: ${normalizeText(report.brief.goal)}`,
    "",
    "## Recommendations",
    "",
    ...report.recommendations.flatMap((recommendation, index) => [
      `### ${index + 1}. ${normalizeText(recommendation.domain)} recommendation`,
      `- Finding: ${normalizeText(recommendation.finding)}`,
      `- Action: ${normalizeText(recommendation.action)}`,
      `- Source: ${normalizeText(recommendation.source)}`,
      `- Effort: ${recommendation.effort}`,
      `- Impact: ${recommendation.impact}`,
      `- Approval: ${
        recommendation.needs_approval
          ? approvals.get(recommendation.id) ?? "pending"
          : "not required"
      }`,
      "",
    ]),
    "## Audit Trace",
    "",
    ...auditRows.flatMap((row) => [
      `### Step ${row.step_index}: ${normalizeText(row.node)}`,
      `- Summary: ${normalizeText(row.summary)}`,
      `- Source: ${normalizeText(row.source ?? "none")}`,
      `- Confidence: ${row.confidence ?? "unknown"}`,
      `- Model: ${normalizeText(row.model_used ?? "none")}`,
      "",
    ]),
    "## Metadata",
    `- Action sheet: ${report.action_sheet_id}`,
    `- Campaign: ${report.campaign_id}`,
    `- Run: ${report.run_id}`,
    `- Model: ${normalizeText(report.model_used)}`,
    `- Processing: ${report.processing_ms ?? "unknown"} ms`,
  ];

  return `${lines.join("\n").trim()}\n`;
}

function normalizeText(value: string): string {
  return value.replace(/[\r\n]+/g, " ").replace(/#+/g, "").trim();
}
