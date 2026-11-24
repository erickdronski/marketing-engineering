class MktgError(Exception):
    """A workspace or input problem the operator can correct."""

    def __init__(self, message, *, path=None, fix=None, exit_code=1):
        super().__init__(message)
        self.message = message
        self.path = path
        self.fix = fix
        self.exit_code = exit_code

    def format(self):
        where = f"{self.path}: " if self.path else ""
        remedy = f"\n  → {self.fix}" if self.fix else ""
        return f"mktgkit: {where}{self.message}{remedy}"
