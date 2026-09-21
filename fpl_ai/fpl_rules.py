"""Versioned, deliberately narrow rules registry for one-GW decisions."""
from dataclasses import asdict, dataclass


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, name, minimum=0, maximum=None):
    require(type(value) is int and value >= minimum and
            (maximum is None or value <= maximum), f'invalid {name}')
    return value


@dataclass(frozen=True)
class Rules:
    version: str = 'fpl-2026-27-one-gw-v1'
    season: str = '2026-27'
    squad_size: int = 15
    position_counts: tuple = (2, 5, 5, 3)
    club_limit: int = 3
    xi_size: int = 11
    xi_min: tuple = (1, 3, 2, 1)
    xi_max: tuple = (1, 5, 5, 3)
    captain_multiplier: int = 2
    free_transfer_cap: int = 5
    weekly_free_transfers: int = 1
    hit_cost: int = 4
    gameweeks: int = 38
    money_unit: str = 'GBP 0.1 million; integer'
    chips: tuple = ()

    def validate(self):
        # Only registered contracts are executable. A future version gets its own
        # registry entry and validation, without changing the optimisation engine.
        require(self == Rules() and all(type(getattr(self, n)) is int for n in
                ('squad_size', 'club_limit', 'xi_size', 'captain_multiplier',
                 'free_transfer_cap', 'weekly_free_transfers', 'hit_cost', 'gameweeks'))
                and all(type(v) is int for vs in (self.position_counts, self.xi_min, self.xi_max) for v in vs),
                'unsupported rules contract')
        return self

    def as_dict(self):
        self.validate()
        return {k: list(v) if isinstance(v, tuple) else v for k, v in asdict(self).items()}

    def hit(self, transfers, free):
        return self.hit_cost * max(0, transfers - free)

    def next_free(self, transfers, free):
        return min(self.free_transfer_cap, max(0, free - transfers) + self.weekly_free_transfers)
