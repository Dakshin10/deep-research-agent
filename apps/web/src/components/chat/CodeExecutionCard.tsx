'use client';

import React, { useState } from 'react';
import { CodeExecutionItem } from '@/types/chat';
import { Terminal, ChevronDown, ChevronUp, Copy, Check } from 'lucide-react';

export function CodeExecutionCard({ execution }: { execution: CodeExecutionItem }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyCode = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(execution.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="my-2 border border-border bg-surface rounded-lg overflow-hidden text-xs">
      <div
        onClick={() => setExpanded(!expanded)}
        className="flex items-center justify-between px-3.5 py-2.5 bg-surface-raised cursor-pointer hover:bg-surface-raised/80 select-none"
      >
        <div className="flex items-center gap-2">
          <Terminal className="w-3.5 h-3.5 text-white" />
          <span className="font-mono text-muted">Code Mode executed</span>
          <span className="font-mono text-[10px] bg-background border border-border px-1.5 py-0.5 rounded text-white">
            {execution.duration_ms}ms
          </span>
          <span className="text-[10px] text-muted">sandbox: v8 isolate</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={copyCode}
            className="p-1 hover:bg-surface rounded text-muted hover:text-white transition-colors"
            title="Copy code"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-white" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
          {expanded ? <ChevronUp className="w-3.5 h-3.5 text-muted" /> : <ChevronDown className="w-3.5 h-3.5 text-muted" />}
        </div>
      </div>

      {expanded && (
        <div className="border-t border-border p-3 space-y-2 bg-background font-mono text-xs">
          <div>
            <div className="text-[10px] uppercase text-muted mb-1 font-semibold">Script</div>
            <pre className="p-2.5 bg-surface border border-border rounded text-foreground overflow-x-auto">
              <code>{execution.code}</code>
            </pre>
          </div>
          <div>
            <div className="text-[10px] uppercase text-muted mb-1 font-semibold">Result</div>
            <pre className="p-2 bg-surface/50 border border-border/50 rounded text-muted overflow-x-auto text-[11px]">
              <code>{execution.result}</code>
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
