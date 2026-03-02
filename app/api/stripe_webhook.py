"""
Stripe webhook handler.
Syncs subscription state to local DB on Stripe events.

Required Stripe events to enable in dashboard:
  - customer.subscription.created
  - customer.subscription.updated
  - customer.subscription.deleted
  - invoice.payment_failed
"""
from __future__ import annotations

import stripe
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import log
from app.models.user import Subscription, User

router = APIRouter(tags=["stripe"])

# Stripe plan slug resolution: price_id → plan name
def _plan_from_price(price_id: str | None) -> str:
    if not price_id:
        return "free"
    if price_id == settings.stripe_basic_price_id:
        return "basic"
    if price_id == settings.stripe_pro_price_id:
        return "pro"
    return "basic"  # unknown price → default to basic


async def _upsert_subscription(stripe_sub: dict) -> None:
    """Create or update local Subscription row from a Stripe subscription object."""
    from datetime import datetime, timezone

    customer_id: str = stripe_sub["customer"]
    stripe_sub_id: str = stripe_sub["id"]
    stripe_status: str = stripe_sub["status"]   # active | canceled | past_due | trialing

    # Map Stripe status to local status
    local_status = stripe_status  # 1:1 for now

    price_id = None
    items = stripe_sub.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id")

    plan = _plan_from_price(price_id)

    period_start = stripe_sub.get("current_period_start")
    period_end = stripe_sub.get("current_period_end")

    def _ts(unix: int | None):
        return datetime.fromtimestamp(unix, tz=timezone.utc) if unix else None

    async with AsyncSessionLocal() as session:
        # Find user by Stripe customer_id
        user_result = await session.execute(
            select(User).where(User.stripe_customer_id == customer_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            log.warning("stripe_webhook: no user found for customer", customer_id=customer_id)
            return

        # Find or create subscription
        sub_result = await session.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        )
        sub = sub_result.scalar_one_or_none()

        if sub:
            sub.stripe_subscription_id = stripe_sub_id
            sub.stripe_price_id = price_id
            sub.plan = plan
            sub.status = local_status
            sub.current_period_start = _ts(period_start)
            sub.current_period_end = _ts(period_end)
            if local_status == "canceled":
                sub.canceled_at = datetime.now(timezone.utc)
        else:
            session.add(
                Subscription(
                    user_id=user.id,
                    stripe_subscription_id=stripe_sub_id,
                    stripe_price_id=price_id,
                    plan=plan,
                    status=local_status,
                    current_period_start=_ts(period_start),
                    current_period_end=_ts(period_end),
                )
            )

        await session.commit()
        log.info(
            "stripe_webhook: subscription synced",
            user_id=user.id,
            plan=plan,
            status=local_status,
        )


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """
    Receive and verify Stripe webhook events.
    Stripe signature is validated before any processing.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not settings.stripe_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="STRIPE_WEBHOOK_SECRET not configured",
        )

    # Verify webhook signature
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except stripe.SignatureVerificationError:
        log.warning("stripe_webhook: invalid signature")
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception as exc:
        log.error("stripe_webhook: parse error", error=str(exc))
        raise HTTPException(status_code=400, detail="Webhook parse error")

    event_type: str = event["type"]
    log.info("stripe_webhook: received", event_type=event_type, event_id=event["id"])

    # ── Handle subscription lifecycle events ───────────────────────────────
    if event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        await _upsert_subscription(event["data"]["object"])

    elif event_type == "invoice.payment_failed":
        # Mark subscription as past_due
        invoice = event["data"]["object"]
        sub_id = invoice.get("subscription")
        if sub_id:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Subscription).where(
                        Subscription.stripe_subscription_id == sub_id
                    )
                )
                sub = result.scalar_one_or_none()
                if sub:
                    sub.status = "past_due"
                    await session.commit()
                    log.warning("stripe_webhook: payment failed", sub_id=sub_id)

    # Return 200 to acknowledge receipt (Stripe retries on non-2xx)
    return {"received": True}
