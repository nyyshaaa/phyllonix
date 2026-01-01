## 🌱 Inspiration
The project is inspired by two goals:  
1. **Real-world use case:** starting a small e-commerce platform in local area for healthy snacks, arts stuff...  
2. **Engineering practice:** A full end-to-end system with clean architecture, strong security, and performance optimizations, scalabale design , focused on correctness under concurrency/retries, idempotent workflows, and clean state transitions.

-------------------------------------------------------------------------------------------------------------------------------------------------------

High level architecture summary --

>Idempotency is applied differently based on domain requirements.
Critical workflows (payments, order creation, inventory updates) are protected using explicit ephemeral(24 hours) idempotency key states, while being idempotent at each sub-level, 
Other operations rely on database constraints or eventual consistency.

>Concurrency safety for payments --
Designed for multiple application servers with a single primary database for writes, relying on database-level guarantees (conditional updates, unique constraints, transactional boundaries) to maintain high concurrency and do safe updates for concurrent requests and retries.

>API Design & Performance
APIs are designed to be concurrent- and retry-safe, with minimal data access per request, efficient query patterns, and clearly defined state transitions plus business invariants .

>State Modeling & Transitions
Modeled data schemas intentionally around access patterns and invariants, improving query efficiency and data integrity.
Domain schemas are designed to minimize state ambiguity, support safe concurrent transitions with minimal locking, and reduce the need for future migrations while remaining index-efficient.

>Caching Strategy
Redis caching is implemented for read-heavy endpoints (product listings and product details) to reduce database load and improve response latency.

>Authentication & Rate Limiting
JWT-based authentication(along with authorization and permissions check) with refresh-token rotation and revocation is implemented to limit token replay. Rate limiting is supported via two strategies, along with graceful retries for retryable endpoints and a database circuit-breaker pattern for db transient failures.

>Asynchronous Processing
An eventually consistent queue and worker system (currently in-memory) handles downstream events, with a clean abstraction layer to allow future integration with durable pub/sub systems with minimal refactoring.

>Webhook Handling
Secure webhook consumers are implemented for payment state transitions and image upload workflows, with signature verification, idempotent processing, and retry-safe handling.

>Error Handling & Observability
Consistent error handling, structured logging, and clear failure boundaries are implemented to support debugging and future observability integration.

> The backend APIs are designed with frontend integration in mind, including clear request/response contracts, retry-safe operations, and predictable state transitions .
-------------------------------------------------------------------------------------------------------------------------------------------------------

> Payments Plan & Payment testing ----

[payment_test.webm](https://github.com/user-attachments/assets/6367461f-7dc9-4687-9f1b-426a24d731d8)

<img width="1540" height="132" alt="image" src="https://github.com/user-attachments/assets/620c228d-4b47-4628-b0bb-1c235ba6cf11" />

<img width="1827" height="94" alt="image" src="https://github.com/user-attachments/assets/142bd81a-aeb2-4bba-bafc-19e08b8d8068" />

https://www.notion.so/Orders-and-Pays-28214b400ea780ed8c39c7a451e0eeff

-------------------------------------------------------------------------------------------------------------------------------------------------------

concurrency tests for inventory reservation without direct xclusive locks and with xclusive locks 

test_two_users_concurrent_order_summary_reservation
> without xclusive direct lock it causes oversell as both concurrent requests succeed when product stock was available so that only 1 checkout can succeed 
<img width="1444" height="188" alt="image" src="https://github.com/user-attachments/assets/f70fe577-ff39-4f7c-9c32-22eea6ba9240" />
<img width="1431" height="59" alt="image" src="https://github.com/user-attachments/assets/e3f20f75-ac26-491d-9c55-1dfab123d4ce" />
<img width="1448" height="457" alt="image" src="https://github.com/user-attachments/assets/adad7d6e-157f-48fa-9d55-d7162ddec7be" />

with xclusive locks only 1 checkout request succeeds other informs about not available qty for the product .
<img width="1440" height="307" alt="image" src="https://github.com/user-attachments/assets/d035bd90-0b29-490a-8400-1bb2a8d5be75" />

Also locks are fine here at this level for inventory but for later work to release inv it may cause locks to be held for somewhat longer transactions .
--> So we do a mini time hack(schema and data mig. if they already exist) -- create inv reserve row(with reserved qty as 0 and include the stock qty ) along with product creation so that we do a condition based update instead of insert
as we cannot really make insertion inv reserve idempotent .

-------------------------------------------------------------------------------------------------------------------------------------------------------

CACHED VERSION Product -pages
<img width="1735" height="813" alt="image" src="https://github.com/user-attachments/assets/bc0b0f9d-56d3-487f-a35f-593f16aad320" />

NON CACHED VERSION Product -pages
<img width="1756" height="743" alt="image" src="https://github.com/user-attachments/assets/23460e13-7bdd-4fa3-8a06-dd7601d76e81" />

Cached version improves the throughput by ~195 reqs/sec and avg latency by ~222 ms 

-------------------------------------------------------------------------------------------------------------------------------------------------------
> DB design abstractions notes--
https://www.notion.so/db-design-abstractions-2d314b400ea78071ad97fe0f5fce3df9

Image upload benchmark results experimented on this repo using two approaches --(https://github.com/nyyshaaa/backend-app-complete)
Images will be sent directly to cloud for upload after getting signed url in init stage hence avoiding heavy data transfer over 2 networks .
[image_upload_comps.webm](https://github.com/user-attachments/assets/a1828584-de68-4bb0-9383-3b357659fc02)

> chlorophyll-design-decisions-II (design decisions & notes for some part of project)
> https://ionian-feeling-129.notion.site/chlorophyll-design-decisions-II-2d714b400ea780929f7dc9f7e2ce0aa9

-------------------------------------------------------------------------------------------------------------------------------------------------------

--- Few Clarifications(Known Trade-offs & Planned Refactors)

> Core logic is stable and correct, with known areas identified for future deeper refactoring and to add more optimisations incrmentally.

> The final UPI app simulation endpoint is implemented in test mode; for ease of local and browser-based testing without adding frontend, auth tokens are passed via query params. In production, this would be done cleanly.

> Logging will be further hardened to fully redact sensitive fields (including SQL parameters) and fully align with production-grade security standards.

























