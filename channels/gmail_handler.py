"""
Gmail handler for email channel.
Integrates with Gmail API and Google Pub/Sub for push notifications.
"""

import os
import base64
import logging
from typing import Optional
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify'
]


class GmailHandler:
    """Handler for Gmail email channel."""

    def __init__(self):
        self.credentials_path = os.getenv("GMAIL_CREDENTIALS_JSON")
        self.pubsub_topic = os.getenv("GMAIL_PUBSUB_TOPIC")
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Gmail API."""
        creds = None

        # Load credentials from file if available
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)

        # If no valid credentials, authenticate
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif self.credentials_path and os.path.exists(self.credentials_path):
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save credentials for next run
            if creds:
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())

        if creds:
            self.service = build('gmail', 'v1', credentials=creds)
            logger.info("Gmail API authenticated successfully")
        else:
            logger.warning("Gmail authentication failed - email channel disabled")

    async def setup_push_notifications(self, topic_name: str):
        """Set up Gmail push notifications via Pub/Sub."""
        if not self.service:
            logger.error("Gmail service not initialized")
            return

        try:
            request = {
                'labelIds': ['INBOX'],
                'topicName': topic_name
            }
            self.service.users().watch(userId='me', body=request).execute()
            logger.info(f"Gmail push notifications enabled for topic: {topic_name}")
        except HttpError as e:
            logger.error(f"Failed to setup Gmail push notifications: {e}")

    async def process_notification(self, pubsub_message: dict) -> list[dict]:
        """Process a Pub/Sub notification and return normalized messages."""
        if not self.service:
            return []

        try:
            # Decode the Pub/Sub message
            data = base64.b64decode(pubsub_message.get('data', '')).decode('utf-8')
            history_id = pubsub_message.get('attributes', {}).get('historyId')

            # Get new messages since history_id
            results = self.service.users().history().list(
                userId='me',
                startHistoryId=history_id,
                historyTypes=['messageAdded']
            ).execute()

            messages = []
            for history in results.get('history', []):
                for msg_added in history.get('messagesAdded', []):
                    msg_id = msg_added['message']['id']
                    message = await self.get_message(msg_id)
                    if message:
                        messages.append(message)

            return messages

        except Exception as e:
            logger.error(f"Failed to process Gmail notification: {e}", exc_info=True)
            return []

    async def get_message(self, message_id: str) -> Optional[dict]:
        """Get a specific message and normalize it."""
        if not self.service:
            return None

        try:
            msg = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()

            headers = {h['name']: h['value'] for h in msg['payload']['headers']}

            return {
                "channel": "email",
                "channel_message_id": message_id,
                "customer_email": self._extract_email(headers.get('From', '')),
                "customer_name": self._extract_name(headers.get('From', '')),
                "subject": headers.get('Subject', ''),
                "content": self._extract_body(msg['payload']),
                "thread_id": msg.get('threadId'),
                "received_at": msg.get('internalDate'),
                "metadata": {
                    "labels": msg.get('labelIds', []),
                    "snippet": msg.get('snippet', ''),
                }
            }

        except HttpError as e:
            logger.error(f"Failed to get Gmail message {message_id}: {e}")
            return None

    async def send_reply(
        self,
        to_email: str,
        subject: str,
        body: str,
        thread_id: Optional[str] = None
    ):
        """Send an email reply."""
        if not self.service:
            logger.error("Gmail service not initialized")
            return

        try:
            message = MIMEText(body)
            message['to'] = to_email
            message['subject'] = subject

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

            send_body = {'raw': raw_message}
            if thread_id:
                send_body['threadId'] = thread_id

            self.service.users().messages().send(
                userId='me',
                body=send_body
            ).execute()

            logger.info(f"Email sent to {to_email}")

        except HttpError as e:
            logger.error(f"Failed to send email to {to_email}: {e}")

    def _extract_body(self, payload: dict) -> str:
        """Extract email body from MIME payload."""
        if 'body' in payload and payload['body'].get('data'):
            return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')

        # Handle multipart
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if part['body'].get('data'):
                        return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')

                # Recursively check nested parts
                if 'parts' in part:
                    body = self._extract_body(part)
                    if body:
                        return body

        return ""

    def _extract_email(self, from_header: str) -> str:
        """Extract email address from From header."""
        if '<' in from_header and '>' in from_header:
            start = from_header.index('<') + 1
            end = from_header.index('>')
            return from_header[start:end]
        return from_header.strip()

    def _extract_name(self, from_header: str) -> str:
        """Extract name from From header."""
        if '<' in from_header:
            return from_header[:from_header.index('<')].strip().strip('"')
        return ""
