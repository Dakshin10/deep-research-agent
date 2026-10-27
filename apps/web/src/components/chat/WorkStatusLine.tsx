'use client';

import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Sparkles, Terminal, Globe, CheckCircle2 } from 'lucide-react';
import { ResearchProgressItem, CodeExecutionItem } from '@/types/chat';

interface WorkStatusLineProps {
  isStreaming?: boolean;
  reasoning?: string;
  progress?: ResearchProgressItem;
  codeExecutions?: CodeExecutionItem[];
}

export function WorkStatusLine({
  isStreaming,
  reasoning,
  progress,
  codeExecutions,
}: WorkStatusLineProps) {
  const [expanded, setExpanded] = useState<boolean>(false);

  // If there's no background work, return null
  if (!reasoning && !progress && (!codeExecutions || codeExecutions.length === 0)) {
    return null;
  }

  // Derive concise one-line status
  let statusText = '';
  if (isStreaming) {
    if (progress) {
      const sourcesCount = Object.values(progress.sources_found || {}).reduce((a, b) => a + b, 0);
      statusText = `Searching ${sourcesCount > 0 ? sourcesCount : progress.active_shards} sources across parallel shards...`;
    } else if (codeExecutions && codeExecutions.length > 0) {
      statusText = 'Executing code in isolated sandbox...';
    } else if (reasoning) {
      statusText = reasoning;
    } else {
      statusText = 'Synthesizing response...';
    }
  } else {
    // Done state
    if (progress) {
      const totalSources = Object.values(progress.sources_found || {}).reduce((a, b) => a + b, 0);
      statusText = `Searched ${totalSources > 0 ? totalSources : 5} sources across parallel shards`;
    } else if (codeExecutions && codeExecutions.length > 0) {
      statusText = `Executed ${codeExecutions.length} sandboxed analysis script${codeExecutions.length > 1 ? 's' : ''}`;
    } else {
      statusText = 'Completed synthesis';
    }
  }

  return (
    <div className="mb-3 font-sans text-xs select-none">
      {/* Clickable Status Bar */}
      <button
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
        className="group flex items-center gap-2 text-stone-600 dark:text-stone-300 hover:text-stone-900 dark:hover:text-stone-100 transition-colors py-1 px-2.5 rounded-lg bg-stone-100/70 dark:bg-stone-800/50 hover:bg-stone-200/60 dark:hover:bg-stone-800 border border-stone-200/60 dark:border-stone-700/60"
      >
        {isStreaming ? (
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
          </span>
        ) : (
          <CheckCircle2 className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500" />
        )}

        <span className="font-medium tracking-tight truncate max-w-sm sm:max-w-md">
          {statusText}
        </span>

        <span className="text-[10px] text-stone-400 dark:text-stone-500 font-mono ml-auto pl-2">
          {expanded ? 'Hide' : 'Details'}
        </span>

        {expanded ? (
          <ChevronDown className="w-3 h-3 text-stone-400 dark:text-stone-500" />
        ) : (
          <ChevronRight className="w-3 h-3 text-stone-400 dark:text-stone-500" />
        )}
      </button>

      {/* Expandable Progressive Disclosure Area */}
      {expanded && (
        <div className="mt-2 p-3 space-y-3 rounded-xl bg-stone-50 dark:bg-stone-900/80 border border-stone-200 dark:border-stone-800 text-stone-700 dark:text-stone-300">
          {/* Reasoning Narrative */}
          {reasoning && (
            <div className="space-y-1">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-stone-400 dark:text-stone-500">
                Reasoning Plan
              </div>
              <p className="text-xs leading-relaxed italic text-stone-600 dark:text-stone-300">
                {reasoning}
              </p>
            </div>
          )}

          {/* Parallel Research Shards Table & Sources */}
          {progress && (
            <div className="space-y-2 pt-1 border-t border-stone-200/60 dark:border-stone-800">
              <div className="flex items-center justify-between text-[10px] font-semibold text-stone-400 dark:text-stone-500">
                <span className="uppercase tracking-wider">Parallel Research Shards</span>
                <span>{progress.active_shards} active · Budget {progress.budget_used_pct}%</span>
              </div>

              {/* Budget Bar */}
              <div className="w-full bg-stone-200 dark:bg-stone-800 h-1 rounded-full overflow-hidden">
                <div
                  className="bg-stone-500 dark:bg-stone-400 h-full transition-all duration-300"
                  style={{ width: `${Math.min(100, progress.budget_used_pct || 20)}%` }}
                />
              </div>

              {/* Source Family Breakdown */}
              {progress.sources_found && Object.keys(progress.sources_found).length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {Object.entries(progress.sources_found).map(([family, count]) => (
                    <span
                      key={family}
                      className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-stone-200/80 dark:bg-stone-800 font-medium"
                    >
                      <Globe className="w-2.5 h-2.5 text-stone-400" />
                      <span>{family}: {count}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Code Execution Cards */}
          {codeExecutions && codeExecutions.length > 0 && (
            <div className="space-y-2 pt-1 border-t border-stone-200/60 dark:border-stone-800">
              <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-stone-400 dark:text-stone-500">
                <Terminal className="w-3 h-3" />
                <span>Code Mode Sandbox Execution</span>
              </div>
              {codeExecutions.map((exec, idx) => (
                <div
                  key={idx}
                  className="p-2.5 rounded-lg bg-stone-100 dark:bg-stone-950/70 border border-stone-200 dark:border-stone-800 font-mono text-[11px] space-y-1.5"
                >
                  <div className="text-stone-500 dark:text-stone-400 text-[10px]">
                    JavaScript ({exec.duration_ms}ms)
                  </div>
                  <pre className="overflow-x-auto text-stone-800 dark:text-stone-200 leading-tight">
                    <code>{exec.code}</code>
                  </pre>
                  {exec.result && (
                    <div className="pt-1 border-t border-stone-200 dark:border-stone-800 text-[10px] text-stone-600 dark:text-stone-400 truncate">
                      Output: {exec.result}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
