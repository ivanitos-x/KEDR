def redact(text):
    try:
        from clap.security import redact as platform_redact
        return platform_redact(str(text))
    except ImportError:
        import re
        return re.sub(r'(?i)(token|password|secret|api[_-]?key)\s*[:=]\s*\S+', r'\1=[REDACTED]', str(text))
