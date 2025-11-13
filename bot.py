import os
import logging
import io
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from fpdf import FPDF
from PIL import Image
from docx import Document
from docx.oxml.ns import qn
from dotenv import load_dotenv

# .env faylni o'qish
load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 🔑 API Keys
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not BOT_TOKEN or not GROQ_API_KEY:
    print("❌ XATOLIK: .env faylda BOT_TOKEN va GROQ_API_KEY topilmadi!")
    print("📝 .env faylni tekshiring:")
    print("   BOT_TOKEN=your_telegram_token")
    print("   GROQ_API_KEY=your_groq_key (https://console.groq.com)")
    exit(1)

# 📊 Foydalanuvchi ma'lumotlari
USER_STATE = {}
USER_DATA = {}
CHAT_HISTORY = {}

# 🔹 Asosiy menyu
def main_menu():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🖼 Image → PDF"), KeyboardButton("📄 Word → PDF")]
        ],
        resize_keyboard=True
    )

# 🔹 Image menyusi
def image_menu():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("✅ Create PDF")], [KeyboardButton("🔙 Back")]],
        resize_keyboard=True
    )

# 🔹 Word menyusi
def word_menu():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("✅ Create PDF")], [KeyboardButton("🔙 Back")]],
        resize_keyboard=True
    )

# 🤖 Groq API Chatbot (BEPUL, CHEKSIZ!)
async def chatbot_reply(user_text: str, user_id: int) -> str:
    """Groq Llama 3.3 70B model bilan suhbat"""
    try:
        # Suhbat tarixini olish
        if user_id not in CHAT_HISTORY:
            CHAT_HISTORY[user_id] = []
        
        # Foydalanuvchi xabarini qo'shish
        CHAT_HISTORY[user_id].append({"role": "user", "content": user_text})
        
        # Oxirgi 10 ta xabarni saqlash
        if len(CHAT_HISTORY[user_id]) > 10:
            CHAT_HISTORY[user_id] = CHAT_HISTORY[user_id][-10:]
        
        # System prompt + suhbat tarixi
        messages = [
            {
                "role": "system",
                "content": "Siz do'stona, hazilkash va yordam beruvchi yordamchi botsiz. O'zbekcha javob bering. Qisqa va samimiy javoblar bering (2-4 jumla). Emoji ishlating."
            }
        ] + CHAT_HISTORY[user_id]
        
        # Groq API so'rovi
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 500
            },
            timeout=30
        )
        
        if response.status_code == 200:
            bot_reply = response.json()["choices"][0]["message"]["content"]
            # Bot javobini tarixga qo'shish
            CHAT_HISTORY[user_id].append({"role": "assistant", "content": bot_reply})
            return bot_reply
        else:
            logger.error(f"Groq xatolik: {response.status_code} - {response.text}")
            return f"❌ API xatolik ({response.status_code}). Keyinroq urinib ko'ring."
        
    except Exception as e:
        logger.error(f"Chatbot xatolik: {e}")
        return f"❌ Xatolik: {str(e)}"

# 🏁 START komandasi
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    USER_STATE[update.message.from_user.id] = "main"
    await update.message.reply_text(
        "👋 Salom! Men ko'p funksiyali botman:\n\n"
        "🖼 Rasmlarni PDF ga\n"
        "📄 Word faylni PDF ga (rasmlar bilan!)\n"
        "💬 Suhbatlashish (har qanday xabar yuboring)\n\n"
        "Quyidagi menyudan tanlang yoki oddiy xabar yuboring 👇",
        reply_markup=main_menu()
    )

# 📥 Text xabarlarni boshqarish
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    current_state = USER_STATE.get(user_id, "main")

    # 🔙 Back tugmasi
    if text == "🔙 Back":
        USER_STATE[user_id] = "main"
        USER_DATA.pop(user_id, None)
        await update.message.reply_text("🏠 Asosiy menyuga qaytdingiz.", reply_markup=main_menu())
        return

    # 🖼 Image → PDF menyusi
    if text == "🖼 Image → PDF":
        USER_STATE[user_id] = "image"
        USER_DATA[user_id] = []
        os.makedirs(f"data/{user_id}", exist_ok=True)
        await update.message.reply_text(
            "📸 Endi rasmlarni yuboring.\n"
            "Barcha rasmlar yuborilgach '✅ Create PDF' tugmasini bosing.",
            reply_markup=image_menu()
        )
        return

    # 📄 Word → PDF menyusi
    if text == "📄 Word → PDF":
        USER_STATE[user_id] = "word"
        os.makedirs(f"data/{user_id}", exist_ok=True)
        USER_DATA[user_id] = None
        await update.message.reply_text(
            "📄 Endi Word faylni (.docx) yuboring.\n"
            "Tayyor bo'lgach '✅ Create PDF' tugmasini bosing.",
            reply_markup=word_menu()
        )
        return

    # ✅ Image PDF yaratish
    if text == "✅ Create PDF" and current_state == "image":
        await create_image_pdf(update, context)
        return

    # ✅ Word PDF yaratish
    if text == "✅ Create PDF" and current_state == "word":
        await create_word_pdf(update, context)
        return

    # 💬 Qolgan barcha xabarlar - Chatbot
    if current_state == "main":
        await update.message.reply_text("⏳ Javob tayyorlanmoqda...")
        reply = await chatbot_reply(text, user_id)
        await update.message.reply_text(reply)
        return

    await update.message.reply_text("⚠️ Iltimos, menyudan tanlang.", reply_markup=main_menu())

# 🖼 Rasm yuborilganda
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if USER_STATE.get(user_id) != "image":
        return

    os.makedirs(f"data/{user_id}", exist_ok=True)

    if update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        path = f"data/{user_id}/{photo.file_id}.jpg"
        await file.download_to_drive(path)
        USER_DATA[user_id].append(path)
        await update.message.reply_text(f"🖼 Rasm saqlandi ({len(USER_DATA[user_id])} ta).")

    elif update.message.document:
        doc = update.message.document
        if not doc.mime_type.startswith("image/"):
            await update.message.reply_text("⚠️ Faqat rasm yuboring.")
            return
        file = await doc.get_file()
        path = f"data/{user_id}/{doc.file_id}.jpg"
        await file.download_to_drive(path)
        USER_DATA[user_id].append(path)
        await update.message.reply_text(f"🖼 Rasm saqlandi ({len(USER_DATA[user_id])} ta).")

# 📄 Word fayl yuborilganda
async def handle_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if USER_STATE.get(user_id) != "word":
        return

    if not update.message.document:
        await update.message.reply_text("⚠️ Iltimos, Word fayl yuboring (.docx).")
        return

    doc = update.message.document
    if not doc.file_name.endswith(".docx"):
        await update.message.reply_text("⚠️ Faqat .docx formatdagi faylni yuboring.")
        return

    os.makedirs(f"data/{user_id}", exist_ok=True)
    path = f"data/{user_id}/{doc.file_name}"
    file = await doc.get_file()
    await file.download_to_drive(path)
    USER_DATA[user_id] = path
    await update.message.reply_text("📄 Word fayl saqlandi. Endi '✅ Create PDF' tugmasini bosing.")

# 🧾 Image → PDF funksiyasi
async def create_image_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    image_files = USER_DATA.get(user_id, [])
    if not image_files:
        await update.message.reply_text("⚠️ Rasm topilmadi.")
        return

    pdf_path = f"data/{user_id}/images_result.pdf"
    
    try:
        await update.message.reply_text("⏳ PDF yaratilmoqda...")
        
        pdf = FPDF(unit="mm", format="A4")
        processed_images = 0

        for i, img_path in enumerate(image_files):
            try:
                pdf.add_page()
                with Image.open(img_path) as img:
                    img = img.convert("RGB")
                    
                    img_width, img_height = img.size
                    page_w, page_h = 210, 297  # A4
                    margin = 10
                    available_w = page_w - 2 * margin
                    available_h = page_h - 2 * margin
                    
                    img_ratio = img_width / img_height
                    available_ratio = available_w / available_h
                    
                    if img_ratio > available_ratio:
                        new_w = available_w
                        new_h = available_w / img_ratio
                    else:
                        new_h = available_h
                        new_w = available_h * img_ratio
                    
                    x = margin + (available_w - new_w) / 2
                    y = margin + (available_h - new_h) / 2
                    
                    temp_jpg = f"data/{user_id}/temp_{i}.jpg"
                    
                    # Optimallashtirish
                    max_pixels = 1200 * 1200
                    current_pixels = img_width * img_height
                    
                    if current_pixels > max_pixels:
                        scale_factor = (max_pixels / current_pixels) ** 0.5
                        new_width = int(img_width * scale_factor)
                        new_height = int(img_height * scale_factor)
                        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    img.save(temp_jpg, "JPEG", quality=60, optimize=True)
                    pdf.image(temp_jpg, x=x, y=y, w=new_w, h=new_h)
                    
                    processed_images += 1
                    
                    if os.path.exists(temp_jpg):
                        os.remove(temp_jpg)
                        
            except Exception as e:
                logger.error(f"Rasm xatolik: {e}")
                continue

        if processed_images == 0:
            await update.message.reply_text("❌ Hech qanday rasm qo'shilmadi.")
            return

        pdf.output(pdf_path)
        
        pdf_size = os.path.getsize(pdf_path)
        size_info = f"{pdf_size/1024:.0f}KB" if pdf_size < 1024*1024 else f"{pdf_size/(1024*1024):.1f}MB"
        
        with open(pdf_path, "rb") as pdf_file:
            await update.message.reply_document(
                document=pdf_file,
                filename="converted.pdf",
                caption=f"✅ PDF tayyor! {processed_images} ta rasm, Hajmi: {size_info}"
            )
        
        USER_STATE[user_id] = "main"
        await update.message.reply_text("🏠 Asosiy menyuga qaytdingiz.", reply_markup=main_menu())

    except Exception as e:
        logger.error(f"PDF xatolik: {e}")
        await update.message.reply_text(f"❌ PDF yaratishda xatolik: {e}")
    
    finally:
        for img in image_files:
            if os.path.exists(img):
                try:
                    os.remove(img)
                except:
                    pass
        if os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except:
                pass
        USER_DATA[user_id] = []

# 🧾 MUKAMMAL Word → PDF (Krill + Rasmlar!)
async def create_word_pdf(update, context):
    user_id = update.message.from_user.id
    word_path = USER_DATA.get(user_id)
    
    if not word_path or not os.path.exists(word_path):
        await update.message.reply_text("❌ Avval Word fayl yuklang.")
        return

    pdf_path = word_path.replace(".docx", ".pdf")
    
    try:
        await update.message.reply_text("⏳ PDF yaratilmoqda...")
        
        document = Document(word_path)
        
        # PDF yaratish (UTF-8 qo'llab-quvvatlash)
        pdf = FPDF()
        pdf.add_page()
        
        # DejaVu font (Kriril harflarni qo'llab-quvvatlaydi)
        try:
            pdf.add_font('DejaVu', '', 'DejaVuSans.ttf', uni=True)
            pdf.set_font('DejaVu', '', 12)
        except:
            # Agar DejaVu yo'q bo'lsa, Arial
            pdf.set_font('Arial', '', 12)
            logger.warning("DejaVu font topilmadi, Arial ishlatilmoqda")

        has_content = False
        
        for element in document.element.body:
            # Paragraflar
            if element.tag == qn('w:p'):
                para = None
                for p in document.paragraphs:
                    if p._element == element:
                        para = p
                        break
                
                if para:
                    text = para.text.strip()
                    if text:
                        has_content = True
                        if pdf.get_y() > 270:
                            pdf.add_page()
                        
                        try:
                            pdf.multi_cell(0, 8, text)
                            pdf.ln(2)
                        except Exception as e:
                            logger.error(f"Matn xatolik: {e}")
                            safe_text = text.encode('ascii', 'ignore').decode('ascii')
                            if safe_text:
                                pdf.multi_cell(0, 8, safe_text)
                                pdf.ln(2)
            
            # Rasmlar
            elif element.tag == qn('w:r'):
                for drawing in element.findall('.//'+qn('a:blip')):
                    try:
                        embed = drawing.get(qn('r:embed'))
                        if embed:
                            image_part = document.part.related_parts[embed]
                            image_bytes = image_part.blob
                            
                            temp_img = f"data/{user_id}/temp_word_img.jpg"
                            
                            with Image.open(io.BytesIO(image_bytes)) as img:
                                img = img.convert('RGB')
                                
                                img_w, img_h = img.size
                                max_w = 180  # mm
                                max_h = 240  # mm
                                
                                ratio = min(max_w / img_w, max_h / img_h) * 25.4
                                new_w = img_w * ratio / 25.4
                                new_h = img_h * ratio / 25.4
                                
                                img.save(temp_img, 'JPEG', quality=85)
                                
                                if pdf.get_y() + new_h > 280:
                                    pdf.add_page()
                                
                                pdf.image(temp_img, x=15, w=new_w)
                                pdf.ln(5)
                                
                                if os.path.exists(temp_img):
                                    os.remove(temp_img)
                                
                                has_content = True
                    except Exception as e:
                        logger.error(f"Rasm xatolik: {e}")
                        continue

        if not has_content:
            pdf.multi_cell(0, 10, "Faylda matn yoki rasm topilmadi.")

        pdf.output(pdf_path)
        
        with open(pdf_path, "rb") as pdf_file:
            await update.message.reply_document(
                document=pdf_file,
                filename="converted.pdf",
                caption="✅ Word fayl PDF ga aylantirildi! (Matn + Rasmlar)"
            )
        
        USER_STATE[user_id] = "main"
        await update.message.reply_text("🏠 Asosiy menyuga qaytdingiz.", reply_markup=main_menu())

    except Exception as e:
        logger.error(f"Word PDF xatolik: {e}")
        await update.message.reply_text(f"❌ Xatolik: {str(e)}\n\nIltimos qaytadan urinib ko'ring.")
    
    finally:
        for file_path in [word_path, pdf_path]:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
        USER_DATA[user_id] = None

# 🚀 Botni ishga tushirish
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlerlar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_word))

    print("🤖 Bot ishga tushdi...")
    print("💬 Chatbot: Groq Llama 3.3 70B (BEPUL, CHEKSIZ)")
    print("📄 Word → PDF: Krill + Rasmlar qo'llab-quvvatlanadi")
    
    # Render.com uchun webhook (PORT majburiy)
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    PORT = int(os.getenv("PORT", 10000))
    
    if WEBHOOK_URL:
        # Webhook rejimi (Render.com)
        print(f"🌐 Webhook rejimi: {WEBHOOK_URL}")
        print(f"📡 Port: {PORT}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
            drop_pending_updates=True
        )
    else:
        # Polling rejimi (local)
        print("🔄 Polling rejimi (local)")
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()