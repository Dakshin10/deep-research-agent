'use client';

import React, { useState } from 'react';
import { ArtifactItem, CitationItem } from '@/types/chat';
import { X, Download, FileText, Globe, CheckCircle2, Copy, Check } from 'lucide-react';

export function ArtifactDrawer({
  artifact,
  citations = [],
  onClose,
}: {
  artifact: ArtifactItem | null;
  citations?: CitationItem[];
  onClose: () => void;
}) {
  const [tab, setTab] = useState<'artifact' | 'sources'>('artifact');
  const [copied, setCopied] = useState(false);

  if (!artifact && citations.length === 0) return null;

  const handleDownload = () => {
    if (!artifact?.preview_content) return;
    const blob = new Blob([artifact.preview_content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${artifact.title.toLowerCase().replace(/\s+/g, '_')}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopy = () => {
    if (!artifact?.preview_content) return;
    navigator.clipboard.writeText(artifact.preview_content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <aside className="w-96 border-l border-border bg-surface flex flex-col h-full shadow-2xl z-20">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-border bg-surface-raised">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setTab('artifact')}
            className={`text-xs font-semibold px-3 py-1.5 rounded-lg transition-all ${
              tab === 'artifact'
                ? 'bg-white text-black font-bold shadow'
                : 'text-muted hover:text-white'
            }`}
          >
            <span className="flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5" /> Artifact
            </span>
          </button>
          <button
            onClick={() => setTab('sources')}
            className={`text-xs font-semibold px-3 py-1.5 rounded-lg transition-all ${
              tab === 'sources'
                ? 'bg-white text-black font-bold shadow'
                : 'text-muted hover:text-white'
            }`}
          >
            <span className="flex items-center gap-1.5">
              <Globe className="w-3.5 h-3.5" /> Sources ({citations.length})
            </span>
          </button>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 hover:bg-surface rounded-lg text-muted hover:text-white transition-colors"
          title="Close drawer"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {tab === 'artifact' && (
          <div>
            {artifact ? (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="text-sm font-bold text-white line-clamp-1">{artifact.title}</div>
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={handleCopy}
                      className="p-1.5 bg-surface-raised border border-border hover:border-white rounded text-muted hover:text-white text-xs"
                      title="Copy content"
                    >
                      {copied ? <Check className="w-3.5 h-3.5 text-white" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>
                    <button
                      onClick={handleDownload}
                      className="p-1.5 bg-white text-black font-bold rounded hover:bg-white/90 text-xs flex items-center gap-1"
                      title="Download artifact"
                    >
                      <Download className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <div className="p-4 bg-background border border-border rounded-xl text-xs leading-relaxed text-foreground whitespace-pre-wrap font-sans">
                  {artifact.preview_content}
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-muted text-xs">No active artifact.</div>
            )}
          </div>
        )}

        {tab === 'sources' && (
          <div className="space-y-3">
            {citations.length === 0 ? (
              <div className="text-center py-12 text-muted text-xs">No citations in current turn.</div>
            ) : (
              citations.map((c, idx) => (
                <div
                  key={idx}
                  className="p-3 bg-background border border-border rounded-lg space-y-1.5 text-xs hover:border-border-hover transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px] text-white font-bold bg-surface px-1.5 py-0.5 rounded border border-border">
                      [{idx + 1}]
                    </span>
                    <span className="flex items-center gap-1 text-[10px] text-white">
                      <CheckCircle2 className="w-3 h-3 text-white" /> verified location
                    </span>
                  </div>
                  <div className="font-semibold text-white line-clamp-1">{c.title}</div>
                  <div className="text-[11px] text-muted italic line-clamp-2">"{c.excerpt}"</div>
                  <div className="text-[10px] text-white/80 font-mono bg-surface p-1 rounded">
                    {c.location}
                  </div>
                  <a
                    href={c.text_fragment_url || c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[11px] text-white hover:underline block pt-1 font-semibold"
                  >
                    Open at verified offset ↗
                  </a>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
