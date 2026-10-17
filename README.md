# Secure Web Proxy — Frappe app

تطبيق Frappe يوفّر Proxy فعليًا من جهة الخادم. يدخل المستخدم رابطًا، ثم يجلب خادم Frappe الموقع الخارجي ويعيد المحتوى إلى المتصفح. لا يوجد redirect إلى الموقع الأصلي ولا iframe يحمّل الموقع الخارجي مباشرة.

## الوظائف

- قبول `http` و`https` فقط، مع إضافة `https://` تلقائيًا للنطاقات.
- منع عناوين localhost وIP الخاصة وlink-local وmetadata وDNS غير العام.
- إعادة التحقق من DNS قبل كل طلب وقبل كل redirect، مع حد خمسة redirects.
- حد استجابة افتراضي 5MB، timeout للشبكة، وحد rate limit بسيط لكل عنوان عميل.
- عدم تمرير cookies أو Authorization أو headers الحساسة إلى الوجهة.
- إعادة كتابة روابط HTML وforms والصور والسكريبتات وCSS و`srcset` إلى مسار الـ Proxy.
- منع تنفيذ JavaScript الخارجي في الواجهة الأساسية باستخدام iframe sandbox.
- واجهة عربية/إنجليزية، RTL، responsive، ووضع فاتح/داكن.

## التثبيت على Frappe Cloud

أضف المستودع كتطبيق إلى Private Bench، ثم ثبته على الموقع:

```bash
bench get-app https://github.com/alrufaaey-yahoo/back4app-xhttp-relay-frappe
bench --site alrufaaey.k.frappe.cloud install-app back4app_xhttp_relay
bench --site alrufaaey.k.frappe.cloud migrate
```

بعد النشر، افتح `https://alrufaaey.k.frappe.cloud/`. إذا كان الموقع خلف تسجيل الدخول، يجب السماح للزوار الضيوف من إعدادات الموقع حتى تعمل الصفحة العامة ونقطة الـ Proxy.

يمكن ضبط الحدود عبر إعدادات الموقع عند الحاجة:

```json
{
  "proxy_rate_limit_per_minute": 30
}
```

## نقاط API

```text
GET /api/method/back4app_xhttp_relay.api.health
GET /api/method/back4app_xhttp_relay.api.proxy?url=https%3A%2F%2Fexample.com
```

## ملاحظات أمنية وتشغيلية

هذا Proxy عام يمكن إساءة استخدامه في استهلاك bandwidth أو الوصول إلى وجهات محظورة. يجب تشغيل rate limiting على طبقة CDN/reverse proxy أيضًا، ومراقبة السجلات، ووضع حد حسابي مناسب. لا يُنفّذ JavaScript الخارجي في الواجهة الأساسية، لذلك قد لا تعمل تطبيقات SPA المعقدة أو WebSockets أو service workers بشكل كامل. لا تُرسل بيانات دخول أو cookies إلى المواقع الخارجية.

## الاختبارات

```bash
python -m compileall back4app_xhttp_relay
pytest -q
```
