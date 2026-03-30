# =============================================================
# app.py — English Communication Assistant for UWA Study Tour 2569
# Faculty of Education, Silpakorn University
# The University of Western Australia, Perth | 29 Mar – 5 Apr 2569
# =============================================================

import os
import re
import json
import time
import logging
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# APP INITIALIZATION
# ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="English Communication Assistant — UWA 2569",
    version="1.0.0"
)
templates = Jinja2Templates(directory="templates")

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
MAX_HISTORY           = 20
SESSION_TIMEOUT       = 7200   # 2 hours (seconds)
MAX_REQUESTS_PER_MIN  = 20
RATE_LIMIT_WINDOW     = 60     # seconds

API_KEY       = os.getenv("API_KEY", "")
API_BASE_URL  = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
API_MODEL     = os.getenv("API_MODEL", "gpt-4o-mini")
TTS_API_KEY   = os.getenv("TTS_API_KEY") or API_KEY   # falls back to main key
TTS_MODEL     = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")


# =============================================================
# SECTION 1 — SCENARIOS
# =============================================================
SCENARIOS: Dict[str, Dict] = {
    "airport": {
        "name": "Perth Airport",
        "description": "เช็คอิน, คนเข้าเมือง, Customs, รับกระเป๋า",
        "context": (
            "You are at Perth Airport, Western Australia. Help with check-in procedures, "
            "immigration questions, customs declaration forms, baggage claims, and airport "
            "navigation. Focus on clear, polite Australian English used in airport settings."
        ),
    },
    "accommodation": {
        "name": "Accommodation",
        "description": "เช็คอิน/เอาท์, แจ้งปัญหาห้อง, ขอบริการต่างๆ",
        "context": (
            "You are at a hotel or accommodation in Perth. Help with check-in/check-out, "
            "reporting room issues, requesting services, and communicating with hotel staff "
            "in polite Australian English."
        ),
    },
    "uwa_campus": {
        "name": "UWA Campus",
        "description": "ลงทะเบียน, ถามทาง, ใช้สิ่งอำนวยความสะดวก",
        "context": (
            "You are on the campus of The University of Western Australia (UWA) in Crawley, "
            "Perth. Help with campus navigation, registration, using university facilities, "
            "and interacting with staff and students in an academic environment."
        ),
    },
    "academic": {
        "name": "Academic & Seminars",
        "description": "นำเสนองาน, ถาม-ตอบ, ประชุมวิชาการ, สังเกตการสอน",
        "context": (
            "You are in an academic setting at UWA — attending seminars, observing classes, "
            "participating in faculty meetings, or presenting. Help with formal academic "
            "English, professional communication, and educational discourse appropriate for "
            "faculty exchange programs."
        ),
    },
    "dining": {
        "name": "Australian Dining",
        "description": "สั่งอาหาร, dietary needs, วัฒนธรรมการทาน, café culture",
        "context": (
            "You are at a restaurant or café in Perth, Australia. Help with ordering food, "
            "communicating dietary requirements, understanding the menu, tipping culture "
            "(note: tipping is not compulsory in Australia), and dining etiquette."
        ),
    },
    "tourism": {
        "name": "Perth Tourism",
        "description": "Kings Park, Fremantle, Swan River, Rottnest Island",
        "context": (
            "You are visiting tourist attractions around Perth, WA — Kings Park & Botanic "
            "Garden, Fremantle, Swan River, or Rottnest Island. Help with asking for "
            "directions, buying tickets, interacting with guides, and navigating Perth's "
            "tourist sites."
        ),
    },
    "shopping": {
        "name": "Shopping",
        "description": "Westfield, คืนสินค้า, GST refund, การซื้อของ",
        "context": (
            "You are shopping in Perth — at Westfield or local shops. Help with asking "
            "about products, prices, requesting refunds, understanding the GST tourist "
            "refund scheme, and general shopping interactions in Australian English."
        ),
    },
    "transport": {
        "name": "Transportation",
        "description": "Transperth, SmartRider, Uber, แท็กซี่, ถามทาง",
        "context": (
            "You are using public transportation or taxis in Perth. Help with Transperth "
            "(bus, train, ferry), SmartRider card, booking Uber, taking taxis, asking for "
            "directions, and navigating Perth's transport network."
        ),
    },
    "emergency": {
        "name": "Emergency",
        "description": "เบอร์ 000, โรงพยาบาล, ตำรวจ, ขอความช่วยเหลือด่วน",
        "context": (
            "You are dealing with an emergency situation in Australia. Help with calling "
            "emergency services (Triple Zero: 000), communicating with police, paramedics, "
            "or hospital staff, describing symptoms clearly, and getting urgent help."
        ),
    },
    "social": {
        "name": "Social & Networking",
        "description": "Small talk, ทักทาย, งาน networking, สร้างสัมพันธ์",
        "context": (
            "You are in social situations with Australians — networking events, casual "
            "gatherings, or informal meet-ups. Help with Australian small talk, "
            "understanding Australian humor and culture, polite conversation starters, "
            "and building professional relationships in the Australian academic community."
        ),
    },
}


# =============================================================
# SECTION 2 — USER MODES
# =============================================================
USER_MODES: Dict[str, Dict] = {
    "educator": {
        "name": "Educator Mode",
        "description": "โหมดนักการศึกษา — สำหรับอาจารย์และบุคลากรทางการศึกษา",
        "context": (
            "You are helping Thai educators from Silpakorn University's Faculty of "
            "Education who are on a professional development program at UWA. They need "
            "English appropriate for academic and professional settings, with awareness of "
            "Thai educational culture and how to bridge it with Australian norms."
        ),
    },
    "traveler": {
        "name": "General Traveler Mode",
        "description": "โหมดนักท่องเที่ยวทั่วไป — สำหรับการเดินทางทั่วไป",
        "context": (
            "You are helping general travelers in Australia. Use practical and friendly "
            "English suitable for tourism and daily interactions."
        ),
    },
}


# =============================================================
# SECTION 3 — COACH PERSONAS
# =============================================================
COACHES: Dict[str, Dict] = {
    "Dr. Emma Clarke": {
        "id":          "emma",
        "name":        "Dr. Emma Clarke",
        "specialty":   "Academic & Professional English",
        "experience":  "12 years in international academic exchange programs, UWA English Language Centre",
        "focus_areas": "Academic presentations, seminar participation, professional meetings, formal correspondence",
        "communication_style": (
            "Warm yet professional. Uses precise academic language with clear explanations. "
            "Encourages confidence in formal settings."
        ),
        "tts_voice": "nova",
        "avatar":    "👩‍🎓",
        "best_for":  ["uwa_campus", "academic"],
        "description": "ผู้เชี่ยวชาญด้านภาษาอังกฤษวิชาการและการสื่อสารในสภาพแวดล้อมมหาวิทยาลัย เหมาะสำหรับการนำเสนอ การประชุม และการแลกเปลี่ยนทางวิชาการ",
        "specialty_knowledge": [
            "Expert in academic discourse and educational terminology",
            "Specializes in Australian university culture and academic norms",
            "Experienced in faculty exchange and international educator programs",
            "Knowledgeable about UWA's academic structure and expectations",
            "Focuses on building confidence in formal academic English",
        ],
        "common_phrases": [
            '"Could you please clarify that point?" — ขอให้อธิบายเพิ่มเติมได้ไหม',
            '"I\'d like to share an observation from Thailand." — อยากแบ่งปันสิ่งที่สังเกตจากไทย',
            '"That\'s a fascinating approach." — วิธีการนั้นน่าสนใจมาก',
            '"Would it be possible to arrange a meeting?" — ขอนัดประชุมได้ไหม',
            '"Thank you so much for having us today." — ขอบคุณมากที่ต้อนรับพวกเราวันนี้',
        ],
    },
    "James Wilson": {
        "id":          "james",
        "name":        "James Wilson",
        "specialty":   "Daily Life & Service English",
        "experience":  "8 years helping international visitors navigate daily life in Perth",
        "focus_areas": "Shopping, dining, accommodation, everyday services and interactions",
        "communication_style": (
            "Friendly, relaxed, and practical. Uses everyday Australian English with "
            "cultural context. Very patient and encouraging."
        ),
        "tts_voice": "echo",
        "avatar":    "👨‍💼",
        "best_for":  ["dining", "shopping", "accommodation"],
        "description": "ผู้เชี่ยวชาญด้านภาษาอังกฤษในชีวิตประจำวัน เหมาะสำหรับการช้อปปิ้ง การทานอาหาร และการติดต่อกับบริการต่างๆ ในเพิร์ธ",
        "specialty_knowledge": [
            "Expert in everyday Australian English and casual communication",
            "Specializes in service industry language and customer interactions",
            "Experienced in helping non-native speakers navigate daily tasks",
            "Knowledgeable about Perth's local shops, restaurants, and services",
            "Focuses on practical communication for daily life in Australia",
        ],
        "common_phrases": [
            '"Excuse me, could I get some help?" — ขอโทษนะ ช่วยหน่อยได้ไหม',
            '"I\'ll have the..., please." — ขอ... ครับ/ค่ะ',
            '"Do you have anything gluten-free?" — มีอาหารที่ไม่มีกลูเตนไหม',
            '"Could I get a receipt, please?" — ขอใบเสร็จด้วยได้ไหม',
            '"Is this included in the price?" — รวมอยู่ในราคาแล้วไหม',
        ],
    },
    "Sarah Thompson": {
        "id":          "sarah",
        "name":        "Sarah Thompson",
        "specialty":   "Social & Cultural English",
        "experience":  "10 years as cultural liaison for international exchange programs in WA",
        "focus_areas": "Australian small talk, networking, humor, social etiquette, building relationships",
        "communication_style": (
            "Warm, engaging, culturally insightful. Explains Australian social norms with "
            "humor and practical advice."
        ),
        "tts_voice": "shimmer",
        "avatar":    "👩‍🏫",
        "best_for":  ["social", "dining"],
        "description": "ผู้เชี่ยวชาญด้านวัฒนธรรมและการสื่อสารทางสังคม เหมาะสำหรับการสร้างความสัมพันธ์ การทำ small talk และการเข้าใจวัฒนธรรมออสเตรเลีย",
        "specialty_knowledge": [
            "Expert in Australian social culture and communication styles",
            "Specializes in cross-cultural communication between Thai and Australian contexts",
            "Experienced in networking and professional social events in Australia",
            "Knowledgeable about Australian humor, idioms, and social taboos",
            "Focuses on helping Thai educators build genuine connections with Australians",
        ],
        "common_phrases": [
            '"G\'day! How\'s it going?" — สวัสดี! เป็นยังไงบ้าง (ทางการน้อย)',
            '"No worries at all!" — ไม่เป็นไรเลย',
            '"That sounds great, I\'d love to!" — ฟังดูดีเลย อยากร่วมด้วย',
            '"What do you do for fun around here?" — แถวนี้มีอะไรสนุกๆ บ้าง',
            '"It\'s been lovely chatting with you." — คุยด้วยกันดีมากเลย',
        ],
    },
    "Michael Chen": {
        "id":          "michael",
        "name":        "Michael Chen",
        "specialty":   "Tourism & Exploration English",
        "experience":  "12 years as tour guide and tourism consultant in Perth and WA",
        "focus_areas": "Perth attractions, guided tours, local knowledge, exploration",
        "communication_style": (
            "Enthusiastic, informative, and fun. Loves sharing local knowledge and making "
            "tourism experiences memorable."
        ),
        "tts_voice": "alloy",
        "avatar":    "🧭",
        "best_for":  ["tourism", "transport"],
        "description": "ผู้เชี่ยวชาญด้านการท่องเที่ยวเพิร์ธและออสเตรเลียตะวันตก เหมาะสำหรับการสอบถามเกี่ยวกับสถานที่ท่องเที่ยวและการเดินทาง",
        "specialty_knowledge": [
            "Expert on all major Perth and WA tourist attractions",
            "Specializes in Kings Park, Fremantle, Swan River, and Rottnest Island",
            "Experienced in explaining cultural heritage and natural attractions",
            "Knowledgeable about local cuisine, markets, and hidden gems in Perth",
            "Focuses on making tourism interactions smooth and enjoyable",
        ],
        "common_phrases": [
            '"How do I get to Kings Park from here?" — ไป Kings Park จากที่นี่ยังไง',
            '"What\'s the best way to get to Fremantle?" — วิธีที่ดีที่สุดไป Fremantle คือ?',
            '"Is it worth visiting Rottnest Island?" — Rottnest Island น่าไปไหม',
            '"What time does it close?" — ปิดกี่โมง',
            '"Could you recommend a local restaurant?" — แนะนำร้านอาหารท้องถิ่นได้ไหม',
        ],
    },
    "Dr. Olivia Hart": {
        "id":          "olivia",
        "name":        "Dr. Olivia Hart",
        "specialty":   "Emergency & Urgent Communication",
        "experience":  "15 years in international healthcare and emergency communication, Perth hospitals",
        "focus_areas": "Emergency services (000), hospital communication, urgent situations, medical terms",
        "communication_style": (
            "Clear, calm, and precise. Uses direct, simple English for urgent situations. "
            "Prioritizes clarity over complexity."
        ),
        "tts_voice": "onyx",
        "avatar":    "🏥",
        "best_for":  ["emergency"],
        "description": "ผู้เชี่ยวชาญด้านการสื่อสารในเหตุฉุกเฉินและสถานพยาบาลในออสเตรเลีย เหมาะสำหรับสถานการณ์เร่งด่วนและการขอความช่วยเหลือ",
        "specialty_knowledge": [
            "Expert in Australian emergency services (Triple Zero: 000)",
            "Specializes in medical communication and hospital procedures in Australia",
            "Experienced in guiding non-native speakers through emergency situations",
            "Knowledgeable about Australian healthcare system and visitor rights",
            "Focuses on life-critical, clear communication under pressure",
        ],
        "common_phrases": [
            '"I need help, please!" — ฉันต้องการความช่วยเหลือ!',
            '"Please call Triple Zero — 000!" — กรุณาโทร 000!',
            '"I need to see a doctor." — ฉันต้องพบแพทย์',
            '"I have travel insurance." — ฉันมีประกันการเดินทาง',
            '"Can you speak more slowly, please?" — ช่วยพูดช้าลงหน่อยได้ไหม',
        ],
    },
    "Alex Patterson": {
        "id":          "alex",
        "name":        "Alex Patterson",
        "specialty":   "Transportation & Navigation English",
        "experience":  "10 years in Perth transit authority and transportation consulting",
        "focus_areas": "Transperth bus/train/ferry, SmartRider, Uber, taxis, directions and navigation",
        "communication_style": (
            "Clear and directional. Expert at explaining routes step-by-step with landmarks. "
            "Calm and well-organized."
        ),
        "tts_voice": "fable",
        "avatar":    "🚌",
        "best_for":  ["transport", "airport"],
        "description": "ผู้เชี่ยวชาญด้านระบบขนส่งในเพิร์ธ เหมาะสำหรับการใช้ Transperth รถแท็กซี่ และการนำทางในเมืองเพิร์ธ",
        "specialty_knowledge": [
            "Expert in Transperth bus, train, and ferry network in Perth",
            "Specializes in SmartRider card system and fare zone navigation",
            "Experienced in airport transfers and public transport connections",
            "Knowledgeable about taxi and rideshare services (Uber) in Perth",
            "Focuses on efficient and confident navigation of Perth's transport system",
        ],
        "common_phrases": [
            '"Which bus goes to the city centre?" — รถบัสสายไหนไปใจกลางเมือง',
            '"Does this train stop at Perth Station?" — รถไฟนี้หยุดที่ Perth Station ไหม',
            '"How much is a SmartRider card?" — SmartRider card ราคาเท่าไหร่',
            '"I\'d like to go to UWA, please." — ขอไป UWA ครับ/ค่ะ',
            '"How long does it take to get there?" — ใช้เวลาเดินทางนานแค่ไหน',
        ],
    },
}


# =============================================================
# SECTION 4 — AUSTRALIAN SLANG & REFERENCE
# =============================================================
SLANG_DATA: Dict[str, List[Dict]] = {
    "general": [
        {"term": "Arvo",        "meaning": "ตอนบ่าย (Afternoon)",                    "example": '"See you this arvo!" = เจอกันบ่ายนี้นะ'},
        {"term": "Brekkie",     "meaning": "อาหารเช้า (Breakfast)",                   "example": '"Let\'s grab brekkie." = ไปกินข้าวเช้ากัน'},
        {"term": "Servo",       "meaning": "ปั๊มน้ำมัน / ร้านสะดวกซื้อ (Service station)", "example": '"Stop at the servo." = แวะปั๊มหน่อย'},
        {"term": "Cheers",      "meaning": "ขอบคุณ / ลาก่อน / ชนแก้ว (ใช้ได้หลายความหมาย)", "example": '"Cheers, mate!" = ขอบคุณนะเพื่อน'},
        {"term": "Mate",        "meaning": "เพื่อน / คนรู้จัก (ใช้กว้างมาก ทั้งคนรู้จักและแปลกหน้า)", "example": '"Thanks, mate!" = ขอบคุณนะ'},
        {"term": "No worries",  "meaning": "ไม่เป็นไร / ได้เลย",                    "example": '"Thanks!" → "No worries!"'},
        {"term": "She'll be right", "meaning": "ไม่ต้องกังวล / โอเคแน่นอน",         "example": '"Will this work?" → "She\'ll be right!"'},
        {"term": "Reckon",      "meaning": "คิดว่า / เชื่อว่า",                       "example": '"I reckon it\'s over there." = ฉันคิดว่าอยู่ทางนั้น'},
        {"term": "Heaps",       "meaning": "เยอะมาก / มากๆ",                          "example": '"Thanks heaps!" = ขอบคุณมากๆ'},
        {"term": "Crook",       "meaning": "ป่วย / ไม่สบาย",                          "example": '"I\'m feeling a bit crook." = ฉันรู้สึกไม่ค่อยสบาย'},
        {"term": "Arvo tea",    "meaning": "มื้อว่างตอนบ่าย (Afternoon tea)",         "example": '"Join us for arvo tea?" = มาดื่มชาตอนบ่ายด้วยกันไหม'},
        {"term": "Bogan",       "meaning": "คนบ้านนอก / คนไม่มีการศึกษา (อย่าใช้กับคนอื่น)", "example": "ใช้เป็น slang อธิบายตัวละครในหนัง"},
        {"term": "Thongs",      "meaning": "รองเท้าแตะ (Flip-flops) ไม่ใช่ชุดชั้นใน!", "example": '"I\'ll just wear thongs to the beach." = ใส่แตะไปทะเล'},
        {"term": "Biscuit",     "meaning": "คุกกี้ / แครกเกอร์ (ไม่ใช่ขนมปัง)",      "example": '"Would you like a biscuit with your tea?" = ขนมกินกับชาไหม'},
        {"term": "Flat out",    "meaning": "ยุ่งมาก / เต็มที่",                       "example": '"I\'ve been flat out all week." = ยุ่งมากทั้งสัปดาห์'},
    ],
    "academic": [
        {"term": "On the same page",  "meaning": "เข้าใจตรงกัน / เห็นด้วยกัน",      "example": '"Are we all on the same page?" = ทุกคนเข้าใจตรงกันไหม'},
        {"term": "Flesh out",         "meaning": "อธิบายให้ละเอียดขึ้น / ขยายความ", "example": '"Could you flesh that out a bit?" = ขยายความได้ไหม'},
        {"term": "Take on board",     "meaning": "รับฟังและพิจารณา",                 "example": '"We\'ll take that on board." = เราจะนำไปพิจารณา'},
        {"term": "Touch base",        "meaning": "ติดต่อ / พูดคุยกันอีกครั้ง",       "example": '"Let\'s touch base tomorrow." = คุยกันใหม่พรุ่งนี้'},
        {"term": "Circle back",       "meaning": "กลับมาพูดถึงอีกครั้ง",             "example": '"Let\'s circle back to that point." = ขอกลับมาที่ประเด็นนั้น'},
        {"term": "Unpack",            "meaning": "วิเคราะห์ / อธิบายให้ลึกขึ้น",    "example": '"Let\'s unpack this idea." = ลองวิเคราะห์ไอเดียนี้'},
        {"term": "Going forward",     "meaning": "ต่อจากนี้ / ในอนาคต",             "example": '"Going forward, we should..." = ต่อจากนี้ เราควร...'},
        {"term": "Bandwidth",         "meaning": "ความสามารถในการรับงาน / ทรัพยากรที่มี", "example": '"I don\'t have the bandwidth for that." = ฉันไม่มีเวลาพอสำหรับเรื่องนั้น'},
    ],
    "polite": [
        {"term": "Would you mind...?", "meaning": "คุณจะว่าอะไรไหมถ้า...? (ขอร้องสุภาพ)", "example": '"Would you mind repeating that?" = ช่วยพูดซ้ำได้ไหม'},
        {"term": "I\'m afraid...",    "meaning": "เสียใจที่ต้องบอกว่า... (ปฏิเสธสุภาพ)", "example": '"I\'m afraid I can\'t make it." = เสียใจที่ไปไม่ได้'},
        {"term": "I wonder if...",    "meaning": "ฉันสงสัยว่า... (ถามสุภาพมาก)",     "example": '"I wonder if you could help me." = อยากทราบว่าช่วยได้ไหม'},
        {"term": "That said...",      "meaning": "อย่างไรก็ตาม... (เปลี่ยนมุมมอง)", "example": '"That\'s great. That said, we should consider..." = แต่ควรพิจารณา...'},
        {"term": "Fair enough",       "meaning": "เข้าใจแล้ว / โอเค / รับได้",       "example": '"Fair enough." = โอเค เข้าใจแล้ว'},
        {"term": "Absolutely",        "meaning": "แน่นอน / เห็นด้วยอย่างยิ่ง",       "example": '"Could you help?" → "Absolutely!"'},
        {"term": "I beg your pardon?", "meaning": "ขอโทษ? (ขอให้พูดซ้ำ — ทางการ)",  "example": "ใช้เมื่อไม่ได้ยิน ทางการกว่า 'Sorry?'"},
    ],
    "emergency": [
        {"term": "Triple Zero (000)",  "meaning": "เบอร์ฉุกเฉินออสเตรเลีย (ตำรวจ ดับเพลิง พยาบาล)", "example": '"Call 000 immediately!" = โทร 000 ทันที'},
        {"term": "Ambulance",          "meaning": "รถพยาบาล",                          "example": '"I need an ambulance." = ต้องการรถพยาบาล'},
        {"term": "A&E / Emergency Dept", "meaning": "ห้องฉุกเฉิน (Accident & Emergency)", "example": '"Take me to A&E, please." = พาไปห้องฉุกเฉิน'},
        {"term": "GP",                 "meaning": "แพทย์ประจำตัว / คลินิกทั่วไป (General Practitioner)", "example": '"I need to see a GP." = ต้องการพบแพทย์'},
        {"term": "Chemist",            "meaning": "ร้านขายยา (Pharmacy)",              "example": '"Is there a chemist nearby?" = มีร้านขายยาใกล้ๆ ไหม'},
    ],
}


# =============================================================
# SECTION 5 — QUICK PHRASE CARDS (per scenario)
# =============================================================
PHRASES_DATA: Dict[str, List[Dict]] = {
    "airport": [
        {"english": "I'm here for a professional development program.",    "thai": "ฉันมาเข้าร่วมโปรแกรมพัฒนาวิชาชีพ",              "context": "ตอบ Immigration Officer"},
        {"english": "I'll be staying for 8 days.",                        "thai": "ฉันจะพักอยู่ 8 วัน",                              "context": "แจ้งระยะเวลาพัก"},
        {"english": "I have nothing to declare.",                          "thai": "ฉันไม่มีสิ่งของต้องสำแดง",                       "context": "ที่ Customs"},
        {"english": "Could you help me find my baggage carousel?",        "thai": "ช่วยบอกที่รับกระเป๋าของฉันได้ไหม",              "context": "ถามที่รับกระเป๋า"},
        {"english": "Is there a shuttle bus to the city?",                "thai": "มีรถรับส่งไปเมืองไหม",                            "context": "ถามการเดินทาง"},
        {"english": "Where can I find a SIM card?",                       "thai": "ซื้อซิมการ์ดได้ที่ไหน",                          "context": "หาซื้อซิม"},
    ],
    "accommodation": [
        {"english": "I have a reservation under the name...",             "thai": "ฉันมีการจองในชื่อ...",                           "context": "เช็คอิน"},
        {"english": "Could I have a wake-up call at 7 AM, please?",      "thai": "ขอให้โทรปลุกตอน 7 โมงเช้าได้ไหม",              "context": "ขอบริการปลุก"},
        {"english": "There seems to be an issue with my room.",           "thai": "ดูเหมือนจะมีปัญหากับห้องฉัน",                   "context": "แจ้งปัญหาห้อง"},
        {"english": "Could I request an extra pillow, please?",           "thai": "ขอหมอนเพิ่มได้ไหม",                              "context": "ขอของเพิ่ม"},
        {"english": "What time is check-out?",                            "thai": "เช็คเอาท์กี่โมง",                                "context": "ถามเวลาเช็คเอาท์"},
        {"english": "Is breakfast included?",                             "thai": "รวมอาหารเช้าไหม",                                "context": "ถามเรื่องอาหารเช้า"},
    ],
    "uwa_campus": [
        {"english": "Could you point me to the Faculty of Education?",    "thai": "ช่วยบอกทางไปคณะศึกษาศาสตร์ได้ไหม",            "context": "ถามทางในวิทยาเขต"},
        {"english": "I'm visiting from Silpakorn University, Thailand.",  "thai": "ฉันมาจากมหาวิทยาลัยศิลปากร ประเทศไทย",        "context": "แนะนำตัว"},
        {"english": "We're here for an educational exchange program.",    "thai": "พวกเรามาเข้าร่วมโปรแกรมแลกเปลี่ยนทางการศึกษา", "context": "อธิบายจุดประสงค์"},
        {"english": "Where is the nearest café on campus?",              "thai": "ร้านกาแฟที่ใกล้ที่สุดในวิทยาเขตอยู่ที่ไหน",   "context": "ถามร้านกาแฟ"},
        {"english": "Could I use the Wi-Fi here?",                       "thai": "ใช้ Wi-Fi ที่นี่ได้ไหม",                          "context": "ขอใช้ Wi-Fi"},
        {"english": "Is there a campus map available?",                  "thai": "มีแผนที่วิทยาเขตให้ไหม",                        "context": "ขอแผนที่"},
    ],
    "academic": [
        {"english": "Thank you so much for having us.",                   "thai": "ขอบคุณมากที่ต้อนรับพวกเรา",                     "context": "ทักทายเจ้าของงาน"},
        {"english": "Could I ask a question about your approach?",       "thai": "ขอถามเกี่ยวกับแนวทางของคุณได้ไหม",             "context": "ขอถามในสัมมนา"},
        {"english": "In Thailand, we tend to approach this differently.", "thai": "ในไทย เรามักจะมีแนวทางที่ต่างกัน",               "context": "แบ่งปันมุมมองไทย"},
        {"english": "This is very insightful. Could you elaborate?",     "thai": "ข้อมูลนี้มีประโยชน์มาก ขยายความได้ไหม",        "context": "ขอข้อมูลเพิ่ม"},
        {"english": "I'd love to explore a potential collaboration.",    "thai": "ยินดีที่จะสำรวจความร่วมมือที่เป็นไปได้",        "context": "แสดงความสนใจร่วมมือ"},
        {"english": "Could I have your contact information?",            "thai": "ขอข้อมูลติดต่อของคุณได้ไหม",                    "context": "ขอช่องทางติดต่อ"},
    ],
    "dining": [
        {"english": "Could I see the menu, please?",                     "thai": "ขอดูเมนูได้ไหม",                                 "context": "ขอเมนู"},
        {"english": "I'm allergic to peanuts.",                          "thai": "ฉันแพ้ถั่วลิสง",                                 "context": "แจ้งอาการแพ้"},
        {"english": "What do you recommend?",                            "thai": "คุณแนะนำอะไร",                                   "context": "ขอคำแนะนำ"},
        {"english": "Could I get this without...?",                      "thai": "ขอสั่งแบบไม่มี... ได้ไหม",                      "context": "ขอปรับเมนู"},
        {"english": "Could we get the bill, please?",                    "thai": "ขอบิลได้ไหม",                                   "context": "ขอบิล"},
        {"english": "Do you have vegetarian options?",                   "thai": "มีตัวเลือกมังสวิรัติไหม",                       "context": "ถามเมนูมังสวิรัติ"},
    ],
    "tourism": [
        {"english": "How do I get to Kings Park from here?",             "thai": "ไป Kings Park จากที่นี่ยังไง",                   "context": "ถามทาง"},
        {"english": "What time does this open/close?",                   "thai": "ที่นี่เปิด/ปิดกี่โมง",                          "context": "ถามเวลา"},
        {"english": "How much is the entry fee?",                        "thai": "ค่าเข้าชมเท่าไหร่",                             "context": "ถามราคา"},
        {"english": "Is there a guided tour available?",                 "thai": "มีทัวร์นำเที่ยวไหม",                            "context": "ถามทัวร์"},
        {"english": "Could you take a photo of us, please?",            "thai": "ช่วยถ่ายรูปพวกเราได้ไหม",                      "context": "ขอให้ถ่ายรูป"},
        {"english": "What's the best way to get to Fremantle?",         "thai": "วิธีที่ดีที่สุดไป Fremantle คืออะไร",            "context": "ถามการเดินทาง"},
    ],
    "shopping": [
        {"english": "How much does this cost?",                          "thai": "นี่ราคาเท่าไหร่",                               "context": "ถามราคา"},
        {"english": "Do you have this in a different size?",            "thai": "มีไซส์อื่นไหม",                                 "context": "ถามไซส์"},
        {"english": "Could I try this on?",                             "thai": "ลองใส่ดูได้ไหม",                                "context": "ขอลองเสื้อผ้า"},
        {"english": "I'd like to return this, please.",                 "thai": "ขอคืนสินค้านี้ได้ไหม",                         "context": "ขอคืนสินค้า"},
        {"english": "Do you offer a tourist refund for GST?",           "thai": "มี GST refund สำหรับนักท่องเที่ยวไหม",           "context": "ถาม GST refund"},
        {"english": "Do you accept credit cards?",                      "thai": "รับบัตรเครดิตไหม",                              "context": "ถามวิธีชำระเงิน"},
    ],
    "transport": [
        {"english": "Which bus goes to the city centre?",               "thai": "รถบัสสายไหนไปใจกลางเมือง",                    "context": "ถามรถบัส"},
        {"english": "How do I get a SmartRider card?",                  "thai": "ขอ SmartRider card ได้ที่ไหน",                  "context": "ถาม SmartRider"},
        {"english": "Does this train stop at Perth Station?",           "thai": "รถไฟนี้หยุดที่ Perth Station ไหม",              "context": "ถามรถไฟ"},
        {"english": "I'd like to go to UWA, please.",                   "thai": "ขอไป UWA ครับ/ค่ะ",                            "context": "บอกปลายทางแท็กซี่"},
        {"english": "How long does it take to get there?",             "thai": "ใช้เวลาเดินทางนานแค่ไหน",                      "context": "ถามเวลาเดินทาง"},
        {"english": "Is there a direct bus to Fremantle?",             "thai": "มีรถบัสตรงไป Fremantle ไหม",                   "context": "ถามรถตรง"},
    ],
    "emergency": [
        {"english": "Please call Triple Zero — 000!",                   "thai": "กรุณาโทร 000!",                                 "context": "ขอให้โทรฉุกเฉิน"},
        {"english": "I need an ambulance!",                             "thai": "ฉันต้องการรถพยาบาล!",                          "context": "ขอรถพยาบาล"},
        {"english": "I need help, please!",                             "thai": "ฉันต้องการความช่วยเหลือ!",                     "context": "ขอความช่วยเหลือ"},
        {"english": "I have travel insurance.",                         "thai": "ฉันมีประกันการเดินทาง",                        "context": "แจ้งประกัน"},
        {"english": "I've lost my passport.",                           "thai": "ฉันทำพาสปอร์ตหาย",                            "context": "แจ้งทำพาสปอร์ตหาย"},
        {"english": "Please speak more slowly.",                        "thai": "ช่วยพูดช้าลงหน่อยได้ไหม",                     "context": "ขอให้พูดช้า"},
    ],
    "social": [
        {"english": "G'day! How are you going?",                        "thai": "สวัสดี! เป็นยังไงบ้าง (ทางการน้อยมาก)",         "context": "ทักทายแบบ Aussie"},
        {"english": "I'm from Thailand — it's my first time in Perth!", "thai": "ฉันมาจากไทย นี่เป็นครั้งแรกที่มาเพิร์ธ!",    "context": "แนะนำตัวในงานสังสรรค์"},
        {"english": "That's brilliant! Tell me more.",                  "thai": "นั่นยอดเยี่ยมมาก! บอกเพิ่มเติมหน่อย",        "context": "แสดงความสนใจ"},
        {"english": "Shall we grab a coffee sometime?",                 "thai": "เดี๋ยวไปดื่มกาแฟด้วยกันได้ไหม",              "context": "ชวนพบปะอย่างไม่เป็นทางการ"},
        {"english": "It was really lovely meeting you!",                "thai": "ยินดีมากที่ได้รู้จัก!",                       "context": "ลาในงาน networking"},
        {"english": "What do you get up to on weekends?",               "thai": "สุดสัปดาห์ทำอะไรบ้าง (Small talk)",           "context": "Small talk"},
    ],
}


# =============================================================
# SECTION 6 — SYSTEM PROMPT TEMPLATES
# =============================================================

COACH_PROMPT = """You are {coach_name}, an expert English Communication Coach helping Thai educators from Silpakorn University navigate their professional development program at The University of Western Australia (UWA) in Perth, Australia.

About You:
- Name: {coach_name}
- Specialty: {specialty}
- Experience: {experience}
- Focus: {focus_areas}
- Style: {communication_style}

Program Context:
- Program: English Language Development Study Tour
- Host: The University of Western Australia (UWA), Perth WA
- Home: Faculty of Education, Silpakorn University, Thailand
- Dates: 29 March – 5 April 2569 (2026)
- Current User Mode: {user_mode_context}
- Current Scenario: {scenario_context}

YOUR PRIMARY ROLE — COMMUNICATION COACH, NOT A GRAMMAR TEACHER:
When users describe in Thai what they want to say, immediately give them the natural English they need. Do NOT explain grammar rules or say "I suggest you use the phrase..." — ACT as a real communication partner and give the language directly.

RESPONSE FORMAT (strictly follow this):
Line 1+: The complete, natural English expression(s) — clear and ready to use
(pronunciation tip in parentheses only if genuinely helpful)
---
Thai explanation, cultural note, and any Australian etiquette relevant to the scenario.

EXAMPLE of a CORRECT response:
"Excuse me, could you help me find the registration office?"
(stress: could YOU help ME)
---
ใช้เมื่อต้องการความช่วยเหลือในวิทยาเขต UWA การใช้ "could" ทำให้ฟังดูสุภาพ 🇦🇺 ชาวออสเตรเลียมักตอบว่า "Sure!" หรือ "No worries!"

แนะนำประโยคถัดไป:
1. "Is there a map of the campus?" → มีแผนที่วิทยาเขตไหม
2. "Which building is the Faculty of...?" → ตึกคณะ...อยู่ที่ไหน
3. "Thank you so much for your help!" → ขอบคุณมากสำหรับความช่วยเหลือ

RULES:
1. Always give the English expression FIRST, before the "---"
2. Always include a 🇦🇺 Australian cultural note when relevant
3. Always include pronunciation tips for challenging words/phrases in (parentheses)
4. Always end with "แนะนำประโยคถัดไป:" with exactly 3 follow-up phrases
5. Never say "I suggest you say..." — just GIVE the English
6. Keep responses warm and confidence-building
7. Focus on Scenario: {scenario_context}

Your Specialist Knowledge:
{specialty_knowledge}

Common Phrases in Your Specialty:
{common_phrases}"""


UNDERSTAND_PROMPT = """You are {coach_name}, an expert English Communication Coach helping Thai educators understand native English speakers and respond naturally at UWA, Perth, Australia.

Your Role — ENGLISH → THAI TRANSLATOR + RESPONSE ADVISOR:
When users input English text they heard or read, you:
1. Translate it clearly to Thai
2. Flag any slang, idioms, or Australian expressions
3. Explain the tone and cultural context
4. Suggest 3 natural English responses

Context:
- Coach: {coach_name} ({specialty})
- Scenario: {scenario_context}
- User Mode: {user_mode_context}

RESPONSE FORMAT (strictly follow this):
🔍 ความหมาย: [clear Thai translation]
[🇦🇺 Australian note if there's slang/idiom — explain it in Thai]
---
📝 บริบท: [tone, situation, cultural notes in Thai]
---
💬 แนะนำการตอบกลับ:
1. [Natural English response] → [ความหมายไทย]
2. [Natural English response] → [ความหมายไทย]
3. [Natural English response] → [ความหมายไทย]

Rules:
- Always translate first
- Always explain Australian slang/idioms when present
- Provide exactly 3 responses matching the scenario's formality level
- Scenario focus: {scenario_context}

Specialist Knowledge:
{specialty_knowledge}"""


CONSULT_PROMPT = """You are {coach_name}, a cross-cultural communication consultant for Thai educators from Silpakorn University's Faculty of Education during their professional development program at The University of Western Australia (UWA), Perth.

Your Role — CULTURAL COMMUNICATION CONSULTANT:
Provide strategic advice, cultural insights, and communication guidance for navigating Australian academic and professional environments.

Program: English Language Development Study Tour
Home: Faculty of Education, Silpakorn University (มหาวิทยาลัยศิลปากร)
Host: The University of Western Australia (UWA), Perth WA 6009
Dates: 29 March – 5 April 2569 (2026)
Key Activities: Academic observations, seminars, cultural exchange, professional networking
Locations: UWA Crawley Campus, Perth CBD, Kings Park, Fremantle

Context:
- Coach: {coach_name} ({specialty})
- Scenario: {scenario_context}
- User Mode: {user_mode_context}

Respond primarily in Thai. Include English examples when helpful.

Key Cultural Contrasts to Address:
🇦🇺 Australians are typically direct and informal even in professional settings
🇦🇺 First names are standard even with professors ("Call me John, please")
🇦🇺 Questions and respectful disagreement are encouraged in seminars
🇦🇺 "No worries" and "Cheers" are genuine expressions, not dismissive
🇹🇭 vs 🇦🇺 Hierarchy: Australian workplaces are much flatter than Thai ones — this can feel surprising

Specialist Knowledge:
{specialty_knowledge}

Always give practical, actionable advice to help Thai educators succeed at UWA."""


PRONUNCIATION_PROMPT = """You are {coach_name}, a specialist English pronunciation and expression coach for Thai educators at UWA.

Your Role — PRONUNCIATION & EXPRESSION ANALYST:
Analyze English sentences the user wants to say and provide:
1. Naturalness assessment
2. Stress and rhythm guide
3. More natural alternative phrasings
4. Common Thai-speaker pitfalls for this phrase
5. Australian English note (if relevant)

User Mode: {user_mode_context}

RESPONSE FORMAT (always in Thai):
✅ การประเมิน: [เป็นธรรมชาติ / ค่อนข้างเป็นธรรมชาติ / แนะนำให้ปรับ]

🎯 Stress & Rhythm:
[แสดงการเน้นเสียง เช่น "Could YOU help ME?" หรือ "I'd LIKE to ORDER please"]

🔄 ทางเลือกที่เป็นธรรมชาติกว่า:
1. [alternative 1]
2. [alternative 2]

⚠️ จุดระวังสำหรับคนไทย:
[Common mistakes Thai speakers make with this phrase — e.g., syllable timing, th-sound, final consonants, rising vs. falling intonation]

🇦🇺 Australian English Note:
[Difference from British/American if relevant; otherwise omit]

Key Focus Areas for Thai Speakers:
- Final consonant sounds (often reduced or dropped in Thai)
- Th-sounds (ð as in "the" and θ as in "think")
- Vowel length and stress-timed rhythm (Thai is syllable-timed)
- Rising intonation for genuine questions vs. falling for statements
- Word linking and natural speech flow"""


# =============================================================
# SECTION 7 — SESSION MANAGEMENT
# =============================================================
sessions: Dict[str, Dict[str, Any]] = {}


def create_session(session_id: str) -> Dict[str, Any]:
    """Initialize a new session with default state."""
    return {
        "session_id":           session_id,
        "coach_name":           "Dr. Emma Clarke",
        "scenario":             "uwa_campus",
        "user_mode":            "educator",
        "history":              [],   # main coach chat
        "understand_history":   [],   # understand-native tab
        "consult_history":      [],   # consultation tab
        "pronunciation_history": [],  # pronunciation tab
        "request_timestamps":   [],
        "created_at":           time.time(),
        "last_active":          time.time(),
    }


def get_session(session_id: str) -> Dict[str, Any]:
    """Return existing session or create a new one."""
    if session_id not in sessions:
        sessions[session_id] = create_session(session_id)
    sessions[session_id]["last_active"] = time.time()
    return sessions[session_id]


def cleanup_sessions() -> None:
    """Remove sessions that have been inactive for SESSION_TIMEOUT seconds."""
    now = time.time()
    expired = [
        sid for sid, s in sessions.items()
        if now - s["last_active"] > SESSION_TIMEOUT
    ]
    for sid in expired:
        del sessions[sid]
    if expired:
        logger.info(f"Cleaned up {len(expired)} expired session(s)")


def check_rate_limit(session: Dict) -> bool:
    """Sliding-window rate limiter. Returns True if request is allowed."""
    now = time.time()
    ts = [t for t in session.get("request_timestamps", []) if now - t <= RATE_LIMIT_WINDOW]
    if len(ts) >= MAX_REQUESTS_PER_MIN:
        session["request_timestamps"] = ts
        return False
    ts.append(now)
    session["request_timestamps"] = ts
    return True


# =============================================================
# SECTION 8 — SYSTEM PROMPT BUILDERS
# =============================================================

def _coach_data(coach_name: str) -> Dict:
    return COACHES.get(coach_name, COACHES["Dr. Emma Clarke"])

def _scenario_data(scenario: str) -> Dict:
    return SCENARIOS.get(scenario, SCENARIOS["uwa_campus"])

def _mode_data(user_mode: str) -> Dict:
    return USER_MODES.get(user_mode, USER_MODES["educator"])


def build_coach_prompt(coach_name: str, scenario: str, user_mode: str) -> str:
    c = _coach_data(coach_name)
    return COACH_PROMPT.format(
        coach_name        = c["name"],
        specialty         = c["specialty"],
        experience        = c["experience"],
        focus_areas       = c["focus_areas"],
        communication_style = c["communication_style"],
        user_mode_context = _mode_data(user_mode)["context"],
        scenario_context  = _scenario_data(scenario)["context"],
        specialty_knowledge = "\n".join(f"- {k}" for k in c["specialty_knowledge"]),
        common_phrases    = "\n".join(f"- {p}" for p in c["common_phrases"]),
    )


def build_understand_prompt(coach_name: str, scenario: str, user_mode: str) -> str:
    c = _coach_data(coach_name)
    return UNDERSTAND_PROMPT.format(
        coach_name          = c["name"],
        specialty           = c["specialty"],
        scenario_context    = _scenario_data(scenario)["context"],
        user_mode_context   = _mode_data(user_mode)["context"],
        specialty_knowledge = "\n".join(f"- {k}" for k in c["specialty_knowledge"]),
    )


def build_consult_prompt(coach_name: str, scenario: str, user_mode: str) -> str:
    c = _coach_data(coach_name)
    return CONSULT_PROMPT.format(
        coach_name          = c["name"],
        specialty           = c["specialty"],
        scenario_context    = _scenario_data(scenario)["context"],
        user_mode_context   = _mode_data(user_mode)["context"],
        specialty_knowledge = "\n".join(f"- {k}" for k in c["specialty_knowledge"]),
    )


def build_pronunciation_prompt(coach_name: str, user_mode: str) -> str:
    c = _coach_data(coach_name)
    return PRONUNCIATION_PROMPT.format(
        coach_name        = c["name"],
        user_mode_context = _mode_data(user_mode)["context"],
    )


# =============================================================
# SECTION 9 — TTS PIPELINE
# =============================================================

def filter_for_tts(text: str) -> str:
    """
    Prepare text for TTS:
      1. Extract English section (before first '---')
      2. Remove *action text*  e.g. *smiles warmly*
      3. Remove (parenthetical notes)  e.g. (stress: FIRST syllable)
      4. Remove emoji characters
      5. Strip markdown bold/italic markers
      6. Normalize whitespace
    """
    # 1. English section only
    english = text.split("---")[0].strip()

    # 2. Remove *action text*
    english = re.sub(r'\*[^*]+\*', '', english)

    # 3. Remove (parenthetical notes)
    english = re.sub(r'\([^)]*\)', '', english)

    # 4. Remove emoji / non-ASCII non-Latin non-Thai characters
    english = re.sub(
        r'[^\x00-\x7F\u00C0-\u024F\u1E00-\u1EFF\u0E00-\u0E7F\s]', '', english
    )

    # 5. Strip markdown
    english = re.sub(r'\*\*([^*]+)\*\*', r'\1', english)
    english = re.sub(r'\*([^*]+)\*', r'\1', english)

    # 6. Normalize whitespace
    english = re.sub(r'\s+', ' ', english).strip()

    return english or text.split("---")[0].strip()


async def generate_tts_audio(text: str, voice: str) -> Optional[bytes]:
    """Generate TTS audio and return bytes. Does NOT write to disk."""
    if not TTS_API_KEY:
        logger.error("TTS_API_KEY not configured")
        return None

    filtered = filter_for_tts(text)
    if not filtered:
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {TTS_API_KEY}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model": TTS_MODEL,
                    "voice": voice,
                    "input": filtered,
                },
            )
            resp.raise_for_status()

        logger.info(f"TTS generated ({len(resp.content)} bytes)")
        return resp.content

    except Exception as exc:
        logger.error(f"TTS generation failed: {exc}")
        return None


# =============================================================
# SECTION 10 — LLM STREAMING HELPER
# =============================================================

async def stream_llm(system_prompt: str, messages: List[Dict]):
    """Async generator yielding text chunks from the LLM."""
    if not API_KEY:
        yield "⚠️ API_KEY ไม่ได้ตั้งค่า กรุณาตรวจสอบไฟล์ .env"
        return

    payload = {
        "model":       API_MODEL,
        "messages":    [{"role": "system", "content": system_prompt}] + messages,
        "max_tokens":  1024,
        "temperature": 0.7,
        "stream":      True,
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type":  "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{API_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        content = chunk["choices"][0]["delta"].get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError):
                        continue

    except httpx.HTTPStatusError as exc:
        logger.error(f"LLM HTTP error {exc.response.status_code}")
        yield f"\n\n⚠️ เกิดข้อผิดพลาดจาก API: {exc.response.status_code}"
    except Exception as exc:
        logger.error(f"LLM streaming error: {exc}")
        yield f"\n\n⚠️ เกิดข้อผิดพลาด: {exc}"


def build_messages(history: List[Dict]) -> List[Dict]:
    """Convert session history list to OpenAI messages format."""
    msgs = []
    for turn in history:
        msgs.append({"role": "user",      "content": turn["user"]})
        if turn.get("assistant"):
            msgs.append({"role": "assistant", "content": turn["assistant"]})
    return msgs


# =============================================================
# SECTION 11 — PYDANTIC REQUEST MODELS
# =============================================================

class SessionConfig(BaseModel):
    session_id: str
    coach_name: str
    scenario:   str
    user_mode:  str

class ChatRequest(BaseModel):
    session_id: str
    message:    str

class TTSRequest(BaseModel):
    session_id: str
    text:       str

class ClearRequest(BaseModel):
    session_id: str

class SaveRequest(BaseModel):
    session_id: str
    history:    List[Dict]
    mode:       str = "chat"   # chat | understand | consult | pronunciation


# =============================================================
# SECTION 12 — ROUTE: INDEX
# =============================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


# =============================================================
# SECTION 13 — ROUTE: SESSION
# =============================================================

@app.post("/api/session/init")
async def init_session(config: SessionConfig):
    """Initialize or update session config (coach / scenario / mode)."""
    cleanup_sessions()
    session = get_session(config.session_id)

    # Validate inputs; fall back to defaults if unknown
    session["coach_name"] = config.coach_name if config.coach_name in COACHES   else "Dr. Emma Clarke"
    session["scenario"]   = config.scenario   if config.scenario   in SCENARIOS else "uwa_campus"
    session["user_mode"]  = config.user_mode  if config.user_mode  in USER_MODES else "educator"

    coach    = _coach_data(session["coach_name"])
    scenario = _scenario_data(session["scenario"])
    mode     = _mode_data(session["user_mode"])

    return {
        "status":     "ok",
        "session_id": config.session_id,
        "coach": {
            "name":       coach["name"],
            "avatar":     coach["avatar"],
            "specialty":  coach["specialty"],
            "tts_voice":  coach["tts_voice"],
            "description": coach["description"],
        },
        "scenario":  scenario["name"],
        "user_mode": mode["name"],
    }


# =============================================================
# SECTION 14 — ROUTE: CHAT (MAIN COACH)
# =============================================================

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """SSE streaming — main English coach conversation."""
    session = get_session(req.session_id)

    if not check_rate_limit(session):
        raise HTTPException(429, "คุณส่งข้อความเร็วเกินไป กรุณารอสักครู่")
    if len(session["history"]) >= MAX_HISTORY:
        raise HTTPException(400, "ถึงขีดจำกัดจำนวนข้อความ กรุณาล้างการสนทนา")

    system_prompt = build_coach_prompt(
        session["coach_name"], session["scenario"], session["user_mode"]
    )
    messages = build_messages(session["history"])
    messages.append({"role": "user", "content": req.message})

    idx = len(session["history"])
    session["history"].append({"user": req.message, "assistant": ""})
    full: list[str] = []

    async def generate():
        async for chunk in stream_llm(system_prompt, messages):
            full.append(chunk)
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        complete = "".join(full)
        session["history"][idx]["assistant"] = complete
        yield f"data: {json.dumps({'done': True, 'full_response': complete})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# =============================================================
# SECTION 15 — ROUTE: UNDERSTAND NATIVE SPEAKER
# =============================================================

@app.post("/api/understand")
async def understand_endpoint(req: ChatRequest):
    """SSE streaming — understand native English speaker."""
    session = get_session(req.session_id)

    if not check_rate_limit(session):
        raise HTTPException(429, "คุณส่งข้อความเร็วเกินไป กรุณารอสักครู่")
    if len(session["understand_history"]) >= MAX_HISTORY:
        raise HTTPException(400, "ถึงขีดจำกัดจำนวนข้อความ กรุณาล้างประวัติ")

    system_prompt = build_understand_prompt(
        session["coach_name"], session["scenario"], session["user_mode"]
    )
    messages = build_messages(session["understand_history"])
    messages.append({
        "role": "user",
        "content": f"กรุณาแปลและอธิบายข้อความภาษาอังกฤษนี้: {req.message}",
    })

    idx = len(session["understand_history"])
    session["understand_history"].append({"user": req.message, "assistant": ""})
    full: list[str] = []

    async def generate():
        async for chunk in stream_llm(system_prompt, messages):
            full.append(chunk)
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        complete = "".join(full)
        session["understand_history"][idx]["assistant"] = complete
        yield f"data: {json.dumps({'done': True, 'full_response': complete})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# =============================================================
# SECTION 16 — ROUTE: CONSULTATION
# =============================================================

@app.post("/api/consult")
async def consult_endpoint(req: ChatRequest):
    """SSE streaming — cultural communication consultation."""
    session = get_session(req.session_id)

    if not check_rate_limit(session):
        raise HTTPException(429, "คุณส่งข้อความเร็วเกินไป กรุณารอสักครู่")
    if len(session["consult_history"]) >= MAX_HISTORY:
        raise HTTPException(400, "ถึงขีดจำกัดจำนวนข้อความ กรุณาล้างประวัติ")

    system_prompt = build_consult_prompt(
        session["coach_name"], session["scenario"], session["user_mode"]
    )
    messages = build_messages(session["consult_history"])
    messages.append({"role": "user", "content": req.message})

    idx = len(session["consult_history"])
    session["consult_history"].append({"user": req.message, "assistant": ""})
    full: list[str] = []

    async def generate():
        async for chunk in stream_llm(system_prompt, messages):
            full.append(chunk)
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        complete = "".join(full)
        session["consult_history"][idx]["assistant"] = complete
        yield f"data: {json.dumps({'done': True, 'full_response': complete})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# =============================================================
# SECTION 17 — ROUTE: PRONUNCIATION FEEDBACK
# =============================================================

@app.post("/api/pronunciation")
async def pronunciation_endpoint(req: ChatRequest):
    """SSE streaming — pronunciation and expression feedback."""
    session = get_session(req.session_id)

    if not check_rate_limit(session):
        raise HTTPException(429, "คุณส่งข้อความเร็วเกินไป กรุณารอสักครู่")

    system_prompt = build_pronunciation_prompt(
        session["coach_name"], session["user_mode"]
    )
    messages = [{
        "role": "user",
        "content": f'วิเคราะห์การออกเสียงและความเป็นธรรมชาติของประโยคนี้: "{req.message}"',
    }]

    if "pronunciation_history" not in session:
        session["pronunciation_history"] = []
    idx = len(session["pronunciation_history"])
    session["pronunciation_history"].append({"user": req.message, "assistant": ""})
    full: list[str] = []

    async def generate():
        async for chunk in stream_llm(system_prompt, messages):
            full.append(chunk)
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        complete = "".join(full)
        session["pronunciation_history"][idx]["assistant"] = complete
        yield f"data: {json.dumps({'done': True, 'full_response': complete})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# =============================================================
# SECTION 18 — ROUTE: TTS
# =============================================================

@app.post("/api/tts")
async def tts_endpoint(req: TTSRequest):
    """Generate TTS audio for the given text. Returns audio bytes directly."""
    session  = get_session(req.session_id)
    coach    = _coach_data(session.get("coach_name", "Dr. Emma Clarke"))
    voice    = coach.get("tts_voice", "nova")

    audio_bytes = await generate_tts_audio(req.text, voice)
    if not audio_bytes:
        raise HTTPException(500, "ไม่สามารถสร้างเสียงได้ กรุณาตรวจสอบ TTS_API_KEY")

    return StreamingResponse(
        iter([audio_bytes]),
        media_type="audio/mpeg",
        headers={"Content-Disposition": 'attachment; filename="speech.mp3"'},
    )


# =============================================================
# SECTION 19 — ROUTE: REFERENCE DATA
# =============================================================

@app.get("/api/phrases/{scenario}")
async def get_phrases(scenario: str):
    """Return Quick Phrase Cards for the given scenario."""
    if scenario not in PHRASES_DATA:
        raise HTTPException(404, f"Scenario '{scenario}' not found")
    return {
        "scenario":      scenario,
        "scenario_name": SCENARIOS.get(scenario, {}).get("name", scenario),
        "phrases":       PHRASES_DATA[scenario],
    }


@app.get("/api/slang")
async def get_slang():
    """Return the full Australian Slang & Reference dictionary."""
    return SLANG_DATA


@app.get("/api/coaches")
async def get_coaches():
    """Return metadata for all available coaches."""
    return {
        name: {
            "id":          c["id"],
            "name":        c["name"],
            "specialty":   c["specialty"],
            "avatar":      c["avatar"],
            "description": c["description"],
            "best_for":    c["best_for"],
            "tts_voice":   c["tts_voice"],
        }
        for name, c in COACHES.items()
    }


@app.get("/api/scenarios")
async def get_scenarios():
    """Return all available scenarios."""
    return {
        key: {"name": s["name"], "description": s["description"]}
        for key, s in SCENARIOS.items()
    }


# =============================================================
# SECTION 20 — ROUTE: CLEAR HISTORY
# =============================================================

@app.post("/api/clear/{mode}")
async def clear_history(mode: str, req: ClearRequest):
    """Clear conversation history for the specified mode."""
    mode_map = {
        "chat":          "history",
        "understand":    "understand_history",
        "consult":       "consult_history",
        "pronunciation": "pronunciation_history",
    }
    if mode not in mode_map:
        raise HTTPException(400, f"Unknown mode: {mode}")

    session = get_session(req.session_id)
    session[mode_map[mode]] = []
    return {"status": "ok", "mode": mode}


# =============================================================
# SECTION 21 — ROUTE: SAVE CONVERSATION
# =============================================================

@app.post("/api/save")
async def save_conversation(req: SaveRequest):
    """Serialize conversation history to formatted text. Returns content string."""
    if not req.history:
        raise HTTPException(400, "ไม่มีประวัติการสนทนา")

    session      = get_session(req.session_id)
    coach_name   = session.get("coach_name", "Unknown")
    scenario_key = session.get("scenario", "uwa_campus")
    scenario_name = SCENARIOS.get(scenario_key, {}).get("name", scenario_key)
    now          = datetime.now()

    mode_labels = {
        "chat":          "💬 ใช้งาน Coach",
        "understand":    "🔄 เข้าใจเจ้าของภาษา",
        "consult":       "🤝 ปรึกษา Coach",
        "pronunciation": "🎙️ ฝึกสำเนียง",
    }
    mode_label = mode_labels.get(req.mode, req.mode)

    lines = [
        "📝 บันทึกการสนทนา — English Communication Assistant for UWA Study Tour 2569",
        f"📅 วันที่  : {now.strftime('%Y-%m-%d')}",
        f"⏰ เวลา   : {now.strftime('%H:%M:%S')}",
        f"👨‍🏫 Coach  : {coach_name}",
        f"🗺️ สถานการณ์: {scenario_name}",
        f"📋 โหมด   : {mode_label}",
        "=" * 60,
        "",
    ]

    for turn in req.history:
        lines += [
            f"👤 ผู้ใช้: {turn.get('user', '')}",
            "",
            f"👨‍🏫 Coach: {turn.get('assistant', '')}",
            "",
            "-" * 50,
            "",
        ]

    content  = "\n".join(lines)
    filename = f"uwa_conversation_{now.strftime('%Y%m%d_%H%M%S')}.txt"
    return {"status": "ok", "content": content, "filename": filename}


# =============================================================
# SECTION 22 — ROUTE: HEALTH CHECK
# =============================================================

@app.get("/api/health")
async def health_check():
    return {
        "status":          "ok",
        "active_sessions": len(sessions),
        "api_configured":  bool(API_KEY),
        "tts_configured":  bool(TTS_API_KEY),
        "model":           API_MODEL,
        "coaches":         len(COACHES),
        "scenarios":       len(SCENARIOS),
    }


# =============================================================
# SECTION 23 — STARTUP EVENT
# =============================================================

@app.on_event("startup")
async def on_startup():
    logger.info("=" * 60)
    logger.info("English Communication Assistant — UWA Study Tour 2569")
    logger.info("Faculty of Education, Silpakorn University")
    logger.info(f"  API Base   : {API_BASE_URL}")
    logger.info(f"  API Model  : {API_MODEL}")
    logger.info(f"  API Key    : {'✓ configured' if API_KEY    else '✗ MISSING'}")
    logger.info(f"  TTS Key    : {'✓ configured' if TTS_API_KEY else '✗ MISSING'}")
    logger.info(f"  Coaches    : {len(COACHES)}")
    logger.info(f"  Scenarios  : {len(SCENARIOS)}")
    logger.info("=" * 60)


# =============================================================
# ENTRY POINT
# =============================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)