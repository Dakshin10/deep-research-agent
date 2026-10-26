'use client';

import React, { useState, useRef, useEffect } from 'react';
import { ArrowUp, Square, Paperclip, Sparkles } from 'lucide-react';

export function Composer({
  onSendMessage,
  onStop,
  isStreaming,
}: {
  onSendMessage: (msg: string) => void;
  onStop: () => void;
  isStreaming: boolean;
}) {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const presets = [
    'Critically evaluate commercialization hurdles of Room Temperature Superconductors.',
    'Compare solid-state batteries vs lithium-ion in energy density, cost, and safety.',
    'Mine healthcare hackathon winners and synthesize 3 novel IdeaCards.',
  ];

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [input]);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!input.trim() || isStreaming) return;
    onSendMessage(input.trim());
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="w-full max-w-3xl mx-auto px-4 pb-4">
      {/* Quick Presets */}
      <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-none">
        {presets.map((preset, idx) => (
          <button
            key={idx}
            onClick={() => onSendMessage(preset)}
            disabled={isStreaming}
            className="flex items-center gap-1.5 shrink-0 px-2.5 py-1 text-[11px] bg-surface hover:bg-surface-raised border border-border hover:border-white text-muted hover:text-white rounded-full transition-all"
          >
            <Sparkles className="w-3 h-3 text-white" />
            <span className="truncate max-w-[240px]">{preset}</span>
          </button>
        ))}
      </div>

      {/* Composer Input Box */}
      <div className="relative border border-border bg-surface rounded-2xl shadow-xl overflow-hidden focus-within:border-white transition-colors">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a deep question, search hackathon ideas, or request research..."
          rows={1}
          className="w-full pl-4 pr-24 pt-3.5 pb-3 bg-transparent text-sm text-foreground placeholder:text-muted focus:outline-none resize-none leading-relaxed"
        />

        <div className="flex items-center justify-between px-3 pb-2 pt-1">
          <button
            type="button"
            className="p-1.5 hover:bg-surface-raised rounded-lg text-muted hover:text-white transition-colors"
            title="Attach documents (PDF, DOCX, TXT, CSV)"
          >
            <Paperclip className="w-4 h-4" />
          </button>

          <div className="flex items-center gap-2">
            <span className="text-[10px] text-muted-dark hidden sm:inline">Press Enter to send</span>
            {isStreaming ? (
              <button
                type="button"
                onClick={onStop}
                className="p-2 bg-white text-black font-bold rounded-xl hover:bg-white/90 transition-all shadow"
                title="Stop generation"
              >
                <Square className="w-4 h-4 fill-black" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!input.trim()}
                className={`p-2 rounded-xl transition-all shadow ${
                  input.trim()
                    ? 'bg-white text-black font-bold hover:bg-white/90'
                    : 'bg-surface-raised text-muted cursor-not-allowed border border-border'
                }`}
                title="Send message"
              >
                <ArrowUp className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
