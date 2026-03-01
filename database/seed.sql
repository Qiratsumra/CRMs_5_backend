-- Seed data for knowledge_base table
-- This will be populated with product documentation

-- Product Overview
INSERT INTO knowledge_base (title, content, category) VALUES
('TechCorp Product Overview', 'TechCorp provides enterprise software solutions including CRM systems, analytics platforms, and customer success tools. Our flagship product is the Customer Success Platform which helps businesses manage customer relationships, track support tickets, and analyze customer sentiment across multiple channels.', 'product_overview'),

-- Getting Started
('Getting Started with TechCorp Platform', 'To get started with TechCorp Platform: 1) Create an account at app.techcorp.com, 2) Complete the onboarding wizard, 3) Connect your communication channels (email, WhatsApp, web forms), 4) Import your customer data, 5) Configure your team settings. The platform is ready to use immediately after setup.', 'getting_started'),

-- Features
('Multi-Channel Support', 'TechCorp Platform supports customer communication across email, WhatsApp, and web forms. All conversations are unified in a single interface, allowing seamless cross-channel support. Customers can start a conversation on one channel and continue on another without losing context.', 'features'),

('AI-Powered Agent', 'Our AI agent automatically handles customer inquiries using natural language processing and machine learning. It searches the knowledge base, analyzes sentiment, creates tickets, and provides personalized responses. The agent escalates complex issues to human agents when needed.', 'features'),

('Ticket Management', 'Create, track, and resolve customer support tickets. Tickets are automatically categorized by priority (low, medium, high, urgent) and type (technical, billing, general, bug_report, feedback). View ticket history, add notes, and track resolution times.', 'features'),

('Knowledge Base Search', 'Powerful semantic search across your documentation using vector embeddings. The AI agent automatically searches relevant articles to answer customer questions. Supports categories, tags, and version control.', 'features'),

-- Technical Support
('System Requirements', 'TechCorp Platform is cloud-based and requires: Modern web browser (Chrome, Firefox, Safari, Edge), Stable internet connection (minimum 1 Mbps), JavaScript enabled. Mobile apps available for iOS 14+ and Android 10+.', 'technical'),

('API Access', 'REST API available for enterprise customers. Includes endpoints for customer management, ticket creation, conversation history, and analytics. Rate limits: 1000 requests/hour for standard plans, 10000 requests/hour for enterprise. API documentation at docs.techcorp.com/api', 'technical'),

('Data Security', 'All data is encrypted in transit (TLS 1.3) and at rest (AES-256). SOC 2 Type II certified. GDPR and CCPA compliant. Regular security audits and penetration testing. Data backups every 6 hours with 30-day retention.', 'technical'),

('Integration Options', 'Integrate with popular tools: Slack, Microsoft Teams, Salesforce, HubSpot, Zendesk, Jira. Webhooks available for real-time event notifications. OAuth 2.0 authentication supported.', 'technical'),

-- Billing
('Pricing Plans', 'Starter: $29/month (1 user, 100 tickets/month), Professional: $99/month (5 users, 1000 tickets/month), Enterprise: Custom pricing (unlimited users and tickets). All plans include 14-day free trial. Annual billing saves 20%.', 'billing'),

('Payment Methods', 'We accept credit cards (Visa, Mastercard, Amex), PayPal, and bank transfers (enterprise only). Billing is monthly or annual. Invoices sent via email. Payment processing by Stripe.', 'billing'),

('Refund Policy', 'Full refund within 14 days of initial purchase if not satisfied. No refunds for renewals. Contact support@techcorp.com to request refund. Processing time: 5-7 business days.', 'billing'),

-- Troubleshooting
('Login Issues', 'If you cannot log in: 1) Verify your email and password, 2) Check for typos, 3) Try password reset at app.techcorp.com/reset, 4) Clear browser cache and cookies, 5) Try incognito/private mode, 6) Check if account is active. Contact support if issues persist.', 'troubleshooting'),

('Email Not Receiving', 'If not receiving emails from TechCorp: 1) Check spam/junk folder, 2) Add noreply@techcorp.com to contacts, 3) Verify email address in account settings, 4) Check email filters/rules, 5) Try alternative email address. Email delivery typically within 5 minutes.', 'troubleshooting'),

('WhatsApp Connection Issues', 'To fix WhatsApp connection: 1) Ensure phone has internet connection, 2) Verify WhatsApp is updated to latest version, 3) Check if number is correctly registered, 4) Re-scan QR code in settings, 5) Restart WhatsApp app. Connection typically restores within 2 minutes.', 'troubleshooting'),

('Slow Performance', 'If platform is slow: 1) Check internet connection speed, 2) Close unnecessary browser tabs, 3) Clear browser cache, 4) Disable browser extensions, 5) Try different browser, 6) Check system status at status.techcorp.com. Expected load time: under 3 seconds.', 'troubleshooting'),

-- Account Management
('Changing Password', 'To change password: 1) Go to Settings > Security, 2) Click Change Password, 3) Enter current password, 4) Enter new password (minimum 8 characters, include uppercase, lowercase, number, special character), 5) Confirm new password, 6) Click Save. You will be logged out and need to log in again.', 'account'),

('Adding Team Members', 'To add team members: 1) Go to Settings > Team, 2) Click Invite Member, 3) Enter email address, 4) Select role (Admin, Agent, Viewer), 5) Click Send Invite. They will receive an email invitation. Limit based on your plan.', 'account'),

('Deleting Account', 'To delete account: 1) Go to Settings > Account, 2) Scroll to Danger Zone, 3) Click Delete Account, 4) Confirm by typing account name, 5) Click Permanently Delete. This action cannot be undone. All data will be deleted within 30 days.', 'account'),

-- Best Practices
('Response Time Best Practices', 'Aim to respond to customer inquiries within: Email - 24 hours, WhatsApp - 1 hour, Web forms - 4 hours. Set up auto-replies for after-hours. Use templates for common questions. Prioritize urgent tickets. Monitor response time metrics in dashboard.', 'best_practices'),

('Escalation Guidelines', 'Escalate to human agent when: Customer explicitly requests human support, Legal/attorney/lawsuit mentioned, Sentiment score below 0.3, Issue requires refund or pricing discussion, Technical issue beyond knowledge base, Security concern reported.', 'best_practices');
