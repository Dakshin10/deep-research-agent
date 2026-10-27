'use client';

import { useState, useRef, useCallback } from 'react';
import {
  ChatMessage,
  CitationItem,
  ArtifactItem,
  CodeExecutionItem,
  ResearchProgressItem,
  ClarificationItem,
  ApprovalItem,
} from '@/types/chat';

export function useChatStream({
  onUIAction,
}: {
  onUIAction?: (action: string, payload: any) => void;
} = {}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [activeArtifact, setActiveArtifact] = useState<ArtifactItem | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const lastEventIdRef = useRef<string | null>(null);

  const stopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsStreaming(false);
      setMessages((prev) =>
        prev.map((msg, idx) =>
          idx === prev.length - 1 ? { ...msg, isStreaming: false } : msg
        )
      );
    }
  }, []);

  const sendMessage = useCallback(
    async ({
      conversationId,
      message,
      modelRole = 'fast',
      incognito = false,
      approvalToken,
    }: {
      conversationId: string;
      message: string;
      modelRole?: string;
      incognito?: boolean;
      approvalToken?: string;
    }) => {
      stopGeneration();

      const userMsgId = `user_${Date.now()}`;
      const asstMsgId = `asst_${Date.now()}`;

      const userMsg: ChatMessage = {
        id: userMsgId,
        conversation_id: conversationId,
        role: 'user',
        content: message,
        citations: [],
        artifacts: [],
        code_executions: [],
      };

      const asstMsg: ChatMessage = {
        id: asstMsgId,
        conversation_id: conversationId,
        role: 'assistant',
        content: '',
        citations: [],
        artifacts: [],
        code_executions: [],
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMsg, asstMsg]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const response = await fetch('/v1/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
            'X-Tenant-ID': 'default_tenant',
          },
          body: JSON.stringify({
            conversation_id: conversationId,
            message,
            model_role: modelRole,
            incognito,
            approval_token: approvalToken,
          }),
          signal: controller.signal,
        });

        if (!response.ok || !response.body) {
          throw new Error(`Chat error: ${response.statusText}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          buffer = buffer.replace(/\r\n/g, '\n');
          const lines = buffer.split('\n\n');
          buffer = lines.pop() || '';

          for (const chunk of lines) {
            if (!chunk.trim()) continue;

            let eventType = 'message';
            let eventData = '';
            let eventId = '';

            const partLines = chunk.split('\n');
            for (const line of partLines) {
              if (line.startsWith('id: ')) {
                eventId = line.replace('id: ', '').trim();
                lastEventIdRef.current = eventId;
              } else if (line.startsWith('event: ')) {
                eventType = line.replace('event: ', '').trim();
              } else if (line.startsWith('data: ')) {
                eventData = line.replace('data: ', '').trim();
              }
            }

            if (!eventData) continue;

            try {
              const payload = JSON.parse(eventData);

              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== asstMsgId) return m;

                  const updated = { ...m };

                  switch (eventType) {
                    case 'text_delta':
                      updated.content += payload.content || '';
                      break;

                    case 'reasoning_summary':
                      updated.reasoning = payload.summary || '';
                      break;

                    case 'research_progress':
                      updated.research_progress = payload;
                      break;

                    case 'code_execution':
                      updated.code_executions = [...(updated.code_executions || []), payload];
                      break;

                    case 'citation':
                      updated.citations = [...(updated.citations || []), payload];
                      break;

                    case 'artifact':
                      updated.artifacts = [...(updated.artifacts || []), payload];
                      setActiveArtifact(payload);
                      break;

                    case 'clarification_request':
                      updated.clarification = payload;
                      break;

                    case 'approval_request':
                      updated.approval = payload;
                      break;

                    case 'memory_used':
                      updated.memories_used = payload.memories || [];
                      break;

                    case 'ui_action':
                      updated.ui_actions = [...(updated.ui_actions || []), payload];
                      if (onUIAction) {
                        onUIAction(payload.action, payload.payload);
                      }
                      break;

                    case 'job_update':
                      if (payload.artifact_id && payload.summary) {
                        // Background job updated
                      }
                      break;

                    case 'done':
                      updated.isStreaming = false;
                      break;
                  }

                  return updated;
                })
              );
            } catch (e) {
              console.warn('Failed to parse SSE payload:', eventData);
            }
          }
        }
      } catch (err: any) {
        if (err.name !== 'AbortError') {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === asstMsgId
                ? {
                    ...m,
                    content: m.content + `\n\n*⚠️ Error: ${err.message || 'Stream interrupted.'}*`,
                    isStreaming: false,
                  }
                : m
            )
          );
        }
      } finally {
        setIsStreaming(false);
        abortControllerRef.current = null;
      }
    },
    [stopGeneration]
  );

  return {
    messages,
    setMessages,
    isStreaming,
    activeArtifact,
    setActiveArtifact,
    sendMessage,
    stopGeneration,
  };
}
