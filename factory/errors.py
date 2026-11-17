"""Error types. The CLI prints any FactoryError message and exits 1."""


class FactoryError(Exception):
    """Base class for expected, user-facing failures."""


class LedgerError(FactoryError):
    """The ledger file cannot be read or parsed."""


class GitError(FactoryError):
    """A git command failed."""


class WorkflowError(FactoryError):
    """A role was run out of order."""


class AgentRunError(FactoryError):
    """The agent runtime failed to produce a result."""


class AgentOutputError(FactoryError):
    """The agent's final message did not satisfy the output contract."""


class ProtectedPathError(FactoryError):
    """An agent changed files it is not allowed to change."""
