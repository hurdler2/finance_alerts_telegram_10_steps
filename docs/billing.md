# Billing & Subscription — Finance Alerts

## 1. Plans

| Plan | Price | Sources | Channels | Latency | Custom Keywords |
|------|-------|---------|----------|---------|-----------------|
| Free (trial) | $0 | 5 | 1 | 5 min | No |
| Basic | $19/mo | 10 | 1 | 5 min | No |
| Pro | $49/mo | 20 | 3 | 1 min | Yes |
| Team | $149/mo | All | 10 | 1 min | Yes + webhook |

Trial: 14 days on Free, full Basic features. No card required.

---

## 2. Stripe Setup (One-time)

### 2.1 Create products in Stripe Dashboard

```
Product: Finance Alerts Basic
  Price: $19.00 / month  → copy Price ID → STRIPE_BASIC_PRICE_ID

Product: Finance Alerts Pro
  Price: $49.00 / month  → copy Price ID → STRIPE_PRO_PRICE_ID
```

### 2.2 Configure webhook endpoint

In Stripe Dashboard → Developers → Webhooks → Add endpoint:

```
URL:    https://yourdomain.com/stripe/webhook
Events: customer.subscription.created
        customer.subscription.updated
        customer.subscription.deleted
        invoice.payment_failed
```

Copy the **Signing secret** → `STRIPE_WEBHOOK_SECRET` in `.env`.

### 2.3 Set .env values

```bash
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_BASIC_PRICE_ID=price_...
STRIPE_PRO_PRICE_ID=price_...
```

---

## 3. Subscription Lifecycle

```
User registers
  └─ POST /auth/register  →  User row created

User subscribes
  └─ Frontend: Stripe Checkout session
     (create via Stripe SDK with price_id + customer_id)
  └─ Stripe fires: customer.subscription.created
     → /stripe/webhook syncs → Subscription row: status=active

Payment renews monthly
  └─ Stripe fires: customer.subscription.updated
     → period_start/period_end updated

Payment fails
  └─ Stripe fires: invoice.payment_failed
     → status=past_due
     → service continues 3-day grace period (Stripe dunning)

User cancels
  └─ Stripe fires: customer.subscription.deleted
     → status=canceled, canceled_at=now
     → service ends at period_end (access until then)
```

---

## 4. Webhook Event Handling

| Stripe Event | Local Action |
|--------------|-------------|
| `customer.subscription.created` | Insert/update Subscription row, set plan + status |
| `customer.subscription.updated` | Update plan, status, period dates |
| `customer.subscription.deleted` | Set status=canceled, record canceled_at |
| `invoice.payment_failed` | Set status=past_due |

All events are idempotent — re-delivery is safe.

---

## 5. Plan Enforcement (v2 roadmap)

For MVP, plan enforcement is manual/honor-based. In v2:
- Middleware checks `subscription.status` on each API call
- `past_due` → allow 3-day grace, then block alerts
- `canceled` → block immediately after `period_end`
- `active` → full access per plan limits

---

## 6. Testing Stripe Locally

```bash
# Install Stripe CLI
brew install stripe/stripe-cli/stripe

# Forward webhooks to local server
stripe listen --forward-to localhost:8000/stripe/webhook

# Trigger test events
stripe trigger customer.subscription.created
stripe trigger invoice.payment_failed
```

---

## 7. Security Notes

- Stripe webhook signature is always verified via `stripe.Webhook.construct_event()`
- `STRIPE_SECRET_KEY` is never logged or returned in API responses
- Use `sk_test_` keys in development, `sk_live_` only in production
- Rotate keys immediately if compromised (Stripe Dashboard → API Keys)
