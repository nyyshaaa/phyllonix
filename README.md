## 🌱 Inspiration
The project is inspired by two goals:  
1. **Real-world use case:** starting a small e-commerce platform in local area for healthy snacks,arts stuff...  
2. **Engineering practice:** building a full end-to-end system with clean architecture, strong security, and performance optimizations, scalabale design.

   Total Work hours on project september 1 -- september 30 (~130 hours)  October 1 - November 21 (~245 hours)

> DB Design Plan --
https://www.notion.so/Project-DB-Design-Flow-25b14b400ea7803bb6faf782b43b1776

> Image uploads plan and notes --
https://www.notion.so/image-uploads-highly-scalable-apps-styles-27614b400ea78083a016fdd43bdcd15d


Image upload benchmark results experimented on this repo using two approaches --(https://github.com/nyyshaaa/backend-app-complete/blob/dev/src/via_server/uploads.md)
Almost always images won't be sent over backend server but directly to cloud for upload hence avoiding heavy data transfer over 2 networks .
[image_upload_comps.webm](https://github.com/user-attachments/assets/a1828584-de68-4bb0-9383-3b357659fc02)

> Payments Current Plan & Payment testing ----

[payment_test.webm](https://github.com/user-attachments/assets/6367461f-7dc9-4687-9f1b-426a24d731d8)

<img width="1540" height="132" alt="image" src="https://github.com/user-attachments/assets/620c228d-4b47-4628-b0bb-1c235ba6cf11" />

<img width="1827" height="94" alt="image" src="https://github.com/user-attachments/assets/142bd81a-aeb2-4bba-bafc-19e08b8d8068" />





concurrency tests for inventory reservation without direct xclusive locks and with xclusive locks 

test_two_users_concurrent_order_summary_reservation
> without xclusive direct lock it causes oversell as both concurrent requests succeed when product stock was available so that only 1 checkout can succeed 
<img width="1444" height="188" alt="image" src="https://github.com/user-attachments/assets/f70fe577-ff39-4f7c-9c32-22eea6ba9240" />
<img width="1431" height="59" alt="image" src="https://github.com/user-attachments/assets/e3f20f75-ac26-491d-9c55-1dfab123d4ce" />
<img width="1448" height="457" alt="image" src="https://github.com/user-attachments/assets/adad7d6e-157f-48fa-9d55-d7162ddec7be" />

with xclusive locks only 1 checkout request succeeds other informs about not available qty for the product .
<img width="1440" height="307" alt="image" src="https://github.com/user-attachments/assets/d035bd90-0b29-490a-8400-1bb2a8d5be75" />



















