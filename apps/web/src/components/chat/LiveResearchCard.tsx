'use client';

import React, { useState } from 'react';
import { ResearchProgressItem } from '@/types/chat';
import { ChevronDown, ChevronUp, Layers, CheckCircle2, ShieldCheck, Zap } from 'lucide-react';

export function LiveResearchCard({ progress }: { progress: ResearchProgressItem }) {
  const [expanded, setExpanded] = useState(true);

  const isDone = progress.stage === 'done' || progress.completed_shards >= progress.active_shards;

  return (
    <div className="my-3 border border-border bg-surface rounded-xl overflow-hidden transition-all shadow-md">
      {/* Header */}
      <div
        onClick={() => setExpanded(!expanded)}
        className="flex items-center justify-between px-4 py-3 bg-surface-raised cursor-pointer hover:bg-surface-raised/80 select-none border-b border-border/50"
      >
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-white animate-pulse" />
          <span className="text-xs font-bold uppercase tracking-wider text-white">
            {isDone ? 'Research Completed' : `Researching • Stage: ${progress.stage}`}
          </span>
          <span className="text-xs font-mono text-muted bg-surface px-2 py-0.5 rounded border border-border">
            {progress.completed_shards}/{progress.active_shards} Shards
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-muted">{progress.budget_used_pct.toFixed(0)}% budget</span>
          {expanded ? <ChevronUp className="w-4 h-4 text-muted" /> : <ChevronDown className="w-4 h-4 text-muted" />}
        </div>
      </div>

      {/* Progress Bar */}
      <div className="w-full bg-border h-1">
        <div
          className="bg-white h-1 transition-all duration-300"
          style={{ width: `${Math.min(100, progress.budget_used_pct)}%` }}
        />
      </div>

      {/* Expanded Details */}
      {expanded && (
        <div className="p-4 space-y-3">
          <div className="text-xs text-muted font-medium flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-white" />
            Parallel Sources Discovered:
          </div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(progress.sources_found || {}).map(([family, count]) => (
              <div
                key={family}
                className="flex items-center gap-1.5 bg-background border border-border px-2.5 py-1 rounded-md text-xs"
              >
                <span className="text-muted uppercase text-[10px] font-semibold">{family.replace('_', ' ')}</span>
                <span className="font-mono font-bold text-white">{count}</span>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2 pt-1 text-[11px] text-muted">
            <ShieldCheck className="w-3.5 h-3.5 text-white" />
            <span>Citation Gate: All claims enforced with exact byte/character offsets.</span>
          </div>
        </div>
      )}
    </div>
  );
}
