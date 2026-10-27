'use client';

import React, { useState, useEffect } from 'react';
import { X, Key, Cpu, Shield, Database, Trash2, Check, RefreshCw } from 'lucide-react';

interface SettingsOverlayProps {
  isOpen: boolean;
  onClose: () => void;
  defaultSection?: string;
}

export function SettingsOverlay({
  isOpen,
  onClose,
  defaultSection = 'general',
}: SettingsOverlayProps) {
  const [activeTab, setActiveTab] = useState(defaultSection);
  const [codeModeBackend, setCodeModeBackend] = useState('local');
  const [fastModel, setFastModel] = useState('llama-3.3-70b-versatile');
  const [strongModel, setStrongModel] = useState('gemini-2.5-flash');
  const [codeModel, setCodeModel] = useState('llama-3.3-70b-versatile');
  const [allowlist, setAllowlist] = useState('api.github.com, news.ycombinator.com, arxiv.org, devpost.com');
  const [savedToast, setSavedToast] = useState(false);

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

  const handleSave = () => {
    setSavedToast(true);
    setTimeout(() => setSavedToast(false), 2500);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-stone-900/40 dark:bg-stone-950/70 backdrop-blur-sm transition-opacity"
      />

      {/* Modal Card */}
      <div className="relative w-full max-w-2xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 rounded-2xl shadow-2xl flex flex-col max-h-[85vh] overflow-hidden z-10 animate-in fade-in zoom-in-95 duration-150">
        {/* Top Header */}
        <div className="p-4 border-b border-stone-200 dark:border-stone-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-sm text-stone-900 dark:text-stone-100">
              Settings & Preferences
            </span>
            <span className="text-[10px] font-mono bg-stone-100 dark:bg-stone-800 text-stone-500 px-2 py-0.5 rounded-full">
              Tenant: default_tenant
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-stone-200 dark:border-stone-800 px-4 gap-4 text-xs font-medium">
          <button
            onClick={() => setActiveTab('models')}
            className={`py-2.5 border-b-2 transition-colors ${
              activeTab === 'models'
                ? 'border-stone-900 dark:border-stone-100 text-stone-900 dark:text-stone-100'
                : 'border-transparent text-stone-500 hover:text-stone-700 dark:hover:text-stone-300'
            }`}
          >
            Model Roles
          </button>
          <button
            onClick={() => setActiveTab('codemode')}
            className={`py-2.5 border-b-2 transition-colors ${
              activeTab === 'codemode'
                ? 'border-stone-900 dark:border-stone-100 text-stone-900 dark:text-stone-100'
                : 'border-transparent text-stone-500 hover:text-stone-700 dark:hover:text-stone-300'
            }`}
          >
            Cloudflare Code Mode
          </button>
          <button
            onClick={() => setActiveTab('data')}
            className={`py-2.5 border-b-2 transition-colors ${
              activeTab === 'data'
                ? 'border-stone-900 dark:border-stone-100 text-stone-900 dark:text-stone-100'
                : 'border-transparent text-stone-500 hover:text-stone-700 dark:hover:text-stone-300'
            }`}
          >
            Data & Privacy
          </button>
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto p-5 text-xs text-stone-700 dark:text-stone-300 space-y-4">
          {activeTab === 'models' && (
            <div className="space-y-4">
              <div>
                <label className="block font-semibold mb-1">Fast Role (Quick answers, titles, memory recall)</label>
                <input
                  type="text"
                  value={fastModel}
                  onChange={(e) => setFastModel(e.target.value)}
                  className="w-full p-2 rounded-lg bg-stone-100 dark:bg-stone-800 border border-stone-200 dark:border-stone-700 font-mono text-xs focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-semibold mb-1">Strong Role (Deep research synthesis, report writing)</label>
                <input
                  type="text"
                  value={strongModel}
                  onChange={(e) => setStrongModel(e.target.value)}
                  className="w-full p-2 rounded-lg bg-stone-100 dark:bg-stone-800 border border-stone-200 dark:border-stone-700 font-mono text-xs focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-semibold mb-1">Code Role (JavaScript generation for Code Mode)</label>
                <input
                  type="text"
                  value={codeModel}
                  onChange={(e) => setCodeModel(e.target.value)}
                  className="w-full p-2 rounded-lg bg-stone-100 dark:bg-stone-800 border border-stone-200 dark:border-stone-700 font-mono text-xs focus:outline-none"
                />
              </div>
            </div>
          )}

          {activeTab === 'codemode' && (
            <div className="space-y-4">
              <div>
                <label className="block font-semibold mb-1">Sandbox Execution Backend</label>
                <select
                  value={codeModeBackend}
                  onChange={(e) => setCodeModeBackend(e.target.value)}
                  className="w-full p-2 rounded-lg bg-stone-100 dark:bg-stone-800 border border-stone-200 dark:border-stone-700 text-xs focus:outline-none"
                >
                  <option value="local">Local Isolated Sandbox (Subprocess / Deno / Node)</option>
                  <option value="cloudflare">Cloudflare Dynamic Workers (Production V8 Isolates)</option>
                </select>
              </div>

              <div>
                <label className="block font-semibold mb-1">Host Allowlist (Outside-sandbox Gate Enforcement)</label>
                <textarea
                  rows={2}
                  value={allowlist}
                  onChange={(e) => setAllowlist(e.target.value)}
                  className="w-full p-2 rounded-lg bg-stone-100 dark:bg-stone-800 border border-stone-200 dark:border-stone-700 font-mono text-xs focus:outline-none"
                />
                <p className="text-[10px] text-stone-500 mt-1">
                  Only network requests matching allowlisted hosts are permitted outside the isolate.
                </p>
              </div>
            </div>
          )}

          {activeTab === 'data' && (
            <div className="space-y-4">
              <div>
                <label className="block font-semibold mb-1 text-red-600 dark:text-red-400">
                  Data Purge & Privacy Actions
                </label>
                <p className="text-[11px] text-stone-500 mb-2">
                  Permanently delete your conversation history, temporal facts, and vault notes.
                </p>
                <button
                  type="button"
                  onClick={() => alert('To purge data, you can also type "forget everything" in chat.')}
                  className="px-3 py-1.5 rounded-lg bg-red-100 dark:bg-red-950/60 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-900 font-semibold hover:bg-red-200 transition-colors"
                >
                  Purge Tenant Memory & History
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-stone-200 dark:border-stone-800 flex items-center justify-between bg-stone-50/50 dark:bg-stone-900/50">
          <div className="text-[11px] text-stone-500">
            {savedToast && <span className="text-emerald-600 font-semibold">Settings saved.</span>}
          </div>
          <button
            onClick={handleSave}
            className="px-4 py-1.5 rounded-lg bg-stone-900 dark:bg-stone-100 text-stone-50 dark:text-stone-900 font-semibold text-xs hover:bg-stone-800 dark:hover:bg-stone-200 transition-colors"
          >
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
}
