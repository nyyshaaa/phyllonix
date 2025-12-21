## 🌱 Inspiration
The project is inspired by two goals:  
1. **Real-world use case:** starting a small e-commerce platform in local area for healthy snacks,icecreams,arts stuff...  
2. **Engineering practice:** building a full end-to-end system with clean architecture, strong security, and performance optimizations, scalabale design.
   A full end-to-end system with clean architecture, strong security, and performance optimizations, scalabale design an e-commerce system, focused on correctness under concurrency/retries, idempotent workflows, and clean state transitions.

   Total Work hours on project(including rechecks and renalyzations and notes etc.)
   september 1 -- september 30 (~130 hours)  October 1 - December 21 (~439 hours)  ~~569 hours (~ 2 months at rate of 9 hours/day) would have done faster with higher focus .
   

> DB Design Plan --
https://www.notion.so/Project-DB-Design-Flow-25b14b400ea7803bb6faf782b43b1776

> Image uploads plan and notes --
https://www.notion.so/image-uploads-highly-scalable-apps-styles-27614b400ea78083a016fdd43bdcd15d


Image upload benchmark results experimented on this repo using two approaches --(https://github.com/nyyshaaa/backend-app-complete/blob/dev/src/via_server/uploads.md)
Almost always images won't be sent over backend server but directly to cloud for upload hence avoiding heavy data transfer over 2 networks .
[image_upload_comps.webm](https://github.com/user-attachments/assets/a1828584-de68-4bb0-9383-3b357659fc02)

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

Idempotency is applied differently based on domain requirements.
Critical workflows (payments, order creation, inventory updates) are protected using explicit ephemeral(24 hours) idempotency key states, while being idempotent at each sub-level, 
Other operations rely on database constraints or eventual consistency.

Concurrency safety for payments --
Designed for multiple application servers with a single primary database for writes, relying on database-level guarantees (conditional updates, unique constraints, transactional boundaries) to maintain high concurrency and do safe updates for concurrent requests and retries.

State transitions use explicit transactional boundaries with careful commit placement to avoid inconsistent updates.

Schema designed to minimize state ambiguity, higher future scalability(in terms of requiring minimal migrations) , support safe concurrent updates with minimal locking , and efficient indexing.

API queries are designed with minimal data access per request and avoidance of unnecessary joins. 

Redis caching is implemented for read-heavy endpoints (product listings & product details).

JWT-based authentication with refresh-token rotation and revocation to limit token replay.

-------------------------------------------------------------------------------------------------------------------------------------------------------


















