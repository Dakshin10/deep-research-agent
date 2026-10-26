'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Sidebar } from '@/components/layout/Sidebar';
import { ChatArea } from '@/components/chat/ChatArea';
import { Composer } from '@/components/chat/Composer';
import { ArtifactDrawer } from '@/components/artifacts/ArtifactDrawer';
import { useChatStream } from '@/hooks/useChatStream';
import { Conversation } from '@/types/chat';
import { PanelRight, RefreshCw, Trash2 } from 'lucide-react';

export default function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([
    {
      id: 'default_conv',
      title: 'New Research & Idea Session',
      tenant_id: 'default_tenant',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      is_archived: false,
    },
  ]);
  const [activeConvId, setActiveConvId] = useState<string>('default_conv');
  const [modelRole, setModelRole] = useState<string>('fast');
  const [incognito, setIncognito] = useState<boolean>(false);
  const [drawerOpen, setDrawerOpen] = useState<boolean>(true);

  const {
    messages,
    setMessages,
    isStreaming,
    activeArtifact,
    setActiveArtifact,
    sendMessage,
    stopGeneration,
  } = useChatStream();

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
        // Fallback to local default conversation if offline/mock
      }
    }
    fetchConversations();
  }, []);

  const handleNewChat = useCallback(() => {
    const newId = `conv_${Date.now()}`;
    const newConv: Conversation = {
      id: newId,
      title: 'New Conversation',
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
        setActiveConvId('');
      }
    },
    [activeConvId, setMessages, setActiveArtifact]
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
      modelRole,
      incognito,
    });
  };

  const handleClarifyReply = (answer: string) => {
    handleSend(answer);
  };

  const handleApprovalDecision = (approved: boolean, token?: string) => {
    if (approved && token) {
      sendMessage({
        conversationId: activeConvId,
        message: 'Proceed with approved action.',
        modelRole,
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
          content: '❌ Action was rejected by user.',
          citations: [],
          artifacts: [],
          code_executions: [],
        },
      ]);
    }
  };

  // Collect all citations from the latest assistant message
  const lastAsstMsg = [...messages].reverse().find((m) => m.role === 'assistant');
  const currentCitations = lastAsstMsg?.citations || [];

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <Sidebar
        conversations={conversations}
        activeConversationId={activeConvId}
        onSelectConversation={(id) => {
          setActiveConvId(id);
          setMessages([]);
          setActiveArtifact(null);
        }}
        onNewChat={handleNewChat}
        onDeleteConversation={handleDeleteConversation}
        modelRole={modelRole}
        onChangeModelRole={setModelRole}
        incognito={incognito}
        onToggleIncognito={() => setIncognito((prev) => !prev)}
      />

      {/* Main Center Area */}
      <main className="flex-1 flex flex-col h-full overflow-hidden relative">
        {/* Top Navbar */}
        <header className="h-12 border-b border-border bg-surface px-4 flex items-center justify-between select-none">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-white tracking-tight truncate max-w-xs md:max-w-md">
              {conversations.find((c) => c.id === activeConvId)?.title || 'Unified Assistant'}
            </span>
            {incognito && (
              <span className="text-[10px] bg-white text-black font-bold px-1.5 py-0.5 rounded">
                Incognito
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {(activeArtifact || currentCitations.length > 0) && (
              <button
                onClick={() => setDrawerOpen((prev) => !prev)}
                className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border transition-colors ${
                  drawerOpen
                    ? 'bg-white text-black font-bold border-white'
                    : 'bg-surface-raised text-muted border-border hover:text-white'
                }`}
                title="Toggle artifact and citation drawer"
              >
                <PanelRight className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Side Panel</span>
              </button>
            )}
          </div>
        </header>

        {/* Chat Area */}
        <ChatArea
          messages={messages}
          onClarifyReply={handleClarifyReply}
          onApprovalDecision={handleApprovalDecision}
        />

        {/* Composer */}
        <Composer
          onSendMessage={handleSend}
          onStop={stopGeneration}
          isStreaming={isStreaming}
        />
      </main>

      {/* Right Drawer for Artifacts and Sources */}
      {drawerOpen && (
        <ArtifactDrawer
          artifact={activeArtifact}
          citations={currentCitations}
          onClose={() => setDrawerOpen(false)}
        />
      )}
    </div>
  );
}
