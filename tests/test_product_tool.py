from customer_needs_agent.catalog import load_catalog
from customer_needs_agent.models import QueryProductsArgs, Urgency
from customer_needs_agent.product_tool import query_products


def test_query_applies_budget_and_capability_constraints() -> None:
    matches = query_products(
        QueryProductsArgs(
            business_type="零售",
            budget_max=30_000,
            urgency=Urgency.HIGH,
            required_capabilities=["客户管理"],
        ),
        load_catalog(),
    )
    assert [item.product.id for item in matches] == ["crm-starter"]


def test_query_returns_empty_when_delivery_deadline_is_impossible() -> None:
    matches = query_products(
        QueryProductsArgs(
            business_type="制造",
            budget_max=300_000,
            urgency=Urgency.CRITICAL,
            required_capabilities=["生产计划"],
        ),
        load_catalog(),
    )
    assert matches == []


def test_query_order_is_deterministic() -> None:
    args = QueryProductsArgs(
        business_type="互联网",
        budget_max=250_000,
        urgency=Urgency.LOW,
        required_capabilities=[],
    )
    first = query_products(args, load_catalog())
    second = query_products(args, load_catalog())
    assert [item.product.id for item in first] == [item.product.id for item in second]
