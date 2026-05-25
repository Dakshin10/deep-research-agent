from dotenv import load_dotenv
import gradio as gr
from langchain_groq import ChatGroq
from agents.responder import build_responder
from agents.revisor import build_revisor_chain
from tools.tavily_search import tavily_tool
from graph.workflow import build_graph
import urllib.parse

# -----------------------------------
# LOAD ENV VARIABLES
# -----------------------------------
load_dotenv()

# -----------------------------------
# INITIALIZE LLM
# -----------------------------------
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0
)

# -----------------------------------
# BUILD COMPONENTS
# -----------------------------------
responder = build_responder(llm)
revisor_chain = build_revisor_chain(llm)
app_graph = build_graph(
    responder,
    tavily_tool,
    revisor_chain
)

# -----------------------------------
# HELPER FUNCTIONS
# -----------------------------------

def format_search_results_html(search_results):
    if not search_results:
        return "<div style='text-align: center; padding: 20px; color: #a1a1aa;'>No search evidence available yet.</div>"
    
    html = '<div class="sources-container">'
    for idx, result in enumerate(search_results):
        if isinstance(result, dict):
            query = result.get("query", "Unknown Query")
            html += '<div class="query-section">'
            html += f'  <div class="query-header"><span class="query-icon">🔍</span> Query: <i>{query}</i></div>'
            html += '  <div class="results-grid">'
            
            results = result.get("results", [])
            if not results:
                html += '    <div style="grid-column: 1/-1; color: #a1a1aa; padding: 10px;">No results found.</div>'
            for item_idx, item in enumerate(results):
                title = item.get("title", "No Title")
                url = item.get("url", "#")
                content = item.get("content", "No Content")
                
                # Parse domain name for clean badge
                try:
                    parsed_url = urllib.parse.urlparse(url)
                    domain = parsed_url.netloc.replace("www.", "")
                except Exception:
                    domain = "Link"
                
                html += f'''
                <div class="search-card">
                    <div class="card-header">
                        <span class="badge">{domain}</span>
                        <a href="{url}" target="_blank" class="card-title-link">
                            {title} <span class="external-icon">↗</span>
                        </a>
                    </div>
                    <div class="card-content">
                        {content}
                    </div>
                    <div class="card-footer">
                        <a href="{url}" target="_blank" class="card-url">{url}</a>
                    </div>
                </div>
                '''
            html += '  </div>'  # results-grid
            html += '</div>'  # query-section
        else:
            html += f'<div class="query-section"><pre>{str(result)}</pre></div>'
            
    html += '</div>'
    return html


def format_reflection_html(reflection_obj):
    return f"""
    <div style="display: flex; flex-direction: column; gap: 16px; margin-top: 10px;">
        <div style="background: rgba(239, 68, 68, 0.08); border-left: 4px solid #ef4444; padding: 16px; border-radius: 6px;">
            <div style="color: #f87171; font-weight: bold; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; font-size: 14px;">
                <span>⚠️</span> Critique: Missing Information
            </div>
            <div style="color: #e5e7eb; font-size: 13.5px; line-height: 1.6;">
                {reflection_obj.missing}
            </div>
        </div>
        <div style="background: rgba(234, 179, 8, 0.08); border-left: 4px solid #eab308; padding: 16px; border-radius: 6px;">
            <div style="color: #facc15; font-weight: bold; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; font-size: 14px;">
                <span>🗑️</span> Critique: Unnecessary Information
            </div>
            <div style="color: #e5e7eb; font-size: 13.5px; line-height: 1.6;">
                {reflection_obj.unnecessary}
            </div>
        </div>
    </div>
    """


def run_agent(question):
    if not question.strip():
        return (
            "### Please enter a question to start the research process.",
            "",
            "<div style='color: #ef4444;'>No reflection available. Please ask a valid question.</div>",
            "",
            "<div style='color: #a1a1aa;'>No search evidence.</div>"
        )
        
    result = app_graph.invoke({
        "question": question
    })

    initial_response = result["initial_response"]

    reflection_html = format_reflection_html(initial_response.reflection)

    search_queries = "\n".join([
        f"- {query}"
        for query in initial_response.search_queries
    ])

    search_results = result["search_results"]
    formatted_search_results_html = format_search_results_html(search_results)
    final_answer = result["final_response"]

    return (
        final_answer,
        initial_response.answer,
        reflection_html,
        search_queries,
        formatted_search_results_html
    )


def clear_all():
    return "", "", "", "<div style='color: #a1a1aa;'>No reflection available.</div>", "", "<div style='color: #a1a1aa;'>No search evidence.</div>"

# -----------------------------------
# STYLING & CUSTOMIZATION
# -----------------------------------

custom_css = """
/* Body background & base styling */
.gradio-container {
    background: #09090b !important;
}

/* Sidebar & Content Panels styling */
.sidebar-panel {
    background: #111113 !important;
    border: 1px solid #1f1f23 !important;
    border-radius: 16px !important;
    padding: 20px !important;
}
.content-panel {
    background: #111113 !important;
    border: 1px solid #1f1f23 !important;
    border-radius: 16px !important;
    padding: 24px !important;
}

/* Premium Header styling */
.agent-header {
    background: linear-gradient(135deg, rgba(139, 92, 246, 0.1) 0%, rgba(99, 102, 241, 0.1) 100%);
    border: 1px solid rgba(139, 92, 246, 0.2);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
    text-align: center;
}
.agent-header h1 {
    margin: 0 !important;
    background: linear-gradient(90deg, #c084fc, #818cf8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800 !important;
    font-size: 24px !important;
}
.agent-header p {
    margin: 6px 0 0 0 !important;
    color: #9ca3af;
    font-size: 13px;
    line-height: 1.4;
}

/* Example button styling */
.example-btn {
    text-align: left !important;
    justify-content: flex-start !important;
    white-space: normal !important;
    font-size: 12px !important;
    padding: 10px 14px !important;
    margin-bottom: 8px !important;
    background: rgba(255, 255, 255, 0.02) !important;
    border: 1px solid rgba(255, 255, 255, 0.05) !important;
    color: #e5e7eb !important;
    transition: all 0.2s ease !important;
    cursor: pointer;
}
.example-btn:hover {
    background: rgba(139, 92, 246, 0.1) !important;
    border-color: rgba(139, 92, 246, 0.3) !important;
    transform: translateX(2px);
}

/* Search cards & evidence styling */
.sources-container {
    display: flex;
    flex-direction: column;
    gap: 24px;
    padding: 10px 0;
}
.query-section {
    background: rgba(30, 30, 46, 0.4);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
    padding: 18px;
}
.query-header {
    font-size: 14px;
    font-weight: 600;
    color: #c084fc;
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    padding-bottom: 8px;
}
.results-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 16px;
}
@media (min-width: 992px) {
    .results-grid {
        grid-template-columns: 1fr 1fr;
    }
}
.search-card {
    background: rgba(17, 17, 19, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 10px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 10px;
    transition: all 0.2s ease;
}
.search-card:hover {
    transform: translateY(-2px);
    border-color: rgba(139, 92, 246, 0.3);
    box-shadow: 0 4px 12px rgba(139, 92, 246, 0.08);
}
.card-header {
    display: flex;
    flex-direction: column;
    gap: 8px;
}
.badge {
    background: rgba(139, 92, 246, 0.15);
    color: #a78bfa;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 9999px;
    align-self: flex-start;
    border: 1px solid rgba(139, 92, 246, 0.2);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.card-title-link {
    color: #f3f4f6 !important;
    font-weight: 600;
    font-size: 14px;
    text-decoration: none !important;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    line-height: 1.4;
}
.card-title-link:hover {
    color: #a78bfa !important;
}
.external-icon {
    font-size: 11px;
    opacity: 0.7;
}
.card-content {
    font-size: 13px;
    color: #9ca3af;
    line-height: 1.5;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
}
.card-footer {
    border-top: 1px solid rgba(255, 255, 255, 0.05);
    padding-top: 8px;
    font-size: 11px;
    word-break: break-all;
}
.card-url {
    color: #6b7280 !important;
    text-decoration: none;
}
.card-url:hover {
    color: #a78bfa !important;
    text-decoration: underline !important;
}

/* Typography settings for output components */
.prose {
    font-size: 15px !important;
    line-height: 1.8 !important;
    color: #e5e7eb !important;
}
.prose h1, .prose h2, .prose h3 {
    color: #f3f4f6 !important;
    margin-top: 1.5rem !important;
    margin-bottom: 0.75rem !important;
}
"""

custom_theme = gr.themes.Default(
    primary_hue="violet",
    secondary_hue="indigo",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Outfit"), "ui-sans-serif", "system-ui", "sans-serif"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "ui-monospace", "SFMono-Regular", "monospace"]
).set(
    body_background_fill="#09090b",
    body_background_fill_dark="#09090b",
    block_background_fill="#111113",
    block_background_fill_dark="#111113",
    block_border_width="1px",
    block_border_color="#1f1f23",
    block_shadow="0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)",
    button_primary_background_fill="linear-gradient(90deg, #8b5cf6, #6366f1)",
    button_primary_background_fill_hover="linear-gradient(90deg, #7c3aed, #4f46e5)",
    button_primary_text_color="white",
)

# -----------------------------------
# GRADIO INTERFACE
# -----------------------------------

with gr.Blocks(title="Deep Research Agent") as demo:
    with gr.Row():
        # Left Panel (Sidebar for input & quick examples)
        with gr.Column(scale=1, elem_classes=["sidebar-panel"]):
            gr.HTML("""
            <div class="agent-header">
                <h1>🔥 Deep Research Agent</h1>
                <p>Reflection-based AI research workflow using LangGraph, Groq, and Tavily</p>
            </div>
            """)
            
            question_input = gr.Textbox(
                lines=5,
                placeholder="Ask a deep research question...",
                label="Research Inquiry"
            )
            
            with gr.Row():
                submit_btn = gr.Button("Research", variant="primary")
                clear_btn = gr.Button("Clear", variant="secondary")
            
            gr.Markdown("### 💡 Quick Examples")
            
            example_questions = [
                "Critically evaluate the current commercialization hurdles of Room Temperature Superconductors.",
                "Compare solid-state batteries vs lithium-ion batteries in terms of energy density, cost, and safety.",
                "Detail the architectural evolution of large language models from GPT-3 to Llama 3.3."
            ]
            
            for ex in example_questions:
                ex_btn = gr.Button(ex, variant="secondary", size="sm", elem_classes=["example-btn"])
                ex_btn.click(fn=lambda val=ex: val, inputs=[], outputs=question_input)
                
        # Right Panel (Workspace for displaying results)
        with gr.Column(scale=2, elem_classes=["content-panel"]):
            with gr.Tabs() as tabs:
                with gr.Tab("🏆 Research Report"):
                    gr.Markdown("### 🚀 Final Revised Answer")
                    final_output = gr.Markdown()
                    
                with gr.Tab("🔍 Sources & Evidence"):
                    gr.Markdown("### 🌐 Gathered Web Evidence")
                    search_output = gr.HTML(value="<div style='color: #a1a1aa; padding: 10px;'>Run research to populate sources.</div>")
                    
                with gr.Tab("🧠 Process & Reflection"):
                    gr.Markdown("### 🕵️‍♂️ Under-the-hood Execution Steps")
                    
                    with gr.Accordion("📝 Step 1: Initial Answer Draft", open=True):
                        initial_output = gr.Markdown()
                        
                    with gr.Accordion("🧐 Step 2: Critical Self-Reflection", open=False):
                        reflection_output = gr.HTML(value="<div style='color: #a1a1aa;'>No reflection available.</div>")
                        
                    with gr.Accordion("🏷️ Step 3: Targeted Search Queries", open=False):
                        query_output = gr.Markdown()

    # Event handlers
    submit_btn.click(
        fn=run_agent,
        inputs=question_input,
        outputs=[
            final_output,
            initial_output,
            reflection_output,
            query_output,
            search_output
        ]
    )
    
    clear_btn.click(
        fn=clear_all,
        inputs=[],
        outputs=[
            question_input,
            final_output,
            initial_output,
            reflection_output,
            query_output,
            search_output
        ]
    )

# -----------------------------------
# LAUNCH
# -----------------------------------
demo.launch(theme=custom_theme, css=custom_css)