"""
Evaluation protocols for LinkedIn Assistant.
"""

from .skill_degradation import SkillDegradationTest
from .explainability import ExplainabilityTest

__all__ = ['SkillDegradationTest', 'ExplainabilityTest']

