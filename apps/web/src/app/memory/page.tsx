'use client';

import React from 'react';
import Link from 'next/link';
import { MemoryGraphView } from '@/components/memory/MemoryGraphView';
import { ArrowLeft, Download, ShieldCheck, RefreshCw, FolderGit2 } from 'lucide-react';

export default function MemoryPage() {
  const handleExportVault = () => {
    alert('Exporting Obsidian markdown vault from ./vault...');
  };

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-background">
      {/* Top Header */}
      <header className="h-14 border-b border-border bg-surface px-6 flex items-center justify-between select-none">
        <div className="flex items-center gap-4">
          <Link
            href="/"
            className="flex items-center gap-1.5 text-xs text-muted hover:text-white transition-colors p-1.5 rounded-lg hover:bg-surface-raised"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to Chat</span>
          </Link>
          <div className="h-4 w-px bg-border" />
          <div className="flex items-center gap-2">
            <span className="font-bold text-sm text-white">Temporal Graph Memory Explorer</span>
            <span className="text-[10px] bg-surface-raised border border-border px-2 py-0.5 rounded text-muted font-mono">
              L2 Temporal KG + L3 Obsidian Vault
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs text-muted bg-surface-raised border border-border px-3 py-1.5 rounded-lg">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span className="hidden sm:inline">PII & Secret Fence Active</span>
          </div>

          <button
            onClick={handleExportVault}
            className="flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 bg-white text-black hover:bg-white/90 rounded-lg transition-all shadow"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export Vault (.zip)</span>
          </button>
        </div>
      </header>

      {/* Main Graph View Area */}
      <main className="flex-1 overflow-hidden">
        <MemoryGraphView />
      </main>
    </div>
  );
}
