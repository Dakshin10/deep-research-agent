export type ChatRole = 'user' | 'assistant' | 'system' | 'tool';

export interface CitationItem {
  type: 'citation';
  turn_id: string;
  note_id: string;
  url: string;
  title: string;
  excerpt: string;
  location: string;
  text_fragment_url?: string;
  verified: boolean;
}

export interface ArtifactItem {
  type: 'artifact';
  turn_id: string;
  artifact_id: string;
  title: string;
  artifact_type: string; // 'report' | 'idea-cards' | 'chart' | 'deck' | 'table'
  mime_type: string;
  download_url?: string;
  preview_content?: string;
}

export interface CodeExecutionItem {
  type: 'code_execution';
  turn_id: string;
  execution_id: string;
  code: string;
  result: string;
  duration_ms: number;
  sandboxed: boolean;
}

export interface ResearchProgressItem {
  type: 'research_progress';
  turn_id: string;
  job_id: string;
  stage: string;
  active_shards: number;
  completed_shards: number;
  sources_found: Record<string, number>;
  budget_used_pct: number;
}

export interface ClarificationItem {
  type: 'clarification_request';
  turn_id: string;
  question: string;
  suggested_answers: string[];
}

export interface ApprovalItem {
  type: 'approval_request';
  turn_id: string;
  action_id: string;
  description: string;
  payload: Record<string, any>;
}

export interface MemoryUsedItem {
  type: 'memory_used';
  turn_id: string;
  memories: Array<{
    id: string;
    entity: string;
    fact: string;
    provenance?: string;
  }>;
}

export interface MessagePart {
  id: string;
  part_type: 'text' | 'tool_call' | 'code_execution' | 'citation' | 'artifact' | 'reasoning';
  content: string;
  metadata?: Record<string, any>;
}

export interface UIActionItem {
  type: 'ui_action';
  turn_id: string;
  action: string;
  payload: Record<string, any>;
}

export interface JobUpdateItem {
  type: 'job_update';
  turn_id: string;
  job_id: string;
  status: string;
  progress_pct: number;
  summary?: string;
  artifact_id?: string;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: ChatRole;
  content: string;
  reasoning?: string;
  citations: CitationItem[];
  artifacts: ArtifactItem[];
  code_executions: CodeExecutionItem[];
  research_progress?: ResearchProgressItem;
  clarification?: ClarificationItem;
  approval?: ApprovalItem;
  memories_used?: MemoryUsedItem['memories'];
  ui_actions?: UIActionItem[];
  isStreaming?: boolean;
}

export interface Conversation {
  id: string;
  tenant_id: string;
  title: string;
  active_branch_leaf_id?: string;
  updated_at: string;
  created_at: string;
  is_archived?: boolean;
}

