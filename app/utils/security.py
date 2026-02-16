import re
from urllib.parse import urlparse

# List of keywords that might indicate inappropriate content
# This is a basic list and can be expanded.
# List of keywords that might indicate inappropriate content
# This is a basic list and can be expanded.
BAD_KEYWORDS = [
    # "porn", "xxx", "sex", "nude", "naked", "erotic", "adult", 
    # "casino", "gambling", "betting", "poker", "rummy", "lottery",
    # "malware", "virus", "phishing", "trojan", "spyware",
    # "hack", "crack", "warez", "hentai", "camgirl", "escort",
    # "faucet", "crypto-giveaway" # common spam
]

# List of domains known for spam, disposable emails, or specific bad sites
# This should be updated regularly or fetched from an external source if possible.
BAD_DOMAINS = [
    # Add known bad domains here
    # "malicious-site.com",
    # "adult-site.com",
    # "example-phishing.com",
    # "bad-content.org"
]

def is_unsafe_url(url: str) -> tuple[bool, str | None]:
    """
    Checks if a URL is unsafe based on a local blocklist of keywords and domains.
    
    Args:
        url (str): The URL to check.
        
    Returns:
        tuple[bool, str | None]: (is_unsafe, reason)
        - is_unsafe: True if the URL is blocked, False otherwise.
        - reason: A string explaining why it was blocked, or None.
    """
    if not url:
        return False, None
        
    url_lower = url.lower()
    
    # 1. Check for bad keywords in the URL string
    for keyword in BAD_KEYWORDS:
        # We use a simple containment check. 
        # For more precision, we could use regex with word boundaries, 
        # but URLs often combine words (e.g. "sexcam").
        if keyword in url_lower:
             return True, f"URL contains possibly inappropriate content: '{keyword}'"

    # 2. Check domain against blocklist
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Remove port if present
        if ':' in domain:
            domain = domain.split(':')[0]
            
        if domain in BAD_DOMAINS:
            return True, f"Domain '{domain}' is blocked."
            
        # Check subdomains
        for bad_domain in BAD_DOMAINS:
            if domain.endswith("." + bad_domain) or domain == bad_domain:
                 return True, f"Domain '{domain}' is blocked."

    except Exception:
        # If URL parsing fails, might be prudent to block or just log
        pass

    return False, None
