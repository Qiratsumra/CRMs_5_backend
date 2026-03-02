"""
Resend email handler for sending support responses.
More reliable than SMTP on hosting platforms like Render.
"""
import os
import logging
import resend
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class ResendHandler:
    """Handler for sending emails via Resend API."""

    def __init__(self):
        self.api_key = os.getenv("RESEND_API_KEY")
        self.from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")
        self.enabled = bool(self.api_key)

        if self.enabled:
            resend.api_key = self.api_key
            logger.info("Resend email handler initialized")
        else:
            logger.warning("Resend not configured - email sending disabled")

    def send_email(self, to_email: str, subject: str, body: str, html: bool = False):
        """Send an email via Resend API."""
        if not self.enabled:
            logger.warning(f"Cannot send email to {to_email} - Resend not configured")
            return False

        try:
            params = {
                "from": self.from_email,
                "to": [to_email],
                "subject": subject,
            }

            if html:
                params["html"] = body
            else:
                params["text"] = body

            logger.info(f"Sending email to {to_email} via Resend...")
            response = resend.Emails.send(params)

            logger.info(f"Email sent successfully to {to_email}: {subject} (ID: {response.get('id', 'N/A')})")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False


# Global instance
_resend_handler = None


def get_resend_handler() -> ResendHandler:
    """Get or create Resend handler instance."""
    global _resend_handler
    if _resend_handler is None:
        _resend_handler = ResendHandler()
    return _resend_handler
