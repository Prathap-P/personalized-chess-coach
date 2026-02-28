"""LLM interface supporting LM Studio (local) and cloud providers."""

import logging
from typing import Optional, List, Dict, Any

from ..config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Client for interacting with LLMs.

    For LM Studio (local): Uses OpenAI-compatible SDK directly via base_url.
    For cloud providers: Uses LiteLLM.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize LLM client.

        Args:
            model: Model name (e.g., "nemotron-3-nano")
            base_url: Local server URL (e.g., "http://localhost:1234/v1")
            api_key: API key for cloud providers (not needed for LM Studio)
        """
        self.model = model or settings.default_llm_model
        self.base_url = base_url or settings.llm_base_url
        self.api_key = api_key or settings.openai_api_key

        # Determine mode: local (LM Studio) or cloud
        self.is_local = bool(self.base_url)

        if self.is_local:
            # Use OpenAI SDK with custom base_url — most reliable for LM Studio
            from openai import OpenAI
            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key or "lm-studio",  # LM Studio ignores this
            )
            logger.info(f"LLM: LM Studio at {self.base_url}, model={self.model}")
        else:
            # Cloud provider via LiteLLM
            import litellm
            litellm.drop_params = True
            self._litellm = litellm
            logger.info(f"LLM: Cloud provider, model={settings.default_llm_provider}/{self.model}")

    @property
    def provider(self) -> str:
        return "lm_studio" if self.is_local else settings.default_llm_provider

    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Get completion from LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response
        """
        try:
            if self.is_local:
                return self._complete_local(messages, temperature, max_tokens)
            else:
                return self._complete_cloud(messages, temperature, max_tokens)
        except Exception as e:
            logger.error(f"LLM completion error: {e}")
            raise

    def _complete_local(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
    ) -> str:
        """Call LM Studio via OpenAI-compatible SDK."""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def _complete_cloud(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
    ) -> str:
        """Call cloud provider via LiteLLM."""
        model_string = self.model if "/" in self.model else f"{settings.default_llm_provider}/{self.model}"
        kwargs = {
            "model": model_string,
            "messages": messages,
            "temperature": temperature,
            "api_key": self.api_key,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        response = self._litellm.completion(**kwargs)
        return response.choices[0].message.content

    def generate_game_analysis(
        self,
        game_summary: str,
        errors: List[Dict[str, Any]],
        patterns: List[Dict[str, Any]],
        player_level: Optional[int] = None,
        player_stats: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate personalized game analysis using LLM.

        Args:
            game_summary: Summary of the game
            errors: List of errors made during the game
            patterns: Identified patterns in gameplay
            player_level: Player's ELO rating or skill level
            player_stats: Dict with 'white' and 'black' accuracy/classification stats

        Returns:
            Dict with 'summary', 'strengths', 'weaknesses', 'recommendations'
        """
        level_context = ""
        if player_level:
            level_context = f"\nPlayer skill level: {player_level} ELO"

        accuracy_context = ""
        if player_stats:
            accuracy_context = f"\nMove Quality Summary:\n{self._format_player_stats(player_stats)}"

        prompt = f"""You are an expert chess coach analyzing a game. Provide personalized, constructive feedback.
{level_context}{accuracy_context}

Game Summary:
{game_summary}

Errors Made:
{self._format_errors(errors)}

Patterns Identified:
{self._format_patterns(patterns)}

Please provide:
1. A brief overall summary of the game performance (reference accuracy scores where relevant)
2. Key strengths demonstrated in this game
3. Main weaknesses or areas for improvement
4. Specific, actionable recommendations for improvement

Format your response as:
SUMMARY: [1-2 sentences]
STRENGTHS: [2-3 bullet points]
WEAKNESSES: [2-3 bullet points]
RECOMMENDATIONS: [3-4 specific action items]
"""

        messages = [
            {"role": "system", "content": "You are an expert chess coach providing personalized feedback."},
            {"role": "user", "content": prompt},
        ]

        response = self.complete(messages, temperature=0.7, max_tokens=800)
        return self._parse_analysis_response(response)

    def explain_move(
        self,
        position_fen: str,
        move_played: str,
        best_move: str,
        eval_loss: float,
        mistake_type: str,
    ) -> str:
        """
        Get explanation for why a move was a mistake.

        Args:
            position_fen: FEN string of position
            move_played: Move that was played
            best_move: Best move according to engine
            eval_loss: Evaluation loss in centipawns
            mistake_type: Type of mistake (tactical, positional, etc.)

        Returns:
            Natural language explanation
        """
        prompt = f"""Explain why this chess move was a mistake:

Position (FEN): {position_fen}
Move played: {move_played}
Best move: {best_move}
Evaluation loss: {eval_loss:.0f} centipawns
Mistake type: {mistake_type}

Provide a clear, educational explanation in 2-3 sentences that helps the player understand what went wrong and what they should have considered instead."""

        messages = [
            {"role": "system", "content": "You are a chess coach explaining mistakes clearly and constructively."},
            {"role": "user", "content": prompt},
        ]

        return self.complete(messages, temperature=0.7, max_tokens=200)

    def _format_errors(self, errors: List[Dict[str, Any]]) -> str:
        """Format errors for prompt."""
        if not errors:
            return "No significant errors"

        lines = []
        for i, error in enumerate(errors[:5], 1):  # Limit to top 5
            lines.append(
                f"{i}. Move {error.get('move_number')}: {error.get('move')} "
                f"({error.get('classification')}, -{error.get('eval_loss', 0):.0f} cp)"
            )
        return "\n".join(lines)

    def _format_patterns(self, patterns: List[Dict[str, Any]]) -> str:
        """Format patterns for prompt."""
        if not patterns:
            return "No recurring patterns identified"

        lines = []
        for pattern in patterns[:3]:  # Limit to top 3
            lines.append(
                f"- {pattern.get('description')} "
                f"({pattern.get('occurrences')} occurrences, {pattern.get('severity')} severity)"
            )
        return "\n".join(lines)

    def _format_player_stats(self, player_stats: Dict[str, Any]) -> str:
        """Format per-player accuracy and classification counts for prompt."""
        lines = []
        for color, s in player_stats.items():
            if not s:
                continue
            lines.append(
                f"  {color.capitalize()} ({s.get('accuracy', 0):.1f}% accuracy): "
                f"Best={s.get('best', 0)}, Excellent={s.get('excellent', 0)}, "
                f"Good={s.get('good', 0)}, Inaccuracies={s.get('inaccuracy', 0)}, "
                f"Mistakes={s.get('mistake', 0)}, Blunders={s.get('blunder', 0)}"
            )
        return "\n".join(lines) if lines else "No stats available"

    def _parse_analysis_response(self, response: str) -> Dict[str, Any]:
        """Parse structured analysis response from LLM."""
        result = {
            "summary": "",
            "strengths": [],
            "weaknesses": [],
            "recommendations": [],
        }

        lines = response.strip().split("\n")
        current_section = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("SUMMARY:"):
                current_section = "summary"
                result["summary"] = line.replace("SUMMARY:", "").strip()
            elif line.startswith("STRENGTHS:"):
                current_section = "strengths"
            elif line.startswith("WEAKNESSES:"):
                current_section = "weaknesses"
            elif line.startswith("RECOMMENDATIONS:"):
                current_section = "recommendations"
            elif current_section and line.startswith(("-", "•", "*")):
                # Bullet point
                text = line.lstrip("-•* ").strip()
                if current_section != "summary":
                    result[current_section].append(text)

        return result
