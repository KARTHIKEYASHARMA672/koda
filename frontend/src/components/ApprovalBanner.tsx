import { AlertTriangle, Check, X } from "lucide-react";
import type { PendingApproval } from "../types";

interface ApprovalBannerProps {
  approvals: PendingApproval[];
  onResolve: (approvalId: string, approved: boolean) => void;
}

export function ApprovalBanner({ approvals, onResolve }: ApprovalBannerProps) {
  if (approvals.length === 0) return null;

  return (
    <section aria-label="Pending safety approvals" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {approvals.map((apr) => (
        <div key={apr.id} className="koda-approval-card" role="alert">
          <div className="koda-row-between">
            <span className="koda-pill koda-pill--gold">
              <AlertTriangle size={13} aria-hidden="true" />
              {apr.tier} · {apr.tool_name}
            </span>
            <span className="koda-mono koda-muted">{apr.id}</span>
          </div>
          <div>{apr.summary}</div>
          <div className="koda-row-between">
            <code className="koda-mono koda-muted">{apr.args_json}</code>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className="koda-btn koda-btn--primary"
                aria-label="Approve action"
                onClick={() => onResolve(apr.id, true)}
              >
                <Check size={14} aria-hidden="true" />
                Approve
              </button>
              <button
                type="button"
                className="koda-btn koda-btn--danger"
                aria-label="Deny action"
                onClick={() => onResolve(apr.id, false)}
              >
                <X size={14} aria-hidden="true" />
                Deny
              </button>
            </div>
          </div>
        </div>
      ))}
    </section>
  );
}
