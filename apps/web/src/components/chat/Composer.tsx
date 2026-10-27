'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { ArrowUp, Square, Plus, FileText, X, Image as ImageIcon } from 'lucide-react';

interface Attachment {
  id: string;
  name: string;
  size: number;
  type: string;
}

interface ComposerProps {
  onSendMessage: (msg: string, attachments?: Attachment[]) => void;
  onStop: () => void;
  isStreaming: boolean;
  placeholder?: string;
}

export function Composer({
  onSendMessage,
  onStop,
  isStreaming,
  placeholder = 'Ask a question, request deep research, or analyze a topic...',
}: ComposerProps) {
  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-resize textarea up to 200px
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if ((!input.trim() && attachments.length === 0) || isStreaming) return;
    onSendMessage(input.trim(), attachments);
    setInput('');
    setAttachments([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    } else if (e.key === 'Escape' && isStreaming) {
      e.preventDefault();
      onStop();
    }
  };

  // Auto-convert very long pasted text (>800 chars) into an attachment chip
  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const text = e.clipboardData.getData('text');
    if (text && text.length > 800) {
      e.preventDefault();
      const chip: Attachment = {
        id: `att_${Date.now()}`,
        name: `pasted-text-${Date.now().toString().slice(-4)}.txt`,
        size: text.length,
        type: 'text/plain',
      };
      setAttachments((prev) => [...prev, chip]);
    }

    // Handle pasted files (like screenshots)
    if (e.clipboardData.files && e.clipboardData.files.length > 0) {
      const file = e.clipboardData.files[0];
      const chip: Attachment = {
        id: `att_${Date.now()}`,
        name: file.name || 'Pasted Image',
        size: file.size,
        type: file.type,
      };
      setAttachments((prev) => [...prev, chip]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const files = Array.from(e.target.files);
      const newChips: Attachment[] = files.map((f) => ({
        id: `att_${Date.now()}_${Math.random()}`,
        name: f.name,
        size: f.size,
        type: f.type,
      }));
      setAttachments((prev) => [...prev, ...newChips]);
    }
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  };

  // Drag and drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const files = Array.from(e.dataTransfer.files);
      const newChips: Attachment[] = files.map((f) => ({
        id: `att_${Date.now()}_${Math.random()}`,
        name: f.name,
        size: f.size,
        type: f.type,
      }));
      setAttachments((prev) => [...prev, ...newChips]);
    }
  };

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className="w-full max-w-[720px] mx-auto px-4 pb-4 select-none relative"
    >
      {/* Hidden File Input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={handleFileChange}
      />

      {/* Drag Overlay */}
      {isDragging && (
        <div className="absolute inset-0 bg-stone-100/90 dark:bg-stone-800/90 border-2 border-dashed border-stone-400 dark:border-stone-500 rounded-2xl flex items-center justify-center text-xs text-stone-700 dark:text-stone-300 z-10">
          Drop files to attach
        </div>
      )}

      {/* Composer Container */}
      <div className="relative border border-stone-300 dark:border-stone-700/80 bg-white dark:bg-stone-900 rounded-2xl shadow-sm focus-within:border-stone-400 dark:focus-within:border-stone-500 transition-all overflow-hidden">
        {/* Attachment Chips */}
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-1.5 p-2.5 pb-1 border-b border-stone-100 dark:border-stone-800">
            {attachments.map((att) => (
              <span
                key={att.id}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-stone-100 dark:bg-stone-800 text-[11px] text-stone-700 dark:text-stone-300 font-mono"
              >
                {att.type.startsWith('image/') ? (
                  <ImageIcon className="w-3 h-3 text-stone-500" />
                ) : (
                  <FileText className="w-3 h-3 text-stone-500" />
                )}
                <span className="truncate max-w-[140px]">{att.name}</span>
                <button
                  type="button"
                  onClick={() => removeAttachment(att.id)}
                  className="hover:text-red-500 p-0.5"
                  title="Remove attachment"
                >
                  <X className="w-2.5 h-2.5" />
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Text Input Area */}
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={placeholder}
          rows={1}
          className="w-full pl-4 pr-12 pt-3 pb-2.5 bg-transparent text-sm text-stone-900 dark:text-stone-100 placeholder:text-stone-400 focus:outline-none resize-none leading-relaxed font-sans"
        />

        {/* Controls Footer */}
        <div className="flex items-center justify-between px-3 pb-2.5 pt-0.5">
          {/* Attach (+) Button */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="p-1.5 text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
            title="Attach file or document (+)"
            aria-label="Attach file"
          >
            <Plus className="w-4 h-4" />
          </button>

          {/* Send / Stop Button */}
          <div>
            {isStreaming ? (
              <button
                type="button"
                onClick={onStop}
                className="p-1.5 bg-stone-900 dark:bg-stone-100 text-stone-50 dark:text-stone-900 rounded-xl hover:opacity-90 transition-all shadow-sm"
                title="Stop generation (Esc)"
                aria-label="Stop generation"
              >
                <Square className="w-3.5 h-3.5 fill-current" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!input.trim() && attachments.length === 0}
                className={`p-1.5 rounded-xl transition-all shadow-sm ${
                  input.trim() || attachments.length > 0
                    ? 'bg-stone-900 dark:bg-stone-100 text-stone-50 dark:text-stone-900 hover:opacity-90'
                    : 'bg-stone-200 dark:bg-stone-800 text-stone-400 dark:text-stone-600 cursor-not-allowed'
                }`}
                title="Send message (Enter)"
                aria-label="Send message"
              >
                <ArrowUp className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
