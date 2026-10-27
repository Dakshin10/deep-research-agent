'use client';

import React, { useState } from 'react';
import { ApprovalItem } from '@/types/chat';
import { AlertTriangle, Check, X } from 'lucide-react';

export function ApprovalCard({
  approval,
  onDecision,
}: {
  approval: ApprovalItem;
  onDecision: (approved: boolean, token?: string) => void;
}) {
  const [decided, setDecided] = useState<'approved' | 'denied' | null>(null);

  const handleApprove = () => {
    setDecided('approved');
    onDecision(true, approval.token || `approval_token_${approval.action_id}`);
  };

  const handleDeny = () => {
    setDecided('denied');
    onDecision(false);
  };

  return (
    <div className="my-3 p-4 bg-surface border border-white/20 rounded-xl shadow-lg">
      <div className="flex items-center gap-2 mb-2 text-white font-semibold text-xs">
        <AlertTriangle className="w-4 h-4 text-white" />
        <span className="uppercase tracking-wider">Mutation Action Approval Required</span>
      </div>

      <div className="text-sm text-foreground mb-2">{approval.description}</div>

      <pre className="p-2.5 bg-background border border-border rounded text-[11px] font-mono text-muted mb-3 overflow-x-auto">
        {JSON.stringify(approval.payload, null, 2)}
      </pre>

      {decided === null ? (
        <div className="flex items-center gap-2">
          <button
            onClick={handleApprove}
            className="flex items-center gap-1.5 px-4 py-1.5 bg-white text-black text-xs font-bold rounded-lg hover:bg-white/90 transition-all shadow"
          >
            <Check className="w-3.5 h-3.5" /> Approve & Execute
          </button>
          <button
            onClick={handleDeny}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-raised border border-border text-muted hover:text-white hover:border-border-hover text-xs font-semibold rounded-lg transition-all"
          >
            <X className="w-3.5 h-3.5" /> Deny
          </button>
        </div>
      ) : (
        <div className="text-xs font-mono font-semibold text-white">
          Status: {decided === 'approved' ? '✅ Action Approved' : '❌ Action Denied'}
        </div>
      )}
    </div>
  );
}
