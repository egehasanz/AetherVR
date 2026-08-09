import discord
from discord.ext import commands, tasks
import json
import os
import requests
import hashlib
import base64
import random
from datetime import datetime
from urllib.parse import urlparse, parse_qs

# --- AYARLAR ---
# Token'ı artık Railway'deki Variables sekmesinden çekecek
BOT_TOKEN = os.getenv("BOT_TOKEN") 
CLIENT_ID = "1417273808645259344"
GUILD_ID = 1515086899872796822     # Senin sunucu ID'n
BOOST_ROLE_ID = 1536136751565906013 # Boost rolü ID'n
ANNOUNCEMENT_CHANNEL_ID = 1536152946394529802 # Redeploy duyuru kanalı ID'si
DB_FILE = "veritabani.json"
LOG_FILE = "log.json"

# --- BOTUN DURUMUNDA YAZACAK ÖZEL VR SEÇENEKLERİ ---
VR_ACTIVITIES = [
    "Meta Quest VR ile oynuyor",
    "Quest OS Ana Menüde",
    "VRChat dünyalarını geziyor",
    "https://discord.gg/allahinaslanlari"
]

# --- LOG FONKSİYONU ---
def add_log(event_type, message):
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except:
            logs = []
    
    log_entry = {
        "zaman": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tur": event_type,
        "detay": message
    }
    
    logs.append(log_entry)
    if len(logs) > 500:
        logs = logs[-500:]
        
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=4, ensure_ascii=False)

# --- JSON VERİTABANI YÖNETİCİSİ ---
def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=".", intents=intents)

# PKCE Üretici
def generate_pkce():
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode('utf-8')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).rstrip(b'=').decode('utf-8')
    return code_verifier, code_challenge

VERIFIER_STORE = {}

class VRModal(discord.ui.Modal, title="Meta / Oculus Bağlantısı"):
    url_input = discord.ui.TextInput(
        label="Oculus Yönlendirme Linki",
        placeholder="https://www.oculus.com/oauth_account_linking/login_redirect?code=...",
        style=discord.TextStyle.long
    )

    def __init__(self, code_verifier):
        super().__init__()
        self.code_verifier = code_verifier

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        redirected_url = self.url_input.value.strip()

        try:
            parsed = urlparse(redirected_url)
            code = parse_qs(parsed.query).get('code', [None])[0]
            if not code:
                raise ValueError()
        except:
            add_log("HATA", f"Kullanıcı hatalı link girdi: {interaction.user} ({interaction.user.id})")
            await interaction.followup.send("❌ Hatalı link girdin, lütfen oculus.com ile başlayan tam adresi yapıştır.", ephemeral=True)
            return

        data = {
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://oculus.com/oauth_account_linking/login_redirect",
            "code_verifier": self.code_verifier,
        }
        
        response = requests.post("https://discord.com/api/v10/oauth2/token", data=data)
        
        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data["access_token"]
            refresh_token = token_data.get("refresh_token", "")
            
            db = load_db()
            db[str(interaction.user.id)] = {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "status_type": "dnd"
            }
            save_db(db)
            
            add_log("BASARILI", f"Kullanıcı VR hesabını bağladı: {interaction.user} ({interaction.user.id})")
            await interaction.followup.send("✅ **İşlem Başarılı!** Sistem başarıyla onaylandı.", ephemeral=True)
        else:
            add_log("API_HATA", f"Discord/Meta token alınamadı. Kod: {response.status_code}, Kullanıcı: {interaction.user}")
            await interaction.followup.send("❌ Discord/Meta tarafında yetki alınamadı. Linkin süresi dolmuş olabilir, tekrar dene.", ephemeral=True)

class VRView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔗 VR Hesabını Bağla", style=discord.ButtonStyle.green, custom_id="vr_baglan_btn")
    async def baglan_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = bot.get_guild(GUILD_ID)
        member = guild.get_member(interaction.user.id)
        
        if not member or not any(role.id == BOOST_ROLE_ID for role in member.roles):
            await interaction.response.send_message("❌ Bu sistemi kullanabilmek için sunucumuza **Boost** basmış olman gerekiyor!", ephemeral=True)
            return

        code_verifier, code_challenge = generate_pkce()
        VERIFIER_STORE[interaction.user.id] = code_verifier

        auth_url = (
            f"https://discord.com/oauth2/authorize"
            f"?client_id={CLIENT_ID}"
            f"&redirect_uri=https://oculus.com/oauth_account_linking/login_redirect"
            f"&response_type=code"
            f"&scope=identify"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
        )

        embed = discord.Embed(
            title="🥽 Meta Quest Entegrasyon Adımları",
            description="Sistemi onaylamak için aşağıdaki adımları takip et:",
            color=discord.Color.from_rgb(88, 101, 242)
        )
        embed.add_field(
            name="1️⃣ Yetkilendirme Sayfasına Git",
            value="Aşağıdaki **🌐 Meta ile Giriş Yap** butonuna tıklayarak onay ver.",
            inline=False
        )
        embed.add_field(
            name="2️⃣ Yönlendirme Linkini Kopyala",
            value="Yönlendirildiğin sayfanın adres çubuğundaki (`https://oculus.com/...`) adresi **tam olarak** kopyala.",
            inline=False
        )
        embed.add_field(
            name="3️⃣ Linki Sisteme İlet",
            value="**📝 Kopyaladığım Linki Gir** butonuna tıklayıp açılan kutucuğa yapıştır.",
            inline=False
        )

        class ActionView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=180)
                self.add_item(discord.ui.Button(label="🌐 Meta ile Giriş Yap", style=discord.ButtonStyle.link, url=auth_url))

            @discord.ui.button(label="📝 Kopyaladığım Linki Gir", style=discord.ButtonStyle.primary, custom_id="modal_trigger_btn")
            async def open_modal(self, inner_interaction: discord.Interaction, inner_button: discord.ui.Button):
                await inner_interaction.response.send_modal(VRModal(VERIFIER_STORE[inner_interaction.user.id]))

        await interaction.response.send_message(embed=embed, view=ActionView(), ephemeral=True)

    @discord.ui.button(label="🔌 Bağlantıyı Kes", style=discord.ButtonStyle.red, custom_id="vr_kopar_btn")
    async def kopar_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_db()
        user_id_str = str(interaction.user.id)
        if user_id_str in db:
            del db[user_id_str]
            save_db(db)
            add_log("KOPARMA", f"Kullanıcı bağlantıyı kesti: {interaction.user} ({interaction.user.id})")
            await interaction.response.send_message("🔌 Kayıt sisteminden kaldırıldı.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Zaten aktif bir kaydın bulunmuyor.", ephemeral=True)

@bot.event
async def on_ready():
    print(f"Bot aktif: {bot.user.name}")
    add_log("BILGI", f"Bot aktifleşti: {bot.user.name}")
    bot.add_view(VRView())
    
    # VR durum döngüsünü başlat
    if not bot_vr_status_loop.is_running():
        bot_vr_status_loop.start()

    # Redeploy duyuru mesajını ilgili kanala gönder
    channel = bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)
    if channel:
        try:
            await channel.send("Bot redeploy oldu VRlarınızı tekrar etkinleştirin.")
            add_log("DUYURU", f"Redeploy mesajı {ANNOUNCEMENT_CHANNEL_ID} kanalına gönderildi.")
        except Exception as e:
            add_log("HATA", f"Duyuru mesajı gönderilemedi: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def kurulumpanel(ctx):
    embed = discord.Embed(
        title="🥽 Meta Quest Entegrasyon Merkezi",
        description=(
            "Sunucumuza **Boost** basarak sisteme dahil olabilirsin!\n\n"
            "🚀 **Nasıl Aktif Edilir?**\n"
            "Aşağıdaki **🔗 VR Hesabını Bağla** butonuna tıklayarak adımları takip etmeniz yeterlidir."
        ),
        color=discord.Color.from_rgb(88, 101, 242)
    )
    await ctx.send(embed=embed, view=VRView())
    await ctx.message.delete()
    add_log("PANEL", f"Kurulum paneli oluşturuldu: {ctx.channel.name} ({ctx.author})")

@bot.command()
@commands.has_permissions(administrator=True)
async def aktifler(ctx):
    db = load_db()
    guild = bot.get_guild(GUILD_ID)
    
    if not guild:
        await ctx.send("❌ Sunucu bulunamadı.", delete_after=10)
        return

    aktif_kullanicilar = []
    for discord_id in db.keys():
        member = guild.get_member(int(discord_id))
        if member:
            aktif_kullanicilar.append(f"• {member.mention} (`{member.name}`)")

    embed = discord.Embed(
        title="🥽 Sisteme Kayıtlı Kullanıcılar",
        color=discord.Color.green()
    )

    if aktif_kullanicilar:
        embed.description = "\n".join(aktif_kullanicilar)
        embed.set_footer(text=f"Toplam Kayıtlı: {len(aktif_kullanicilar)}")
    else:
        embed.description = "Şu anda sistemde kayıtlı kimse yok."

    await ctx.send(embed=embed)
    await ctx.message.delete()

# Botun kendi profilinde VR durumlarını döndüren döngü
@tasks.loop(seconds=45)
async def bot_vr_status_loop():
    chosen_activity_name = random.choice(VR_ACTIVITIES)
    activity = discord.Activity(type=discord.ActivityType.playing, name=chosen_activity_name)
    await bot.change_presence(activity=activity)

# Token kontrolü ekleyelim ki variable girilmediğinde ne olduğunu anla
if not BOT_TOKEN:
    print("HATA: BOT_TOKEN çevre değişkeni bulunamadı! Lütfen Railway paneline ekle.")
else:
    bot.run(BOT_TOKEN)