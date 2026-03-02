# Resend Email Setup Guide

## What Changed

We replaced SMTP (which was failing on Render) with **Resend** - a modern email API that works reliably on hosting platforms.

## Setup Steps

### 1. Verify Your Domain (Optional but Recommended)

For production, you should verify your domain in Resend:

1. Go to https://resend.com/domains
2. Click "Add Domain"
3. Add your domain (e.g., `yourdomain.com`)
4. Add the DNS records shown
5. Wait for verification (usually 5-10 minutes)
6. Update `.env`: `RESEND_FROM_EMAIL=support@yourdomain.com`

### 2. For Testing (Current Setup)

You're currently using `onboarding@resend.dev` which works for testing but:
- ⚠️ Emails may go to spam
- ⚠️ Limited to 100 emails/day
- ⚠️ Shows "via resend.dev" in email clients

Your current `.env` is configured with:
```

```

**Note**: You're using your Gmail address as the from email, but this will only work if you verify this email in Resend first.

### 3. Verify Your Email Address

Since you're using `sheikhqirat100@gmail.com`:

1. Go to https://resend.com/emails
2. Click "Verify Email"
3. Enter `sheikhqirat100@gmail.com`
4. Check your Gmail inbox for verification email
5. Click the verification link

OR use the default testing email:
```
RESEND_FROM_EMAIL=onboarding@resend.dev
```

## Render Deployment

Add these environment variables in Render dashboard:

```
RESEND_API_KEY=re_B24Uskq4_FA3eXvwJU5JBU1Qxzk9xzoY5
RESEND_FROM_EMAIL=sheikhqirat100@gmail.com
```

## Testing

Test email sending locally:

```bash
curl -X POST http://localhost:8000/support/submit \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test User",
    "email": "test@example.com",
    "category": "technical",
    "message": "This is a test support request to verify email sending"
  }'
```

Check logs for:
```
INFO - Sending email to test@example.com via Resend...
INFO - Email sent successfully to test@example.com
```

## Troubleshooting

### Email not sending?

1. Check API key is valid: https://resend.com/api-keys
2. Verify from email is verified in Resend
3. Check logs for error messages
4. Ensure `RESEND_API_KEY` is set in environment

### Emails going to spam?

- Verify your domain (don't use onboarding@resend.dev)
- Add SPF, DKIM, DMARC records (Resend provides these)

## Benefits Over SMTP

✓ No port blocking issues on Render
✓ Better deliverability
✓ Simpler API (no TLS/SSL complexity)
✓ Built-in analytics
✓ Free tier: 100 emails/day, 3,000/month

## Files Changed

- ✓ Added `channels/resend_handler.py` - New Resend email handler
- ✓ Updated `channels/web_form_handler.py` - Uses Resend instead of SMTP
- ✓ Updated `.env` - Added Resend configuration
- ✓ Updated `.env.example` - Added Resend example
- ✓ Installed `resend` package via uv

## Next Steps

1. Verify your email address in Resend dashboard
2. Test locally
3. Deploy to Render with environment variables
4. (Optional) Verify your domain for production use
