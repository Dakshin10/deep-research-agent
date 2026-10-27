'use client';

import React, { useState } from 'react';
import { CitationItem } from '@/types/chat';
import { ExternalLink, CheckCircle2, AlertCircle } from 'lucide-react';

export function CitationChip({ citation, index }: { citation: CitationItem; index: number }) {
  const [showCard, setShowCard] = useState(false);

  let domain = 'source';
  try {
    domain = new URL(citation.url).hostname.replace('www.', '');
  } catch {}

  const link = citation.text_fragment_url || citation.url;

  return (
    <span
      className="relative inline-block ml-1 align-baseline select-none"
      onMouseEnter={() => setShowCard(true)}
      onMouseLeave={() => setShowCard(false)}
    >
      <a
        href={link}
        target="_blank"
        rel="noopener noreferrer"
        className={`inline-flex items-center px-1.5 py-0.2 text-[10px] font-mono font-medium rounded transition-colors ${
          citation.verified
            ? 'bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300 hover:bg-stone-200 dark:hover:bg-stone-700 border border-stone-200 dark:border-stone-700'
            : 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800'
        }`}
        title={`Source [${index + 1}]: ${citation.title}`}
      >
        [{index + 1}]
      </a>

      {showCard && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-72 p-3 bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 rounded-xl shadow-2xl text-left text-xs pointer-events-auto backdrop-blur-md animate-in fade-in zoom-in-95">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] uppercase font-mono text-stone-500 bg-stone-100 dark:bg-stone-800 px-1.5 py-0.5 rounded">
              {domain}
            </span>
            {citation.verified ? (
              <span className="flex items-center gap-1 text-[10px] text-emerald-600 dark:text-emerald-400 font-mono">
                <CheckCircle2 className="w-3 h-3" /> Location Verified
              </span>
            ) : (
              <span className="flex items-center gap-1 text-[10px] text-amber-600 dark:text-amber-400 font-mono">
                <AlertCircle className="w-3 h-3" /> Reference
              </span>
            )}
          </div>

          <div className="font-semibold text-stone-900 dark:text-stone-100 text-xs line-clamp-2 mb-1">
            {citation.title}
          </div>
          <div className="text-stone-600 dark:text-stone-300 text-[11px] line-clamp-3 italic mb-2">
            "{citation.excerpt}"
          </div>

          <div className="text-[10px] text-stone-500 font-mono mb-2 bg-stone-50 dark:bg-stone-950 p-1.5 rounded border border-stone-100 dark:border-stone-800 truncate">
            {citation.location}
          </div>

          <a
            href={link}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-[11px] text-stone-800 dark:text-stone-200 hover:underline font-medium"
          >
            Scroll to Text in Source <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      )}
    </span>
  );
}
