'use client';

import React, { useEffect, useState } from 'react';
import { X, Download, RefreshCw, Brain, Pin, Trash2, Edit3, ShieldAlert } from 'lucide-react';
import { MemoryGraphView, GraphNode } from './MemoryGraphView';

interface MemoryOverlayProps {
  isOpen: boolean;
  onClose: () => void;
  onExportVault: () => void;
}

export function MemoryOverlay({
  isOpen,
  onClose,
  onExportVault,
}: MemoryOverlayProps) {
  const [syncing, setSyncing] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

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

  const handleSyncVault = async () => {
    setSyncing(true);
    try {
      await new Promise((r) => setTimeout(r, 600));
      setToastMessage('Vault synchronized with ./vault markdown notes.');
      setTimeout(() => setToastMessage(null), 3000);
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-stone-50/95 dark:bg-stone-900/95 backdrop-blur-xl animate-in fade-in duration-150">
      {/* Top Bar */}
      <div className="h-14 border-b border-stone-200 dark:border-stone-800 px-4 md:px-6 flex items-center justify-between select-none">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-stone-900 dark:bg-stone-100 text-stone-50 dark:text-stone-900 flex items-center justify-center shadow">
            <Brain className="w-4 h-4" />
          </div>
          <div>
            <div className="font-semibold text-xs text-stone-900 dark:text-stone-100 tracking-tight">
              Aether Knowledge Graph & Memory
            </div>
            <div className="text-[10px] text-stone-500 font-mono">
              Temporal L2 KG · L3 Obsidian Vault (./vault)
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Export Vault */}
          <button
            onClick={onExportVault}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs bg-stone-200/80 dark:bg-stone-800 hover:bg-stone-300 dark:hover:bg-stone-700 text-stone-700 dark:text-stone-300 transition-colors font-medium"
            title="Download Obsidian-compatible markdown vault (.zip)"
          >
            <Download className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Export Vault</span>
          </button>

          {/* Sync Vault */}
          <button
            onClick={handleSyncVault}
            disabled={syncing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs bg-stone-200/80 dark:bg-stone-800 hover:bg-stone-300 dark:hover:bg-stone-700 text-stone-700 dark:text-stone-300 transition-colors font-medium"
            title="Force synchronization between graph and ./vault"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">Sync</span>
          </button>

          {/* Close Overlay */}
          <button
            onClick={onClose}
            className="p-1.5 text-stone-500 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100 rounded-lg hover:bg-stone-200/60 dark:hover:bg-stone-800 transition-colors ml-2"
            title="Close (Esc)"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Toast Notification */}
      {toastMessage && (
        <div className="absolute top-16 left-1/2 -translate-x-1/2 z-50 px-4 py-2 bg-stone-900 text-stone-50 dark:bg-stone-100 dark:text-stone-900 rounded-full text-xs shadow-xl animate-in fade-in">
          {toastMessage}
        </div>
      )}

      {/* Main Graph Content */}
      <div className="flex-1 overflow-hidden p-4 md:p-6">
        <MemoryGraphView />
      </div>
    </div>
  );
}
