'use client';

import React, { useEffect, useRef } from 'react';
import { ChatMessage } from '@/types/chat';
import { LiveResearchCard } from './LiveResearchCard';
import { CodeExecutionCard } from './CodeExecutionCard';
import { CitationChip } from './CitationChip';
import { ClarificationCard } from './ClarificationCard';
import { ApprovalCard } from './ApprovalCard';
import { User, Sparkles, Brain } from 'lucide-react';

export function ChatArea({
  messages,
  onClarifyReply,
  onApprovalDecision,
}: {
  messages: ChatMessage[];
  onClarifyReply: (ans: string) => void;
  onApprovalDecision: (approved: boolean, token?: string) => void;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-6 text-center select-none">
        <div className="w-12 h-12 rounded-2xl bg-white text-black flex items-center justify-center font-black text-xl mb-4 shadow-xl">
          ⚡
        </div>
        <h2 className="text-xl font-bold text-white tracking-tight mb-2">
          Deep Research & Idea Miner
        </h2>
        <p className="text-xs text-muted max-w-md leading-relaxed mb-6">
          Single unified Claude-style assistant with parallel research fan-out, Cloudflare Code Mode, verified document offsets, and temporal graph memory.
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6 max-w-3xl w-full mx-auto">
      {messages.map((msg) => {
        const isUser = msg.role === 'user';

        return (
          <div key={msg.id} className="space-y-2">
            {/* Message Header */}
            <div className="flex items-center gap-2">
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                  isUser
                    ? 'bg-surface-raised border border-border text-foreground'
                    : 'bg-white text-black'
                }`}
              >
                {isUser ? <User className="w-3.5 h-3.5" /> : <Sparkles className="w-3.5 h-3.5" />}
              </div>
              <span className="text-xs font-semibold text-white">
                {isUser ? 'You' : 'Deep Research Agent'}
              </span>
            </div>

            {/* Message Body Container */}
            <div className="pl-8 text-sm leading-relaxed text-foreground">
              {/* Reasoning Summary */}
              {msg.reasoning && (
                <div className="text-xs text-muted italic mb-2 p-2 bg-surface rounded-lg border border-border flex items-center gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-white animate-ping" />
                  <span>{msg.reasoning}</span>
                </div>
              )}

              {/* Memory Used Chip */}
              {msg.memories_used && msg.memories_used.length > 0 && (
                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 mb-2 bg-surface border border-border rounded-full text-[11px] text-white">
                  <Brain className="w-3 h-3 text-white" />
                  <span>
                    Influenced by {msg.memories_used.length} memory item{msg.memories_used.length > 1 ? 's' : ''}
                  </span>
                </div>
              )}

              {/* Research Progress Card */}
              {msg.research_progress && (
                <LiveResearchCard progress={msg.research_progress} />
              )}

              {/* Code Execution Cards */}
              {msg.code_executions && msg.code_executions.length > 0 && (
                <div className="space-y-1.5">
                  {msg.code_executions.map((exec, idx) => (
                    <CodeExecutionCard key={idx} execution={exec} />
                  ))}
                </div>
              )}

              {/* Main Content Markdown */}
              <div className="whitespace-pre-wrap font-sans text-sm">
                {msg.content}
                {msg.isStreaming && (
                  <span className="inline-block w-2 h-4 ml-1 bg-white animate-pulse align-middle" />
                )}
              </div>

              {/* Inline Citations List */}
              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-3 pt-2 border-t border-border/50 flex flex-wrap items-center gap-1">
                  <span className="text-xs text-muted mr-1 font-semibold">Citations:</span>
                  {msg.citations.map((c, idx) => (
                    <CitationChip key={idx} citation={c} index={idx} />
                  ))}
                </div>
              )}

              {/* Clarification Request Inline Card */}
              {msg.clarification && (
                <ClarificationCard
                  clarification={msg.clarification}
                  onReply={onClarifyReply}
                />
              )}

              {/* Mutation Approval Card */}
              {msg.approval && (
                <ApprovalCard
                  approval={msg.approval}
                  onDecision={onApprovalDecision}
                />
              )}
            </div>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
