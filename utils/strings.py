STRINGS = {
    'ar': {
        'start': "👋 أهلاً بك في بوت AnoSim!\n\nهذا البوت يقوم بإنشاء حسابات تيليجرام تلقائياً وحفظها.\n\nالرصيد الحالي: /balance\nشراء حساب جديد: /buy\nالمخزون: /stock\nتغيير اللغة: /lang",
        'balance': "💰 رصيدك الحالي في Anosim.net هو: **${balance}**",
        'balance_error': "❌ فشل في جلب الرصيد. تأكد من مفتاح الـ API.",
        'choose_country': "🌍 اختر الدولة التي تريد شراء رقم منها:",
        'countries_error': "❌ فشل في جلب قائمة الدول.",
        'creating_acc': "⏳ جاري البدء في إنشاء الحساب...",
        'status_bought': "⚡️ **عملية شراء جديدة**\n\n📞 الرقم: `{phone}`\n🆔 معرف الطلب: `{id}`\n💬 الكود: جاري الطلب...",
        'status_requesting': "⚡️ **عملية شراء جديدة**\n\n📞 الرقم: `{phone}`\n🆔 معرف الطلب: `{id}`\n💬 الكود: 📲 جاري طلب الكود من تيليجرام...",
        'status_email_created': "⚡️ **عملية شراء جديدة**\n\n📞 الرقم: `{phone}`\n🆔 معرف الطلب: `{id}`\n📧 الإيميل: `{email}`\n💬 الكود: 📩 جاري انتظار كود الإيميل...",
        'status_email_success': "⚡️ **عملية شراء جديدة**\n\n📞 الرقم: `{phone}`\n🆔 معرف الطلب: `{id}`\n📧 الإيميل: `{email}`\n💬 الكود: ✅ تم تأكيد الإيميل بنجاح!",
        'status_waiting': "⚡️ **عملية شراء جديدة**\n\n📞 الرقم: `{phone}`\n🆔 معرف الطلب: `{id}`\n💬 الكود: ⏳ Waiting... ({attempt}/{total})",
        'manual_test_start': "🛠 **وضع الاختبار اليدوي**\n\nتم شراء الرقم: `{phone}`\n\n👉 من فضلك اطلب الكود لهذا الرقم من تطبيق تيليجرام الرسمي الآن.\nالبوت سينتظر وصول الكود وعرضه هنا.",
        'manual_test_success': "✅ وصل الكود بنجاح!\n💬 الكود: `{code}`",
        'confirm_purchase': "⚠️ **تأكيد الشراء:**\n\n🌍 الدولة: {country}\n💰 السعر: ${price}\n📦 الكمية المتوفرة: {count}\n📶 المزود: {provider}\n\nهل أنت متأكد من رغبتك في شراء هذا الرقم الآن؟",
        'confirm_btn': "✅ نعم، شراء الآن",
        'cancel_btn': "❌ إلغاء",
        'order_cancelled': "✅ تم إلغاء العملية ولم يتم خصم أي مبالغ.",
        'acc_success': "✅ تم إنشاء الحساب بنجاح!\n\n📞 الرقم: `{phone}`\n👤 الاسم: {first_name}\n📂 ملف الجلسة: {session}",
        'acc_failed': "❌ فشل إنشاء الحساب: {error}",
        'empty_stock': "📭 المخزون فارغ حالياً.",
        'stock_list': "📂 **قائمة الحسابات المتوفرة:**\n\n",
        'choose_lang': "🌐 اختر اللغة / Choose Language:",
        'lang_updated': "✅ تم تغيير اللغة إلى العربية."
    },
    'en': {
        'start': "👋 Welcome to AnoSim Bot!\n\nThis bot automatically creates and stores Telegram accounts.\n\nBalance: /balance\nBuy Account: /buy\nInventory: /stock\nChange Language: /lang",
        'balance': "💰 Your current balance in Anosim.net is: **${balance}**",
        'balance_error': "❌ Failed to fetch balance. Check your API key.",
        'choose_country': "🌍 Choose a country to buy a number from:",
        'countries_error': "❌ Failed to fetch countries list.",
        'creating_acc': "⏳ Initializing account creation...",
        'status_bought': "⚡️ **New Purchase Operation**\n\n📞 Phone: `{phone}`\n🆔 Order ID: `{id}`\n💬 Code: Requesting...",
        'status_requesting': "⚡️ **New Purchase Operation**\n\n📞 Phone: `{phone}`\n🆔 Order ID: `{id}`\n💬 Code: 📲 Requesting from Telegram...",
        'status_email_created': "⚡️ **New Purchase Operation**\n\n📞 Phone: `{phone}`\n🆔 Order ID: `{id}`\n📧 Email: `{email}`\n💬 Code: 📩 Waiting for email code...",
        'status_email_success': "⚡️ **New Purchase Operation**\n\n📞 Phone: `{phone}`\n🆔 Order ID: `{id}`\n📧 Email: `{email}`\n💬 Code: ✅ Email verified successfully!",
        'status_waiting': "⚡️ **New Purchase Operation**\n\n📞 Phone: `{phone}`\n🆔 Order ID: `{id}`\n💬 Code: ⏳ Waiting... ({attempt}/{total})",
        'manual_test_start': "🛠 **Manual Test Mode**\n\nNumber purchased: `{phone}`\n\n👉 Please request the code for this number manually from your official Telegram app now.\nThe bot will wait for the code and display it here.",
        'manual_test_success': "✅ Code received successfully!\n💬 Code: `{code}`",
        'confirm_purchase': "⚠️ **Confirm Purchase:**\n\n🌍 Country: {country}\n💰 Price: ${price}\n📦 Available: {count}\n📶 Provider: {provider}\n\nAre you sure you want to buy this number now?",
        'confirm_btn': "✅ Yes, Buy Now",
        'cancel_btn': "❌ Cancel",
        'order_cancelled': "✅ Operation cancelled. No charges applied.",
        'acc_success': "✅ Account created successfully!\n\n📞 Number: `{phone}`\n👤 Name: {first_name}\n📂 Session: {session}",
        'acc_failed': "❌ Account creation failed: {error}",
        'empty_stock': "📭 Inventory is currently empty.",
        'stock_list': "📂 **Available Accounts:**\n\n",
        'choose_lang': "🌐 Choose Language / اختر اللغة:",
        'lang_updated': "✅ Language updated to English."
    }
}

def get_string(key, lang='ar', **kwargs):
    text = STRINGS.get(lang, STRINGS['ar']).get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text
