'use client';

import React, { useState } from 'react';
import { CitationItem } from '@/types/chat';
import { ExternalLink, CheckCircle } from 'lucide-react';

export function CitationChip({ citation, index }: { citation: CitationItem; index: number }) {
  const [showCard, setShowCard] = useState(false);

  let domain = 'link';
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
        className="inline-flex items-center px-1.5 py-0.2 text-[10px] font-mono font-bold bg-surface-raised border border-border text-foreground hover:bg-white hover:text-black hover:border-white rounded transition-colors"
      >
        [{index + 1}]
      </a>

      {showCard && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-72 p-3 bg-surface border border-border-hover rounded-xl shadow-2xl text-left text-xs pointer-events-auto backdrop-blur-md">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] uppercase font-bold text-muted bg-surface-raised px-1.5 py-0.5 rounded border border-border">
              {domain}
            </span>
            <span className="flex items-center gap-1 text-[10px] text-white font-mono">
              <CheckCircle className="w-3 h-3 text-white" /> 100% verified
            </span>
          </div>

          <div className="font-semibold text-white text-xs line-clamp-1 mb-1">{citation.title}</div>
          <div className="text-muted text-[11px] line-clamp-3 italic mb-2">"{citation.excerpt}"</div>

          <div className="text-[10px] text-white/80 font-mono mb-2 bg-background p-1 rounded border border-border/50">
            {citation.location}
          </div>

          <a
            href={link}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-[11px] text-white hover:underline font-semibold"
          >
            Scroll to Text in Source <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      )}
    </span>
  );
}
