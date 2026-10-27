'use client';

import React, { useEffect } from 'react';
import { X, ExternalLink, CheckCircle2, AlertCircle, Globe } from 'lucide-react';
import { CitationItem } from '@/types/chat';

interface SourcesSheetProps {
  isOpen: boolean;
  onClose: () => void;
  citations: CitationItem[];
}

export function SourcesSheet({
  isOpen,
  onClose,
  citations,
}: SourcesSheetProps) {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-stone-900/30 dark:bg-stone-950/60 backdrop-blur-sm transition-opacity"
      />

      {/* Slide-over Panel */}
      <div className="relative w-96 max-w-[90vw] h-full bg-white dark:bg-stone-900 border-l border-stone-200 dark:border-stone-800 shadow-2xl flex flex-col z-10 animate-in slide-in-from-right duration-200">
        <div className="p-4 border-b border-stone-200 dark:border-stone-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Globe className="w-4 h-4 text-stone-500" />
            <span className="font-semibold text-xs text-stone-900 dark:text-stone-100">
              Verified Sources & Evidence ({citations.length})
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 rounded-lg"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {citations.length === 0 ? (
            <div className="text-center py-12 text-xs text-stone-400">
              No citations generated for this conversation yet.
            </div>
          ) : (
            citations.map((c, idx) => {
              const domain = (() => {
                try {
                  return new URL(c.url).hostname;
                } catch {
                  return c.url;
                }
              })();

              return (
                <div
                  key={idx}
                  className="p-3 rounded-xl border border-stone-200 dark:border-stone-800 bg-stone-50 dark:bg-stone-950/50 space-y-2 text-xs"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-semibold text-stone-900 dark:text-stone-100 line-clamp-2">
                      [{idx + 1}] {c.title}
                    </span>
                    <a
                      href={c.text_fragment_url || c.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-1 text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 shrink-0"
                      title="Open at exact document location"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  </div>

                  <div className="flex items-center gap-2 text-[10px] text-stone-500 font-mono">
                    <span>{domain}</span>
                    <span>·</span>
                    <span className="truncate">{c.location}</span>
                  </div>

                  <p className="text-[11px] text-stone-600 dark:text-stone-300 italic bg-white dark:bg-stone-900 p-2 rounded-lg border border-stone-200/60 dark:border-stone-800 line-clamp-3">
                    "{c.excerpt}"
                  </p>

                  <div className="flex items-center gap-1 text-[10px]">
                    {c.verified ? (
                      <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium">
                        <CheckCircle2 className="w-3 h-3" /> Location Verified
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400 font-medium">
                        <AlertCircle className="w-3 h-3" /> Unverified
                      </span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
