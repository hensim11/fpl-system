# M5D — joint-simulation-v1

M5B supplies immutable point forecasts and exact legal transfer paths. M5C supplies
keyed empirical residuals and fixed marginal intervals. M5D defines an explicit
joint empirical law, draws reproducible scenarios, and compares those existing
paths with common random numbers. It does not change either upstream model or
the expected-points optimiser.

## The empirical law

For requested horizon H, reconstruct the exact accepted M5C calibration, including
its pinned M5B predictions/model bundle, M3 outcomes, original prediction keys,
label joins, settlement cutoff and three/five-GW eligibility. Keep a historical
donor only when all offsets 0 through H−1 have labels at the same original
(as-of Gameweek, player). Record every excluded key and reason. There is no
imputation, shorter-window substitution or prospective outcome input. Fewer than
100 complete donors makes operational simulation unavailable.

Sort donors by (as-of GW, element). For each scenario:

1. Draw one donor uniformly from all complete donors, and use its as-of GW as the
   shared block. Thus a block's probability is its donor count / total donors.
2. For every current player, in ascending element order, draw a donor uniformly
   **with replacement** from that block. Retain that donor's entire H-vector.
3. Add its raw signed residuals to the player's unchanged binary64 point forecasts.

This is equivalent to preserving the block mean vector plus each selected donor's
unmodified deviation from that mean, without estimating or fitting either as a
new parametric component. An individual player's marginal donor is uniform over
all complete windows. No residual is recentered, clipped or rescaled; simulated
means can differ from the frozen forecasts because historical bias is retained.
Values are continuous point scenarios, not a discrete football event simulator.

Two different current players move together because their donor distribution is
conditioned on the same historical block. They are **conditionally independent**
given that block. A single current player carries one donor's observed trajectory,
including positive or negative horizon dependence. Historical overlapping windows
remain overlapping evidence, not additional independent seasons. Block means can
also reflect donor composition changes and common forecast bias; this model does
not identify a causal football or Gameweek shock.

Let C be the covariance of complete donor vectors, B the size-weighted covariance
of block means, and P the current player count. The declared law implies:

- one player's residual covariance is C;
- two distinct players' residual cross-covariance is B;
- the covariance of the cross-sectional mean is B + (C−B)/P.

The matched **independent-residual-null-v1** draws every player/horizon component
independently from the same complete donor population. Its marginal distributions
match the joint law; within-player off-diagonal and cross-player covariances are
zero. Its aggregate-mean covariance is diag(diag(C))/P. This null is diagnostic
only; no calibration-reuse result selects a winning dependency model.

## What is unsupported

Current players are exchangeable with historical donors regardless of position,
club, opponent, price or expected minutes. Current IDs do not match historical
IDs. The shared block represents broad historical scoring environments and their
horizon trajectory; it does not reconstruct an individual football match. Residual
pair interactions within a block are not retained. In particular, this model cannot
represent opponent-specific negative same-GW dependence, clean-sheet coupling,
rotation competition or current-player conditional uncertainty. Same-GW cross-player
covariance is nonnegative under this law. No dependence is claimed across separate
forecast publications. All of these are explicit v1 limits, not omitted parameters.

The complete-window marginal differs from M5C's full marginal pool at early offsets
because late-season windows are excluded. Both populations and distributions are
reported; M5C's original interval endpoints remain unchanged. Its cumulative
residual is sum(y)−sum(p), while scenario sums add raw component residuals; these
are mathematically equivalent but may differ in the last binary64 bit. No M5C
quantile is recalculated or overwritten.

## Reproducibility and artifacts

`fpl_ai/joint_simulation.py` freezes the contract, source references, software,
implementation hash, configuration, population/exclusions and diagnostics in
`data/simulations/<identity>/`. The publisher enforces a closed artifact set and
checksums. Exact point, residual and donor-index trace SHA-256 hashes bind all
scenarios. Raw cubes are not retained: the sources, algorithm, environment, seed
and count reconstruct them. This avoids hundreds of megabytes of opaque files.

The RNG is NumPy Generator(PCG64(seed)), with the NumPy version bound. Joint draws
use one int64 anchor and then P int64 within-block indices per scenario. The null
uses an (H,P) int64 index array per scenario. Each model restarts its own generator
from the recorded seed. Increasing count preserves each model's original prefix.
Hash encoding is little-endian float64 C-order, (scenario,horizon,ascending player);
trace indices use little-endian int64. There is no dependency on a global RNG.

The simulation key binds all deterministic inputs; the publication identity also
binds actual start/computation timestamps. New publication, computation and final
verification must finish before the original first target deadline. There is no
timestamp override. Repeating the same configuration in the same output root
verifies and reuses it, even after the deadline. `replay` copies a verified original
attestation to a new root without redating. A separate new publication can have a
new attestation identity while retaining the same simulation key and scenario
hashes. Exact reproducibility is promised for the bound software environment.

## Plan evaluation

`fpl_ai/simulation_plans.py` publishes separately under
`data/simulation_evaluations/<identity>/`. It binds one simulation and one M5B path
artifact. It replays squad legality, exact prices, bank, free transfers, hits,
optimal forecast XI and captain using existing M5B helpers. The two already
accepted M5B identities reuse their accepted exact-ranking evidence. Any other
identity must reproduce the unchanged exact optimiser and greedy computation;
rehashing an altered path cannot confer acceptance. There is no candidate pruning
or weaker tie gate. Original M5B source files remain unchanged.

Every candidate sees the identical player scenario cube. Each GW scores the fixed
forecast-selected XI plus the extra captain multiplier, minus transfer hits.
There is no hindsight XI/captain selection, autosub/vice-captain policy, chip or
adaptive future transfer rule. These are static committed paths under M5B's
existing semantics, not a full realised-match FPL settlement engine.

Reports expose the original M5B objective, analytical simulation expectation,
Monte Carlo mean, median, population SD, P05/P10/P90/P95, extrema, lower-tail mean,
paired win/tie/loss probabilities and gain distributions versus no-transfer and
greedy. Highest-return credit is divided equally among tied supplied candidate
entries; inclusive and sole-win probabilities are also reported. Duplicate entries
are disclosed. Simulation ties use exact binary64 equality, independently of the
unchanged M5B optimisation tie contract.

The 10% lower-tail mean integrates exactly 10% of the empirical distribution,
using a fractional boundary observation where necessary. Monte Carlo standard
errors describe sampling precision conditional on this law; they do not quantify
model error or uncertainty in the historical evidence. No metric is collapsed into
a risk score, no risk preference is chosen, and the optimiser retains its objective.

## Verification boundaries

`tests/test_joint_simulation.py` covers known positive/negative dependence, common
GW shocks, donor-specific persistence, independent factorial behaviour, RNG replay,
missing evidence, source mutations, closed artifacts, clock gates, legal path
replay, returns, paired metrics, ties and fractional shortfall. Its upstream clock
and evidence mocks are confined to explicitly synthetic tests.

`scripts/verify_joint_simulation.py` reconstructs complete donors from M5C rows,
uses the existing independent M5C CSV/label audit, independently implements RNG
index mapping, checks every scenario/trace hash, enumerates scalar path returns,
and independently computes risk metrics and dependence moments. It does not use
production sampling or metric functions as the reference. The existing independent
M5B exhaustive XI/economics audit and exact ranking oracle remain unchanged.

`scripts/profile_joint_simulation.py` examines scenario-count convergence at fixed
seeds and a fixed dependency law. Its only choice is numerical simulation precision,
not selecting a model on consumed historical evidence. Acceptance results and
measured runtimes are recorded in M5D_VERIFICATION.md and machine evidence.
