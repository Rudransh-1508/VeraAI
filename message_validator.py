"""
Message validation module to ensure generated messages follow all rules.
"""

import re
from typing import Dict, List, Tuple


class MessageValidator:
    """Validates generated messages against quality rules."""
    
    # Urgency words that MUST be present for high-urgency triggers
    URGENCY_WORDS = ["only", "just", "losing", "missing", "sirf", "bas"]
    
    # Active loss words (better than passive)
    ACTIVE_LOSS_WORDS = ["losing", "missing", "miss", "lose", "kam"]
    
    # Passive state words (should be avoided)
    PASSIVE_WORDS = ["is below", "hai neeche", "thoda neeche", "below peer"]
    
    def __init__(self):
        pass
    
    def validate_message(
        self, 
        body: str, 
        trigger: dict,
        merchant: dict,
        category: dict = None
    ) -> Tuple[bool, List[str], Dict[str, bool]]:
        """
        Validate a message against all rules.
        
        Returns:
            (is_valid, issues, checks)
            - is_valid: True if message passes all critical checks
            - issues: List of validation issues found
            - checks: Dict of individual check results
        """
        issues = []
        checks = {}
        
        trigger_kind = trigger.get("kind", "")
        trigger_urgency = trigger.get("urgency", 0)
        languages = merchant.get("identity", {}).get("languages", ["en"])
        
        # Check 1: Trigger-first messaging
        checks["trigger_first"] = self._check_trigger_first(body, trigger_kind)
        if not checks["trigger_first"]:
            issues.append(f"CRITICAL: First sentence should address trigger ({trigger_kind}), not merchant stats")
        
        # Check 2: Urgency words (for high-urgency triggers)
        if trigger_urgency >= 3:
            checks["urgency_words"] = self._check_urgency_words(body)
            if not checks["urgency_words"]:
                issues.append(f"CRITICAL: Missing urgency words (only/just/losing/missing) for urgency={trigger_urgency}")
        else:
            checks["urgency_words"] = True  # Not required for low urgency
        
        # Check 3: Quantified loss conversion
        checks["quantified_loss"] = self._check_quantified_loss(body)
        if not checks["quantified_loss"]:
            issues.append("WARNING: Missing quantified loss (e.g., 'missing 9 calls/month', '₹X/month')")
        
        # Check 4: Compelling CTA
        checks["compelling_cta"] = self._check_compelling_cta(body)
        if not checks["compelling_cta"]:
            issues.append("WARNING: CTA is generic 'Reply YES / NO' - should add context")
        
        # Check 5: Active loss framing (not passive)
        checks["active_loss"] = self._check_active_loss(body)
        if not checks["active_loss"]:
            issues.append("INFO: Uses passive framing - consider active loss framing")
        
        # Check 6: Merchant-specific data
        checks["merchant_data"] = self._check_merchant_data(body, merchant)
        if not checks["merchant_data"]:
            issues.append("WARNING: Missing merchant-specific data (locality, numbers)")
        
        # Check 7: Effort externalization
        checks["effort_externalization"] = self._check_effort_externalization(body)
        if not checks["effort_externalization"]:
            issues.append("INFO: Missing effort externalization ('I've done X')")
        
        # Check 8: Hindi-English code-mix (if applicable)
        if "hi" in languages:
            checks["code_mix"] = self._check_code_mix(body)
            if not checks["code_mix"]:
                issues.append("INFO: Should use Hindi-English code-mix for Hindi speakers")
        else:
            checks["code_mix"] = True
        
        # Check 9: No URLs
        checks["no_urls"] = not self._contains_url(body)
        if not checks["no_urls"]:
            issues.append("CRITICAL: Contains URL - instant penalty")
        
        # Determine if valid (all CRITICAL checks pass)
        critical_checks = [
            checks["trigger_first"],
            checks["urgency_words"],
            checks["no_urls"],
        ]
        is_valid = all(critical_checks)
        
        return is_valid, issues, checks
    
    def _check_trigger_first(self, body: str, trigger_kind: str) -> bool:
        """Check if first sentence addresses the trigger."""
        # Get first sentence
        first_sentence = body.split(".")[0] if "." in body else body.split(",")[0]
        first_sentence = first_sentence.lower()
        
        # Trigger-specific keywords that should appear in first sentence
        trigger_keywords = {
            "research_digest": ["jida", "research", "study", "shows", "finding"],
            "regulation_change": ["deadline", "compliance", "dci", "days left", "days remaining"],
            "perf_dip": ["dropped", "drop", "dip", "losing", "missing", "down"],
            "winback_eligible": ["lapsed", "haven't visited", "days since", "customers added"],
            "active_planning_intent": ["asked", "you asked", "question", "planning"],
            "recall": ["recall", "batch", "affected"],
            "refill": ["refill", "prescription", "due"],
        }
        
        keywords = trigger_keywords.get(trigger_kind, [])
        if not keywords:
            return True  # Unknown trigger type, pass
        
        # Check if any keyword appears in first sentence
        return any(keyword in first_sentence for keyword in keywords)
    
    def _check_urgency_words(self, body: str) -> bool:
        """Check if message contains urgency words."""
        body_lower = body.lower()
        return any(word in body_lower for word in self.URGENCY_WORDS)
    
    def _check_quantified_loss(self, body: str) -> bool:
        """Check if message contains quantified loss (concrete numbers with time period)."""
        # Patterns for quantified loss
        patterns = [
            r"\d+\s*calls?/month",
            r"\d+\s*calls?/day",
            r"\d+\s*calls?/week",
            r"₹\s*\d+[,\d]*/month",
            r"₹\s*\d+[,\d]*/day",
            r"missing\s+~?\d+",
            r"losing\s+~?\d+",
            r"=\s*missing",
            r"=\s*losing",
        ]
        
        return any(re.search(pattern, body, re.IGNORECASE) for pattern in patterns)
    
    def _check_compelling_cta(self, body: str) -> bool:
        """Check if CTA is compelling (not generic 'Reply YES / NO')."""
        # Generic CTAs to avoid
        generic_ctas = [
            "reply yes / no",
            "reply yes/no",
            "want me to",
            "interested?",
        ]
        
        body_lower = body.lower()
        
        # If it has a generic CTA, fail
        if any(generic in body_lower for generic in generic_ctas):
            # Unless it has context added
            compelling_additions = [
                "just reply yes",
                "reply yes to stop",
                "reply yes to recover",
                "reply yes for",
                "reply yes —",
                "only takes",
                "2-min",
                "2 min",
            ]
            return any(addition in body_lower for addition in compelling_additions)
        
        return True
    
    def _check_active_loss(self, body: str) -> bool:
        """Check if message uses active loss framing."""
        body_lower = body.lower()
        
        # Check for active loss words
        has_active = any(word in body_lower for word in self.ACTIVE_LOSS_WORDS)
        
        # Check for passive words (penalty)
        has_passive = any(word in body_lower for word in self.PASSIVE_WORDS)
        
        # Prefer active over passive
        return has_active or not has_passive
    
    def _check_merchant_data(self, body: str, merchant: dict) -> bool:
        """Check if message includes merchant-specific data."""
        identity = merchant.get("identity", {})
        locality = identity.get("locality", "")
        city = identity.get("city", "")
        
        # Check for locality or city mention
        has_location = False
        if locality and locality.lower() in body.lower():
            has_location = True
        if city and city.lower() in body.lower():
            has_location = True
        
        # Check for numbers (CTR, calls, views, customers, etc.)
        has_numbers = bool(re.search(r"\d+", body))
        
        return has_location and has_numbers
    
    def _check_effort_externalization(self, body: str) -> bool:
        """Check if message uses effort externalization."""
        patterns = [
            r"i've\s+\w+",
            r"i've already",
            r"maine\s+\w+",
            r"ready\s+(hai|kar)",
            r"drafted",
            r"pulled",
            r"setup is ready",
        ]
        
        return any(re.search(pattern, body, re.IGNORECASE) for pattern in patterns)
    
    def _check_code_mix(self, body: str) -> bool:
        """Check if message uses Hindi-English code-mix."""
        # Hindi words that should appear
        hindi_words = ["hai", "aap", "aapke", "aapka", "ke", "se", "mein", "ka", "ki"]
        
        body_lower = body.lower()
        return any(word in body_lower for word in hindi_words)
    
    def _contains_url(self, body: str) -> bool:
        """Check if message contains URLs."""
        return bool(re.search(r"https?://\S+", body))
    
    def get_validation_score(self, checks: Dict[str, bool]) -> float:
        """
        Calculate a validation score (0.0-1.0) based on checks.
        
        Critical checks are weighted higher.
        """
        weights = {
            "trigger_first": 0.20,
            "urgency_words": 0.20,
            "quantified_loss": 0.15,
            "compelling_cta": 0.15,
            "active_loss": 0.10,
            "merchant_data": 0.10,
            "effort_externalization": 0.05,
            "code_mix": 0.05,
            "no_urls": 0.20,  # Critical
        }
        
        score = 0.0
        for check, passed in checks.items():
            if check in weights and passed:
                score += weights[check]
        
        return score


def validate_and_score(
    body: str,
    trigger: dict,
    merchant: dict,
    category: dict = None
) -> Tuple[bool, float, List[str]]:
    """
    Convenience function to validate and score a message.
    
    Returns:
        (is_valid, score, issues)
    """
    validator = MessageValidator()
    is_valid, issues, checks = validator.validate_message(body, trigger, merchant, category)
    score = validator.get_validation_score(checks)
    
    return is_valid, score, issues
