"""Payment provider integration.

The rest of the app depends only on the `PaymentGateway` interface, so the simulated gateway
used locally can be swapped for a real provider (Stripe, Adyen, ...) without touching
business logic, and tests can plug in a gateway that fails on purpose.
"""

import uuid
from typing import Protocol


class PaymentGatewayError(Exception):
    """The provider could not process the request (timeout, outage, decline)."""


class PaymentGateway(Protocol):
    def refund(
        self, *, order_number: str, amount_cents: int, currency: str, idempotency_key: str
    ) -> str:
        """Send money back to the customer and return the provider's reference id.

        The idempotency key is forwarded so the provider can also de-duplicate retries,
        which protects against double refunds even if our own records were lost.
        """
        ...


class SimulatedPaymentGateway:
    def refund(
        self, *, order_number: str, amount_cents: int, currency: str, idempotency_key: str
    ) -> str:
        return f"re_{uuid.uuid4().hex[:20]}"


_gateway: PaymentGateway = SimulatedPaymentGateway()


def get_payment_gateway() -> PaymentGateway:
    """FastAPI dependency. Tests override it to simulate provider behavior."""
    return _gateway
