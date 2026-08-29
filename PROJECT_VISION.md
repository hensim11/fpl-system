# FPL AI Platform — Project Vision

## Mission

Build one integrated, AI-powered Fantasy Premier League intelligence platform that helps a manager make better, more informed decisions over several Gameweeks.

The platform should turn trustworthy FPL data into calibrated predictions, realistic future scenarios, rule-aware plans, and clear explanations. It has two equally important goals:

1. Become a genuinely useful FPL decision-support product.
2. Become a technically strong AI/ML portfolio project whose architecture, modelling choices, evidence, and implementation can be understood and explained confidently.

This document describes that long-term destination. It does not describe the current feature set or promise that every capability will be built. The repository is intentionally at the data-foundation stage and should advance through `ROADMAP.md` in small, validated increments.

## What We Are Building

The intended product is a connected analytical system, not twelve independent experiments. Its components should share canonical data, feature definitions, predictions, uncertainty estimates, simulation infrastructure, and versioned FPL rules. Each layer should have a clear responsibility, and higher layers should consume evidence produced below them rather than recreate or invent it.

At maturity, the platform should be able to evaluate questions such as:

- Which transfers improve this squad over the next several Gameweeks after costs and constraints?
- How does a player's points outlook change when minutes, injury news, rotation risk, fixtures, or role change?
- Which captain, differential, or chip plan offers the best balance of expected return and risk?
- What plausible outcomes surround a recommendation, and what alternatives remain strong if assumptions change?

Recommendations should be decision support, not unexplained commands. The system should make its assumptions visible and allow its conclusions to be challenged.

## Product Capabilities

The long-term capability set comprises:

1. **AI FPL Decision Engine** — combines analytical outputs, user squad context, FPL constraints, and planning objectives into coherent recommendations.
2. **Multi-Gameweek Transfer Optimiser** — evaluates transfer paths across future Gameweeks, including transfer costs, budget, free-transfer state, squad structure, and later flexibility.
3. **Expected Points (xPts) Model** — estimates future FPL points over relevant horizons, with uncertainty where useful.
4. **Expected Minutes / Rotation Predictor** — estimates playing-time and start probabilities, including availability and rotation risk; these estimates are important inputs to xPts.
5. **AI News + Press Conference Agent** — collects and structures relevant updates, preserving source and timing, so news can affect availability, expected minutes, and uncertainty without becoming untraceable advice.
6. **Transfer Value Model** — assesses return relative to price, transfer cost, opportunity cost, holding period, and squad needs rather than treating cheapness alone as value.
7. **Differential Finder** — identifies potentially useful low-ownership choices by combining projected outcomes, ownership, risk, and team context.
8. **Captaincy AI** — compares captain candidates using outcome distributions, minutes risk, fixtures, and the manager's risk preferences, not only a single point estimate.
9. **Ownership Prediction Model** — forecasts relevant ownership or effective-ownership behaviour where feasible, helping quantify differential value and rank-related trade-offs.
10. **Chip Strategy AI** — evaluates chips over longer planning horizons, accounting for squad trajectory, fixtures, transfer plans, uncertainty, and the option value of retaining a chip.
11. **Monte Carlo FPL Simulator** — samples plausible future minutes, points, and related outcomes so planning uses ranges and probabilities rather than assuming predictions are exact.
12. **AI FPL Scout** — provides the user-facing conversational and explanation layer over the data, models, simulations, and optimisers.

These capabilities should reinforce one another. Expected-minutes estimates should inform xPts. xPts should inform transfer planning, captaincy, chip analysis, and simulation. Ownership forecasts should help evaluate differentials rather than replace expected performance. Timely news should update relevant facts, estimates, and confidence. Simulation should expose the range of possible futures used by optimisers. The Decision Engine should combine these outputs; it should not manufacture recommendations independently. The AI Scout should explain and interrogate the analytical system, not act as an LLM wrapper that invents FPL advice.

## How the System Fits Together

The conceptual architecture is:

```text
External data sources
  (FPL data, results, schedules, news and other permitted sources)
                           |
                           v
Ingestion and historical data foundation
  (raw preservation, provenance, timing, validation, quality checks)
                           |
                           v
Canonical FPL datasets
  (players, teams, fixtures, Gameweeks, events, prices, squads, rules)
                           |
                           v
Feature engineering
  (leakage-safe, reproducible, point-in-time features)
                           |
                           v
Predictive models
  (minutes, xPts, ownership, value-related signals, uncertainty)
                           |
                           v
Simulation and optimisation
  (Monte Carlo scenarios, transfers, captaincy, chips, constraints)
                           |
                           v
Decision Engine
  (combines evidence for the user's squad, horizon, and objectives)
                           |
                           v
AI Scout / user interface
  (questions, comparisons, explanations, assumptions, alternatives)
```

The arrows describe responsibility and information flow, not a required deployment topology. Components may share reusable domain logic and artifacts while retaining explicit interfaces. No particular ML algorithm, database, web framework, cloud platform, or LLM provider is part of this vision. Those choices should be made only when measured needs justify them.

Common foundations matter more than the number of named features. A player identity, deadline, price, or fixture should have one canonical meaning. Predictions should carry their target, horizon, as-of time, model or configuration version, and uncertainty where relevant. Simulation and optimisation should use the same rule definitions and prediction artifacts rather than maintain private, inconsistent interpretations.

## Decision Flow

A future transfer recommendation might follow this path:

1. Point-in-time facts establish the user's squad, prices, fixtures, deadlines, injuries, transfer state, and other information genuinely available at the decision time.
2. Reproducible features describe form, role, schedule, team context, news signals, and other justified inputs.
3. Models estimate expected minutes, points, ownership, and uncertainty over multiple future Gameweeks.
4. Simulation produces distributions of plausible player and squad outcomes instead of treating forecasts as certainties.
5. A rules-aware optimiser compares legal transfer paths, including hits, budget, free transfers, future flexibility, squad structure, and chip interactions.
6. The Decision Engine ranks or synthesises the results according to the user's horizon and objectives.
7. The AI Scout explains the recommendation, alternatives, assumptions, uncertainty, and conditions that could change the answer.

The platform should preserve the distinction between **observed facts**, **engineered features**, **model predictions**, **uncertainty and simulation outputs**, **optimisation decisions**, and **natural-language explanations**. This separation supports debugging, evaluation, auditability, and honest communication. It also prevents a fluent explanation from being mistaken for analytical evidence.

## Modelling Principles

- Evaluate prediction quality objectively using predefined targets and appropriate metrics.
- Prevent data leakage. Historical information available only after a Gameweek or deadline must never enter a prediction for an earlier decision point.
- Use time-aware validation and realistic backtesting rather than random splits that ignore chronology.
- Compare sophisticated approaches against simple, transparent baselines. Added complexity must demonstrate value.
- Preserve reproducibility across source snapshots, transformations, features, configurations, model runs, and evaluation results.
- Represent uncertainty where it materially improves decisions, and distinguish model uncertainty from ordinary randomness in outcomes when practical.
- Do not judge a model from a handful of memorable successful predictions. Use sufficiently broad, repeatable evidence.
- Keep data generation, prediction, simulation, and optimisation conceptually separate, even when they are executed in one workflow.
- Record prediction horizons and as-of times so results can be evaluated against exactly what was knowable when they were produced.

Model performance is not the same as product value. A statistically improved forecast must still be integrated into realistic FPL decisions and assessed for robustness, interpretability, and usefulness.

## FPL Domain Principles

FPL is a changing rules environment. Important rules should eventually be configurable and versioned by season or effective period rather than silently hard-coded into data transformations or models. Where practical, this includes:

- scoring;
- squad constraints and positions;
- transfers, free transfers, and transfer hits;
- prices and budget;
- chips;
- deadlines.

Rules should be applied consistently by backtests, simulations, optimisers, and live decision support. Data should retain the timing needed to reconstruct what was known before each deadline.

The core planning horizon should span several future Gameweeks. Next-Gameweek performance remains important, but greedy selection can create poor later fixtures, forced transfers, weak squad structure, or missed chip opportunities. Transfer and chip decisions should therefore consider trajectories, constraints, uncertainty, and future options.

## Product Experience and Explainability

The final product should be able to say more than “Buy Player X.” A useful explanation should identify the strongest signals and trade-offs, potentially including:

- predicted points and expected minutes;
- fixture outlook and planning horizon;
- player price and transfer value;
- ownership and differential implications;
- uncertainty and downside scenarios;
- transfer cost and available free transfers;
- credible alternative players or transfer paths;
- multi-Gameweek consequences and squad structure;
- chip implications when relevant.

Explanations should be faithful to the underlying computation. The interface should expose assumptions, data freshness, and uncertainty in language appropriate to the user, and should support comparisons and “what if” questions. It should not imply certainty that the models do not possess.

## Development Philosophy

The operating pattern is:

**working simple version → validate → understand → improve → expand**

The ambition of the destination does not justify building all capabilities at once. Progress should follow the existing roadmap: extend the current data foundation, establish historical and evaluation foundations, prove useful predictive increments, and add decision layers only when their prerequisites are reliable.

New infrastructure, dependencies, abstractions, and services should be introduced in response to real requirements. The current foundation should be extended rather than repeatedly replaced. Early implementations may be deliberately simple if they create a correct, testable baseline and reveal what the next increment actually needs.

Because this is both a product and a portfolio project, the codebase should favour understandable architecture, explicit assumptions, modular components, reproducible experiments, meaningful tests, documented decisions, and explainable analytical outputs. Technical sophistication is valuable only when it makes the system more correct, useful, maintainable, or demonstrably capable.

## What This Project Is Not

- It is not a collection of disconnected AI demos with duplicate data and incompatible assumptions.
- It is not an LLM wrapper that invents FPL advice without traceable analytical support.
- It is not a system optimised for flashy complexity, fashionable tools, or unnecessary infrastructure.
- It is not a promise to implement the full vision immediately or in a fixed technical form.
- It is not an oracle: football and FPL outcomes remain uncertain, and recommendations must reflect that.
- It is not a replacement for objective validation, domain rules, or human judgement.

## Definition of Long-Term Success

Long-term success means a user can bring a real squad and planning question to the platform and receive a legal, multi-Gameweek, uncertainty-aware recommendation supported by current and historical evidence. They can see why it was made, compare credible alternatives, understand the principal risks, and revisit the decision when news or assumptions change.

The analytical system should be independently credible: datasets are reproducible, temporal integrity is protected, models beat relevant baselines where claimed, simulation and optimisation are testable, rules are versioned, and natural-language outputs can be traced back to structured evidence. A future developer should be able to explain not only what the system predicts, but how it was evaluated and how that prediction becomes a decision.

## Relationship to Repository Documentation

- `PROJECT_VISION.md` defines the long-term destination, component relationships, and guiding principles.
- `ROADMAP.md` defines the incremental sequence for moving toward that destination; it remains the guide for what should be built next.
- `PROJECT_STATE.md` records what is implemented and verified now, including limitations and the recommended handoff.
- `README.md` explains the repository's current purpose, usage, data outputs, architecture, and operational assumptions.
- `DECISIONS.md` records accepted technical decisions, their context, and consequences as concrete choices are made.

When these documents differ in scope, the narrower document governs its subject: vision does not override roadmap order, roadmap does not imply current implementation, and current-state documentation should never claim aspirational capabilities already exist. Important future implementation choices should be recorded when evidence and requirements make them decisions rather than speculation.
