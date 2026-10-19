"""确定性的产品查询工具。"""

from collections.abc import Sequence

from customer_needs_agent.models import Product, ProductMatch, QueryProductsArgs, Urgency

DELIVERY_LIMITS: dict[Urgency, int | None] = {
    Urgency.CRITICAL: 7,
    Urgency.HIGH: 14,
    Urgency.MEDIUM: 30,
    Urgency.LOW: None,
}


def _contains(text: str, candidate: str) -> bool:
    return text.casefold() in candidate.casefold() or candidate.casefold() in text.casefold()


def _industry_matches(business_type: str, industries: Sequence[str]) -> bool:
    return "通用" in industries or any(_contains(business_type, item) for item in industries)


def _capability_matches(required: Sequence[str], available: Sequence[str]) -> list[str]:
    return [
        need for need in required if any(_contains(need, capability) for capability in available)
    ]


def query_products(
    args: QueryProductsArgs,
    products: Sequence[Product],
    *,
    limit: int = 3,
) -> list[ProductMatch]:
    """先应用预算、行业、交付周期硬约束，再按能力覆盖率稳定排序。"""

    delivery_limit = DELIVERY_LIMITS[args.urgency]
    matches: list[ProductMatch] = []

    for product in products:
        if product.annual_price > args.budget_max:
            continue
        if delivery_limit is not None and product.delivery_days > delivery_limit:
            continue
        if not _industry_matches(args.business_type, product.industries):
            continue

        matched = _capability_matches(args.required_capabilities, product.capabilities)
        if args.required_capabilities and not matched:
            continue

        coverage = len(matched) / max(len(args.required_capabilities), 1)
        budget_efficiency = 1 - (product.annual_price / max(args.budget_max, 1))
        score = round(coverage * 80 + max(budget_efficiency, 0) * 20, 2)
        matches.append(ProductMatch(product=product, score=score, matched_capabilities=matched))

    matches.sort(key=lambda item: (-item.score, item.product.annual_price, item.product.id))
    return matches[:limit]
