'use client';

import React, { useEffect, useRef, useState } from 'react';
import { ChatMessage, ArtifactItem } from '@/types/chat';
import { WorkStatusLine } from './WorkStatusLine';
import { CitationChip } from './CitationChip';
import { ClarificationCard } from './ClarificationCard';
import { ApprovalCard } from './ApprovalCard';
import { Brain, FileText, Sparkles, ChevronDown, ChevronRight, X, ExternalLink } from 'lucide-react';

interface ChatAreaProps {
  messages: ChatMessage[];
  onSendMessage: (msg: string) => void;
  onClarifyReply: (ans: string) => void;
  onApprovalDecision: (approved: boolean, token?: string) => void;
  onOpenArtifact: (artifact: ArtifactItem) => void;
  onOpenSources: () => void;
}

export function ChatArea({
  messages,
  onSendMessage,
  onClarifyReply,
  onApprovalDecision,
  onOpenArtifact,
  onOpenSources,
}: ChatAreaProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [expandedMemoryTurns, setExpandedMemoryTurns] = useState<Record<string, boolean>>({});

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const toggleMemoryExpansion = (msgId: string) => {
    setExpandedMemoryTurns((prev) => ({
      ...prev,
      [msgId]: !prev[msgId],
    }));
  };

  // 1. Calm, Centered Empty State
  if (messages.length === 0) {
    const suggestions = [
      'Research the commercialization hurdles of Room Temperature Superconductors.',
      'Compare solid-state batteries vs lithium-ion in energy density and cost.',
      'Mine healthcare hackathon winners and synthesize 3 novel IdeaCards.',
    ];

    return (
      <div className="flex-1 flex flex-col items-center justify-center p-6 text-center select-none max-w-xl mx-auto animate-in fade-in duration-300">
        <div className="w-10 h-10 rounded-xl bg-stone-900 dark:bg-stone-100 text-stone-50 dark:text-stone-900 flex items-center justify-center font-bold text-sm mb-4 shadow-sm">
          Æ
        </div>
        <h1 className="text-xl font-serif text-stone-900 dark:text-stone-100 tracking-tight mb-2">
          What would you like to explore?
        </h1>
        <p className="text-xs text-stone-500 dark:text-stone-400 max-w-sm leading-relaxed mb-6">
          Ask questions, initiate deep multi-source research, synthesize hackathon ideas, or consult your knowledge graph.
        </p>

        {/* At most 3 clean suggestion chips */}
        <div className="w-full space-y-2 text-left">
          {suggestions.map((prompt, idx) => (
            <button
              key={idx}
              onClick={() => onSendMessage(prompt)}
              className="w-full p-3 rounded-xl border border-stone-200 dark:border-stone-800 bg-white/70 dark:bg-stone-900/60 hover:bg-stone-100 dark:hover:bg-stone-800/80 text-stone-700 dark:text-stone-300 text-xs transition-colors flex items-center justify-between group shadow-xs"
            >
              <span className="line-clamp-1">{prompt}</span>
              <span className="opacity-0 group-hover:opacity-100 text-stone-400 text-[10px] font-mono transition-opacity ml-2 shrink-0">
                ↵
              </span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  // 2. Conversation Reading Column (~720px width, generous whitespace)
  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="max-w-[720px] mx-auto space-y-8">
        {messages.map((msg) => {
          const isUser = msg.role === 'user';

          if (isUser) {
            // User message: Light bubble on the right
            return (
              <div key={msg.id} className="flex justify-end">
                <div className="max-w-[85%] rounded-2xl px-4 py-2.5 bg-stone-100 dark:bg-stone-800 text-stone-900 dark:text-stone-100 text-sm leading-relaxed shadow-xs">
                  {msg.content}
                </div>
              </div>
            );
          }

          // Assistant message: Clean prose (not bubbles), generous whitespace
          const isMemoryExpanded = !!expandedMemoryTurns[msg.id];

          return (
            <div key={msg.id} className="space-y-3 animate-in fade-in duration-200">
              {/* Quiet Progressive Work Status Line */}
              <WorkStatusLine
                isStreaming={msg.isStreaming}
                reasoning={msg.reasoning}
                progress={msg.research_progress}
                codeExecutions={msg.code_executions}
              />

              {/* Memory Used Chip */}
              {msg.memories_used && msg.memories_used.length > 0 && (
                <div className="font-sans text-xs">
                  <button
                    onClick={() => toggleMemoryExpansion(msg.id)}
                    className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-stone-100 dark:bg-stone-800/70 border border-stone-200/60 dark:border-stone-700/60 text-stone-500 dark:text-stone-400 hover:text-stone-800 dark:hover:text-stone-200 transition-colors text-[11px]"
                  >
                    <Brain className="w-3 h-3 text-stone-400" />
                    <span>Memory used ({msg.memories_used.length})</span>
                    {isMemoryExpanded ? (
                      <ChevronDown className="w-2.5 h-2.5" />
                    ) : (
                      <ChevronRight className="w-2.5 h-2.5" />
                    )}
                  </button>

                  {isMemoryExpanded && (
                    <div className="mt-2 p-2.5 rounded-xl bg-stone-50 dark:bg-stone-900/90 border border-stone-200 dark:border-stone-800 text-[11px] space-y-1.5">
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-stone-400">
                        Recalled Memories
                      </div>
                      {msg.memories_used.map((mem, i) => (
                        <div key={i} className="flex items-start justify-between gap-2 text-stone-600 dark:text-stone-300">
                          <div>
                            <span className="font-semibold text-stone-800 dark:text-stone-200">
                              {mem.entity}:
                            </span>{' '}
                            {mem.fact}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Clean Assistant Prose */}
              <div className="font-serif text-[15px] leading-relaxed text-stone-800 dark:text-stone-200 whitespace-pre-wrap selection:bg-stone-200 dark:selection:bg-stone-700">
                {msg.content}
                {msg.isStreaming && (
                  <span className="inline-block w-1.5 h-4 ml-1 bg-stone-400 dark:bg-stone-500 animate-pulse align-middle" />
                )}
              </div>

              {/* Compact Artifact Cards */}
              {msg.artifacts && msg.artifacts.length > 0 && (
                <div className="space-y-2 pt-2">
                  {msg.artifacts.map((art) => (
                    <button
                      key={art.artifact_id}
                      onClick={() => onOpenArtifact(art)}
                      className="w-full flex items-center justify-between p-3 rounded-xl border border-stone-200 dark:border-stone-800 bg-stone-50/80 dark:bg-stone-900/60 hover:bg-stone-100 dark:hover:bg-stone-800/80 text-left transition-colors group shadow-xs"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-stone-200 dark:bg-stone-800 flex items-center justify-center shrink-0">
                          <FileText className="w-4 h-4 text-stone-700 dark:text-stone-300" />
                        </div>
                        <div>
                          <div className="font-semibold text-xs text-stone-900 dark:text-stone-100 group-hover:underline">
                            {art.title}
                          </div>
                          <div className="text-[10px] text-stone-400 uppercase font-mono">
                            {art.artifact_type} · Click to view in panel
                          </div>
                        </div>
                      </div>
                      <ExternalLink className="w-3.5 h-3.5 text-stone-400 group-hover:text-stone-700 dark:group-hover:text-stone-200 shrink-0" />
                    </button>
                  ))}
                </div>
              )}

              {/* Numbered Inline Citation Chips */}
              {msg.citations && msg.citations.length > 0 && (
                <div className="pt-2 flex flex-wrap items-center gap-1 text-xs">
                  <span className="text-[11px] text-stone-400 font-medium mr-1 font-sans">
                    Sources:
                  </span>
                  {msg.citations.map((c, idx) => (
                    <CitationChip key={idx} citation={c} index={idx} />
                  ))}
                  <button
                    onClick={onOpenSources}
                    className="text-[10px] text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 underline ml-2 font-mono"
                  >
                    View all ({msg.citations.length})
                  </button>
                </div>
              )}

              {/* Inline Clarification Quick-Reply Cards */}
              {msg.clarification && (
                <div className="pt-2">
                  <ClarificationCard
                    clarification={msg.clarification}
                    onReply={onClarifyReply}
                  />
                </div>
              )}

              {/* Inline Mutation Approval Cards */}
              {msg.approval && (
                <div className="pt-2">
                  <ApprovalCard
                    approval={msg.approval}
                    onDecision={onApprovalDecision}
                  />
                </div>
              )}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
