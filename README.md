# Back4App XHTTP Relay — Frappe App

تطبيق Frappe خفيف يعرّض HTTP relay قابلًا للضبط عبر REST API، بهدف تشغيله على Bench يدعم التطبيقات المخصصة.

## توافق Frappe Cloud

المستودع يحتوي في جذره على `pyproject.toml` مع إعلان التوافق المطلوب:

```toml
[tool.bench.frappe-dependencies]
frappe = ">=16.0.0-dev,<17.0.0"
```

هذا التطبيق يستهدف Frappe Framework v16.

## نقاط API

```text
GET /api/method/back4app_xhttp_relay.api.health

GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD \
  /api/method/back4app_xhttp_relay.api.relay?path=/your/path
```

نقطة `relay` تمرر جسم الطلب وبعض الترويسات إلى المضيف المعرّف في إعدادات الموقع، ولا تسمح للعميل بتغيير المضيف.

## الإعداد

اضبط الموقع عبر `site_config.json` أو Bench:

```bash
bench --site alrufaaey.k.frappe.cloud set-config \
  back4app_relay_target_domain https://vps.thumbayan.com:443

bench --site alrufaaey.k.frappe.cloud set-config \
  back4app_relay_token 'ضع-رمزًا-عشوائيًا-طويلًا'
```

عند تعيين الرمز، أرسله في كل طلب:

```http
X-Relay-Token: ضع-رمزًا-عشوائيًا-طويلًا
```

لا تترك الرمز فارغًا في بيئة الإنتاج؛ وإلا أصبحت نقطة relay متاحة للزوار المجهولين.

## التثبيت على Bench خاص

```bash
bench get-app https://github.com/alrufaaey-yahoo/back4app-xhttp-relay-frappe
bench --site alrufaaey.k.frappe.cloud install-app back4app_xhttp_relay
bench --site alrufaaey.k.frappe.cloud migrate
```

## ملاحظة حول خطة Frappe الحالية

موقع `alrufaaey.k.frappe.cloud` يعمل حاليًا على Shared Bench / Free. تثبيت التطبيقات المخصصة يتطلب Private Bench وفق إعدادات الموقع وتوثيق Frappe Cloud. إنشاء هذا المستودع يجعله جاهزًا للتثبيت على Bench مؤهل، لكنه لا يتجاوز قيد خطة الاستضافة الحالية.

للمستودع الخاص، يجب منح Frappe Cloud صلاحية الوصول إلى مستودع GitHub من إعدادات GitHub App قبل محاولة جلبه.

## التطوير والاختبار

```bash
python -m compileall back4app_xhttp_relay
pytest -q
```
