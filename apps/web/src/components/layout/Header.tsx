'use client';

import React, { useState, useRef, useEffect } from 'react';
import { History, Shield, ShieldAlert, MoreHorizontal, Settings, Brain, Sparkles, Plus } from 'lucide-react';

interface HeaderProps {
  title?: string;
  incognito: boolean;
  onToggleIncognito: () => void;
  onOpenHistory: () => void;
  onOpenMemory: () => void;
  onOpenSettings: () => void;
  onNewChat: () => void;
}

export function Header({
  title,
  incognito,
  onToggleIncognito,
  onOpenHistory,
  onOpenMemory,
  onOpenSettings,
  onNewChat,
}: HeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <header className="h-13 w-full border-b border-stone-200/80 dark:border-stone-800/80 bg-stone-50/90 dark:bg-stone-900/90 backdrop-blur-md px-4 flex items-center justify-between select-none z-20 sticky top-0 transition-colors">
      {/* Left: History Toggle & Brand */}
      <div className="flex items-center gap-3">
        <button
          onClick={onOpenHistory}
          className="p-1.5 text-stone-500 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100 rounded-lg hover:bg-stone-200/60 dark:hover:bg-stone-800 transition-colors"
          title="Open Conversation History (Cmd+K)"
          aria-label="History"
        >
          <History className="w-4 h-4" />
        </button>

        <button
          onClick={onNewChat}
          className="p-1.5 text-stone-500 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100 rounded-lg hover:bg-stone-200/60 dark:hover:bg-stone-800 transition-colors"
          title="Start New Chat"
          aria-label="New Chat"
        >
          <Plus className="w-4 h-4" />
        </button>

        {/* Minimal Identity Logo */}
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-md bg-stone-900 dark:bg-stone-100 text-stone-50 dark:text-stone-900 flex items-center justify-center font-bold text-[11px] shadow-sm">
            Æ
          </div>
          <span className="font-semibold text-xs tracking-tight text-stone-900 dark:text-stone-100 font-sans">
            Aether
          </span>
        </div>
      </div>

      {/* Center: Conversation Title (Subtle) */}
      <div className="hidden sm:block text-xs text-stone-600 dark:text-stone-400 font-medium truncate max-w-xs md:max-w-md text-center">
        {title || 'New inquiry'}
      </div>

      {/* Right: Private Mode & Context Menu */}
      <div className="flex items-center gap-2">
        {/* Private / Incognito Toggle */}
        <button
          onClick={onToggleIncognito}
          className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full transition-all border ${
            incognito
              ? 'bg-amber-100 dark:bg-amber-950/60 text-amber-900 dark:text-amber-200 border-amber-300 dark:border-amber-800 font-medium'
              : 'text-stone-600 hover:text-stone-900 dark:text-stone-300 dark:hover:text-stone-100 border-stone-200/60 dark:border-stone-800 hover:bg-stone-200/60 dark:hover:bg-stone-800'
          }`}
          title={incognito ? 'Private mode is ON (no memory recorded)' : 'Turn on Private Mode'}
        >
          {incognito ? <ShieldAlert className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" /> : <Shield className="w-3.5 h-3.5" />}
          <span className="hidden md:inline text-[11px] font-medium">{incognito ? 'Private' : 'Normal'}</span>
        </button>

        {/* '...' Overflow Menu */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen((prev) => !prev)}
            className="p-1.5 text-stone-500 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100 rounded-lg hover:bg-stone-200/60 dark:hover:bg-stone-800 transition-colors"
            title="More Options"
            aria-label="Options"
          >
            <MoreHorizontal className="w-4 h-4" />
          </button>

          {menuOpen && (
            <div className="absolute right-0 mt-1.5 w-44 rounded-xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 shadow-xl py-1 text-xs text-stone-700 dark:text-stone-300 z-50 animate-in fade-in zoom-in-95">
              <button
                onClick={() => {
                  setMenuOpen(false);
                  onOpenMemory();
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-stone-100 dark:hover:bg-stone-800 text-left transition-colors"
              >
                <Brain className="w-3.5 h-3.5 text-stone-500" />
                <span>Memory Graph</span>
              </button>

              <button
                onClick={() => {
                  setMenuOpen(false);
                  onOpenSettings();
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-stone-100 dark:hover:bg-stone-800 text-left transition-colors"
              >
                <Settings className="w-3.5 h-3.5 text-stone-500" />
                <span>Settings</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
