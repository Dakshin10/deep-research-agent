'use client';

import React, { useState, useEffect } from 'react';
import { Conversation } from '@/types/chat';
import { Search, Plus, Shield, Brain, Settings, Download, MessageSquare } from 'lucide-react';

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  conversations: Conversation[];
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onTogglePrivate: () => void;
  onOpenMemory: () => void;
  onOpenSettings: () => void;
  onExportVault: () => void;
}

export function CommandPalette({
  isOpen,
  onClose,
  conversations,
  onSelectConversation,
  onNewChat,
  onTogglePrivate,
  onOpenMemory,
  onOpenSettings,
  onExportVault,
}: CommandPaletteProps) {
  const [query, setQuery] = useState('');

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (isOpen) {
          onClose();
        } else {
          // Trigger open via parent
        }
      }
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const filteredChats = conversations.filter((c) =>
    c.title.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 p-4">
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-stone-900/40 dark:bg-stone-950/70 backdrop-blur-sm transition-opacity"
      />

      {/* Palette Modal */}
      <div className="relative w-full max-w-lg bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 rounded-2xl shadow-2xl overflow-hidden z-10 animate-in fade-in zoom-in-95 duration-150">
        <div className="p-3 border-b border-stone-200 dark:border-stone-800 flex items-center gap-2.5">
          <Search className="w-4 h-4 text-stone-400 dark:text-stone-500" />
          <input
            type="text"
            placeholder="Type a command or search chats..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full bg-transparent text-sm text-stone-900 dark:text-stone-100 placeholder:text-stone-400 focus:outline-none"
            autoFocus
          />
          <kbd className="text-[10px] font-mono text-stone-400 bg-stone-100 dark:bg-stone-800 px-1.5 py-0.5 rounded border border-stone-200 dark:border-stone-700">
            Esc
          </kbd>
        </div>

        <div className="max-h-80 overflow-y-auto p-2 space-y-3">
          {/* Quick Actions */}
          {!query && (
            <div className="space-y-1">
              <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-stone-400">
                Actions
              </div>
              <button
                onClick={() => {
                  onNewChat();
                  onClose();
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
              >
                <Plus className="w-3.5 h-3.5 text-stone-500" />
                <span>Start New Chat</span>
              </button>

              <button
                onClick={() => {
                  onTogglePrivate();
                  onClose();
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
              >
                <Shield className="w-3.5 h-3.5 text-stone-500" />
                <span>Toggle Private / Incognito Mode</span>
              </button>

              <button
                onClick={() => {
                  onOpenMemory();
                  onClose();
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
              >
                <Brain className="w-3.5 h-3.5 text-stone-500" />
                <span>Open Memory Knowledge Graph</span>
              </button>

              <button
                onClick={() => {
                  onOpenSettings();
                  onClose();
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
              >
                <Settings className="w-3.5 h-3.5 text-stone-500" />
                <span>Settings & Providers</span>
              </button>

              <button
                onClick={() => {
                  onExportVault();
                  onClose();
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
              >
                <Download className="w-3.5 h-3.5 text-stone-500" />
                <span>Export Obsidian Vault (.zip)</span>
              </button>
            </div>
          )}

          {/* Conversations */}
          <div className="space-y-1">
            <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-stone-400">
              Chats
            </div>
            {filteredChats.length === 0 ? (
              <div className="px-3 py-2 text-xs text-stone-400">No chats found.</div>
            ) : (
              filteredChats.map((c) => (
                <button
                  key={c.id}
                  onClick={() => {
                    onSelectConversation(c.id);
                    onClose();
                  }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors text-left"
                >
                  <MessageSquare className="w-3.5 h-3.5 text-stone-400 shrink-0" />
                  <span className="truncate">{c.title}</span>
                </button>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
