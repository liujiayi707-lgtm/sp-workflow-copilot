# SP Workflow Copilot

A lightweight customer feedback workflow prototype for Customer Success and Product Operations.

SP Workflow Copilot helps structure customer-group messages into trackable Bug reports and feature requests. The current version uses manually pasted messages, rule-based classification, and a local SQLite database.

## Business Problem

Customer feedback often arrives through group chats and can be difficult to organize, track, and connect to existing issues.

This prototype explores a structured workflow for:

- Identifying potential Bugs and feature requests.
- Creating feedback records from incoming messages.
- Appending follow-up information to existing feedback.
- Flagging ambiguous cases for human confirmation.
- Persisting messages and feedback records locally.

## Workflow

1. Manually paste a customer message into the bridge program.
2. Select the corresponding demo customer.
3. Classify the message as a Bug, a feature request, an ambiguous message, or a normal message.
4. Create a new feedback record or append information to an explicitly selected existing record.
5. Review the processing result and generated information-collection template.

## Project Structure

```text
SP Workflow Copilot/
├── src/sp_workflow/
│   ├── agent/
│   │   └── manual_wechat_bridge.py
│   ├── skills/
│   │   ├── feedback_intake.py
│   │   └── feedback_processor.py
│   └── systems/
│       └── database.py
├── tests/
│   ├── test_feedback_intake.py
│   └── test_feedback_processor.py
├── data/                  # Local database; not committed
├── .gitignore
└── README.md
```

## Current Capabilities

- Rule-based message classification.
- Bug and feature-request collection templates.
- SQLite persistence for messages and feedback records.
- Follow-up information append with duplicate-content protection.
- Explicit feedback-ID selection and ambiguous-case handling.
- Interactive local controls: `ON`, `OFF`, `STATUS`, and `Q`.

## Setup

Python 3.14.