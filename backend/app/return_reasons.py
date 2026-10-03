"""Synthetic customer-written return reasons, used to generate realistic demo data.

Each true cause (what actually went wrong) has several ways customers describe it. Because
customers often pick the wrong dropdown option, the written text is the more reliable
signal, which is what the return-routing model learns from.
"""

import random
from dataclasses import dataclass

from app.domain.returns import ReturnReason

TEMPLATES: dict[ReturnReason, list[str]] = {
    ReturnReason.DAMAGED: [
        "The box arrived crushed and the {product} was cracked.",
        "Package was soaked and torn when it got here, {product} has dents all over.",
        "Outer carton was ripped open by the courier and the {product} is scratched.",
        "Delivery guy threw it over the gate, the {product} came broken.",
        "Shipping damage, the corner of the {product} is smashed.",
        "Arrived with a big dent, looks like it was dropped in transit.",
    ],
    ReturnReason.DEFECTIVE: [
        "There's a manufacturing flaw, the {product} is faulty out of the box.",
        "Quality problem, the {product} started falling apart within days.",
    ],
    ReturnReason.WRONG_ITEM: [
        "I ordered the {product} but received something completely different.",
        "Wrong item in the box, this is not what I bought.",
        "Got a different color and model than what I ordered.",
        "The label says {product} but the item inside is something else.",
        "Received someone else's order, not my {product}.",
    ],
    ReturnReason.MISSING_PARTS: [
        "The {product} came without the charger and cable.",
        "Box was missing the screws and the manual.",
        "Only one piece in the box, the set should have more.",
        "Accessories listed on the page were not included.",
        "Half the parts are missing, can't assemble it.",
    ],
    ReturnReason.NOT_AS_DESCRIBED: [
        "The {product} looks nothing like the photos on the listing.",
        "Material feels cheap, the description said premium quality.",
        "Listing said it's waterproof but it clearly isn't.",
        "Specs don't match the page, the screen is smaller than advertised.",
        "Color is very different from what was shown online.",
    ],
    ReturnReason.SIZE_FIT: [
        "Too small, I need one size up.",
        "The {product} runs large, doesn't fit well.",
        "Fits too tight around the shoulders.",
        "Length is too short for me, want to exchange for a bigger size.",
        "Sizing chart was off, this is way too loose.",
    ],
    ReturnReason.LATE_DELIVERY: [
        "Arrived two weeks late, I needed it for a trip and no longer need it.",
        "Delivery was delayed so many times I bought it elsewhere.",
        "Tracking was stuck for days and it came after the event.",
        "Took far longer than the promised delivery date.",
    ],
    ReturnReason.CHANGED_MIND: [
        "Changed my mind, I don't need the {product} anymore.",
        "Found a better price somewhere else.",
        "Ordered by mistake, would like to return it.",
        "It's fine but I just don't like it as much as I thought.",
        "Bought it as a gift and they already have one.",
    ],
}

# Defects that only make sense for some kinds of products.
DEVICE_DEFECTS = [
    "The {product} stopped working after two days.",
    "It won't turn on at all, tried charging it overnight.",
    "{product} keeps shutting off randomly, seems faulty.",
    "Battery drains in an hour, this unit is defective.",
    "Makes a loud buzzing noise, something inside is broken.",
]
DEVICES = {"electronics", "home", "beauty"}
BOOK_DEFECTS = [
    "Several pages are blank and some are printed upside down.",
    "The binding came apart the first time I opened it.",
    "Pages are printed out of order, a whole chapter is missing.",
]

SOFT_GOODS_DEFECTS = [
    "The zipper broke the first time I used it.",
    "Stitching came apart after one wash.",
    "Sole started peeling off within a week.",
]
SOFT_GOODS = {"apparel", "sports"}

# Real customers are often vague or ambiguous. These texts carry little or no signal about
# the cause, which keeps any model honest: it can't reach 100% accuracy on them.
VAGUE_TEXTS = [
    "Item has an issue, please process my return.",
    "Not what I expected.",
    "I want to return this.",
    "There's a problem with my order.",
    "Please take this back.",
    "Not satisfied with this purchase.",
]
VAGUE_RATE = 0.10

# Phrases that genuinely fit more than one cause.
AMBIGUOUS_TEXTS: dict[ReturnReason, list[str]] = {
    ReturnReason.DAMAGED: ["It arrived broken.", "Came broken, the {product} doesn't work."],
    ReturnReason.DEFECTIVE: ["It arrived broken.", "Came broken, the {product} doesn't work."],
    ReturnReason.WRONG_ITEM: ["This isn't what I ordered at all."],
    ReturnReason.NOT_AS_DESCRIBED: ["This isn't what I ordered at all."],
}
AMBIGUOUS_RATE = 0.10

OPENERS = ["", "", "", "Hi, ", "Hello, ", "Unfortunately, ", "Not happy. "]
CLOSERS = [
    "",
    "",
    "",
    " Please refund.",
    " Please help.",
    " Want my money back.",
    " Very disappointed.",
]
NEGATIVE_OPENERS = {"Not happy. "}
NEGATIVE_CLOSERS = {" Want my money back.", " Very disappointed."}

# How often the customer picks the dropdown option that matches what actually happened.
DROPDOWN_ACCURACY = 0.78

# Common mix-ups: what customers pick instead of the true cause.
CONFUSIONS: dict[ReturnReason, list[ReturnReason]] = {
    ReturnReason.DAMAGED: [ReturnReason.DEFECTIVE, ReturnReason.NOT_AS_DESCRIBED],
    ReturnReason.DEFECTIVE: [ReturnReason.DAMAGED, ReturnReason.NOT_AS_DESCRIBED],
    ReturnReason.WRONG_ITEM: [ReturnReason.NOT_AS_DESCRIBED, ReturnReason.CHANGED_MIND],
    ReturnReason.MISSING_PARTS: [ReturnReason.DEFECTIVE, ReturnReason.NOT_AS_DESCRIBED],
    ReturnReason.NOT_AS_DESCRIBED: [ReturnReason.DEFECTIVE, ReturnReason.CHANGED_MIND],
    ReturnReason.SIZE_FIT: [ReturnReason.NOT_AS_DESCRIBED, ReturnReason.CHANGED_MIND],
    ReturnReason.LATE_DELIVERY: [ReturnReason.CHANGED_MIND, ReturnReason.DAMAGED],
    ReturnReason.CHANGED_MIND: [ReturnReason.SIZE_FIT, ReturnReason.NOT_AS_DESCRIBED],
}

# Rough real-world share of each true cause.
CAUSE_WEIGHTS: dict[ReturnReason, int] = {
    ReturnReason.SIZE_FIT: 24,
    ReturnReason.DEFECTIVE: 16,
    ReturnReason.CHANGED_MIND: 15,
    ReturnReason.DAMAGED: 14,
    ReturnReason.NOT_AS_DESCRIBED: 12,
    ReturnReason.WRONG_ITEM: 8,
    ReturnReason.MISSING_PARTS: 6,
    ReturnReason.LATE_DELIVERY: 5,
}

APPAREL_ONLY = {ReturnReason.SIZE_FIT}


@dataclass(frozen=True)
class SampledReason:
    true_cause: ReturnReason  # what actually happened
    picked: ReturnReason  # what the customer chose in the dropdown
    text: str  # what the customer wrote
    upset: bool  # whether the customer sounds angry


def sample_return_reason(rng: random.Random, product_name: str, category: str) -> SampledReason:
    """Simulate one customer's return request."""
    causes = [c for c in CAUSE_WEIGHTS if category in SOFT_GOODS or c not in APPAREL_ONLY]
    true_cause = rng.choices(causes, weights=[CAUSE_WEIGHTS[c] for c in causes])[0]

    picked = true_cause if rng.random() < DROPDOWN_ACCURACY else rng.choice(CONFUSIONS[true_cause])

    templates = TEMPLATES[true_cause]
    if true_cause is ReturnReason.DEFECTIVE:
        if category in DEVICES:
            templates = templates + DEVICE_DEFECTS
        elif category in SOFT_GOODS:
            templates = templates + SOFT_GOODS_DEFECTS
        elif category == "books":
            templates = templates + BOOK_DEFECTS
    roll = rng.random()
    if roll < VAGUE_RATE:
        templates = VAGUE_TEXTS
    elif roll < VAGUE_RATE + AMBIGUOUS_RATE and true_cause in AMBIGUOUS_TEXTS:
        templates = AMBIGUOUS_TEXTS[true_cause]

    body = rng.choice(templates).format(product=product_name.lower())
    opener, closer = rng.choice(OPENERS), rng.choice(CLOSERS)
    if opener.endswith(", ") and not body.startswith("I "):
        body = body[0].lower() + body[1:]
    text = f"{opener}{body}{closer}"
    return SampledReason(
        true_cause=true_cause,
        picked=picked,
        text=text[0].upper() + text[1:],
        upset=opener in NEGATIVE_OPENERS or closer in NEGATIVE_CLOSERS,
    )
