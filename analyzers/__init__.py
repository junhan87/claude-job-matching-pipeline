from .linkedin import LinkedInAnalysisStrategy
from .direct import DirectAnalysisStrategy

# Ordered by specificity — first match wins; DirectAnalysisStrategy is the fallback.
ANALYZERS = [
    LinkedInAnalysisStrategy(),
    DirectAnalysisStrategy(),
]
