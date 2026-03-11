# OzodBot — Konveyer buyurtmalarini boshqarish uchun Telegram-bot

OzodBot — direktor, ishchi va mijoz rollarini qo'llab-quvvatlaydigan oddiy konveyer/buyurtma boshqaruv botidir. Direktor foydalanuvchilarni tasdiqlaydi, jarayon shablonlarini yaratadi va buyurtmalarni ishga tushiradi. Ishchilar vazifalarni olib, bajarilgan deb belgilaydilar. Mijozlar esa o'z buyurtmalari holatini kuzatishi mumkin.

## Tez boshlash

1. Bog'liqliklarni o'rnating:

```
python -m pip install -r requirements.txt
```

2. Muhit o'zgaruvchilarini yarating (masalan `.env`):

```
BOT_TOKEN=sizning_bot_tokeningiz
# Ixtiyoriy: avvaldan direktor qo'yish uchun
DIRECTOR_TELEGRAM_ID=123456789
```

3. Ma'lumotlar bazasini yarating:

```
# Virtualenv ichida (tavsiyalangan):
.venv/bin/python3 scripts/create_db.py

# yoki umumiy tizim Python bilan:
python3 scripts/create_db.py
```

4. Botni ishga tushiring:

```
python app.py
```

## Asosiy xususiyatlar va komandalar

- `/start` — foydalanuvchi botga yozgan zahoti avtomatik ravishda `users` jadvaliga saqlanadi (rol belgilanmaydi) va foydalanuvchiga oʻzbek tilida xabar yuboriladi: "Sizning murojaatingiz admin tomonidan ko'rib chiqilmoqda".
- Direktor funktsiyalari:
	- `/pending_users` yoki `Arizalar` — yangi arizalar ro'yxati. Har bir ariza ostida 3 ta tugma: **Ishchi**, **Direktor**, **Mijoz**. Tugma bosilganda foydalanuvchiga quyidagi tasdiq xabarlari yuboriladi:
		- Ishchi/Direktor uchun: "Sizning arizangiz tasdiqlandi. Siz - ishchi." yoki "Sizning arizangiz tasdiqlandi. Siz - direktor."
		- Mijoz uchun: "Hurmatli mijoz bizga ishonch bildirganingiz uchun tashakkur! Siz buyurtmalaringiz holatini ushbu botimiz orqali kuzatib borishingiz mumkin."
	- `/appoint_director <telegram_id>` — boshqa foydalanuvchini direktor qilib tayinlash.
	- `/create_template <name>` va `/add_step <template_id> | <instruction> | <notification>` — shablon va qadamlar yaratish.
	- `Qadamlar` — joriy jarayon (Process)lar ro'yxati; har bir element ostida **O'chirish** va **Qayta nomlash** tugmalari mavjud.

- Ishchilar:
	- `/pickup` — navbatdagi ochiq bosqichni olish.
	- `/my_tasks` — sizga tayinlangan vazifalar.
	- `/complete <order_step_id>` — bosqichni bajarilgan deb belgilash.

- Mijozlar:
	- `/my_orders` — mijozning buyurtmalari (paginatsiya bilan).
	- `/order_status <order_id>` — buyurtma holatini ko'rish.

## Ma'lumotlar bazasi va .gitignore

- Loyihada SQLite DB fayli `ozodbot.db` deb yaratiladi.

## Foydali skriptlar

- `scripts/create_db.py` — DB yaratish va kerakli jadvallarni initsializatsiya qilish.

## Ishlab chiquvchiga eslatma

- Kodda paginatsiya va har bir element alohida xabar sifatida yuboriladi — shuning uchun tugma bosilganda faqat o'sha xabar yangilanadi (katta qayta yuborishlar oldini olish uchun).
- Agar siz direktorni dastlabki sozlash uchun avtomatik qo'shmoqchi bo'lsangiz, `.env` ichida `DIRECTOR_TELEGRAM_ID` ni belgilang yoki `/become_director` buyrug'idan foydalaning.

## Litsenziya

Bu loyiha minimal namuna sifatida taqdim etilgan; kerak bo'lsa kengaytirishingiz mumkin.

----

Ishni boshlash uchun yuqoridagi bosqichlarni bajaring va agar qo'shimcha misollar yoki boshlang'ich ma'lumotlar kerak bo'lsa, xabar bering.
