/**
 * TypeScript Supervisor Gate for Cloudflare Worker isolates.
 */

export interface GateOptions {
  allowedHosts?: string[];
  maxCalls?: number;
  maxResponseBytes?: number;
}

const DEFAULT_ALLOWED_HOSTS = [
  'localhost',
  '127.0.0.1',
  'api.github.com',
  'hacker-news.firebaseio.com',
  'export.arxiv.org',
  'api.openalex.org',
  'en.wikipedia.org',
];

export class WorkerGate {
  private allowedHosts: Set<string>;
  private maxCalls: number;
  private maxResponseBytes: number;

  constructor(options: GateOptions = {}) {
    this.allowedHosts = new Set(options.allowedHosts || DEFAULT_ALLOWED_HOSTS);
    this.maxCalls = options.maxCalls || 20;
    this.maxResponseBytes = options.maxResponseBytes || 32768;
  }

  isHostAllowed(urlString: string): boolean {
    try {
      const url = new URL(urlString);
      return this.allowedHosts.has(url.hostname.toLowerCase());
    } catch {
      return false;
    }
  }

  checkMutation(method: string, isMutation: boolean, approvalToken?: string): { allowed: boolean; reason?: string } {
    if (!isMutation && ['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase())) {
      return { allowed: true };
    }
    if (!approvalToken || approvalToken.length < 8) {
      return {
        allowed: false,
        reason: 'Mutating operation blocked: valid user approval token required.',
      };
    }
    return { allowed: true };
  }

  truncate(content: string): { text: string; truncated: boolean } {
    const encoder = new TextEncoder();
    const bytes = encoder.encode(content);
    if (bytes.length > this.maxResponseBytes) {
      const decoder = new TextDecoder('utf-8');
      const truncated = decoder.decode(bytes.slice(0, this.maxResponseBytes));
      return {
        text: truncated + '\n\n[... Truncated: response exceeded 32KB limit ...]',
        truncated: true,
      };
    }
    return { text: content, truncated: false };
  }
}
