# SaaS Support Contact Data Dictionary

> **Sample dataset** — fictional company used for demonstration purposes.
> This dictionary describes a customer support contact dataset for a fictional B2B SaaS product ("NovaDeskAI").
> It is provided as a reference input for the data quality agent.

| Variable | Definition | Data Type |
|---|---|---|
| CONTACT_ID | Unique identifier for each support contact | Integer/Number |
| CHANNEL | Channel through which the customer initiated contact (email, chat, phone, portal) | String/Text |
| CUSTOMER_JOURNEY_STAGE | Stage of the customer lifecycle at time of contact (onboarding, active, renewal, churned) | String/Text |
| CONTACT_REASON_CATEGORY | High-level category of the contact reason selected by the customer | String/Text |
| CONTACT_REASON_DETAIL | Detailed sub-reason for the contact | String/Text |
| SALES_CONTACT | True if the contact was related to a purchase or upgrade inquiry | Boolean |
| ACCOUNT_ID | Account (company) ID associated with the contact | String/Text |
| USER_ID | Individual user ID within the account who initiated contact | String/Text |
| TICKET_ID | Support ticket ID linked to this contact, if applicable | String/Text |
| CONTACT_CREATED_AT | Timestamp when the contact was created in the system | Timestamp |
| QUEUE_ENTER_AT | Timestamp when the contact entered the support queue | Timestamp |
| QUEUE_EXIT_AT | Timestamp when the contact left the queue and was assigned to an agent | Timestamp |
| RESOLVED_AT | Timestamp when the contact was marked resolved | Timestamp |
| TOTAL_HANDLING_TIME_SEC | Time in seconds from queue exit to resolution | Integer/Number |
| QUEUE_WAIT_TIME_SEC | Time in seconds the contact spent waiting in the queue | Integer/Number |
| PLAN_TIER | Subscription plan tier of the account (starter, growth, enterprise) | String/Text |
| REGION | Geographic region of the account | String/Text |
| LANGUAGE | Language of the contact | String/Text |
| NPS_SCORE | Net Promoter Score submitted by the customer (0–10) | Integer/Number |
| CSAT_SCORE | Customer Satisfaction score submitted by the customer (1–5) | Integer/Number |
| CUSTOMER_COMMENT | Free-text comment submitted by the customer in the post-contact survey | String/Text |
| FIRST_CONTACT_RESOLUTION | True if the issue was resolved in a single contact without follow-up | Boolean |
| AGENT_ID | Unique identifier of the agent who handled the contact | Integer/Number |
| AGENT_NAME | Full name of the agent | String/Text |
| AGENT_TEAM | Team the agent belongs to (tier-1, tier-2, solutions-engineering) | String/Text |
| AGENT_TENURE_MONTHS | Number of months the agent has been in the role | Integer/Number |
| AGENT_SITE | Office location of the agent | String/Text |
| AGENT_MANAGER | Name of the agent's direct manager | String/Text |
| IS_INBOUND | True if the contact was inbound (customer-initiated) | Boolean |
| IS_INTERNAL | True if the contact was an internal test or escalation | Boolean |
| IS_ESCALATED | True if the contact was escalated to a higher support tier | Boolean |
| ESCALATION_TIER | Tier to which the contact was escalated, if applicable | String/Text |
| AI_ASSISTED | True if the contact was handled or assisted by an AI agent | Boolean |
| AI_DEFLECTED | True if the contact was fully resolved by the AI without agent involvement | Boolean |
| DEFLECTION_ATTEMPTED | True if an AI deflection was offered to the customer | Boolean |
| DEFLECTION_TOPIC | Topic of the deflection attempt (e.g. password-reset, billing-faq) | String/Text |
| BOT_MESSAGE_COUNT | Number of messages sent by the AI bot during the contact | Integer/Number |
| CUSTOMER_MESSAGE_COUNT | Number of messages sent by the customer during the contact | Integer/Number |
| IS_ABANDONED | True if the customer left the queue before being connected to an agent | Boolean |
| IS_SHORT_ABANDON | True if the customer abandoned within 10 seconds of entering the queue | Boolean |
| WITHIN_SLA | True if the contact was answered within the contracted service level agreement | Boolean |
| SLA_TARGET_SEC | SLA target in seconds for this account's plan tier | Integer/Number |
| HAS_REPEAT_CONTACT | True if the customer contacted support again within 7 days with the same account ID | Boolean |
| HAS_REPEAT_CONTACT_BY_TICKET | True if the customer contacted support again referencing the same ticket ID | Boolean |
| REPEAT_CONTACT_AT | Timestamp of the follow-up contact, if applicable | Timestamp |
| HOURS_BETWEEN_CONTACTS | Hours between this contact and the next contact from the same account | Integer/Number |
| PREVIOUS_AGENT_ID | Agent ID who handled the most recent prior contact from this account | Integer/Number |
| HAS_FRUSTRATION | True if the conversation contains signals of customer frustration or dissatisfaction | Boolean |
| HAS_PRAISE | True if the conversation contains positive feedback or compliments | Boolean |
| HAS_CONFUSION | True if the conversation shows the customer is confused or uncertain | Boolean |
| HAS_GRATITUDE | True if the conversation contains expressions of thanks or appreciation | Boolean |
| AI_DISPOSITION_CODE | Contact reason automatically tagged by the AI model based on conversation content | String/Text |
| AGENT_DISPOSITION_CODE | Contact reason manually tagged by the agent at wrap-up | String/Text |
| DISPOSITION_GROUP | Grouped category of the disposition code | String/Text |
| AI_CONVERSATION_SUMMARY | AI-generated summary of the conversation | String/Text |
| CUSTOMER_INITIAL_QUERY | Customer's initial message or query as submitted in the contact form | String/Text |
| FEATURE_AREA | Product feature area related to the contact reason (e.g. billing, integrations, reporting) | String/Text |
| BUG_REPORTED | True if the contact resulted in a bug report being filed | Boolean |
| PAGE_SOURCE | URL or page title where the customer initiated a chat contact | String/Text |
| SESSION_ID | Web session ID linked to the contact, if available | String/Text |
| PROACTIVE_CONTACT | True if the contact was proactively initiated by the support team (outbound) | Boolean |
| CONTACT_MONTH | Calendar month the contact occurred (YYYY-MM) | String/Text |
