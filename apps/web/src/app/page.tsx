'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Header } from '@/components/layout/Header';
import { HistoryDrawer } from '@/components/layout/HistoryDrawer';
import { CommandPalette } from '@/components/layout/CommandPalette';
import { SettingsOverlay } from '@/components/layout/SettingsOverlay';
import { MemoryOverlay } from '@/components/memory/MemoryOverlay';
import { SourcesSheet } from '@/components/citations/SourcesSheet';
import { ArtifactDrawer } from '@/components/artifacts/ArtifactDrawer';
import { ChatArea } from '@/components/chat/ChatArea';
import { Composer } from '@/components/chat/Composer';
import { useChatStream } from '@/hooks/useChatStream';
import { Conversation, ArtifactItem } from '@/types/chat';

export default function SingleScreenAssistantPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [conversations, setConversations] = useState<Conversation[]>([
    {
      id: 'default_conv',
      title: 'New Inquiry',
      tenant_id: 'default_tenant',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      is_archived: false,
    },
  ]);
  const [activeConvId, setActiveConvId] = useState<string>('default_conv');
  const [incognito, setIncognito] = useState<boolean>(false);

  // Overlay states (synchronized with URL query params)
  const overlayParam = searchParams.get('overlay');
  const [historyOpen, setHistoryOpen] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(overlayParam === 'settings');
  const [memoryOpen, setMemoryOpen] = useState(overlayParam === 'memory');
  const [sourcesOpen, setSourcesOpen] = useState(overlayParam === 'sources');
  const [artifactDrawerOpen, setArtifactDrawerOpen] = useState(overlayParam === 'artifact');

  // Handle natural language UI actions from the agent
  const handleUIAction = useCallback((action: string, payload: any) => {
    switch (action) {
      case 'ui.open_memory_graph':
        setMemoryOpen(true);
        break;
      case 'ui.open_sources':
        setSourcesOpen(true);
        break;
      case 'ui.open_artifact':
        setArtifactDrawerOpen(true);
        break;
      case 'ui.open_settings':
        setSettingsOpen(true);
        break;
      case 'ui.set_private_mode':
        setIncognito(!!payload?.private);
        break;
      case 'ui.export_vault':
        handleExportVault();
        break;
      case 'ui.rename_chat':
        if (payload?.title) {
          setConversations((prev) =>
            prev.map((c) => (c.id === activeConvId ? { ...c, title: payload.title } : c))
          );
        }
        break;
    }
  }, [activeConvId]);

  const {
    messages,
    setMessages,
    isStreaming,
    activeArtifact,
    setActiveArtifact,
    sendMessage,
    stopGeneration,
  } = useChatStream({ onUIAction: handleUIAction });

  // Sync active artifact opening
  useEffect(() => {
    if (activeArtifact) {
      setArtifactDrawerOpen(true);
    }
  }, [activeArtifact]);

  // Load conversations on mount
  useEffect(() => {
    async function fetchConversations() {
      try {
        const res = await fetch('/v1/chat/conversations', {
          headers: { 'X-Tenant-ID': 'default_tenant' },
        });
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data) && data.length > 0) {
            setConversations(data);
            setActiveConvId(data[0].id);
          }
        }
      } catch (e) {
        // Fallback to local default conversation if offline
      }
    }
    fetchConversations();
  }, []);

  // Global keyboard shortcuts (Cmd/Ctrl+K, Esc)
  useEffect(() => {
    function handleGlobalKeys(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setCommandPaletteOpen((prev) => !prev);
      } else if (e.key === 'Escape') {
        setHistoryOpen(false);
        setCommandPaletteOpen(false);
        setSettingsOpen(false);
        setMemoryOpen(false);
        setSourcesOpen(false);
        setArtifactDrawerOpen(false);
      }
    }
    window.addEventListener('keydown', handleGlobalKeys);
    return () => window.removeEventListener('keydown', handleGlobalKeys);
  }, []);

  const handleNewChat = useCallback(() => {
    const newId = `conv_${Date.now()}`;
    const newConv: Conversation = {
      id: newId,
      title: 'New Inquiry',
      tenant_id: 'default_tenant',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      is_archived: false,
    };
    setConversations((prev) => [newConv, ...prev]);
    setActiveConvId(newId);
    setMessages([]);
    setActiveArtifact(null);
  }, [setMessages, setActiveArtifact]);

  const handleDeleteConversation = useCallback(
    (id: string) => {
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeConvId === id) {
        setMessages([]);
        setActiveArtifact(null);
        handleNewChat();
      }
    },
    [activeConvId, setMessages, setActiveArtifact, handleNewChat]
  );

  const handleSend = (text: string) => {
    let convId = activeConvId;
    if (!convId) {
      convId = `conv_${Date.now()}`;
      handleNewChat();
    }
    sendMessage({
      conversationId: convId,
      message: text,
      incognito,
    });
  };

  const handleExportVault = () => {
    // Trigger download of vault bundle
    const link = document.createElement('a');
    link.href = '/v1/memory/vault/export';
    link.download = 'vault.zip';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleClarifyReply = (answer: string) => {
    handleSend(answer);
  };

  const handleApprovalDecision = (approved: boolean, token?: string) => {
    if (approved && token) {
      sendMessage({
        conversationId: activeConvId,
        message: 'Proceed with approved action.',
        incognito,
        approvalToken: token,
      });
    } else {
      setMessages((prev) => [
        ...prev,
        {
          id: `sys_${Date.now()}`,
          conversation_id: activeConvId,
          role: 'assistant',
          content: '❌ Action cancelled.',
          citations: [],
          artifacts: [],
          code_executions: [],
        },
      ]);
    }
  };

  // Collect all citations across messages for the sources sheet
  const allCitations = messages.flatMap((m) => m.citations || []);
  const activeChatTitle = conversations.find((c) => c.id === activeConvId)?.title;

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-stone-50 dark:bg-stone-950 text-stone-900 dark:text-stone-100 font-sans">
      {/* 1. Minimal Header */}
      <Header
        title={activeChatTitle}
        incognito={incognito}
        onToggleIncognito={() => setIncognito((prev) => !prev)}
        onOpenHistory={() => setHistoryOpen(true)}
        onOpenMemory={() => setMemoryOpen(true)}
        onOpenSettings={() => setSettingsOpen(true)}
        onNewChat={handleNewChat}
      />

      {/* 2. Main Center Conversation Column */}
      <main className="flex-1 flex flex-col h-full overflow-hidden relative">
        <ChatArea
          messages={messages}
          onSendMessage={handleSend}
          onClarifyReply={handleClarifyReply}
          onApprovalDecision={handleApprovalDecision}
          onOpenArtifact={(art: ArtifactItem) => {
            setActiveArtifact(art);
            setArtifactDrawerOpen(true);
          }}
          onOpenSources={() => setSourcesOpen(true)}
        />

        {/* 3. Pinned Composer */}
        <Composer
          onSendMessage={handleSend}
          onStop={stopGeneration}
          isStreaming={isStreaming}
        />
      </main>

      {/* 4. Overlays (Rendered on same route) */}
      <HistoryDrawer
        isOpen={historyOpen}
        onClose={() => setHistoryOpen(false)}
        conversations={conversations}
        activeConversationId={activeConvId}
        onSelectConversation={(id) => {
          setActiveConvId(id);
          setMessages([]);
          setActiveArtifact(null);
        }}
        onNewChat={handleNewChat}
        onDeleteConversation={handleDeleteConversation}
      />

      <CommandPalette
        isOpen={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        conversations={conversations}
        onSelectConversation={(id) => {
          setActiveConvId(id);
          setMessages([]);
          setActiveArtifact(null);
        }}
        onNewChat={handleNewChat}
        onTogglePrivate={() => setIncognito((prev) => !prev)}
        onOpenMemory={() => setMemoryOpen(true)}
        onOpenSettings={() => setSettingsOpen(true)}
        onExportVault={handleExportVault}
      />

      <MemoryOverlay
        isOpen={memoryOpen}
        onClose={() => setMemoryOpen(false)}
        onExportVault={handleExportVault}
      />

      <SettingsOverlay
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />

      <SourcesSheet
        isOpen={sourcesOpen}
        onClose={() => setSourcesOpen(false)}
        citations={allCitations}
      />

      {artifactDrawerOpen && activeArtifact && (
        <ArtifactDrawer
          artifact={activeArtifact}
          citations={allCitations}
          onClose={() => setArtifactDrawerOpen(false)}
        />
      )}
    </div>
  );
}
