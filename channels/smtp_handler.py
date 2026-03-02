"""
Simple SMTP email handler for sending support responses.
"""
import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class SMTPHandler:
    """Handler for sending emails via SMTP."""

    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.from_email = os.getenv("SMTP_FROM_EMAIL", self.smtp_user)
        self.enabled = bool(self.smtp_user and self.smtp_password)

        if not self.enabled:
            logger.warning("SMTP not configured - email sending disabled")

    def send_email(self, to_email: str, subject: str, body: str, html: bool = False):
        """Send an email via SMTP with timeout."""
        if not self.enabled:
            logger.warning(f"Cannot send email to {to_email} - SMTP not configured")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self.from_email
            msg["To"] = to_email
            msg["Subject"] = subject

            if html:
                msg.attach(MIMEText(body, "html"))
            else:
                msg.attach(MIMEText(body, "plain"))

            logger.info(f"Connecting to SMTP server {self.smtp_host}:{self.smtp_port}")
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                logger.info("Starting TLS...")
                server.starttls()
                logger.info(f"Logging in as {self.smtp_user}...")
                server.login(self.smtp_user, self.smtp_password)
                logger.info(f"Sending email to {to_email}...")
                result = server.send_message(msg)
                logger.info(f"SMTP send result: {result}")

            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True

        except OSError as e:
            if e.errno == 101:
                logger.error(f"Network unreachable - SMTP server {self.smtp_host}:{self.smtp_port} cannot be reached. Check firewall/network settings or use a transactional email service.")
            else:
                logger.error(f"Network error sending email to {to_email}: {e}")
            return False
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed for {self.smtp_user}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}", exc_info=True)
            return False


# Global instance
_smtp_handler = None


def get_smtp_handler() -> SMTPHandler:
    """Get or create SMTP handler instance."""
    global _smtp_handler
    if _smtp_handler is None:
        _smtp_handler = SMTPHandler()
    return _smtp_handler
