"""LLM interface supporting LM Studio (local) and cloud providers via LangChain."""

import logging
import time
from typing import Optional, List, Dict, Any

from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser

from ..config import settings

logger = logging.getLogger(__name__)

_parser = StrOutputParser()


def _build_chat_model(
    provider: str,
    model: str,
    base_url: Optional[str],
    api_key: Optional[str],
    temperature: float,
    max_tokens: Optional[int],
) -> BaseChatModel:
    """Instantiate the appropriate LangChain chat model for the given provider."""
    common: Dict[str, Any] = {"temperature": temperature}
    if max_tokens is not None:
        common["max_tokens"] = max_tokens

    # Local server (LM Studio, vLLM, local OpenAI-compatible endpoint)
    if base_url:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            base_url=base_url,
            api_key=api_key or "lm-studio",  # LM Studio ignores the key
            **common,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model,
            anthropic_api_key=api_key or settings.anthropic_api_key,
            **common,
        )

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model, **common)

    # Default: OpenAI (or any OpenAI-compatible cloud)
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=model,
        api_key=api_key or settings.openai_api_key,
        **common,
    )


def _to_lc_messages(messages: List[Dict[str, str]]) -> List[BaseMessage]:
    """Convert role/content dicts to LangChain message objects."""
    lc: List[BaseMessage] = []
    for m in messages:
        role, content = m["role"], m["content"]
        if role == "system":
            lc.append(SystemMessage(content=content))
        else:
            lc.append(HumanMessage(content=content))
    return lc


class LLMClient:
    """
    LangChain-backed LLM client.

    Supports:
    - LM Studio / local OpenAI-compatible servers (set llm_base_url)
    - OpenAI cloud  (provider = "openai")
    - Anthropic     (provider = "anthropic")
    - Ollama        (provider = "ollama")
    """

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.model = model or settings.default_llm_model
        self.base_url = base_url or settings.llm_base_url
        self.api_key = api_key or settings.openai_api_key
        self._provider = "lm_studio" if self.base_url else settings.default_llm_provider
        logger.info(f"LLM: provider={self._provider}, model={self.model}, local={bool(self.base_url)}")

    @property
    def provider(self) -> str:
        return self._provider

    def _model(self, temperature: float, max_tokens: Optional[int]) -> BaseChatModel:
        return _build_chat_model(
            provider=self._provider,
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Get a completion from the LLM.

        Args:
            messages: List of {"role": "system"|"user", "content": str}
            temperature: Sampling temperature
            max_tokens: Max tokens to generate

        Returns:
            Generated text string
        """
        try:
            t0 = time.perf_counter()
            chain = self._model(temperature, max_tokens) | _parser
            response = chain.invoke(_to_lc_messages(messages))
            elapsed = (time.perf_counter() - t0) * 1000
            logger.debug(
                f"LLM complete: provider={self._provider} model={self.model} "
                f"prompt_chars={sum(len(m['content']) for m in messages)} "
                f"response_chars={len(response)} elapsed={elapsed:.0f}ms"
            )
            return response
        except Exception as e:
            logger.error(f"LLM complete error provider={self._provider} model={self.model}: {e}")
            raise

    def explain_move_detailed(
        self,
        *,
        move_san: str,
        best_move_san: Optional[str],
        position_description: str,
        eval_loss_cp: float,
        classification: str,
        followup_line: List[str],
        best_followup_line: List[str],
        tactical_motif: Optional[str],
        game_phase: str,
        recent_moves: List[str],
    ) -> Dict[str, Any]:
        """
        Generate a per-move coaching explanation.

        Returns a dict with keys:
            move_intent           -- what the played move accomplishes
            why_bad               -- empty string if move was best/good
            better_move_san       -- empty string if move was best
            better_move_explanation -- empty string if move was best
        """
        is_good_move = best_move_san is None or best_move_san == move_san

        motif_note = f"\nTactical motif detected: {tactical_motif}." if tactical_motif else ""
        recent_note = (
            f"\nRecent moves leading here: {' '.join(recent_moves[-5:])}"
            if recent_moves else ""
        )
        followup_note = (
            f"\nBest continuation after the played move: {' '.join(followup_line)}"
            if followup_line else ""
        )
        best_note = (
            f"\nBest continuation after {best_move_san}: {' '.join(best_followup_line)}"
            if best_followup_line and not is_good_move else ""
        )

        if is_good_move:
            prompt = f"""You are a chess coach. Explain what the move {move_san} accomplishes.

Game phase: {game_phase}
Position:{recent_note}
{position_description}{followup_note}{motif_note}

In 2-3 sentences, explain:
- What does {move_san} accomplish positionally or tactically?
- What plan or idea does it support?

Be specific to the position, not generic.

Respond with ONLY:
INTENT: [2-3 sentences]"""
        else:
            prompt = f"""You are a chess coach. Analyse this chess move and explain why a better move exists.

Game phase: {game_phase}
Move played: {move_san} (classification: {classification}, eval loss: {eval_loss_cp:.0f} centipawns)
Better move: {best_move_san}
Position:{recent_note}
{position_description}{followup_note}{best_note}{motif_note}

Respond with ONLY these three sections:
INTENT: [What was the player likely trying to achieve with {move_san}? 1-2 sentences]
WHY_BAD: [Specifically why {move_san} is a {classification} — concrete consequences, not generic advice. 2-3 sentences]
BETTER: [Why {best_move_san} is stronger — what specific threat, defence, or plan does it create? 2-3 sentences]"""

        messages = [
            {"role": "system", "content": "You are a precise chess coach. Answer only in the exact format requested. No extra text."},
            {"role": "user", "content": prompt},
        ]

        try:
            raw = self.complete(messages, temperature=0.4, max_tokens=350)
            result = self._parse_move_explanation(raw, is_good_move, move_san, best_move_san)
            logger.debug(
                f"LLM explain_move: move={move_san} classification={classification} "
                f"intent_len={len(result.get('move_intent',''))} fallback=False"
            )
            return result
        except Exception as e:
            logger.warning(f"LLM move explanation failed move={move_san}: {e}")
            return self._fallback_move_explanation(move_san, best_move_san, eval_loss_cp, classification, tactical_motif)

    def _parse_move_explanation(
        self,
        raw: str,
        is_good_move: bool,
        move_san: str,
        best_move_san: Optional[str],
    ) -> Dict[str, Any]:
        """Parse structured LLM response into a clean dict."""
        result: Dict[str, Any] = {
            "move_intent": "",
            "why_bad": "",
            "better_move_san": "" if is_good_move else (best_move_san or ""),
            "better_move_explanation": "",
        }
        for line in raw.strip().splitlines():
            line = line.strip()
            if line.startswith("INTENT:"):
                result["move_intent"] = line[len("INTENT:"):].strip()
            elif line.startswith("WHY_BAD:"):
                result["why_bad"] = line[len("WHY_BAD:"):].strip()
            elif line.startswith("BETTER:"):
                result["better_move_explanation"] = line[len("BETTER:"):].strip()
        return result

    def _fallback_move_explanation(
        self,
        move_san: str,
        best_move_san: Optional[str],
        eval_loss_cp: float,
        classification: str,
        tactical_motif: Optional[str],
    ) -> Dict[str, Any]:
        """Template-based fallback when LLM is unavailable."""
        motif_txt = f" It involves a {tactical_motif} pattern." if tactical_motif else ""
        if best_move_san and best_move_san != move_san:
            why_bad = (
                f"{move_san} loses {eval_loss_cp:.0f} centipawns ({classification}).{motif_txt} "
                f"{best_move_san} was the stronger choice."
            )
            better = f"Playing {best_move_san} instead keeps a better position."
        else:
            why_bad = ""
            better = ""
        return {
            "move_intent": f"{move_san} was played.",
            "why_bad": why_bad,
            "better_move_san": best_move_san or "",
            "better_move_explanation": better,
            "is_fallback": True,
        }

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
