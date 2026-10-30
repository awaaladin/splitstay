package com.splitpay.app.data

/** Mirrors apps/web/banks.py: the API has no bank-list endpoint. */
val BANKS = listOf(
    "044" to "Access Bank",
    "063" to "Access Bank (Diamond)",
    "011" to "First Bank of Nigeria",
    "214" to "First City Monument Bank",
    "058" to "Guaranty Trust Bank",
    "050" to "Ecobank Nigeria",
    "070" to "Fidelity Bank",
    "082" to "Keystone Bank",
    "076" to "Polaris Bank",
    "221" to "Stanbic IBTC Bank",
    "232" to "Sterling Bank",
    "032" to "Union Bank of Nigeria",
    "033" to "United Bank for Africa",
    "035" to "Wema Bank",
    "057" to "Zenith Bank",
    "50211" to "Kuda Microfinance Bank",
    "50515" to "Moniepoint MFB",
    "999992" to "OPay",
    "999991" to "PalmPay",
)

/** Mirrors the Purpose choices in apps/groups/models.py. */
val PURPOSES = listOf(
    "rent" to "Rent",
    "electricity" to "Electricity (NEPA)",
    "subscription" to "Subscription",
    "family_upkeep" to "Family upkeep",
    "custom" to "Custom",
)
