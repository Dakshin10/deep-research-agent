'use client';

import React, { useState, useEffect } from 'react';
import { Conversation } from '@/types/chat';
import { Search, X, MessageSquare, Trash2, Plus } from 'lucide-react';

interface HistoryDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  conversations: Conversation[];
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onDeleteConversation: (id: string) => void;
}

export function HistoryDrawer({
  isOpen,
  onClose,
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
}: HistoryDrawerProps) {
  const [searchTerm, setSearchTerm] = useState('');

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

  const filtered = conversations.filter((c) =>
    c.title.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-stone-900/30 dark:bg-stone-950/60 backdrop-blur-sm transition-opacity"
      />

      {/* Slide-over Drawer */}
      <div className="relative w-80 max-w-[85vw] h-full bg-stone-50 dark:bg-stone-900 border-r border-stone-200 dark:border-stone-800 shadow-2xl flex flex-col z-10 animate-in slide-in-from-left duration-200">
        {/* Top Header */}
        <div className="p-3.5 border-b border-stone-200 dark:border-stone-800 flex items-center justify-between">
          <div className="text-xs font-semibold text-stone-800 dark:text-stone-200 tracking-tight">
            Conversations
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => {
                onNewChat();
                onClose();
              }}
              className="p-1 text-stone-500 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100 rounded-md hover:bg-stone-200/60 dark:hover:bg-stone-800 transition-colors"
              title="New Chat"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={onClose}
              className="p-1 text-stone-500 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100 rounded-md hover:bg-stone-200/60 dark:hover:bg-stone-800 transition-colors"
              title="Close (Esc)"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Search */}
        <div className="p-2.5 border-b border-stone-200/70 dark:border-stone-800/70">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-stone-400 dark:text-stone-500" />
            <input
              type="text"
              placeholder="Search chats..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 bg-stone-100 dark:bg-stone-800/60 border border-stone-200 dark:border-stone-700/60 rounded-lg text-xs text-stone-900 dark:text-stone-100 placeholder:text-stone-400 focus:outline-none focus:border-stone-400 transition-colors"
              autoFocus
            />
          </div>
        </div>

        {/* Recents List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {filtered.length === 0 ? (
            <div className="text-center py-8 text-xs text-stone-400 dark:text-stone-500">
              No matching conversations.
            </div>
          ) : (
            filtered.map((c) => {
              const isActive = c.id === activeConversationId;
              return (
                <div
                  key={c.id}
                  onClick={() => {
                    onSelectConversation(c.id);
                    onClose();
                  }}
                  className={`group flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer text-xs transition-colors ${
                    isActive
                      ? 'bg-stone-200/70 dark:bg-stone-800 text-stone-900 dark:text-stone-100 font-medium'
                      : 'text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800/50 hover:text-stone-900 dark:hover:text-stone-200'
                  }`}
                >
                  <div className="flex items-center gap-2 truncate pr-1">
                    <MessageSquare className="w-3.5 h-3.5 shrink-0 text-stone-400 dark:text-stone-500" />
                    <span className="truncate">{c.title}</span>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteConversation(c.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-500 transition-opacity"
                    title="Delete conversation"
                  >
                    <Trash2 className="w-3 h-3 text-stone-400 hover:text-red-500" />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
