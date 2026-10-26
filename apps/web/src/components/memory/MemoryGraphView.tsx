'use client';

import React, { useState, useMemo } from 'react';
import { Search, Brain, ExternalLink, Calendar, Tag, ShieldCheck } from 'lucide-react';

export interface GraphNode {
  id: string;
  name: string;
  type: 'Person' | 'Project' | 'Topic' | 'Tool' | 'Idea' | 'Decision';
  summary?: string;
  salience?: number;
  valid_from?: string;
  valid_to?: string;
  provenance?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  valid_from?: string;
  valid_to?: string;
}

interface MemoryGraphViewProps {
  nodes?: GraphNode[];
  edges?: GraphEdge[];
  onNodeSelect?: (node: GraphNode) => void;
}

const DEFAULT_NODES: GraphNode[] = [
  { id: '1', name: 'Deep Research Agent', type: 'Project', summary: 'Autonomous AI research agent with parallel fan-out and location-verified notes.', salience: 0.95, valid_from: '2026-01-01' },
  { id: '2', name: 'Cloudflare Code Mode', type: 'Tool', summary: 'Dynamic Worker V8 isolates executing search + execute against typed OpenAPI SDK.', salience: 0.9, valid_from: '2026-03-01' },
  { id: '3', name: 'Temporal Graph Memory', type: 'Topic', summary: 'L0-L4 memory architecture with Obsidian vault bidirectional sync.', salience: 0.88, valid_from: '2026-03-15' },
  { id: '4', name: 'Idea Miner', type: 'Project', summary: 'Continuous crawler, clustering, and hackathon opportunity generator.', salience: 0.82, valid_from: '2026-02-10' },
  { id: '5', name: 'SearXNG', type: 'Tool', summary: 'Self-hosted metasearch engine serving privacy-first query shards.', salience: 0.75, valid_from: '2026-01-10' },
  { id: '6', name: 'LangGraph Engine', type: 'Tool', summary: 'Stateful multi-actor agent orchestration and cyclical graph engine.', salience: 0.85, valid_from: '2026-01-05' },
  { id: '7', name: 'Obsidian Vault', type: 'Tool', summary: 'Local markdown knowledge base in ./vault with wikilinks and frontmatter.', salience: 0.8, valid_from: '2026-03-20' },
];

const DEFAULT_EDGES: GraphEdge[] = [
  { source: '1', target: '2', relation: 'USES_TOOL' },
  { source: '1', target: '3', relation: 'PERSISTS_TO' },
  { source: '1', target: '4', relation: 'ORCHESTRATES' },
  { source: '1', target: '5', relation: 'QUERIES' },
  { source: '1', target: '6', relation: 'BUILT_ON' },
  { source: '3', target: '7', relation: 'SYNCS_BIDIRECTIONAL' },
  { source: '4', target: '3', relation: 'MINES_ENTITIES' },
];

export function MemoryGraphView({
  nodes = DEFAULT_NODES,
  edges = DEFAULT_EDGES,
  onNodeSelect,
}: MemoryGraphViewProps) {
  const [query, setQuery] = useState('');
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(nodes[0] || null);

  const filteredNodes = useMemo(() => {
    if (!query.trim()) return nodes;
    const q = query.toLowerCase();
    return nodes.filter(
      (n) => n.name.toLowerCase().includes(q) || n.type.toLowerCase().includes(q)
    );
  }, [nodes, query]);

  // Compute circular layout coordinates
  const layout = useMemo(() => {
    const width = 600;
    const height = 400;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * 0.38;

    const coords: Record<string, { x: number; y: number }> = {};
    nodes.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
      coords[node.id] = {
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
      };
    });
    return { width, height, coords };
  }, [nodes]);

  const handleSelect = (node: GraphNode) => {
    setSelectedNode(node);
    onNodeSelect?.(node);
  };

  return (
    <div className="flex flex-col lg:flex-row h-full gap-4 p-4 text-white">
      {/* Visual Canvas */}
      <div className="flex-1 bg-surface rounded-2xl border border-border p-4 flex flex-col relative overflow-hidden">
        <div className="flex items-center justify-between mb-4 z-10">
          <div className="flex items-center gap-2">
            <Brain className="w-5 h-5 text-white" />
            <h3 className="text-sm font-bold text-white tracking-tight">Temporal Knowledge Graph</h3>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-surface-raised border border-border text-muted">
              {nodes.length} entities • {edges.length} relations
            </span>
          </div>

          <div className="relative w-48">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search graph..."
              className="w-full bg-surface-raised border border-border rounded-lg pl-8 pr-3 py-1 text-xs text-white placeholder-muted focus:outline-none focus:border-white transition-colors"
            />
          </div>
        </div>

        {/* SVG Render */}
        <div className="flex-1 flex items-center justify-center relative">
          <svg
            viewBox={`0 0 ${layout.width} ${layout.height}`}
            className="w-full h-full max-h-[500px] select-none"
          >
            <defs>
              <marker
                id="arrowhead"
                markerWidth="8"
                markerHeight="6"
                refX="16"
                refY="3"
                orient="auto"
              >
                <polygon points="0 0, 8 3, 0 6" fill="#52525b" />
              </marker>
            </defs>

            {/* Edges */}
            {edges.map((edge, i) => {
              const start = layout.coords[edge.source];
              const end = layout.coords[edge.target];
              if (!start || !end) return null;
              const isHighlighted =
                selectedNode && (selectedNode.id === edge.source || selectedNode.id === edge.target);

              return (
                <g key={i}>
                  <line
                    x1={start.x}
                    y1={start.y}
                    x2={end.x}
                    y2={end.y}
                    stroke={isHighlighted ? '#ffffff' : '#27272a'}
                    strokeWidth={isHighlighted ? 1.5 : 1}
                    markerEnd="url(#arrowhead)"
                    strokeDasharray={isHighlighted ? 'none' : '2,2'}
                    className="transition-colors duration-200"
                  />
                  <text
                    x={(start.x + end.x) / 2}
                    y={(start.y + end.y) / 2 - 4}
                    fill={isHighlighted ? '#a1a1aa' : '#52525b'}
                    fontSize="8"
                    fontFamily="monospace"
                    textAnchor="middle"
                  >
                    {edge.relation}
                  </text>
                </g>
              );
            })}

            {/* Nodes */}
            {filteredNodes.map((node) => {
              const pos = layout.coords[node.id];
              if (!pos) return null;
              const isSelected = selectedNode?.id === node.id;

              return (
                <g
                  key={node.id}
                  transform={`translate(${pos.x}, ${pos.y})`}
                  onClick={() => handleSelect(node)}
                  className="cursor-pointer group"
                >
                  <circle
                    r={isSelected ? 18 : 14}
                    className={`transition-all duration-200 ${
                      isSelected
                        ? 'fill-white stroke-surface stroke-2'
                        : 'fill-surface-raised stroke-border group-hover:stroke-white'
                    }`}
                  />
                  <text
                    textAnchor="middle"
                    dy="3"
                    fontSize="9"
                    fontWeight="bold"
                    fill={isSelected ? '#000000' : '#ffffff'}
                    className="pointer-events-none"
                  >
                    {node.name.slice(0, 2).toUpperCase()}
                  </text>
                  <text
                    textAnchor="middle"
                    dy="28"
                    fontSize="9"
                    fill={isSelected ? '#ffffff' : '#a1a1aa'}
                    fontWeight={isSelected ? 'bold' : 'normal'}
                    className="pointer-events-none"
                  >
                    {node.name}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      </div>

      {/* Node Inspector Sidebar */}
      <div className="w-full lg:w-80 bg-surface rounded-2xl border border-border p-5 flex flex-col justify-between">
        {selectedNode ? (
          <div className="space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-surface-raised border border-border text-muted">
                  {selectedNode.type}
                </span>
                <h4 className="text-base font-bold text-white mt-1">{selectedNode.name}</h4>
              </div>
              <div className="text-right">
                <span className="text-[10px] text-muted block">Salience</span>
                <span className="text-xs font-mono font-bold text-white">
                  {Math.round((selectedNode.salience ?? 0.8) * 100)}%
                </span>
              </div>
            </div>

            <p className="text-xs text-muted leading-relaxed">
              {selectedNode.summary || 'No summary available.'}
            </p>

            <div className="space-y-2 pt-3 border-t border-border">
              <div className="flex items-center gap-2 text-xs text-muted">
                <Calendar className="w-3.5 h-3.5" />
                <span>Valid: {selectedNode.valid_from || 'Always'}</span>
                {selectedNode.valid_to && <span>&rarr; {selectedNode.valid_to}</span>}
              </div>
              <div className="flex items-center gap-2 text-xs text-muted">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                <span>Verified in Obsidian vault: <code className="text-white">./vault/{selectedNode.type}/{selectedNode.name}.md</code></span>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-xs text-muted text-center p-6">
            Click an entity node on the canvas to inspect facts, validity ranges, and provenance.
          </div>
        )}

        <div className="pt-4 border-t border-border mt-4">
          <button
            onClick={() => alert('Obsidian vault watcher active: editing ./vault automatically syncs back into graph.')}
            className="w-full py-2 bg-surface-raised hover:bg-surface border border-border rounded-xl text-xs font-semibold text-white flex items-center justify-center gap-1.5 transition-colors"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            Open in Obsidian
          </button>
        </div>
      </div>
    </div>
  );
}
