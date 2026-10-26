'use client';

import React from 'react';
import { ClarificationItem } from '@/types/chat';
import { HelpCircle } from 'lucide-react';

export function ClarificationCard({
  clarification,
  onReply,
}: {
  clarification: ClarificationItem;
  onReply: (answer: string) => void;
}) {
  return (
    <div className="my-3 p-4 bg-surface border border-border rounded-xl shadow-md">
      <div className="flex items-center gap-2 mb-2 text-white font-semibold text-xs">
        <HelpCircle className="w-4 h-4 text-white" />
        <span>Clarification Needed:</span>
      </div>
      <div className="text-sm text-foreground mb-3">{clarification.question}</div>
      <div className="flex flex-wrap gap-2">
        {clarification.suggested_answers.map((ans, i) => (
          <button
            key={i}
            onClick={() => onReply(ans)}
            className="text-xs bg-surface-raised border border-border hover:border-white hover:text-white text-muted px-3 py-1.5 rounded-lg transition-all"
          >
            {ans}
          </button>
        ))}
      </div>
    </div>
  );
}
