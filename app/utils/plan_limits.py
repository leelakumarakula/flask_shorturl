# utils/plan_limits.py
PLAN_LIMITS = {
    "free": {
        "links": 5,            # maximum short links (NOT counting QR-only)
        "qrs": 2,              # maximum QR records (qr_generated == True)
        "custom": 3,           # maximum custom short codes (custom == True)
        "analytics_limit": None, # per-url analytics cap
        "analytics_days": None,
         "edit_limit": 0
    },
    "pro": {
        "links": 200,
        "qrs": 150,
        "custom": 100,
        "analytics_limit": 5,
        "analytics_days": 30,
         "edit_limit": 5 
    },
    "enterprise": {
        "links": 1000,
        "qrs": 750,
        "custom": 500,
        "analytics_limit": 10000,
        "analytics_days": 88,
         "edit_limit": 50 
    }
}
