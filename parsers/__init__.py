from core.config import LINKEDIN, MCF, JOBSTREET
from .linkedin import LinkedInStrategy
from .mcf import MCFStrategy
from .jobstreet import JobStreetStrategy

STRATEGIES = {
    LINKEDIN: LinkedInStrategy(),
    MCF: MCFStrategy(),
    JOBSTREET: JobStreetStrategy(),
}
