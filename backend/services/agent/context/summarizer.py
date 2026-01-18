"""
Conversation Summarizer for AI Agent

Uses LLM to summarize conversation history 
to reduce token usage while preserving context.
"""

from typing import List, Optional
from langchain_core.messages import HumanMessage, SystemMessage

from ..models.router import ModelRouter
from ..logger import agent_logger


SUMMARIZATION_PROMPT = """Summarize the following conversation in 2-3 sentences.
Focus on: main topics discussed, code/files involved, and key decisions made.
Be concise and factual.

Conversation:
{conversation}

Summary:"""


class ConversationSummarizer:
    """
    Summarizes conversation history using a fast local model.
    """
    
    def __init__(self):
        self.model_router = ModelRouter()
    
    async def summarize(self, messages: List[dict]) -> str:
        """
        Summarize a list of messages.
        
        Args:
            messages: List of {"role": str, "content": str}
            
        Returns:
            Summarized text
        """
        if not messages:
            return ""
        
        # Build conversation text
        conversation = "\n".join([
            f"{m['role'].upper()}: {m['content'][:300]}"  # Truncate long messages
            for m in messages
        ])
        
        prompt = SUMMARIZATION_PROMPT.format(conversation=conversation)
        
        # Use fast local model (Ollama qwen2.5-coder:7b)
        agent_logger.debug("Summarizing conversation with local model...")
        model = self.model_router.get_model_for_provider("ollama", "qwen2.5-coder:7b")
        
        if model is None:
            agent_logger.warning("No model available for summarization, using fallback")
            return self._fallback_summarize(messages)
        
        try:
            response = await model.ainvoke([HumanMessage(content=prompt)])
            summary = response.content.strip()
            agent_logger.info(f"Summarized {len(messages)} messages → {len(summary)} chars")
            return summary
            
        except Exception as e:
            agent_logger.error(f"Summarization failed: {e}")
            return self._fallback_summarize(messages)
    
    def _fallback_summarize(self, messages: List[dict]) -> str:
        """Simple fallback summarization without LLM."""
        user_msgs = [m for m in messages if m.get('role') == 'user']
        
        if not user_msgs:
            return ""
        
        # Extract key topics
        topics = set()
        for msg in user_msgs:
            content = msg.get('content', '').lower()
            
            # Detect topics by keywords
            if any(kw in content for kw in ['create', 'generate', 'write']):
                topics.add('code generation')
            if any(kw in content for kw in ['fix', 'error', 'bug']):
                topics.add('debugging')
            if any(kw in content for kw in ['explain', 'what']):
                topics.add('explanation')
            if any(kw in content for kw in ['test', 'pytest']):
                topics.add('testing')
        
        return f"Discussed: {', '.join(topics) or 'general questions'} ({len(messages)} messages)"
    
    def estimate_tokens(self, text: str) -> int:
        """
        Rough token estimation.
        
        Rule of thumb: ~4 characters per token
        """
        return len(text) // 4


# Singleton instance
_summarizer: Optional[ConversationSummarizer] = None


def get_summarizer() -> ConversationSummarizer:
    """Get or create summarizer instance."""
    global _summarizer
    if _summarizer is None:
        _summarizer = ConversationSummarizer()
    return _summarizer
