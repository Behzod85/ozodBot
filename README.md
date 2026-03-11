# OzodBot — Konveyer buyurtmalarini boshqarish uchun Telegram-bot

Qisqacha: bot uch rolni qo'llab-quvvatlaydi — direktor (admin), mijozlar va ishchilar. Direktor foydalanuvchilarni ro'yxatdan o'tkazadi va tasdiqlaydi, jarayon shablonlari va buyurtmalar yaratadi, konveyerni ishga tushiradi. Ishchilar konveyer bo'yicha vazifalarni oladi va ularni bajarilgan deb belgilaydilar. Mijoz buyurtma holatini so'raydi va har bir bosqichdan so'ng bildirishnomalar oladi.

Tez boshlash

1. Bog'liqliklarni o'rnating:

```bash
python -m pip install -r requirements.txt
```

2. Muhit o'zgaruvchilarini yarating (masalan, `.env` faylida):

```
BOT_TOKEN=sizning_bot_tokeningiz
# ixtiyoriy: agar direktorni oldindan belgilamoqchi bo'lsangiz
DIRECTOR_TELEGRAM_ID=123456789
```

3. Botni ishga tushiring:

```bash
python app.py
```

Asosiy komandalar (direktor):

- `/become_director` — o'zingizni direktor sifatida tayinlash (agar direktor hali tayinlanmagan bo'lsa).
- `/pending_users` — ro'yxatdan o'tish uchun arizalar ro'yxati.
- `/approve <telegram_id> <role>` — foydalanuvchini tasdiqlash; role = client|worker|director.
- `/appoint_director <telegram_id>` — boshqa foydalanuvchini direktor qilib tayinlash (faqat hozirgi direktor tomonidan).
- Har bir ariza uchun bot alohida xabar yuboradi va unga "Tasdiqlash" va "Rad etish" tugmalari qo'yiladi, shunda direktor arizalarni tezda tasdiqlashi yoki rad qilishi mumkin.
- Direktor `/commands` menyusidagi "Ishchilar" tugmasi orqali ishchilar ro'yxatini ko'rishi mumkin. Har bir ishchi ostida "O'chirish" va "Qayta nomlash" tugmalari mavjud. Ismni o'zgartirish uchun tugma bosilgach, yangi ismni javob xabarida yuboring yoki `/set_worker_name <yangi_ism>` buyrug'idan foydalaning.
- `/create_template <name>` — jarayon shablonini yaratish.
- `/add_step <template_id> | <instruction_text> | <notification_text>` — shabloniga qadam qo'shish.
- `/list_templates` — shablonlar va qadamlarni ko'rsatish.
- `/create_order <client_tg_id> <template_id>` — mijoz uchun buyurtma yaratish.
	- `/create_order <client_tg_id> <template_id> | <name> | <description>` — mijoz uchun buyurtma yaratish (nom va tavsifni `|` orqali ixtiyoriy kiritish mumkin).
- `/start_order <order_id>` — buyurtmani ishga tushirish (konveyer bosqichlari yaratiladi).
- `/commands` — sizning rolga mos komandalarni ko'rsatish (direktor/ishchi/mijoz).

Ishchilar uchun komandalar:

- Ro'yxatdan o'tishda `Men ishchi` tugmasini bosing.
- `/pickup` — navbatdagi bo'sh bosqichni olish.
- `/my_tasks` — joriy vazifalarni ko'rish.
- `/complete <order_step_id>` — bosqichni bajarilgan deb belgilash.

Mijozlar uchun komandalar:

- `/order_status <order_id>` — buyurtma holatini bilish.
- `/my_orders` — sizning buyurtmalaringiz ro'yxati.

Izoh

Bu minimal ishchi karkas. Mantiq oddiy va kengaytirilishi mumkin: dialoglar, qulay tugmalar, ruxsatlar, rollar, direktor uchun veb-interfeys va boshqalar.
