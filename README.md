# Back4App XHTTP Relay — Frappe App

تطبيق Frappe v16 يعمل كـ **relay مباشر** على النطاق الرئيسي. عند وصول طلب إلى:

```text
https://alrufaaey.k.frappe.cloud/<path>?<query>
```

يمرر التطبيق الطريقة والجسم والترويسات والمسار نفسه إلى:

```text
https://vps.thumbayan.com:443/<path>?<query>
```

## السلوك المباشر

- `GET /` يمرر إلى `https://vps.thumbayan.com:443/`.
- `POST /api/x?key=1` يمرر إلى `https://vps.thumbayan.com:443/api/x?key=1`.
- يدعم GET وHEAD وPOST وPUT وPATCH وDELETE وOPTIONS عندما يصل الطلب إلى hook التطبيق.
- البث يتم دون تخزين استجابة upstream كاملة في الذاكرة.
- المضيف الهدف ثابت من إعداد الموقع ولا يمكن للعميل تغييره.
- يتم تمرير الترويسات المفيدة مع حذف ترويسات hop-by-hop و`Host` و`Content-Length`.

## مسارات Frappe المستثناة

تبقى مسارات الإدارة والملفات وواجهة API متاحة لـ Frappe ولا يتم اعتراضها:

```text
/api/  /assets/  /files/  /private/files/
/app  /desk  /login  /setup  /socket.io
/backups  /.well-known/
```

لذلك يبقى اختبار التطبيق متاحًا عبر:

```text
GET /api/method/back4app_xhttp_relay.api.health
```

والاستجابة المتوقعة:

```json
{"message":{"status":"ok","upstream":"https://vps.thumbayan.com:443"}}
```

## إعداد upstream اختياري

القيمة الافتراضية هي العنوان المطلوب:

```bash
bench --site alrufaaey.k.frappe.cloud set-config \
  back4app_relay_target_domain https://vps.thumbayan.com:443
```

يمكن حماية relay برمز اختياري. عند ضبطه يجب إرسال `X-Relay-Token`:

```bash
bench --site alrufaaey.k.frappe.cloud set-config \
  back4app_relay_token 'ضع-رمزًا-عشوائيًا-طويلًا'
```

إذا لم يتم ضبط الرمز، يعمل الرابط المباشر دون ترويسة إضافية كما طلبت.

## التثبيت والنشر

المستودع متوافق مع Frappe v16:

```toml
[tool.bench.frappe-dependencies]
frappe = ">=16.0.0-dev,<17.0.0"
```

بعد تحديث الكود على الـ Bench:

```bash
bench --site alrufaaey.k.frappe.cloud migrate
bench --site alrufaaey.k.frappe.cloud clear-cache
```

ثم أعد تشغيل الـ Bench/الموقع.
