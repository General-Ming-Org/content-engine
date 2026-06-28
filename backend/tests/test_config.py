"""Settings helpers."""
from config import Settings


def test_effective_smtp_host_resend_default():
    s = Settings(smtp_host="smtp.gmail.com", smtp_username="resend", smtp_password="x")
    assert s.effective_smtp_host == "smtp.resend.com"


def test_effective_smtp_host_explicit_override():
    s = Settings(smtp_host="smtp.custom.example", smtp_username="resend", smtp_password="x")
    assert s.effective_smtp_host == "smtp.custom.example"
