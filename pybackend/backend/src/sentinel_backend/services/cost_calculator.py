import logging
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.models.agent import Agent
from sentinel_backend.models.pricing import PricingVersion
from sentinel_backend.models.run import Run
from sentinel_backend.models.span import Span
from sentinel_backend.schemas.costs import (
    CostBreakdownItemDTO,
    CostSummaryDTO,
)

logger = logging.getLogger(__name__)

DEFAULT_PRICING_SEEDS = [
    {
        "provider": "openai",
        "model_name": "gpt-4o",
        "version_tag": "2026-11-v1",
        "input_rate_per_1m": Decimal("2.50"),
        "output_rate_per_1m": Decimal("10.00"),
    },
    {
        "provider": "openai",
        "model_name": "gpt-4o-mini",
        "version_tag": "2026-11-v1",
        "input_rate_per_1m": Decimal("0.15"),
        "output_rate_per_1m": Decimal("0.60"),
    },
    {
        "provider": "anthropic",
        "model_name": "claude-3-7-sonnet",
        "version_tag": "2026-11-v1",
        "input_rate_per_1m": Decimal("3.00"),
        "output_rate_per_1m": Decimal("15.00"),
    },
    {
        "provider": "google",
        "model_name": "gemini-2.5-pro",
        "version_tag": "2026-11-v1",
        "input_rate_per_1m": Decimal("1.25"),
        "output_rate_per_1m": Decimal("5.00"),
    },
    {
        "provider": "groq",
        "model_name": "llama-3.3-70b-versatile",
        "version_tag": "2026-11-v1",
        "input_rate_per_1m": Decimal("0.59"),
        "output_rate_per_1m": Decimal("0.79"),
    },
    {
        "provider": "google",
        "model_name": "gemini-2.5-flash",
        "version_tag": "2026-11-v1",
        "input_rate_per_1m": Decimal("0.15"),
        "output_rate_per_1m": Decimal("0.60"),
    },
    {
        "provider": "huggingface",
        "model_name": "deepseek-ai/DeepSeek-R1:fastest",
        "version_tag": "2026-11-v1",
        "input_rate_per_1m": Decimal("0.55"),
        "output_rate_per_1m": Decimal("2.19"),
    },
]


async def seed_default_pricing(db: AsyncSession) -> None:
    """If pricing_versions is empty, insert initial versioned rates."""
    count_res = await db.execute(select(func.count()).select_from(PricingVersion))
    count = count_res.scalar_one()
    if count == 0:
        now_utc = datetime.now(UTC)
        rates = [
            PricingVersion(
                provider=seed["provider"],
                model_name=seed["model_name"],
                version_tag=seed["version_tag"],
                input_rate_per_1m=seed["input_rate_per_1m"],
                output_rate_per_1m=seed["output_rate_per_1m"],
                effective_from=now_utc,
            )
            for seed in DEFAULT_PRICING_SEEDS
        ]
        db.add_all(rates)
        await db.commit()
        logger.info("Seeded %d default pricing versions into database.", len(rates))


async def calculate_run_costs(db: AsyncSession, run_id: str) -> None:
    """Calculate leaf billable span costs and roll up run-level cost attribution.

    - Only calculates direct_cost_usd on leaf billable spans (span.span_type == "LLM").
    - Missing tokens -> direct_cost_usd = None, cost_basis = "UNKNOWN" (never 0.0).
    - Unconfigured pricing -> direct_cost_usd = None, cost_basis = "UNKNOWN".
    - Matched pricing -> direct_cost_usd = (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000,
      cost_basis = "EXACT".
    - Non-leaf spans (AGENT, TOOL, APPROVAL) keep direct_cost_usd = None.
    - Rollup rules:
      - If unknown_count > 0 and known_sum == 0 -> run.total_cost_usd = None, cost_status = "UNKNOWN"
      - Else if unknown_count > 0 -> run.total_cost_usd = known_sum, cost_status = "PARTIAL"
      - Else -> run.total_cost_usd = known_sum, cost_status = "EXACT"
    """
    run = await db.get(Run, run_id)
    if not run:
        return

    # Load all spans for this run
    stmt = select(Span).where(Span.run_id == run_id)
    res = await db.execute(stmt)
    spans = list(res.scalars().all())

    # Load active PricingVersion rows (ordered by effective_from ASC so latest overwrites earlier)
    pricing_stmt = select(PricingVersion).order_by(PricingVersion.effective_from.asc())
    pricing_res = await db.execute(pricing_stmt)
    all_pricing = pricing_res.scalars().all()

    active_pricing: dict[tuple[str, str], PricingVersion] = {}
    for p in all_pricing:
        active_pricing[(p.provider.strip().lower(), p.model_name.strip().lower())] = p

    for span in spans:
        if span.span_type == "LLM":
            if span.input_tokens is None or span.output_tokens is None:
                span.direct_cost_usd = None
                span.cost_basis = "UNKNOWN"
            else:
                provider_key = (
                    span.model_provider.strip().lower()
                    if span.model_provider
                    else ""
                )
                model_key = (
                    span.model_name.strip().lower()
                    if span.model_name
                    else ""
                )
                pricing = active_pricing.get((provider_key, model_key))
                if pricing is not None:
                    input_rate = Decimal(str(pricing.input_rate_per_1m))
                    output_rate = Decimal(str(pricing.output_rate_per_1m))
                    cost = (
                        Decimal(span.input_tokens) * input_rate
                        + Decimal(span.output_tokens) * output_rate
                    ) / Decimal(1000000)
                    span.direct_cost_usd = round(cost, 6)
                    span.cost_basis = "EXACT"
                else:
                    span.direct_cost_usd = None
                    span.cost_basis = "UNKNOWN"
        else:
            # Non-leaf spans (AGENT, TOOL, APPROVAL) keep direct_cost_usd = None
            span.direct_cost_usd = None

    # Roll up the run total from leaf LLM spans
    llm_spans = [s for s in spans if s.span_type == "LLM"]
    known_costs = [
        s.direct_cost_usd for s in llm_spans if s.direct_cost_usd is not None
    ]
    known_sum = sum(known_costs, Decimal(0))
    unknown_count = sum(1 for s in llm_spans if s.cost_basis == "UNKNOWN")

    if unknown_count > 0 and known_sum == 0:
        run.total_cost_usd = None
        run.cost_status = "UNKNOWN"
    elif unknown_count > 0:
        run.total_cost_usd = round(known_sum, 6)
        run.cost_status = "PARTIAL"
    else:
        run.total_cost_usd = round(known_sum, 6)
        run.cost_status = "EXACT"

    await db.flush()


async def get_cost_summary(db: AsyncSession) -> CostSummaryDTO:
    """Aggregate fleet-wide costs and unknown-usage counts grouped by

    agent_id, team, model_name, and run_id.
    """
    # 1. Fetch all runs
    runs_res = await db.execute(select(Run).order_by(Run.started_at.desc()))
    runs = list(runs_res.scalars().all())
    run_map = {r.run_id: r for r in runs}

    # 2. Fetch all agents
    agents_res = await db.execute(select(Agent))
    agents = list(agents_res.scalars().all())
    agent_display_names = {a.agent_id: a.display_name for a in agents}

    # 3. Fetch all spans
    spans_res = await db.execute(select(Span))
    spans = list(spans_res.scalars().all())

    # Overall totals
    total_tokens = sum((s.input_tokens or 0) + (s.output_tokens or 0) for s in spans)
    known_costs = [
        s.direct_cost_usd for s in spans if s.direct_cost_usd is not None
    ]
    total_known_cost = float(sum(known_costs, Decimal(0)))

    unknown_usage_spans_count = sum(
        1
        for s in spans
        if s.span_type == "LLM"
        and (s.cost_basis == "UNKNOWN" or s.direct_cost_usd is None)
    )

    # Breakdown by agent
    agent_spans: dict[str, list[Span]] = defaultdict(list)
    for s in spans:
        agent_spans[s.agent_id].append(s)

    by_agent: list[CostBreakdownItemDTO] = []
    for agent_id, a_spans in sorted(agent_spans.items(), key=lambda x: x[0]):
        runs_for_agent = {s.run_id for s in a_spans}
        input_t = sum(s.input_tokens or 0 for s in a_spans)
        output_t = sum(s.output_tokens or 0 for s in a_spans)
        costs = [s.direct_cost_usd for s in a_spans if s.direct_cost_usd is not None]
        cost_sum = sum(costs, Decimal(0))
        unknowns = sum(
            1
            for s in a_spans
            if s.span_type == "LLM"
            and (s.cost_basis == "UNKNOWN" or s.direct_cost_usd is None)
        )
        total_cost = (
            None if (unknowns > 0 and cost_sum == 0)
            else round(float(cost_sum), 6)
        )
        by_agent.append(
            CostBreakdownItemDTO(
                key=agent_id,
                label=agent_display_names.get(agent_id, agent_id),
                run_count=len(runs_for_agent),
                span_count=len(a_spans),
                input_tokens=input_t,
                output_tokens=output_t,
                total_cost_usd=total_cost,
                unknown_spans_count=unknowns,
            )
        )
    by_agent.sort(
        key=lambda item: (item.total_cost_usd is not None, item.total_cost_usd or 0.0),
        reverse=True,
    )

    # Breakdown by team
    team_spans: dict[str, list[Span]] = defaultdict(list)
    team_runs: dict[str, set[str]] = defaultdict(set)
    for r in runs:
        team_runs[r.team].add(r.run_id)
    for s in spans:
        parent_run = run_map.get(s.run_id)
        team_name = parent_run.team if parent_run else "default"
        team_spans[team_name].append(s)
        team_runs[team_name].add(s.run_id)

    all_teams = sorted(set(team_runs.keys()) | set(team_spans.keys()))
    by_team: list[CostBreakdownItemDTO] = []
    for team in all_teams:
        t_spans = team_spans[team]
        r_count = len(team_runs[team])
        input_t = sum(s.input_tokens or 0 for s in t_spans)
        output_t = sum(s.output_tokens or 0 for s in t_spans)
        costs = [s.direct_cost_usd for s in t_spans if s.direct_cost_usd is not None]
        cost_sum = sum(costs, Decimal(0))
        unknowns = sum(
            1
            for s in t_spans
            if s.span_type == "LLM"
            and (s.cost_basis == "UNKNOWN" or s.direct_cost_usd is None)
        )
        total_cost = (
            None if (unknowns > 0 and cost_sum == 0)
            else round(float(cost_sum), 6)
        )
        by_team.append(
            CostBreakdownItemDTO(
                key=team,
                label=team,
                run_count=r_count,
                span_count=len(t_spans),
                input_tokens=input_t,
                output_tokens=output_t,
                total_cost_usd=total_cost,
                unknown_spans_count=unknowns,
            )
        )
    by_team.sort(
        key=lambda item: (item.total_cost_usd is not None, item.total_cost_usd or 0.0),
        reverse=True,
    )

    # Breakdown by model
    model_spans: dict[str, list[Span]] = defaultdict(list)
    for s in spans:
        if s.model_name:
            model_spans[s.model_name].append(s)
        elif s.span_type == "LLM":
            model_spans["unknown"].append(s)

    by_model: list[CostBreakdownItemDTO] = []
    for model_name, m_spans in sorted(model_spans.items(), key=lambda x: x[0]):
        runs_for_model = {s.run_id for s in m_spans}
        input_t = sum(s.input_tokens or 0 for s in m_spans)
        output_t = sum(s.output_tokens or 0 for s in m_spans)
        costs = [s.direct_cost_usd for s in m_spans if s.direct_cost_usd is not None]
        cost_sum = sum(costs, Decimal(0))
        unknowns = sum(
            1
            for s in m_spans
            if s.cost_basis == "UNKNOWN" or s.direct_cost_usd is None
        )
        total_cost = (
            None if (unknowns > 0 and cost_sum == 0)
            else round(float(cost_sum), 6)
        )
        by_model.append(
            CostBreakdownItemDTO(
                key=model_name,
                label=model_name,
                run_count=len(runs_for_model),
                span_count=len(m_spans),
                input_tokens=input_t,
                output_tokens=output_t,
                total_cost_usd=total_cost,
                unknown_spans_count=unknowns,
            )
        )
    by_model.sort(
        key=lambda item: (item.total_cost_usd is not None, item.total_cost_usd or 0.0),
        reverse=True,
    )

    # Breakdown by run
    run_spans: dict[str, list[Span]] = defaultdict(list)
    for s in spans:
        run_spans[s.run_id].append(s)

    by_run: list[CostBreakdownItemDTO] = []
    seen_run_ids: set[str] = set()
    for r in runs:
        seen_run_ids.add(r.run_id)
        r_spans = run_spans.get(r.run_id, [])
        input_t = sum(s.input_tokens or 0 for s in r_spans)
        output_t = sum(s.output_tokens or 0 for s in r_spans)
        unknowns = sum(
            1
            for s in r_spans
            if s.span_type == "LLM"
            and (s.cost_basis == "UNKNOWN" or s.direct_cost_usd is None)
        )
        total_cost = (
            round(float(r.total_cost_usd), 6)
            if r.total_cost_usd is not None
            else None
        )
        by_run.append(
            CostBreakdownItemDTO(
                key=r.run_id,
                label=r.run_id,
                run_count=1,
                span_count=len(r_spans),
                input_tokens=input_t,
                output_tokens=output_t,
                total_cost_usd=total_cost,
                unknown_spans_count=unknowns,
            )
        )

    # Any orphan runs in run_spans not in runs
    for r_id, r_spans in run_spans.items():
        if r_id not in seen_run_ids:
            input_t = sum(s.input_tokens or 0 for s in r_spans)
            output_t = sum(s.output_tokens or 0 for s in r_spans)
            costs = [s.direct_cost_usd for s in r_spans if s.direct_cost_usd is not None]
            cost_sum = sum(costs, Decimal(0))
            unknowns = sum(
                1
                for s in r_spans
                if s.span_type == "LLM"
                and (s.cost_basis == "UNKNOWN" or s.direct_cost_usd is None)
            )
            total_cost = (
                None if (unknowns > 0 and cost_sum == 0)
                else round(float(cost_sum), 6)
            )
            by_run.append(
                CostBreakdownItemDTO(
                    key=r_id,
                    label=r_id,
                    run_count=1,
                    span_count=len(r_spans),
                    input_tokens=input_t,
                    output_tokens=output_t,
                    total_cost_usd=total_cost,
                    unknown_spans_count=unknowns,
                )
            )

    return CostSummaryDTO(
        total_known_cost_usd=round(total_known_cost, 6),
        total_tokens=total_tokens,
        unknown_usage_spans_count=unknown_usage_spans_count,
        by_agent=by_agent,
        by_team=by_team,
        by_model=by_model,
        by_run=by_run,
    )


__all__ = [
    "DEFAULT_PRICING_SEEDS",
    "calculate_run_costs",
    "get_cost_summary",
    "seed_default_pricing",
]
