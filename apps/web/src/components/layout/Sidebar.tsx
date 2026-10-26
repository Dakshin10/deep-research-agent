'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { Conversation } from '@/types/chat';
import { Plus, MessageSquare, Trash2, Search, Brain, Shield, Zap, Sparkles } from 'lucide-react';

export function Sidebar({
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  modelRole,
  onChangeModelRole,
  incognito,
  onToggleIncognito,
}: {
  conversations: Conversation[];
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onDeleteConversation: (id: string) => void;
  modelRole: string;
  onChangeModelRole: (role: string) => void;
  incognito: boolean;
  onToggleIncognito: () => void;
}) {
  const [searchTerm, setSearchTerm] = useState('');

  const filtered = conversations.filter((c) =>
    c.title.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <aside className="w-64 border-r border-border bg-surface flex flex-col h-full select-none z-10">
      {/* Brand & New Chat */}
      <div className="p-3 border-b border-border space-y-2">
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-white flex items-center justify-center font-black text-black text-xs">
              ⚡
            </div>
            <span className="font-bold text-sm text-white tracking-tight">Deep Research</span>
          </div>
          <span className="text-[10px] font-mono bg-surface-raised border border-border px-1.5 py-0.5 rounded text-muted">
            v3.0
          </span>
        </div>

        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 py-2 px-3 bg-white hover:bg-white/90 text-black text-xs font-bold rounded-lg transition-all shadow"
        >
          <Plus className="w-3.5 h-3.5" /> New Chat
        </button>
      </div>

      {/* Search */}
      <div className="p-2 border-b border-border/50">
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-muted" />
          <input
            type="text"
            placeholder="Search conversations..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 bg-background border border-border rounded-lg text-xs text-foreground placeholder:text-muted focus:outline-none focus:border-white transition-colors"
          />
        </div>
      </div>

      {/* Conversation List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-dark">
          Recent Chats
        </div>
        {filtered.length === 0 ? (
          <div className="text-center py-6 text-xs text-muted">No conversations found.</div>
        ) : (
          filtered.map((c) => {
            const isActive = c.id === activeConversationId;
            return (
              <div
                key={c.id}
                onClick={() => onSelectConversation(c.id)}
                className={`group flex items-center justify-between px-2.5 py-2 rounded-lg cursor-pointer text-xs transition-colors ${
                  isActive
                    ? 'bg-surface-raised text-white border border-border font-medium'
                    : 'text-muted hover:bg-surface-raised/50 hover:text-foreground'
                }`}
              >
                <div className="flex items-center gap-2 truncate pr-1">
                  <MessageSquare className="w-3.5 h-3.5 shrink-0 text-muted" />
                  <span className="truncate">{c.title}</span>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteConversation(c.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 hover:text-white transition-opacity"
                  title="Delete chat"
                >
                  <Trash2 className="w-3 h-3 text-muted hover:text-white" />
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* Footer Navigation & Controls */}
      <div className="p-3 border-t border-border bg-surface-raised space-y-2">
        {/* Memory Graph Link */}
        <Link
          href="/memory"
          className="flex items-center justify-between p-2 rounded-lg bg-background border border-border hover:border-white text-xs text-white transition-colors"
        >
          <div className="flex items-center gap-2">
            <Brain className="w-4 h-4 text-white" />
            <span className="font-semibold">Memory Graph</span>
          </div>
          <span className="text-[10px] font-mono text-muted bg-surface px-1.5 py-0.5 rounded">
            L2/L3 Vault
          </span>
        </Link>

        {/* Incognito & Model Selector */}
        <div className="flex items-center justify-between pt-1">
          <button
            onClick={onToggleIncognito}
            className={`flex items-center gap-1.5 text-[11px] px-2 py-1 rounded transition-colors ${
              incognito ? 'bg-white text-black font-bold' : 'text-muted hover:text-white'
            }`}
            title="Incognito disables memory read/write"
          >
            <Shield className="w-3 h-3" />
            <span>Incognito</span>
          </button>

          <select
            value={modelRole}
            onChange={(e) => onChangeModelRole(e.target.value)}
            className="bg-background border border-border text-[11px] text-white px-2 py-1 rounded focus:outline-none"
          >
            <option value="fast">Fast (Llama 70B)</option>
            <option value="strong">Strong (Gemini 2.5)</option>
            <option value="code">Code (JS Sandboxed)</option>
          </select>
        </div>
      </div>
    </aside>
  );
}
