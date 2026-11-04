# Requirements Traceability

Review date: 13 October 2026

## Sources reviewed

- `M1_Chatbot_Solution_Design.md`
- `1.2_Service_Catalogue.md`
- `1.3_Menu_Catalogue.md`
- `1.4_Data_Requirements.md`
- `M2_Miro_Flow_Draft.md`
- `FLA_Escalation_Matrix.xlsx`
- Project milestone/task export supplied in five attachments; all five copies have SHA-256 `ADE112F56B26340E5BD3589F38D4384B0BCF760934123DAED16D4F2F4B54CE46`.

## Integrated requirements

| Requirement area | Implementation |
| --- | --- |
| Four main business routes | `app/catalog.py` and `app/workflow.py` implement Life Assurance, Funeral Services, FLIMAS, and Agent/Contact Us. |
| Stable service IDs | Direct routes such as `1.1`, `1.1.1`, `2.3`, `3.1`, `3.3.1`, and `4.2` are supported. |
| Navigation | `Back`, `Main Menu`, `Cancel`, draft resume, session expiry, and local numbered choices are stateful. |
| Invalid input | Consecutive invalid attempts are counted per prompt; the second offers an agent without automatic transfer. |
| Bereavement | Urgent language preempts the current menu, displays configured contacts first, and avoids dispatch promises. |
| Public versus private services | Public information is available without identity verification. Existing policy/payment/claim adapters remain protected and are not exposed on the initial public menu. |
| Approved content control | Database content records include owner, source, approval state, version, effective dates, verification date, and active state. Only approved active records are returned. |
| Enquiry data | Permission, preferred callback number, service-specific minimum fields, review, edit, cancel, stable request ID, and delivery state are implemented. |
| Handover | Context sharing requires recorded permission. Queue success is shown only after notification acknowledgement. |
| Takeover | Internal lifecycle events pause bot replies after takeover acknowledgement and resume after release/resolution. |
| Data records | Contacts, conversations, messages, sessions, requests, transactions, escalations, content, permissions, operational events, contacts, and links persist in SQL Server. |
| Duplicate protection | Meta message IDs are checked against persistent message storage as well as the in-memory TTL cache. |
| Production webhook security | Missing `META_APP_SECRET` fails closed when `APP_ENV` is `production` or `prod`. |

## Material conflicts and decisions

1. M1 excludes in-chat payments and claims from the initial release, while M2 expands those flows and the existing code already contains secure adapters. The public menu now follows M1. Existing policy, payment, and claim workflows remain available only through authenticated internal handoff until business scope and APIs are approved.
2. The design documents say "pending business approval", while the task export labels the milestone as approved. Structural navigation and safety rules are integrated, but rates, detailed benefits, land inventory, dedicated emergency numbers, and unverified links are not published without approved active records.
3. M2 proposes a 10-minute warning and 15-minute expiry, while the current configuration uses 30 minutes. Because the document marks those values as proposals, expiry remains environment-configurable and was not silently changed.
4. The escalation workbook defines four levels but leaves contacts, targets, backups, and authority limits as "To be confirmed". The bot implements Level 1 routing and agent lifecycle controls; human Levels 2-4 remain responsibilities of the connected agent platform until those fields are supplied.

## Outstanding dependencies

- Business approval and effective versions for product content and rates
- Validated funeral emergency contact and FLIMAS production destinations
- Staffed-hours calendar, holidays, queue contacts, service targets, and authority limits
- Agent notification endpoint and acknowledgment/takeover/release contract
- Fidelity core, payment, claims, and customer-verification API contracts
- Privacy notice, final consent wording, retention/deletion schedules, and access-role approval
- UAT hosting, SQL Server, Meta test configuration, test users, and formal sign-off
