import http.server
import socketserver
import os
import json
import base64
import urllib.request
import urllib.parse
import threading
import time
import datetime

PORT = 8000

# ==========================================================
# ⚙️ إعدادات
# ==========================================================
BOT_TOKEN = "8789483444:AAE0Y9PWpVzXcy-vfl2Pzh4WG7PsdlrGtsY"
ADMIN_ID = 8980535537
CHAT_ID = str(ADMIN_ID)

BG_FILE = "wheel_bg.jpg"
AUDIO_FILE = "wheel_audio.ogg"
SPINS_FILE = "spins.json"  # ملف لحفظ أوقات اللعب حسب الـ IP

LAST_UPDATE = 0
COOLDOWN = 24 * 60 * 60  # 24 ساعة بالثواني

# ==========================================================
# 💾 قاعدة بيانات بسيطة (ملف JSON) لتتبع اللعب
# ==========================================================
def load_spins():
    if os.path.exists(SPINS_FILE):
        try:
            with open(SPINS_FILE, "r") as f:
                return json.load(f)
        except: return {}
    return {}

def save_spins(data):
    with open(SPINS_FILE, "w") as f:
        json.dump(data, f)

def can_spin(ip):
    data = load_spins()
    last = data.get(ip, 0)
    return (time.time() - last) >= COOLDOWN

def record_spin(ip):
    data = load_spins()
    data[ip] = time.time()
    save_spins(data)

def get_remaining(ip):
    data = load_spins()
    last = data.get(ip, 0)
    rem = COOLDOWN - (time.time() - last)
    return max(0, int(rem))

# ==========================================================
# 🖼️ تحميل الخلفية (Base64)
# ==========================================================
def get_bg_base64():
    if os.path.exists(BG_FILE):
        with open(BG_FILE, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        return f"data:image/jpeg;base64,{data}"
    return ""

# ==========================================================
# 📤 إرسال رسالة إلى تلغرام
# ==========================================================
def send_telegram(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode())
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print("❌ خطأ إرسال تلغرام:", e)
        return False

# ==========================================================
# 📥 تحميل ملف من تلغرام
# ==========================================================
def get_file_url(file_id):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode())
        if data.get("ok"):
            path = data["result"]["file_path"]
            return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{path}"
    except Exception as e:
        print("❌ خطأ getFile:", e)
    return None

def download_file(url, dest):
    try:
        urllib.request.urlretrieve(url, dest)
        return True
    except Exception as e:
        print("❌ خطأ تنزيل:", e)
        return False

# ==========================================================
# 🤖 حلقة البوت (Polling)
# ==========================================================
def bot_loop():
    global LAST_UPDATE
    print("🤖 بدء البوت...")
    waiting_for_bg = set()
    waiting_for_audio = set()

    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={LAST_UPDATE+1}&timeout=30"
            with urllib.request.urlopen(url, timeout=35) as r:
                data = json.loads(r.read().decode())

            if not data.get("ok"): 
                time.sleep(2); continue

            for upd in data.get("result", []):
                LAST_UPDATE = upd["update_id"]
                msg = upd.get("message")
                if not msg: continue
                
                chat_id = msg["chat"]["id"]
                user_id = msg["from"]["id"]
                text = (msg.get("text") or "").strip()

                if text.startswith("/add"):
                    if user_id != ADMIN_ID:
                        send_telegram(chat_id, "⛔ لا تملك صلاحية هذا الأمر.")
                        continue
                    
                    keyboard = {
                        "keyboard": [
                            [{"text": "🖼️ تعيين خلفية العجلة"}],
                            [{"text": "🎵 تعيين مقطع صوتي"}]
                        ],
                        "resize_keyboard": True
                    }
                    send_telegram(chat_id, "✅ تم تفعيل لوحة الإدارة.", keyboard)

                elif text == "🖼️ تعيين خلفية العجلة":
                    if user_id != ADMIN_ID: continue
                    waiting_for_bg.add(user_id)
                    waiting_for_audio.discard(user_id)
                    send_telegram(chat_id, "📸 الآن أرسل الصورة التي تريد تعيينها كخلفية:")

                elif text == "🎵 تعيين مقطع صوتي":
                    if user_id != ADMIN_ID: continue
                    waiting_for_audio.add(user_id)
                    waiting_for_bg.discard(user_id)
                    send_telegram(chat_id, "ارسل لمقطع صوتي :")

                elif msg.get("photo") and user_id in waiting_for_bg:
                    file_id = msg["photo"][-1]["file_id"]
                    file_url = get_file_url(file_id)
                    if file_url and download_file(file_url, BG_FILE):
                        waiting_for_bg.discard(user_id)
                        send_telegram(chat_id, "✅ تم تعيين الصورة كخلفية للعجلة والموقع.")
                    else:
                        send_telegram(chat_id, "❌ فشل تحميل الصورة.")

                elif (msg.get("audio") or msg.get("voice") or msg.get("video_note")) and user_id in waiting_for_audio:
                    audio_obj = msg.get("audio") or msg.get("voice") or msg.get("video_note")
                    file_id = audio_obj["file_id"]
                    file_url = get_file_url(file_id)
                    
                    if file_url and download_file(file_url, AUDIO_FILE):
                        waiting_for_audio.discard(user_id)
                        send_telegram(chat_id, "✅ تم تعيين صوت للعجلة")
                    else:
                        send_telegram(chat_id, "❌ فشل تحميل المقطع الصوتي.")

        except Exception as e:
            print("⚠️ خطأ حلقة البوت:", e)
            time.sleep(3)

# ==========================================================
# 🌐 صفحة الموقع
# ==========================================================
def build_page():
    bg_b64 = get_bg_base64()
    audio_version = int(os.path.getmtime(AUDIO_FILE)) if os.path.exists(AUDIO_FILE) else 0
    
    page = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>عجلة الحظ الفخمة - Max4win Eagle</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{height:100%}
body{
  font-family:'Segoe UI',Tahoma,sans-serif;
  background: #05000a;
  color:#fff;display:flex;align-items:center;justify-content:center;
  min-height:100vh;overflow:hidden;position:fixed;
  width:100%;
  background-size: cover;
  background-position: center;
}
body::before {
  content: "";
  position: fixed;
  inset: 0;
  background-image: url('__BG_IMAGE__');
  background-size: cover;
  background-position: center;
  opacity: 0.4;
  z-index: -1;
}

.stage{position:relative;z-index:10;display:flex;flex-direction:column;align-items:center;gap:20px;padding:18px}
.title{
  font-size:clamp(20px,4vw,34px);font-weight:900;
  background:linear-gradient(90deg,#ff0080,#ffcc00,#00d4ff,#b000ff);
  -webkit-background-clip:text;background-clip:text;color:transparent;text-align:center;
  text-shadow: 0 0 10px rgba(0,0,0,0.8);
}
.wheel-wrap{position:relative;width:min(86vw,420px);aspect-ratio:1/1;display:flex;align-items:center;justify-content:center}
.ring-border{
  position:absolute;inset:-6px;border-radius:50%;
  background:conic-gradient(from 0deg,#ffd700,#fff8b0,#ffb700,#fff,#ffd700);
  box-shadow:0 0 24px rgba(255,215,0,.6);
}
#wheelRotator{
  position:absolute;inset:0;border-radius:50%;
  will-change:transform;transform-origin:50% 50%;overflow:hidden;
}
#wheelRotator svg{width:100%;height:100%;display:block;border-radius:50%}
.pointer{
  position:absolute;top:-14px;left:50%;transform:translateX(-50%);z-index:5;
  width:0;height:0;border-left:16px solid transparent;border-right:16px solid transparent;
  border-top:30px solid #ffd700;filter:drop-shadow(0 0 8px #ffd700);
}
.hub{
  position:absolute;z-index:3;width:64px;height:64px;border-radius:50%;
  background:radial-gradient(circle at 35% 30%,#fff,#ffd700 40%,#b8860b 100%);
  box-shadow:0 0 18px rgba(255,215,0,.8),inset 0 0 10px rgba(0,0,0,.4);
  display:flex;align-items:center;justify-content:center;font-weight:900;color:#4a2b00;font-size:12px;
}
.spin-btn{
  position:relative;z-index:10;cursor:pointer;border:none;
  padding:15px 56px;border-radius:60px;font-size:19px;font-weight:900;color:#1a0030;
  background:linear-gradient(135deg,#ffe259,#ffa751);
  box-shadow:0 0 20px rgba(255,180,0,.7),0 6px 20px rgba(0,0,0,.5);
  transition:transform .15s;letter-spacing:1px;
}
.spin-btn:hover{transform:translateY(-2px) scale(1.03)}
.spin-btn:active{transform:scale(.97)}
.spin-btn:disabled{opacity:.6;cursor:not-allowed}

/* تصميم العداد التنازلي */
.cooldown-box {
  background: rgba(0,0,0,0.7);
  padding: 15px 25px;
  border-radius: 15px;
  border: 2px solid #ff5577;
  box-shadow: 0 0 20px rgba(255,85,119,0.5);
  text-align: center;
  font-size: 18px;
  font-weight: bold;
  color: #fff;
  display: none;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.cooldown-box.show { display: flex; }
.timer {
  font-size: 28px;
  color: #ffd700;
  font-family: monospace;
  direction: ltr;
}

.result{
  min-height:52px;font-size:clamp(18px,4vw,28px);font-weight:900;text-align:center;
  opacity:0;transform:scale(.8);transition:opacity .4s,transform .4s;padding:0 10px;
}
.result.show{opacity:1;transform:scale(1)}
.result.lose{color:#ff5577;text-shadow:0 0 16px #ff5577}
</style>
</head>
<body>
<div class="stage">
  <div class="title">✦ Max4win Eagle ✦</div>
  <div class="wheel-wrap">
    <div class="ring-border"></div>
    <div class="pointer"></div>
    <div id="wheelRotator"><svg id="wheel" viewBox="0 0 400 400"></svg></div>
    <div class="hub">SPIN</div>
  </div>
  
  <div class="cooldown-box" id="cooldownBox">
    <span>⏳ لقد لعبت بالفعل! يرجى الانتظار:</span>
    <span class="timer" id="timer">00:00:00</span>
  </div>

  <div class="result" id="result"></div>
  <button class="spin-btn" id="spinBtn">دَوِّر العجلة</button>
</div>

<script>
const BG_IMAGE = "__BG_IMAGE__";
const AUDIO_URL = "/audio?v=__AUDIO_VER__";

const bgAudio = new Audio(AUDIO_URL);
bgAudio.loop = true;
bgAudio.volume = 0.6;

document.body.addEventListener('click', () => {
    if (bgAudio.paused) bgAudio.play().catch(e => console.log(e));
}, { once: true });
bgAudio.play().catch(e => console.log(e));

const PRIZES = [
  {label:"10 ليرة",   color:"#8b00ff", text:"#ffffff"},
  {label:"20 ليرة",   color:"#00c2ff", text:"#ffffff"},
  {label:"1000 ليرة", color:"#ffcc00", text:"#3a2800"},
  {label:"5000 ليرة", color:"#ff0080", text:"#ffffff"},
  {label:"5 ليرات",   color:"#00e08a", text:"#003322"},
  {label:"حظ أوفر",   color:"#444466", text:"#ff5577"}
];

const LOSE_INDEX = 5; 

const N = PRIZES.length;
const SVG = document.getElementById('wheel');
const ROT = document.getElementById('wheelRotator');
const CX = 200, CY = 200, R = 195;
const segAngle = 360 / N;

function polar(cx,cy,r,deg){
  const rad = (deg-90) * Math.PI/180;
  return {x: cx + r*Math.cos(rad), y: cy + r*Math.sin(rad)};
}
function wedgePath(s,e){
  const p1 = polar(CX,CY,R,s), p2 = polar(CX,CY,R,e);
  const large = (e-s) > 180 ? 1 : 0;
  return `M ${CX} ${CY} L ${p1.x} ${p1.y} A ${R} ${R} 0 ${large} 1 ${p2.x} ${p2.y} Z`;
}

let svg = '';
if(BG_IMAGE && BG_IMAGE.length > 100){
  svg += `<defs>
    <pattern id="bgImage" patternUnits="userSpaceOnUse" width="${2*R}" height="${2*R}" x="${CX-R}" y="${CY-R}">
      <image href="${BG_IMAGE}" x="0" y="0" width="${2*R}" height="${2*R}" preserveAspectRatio="xMidYMid slice"/>
    </pattern>
  </defs>`;
  svg += `<circle cx="${CX}" cy="${CY}" r="${R}" fill="url(#bgImage)"/>`;
} else {
  svg += `<circle cx="${CX}" cy="${CY}" r="${R}" fill="#1a0533"/>`;
}
svg += `<circle cx="${CX}" cy="${CY}" r="${R+1}" fill="none" stroke="#ffd700" stroke-width="4"/>`;

for(let i=0;i<N;i++){
  const a0 = i*segAngle, a1 = (i+1)*segAngle;
  svg += `<path d="${wedgePath(a0,a1)}" fill="${PRIZES[i].color}" opacity="0.55" stroke="#1a0030" stroke-width="2"/>`;
  const mid = a0 + segAngle/2;
  const pm = polar(CX,CY,R*0.62,mid);
  svg += `<text x="${pm.x}" y="${pm.y}" fill="${PRIZES[i].text}" font-size="19" font-weight="900"
           text-anchor="middle" dominant-baseline="middle"
           transform="rotate(${mid} ${pm.x} ${pm.y})"
           style="paint-order:stroke;stroke:#000;stroke-width:4px;stroke-linejoin:round;">${PRIZES[i].label}</text>`;
}
for(let i=0;i<N;i++){
  const p = polar(CX,CY,R-7,i*segAngle);
  svg += `<circle cx="${p.x}" cy="${p.y}" r="4.5" fill="#ffd700" stroke="#8b6914" stroke-width="1.5"/>`;
}
SVG.innerHTML = svg;

let audioCtx = null;
function ensureAudio(){
  if(!audioCtx) audioCtx = new (window.AudioContext||window.webkitAudioContext)();
  if(audioCtx.state === 'suspended') audioCtx.resume();
}
function tick(){
  if(!audioCtx) return;
  const o = audioCtx.createOscillator(), g = audioCtx.createGain();
  o.type='square'; o.frequency.value=950;
  g.gain.setValueAtTime(0.05, audioCtx.currentTime);
  g.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + 0.04);
  o.connect(g).connect(audioCtx.destination);
  o.start(); o.stop(audioCtx.currentTime + 0.04);
}

let rotation = 0, spinning = false, isLocked = false;
const spinBtn = document.getElementById('spinBtn');
const resultEl = document.getElementById('result');
const cooldownBox = document.getElementById('cooldownBox');
const timerEl = document.getElementById('timer');

// التحقق من الحالة عند فتح الموقع
async function checkStatus(){
    try {
        const r = await fetch('/status');
        const data = await r.json();
        if(data.locked){
            lockWheel(data.remaining);
        } else {
            unlockWheel();
        }
    } catch(e){ console.log("خطأ جلب الحالة:", e); }
}

function lockWheel(remainingSecs){
    isLocked = true;
    spinBtn.disabled = true;
    cooldownBox.classList.add('show');
    startTimer(remainingSecs);
}

function unlockWheel(){
    isLocked = false;
    spinBtn.disabled = false;
    cooldownBox.classList.remove('show');
    if(window.countdownInterval) clearInterval(window.countdownInterval);
}

function startTimer(seconds){
    if(window.countdownInterval) clearInterval(window.countdownInterval);
    let rem = seconds;
    
    function update(){
        if(rem <= 0){
            clearInterval(window.countdownInterval);
            unlockWheel();
            return;
        }
        const h = Math.floor(rem / 3600).toString().padStart(2, '0');
        const m = Math.floor((rem % 3600) / 60).toString().padStart(2, '0');
        const s = (rem % 60).toString().padStart(2, '0');
        timerEl.textContent = `${h}:${m}:${s}`;
        rem--;
    }
    update();
    window.countdownInterval = setInterval(update, 1000);
}

checkStatus();

spinBtn.addEventListener('click', async ()=>{
  if(spinning || isLocked) return;
  
  // التحقق من السيرفر مرة أخيرة
  const r = await fetch('/status');
  const data = await r.json();
  if(data.locked){ lockWheel(data.remaining); return; }

  spinning = true;
  spinBtn.disabled = true;
  resultEl.classList.remove('show','win','lose');
  resultEl.textContent = '';
  ensureAudio();

  // إبلاغ السيرفر أن اللاعب لعب
  await fetch('/record', {method:'POST'});

  const targetCenter = LOSE_INDEX*segAngle + segAngle/2;
  const extraTurns = 6 + Math.floor(Math.random()*4);
  const base = rotation - (rotation % 360);
  const finalRotation = base + extraTurns*360 + (360 - targetCenter);
  const duration = 6000;
  const startTime = performance.now();
  const startRot = rotation;
  const delta = finalRotation - startRot;
  let lastSeg = -1;

  function easeOutCubic(t){ return 1 - Math.pow(1-t,3); }

  function frame(now){
    const elapsed = now - startTime;
    const t = Math.min(elapsed/duration, 1);
    rotation = startRot + delta*easeOutCubic(t);
    ROT.style.transform = `rotate(${rotation}deg)`;
    
    if(t < 0.985){
      const seg = Math.floor((((rotation % 360) + 360) % 360) / segAngle);
      if(seg !== lastSeg){ lastSeg = seg; tick(); }
    }
    
    if(t < 1){
      requestAnimationFrame(frame);
    } else {
      spinning = false;
      showResult();
      lockWheel(86400); // قفل 24 ساعة
    }
  }
  requestAnimationFrame(frame);
});

function showResult(){
  resultEl.textContent = 'حظ أوفر 😔';
  resultEl.classList.add('show', 'lose');
}
</script>
</body>
</html>
"""
    page = page.replace("__BG_IMAGE__", bg_b64)
    page = page.replace("__AUDIO_VER__", str(audio_version))
    return page

# ==========================================================
# 🌐 السيرفر
# ==========================================================
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        client_ip = self.client_address[0]

        if self.path.startswith('/audio'):
            if os.path.exists(AUDIO_FILE):
                with open(AUDIO_FILE, "rb") as f:
                    audio_data = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'audio/ogg')
                self.send_header('Content-Length', str(len(audio_data)))
                self.end_headers()
                self.wfile.write(audio_data)
            else:
                self.send_response(404); self.end_headers()
            return

        if self.path == '/status':
            locked = not can_spin(client_ip)
            remaining = get_remaining(client_ip) if locked else 0
            self._json({'locked': locked, 'remaining': remaining})
            return

        body = build_page().encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        client_ip = self.client_address[0]
        if self.path == '/record':
            record_spin(client_ip)
            self._json({'ok': True})
        else:
            self.send_response(404); self.end_headers()

    def _json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args): pass

def start_server():
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"🌐 السيرفر يعمل على: http://localhost:{PORT}")
        httpd.serve_forever()

if __name__ == '__main__':
    threading.Thread(target=bot_loop, daemon=True).start()
    start_server()